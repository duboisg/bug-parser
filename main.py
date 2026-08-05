#!/usr/bin/env python3
"""
Bug Parser — root cause analysis for JIRA Bug QC issues.

Commands:
  fetch    Pull Bug QC issues from JIRA into local SQLite cache.
  analyze  Run LLM root-cause extraction on cached bugs.
  report   Generate pattern report from analyzed bugs.
  all      fetch -> analyze -> report in sequence.
  fields   List all custom fields on your JIRA instance (useful for debugging).
"""
import argparse
import sys
from datetime import date

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


def _parse_iso(value: str, arg_name: str) -> str:
    """Validate and normalise an ISO date string (YYYY-MM-DD or YYYY-MM)."""
    try:
        date.fromisoformat(value) if len(value) == 10 else date.fromisoformat(value + "-01")
    except ValueError:
        sys.exit(f"[date] --{arg_name} must be an ISO date (YYYY-MM-DD), got: {value!r}")
    return value


def _build_date_jql(args) -> str:
    """Build a JQL `created` range clause from --from-date / --to-date if provided."""
    parts = []
    from_date = getattr(args, "from_date", None)
    to_date   = getattr(args, "to_date", None)
    if from_date:
        parts.append(f'created >= "{_parse_iso(from_date, "from-date")}"')
    if to_date:
        parts.append(f'created <= "{_parse_iso(to_date, "to-date")}"')
    return " AND ".join(parts)


def _combined_jql(args) -> str:
    base      = getattr(args, "jql", "") or ""
    date_part = _build_date_jql(args)
    return " AND ".join(filter(None, [base, date_part]))


def cmd_fetch(args):
    from src import store, jira_client

    store.init_db()
    extra_jql = _combined_jql(args)

    print("Counting bugs…")
    try:
        total = jira_client.fetch_total(
            projects=args.projects,
            extra_jql=extra_jql,
        )
    except Exception as e:
        sys.exit(f"[JIRA] Failed to connect: {e}")

    limit = min(args.limit, total) if args.limit else total
    print(f"Found {total} Bug QC issues — fetching up to {limit}…\n")

    fetched = 0
    with tqdm(total=limit, unit="bug") as bar:
        for issue in jira_client.fetch_bugs(
            projects=args.projects,
            max_results=limit,
            extra_jql=extra_jql,
            page_size=100,
        ):
            store.upsert_bug(issue)
            fetched += 1
            bar.update(1)

    print(f"\nDone. {fetched} bugs stored. Total in DB: {store.count_bugs()}")


def cmd_analyze(args):
    from src import store, analyzer

    store.init_db()
    retry = getattr(args, "retry_errors", False)
    pending = store.get_unanalyzed(limit=args.limit or 0, retry_errors=retry)

    if not pending:
        print("No unanalyzed bugs found.")
        return

    print(f"{len(pending)} bugs to analyze…\n")
    errors = 0

    with tqdm(pending, unit="bug") as bar:
        for row in bar:
            bar.set_description(row["key"])
            result, raw = analyzer.analyze_bug(row)
            store.upsert_analysis(row["key"], result, raw)
            if result["category"] in ("parse_error", "llm_error"):
                errors += 1

    total = store.count_analyses()
    print(f"\nDone. {total} total analyses. {errors} errors.")


def cmd_report(args):
    from src import store, report

    store.init_db()
    rows = store.get_all_analyses()

    if not rows:
        print("No analyzed bugs. Run 'analyze' first.")
        return

    report.run_report(rows, with_narrative=not args.no_narrative)


def cmd_fields(args):
    from src import jira_client

    print("Discovering JIRA fields…")
    try:
        fields = jira_client.discover_fields()
    except Exception as e:
        sys.exit(f"Failed: {e}")

    custom = {k: v for k, v in fields.items() if k.startswith("customfield_")}
    print(f"\n{len(custom)} custom fields:\n")
    for fid, name in sorted(custom.items(), key=lambda x: x[1]):
        print(f"  {fid:<25} {name}")


def cmd_all(args):
    cmd_fetch(args)
    cmd_analyze(args)
    cmd_report(args)


def cmd_sample(args):
    """Fetch the 50 most recent Bug QC issues and run the full pipeline on them."""
    import types
    sample_args = types.SimpleNamespace(
        projects=None,
        limit=50,
        jql="",
        from_date=getattr(args, "from_date", None),
        to_date=getattr(args, "to_date", None),
        no_narrative=False,
    )
    cmd_fetch(sample_args)
    cmd_analyze(sample_args)
    cmd_report(sample_args)


def main():
    parser = argparse.ArgumentParser(
        description="Bug Parser — LLM-powered root cause analysis for JIRA Bug QC issues.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── fetch ─────────────────────────────────────────────────────────────────
    p_fetch = sub.add_parser("fetch", help="Pull bugs from JIRA")
    p_fetch.add_argument("--projects", nargs="+", metavar="KEY",
                         help="Override JIRA_PROJECT_KEYS (e.g. --projects MAG MA)")
    p_fetch.add_argument("--limit", type=int, default=0,
                         help="Max bugs to fetch (0 = all)")
    p_fetch.add_argument("--jql", default="",
                         help="Extra raw JQL appended to the base query")
    p_fetch.add_argument("--from-date", dest="from_date", metavar="YYYY-MM-DD",
                         help="Only fetch bugs created on or after this date")
    p_fetch.add_argument("--to-date", dest="to_date", metavar="YYYY-MM-DD",
                         help="Only fetch bugs created on or before this date")

    # ── analyze ───────────────────────────────────────────────────────────────
    p_analyze = sub.add_parser("analyze", help="Run LLM root-cause extraction")
    p_analyze.add_argument("--limit", type=int, default=0,
                           help="Max bugs to analyze (0 = all pending)")
    p_analyze.add_argument("--retry-errors", dest="retry_errors", action="store_true",
                           help="Re-analyze bugs whose previous result was parse_error or llm_error")

    # ── report ────────────────────────────────────────────────────────────────
    p_report = sub.add_parser("report", help="Generate pattern report")
    p_report.add_argument("--no-narrative", action="store_true",
                          help="Skip LLM narrative summary")

    # ── all ───────────────────────────────────────────────────────────────────
    p_all = sub.add_parser("all", help="Run fetch -> analyze -> report")
    p_all.add_argument("--projects", nargs="+", metavar="KEY")
    p_all.add_argument("--limit", type=int, default=0)
    p_all.add_argument("--jql", default="")
    p_all.add_argument("--from-date", dest="from_date", metavar="YYYY-MM-DD",
                       help="Only fetch bugs created on or after this date")
    p_all.add_argument("--to-date", dest="to_date", metavar="YYYY-MM-DD",
                       help="Only fetch bugs created on or before this date")
    p_all.add_argument("--no-narrative", action="store_true")

    # ── sample ────────────────────────────────────────────────────────────────
    p_sample = sub.add_parser("sample", help="Fetch the 50 most recent bugs and run the full pipeline")
    p_sample.add_argument("--from-date", dest="from_date", metavar="YYYY-MM-DD",
                          help="Only sample bugs created on or after this date")
    p_sample.add_argument("--to-date", dest="to_date", metavar="YYYY-MM-DD",
                          help="Only sample bugs created on or before this date")

    # ── fields ────────────────────────────────────────────────────────────────
    sub.add_parser("fields", help="List JIRA custom fields")

    args = parser.parse_args()

    dispatch = {
        "fetch": cmd_fetch,
        "analyze": cmd_analyze,
        "report": cmd_report,
        "all": cmd_all,
        "sample": cmd_sample,
        "fields": cmd_fields,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
