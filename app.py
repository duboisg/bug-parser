import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.store import DB_PATH, init_db
from src.cluster import semantic_duplicates

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bug Base Analyzer",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── colour constants ──────────────────────────────────────────────────────────
SEV_COLORS = {"S1": "#e74c3c", "S2": "#f39c12", "S3": "#2ecc71", "Unknown": "#95a5a6"}
PROB_ORDER  = ["P1", "P2", "P3", "Unknown"]
SEV_ORDER   = ["S1", "S2", "S3", "Unknown"]
SEV_NUM     = {"S1": 3, "S2": 2, "S3": 1}
PROB_NUM    = {"P1": 3, "P2": 2, "P3": 1}

JIRA_BASE   = os.getenv("JIRA_BROWSE_URL", "").rstrip("/")


# ── data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_df() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT b.key, b.summary, b.cell, b.severity, b.probability,
               b.ubi_priority, b.status, b.created, b.fix_versions,
               a.root_cause, a.category, a.subsystem, a.tags, a.confidence
        FROM bugs b
        JOIN analyses a ON b.key = a.key
        ORDER BY b.created DESC
    """, conn)
    conn.close()

    # parse JSON columns
    df["tags_list"]     = df["tags"].apply(_parse_json_list)
    df["fix_ver_list"]  = df["fix_versions"].apply(_parse_json_list)
    df["fix_versions_str"] = df["fix_ver_list"].apply(lambda v: ", ".join(v) if v else "")

    # normalise key fields
    df["severity"]    = df["severity"].str.upper().fillna("Unknown")
    df["probability"] = df["probability"].str.upper().fillna("Unknown")
    df["category"]    = df["category"].fillna("Unknown")
    df["cell"]        = df["cell"].str.replace("Team-", "", regex=False).fillna("Unknown")

    # numeric axes for scatter
    df["sev_num"]  = df["severity"].map(SEV_NUM).fillna(0)
    df["prob_num"] = df["probability"].map(PROB_NUM).fillna(0)

    # month bucket
    df["created_dt"] = pd.to_datetime(df["created"], errors="coerce", utc=True)
    df["month"]      = df["created_dt"].dt.to_period("M").astype(str)

    # project prefix
    df["project"] = df["key"].str.split("-").str[0]

    return df


def _parse_json_list(val) -> list:
    try:
        result = json.loads(val or "[]")
        return [x for x in result if x] if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _jira_url(key: str) -> str:
    return f"{JIRA_BASE}/{key}" if JIRA_BASE else ""


# ── sidebar filters ───────────────────────────────────────────────────────────
def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.title("Filters")

    error_cats = {"parse_error", "llm_error"}
    clean = df[~df["category"].isin(error_cats)]

    projects    = sorted(clean["project"].unique())
    teams       = sorted(clean["cell"].unique())
    severities  = [s for s in SEV_ORDER if s in clean["severity"].unique()]
    probs       = [p for p in PROB_ORDER if p in clean["probability"].unique()]
    categories  = sorted(clean["category"].unique())
    fix_versions = sorted({v for vlist in clean["fix_ver_list"] for v in vlist if v})

    sel_proj  = st.sidebar.multiselect("Project",      projects,   default=projects)
    sel_team  = st.sidebar.multiselect("Team",          teams,      default=teams)
    sel_sev   = st.sidebar.multiselect("Severity",      severities, default=severities)
    sel_prob  = st.sidebar.multiselect("Probability",   probs,      default=probs)
    sel_cat   = st.sidebar.multiselect("Category",      categories, default=categories)
    sel_fv    = st.sidebar.multiselect("Fix Version",   fix_versions, default=fix_versions)

    st.sidebar.divider()
    show_errors = st.sidebar.checkbox("Include parse/LLM errors", value=False)

    mask = (
        df["project"].isin(sel_proj) &
        df["cell"].isin(sel_team) &
        df["severity"].isin(sel_sev) &
        df["probability"].isin(sel_prob) &
        df["category"].isin(sel_cat) &
        df["fix_ver_list"].apply(lambda v: not sel_fv or bool(set(v) & set(sel_fv)))
    )

    if not show_errors:
        mask &= ~df["category"].isin(error_cats)

    st.sidebar.divider()
    st.sidebar.caption(f"Showing **{mask.sum()}** of **{len(df)}** analyzed bugs")

    return df[mask].copy()


# ── chart helpers ─────────────────────────────────────────────────────────────
def chart_category_severity(df: pd.DataFrame):
    st.subheader("Root Cause Categories by Severity")

    order = (
        df.groupby("category")["key"].count()
        .sort_values(ascending=False).index.tolist()
    )
    counts = (
        df.groupby(["category", "severity"])["key"]
        .count().reset_index(name="count")
    )

    fig = px.bar(
        counts,
        x="count", y="category",
        color="severity",
        orientation="h",
        color_discrete_map=SEV_COLORS,
        category_orders={"category": order, "severity": SEV_ORDER},
        labels={"count": "Bug Count", "category": "", "severity": "Severity"},
        height=max(350, len(order) * 32),
    )
    fig.update_layout(
        legend_title_text="Severity",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=20, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_priority_matrix(df: pd.DataFrame):
    st.subheader("Priority Matrix")

    import numpy as np
    jitter = 0.15
    plot_df = df.copy()
    plot_df["x"] = plot_df["prob_num"] + np.random.uniform(-jitter, jitter, len(df))
    plot_df["y"] = plot_df["sev_num"]  + np.random.uniform(-jitter, jitter, len(df))
    plot_df["hover"] = plot_df["key"] + "<br>" + plot_df["summary"].str[:60] + "..."

    fig = px.scatter(
        plot_df,
        x="x", y="y",
        color="category",
        hover_name="hover",
        hover_data={"x": False, "y": False, "root_cause": True, "cell": True},
        labels={"x": "Probability →  P3     P2     P1",
                "y": "Severity →  S3   S2   S1"},
        height=380,
    )
    fig.update_layout(
        xaxis=dict(tickvals=[1, 2, 3], ticktext=["P3", "P2", "P1"], range=[0.3, 3.7]),
        yaxis=dict(tickvals=[1, 2, 3], ticktext=["S3", "S2", "S1"], range=[0.3, 3.7]),
        margin=dict(l=0, r=0, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=-0.45),
    )
    # quadrant shading — top-right = most critical
    fig.add_shape(type="rect", x0=2.5, x1=3.7, y0=2.5, y1=3.7,
                  fillcolor="rgba(231,76,60,0.08)", line_width=0)
    st.plotly_chart(fig, use_container_width=True)


def chart_team_heatmap(df: pd.DataFrame):
    st.subheader("Team × Category Heatmap")

    top_cats = (
        df.groupby("category")["key"].count()
        .sort_values(ascending=False).head(8).index.tolist()
    )
    sub = df[df["category"].isin(top_cats)]
    pivot = (
        sub.groupby(["cell", "category"])["key"]
        .count().unstack(fill_value=0)
        .reindex(columns=top_cats, fill_value=0)
    )

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="Blues",
        hoverongaps=False,
        hovertemplate="%{y} — %{x}<br>%{z} bugs<extra></extra>",
        text=pivot.values,
        texttemplate="%{text}",
    ))
    fig.update_layout(
        height=max(280, len(pivot) * 36),
        margin=dict(l=0, r=0, t=20, b=20),
        xaxis=dict(tickangle=-25),
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_monthly_trend(df: pd.DataFrame):
    st.subheader("Monthly Trend")

    top_cats = (
        df.groupby("category")["key"].count()
        .sort_values(ascending=False).head(5).index.tolist()
    )
    sub = df[df["category"].isin(top_cats) & (df["month"] != "NaT")]
    counts = (
        sub.groupby(["month", "category"])["key"]
        .count().reset_index(name="count")
    )
    counts = counts.sort_values("month")

    fig = px.line(
        counts, x="month", y="count", color="category",
        markers=True,
        labels={"month": "", "count": "Bugs", "category": "Category"},
        height=320,
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.4),
    )
    st.plotly_chart(fig, use_container_width=True)


def chart_top_tags(df: pd.DataFrame):
    st.subheader("Top Tags")

    from collections import Counter
    counter: Counter = Counter()
    for tags in df["tags_list"]:
        counter.update(tags)

    if not counter:
        st.caption("No tags found.")
        return

    tag_df = pd.DataFrame(counter.most_common(25), columns=["tag", "count"])
    fig = px.bar(
        tag_df.sort_values("count"),
        x="count", y="tag", orientation="h",
        labels={"count": "Occurrences", "tag": ""},
        color="count",
        color_continuous_scale="Blues",
        height=420,
    )
    fig.update_layout(
        coloraxis_showscale=False,
        margin=dict(l=0, r=0, t=20, b=20),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


def section_critical_bugs(df: pd.DataFrame):
    critical = df[(df["severity"] == "S1") & (df["probability"] == "P1")]
    if critical.empty:
        return

    st.subheader(f"S1 + P1 Critical Bugs  ({len(critical)})")

    display = critical[["key", "summary", "category", "cell", "confidence", "root_cause"]].copy()
    display["JIRA"] = display["key"].apply(lambda k: f"[{k}]({_jira_url(k)})")
    display = display.rename(columns={
        "summary": "Summary", "category": "Category",
        "cell": "Team", "confidence": "Conf.", "root_cause": "Root Cause",
    })[["JIRA", "Summary", "Category", "Team", "Conf.", "Root Cause"]]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "JIRA": st.column_config.LinkColumn("JIRA", display_text=r"(MAG|MA|MAGXRAY)-\d+"),
            "Conf.": st.column_config.ProgressColumn("Conf.", min_value=0, max_value=1, format="%.2f"),
            "Root Cause": st.column_config.TextColumn("Root Cause", width="large"),
            "Summary": st.column_config.TextColumn("Summary", width="medium"),
        },
    )


def section_bug_explorer(df: pd.DataFrame):
    st.subheader("Bug Explorer")

    search = st.text_input("Search summary or root cause", placeholder="e.g. placeholder, animation, shop…")
    if search:
        mask = (
            df["summary"].str.contains(search, case=False, na=False) |
            df["root_cause"].str.contains(search, case=False, na=False) |
            df["category"].str.contains(search, case=False, na=False)
        )
        df = df[mask]

    display = df[[
        "key", "summary", "category", "subsystem", "severity", "probability",
        "cell", "confidence", "fix_versions_str", "root_cause",
    ]].copy()
    display["JIRA"] = display["key"].apply(lambda k: f"[{k}]({_jira_url(k)})")
    display = display.rename(columns={
        "summary": "Summary", "category": "Category", "subsystem": "Subsystem",
        "severity": "Sev", "probability": "Prob", "cell": "Team",
        "confidence": "Conf.", "fix_versions_str": "Fix Version",
        "root_cause": "Root Cause",
    })[["JIRA", "Summary", "Category", "Subsystem", "Sev", "Prob",
        "Team", "Conf.", "Fix Version", "Root Cause"]]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "JIRA": st.column_config.LinkColumn("JIRA", display_text=r"(MAG|MA|MAGXRAY)-\d+"),
            "Conf.": st.column_config.ProgressColumn("Conf.", min_value=0, max_value=1, format="%.2f"),
            "Root Cause": st.column_config.TextColumn("Root Cause", width="large"),
            "Summary": st.column_config.TextColumn("Summary", width="medium"),
        },
    )


def section_semantic_dupes(rows):
    clusters = semantic_duplicates(rows)
    if not clusters:
        return

    st.subheader(f"Semantic Duplicate Clusters  ({len(clusters)} found)")
    for clust in clusters[:20]:
        label = f"[{clust['category']}]  {clust['size']} similar bugs"
        with st.expander(label):
            for b in clust["bugs"]:
                url = _jira_url(b["key"])
                st.markdown(f"- [{b['key']}]({url})  {b['summary']}")


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    st.title("Bug Base Analyzer")

    init_db()
    df_full = load_df()

    if df_full.empty:
        st.warning("No analyzed bugs found. Run `python main.py analyze` first.")
        st.stop()

    df = apply_filters(df_full)

    if df.empty:
        st.info("No bugs match the current filters.")
        st.stop()

    # ── KPIs ─────────────────────────────────────────────────────────────────
    s1 = int((df["severity"] == "S1").sum())
    p1 = int((df["probability"] == "P1").sum())
    s1p1 = int(((df["severity"] == "S1") & (df["probability"] == "P1")).sum())
    cats = int(df["category"].nunique())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Bugs",     len(df))
    c2.metric("S1 (Must Fix)",  s1,  delta=None)
    c3.metric("P1 (All Players)", p1, delta=None)
    c4.metric("S1 + P1",        s1p1, delta=None)
    c5.metric("Categories",     cats)

    st.divider()

    # ── category × severity (full width) ─────────────────────────────────────
    chart_category_severity(df)

    st.divider()

    # ── scatter + heatmap ─────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)
    with col_l:
        chart_priority_matrix(df)
    with col_r:
        chart_team_heatmap(df)

    st.divider()

    # ── trend + tags ──────────────────────────────────────────────────────────
    col_l, col_r = st.columns(2)
    with col_l:
        chart_monthly_trend(df)
    with col_r:
        chart_top_tags(df)

    st.divider()

    # ── critical spotlight ────────────────────────────────────────────────────
    section_critical_bugs(df)

    st.divider()

    # ── bug explorer ──────────────────────────────────────────────────────────
    section_bug_explorer(df)

    st.divider()

    # ── semantic duplicates ───────────────────────────────────────────────────
    # Pass raw sqlite rows for the duplicate detector
    from src.store import get_all_analyses
    section_semantic_dupes(get_all_analyses())

    st.caption("Data refreshes every 60 s. Re-run `python main.py analyze` to update.")


if __name__ == "__main__":
    main()
