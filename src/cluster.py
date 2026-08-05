import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime


def _tags(row: sqlite3.Row) -> list[str]:
    try:
        return json.loads(row["tags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def category_breakdown(rows: list[sqlite3.Row]) -> list[dict]:
    """Frequency + example bugs per category."""
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        cat = (r["category"] or "Unknown").strip()
        groups[cat].append(r)

    result = []
    for cat, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        result.append({
            "category": cat,
            "count": len(items),
            "pct": round(100 * len(items) / max(len(rows), 1), 1),
            "examples": [{"key": i["key"], "summary": i["summary"]} for i in items[:3]],
        })
    return result


def subsystem_breakdown(rows: list[sqlite3.Row]) -> list[dict]:
    counter = Counter((r["subsystem"] or "Unknown").strip() for r in rows)
    total = max(len(rows), 1)
    return [
        {"subsystem": s, "count": c, "pct": round(100 * c / total, 1)}
        for s, c in counter.most_common(20)
    ]


def top_tags(rows: list[sqlite3.Row], top_n: int = 30) -> list[dict]:
    counter: Counter = Counter()
    for r in rows:
        counter.update(_tags(r))
    return [{"tag": t, "count": c} for t, c in counter.most_common(top_n)]


def severity_breakdown(rows: list[sqlite3.Row]) -> dict:
    """
    For each category, show the S1/S2/S3 distribution.
    Useful to see which categories produce the most critical bugs.
    """
    data: dict[str, dict[str, int]] = defaultdict(lambda: {"S1": 0, "S2": 0, "S3": 0, "Unknown": 0})
    for r in rows:
        cat = (r["category"] or "Unknown").strip()
        sev = (r["severity"] or "Unknown").upper()
        bucket = sev if sev in ("S1", "S2", "S3") else "Unknown"
        data[cat][bucket] += 1
    return {
        cat: dict(counts)
        for cat, counts in sorted(data.items(), key=lambda x: -(x[1]["S1"] * 3 + x[1]["S2"]))
    }


def probability_breakdown(rows: list[sqlite3.Row]) -> dict:
    """For each category, show the P1/P2/P3 distribution."""
    data: dict[str, dict[str, int]] = defaultdict(lambda: {"P1": 0, "P2": 0, "P3": 0, "Unknown": 0})
    for r in rows:
        cat = (r["category"] or "Unknown").strip()
        prob = (r["probability"] or "Unknown").upper()
        bucket = prob if prob in ("P1", "P2", "P3") else "Unknown"
        data[cat][bucket] += 1
    return {cat: dict(counts) for cat, counts in data.items()}


def high_impact_bugs(rows: list[sqlite3.Row]) -> list[dict]:
    """Return S1+P1 bugs (the most critical ones) for spot-checking."""
    result = []
    for r in rows:
        sev = (r["severity"] or "").upper()
        prob = (r["probability"] or "").upper()
        if sev == "S1" and prob == "P1":
            result.append({
                "key": r["key"],
                "summary": r["summary"],
                "category": r["category"],
                "root_cause": r["root_cause"],
                "cell": r["cell"],
            })
    return result


def team_heatmap(rows: list[sqlite3.Row]) -> dict[str, dict[str, int]]:
    """
    Returns {team: {category: count}} — shows which teams produce which bug types.
    """
    heatmap: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        team = (r["cell"] or "Unknown").replace("Team-", "")
        cat = (r["category"] or "Unknown").strip()
        heatmap[team][cat] += 1
    return {t: dict(cats) for t, cats in heatmap.items()}


def temporal_trend(rows: list[sqlite3.Row], top_categories: int = 5) -> dict:
    """
    Returns {category: {YYYY-MM: count}} for the top N categories,
    letting you see which categories are rising or falling over time.
    """
    # Determine top N categories
    cat_counter = Counter((r["category"] or "Unknown").strip() for r in rows)
    top_cats = {c for c, _ in cat_counter.most_common(top_categories)}

    trend: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        cat = (r["category"] or "Unknown").strip()
        if cat not in top_cats:
            continue
        created = r["created"] or ""
        if created:
            try:
                month = datetime.fromisoformat(created[:10]).strftime("%Y-%m")
            except ValueError:
                month = "unknown"
        else:
            month = "unknown"
        trend[cat][month] += 1

    return {cat: dict(sorted(months.items())) for cat, months in trend.items()}


def semantic_duplicates(rows: list[sqlite3.Row], similarity_threshold: float = 0.8) -> list[dict]:
    """
    Within each category, group bugs whose root_cause text overlaps heavily.
    Uses simple token overlap (Jaccard) — no embedding needed.
    """
    groups_by_cat: dict[str, list] = defaultdict(list)
    for r in rows:
        groups_by_cat[(r["category"] or "Unknown").strip()].append(r)

    clusters = []
    for cat, items in groups_by_cat.items():
        seen: list[tuple[frozenset, list]] = []
        for r in items:
            tokens = frozenset((r["root_cause"] or "").lower().split())
            if not tokens:
                continue
            matched = False
            for existing_tokens, group in seen:
                if not existing_tokens:
                    continue
                jaccard = len(tokens & existing_tokens) / len(tokens | existing_tokens)
                if jaccard >= similarity_threshold:
                    group.append({"key": r["key"], "summary": r["summary"]})
                    matched = True
                    break
            if not matched:
                seen.append((tokens, [{"key": r["key"], "summary": r["summary"]}]))

        # Only report clusters with 2+ members
        for _, group in seen:
            if len(group) >= 2:
                clusters.append({"category": cat, "size": len(group), "bugs": group})

    return sorted(clusters, key=lambda x: -x["size"])
