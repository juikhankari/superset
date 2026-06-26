# Devin Auto-Remediation System

> **Live observability dashboard → https://juikhankari.github.io/superset/**

An event-driven automation that monitors this Apache Superset fork for issues labeled **`devin-fix`** and uses the [Devin API](https://docs.devin.ai/api-reference/overview) to autonomously fix them — opening pull requests and posting status updates with no human in the fix loop.

---

## The Problem

Every engineering team carries a backlog of known bugs — crash paths, unhandled exceptions, low-severity issues — that never get fixed because the cost of context-switching outweighs the benefit of any individual fix. They accumulate silently until they become user-facing incidents.

**This system makes fixing them zero-touch.** A developer labels an issue `devin-fix`, and Devin autonomously clones the repo, navigates the codebase, writes and tests a patch, and opens a pull request — without any human involvement in the fix loop.

**Why Devin specifically?** These fixes aren't mechanical. They require understanding the surrounding code, writing contextually correct patches, and producing a coherent PR description. A static script or template can't do that. Devin can.

**Business impact:** In this demo, Devin resolved 3 crash-path bugs in Apache Superset at an average of 56 minutes per fix, with a 100% success rate. At scale, this pattern eliminates entire categories of engineering toil.

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
   ├── POST /sessions             → Devin API: start a session with full issue context
   ├── GET  /sessions/{id}        → Poll every 30s until done or PR detected
   ├── POST /issues/{n}/comments  → GitHub API: post status updates on the issue
   └── Append to sessions.json   → Structured observability log
           │
           ▼
   Devin works autonomously
   └── Opens a Pull Request in this repo
```

**Key design decisions:**
- The trigger is a GitHub label event — zero infrastructure beyond GitHub Actions. No webhooks to manage, no servers to run.
- Polling exits early when a `pull_request.url` appears in the Devin response, so the session doesn't block for its full timeout after Devin finishes.
- `sessions.json` is committed back to the repo after every run, making the observability log persistent and auditable without external storage.

---

## Issues Remediated

Three verified crash-path bugs in `superset/views/core.py`, all caused by unguarded operations on user-controlled input:

| Issue | Title | Root Cause | PR |
|-------|-------|-----------|-----|
| [#4](https://github.com/juikhankari/superset/issues/4) | Malformed `datasourceKey` in `datasource_metadata` | `KeyError` on unparseable input | [#10](https://github.com/juikhankari/superset/pull/10) ✅ merged |
| [#5](https://github.com/juikhankari/superset/issues/5) | Malformed datasource string in `get_redirect_url` | `ValueError` on bad format | [#11](https://github.com/juikhankari/superset/pull/11) ✅ merged |
| [#6](https://github.com/juikhankari/superset/issues/6) | `JSONDecodeError` on cached explore form data | No guard on corrupt cache | [#12](https://github.com/juikhankari/superset/pull/12) ✅ merged |

Each bug caused a **500 Internal Server Error** on a path that should return a **400** or degrade gracefully.

---

## Repository Layout

```
.github/
└── workflows/
    └── devin-remediate.yml   ← Event trigger: fires on "devin-fix" label

scripts/
├── create_issues.py          ← Seeds the three bug issues with the label
├── devin_remediate.py        ← Core: starts Devin session, polls, logs results
├── dashboard.py              ← Observability: prints aggregated status report
└── requirements.txt          ← Python deps (just requests)

automation/
├── Dockerfile                ← Packages scripts into a container
├── docker-compose.yml        ← Run any step locally without GitHub Actions
└── .env.example              ← Environment variable template

logs/
└── sessions.json             ← Auto-generated structured log of every session
```

---

## Quick Start (Docker)

```bash
git clone https://github.com/juikhankari/superset.git
cd superset
cp automation/.env.example automation/.env
# Fill in DEVIN_API_KEY, DEVIN_ORG_ID, GITHUB_TOKEN in automation/.env
```

**View the observability dashboard** (works immediately — reads existing session log):
```bash
docker compose -f automation/docker-compose.yml run dashboard
```

**Simulate creating new issues** (also triggers the GitHub Action automatically):
```bash
docker compose -f automation/docker-compose.yml run create-issues
```

**Simulate remediation locally** for a single issue (set `ISSUE_NUMBER`, `ISSUE_TITLE`, `ISSUE_BODY`, `ISSUE_URL` in `.env`):
```bash
docker compose -f automation/docker-compose.yml run remediate
```

### Secrets required

Set these in **GitHub → Settings → Secrets and variables → Actions**:

| Secret | Where to get it |
|--------|----------------|
| `DEVIN_API_KEY` | [app.devin.ai](https://app.devin.ai) → Settings → API |
| `DEVIN_ORG_ID` | Same page, visible in your org URL |

`GITHUB_TOKEN` is provided automatically by GitHub Actions — no setup needed.

Also grant Devin access to this repo: **Devin → Settings → Connections → GitHub → select repo**.

---

## Observability

Every session is logged to `logs/sessions.json`:

```json
[
  {
    "timestamp": "2026-06-25T20:51:01+00:00",
    "issue_number": "4",
    "issue_title": "fix(views): handle malformed datasourceKey...",
    "session_id": "devin-de3ed4ba7e8b4d46a9888adb510ed4ff",
    "session_url": "https://app.devin.ai/sessions/de3ed4ba7e8b4d46a9888adb510ed4ff",
    "status": "completed",
    "pr_url": "https://github.com/juikhankari/superset/pull/10",
    "duration_minutes": 55.3
  }
]
```

The dashboard aggregates this into a leadership-readable report:

```
======================================================================
   DEVIN REMEDIATION DASHBOARD
======================================================================

  SUMMARY
  -------
  Total sessions initiated : 3        Success rate    : 100%
  ✅  Completed            : 3        Avg fix duration: 56.3 min
  ❌  Failed / Errored     : 0        Pull requests   : 3

  PER-ISSUE BREAKDOWN
  ------------------------------------------------------------------
  #4   ✅ completed   55.3 min   PR #10
  #5   ✅ completed   56.1 min   PR #11
  #6   ✅ completed   57.4 min   PR #12

  🟢  All sessions completed successfully. System is healthy.
======================================================================
```

A live web version is at **https://juikhankari.github.io/superset/**

Status updates are also posted as comments on each GitHub issue, so engineers watching the issue get real-time progress automatically.

---

## Extending This

| Next Step | Implementation |
|-----------|---------------|
| Trigger from a vulnerability scanner | POST to GitHub Issues API with `devin-fix` label when a CVE is found |
| Slack notifications | Call Slack API in `devin_remediate.py` after posting the GitHub comment |
| Scheduled sweeps | Change `on: issues: [labeled]` to `on: schedule` and query open issues |
| Multi-repo | Parameterize `GITHUB_REPO` as a matrix variable in the workflow |
| Persistent metrics | Upload `sessions.json` as a GitHub Actions artifact for audit trails |
