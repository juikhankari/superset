#!/usr/bin/env python3
"""
create_issues.py — Seed the three bug issues in your Superset fork

Run this once to create the three verified bugs as labeled GitHub issues.
Applying the "devin-fix" label is what triggers the GitHub Action.

Usage:
  export GITHUB_TOKEN=<your-token>
  export GITHUB_REPO=juikhankari/superset   # or your fork slug
  python scripts/create_issues.py

Or via Docker:
  docker compose -f automation/docker-compose.yml run create-issues
"""

import json
import os
import sys
import time

import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ.get("GITHUB_REPO", "juikhankari/superset")
GITHUB_API_URL = "https://api.github.com"
LABEL_NAME = "devin-fix"
LABEL_COLOR = "e11d48"  # red — clearly marks issues targeted for automation


# ---------------------------------------------------------------------------
# The three verified bugs we identified in Apache Superset
# ---------------------------------------------------------------------------

ISSUES = [
    {
        "title": "fix(views): handle malformed datasourceKey in datasource_metadata endpoint",
        "body": """## Bug Description

In `superset/views/core.py` at **line 901**, the `datasource_metadata` endpoint does an unguarded string split:

```python
datasource_id, datasource_type = request.args["datasourceKey"].split("__")
```

If `datasourceKey` is **absent** from the request, Python raises `KeyError`.
If `datasourceKey` is present but contains **no `__`** (e.g. `"invalid"`), Python raises `ValueError` because the tuple unpacking fails.

Neither exception is caught, so the server returns a raw **500 Internal Server Error** instead of a descriptive 400.

This endpoint is called on every chart load in the Explore view, making it a high-impact crash path.

## Steps to Reproduce

```bash
curl "http://localhost:8088/superset/datasource/get/?datasourceKey=badvalue"
# Returns 500 instead of 400
```

## Expected Behavior

A 400 response with a clear error message: `"Invalid datasourceKey format"`.

## Fix

Wrap the split in a `try/except (KeyError, ValueError)` block and return `json_error_response`:

```python
try:
    datasource_id, datasource_type = request.args["datasourceKey"].split("__")
except (KeyError, ValueError):
    return json_error_response("Invalid datasourceKey format", status=400)
```

## File Reference

- **File:** `superset/views/core.py`
- **Line:** 901
- **Function:** `datasource_metadata`
""",
    },
    {
        "title": "fix(views): handle malformed datasource string in get_redirect_url",
        "body": """## Bug Description

In `superset/views/core.py` at **line 406**, the static method `get_redirect_url` splits a datasource string from form data without any error handling:

```python
if datasource := parsed_form_data.get("datasource"):
    datasource_id, datasource_type = datasource.split("__")
```

If the `datasource` field in `form_data` does not contain `__` — due to corrupted data, a browser quirk, or a crafted request — Python raises an unhandled `ValueError`. This silently breaks redirect URL generation and can cause users to lose unsaved chart work.

## Steps to Reproduce

Send a request where `form_data` contains `{"datasource": "malformed"}` (no `__` separator).

## Expected Behavior

The function logs a warning and skips the datasource extraction rather than crashing.

## Fix

Guard the split with a length check:

```python
if datasource := parsed_form_data.get("datasource"):
    parts = datasource.split("__")
    if len(parts) == 2:
        datasource_id, datasource_type = parts
        # ... rest of existing logic
    else:
        logger.warning("Skipping malformed datasource value in form_data: %s", datasource)
```

## File Reference

- **File:** `superset/views/core.py`
- **Line:** 406
- **Function:** `get_redirect_url` (static method)
""",
    },
    {
        "title": "fix(views): handle JSONDecodeError when loading cached explore form data",
        "body": """## Bug Description

In `superset/views/core.py` at **line 475**, the Explore page loads cached form data with a bare `json.loads` call:

```python
initial_form_data = json.loads(value) if value else {}
```

If the value retrieved from the cache (typically Redis) is **non-empty but not valid JSON** — due to cache corruption, a Redis restart, or a serialization bug elsewhere — `json.loads` raises an unhandled `json.JSONDecodeError`. This crashes the entire page load with a 500 error instead of gracefully falling back to an empty form.

## Impact

Any cache corruption event (network blip, Redis restart, partial write) causes every user loading the Explore page to see a 500 error until the bad cache key expires.

## Expected Behavior

Log a warning and fall back to `{}` (empty form), allowing the page to load normally even if the cached state is unrecoverable.

## Fix

```python
try:
    initial_form_data = json.loads(value) if value else {}
except json.JSONDecodeError:
    logger.warning(
        "Failed to parse cached form data (key may be corrupted); falling back to empty form."
    )
    initial_form_data = {}
```

## File Reference

- **File:** `superset/views/core.py`
- **Line:** 475
- **Context:** `explore()` view, inside the block that fetches form data from cache
""",
    },
]


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def ensure_label_exists() -> None:
    """Create the 'devin-fix' label if it doesn't already exist."""
    url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/labels"
    response = requests.get(url, headers=get_headers(), timeout=10)
    response.raise_for_status()

    existing = {label["name"] for label in response.json()}
    if LABEL_NAME in existing:
        print(f"[label] '{LABEL_NAME}' already exists — skipping creation.")
        return

    create_resp = requests.post(
        url,
        headers=get_headers(),
        json={"name": LABEL_NAME, "color": LABEL_COLOR, "description": "Trigger Devin auto-remediation"},
        timeout=10,
    )
    create_resp.raise_for_status()
    print(f"[label] Created label '{LABEL_NAME}' (#{LABEL_COLOR}).")


def create_issue(title: str, body: str) -> dict:
    """Create a GitHub issue and immediately apply the 'devin-fix' label."""
    response = requests.post(
        f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues",
        headers=get_headers(),
        json={"title": title, "body": body, "labels": [LABEL_NAME]},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Creating {len(ISSUES)} issues in {GITHUB_REPO}...")
    print()

    ensure_label_exists()
    print()

    created = []
    for i, issue in enumerate(ISSUES, start=1):
        result = create_issue(issue["title"], issue["body"])
        number = result["number"]
        url = result["html_url"]
        print(f"[{i}/{len(ISSUES)}] Created issue #{number}: {url}")
        created.append({"number": number, "url": url, "title": issue["title"]})

        # Small delay to avoid hitting GitHub's secondary rate limit
        if i < len(ISSUES):
            time.sleep(1)

    print()
    print("=" * 60)
    print("  Issues created successfully!")
    print("  The GitHub Action will fire automatically for each one.")
    print()
    for issue in created:
        print(f"  #{issue['number']} — {issue['url']}")
    print("=" * 60)

    # Write a summary file so it's easy to reference later
    summary_path = "logs/created_issues.json"
    os.makedirs("logs", exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(created, f, indent=2)
    print(f"\n[log] Issue summary written to {summary_path}")


if __name__ == "__main__":
    main()
