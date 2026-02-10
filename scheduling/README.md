# Scheduling

Scheduled jobs run via macOS `launchd`. All jobs use a shared generic wrapper (`run-job.sh`) that handles network readiness, logging, and status tracking.

## Scheduled Jobs

| Job | Schedule | Plist |
|-----|----------|-------|
| Daily Pipeline Report | 00:00 UTC (08:00 SGT) | `com.ally.pipeline-report.plist` |
| Service Health Check | 02:00 UTC (10:00 SGT) | `com.ally.service-check.plist` |

## Generic Wrapper (`run-job.sh`)

All jobs are run through `run-job.sh`, which:
1. Waits for network readiness (DNS check against `api.notion.com`)
2. Runs the Python script, capturing stdout+stderr to `local-data/logs/{job-id}_{timestamp}.log`
3. Writes a status JSON to `local-data/service-status/{job-id}_{timestamp}.json`

```bash
# Usage
scheduling/run-job.sh <job-id> <python-script>

# Example
scheduling/run-job.sh pipeline-report \
  .claude/skills/check-recruit-status/workflows/check_recruit_status.py
```

Status JSON fields:
- `job_id`, `started_at`, `finished_at`, `duration_seconds`, `exit_code`
- `status`: `success` | `failed` | `network_unavailable`
- `log_file`: relative path to log file

## Setup

### 1. Create Slack Incoming Webhook

1. Go to https://api.slack.com/apps → **Create New App** → From scratch
2. **Incoming Webhooks** → Activate → **Add New Webhook to Workspace**
3. Choose the target channel → **Allow**
4. Copy the Webhook URL

### 2. Add to `.env`

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

### 3. Install launchd plists

```bash
# Pipeline report (08:00 SGT)
cp scheduling/com.ally.pipeline-report.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ally.pipeline-report.plist

# Service health check (10:00 SGT)
cp scheduling/com.ally.service-check.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ally.service-check.plist
```

### 4. Test

Trigger immediately:

```bash
# Pipeline report
launchctl start com.ally.pipeline-report

# Service check
launchctl start com.ally.service-check
```

Check logs:

```bash
ls local-data/logs/
ls local-data/service-status/
```

## Uninstall

```bash
# Pipeline report
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ally.pipeline-report.plist
rm ~/Library/LaunchAgents/com.ally.pipeline-report.plist

# Service check
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ally.service-check.plist
rm ~/Library/LaunchAgents/com.ally.service-check.plist
```

## Adding a New Scheduled Job

1. **Create a per-job shim** (optional, or call `run-job.sh` directly from the plist):
   ```bash
   #!/bin/bash
   DIR="$(cd "$(dirname "$0")" && pwd)"
   exec "$DIR/run-job.sh" my-job-id path/to/script.py
   ```

2. **Create a launchd plist** — copy an existing one and update Label, ProgramArguments, and schedule.

3. **Register for monitoring** — add an entry to `.claude/skills/check-service-status/templates/job-registry.json`.

4. **Install** — copy plist to `~/Library/LaunchAgents/` and bootstrap.

## Files

| File | Purpose |
|------|---------|
| `run-job.sh` | Generic wrapper: network wait, run script, write status JSON |
| `run-pipeline-report.sh` | Shim: calls run-job.sh for pipeline report |
| `com.ally.pipeline-report.plist` | launchd schedule (daily 00:00 UTC) |
| `com.ally.service-check.plist` | launchd schedule (daily 02:00 UTC) |

## Notes

- Reports still work without `SLACK_WEBHOOK_URL` — they print to console and save files, just skip Slack.
- Logs go to `local-data/logs/` (gitignored).
- Status files go to `local-data/service-status/` (gitignored).
- Plists use absolute paths. If you move the project, update the plists and re-install.
