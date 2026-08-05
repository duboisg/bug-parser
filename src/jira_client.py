import os
import time
from typing import Iterator

import requests
import urllib3
from dotenv import load_dotenv

load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

JIRA_URL = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_USERNAME = os.getenv("JIRA_USERNAME", "").strip("'\"")
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD", "").strip("'\"")
JIRA_PROJECTS = [p.strip() for p in os.getenv("JIRA_PROJECT_KEYS", "MAG").split(",")]

BASE_URL = f"{JIRA_URL}/rest/api/2"

# Fields to request — standard + we'll get all customfields via expand=names
_FIELDS = ",".join([
    "summary", "description", "components", "labels", "priority", "status",
    "resolution", "created", "updated", "fixVersions", "issuetype",
    "assignee", "reporter", "issuelinks",
])


def _session() -> requests.Session:
    s = requests.Session()
    s.auth = (JIRA_USERNAME, JIRA_PASSWORD)
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    s.verify = False  # internal CA cert
    return s


def discover_fields() -> dict[str, str]:
    """Return {fieldId: fieldName} for all fields on this JIRA instance."""
    s = _session()
    resp = s.get(f"{BASE_URL}/field")
    resp.raise_for_status()
    return {f["id"]: f["name"] for f in resp.json()}


def fetch_bugs(
    projects: list[str] | None = None,
    max_results: int = 10_000,
    extra_jql: str = "",
    page_size: int = 100,
    delay: float = 0.15,
) -> Iterator[dict]:
    """Yield all Bug QC issues from JIRA, paginated."""
    projects = projects or JIRA_PROJECTS
    proj_str = ", ".join(projects)
    jql = f'issuetype = "Bug QC" AND project in ({proj_str})'
    if extra_jql:
        jql += f" AND ({extra_jql})"
    jql += " ORDER BY created DESC"

    s = _session()
    start = 0
    total_fetched = 0

    while total_fetched < max_results:
        batch = min(page_size, max_results - total_fetched)
        try:
            resp = s.get(
                f"{BASE_URL}/search",
                params={
                    "jql": jql,
                    "startAt": start,
                    "maxResults": batch,
                    "fields": "*all",   # fetch all fields including custom ones
                },
                timeout=30,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"JIRA search failed ({e.response.status_code}): {e.response.text[:300]}") from e

        data = resp.json()
        issues = data.get("issues", [])
        if not issues:
            break

        yield from issues

        total_fetched += len(issues)
        start += len(issues)

        if start >= data.get("total", 0):
            break

        time.sleep(delay)


def fetch_total(projects: list[str] | None = None, extra_jql: str = "") -> int:
    """Return total count of Bug QC issues without fetching them all."""
    projects = projects or JIRA_PROJECTS
    proj_str = ", ".join(projects)
    jql = f'issuetype = "Bug QC" AND project in ({proj_str})'
    if extra_jql:
        jql += f" AND ({extra_jql})"

    s = _session()
    resp = s.get(
        f"{BASE_URL}/search",
        params={"jql": jql, "maxResults": 0},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("total", 0)
