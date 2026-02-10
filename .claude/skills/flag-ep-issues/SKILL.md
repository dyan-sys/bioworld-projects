---
name: flag-ep-issues
description: Trigger when user mentions reviewing EP channels, flagging EP issues, checking EP Slack activity, or daily EP channel review
---

# Flag EP Issues Skill

Reviews EP (Executive Partner) Slack channel conversations daily. Reads yesterday's messages from monitored channels, sends a batched analysis to Kimi AI, and posts flagged issues to #ally-jarvis.

## What It Flags

| Type | Description |
|------|-------------|
| Missed Item | Unanswered questions, unacknowledged requests |
| Stalled Progress | Repeated follow-ups, no movement on topics |
| No Activity | Channels with zero messages |

## How to Run

```bash
# Default (yesterday's conversations)
python3.11 .claude/skills/flag-ep-issues/workflows/flag_ep_issues.py

# Specific date
python3.11 .claude/skills/flag-ep-issues/workflows/flag_ep_issues.py --date 2026-02-09

# Single channel
python3.11 .claude/skills/flag-ep-issues/workflows/flag_ep_issues.py --channel C0XXXXXX

# Dry run (no Slack posting)
python3.11 .claude/skills/flag-ep-issues/workflows/flag_ep_issues.py --dry-run
```

## Adding/Removing Channels

Edit `templates/channel-registry.json` — no code changes needed.

## Requirements

- Python 3.11+
- Environment variables: `MOONSHOT_API_KEY_EP` (or `MOONSHOT_API_KEY` fallback), `SLACK_BOT_TOKEN`
- Optional: `SLACK_WEBHOOK_URL_JARVIS` (for posting to Slack)
- Dependencies: `slack-sdk`, `openai`, `httpx`, `h2`, `requests`, `python-dotenv`
- Slack bot must be invited to each monitored channel
