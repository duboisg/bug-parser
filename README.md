# Bug Parser

Bug Parser ingests Bug QC issues from Jira and asks a local OpenAI-compatible model to propose root-cause labels. It stores the results in SQLite for terminal reporting and Streamlit exploration.

## Why this exists

In game development, a bug database contains more than a queue of individual fixes. Across enough reports, it can reveal recurring weaknesses in content pipelines or team hand-offs. These patterns point toward the systems that generate bugs rather than only toward their symptoms.

The proof of concept tests whether a modest local model can make a game bug history useful for upstream production decisions. The classifications remain hypotheses: QA and production teams must review them before changing a process or assigning cause.

## What the prototype does

```text
Jira Bug QC issues
        |
        v
Local SQLite cache  --->  Local LLM root-cause classification
        |                                  |
        +--------------------------------> |
                                           v
                              categories, subsystems, tags,
                              severity patterns, team heatmaps,
                              temporal trends, duplicate clusters
                                           |
                                           v
                              production report + dashboard
```

The current pipeline provides:

- Jira ingestion with project, date, limit, and JQL filters;
- local SQLite storage for bug records and analysis results;
- tolerant JSON extraction from model responses;
- root-cause categories, subsystem labels, tags, confidence, and error states;
- Rich terminal reports and a Streamlit exploration dashboard;
- severity/category breakdowns, team heatmaps, trends, high-impact spotlights, and lightweight duplicate grouping;
- an OpenAI-compatible local endpoint, designed for a small local model rather than a hosted inference API.

## What is demonstrated—and what is not

This repository demonstrates an end-to-end experimental path. Jira data can be fetched and classified locally, then the stored results can be reviewed through reports. Model failures appear as `llm_error` or `parse_error` instead of being silently presented as findings.

It does not yet demonstrate:

- **Classification quality:** accuracy and causal validity have not been established.
- **Evaluation discipline:** model benchmarking and taxonomy governance remain future work.
- **Production impact:** no measured link connects a detected pattern to a confirmed process improvement.

Human review remains essential. Classifications are hypotheses for QA and production teams to validate, not authoritative root-cause decisions.

The next credible evaluation is a manually reviewed validation set. It should measure label agreement and error rates, then track whether reviewed patterns reduce recurring bugs or rework.

## Local-first and low-cost by design

The inference client targets an OpenAI-compatible server on `127.0.0.1`, with a local model name configured in code. This keeps Jira data and inference traffic on the local workstation, avoids per-request hosted-model costs, and makes the model boundary replaceable.

Local inference is a constraint, not a claim that every model will perform equally well. Results depend on the chosen model, the prompt, and source-report quality. The prototype records raw responses and confidence values so that quality can be inspected rather than assumed.

## Quick start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure services

Copy `.env.example` to `.env` and provide credentials for a Jira instance you are authorized to access. Start an OpenAI-compatible local inference server at `http://127.0.0.1:8080/v1`, or adapt `src/llm_client.py` to the local server you use.

The repository excludes private Jira data and generated output. Those files are ignored by Git because bug descriptions and issue metadata may be confidential.

### 3. Run the pipeline

```bash
python main.py sample --from-date 2026-01-01
```

Or run each stage independently:

```bash
python main.py fetch --limit 50
python main.py analyze --retry-errors
python main.py report --no-narrative
streamlit run app.py
```

Generated data is written under `output/` locally and is not intended for publication.

## Repository map

- `main.py` — CLI orchestration for fetch, analyze, report, and sample runs.
- `src/jira_client.py` — Jira REST ingestion.
- `src/analyzer.py` — prompt and structured root-cause extraction.
- `src/llm_client.py` — OpenAI-compatible local inference client.
- `src/store.py` — SQLite schema and persistence.
- `src/cluster.py` — aggregation and lightweight duplicate grouping.
- `src/report.py` — terminal and JSON reporting.
- `app.py` — Streamlit dashboard.

## Status

Exploratory proof of concept. The code is useful as a conversation starter and a base for evaluation; it is not presented as a production-ready quality system.

## Responsible use

Only connect the pipeline to Jira data that you are authorized to process. Review and sanitize exports before sharing them. Keep credentials in environment variables, keep generated databases out of version control, and treat model outputs as decision support subject to human validation.

