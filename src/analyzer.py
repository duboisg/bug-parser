import sqlite3
from src.llm_client import chat, extract_json

_SYSTEM = """\
You are a senior QA analyst for a AAA video game studio. Your task is to identify the ROOT CAUSE of bugs — the underlying process or technical failure that allowed the bug to exist, not the visible symptom.

Bug severity scale (S):
  S1 Must Fix   — crashes, connectivity failures, lost progress, broken monetization, walkthrough blockers, first-party requirements
  S2 Quality    — gameplay issues, major graphics/sound/animation problems, collision, localization
  S3 Nice to Have — minor visual/audio polish, tester suggestions

Bug probability scale (P):
  P1 All Players   — 100% repro, golden-path location, easy steps, all platforms
  P2 Most Players  — 50–99% repro, specific but reachable conditions, some platforms
  P3 Few Players   — <50% repro, edge cases, obscure steps, single device

Common root cause categories in game development:
- Asset Pipeline      : missing, unlinked, or wrongly exported assets (textures, animations, audio, VFX, UI)
- Blueprint/Setup     : asset or feature not wired up in the blueprint or prefab
- Data/Config Error   : wrong values in config sheets, databases, or gameplay data
- Content Error       : wrong text, placeholder, missing localization, bad UI copy
- Missing Implementation : feature was designed but not fully built or left in stub state
- Code Bug            : logic error in gameplay, UI, backend, or tooling code
- Integration/Build   : broken during code merge, packaging, or branch integration
- Regression          : was working, broke after a recent change
- Platform Issue      : device- or platform-specific failure
- Timing/Scheduling   : time-gated content, feature flag, or live event misconfigured
- Test Gap            : bug that existed but wasn't covered by the QA process
- Pipeline/Workflow   : a production step was skipped or done out of order
"""

_PROMPT_TEMPLATE = """\
Analyze this bug report and extract the root cause.

KEY: {key}
SUMMARY: {summary}
CELL (owning team): {cell}
SEVERITY: {severity}  — {severity_desc}
PROBABILITY: {probability}  — {probability_desc}
UBI PRIORITY: {ubi_priority}

DESCRIPTION:
{description}

STEPS TO REPRODUCE:
{steps}

RESOLUTION: {resolution}

Return ONLY valid JSON, no explanation:
{{
  "root_cause": "<one sentence: what fundamentally went wrong, not the symptom>",
  "category": "<category from the list above, or a new one if none fit>",
  "subsystem": "<specific system/process that failed, e.g. 'Animation Blueprint', 'Shop Config Table', 'Build Pipeline', 'Feature Flag Setup'>",
  "tags": ["<3-6 lowercase keyword tags>"],
  "confidence": <0.0-1.0>
}}"""

_SEVERITY_DESC = {
    "S1": "Must Fix — crashes, monetization, progression blocker, first-party requirement",
    "S2": "Quality — gameplay, major graphics/sound/animation, localization",
    "S3": "Nice to Have — minor visual/audio polish",
}
_PROBABILITY_DESC = {
    "P1": "All Players — 100% repro, golden-path, easy steps",
    "P2": "Most Players — 50–99%, specific but reachable conditions",
    "P3": "Few Players — <50%, edge case, hard steps",
}


def analyze_bug(row: sqlite3.Row) -> tuple[dict, str]:
    """
    Returns (parsed_result, raw_response).
    On failure, category is set to 'parse_error' or 'llm_error'.
    """
    severity = (row["severity"] or "").upper()
    probability = (row["probability"] or "").upper()
    desc = (row["description"] or "")[:800]
    steps = (row["steps"] or "")[:400]

    prompt = _PROMPT_TEMPLATE.format(
        key=row["key"],
        summary=row["summary"] or "",
        cell=row["cell"] or "Unknown",
        severity=severity or "Unknown",
        severity_desc=_SEVERITY_DESC.get(severity, ""),
        probability=probability or "Unknown",
        probability_desc=_PROBABILITY_DESC.get(probability, ""),
        ubi_priority=row["ubi_priority"] or "Unknown",
        description=desc or "(none)",
        steps=steps or "(none)",
        resolution=row["resolution"] or "Unresolved",
    )

    try:
        raw = chat([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        err = f"LLM error: {e}"
        return {"root_cause": err, "category": "llm_error", "subsystem": "", "tags": [], "confidence": 0.0}, err

    result = extract_json(raw)
    if not result or "category" not in result:
        return {"root_cause": raw[:200], "category": "parse_error", "subsystem": "", "tags": [], "confidence": 0.0}, raw

    result.setdefault("root_cause", "")
    result.setdefault("subsystem", "")
    result.setdefault("tags", [])
    result.setdefault("confidence", 0.5)
    if isinstance(result["tags"], str):
        result["tags"] = [t.strip() for t in result["tags"].split(",")]

    return result, raw
