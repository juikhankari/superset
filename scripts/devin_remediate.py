#!/usr/bin/env python3
"""
devin_remediate.py — Core Devin Remediation Script

Called by the GitHub Actions workflow when an issue is labeled "devin-fix".
Also runnable locally via Docker for simulation (see automation/docker-compose.yml).

What this script does:
  1. Reads issue context from environment variables (set by GitHub Actions)
  2. Creates a Devin session with a targeted prompt describing the fix
  3. Polls Devin every 30 seconds until the session completes or fails
  4. Posts a status update comment back to the GitHub issue
  5. Appends a structured log entry to logs/sessions.json for observability

Required environment variables:
  DEVIN_API_KEY       — Devin API key (from app.devin.ai → Settings → API Keys)
  GITHUB_TOKEN        — GitHub token with issues:write permission
  GITHUB_REPOSITORY   — "owner/repo" (e.g. juikhankari/superset)
  ISSUE_NUMBER        — GitHub issue number
  ISSUE_TITLE         — GitHub issue title
  ISSUE_BODY          — GitHub issue body (the fix description)
  ISSUE_URL           — Full URL to the GitHub issue
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEVIN_API_KEY = os.environ["DEVIN_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPOSITORY"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE = os.environ["ISSUE_TITLE"]
ISSUE_BODY = os.environ["ISSUE_BODY"]
ISSUE_URL = os.environ["ISSUE_URL"]

# Devin v1 API — works with standard API keys from app.devin.ai → Settings → API Keys
DEVIN_BASE_URL = "https://api.devin.ai/v1"
DEVIN_SESSIONS_URL = f"{DEVIN_BASE_URL}/sessions"

GITHUB_API_URL = "https://api.github.com"
LOGS_FILE = Path("logs/sessions.json")

POLL_INTERVAL_SECONDS = 30
MAX_POLL_ATTEMPTS = 120  # 60 minutes total before we time out


# ---------------------------------------------------------------------------
# Devin API helpers
# ---------------------------------------------------------------------------

def create_devin_session(issue_number: str, issue_title: str, issue_body: str) -> dict:
    """
    Open a new Devin session with a prompt that describes exactly what to fix.

    The prompt is intentionally verbose so Devin has full context: the repo URL,
    the exact file and line, what the bug is, what the fix should look like,
    and how to open the pull request.
    """
    repo_url = f"https://github.com/{GITHUB_REPO}"

    prompt = f"""You are working on a fork of Apache Superset at {repo_url}.

Your task is to fix the bug described in GitHub issue #{issue_number}: "{issue_title}"

--- ISSUE DETAILS ---
{issue_body}
--- END ISSUE DETAILS ---

Step-by-step instructions:
1. Clone the repository and check out the master branch.
2. Locate the exact file and line(s) referenced in the issue details above.
3. Implement the minimal fix described — do not refactor surrounding code.
4. Run any existing unit tests that cover the changed code to confirm nothing regresses.
5. Commit the fix with message: "fix: {issue_title}"
6. Open a pull request against the master branch of {repo_url}.
   - PR title: "fix: {issue_title}"
   - PR body: "Fixes #{issue_number}\\n\\n<brief description of what changed and why>"

Be precise. Change only what is needed to fix the described bug.
"""

    print(f"[devin] Creating session via v1 API for issue #{issue_number}...")
    response = requests.post(
        DEVIN_SESSIONS_URL,
        headers={
            "Authorization": f"Bearer {DEVIN_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"prompt": prompt},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def get_session_status(session_id: str) -> dict:
    """Fetch the current state of a Devin session."""
    response = requests.get(
        f"{DEVIN_BASE_URL}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {DEVIN_API_KEY}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def post_github_comment(issue_number: str, body: str) -> None:
    """Post a comment on the GitHub issue to report status."""
    response = requests.post(
        f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{issue_number}/comments",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"body": body},
        timeout=30,
    )
    response.raise_for_status()


# ---------------------------------------------------------------------------
# Observability: session logging
# ---------------------------------------------------------------------------

def append_session_log(entry: dict) -> None:
    """
    Append a structured record to logs/sessions.json.

    This file is the source of truth for the dashboard.py report.
    Each entry captures: issue context, session ID, final status, PR URL, duration.
    """
    LOGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    sessions = []
    if LOGS_FILE.exists():
        try:
            sessions = json.loads(LOGS_FILE.read_text())
        except json.JSONDecodeError:
            print(f"[warn] {LOGS_FILE} was malformed — starting fresh log.")

    sessions.append(entry)
    LOGS_FILE.write_text(json.dumps(sessions, indent=2))
    print(f"[log] Session appended to {LOGS_FILE}")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    started_at = datetime.now(timezone.utc)

    # Step 1: Create Devin session
    session = create_devin_session(ISSUE_NUMBER, ISSUE_TITLE, ISSUE_BODY)
    session_id = session["session_id"]
    session_url = session.get("url", f"https://app.devin.ai/sessions/{session_id}")

    print(f"[devin] Session ID  : {session_id}")
    print(f"[devin] Session URL : {session_url}")

    # Step 2: Notify the issue that Devin is working on it
    post_github_comment(
        ISSUE_NUMBER,
        f"🤖 **Devin is working on this issue!**\n\n"
        f"A remediation session has been started automatically.\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Session ID | `{session_id}` |\n"
        f"| Session URL | {session_url} |\n"
        f"| Triggered by | `devin-fix` label applied |\n\n"
        f"I'll post another comment here when the fix is complete.",
    )

    # Step 3: Poll until session reaches a terminal state
    final_status = "timed_out"
    pr_url = None
    status_data: dict = {}

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        time.sleep(POLL_INTERVAL_SECONDS)

        try:
            status_data = get_session_status(session_id)
        except requests.RequestException as exc:
            print(f"[warn] Poll attempt {attempt} failed: {exc}")
            continue

        current_status = status_data.get("status", "unknown")
        print(f"[poll] Attempt {attempt}/{MAX_POLL_ATTEMPTS} — status: {current_status}")

        # Extract PR URL if present — Devin may open a PR before the session
        # status transitions to a terminal state in the v1 API.
        pr_info = status_data.get("pull_request")
        if pr_info and pr_info.get("url"):
            pr_url = pr_info["url"]

        if current_status in ("completed", "finished", "failed", "stopped", "error"):
            final_status = current_status
            break

        # Treat an opened PR as implicit completion — the v1 API may keep
        # reporting "running" even after Devin finishes and opens a PR.
        if pr_url:
            print(f"[poll] PR detected ({pr_url}) — treating session as completed.")
            final_status = "completed"
            break

    # Step 4: Calculate how long it took
    finished_at = datetime.now(timezone.utc)
    duration_minutes = round((finished_at - started_at).total_seconds() / 60, 1)

    # Step 5: Post final result to the GitHub issue
    if final_status == "completed":
        result_comment = (
            f"✅ **Devin completed the fix in {duration_minutes} minutes.**\n\n"
            f"| Field | Value |\n"
            f"|---|---|\n"
            f"| Status | `completed` |\n"
            f"| Duration | {duration_minutes} min |\n"
            f"| Session | {session_url} |\n"
        )
        if pr_url:
            result_comment += f"| Pull Request | {pr_url} |\n"
    elif final_status == "timed_out":
        result_comment = (
            f"⏱️ **Devin session timed out after {duration_minutes} minutes.**\n\n"
            f"The session may still be running. Check it directly: {session_url}"
        )
    else:
        result_comment = (
            f"❌ **Devin session ended with status `{final_status}`.**\n\n"
            f"Review the session for details: {session_url}"
        )

    post_github_comment(ISSUE_NUMBER, result_comment)

    # Step 6: Append to the structured log for the dashboard
    append_session_log({
        "timestamp": started_at.isoformat(),
        "issue_number": ISSUE_NUMBER,
        "issue_title": ISSUE_TITLE,
        "issue_url": ISSUE_URL,
        "session_id": session_id,
        "session_url": session_url,
        "status": final_status,
        "pr_url": pr_url,
        "duration_minutes": duration_minutes,
    })

    print(f"[done] status={final_status} duration={duration_minutes}m pr={pr_url}")

    # Exit non-zero so the GitHub Action is marked as failed if remediation failed
    if final_status not in ("completed",):
        sys.exit(1)


if __name__ == "__main__":
    main()
