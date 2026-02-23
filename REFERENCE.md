# Reference

Extended documentation for Ally OS. Read on-demand — not loaded every session.

## Environment Variables

Create a `.env` file with:

```
NOTION_KEY=secret_xxx        # Notion integration token
NOTION_DB_ID=xxx             # Notion database ID
MOONSHOT_API_KEY=xxx         # Moonshot AI API key (for Kimi screener)
MOONSHOT_API_KEY_EP=xxx      # Separate Moonshot key for EP channel review (optional, falls back to MOONSHOT_API_KEY)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...        # Slack Incoming Webhook (optional, for daily report)
SLACK_WEBHOOK_URL_JARVIS=https://hooks.slack.com/services/... # Slack webhook for #ally-jarvis (service status)
SLACK_BOT_TOKEN=xoxb-xxx                                     # Slack Bot Token (channels:history, users:read)
SLACK_APP_TOKEN=xapp-1-xxx                                   # Slack App-Level Token (Socket Mode)
GEMINI_API_KEY=xxx                                            # Google AI Studio API key (Gemini, for background check)
SERPER_API_KEY=xxx                                            # Serper.dev API key (Google Search, for background check)
NOTION_SPEND_DB_ID=xxx                                        # Notion database ID for AI Spend tracking
```

## Data Architecture

```
local-data/
├── logs/                         # Scheduling logs (launchd output)
├── service-status/               # Job status JSONs from run-job.sh
│   ├── {job-id}_{timestamp}.json
│   └── reports/                  # Service check report snapshots
├── slack-mentions/               # Mention monitor state
│   └── state.json
├── linkedin/                     # LinkedIn content engine artifacts
│   ├── research/
│   └── drafts/
├── ai-spend/                     # AI spend tracking receipts
├── slides/                       # Slides generation receipts
└── talent/
    ├── resume_raw_txt/           # Extracted resume text
    ├── resume_receipts/          # Full scoring JSON (Claude + Kimi)
    ├── pipeline_reports/         # Daily pipeline report snapshots
    ├── ep_reviews/               # EP channel review artifacts
    ├── async_completions/        # Recruitment event tracking receipts
    └── invite_emails/            # R1 invite draft receipts
```

## Scheduling

Scheduled jobs run via macOS `launchd`. All jobs use `scheduling/run-job.sh` which handles network readiness, logging, and status tracking.

```bash
scheduling/run-job.sh <job-id> <python-script>
```

Status values: `success` (exit 0), `failed` (exit non-zero), `network_unavailable`

| Job | Schedule (SGT) | Plist |
|-----|----------------|-------|
| Daily Pipeline Report | 08:00 daily | `com.ally.pipeline-report.plist` |
| EP Channel Issue Flagging | 08:00 daily | `com.ally.ep-issues.plist` |
| Scheduled Job Posts | 08:00 Mon + Wed + Thu | `com.ally.job-posts.plist` |
| Resume Screener (Kimi) | 08:00, 12:00, 16:00, 20:00 | `com.ally.resume-screener.plist` |
| Slack Mention Monitor | 09:00, 13:00, 17:00 | `com.ally.slack-mentions.plist` |
| Recruitment Completion Tracker | 08:00, 12:00, 18:00 | `com.ally.recruitment-events.plist` |
| Service Health Check | 09:00 daily | `com.ally.service-check.plist` |
| AI Spend Tracker | 08:00 on 8th, 18th, 28th | `com.ally.ai-spend.plist` |
| Daily Pepper | 07:00 daily | `com.ally.daily-pepper.plist` |
| Ally Slack Bot | Always (daemon) | `com.ally.slack-bot.plist` |

### Adding a New Scheduled Job

1. Create a launchd plist (copy existing, update Label/ProgramArguments/schedule)
2. Add entry to `.claude/skills/check-service-status/templates/job-registry.json`
3. Install plist to `~/Library/LaunchAgents/` and bootstrap

### Install / Uninstall

```bash
# Install (example for pipeline report — repeat pattern for other jobs)
cp scheduling/com.ally.pipeline-report.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ally.pipeline-report.plist

# Uninstall
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ally.pipeline-report.plist
rm ~/Library/LaunchAgents/com.ally.pipeline-report.plist
```

**Logs:** `local-data/logs/` (gitignored)
**Status files:** `local-data/service-status/` (gitignored)
