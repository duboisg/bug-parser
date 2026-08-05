import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "output" / "bugs.db"

# ── exact custom field IDs for this JIRA instance ───────────────────────────
CF_CELL        = "customfield_11426"   # Cell (owning team)
CF_STEPS       = "customfield_10007"   # Steps To Reproduce
CF_SEVERITY    = "customfield_10004"   # Severity  (S1 / S2 / S3)
CF_PROBABILITY = "customfield_10221"   # Probability (P1 / P2 / P3)
CF_UBI_PRIO    = "customfield_10222"   # Ubi Priority (composite ranking)
CF_TECH_REPRO  = "customfield_10006"   # Technical Reproductibility
CF_MOB_PLAT    = "customfield_11188"   # Mobile Platform
CF_LAST_BUILD  = "customfield_15696"   # Last Observed On Build
CF_OBS_BUILDS  = "customfield_15697"   # Observed On Builds


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bugs (
                key          TEXT PRIMARY KEY,
                project      TEXT NOT NULL,
                summary      TEXT,
                description  TEXT,
                steps        TEXT,
                cell         TEXT,
                severity     TEXT,
                probability  TEXT,
                ubi_priority TEXT,
                status       TEXT,
                resolution   TEXT,
                created      TEXT,
                updated      TEXT,
                fix_versions TEXT,
                raw_json     TEXT,
                fetched_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS analyses (
                key          TEXT PRIMARY KEY,
                root_cause   TEXT,
                category     TEXT,
                subsystem    TEXT,
                tags         TEXT,
                confidence   REAL,
                raw_response TEXT,
                analyzed_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (key) REFERENCES bugs(key)
            );

            CREATE INDEX IF NOT EXISTS idx_bugs_project  ON bugs(project);
            CREATE INDEX IF NOT EXISTS idx_bugs_status   ON bugs(status);
            CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);
            CREATE INDEX IF NOT EXISTS idx_analyses_cat  ON analyses(category);
        """)

        # Non-destructive migrations for existing DBs
        _add_column_if_missing(conn, "bugs", "probability",  "TEXT")
        _add_column_if_missing(conn, "bugs", "ubi_priority", "TEXT")


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def upsert_bug(issue: dict):
    fields = issue.get("fields", {})

    fix_versions = fields.get("fixVersions") or []
    fix_ver_str = json.dumps([v.get("name") for v in fix_versions])

    with db() as conn:
        conn.execute("""
            INSERT INTO bugs
                (key, project, summary, description, steps, cell,
                 severity, probability, ubi_priority,
                 status, resolution, created, updated,
                 fix_versions, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                summary      = excluded.summary,
                description  = excluded.description,
                steps        = excluded.steps,
                cell         = excluded.cell,
                severity     = excluded.severity,
                probability  = excluded.probability,
                ubi_priority = excluded.ubi_priority,
                status       = excluded.status,
                resolution   = excluded.resolution,
                updated      = excluded.updated,
                fix_versions = excluded.fix_versions,
                raw_json     = excluded.raw_json,
                fetched_at   = CURRENT_TIMESTAMP
        """, (
            issue.get("key"),
            issue.get("key", "").split("-")[0],
            fields.get("summary"),
            fields.get("description"),
            _pick(fields, CF_STEPS),
            _pick(fields, CF_CELL),
            _pick(fields, CF_SEVERITY),
            _pick(fields, CF_PROBABILITY),
            _pick(fields, CF_UBI_PRIO),
            (fields.get("status") or {}).get("name"),
            (fields.get("resolution") or {}).get("name"),
            fields.get("created"),
            fields.get("updated"),
            fix_ver_str,
            json.dumps(issue),
        ))


def upsert_analysis(key: str, result: dict, raw_response: str):
    with db() as conn:
        conn.execute("""
            INSERT INTO analyses (key, root_cause, category, subsystem, tags, confidence, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                root_cause   = excluded.root_cause,
                category     = excluded.category,
                subsystem    = excluded.subsystem,
                tags         = excluded.tags,
                confidence   = excluded.confidence,
                raw_response = excluded.raw_response,
                analyzed_at  = CURRENT_TIMESTAMP
        """, (
            key,
            result.get("root_cause"),
            result.get("category"),
            result.get("subsystem"),
            json.dumps(result.get("tags", [])),
            result.get("confidence"),
            raw_response,
        ))


def count_bugs() -> int:
    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM bugs").fetchone()[0]


def count_analyses() -> int:
    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]


def get_unanalyzed(limit: int = 0, retry_errors: bool = False) -> list[sqlite3.Row]:
    if retry_errors:
        sql = """
            SELECT b.* FROM bugs b
            LEFT JOIN analyses a ON b.key = a.key
            WHERE a.key IS NULL
               OR a.category IN ('parse_error', 'llm_error')
            ORDER BY b.created DESC
        """
    else:
        sql = """
            SELECT b.* FROM bugs b
            LEFT JOIN analyses a ON b.key = a.key
            WHERE a.key IS NULL
            ORDER BY b.created DESC
        """
    if limit > 0:
        sql += f" LIMIT {limit}"
    with db() as conn:
        return conn.execute(sql).fetchall()


def get_all_analyses() -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute("""
            SELECT b.key, b.summary, b.cell, b.severity, b.probability,
                   b.ubi_priority, b.status, b.created, b.fix_versions,
                   a.root_cause, a.category, a.subsystem, a.tags, a.confidence
            FROM bugs b
            JOIN analyses a ON b.key = a.key
            ORDER BY b.created DESC
        """).fetchall()


# ── field extraction helpers ─────────────────────────────────────────────────

def _pick(fields: dict, cf_id: str) -> str | None:
    """Extract a value from a JIRA custom field, handling all common formats."""
    val = fields.get(cf_id)
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip() or None
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        # Single select: {"value": "S1"} or {"name": "S1"} or {"id": "...", "value": "..."}
        for key in ("value", "name", "displayName"):
            if key in val and val[key]:
                return str(val[key]).strip()
    if isinstance(val, list):
        # Multi-select or array of objects
        parts = []
        for item in val:
            if isinstance(item, dict):
                for key in ("value", "name"):
                    if key in item and item[key]:
                        parts.append(str(item[key]))
                        break
            elif isinstance(item, str):
                parts.append(item)
        return ", ".join(parts) if parts else None
    return None
