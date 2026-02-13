# Daily Pepper

Morning calendar summary bot. Fetches today's Google Calendar events and sends a Slack DM overview.

## Workflow

1. **Auth** — OAuth2 to Google Calendar (read-only scope)
2. **Fetch** — Pull today's events from configured calendars
3. **Format** — Build summary with event list + free blocks
4. **Send** — DM via Slack Bot Token (`chat_postMessage`)

## Usage

```bash
# Dry run (preview without sending DM)
python3.11 .claude/skills/daily-pepper/workflows/daily_pepper.py --dry-run

# Live (sends Slack DM)
python3.11 .claude/skills/daily-pepper/workflows/daily_pepper.py

# Specific date
python3.11 .claude/skills/daily-pepper/workflows/daily_pepper.py --date 2026-02-14
```

## Config

`templates/pepper-config.json`:

| Key | Description | Default |
|-----|-------------|---------|
| `slack_user_id` | Slack user ID to DM | `U0975UFHDB8` |
| `calendar_ids` | Google Calendar IDs to query | `["primary"]` |
| `work_hours.start` | Work day start hour (for free blocks) | `9` |
| `work_hours.end` | Work day end hour (for free blocks) | `18` |
| `show_free_blocks` | Include free block computation | `true` |

## Message Format

```
:sunny: Daily Pepper | Thu, Feb 13 2026

:clipboard: 3 events today

  All day  Company Holiday
  09:00 - 10:00  Team standup
  10:30 - 11:30  Client call -- Zoom

:clock1: Free blocks: 11:30-14:00, 15:00 onwards
```

Empty day: "No events on your calendar today. Wide open!"

## Prerequisites

- **Google Calendar API** enabled in Google Cloud Console (same project as `Google-credentials.json`)
- **First run** triggers browser OAuth consent → saves `local-data/calendar_token.json`
- **SLACK_BOT_TOKEN** env var with `chat:write` scope

## Schedule

7:00 AM SGT daily via `com.ally.daily-pepper.plist`.

## Files

```
.claude/skills/daily-pepper/
├── SKILL.md
├── libraries/
│   ├── calendar_auth.py      # OAuth2 for Google Calendar
│   └── calendar_reader.py    # Fetch + normalize events, free blocks
├── templates/
│   └── pepper-config.json    # Slack user, calendars, work hours
└── workflows/
    └── daily_pepper.py       # Main workflow
```
