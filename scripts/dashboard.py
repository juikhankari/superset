#!/usr/bin/env python3
"""
dashboard.py — Devin Remediation Observability Report

Reads logs/sessions.json and prints a human-readable status report.

This answers the engineering leader question:
  "How do I know the automation is working?"

Metrics reported:
  - Total sessions initiated
  - Completed / failed / in-progress counts
  - Overall success rate
  - Average fix duration (completed sessions only)
  - Pull requests opened by Devin
  - Per-issue breakdown

Usage:
  python scripts/dashboard.py

Or via Docker:
  docker compose -f automation/docker-compose.yml run dashboard
"""

import json
import sys
from collections import Counter
from pathlib import Path

LOGS_FILE = Path("logs/sessions.json")

STATUS_ICONS = {
    "completed": "✅",
    "failed": "❌",
    "error": "❌",
    "stopped": "🛑",
    "timed_out": "⏱️",
    "running": "🔄",
    "unknown": "❓",
}


def load_sessions() -> list[dict]:
    if not LOGS_FILE.exists():
        print("No session log found at logs/sessions.json.")
        print("Run create_issues.py first to create issues and trigger the workflow.")
        sys.exit(0)

    try:
        data = json.loads(LOGS_FILE.read_text())
    except json.JSONDecodeError:
        print(f"Error: {LOGS_FILE} contains invalid JSON.")
        sys.exit(1)

    if not isinstance(data, list) or not data:
        print("No sessions recorded yet.")
        sys.exit(0)

    return data


def format_pr(pr_url: str | None) -> str:
    if not pr_url:
        return "—"
    # Shorten GitHub PR URLs for readability: keep just the PR number
    parts = pr_url.rstrip("/").split("/")
    try:
        return f"PR #{parts[-1]}  ({pr_url})"
    except IndexError:
        return pr_url


def print_dashboard(sessions: list[dict]) -> None:
    total = len(sessions)
    status_counts = Counter(s.get("status", "unknown") for s in sessions)

    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0) + status_counts.get("error", 0)
    stopped = status_counts.get("stopped", 0)
    timed_out = status_counts.get("timed_out", 0)
    running = status_counts.get("running", 0)

    success_rate = round((completed / total) * 100) if total else 0

    completed_durations = [
        s["duration_minutes"]
        for s in sessions
        if s.get("status") == "completed" and s.get("duration_minutes") is not None
    ]
    avg_duration = (
        f"{round(sum(completed_durations) / len(completed_durations), 1)} min"
        if completed_durations
        else "N/A"
    )

    prs = [s["pr_url"] for s in sessions if s.get("pr_url")]

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("   DEVIN REMEDIATION DASHBOARD")
    print("=" * 70)
    print()

    # -----------------------------------------------------------------------
    # Summary metrics
    # -----------------------------------------------------------------------
    print("  SUMMARY")
    print("  -------")
    print(f"  Total sessions initiated : {total}")
    print(f"  ✅  Completed            : {completed}")
    print(f"  ❌  Failed / Errored     : {failed}")
    print(f"  🛑  Stopped              : {stopped}")
    print(f"  ⏱️   Timed out            : {timed_out}")
    print(f"  🔄  Still running        : {running}")
    print()
    print(f"  Success rate             : {success_rate}%")
    print(f"  Avg fix duration         : {avg_duration}")
    print(f"  Pull requests opened     : {len(prs)}")
    print()

    # -----------------------------------------------------------------------
    # Per-session breakdown
    # -----------------------------------------------------------------------
    print("  PER-ISSUE BREAKDOWN")
    print("  " + "-" * 66)
    print(f"  {'ISSUE':<8} {'STATUS':<12} {'DURATION':<12} {'SESSION / PR'}")
    print("  " + "-" * 66)

    for s in sessions:
        status = s.get("status", "unknown")
        icon = STATUS_ICONS.get(status, "❓")
        duration = f"{s.get('duration_minutes', '?')} min"
        pr = format_pr(s.get("pr_url"))
        session_id = s.get("session_id", "")[:12]  # truncate for display
        display = f"{session_id}…  {pr}" if s.get("pr_url") else session_id

        print(f"  #{s.get('issue_number', '?'):<7} {icon} {status:<10} {duration:<12} {display}")

    print()

    # -----------------------------------------------------------------------
    # Pull requests section
    # -----------------------------------------------------------------------
    if prs:
        print("  PULL REQUESTS OPENED BY DEVIN")
        print("  " + "-" * 66)
        for pr in prs:
            print(f"  • {pr}")
        print()

    # -----------------------------------------------------------------------
    # Health signal for engineering leaders
    # -----------------------------------------------------------------------
    print("  SYSTEM HEALTH")
    print("  " + "-" * 66)
    if success_rate == 100:
        print("  🟢  All sessions completed successfully. System is healthy.")
    elif success_rate >= 75:
        print(f"  🟡  {success_rate}% success rate. Review failed sessions above.")
    else:
        print(f"  🔴  {success_rate}% success rate. Investigate failures before proceeding.")
    print()
    print("=" * 70)
    print()


def main() -> None:
    sessions = load_sessions()
    print_dashboard(sessions)


if __name__ == "__main__":
    main()
