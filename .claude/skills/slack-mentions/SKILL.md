---
name: slack-mentions
description: Trigger when user mentions checking Slack mentions, unactioned mentions, missed messages, or mention monitoring
---

# Slack Mention Monitor

Scans all Slack channels the bot is in for unactioned @ mentions of a monitored user. Sends a DM summary with deep links so nothing falls through the cracks.

## What It Checks

| Criteria | Description |
|----------|-------------|
| Mention detected | Message contains `<@USER_ID>` in text |
| Not self-mention | Sender is not the monitored user |
| Not actioned | No reaction from user AND no thread reply from user |
| Not already notified | State file prevents duplicate DMs |

## How to Run

```bash
# Default (8-hour lookback)
python3.11 .claude/skills/slack-mentions/workflows/check_mentions.py

# Dry run (preview without sending DM)
python3.11 .claude/skills/slack-mentions/workflows/check_mentions.py --dry-run

# Custom lookback window
python3.11 .claude/skills/slack-mentions/workflows/check_mentions.py --lookback-hours 24

# Override monitored user
python3.11 .claude/skills/slack-mentions/workflows/check_mentions.py --user-id U0975UFHDB8
```

## Configuration

Edit `templates/mention-config.json` — no code changes needed.

| Field | Description |
|-------|-------------|
| `monitored_user_id` | Slack user ID to watch for mentions |
| `lookback_hours` | How far back to scan (default: 8) |
| `channel_types` | Channel types to scan (public_channel, private_channel) |
| `exclude_channels` | Channel IDs to skip |
| `exclude_bot_messages` | Skip messages from bots |
| `max_preview_length` | Max chars in message preview (default: 120) |
| `state_retention_hours` | How long to keep notified state (default: 48) |

## Requirements

- Python 3.11+
- Environment variable: `SLACK_BOT_TOKEN`
- Slack bot scopes: `channels:history`, `channels:read`, `users:read`, `chat:write`
- Optional for private channels: `groups:read`, `groups:history`
- Dependencies: `slack-sdk`, `python-dotenv`
- Bot must be invited to channels to monitor them
