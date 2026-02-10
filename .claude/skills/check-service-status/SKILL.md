---
name: check-service-status
description: Trigger when user mentions checking service status, job health, scheduled task monitoring, or whether daily jobs ran successfully
---

# Check Service Status Skill

Monitors scheduled jobs by reading status files written by the generic `run-job.sh` wrapper. Checks whether each registered job ran on time, exited cleanly, and produced expected artifacts.

## Health Levels

| Status | Meaning |
|--------|---------|
| OK | Job ran, exit 0, all artifact checks pass |
| WARN | Job ran, exit 0, but some artifact checks failed |
| FAIL | Job ran but exited non-zero |
| MISSED | No status file found (job didn't run) |

## How to Run

```bash
# Check all registered jobs for today
python3.11 .claude/skills/check-service-status/workflows/check_service_status.py

# Check a specific job
python3.11 .claude/skills/check-service-status/workflows/check_service_status.py --job pipeline-report

# Check a specific date
python3.11 .claude/skills/check-service-status/workflows/check_service_status.py --date 2026-02-09
```

## Adding a New Job

1. Add an entry to `templates/job-registry.json`
2. No code changes needed

## Requirements

- Python 3.11+
- Environment variable: `SLACK_WEBHOOK_URL` (optional, for Slack posting)
- Dependencies: `requests`, `python-dotenv`
