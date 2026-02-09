# Scheduling

Daily pipeline report via macOS `launchd`. Runs at 00:00 UTC (08:00 SGT) and posts to Slack.

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

### 3. Install the launchd plist

```bash
cp scheduling/com.ally.pipeline-report.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ally.pipeline-report.plist
```

### 4. Test

Trigger immediately:

```bash
launchctl start com.ally.pipeline-report
```

Check logs:

```bash
ls local-data/logs/
cat local-data/logs/launchd-stdout.log
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.ally.pipeline-report.plist
rm ~/Library/LaunchAgents/com.ally.pipeline-report.plist
```

## Files

| File | Purpose |
|------|---------|
| `com.ally.pipeline-report.plist` | launchd schedule (daily 00:00 UTC) |
| `run-pipeline-report.sh` | Wrapper: sets PATH, runs script, logs output |

## Notes

- The report still works without `SLACK_WEBHOOK_URL` — it prints to console and saves the file, just skips Slack.
- Logs go to `local-data/logs/` (gitignored).
- The plist uses absolute paths. If you move the project, update both the plist and re-install.
