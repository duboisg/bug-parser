import json
import sqlite3
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src import cluster as cl
from src.llm_client import chat

OUTPUT_DIR = Path(__file__).parent.parent / "output"
console = Console()


def _title(text: str) -> None:
    console.print(f"\n[bold cyan]{text}[/bold cyan]")


def print_category_table(breakdown: list[dict], sev_data: dict) -> None:
    _title("Root Cause Categories")
    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("Category", style="yellow", min_width=26)
    t.add_column("Count", justify="right", style="bold white")
    t.add_column("  %", justify="right", style="dim")
    t.add_column("S1", justify="right", style="red")
    t.add_column("S2", justify="right", style="yellow")
    t.add_column("S3", justify="right", style="dim")
    t.add_column("Examples", style="dim", max_width=50)

    for row in breakdown:
        cat = row["category"]
        sev = sev_data.get(cat, {})
        examples = " | ".join(e["key"] for e in row["examples"])
        t.add_row(
            cat,
            str(row["count"]),
            f"{row['pct']}%",
            str(sev.get("S1", 0)) or "-",
            str(sev.get("S2", 0)) or "-",
            str(sev.get("S3", 0)) or "-",
            examples,
        )

    console.print(t)


def print_subsystem_table(breakdown: list[dict]) -> None:
    _title("Top Subsystems / Processes")
    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("Subsystem", style="magenta", min_width=32)
    t.add_column("Count", justify="right", style="bold white")
    t.add_column("  %", justify="right", style="dim")

    for row in breakdown[:15]:
        t.add_row(row["subsystem"], str(row["count"]), f"{row['pct']}%")

    console.print(t)


def print_high_impact(bugs: list[dict]) -> None:
    if not bugs:
        return
    _title(f"S1 + P1 Spotlight  ({len(bugs)} critical bugs)")
    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("Key", style="red bold", min_width=14)
    t.add_column("Category", style="yellow", min_width=22)
    t.add_column("Cell", style="cyan", min_width=16)
    t.add_column("Root Cause", style="white", max_width=60)

    for b in bugs[:20]:
        t.add_row(b["key"], b["category"] or "?", b["cell"] or "?", b["root_cause"] or "")

    console.print(t)


def print_tag_cloud(tags: list[dict]) -> None:
    _title("Top Tags")
    parts = []
    for entry in tags[:30]:
        weight = entry["count"]
        style = "bold white" if weight > 10 else ("white" if weight > 4 else "dim")
        parts.append(f"[{style}]{entry['tag']}({weight})[/{style}]")
    console.print("  " + "  ".join(parts))


def print_team_heatmap(heatmap: dict) -> None:
    if not heatmap:
        return
    _title("Team × Category Heatmap")

    all_cats: list[str] = []
    for cats in heatmap.values():
        all_cats.extend(cats.keys())
    top_cats = [c for c, _ in sorted(
        {c: sum(heatmap[t].get(c, 0) for t in heatmap) for c in all_cats}.items(),
        key=lambda x: -x[1]
    )[:8]]

    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("Team", style="cyan", min_width=20)
    for cat in top_cats:
        t.add_column(cat[:18], justify="right", min_width=6)

    for team, cats in sorted(heatmap.items()):
        row_vals = []
        for cat in top_cats:
            v = cats.get(cat, 0)
            row_vals.append(f"[bold]{v}[/bold]" if v > 0 else "[dim]-[/dim]")
        t.add_row(team, *row_vals)

    console.print(t)


def print_temporal_trend(trend: dict) -> None:
    if not trend:
        return
    _title("Monthly Trend — Top Categories")
    for cat, months in trend.items():
        bar_parts = [f"{m}:{c}" for m, c in list(months.items())[-6:]]
        console.print(f"  [yellow]{cat:<30}[/yellow] {' | '.join(bar_parts)}")


def print_semantic_duplicates(clusters: list[dict], max_shown: int = 10) -> None:
    if not clusters:
        return
    _title(f"Semantic Duplicate Clusters  ({len(clusters)} found)")
    for clust in clusters[:max_shown]:
        keys = ", ".join(b["key"] for b in clust["bugs"][:5])
        console.print(f"  [{clust['category']}] {clust['size']} bugs — {keys}")


def llm_narrative(breakdown: list[dict], sev_data: dict, total: int) -> str:
    top = breakdown[:10]
    lines = []
    for r in top:
        sev = sev_data.get(r["category"], {})
        lines.append(
            f"- {r['category']}: {r['count']} bugs ({r['pct']}%)  "
            f"[S1={sev.get('S1',0)}, S2={sev.get('S2',0)}, S3={sev.get('S3',0)}]"
        )

    prompt = f"""You are a QA lead summarising a bug database for a AAA video game studio.

Total analyzed bugs: {total}
Top root cause categories with severity breakdown (S1=must-fix, S2=quality, S3=nice-to-have):
{chr(10).join(lines)}

Write a concise 3-paragraph strategic summary:
1. The single biggest quality risk and what it signals about the production pipeline.
2. The second and third categories and what process changes could address them.
3. A concrete recommendation the team can act on in the next sprint.

Be direct and specific. No bullet points."""

    try:
        return chat([{"role": "user", "content": prompt}], temperature=0.4)
    except Exception as e:
        return f"(LLM narrative unavailable: {e})"


def run_report(rows: list[sqlite3.Row], with_narrative: bool = True) -> None:
    if not rows:
        console.print("[red]No analyzed bugs found. Run 'analyze' first.[/red]")
        return

    console.print(Panel(
        f"[bold]Bug Base Analysis[/bold]\n{len(rows)} bugs analyzed  •  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        style="bold blue",
    ))

    breakdown  = cl.category_breakdown(rows)
    subsystems = cl.subsystem_breakdown(rows)
    tags       = cl.top_tags(rows)
    heatmap    = cl.team_heatmap(rows)
    trend      = cl.temporal_trend(rows)
    dupes      = cl.semantic_duplicates(rows)
    sev_data   = cl.severity_breakdown(rows)
    critical   = cl.high_impact_bugs(rows)

    print_category_table(breakdown, sev_data)
    print_high_impact(critical)
    print_subsystem_table(subsystems)
    print_tag_cloud(tags)
    print_team_heatmap(heatmap)
    print_temporal_trend(trend)
    print_semantic_duplicates(dupes)

    if with_narrative:
        _title("Strategic Summary (LLM)")
        narrative = llm_narrative(breakdown, sev_data, len(rows))
        console.print(Panel(narrative, style="green", padding=(1, 2)))

    _save_json(rows, breakdown, subsystems, tags, heatmap, trend, dupes, sev_data, critical)


def _save_json(rows, breakdown, subsystems, tags, heatmap, trend, dupes, sev_data, critical):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "generated_at": datetime.now().isoformat(),
        "total_analyzed": len(rows),
        "category_breakdown": breakdown,
        "severity_by_category": sev_data,
        "subsystem_breakdown": subsystems,
        "top_tags": tags,
        "team_heatmap": heatmap,
        "temporal_trend": trend,
        "semantic_duplicate_clusters": [{**c, "bugs": c["bugs"][:10]} for c in dupes[:50]],
        "s1_p1_critical_bugs": critical,
    }
    path = OUTPUT_DIR / "report.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    console.print(f"\n[dim]JSON report saved → {path}[/dim]")
