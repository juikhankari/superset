# Devin Auto-Remediation System

An event-driven automation that monitors this Apache Superset fork for issues labeled **`devin-fix`** and uses the [Devin API](https://docs.devin.ai/api-reference/overview) to autonomously fix them — opening pull requests and posting status updates with no human involvement in the fix loop.

---

## What Problem Does This Solve?

Engineering teams accumulate known bugs — crash paths, unhandled exceptions, security debt — that never get fixed because they're low-severity but time-consuming to context-switch into. This system makes fixing them **zero-touch**: a developer labels an issue, and Devin handles the rest.

**Why Devin specifically?** These fixes require cloning the repo, navigating to the right file, understanding the surrounding code, writing a correct patch, running tests, and opening a PR with a coherent description. A static script can't do that. Devin can.

---

## Architecture

```
GitHub Issue labeled "devin-fix"
           │
           ▼
 GitHub Actions Workflow          (.github/workflows/devin-remediate.yml)
           │
           ▼
  devin_remediate.py              (scripts/devin_remediate.py)
   ├── POST /sessions             → Devin API: start a session
   ├── GET  /sessions/{id}        → Poll every 30s until done
   ├── POST /issues/{n}/comments  → GitHub API: post status updates
   └── Append to sessions.json   → Observability log
           │
           ▼
   Devin works autonomously
   └── Opens a Pull Request in this repo
           │
           ▼
  dashboard.py reads sessions.json and prints a status report
```

---

## Issues Remediated

Three verified bugs in `superset/views/core.py`, all sharing the same root cause — unguarded operations on user-controlled input with no error handling:

| # | Title | File | Line |
|---|-------|------|------|
| 1 | Unhandled `ValueError`/`KeyError` in `datasource_metadata` | `views/core.py` | 901 |
| 2 | Unhandled `ValueError` in `get_redirect_url` | `views/core.py` | 406 |
| 3 | Unhandled `JSONDecodeError` on cached form data | `views/core.py` | 475 |

Each bug causes a **500 Internal Server Error** on a path that should return a **400** or fall back gracefully. See the GitHub Issues in this repo for full details.

---

## Repository Layout

```
.github/
└── workflows/
    └── devin-remediate.yml   ← Event trigger (GitHub Action)

scripts/
├── create_issues.py          ← Seeds the three bug issues with the "devin-fix" label
├── devin_remediate.py        ← Core: creates Devin session, polls, posts results
├── dashboard.py              ← Observability: prints session status report
└── requirements.txt          ← Python dependencies (just requests)

automation/
├── Dockerfile                ← Local Docker image for the scripts
├── docker-compose.yml        ← Run any step locally without GitHub Actions
└── .env.example              ← Environment variable template

logs/
└── sessions.json             ← Auto-generated: structured log of every Devin session
```

---

## Setup

### 1. Fork prerequisites

This automation lives in your Superset fork. You need two secrets set in:
**GitHub → Settings → Secrets and variables → Actions**

| Secret | Where to find it |
|--------|-----------------|
| `DEVIN_API_KEY` | [app.devin.ai](https://app.devin.ai) → Settings → API |
| `DEVIN_ORG_ID` | Same page, or visible in your Devin org URL |

The `GITHUB_TOKEN` secret is provided automatically by GitHub Actions — no setup needed.

Also ensure Devin has access to this repository:
**Devin → Settings → Connections → GitHub → select this repo**

---

### 2. Run locally with Docker

```bash
# Clone your fork
git clone https://github.com/juikhankari/superset.git
cd superset

# Set up environment variables
cp automation/.env.example automation/.env
# Edit automation/.env and fill in DEVIN_API_KEY, DEVIN_ORG_ID, GITHUB_TOKEN
```

**Step 1 — Create the bug issues** (this also triggers the GitHub Action automatically):
```bash
docker compose -f automation/docker-compose.yml run create-issues
```

**Step 2 — (Optional) simulate remediation locally** for a single issue:
```bash
# Set ISSUE_NUMBER, ISSUE_TITLE, ISSUE_BODY, ISSUE_URL in automation/.env first
docker compose -f automation/docker-compose.yml run remediate
```

**Step 3 — View the observability dashboard**:
```bash
docker compose -f automation/docker-compose.yml run dashboard
```

---

### 3. How the event trigger works

When `create_issues.py` creates issues with the `devin-fix` label, GitHub fires a webhook to the Actions runner. The workflow in `.github/workflows/devin-remediate.yml` picks it up and calls `devin_remediate.py` with the issue context injected as environment variables.

You can also trigger it manually: open any issue in this repo, go to the Labels panel, and apply **`devin-fix`**.

---

## Observability

Every Devin session is logged to `logs/sessions.json`:

```json
[
  {
    "timestamp": "2026-06-24T10:00:00+00:00",
    "issue_number": "1",
    "issue_title": "fix(views): handle malformed datasourceKey...",
    "session_id": "abc123",
    "session_url": "https://app.devin.ai/sessions/abc123",
    "status": "completed",
    "pr_url": "https://github.com/juikhankari/superset/pull/4",
    "duration_minutes": 18.3
  }
]
```

Run the dashboard to see an aggregated view:

```
docker compose -f automation/docker-compose.yml run dashboard
```

```
======================================================================
   DEVIN REMEDIATION DASHBOARD
======================================================================

  SUMMARY
  -------
  Total sessions initiated : 3
  ✅  Completed            : 3
  ❌  Failed / Errored     : 0
  Success rate             : 100%
  Avg fix duration         : 21.4 min
  Pull requests opened     : 3

  PER-ISSUE BREAKDOWN
  ------------------------------------------------------------------
  ISSUE    STATUS       DURATION     SESSION / PR
  ------------------------------------------------------------------
  #1       ✅ completed  18.3 min     PR #4  (https://github.com/...)
  #2       ✅ completed  22.1 min     PR #5  (https://github.com/...)
  #3       ✅ completed  23.8 min     PR #6  (https://github.com/...)

  SYSTEM HEALTH
  ------------------------------------------------------------------
  🟢  All sessions completed successfully. System is healthy.
======================================================================
```

Status updates are also posted directly as comments on each GitHub issue, so any engineer watching the issue gets real-time progress without checking the logs.

---

## Extending This System

| Next Step | How |
|-----------|-----|
| Trigger from a vulnerability scanner | POST to the GitHub Issues API with `devin-fix` label when a CVE is detected |
| Add Slack notifications | Call the Slack API in `devin_remediate.py` after posting the GitHub comment |
| Run on a schedule | Change `on: issues: [labeled]` to `on: schedule: [{cron: "0 9 * * 1"}]` and query open issues |
| Scale to multiple repos | Make `GITHUB_REPO` a matrix parameter in the workflow |
| Metrics in CI | Upload `sessions.json` as a GitHub Actions artifact for audit trails |
