# Daily Pepper

Morning calendar summary bot. Fetches today's Google Calendar events, Linear focus issues, and Gmail inbox highlights, then sends a Slack DM overview.

## Workflow

1. **Auth** — OAuth2 to Google Calendar (read-only scope)
2. **Fetch Calendar** — Pull today's events from configured calendars
3. **Fetch Linear** — Pull active issues for the Focus Board (graceful skip if unconfigured)
4. **Fetch Gmail** — Fetch last 24h of emails, prioritize via Gemini (graceful skip if unconfigured)
5. **Format** — Build summary with event list + free blocks + focus board + inbox highlights
6. **Send** — DM via Slack Bot Token (`chat_postMessage`)

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
| `linear_team_id` | Linear team UUID for Focus Board (omit to skip) | — |

## Message Format

```
:sunny: Daily Pepper | Thu, Feb 13 2026

:clipboard: 3 events today

  All day  Company Holiday
  09:00 - 10:00  Team standup
  10:30 - 11:30  Client call -- Zoom

:clock1: Free blocks: 11:30-14:00, 15:00 onwards

:dart: *Focus Board*

_Strategic Impact:_
  :rotating_light: WA-12 Finalize SOW for ACME Corp
  :arrow_up: WA-34 Review Q1 hiring metrics
  :arrow_up: WA-45 Migrate candidate DB schema

_Quick Wins:_
  :arrow_right: WA-78 Update Jobstreet posting template
  :arrow_right: WA-91 Fix typo in R1 invite email
  :arrow_down: WA-102 Archive old EP channels

:email: *Inbox Highlights*

_Needs Attention:_
  :red_circle: Cherie Wong — Re: SOW Review for ACME Corp
  :red_circle: Jeffrey Yu — Availability for Monday sync?
  :red_circle: Jobstreet — 3 new applications received

_Worth Knowing:_
  :large_blue_circle: Linear — WIT-82 marked as done
  :large_blue_circle: Google Calendar — Event updated: Team standup
  :large_blue_circle: Notion — Page shared: Q1 Hiring Dashboard
```

Empty day: "No events on your calendar today. Wide open!"

Focus Board is omitted if `linear_team_id` is not set, `LINEAR_API_KEY` is missing, or the API call fails.

Inbox Highlights is omitted if `gmail_token_ivan.json` doesn't exist, `GEMINI_API_KEY` is missing, or the API call fails.

## Focus Board Logic

- **Query:** Active issues (state type `unstarted` or `started`) with priority 1-4, limit 50
- **Strategic Impact** (top 3): Priority 1 (Urgent) + 2 (High), sorted by priority then oldest first
- **Quick Wins** (top 3): Priority 3 (Normal) + 4 (Low), sorted by most recently updated

## Inbox Highlights Logic

- **Fetch:** Last 24h emails via `newer_than:1d` query, up to 20 messages
- **Prioritize:** Gemini (`gemini-2.5-flash`) picks up to 6 emails across two buckets:
  - **Needs Attention** (up to 3): requires a response, action, or decision soon
  - **Worth Knowing** (up to 3): informational but important to be aware of
- **Token:** Reuses `local-data/gmail_token_ivan.json` (ivan@withally.com, `gmail.readonly` scope)

## Prerequisites

- **Google Calendar API** enabled in Google Cloud Console (same project as `Google-credentials.json`)
- **First run** triggers browser OAuth consent → saves `local-data/calendar_token.json`
- **SLACK_BOT_TOKEN** env var with `chat:write` scope
- **LINEAR_API_KEY** env var (Personal API key from Linear Settings > Account > API) — optional, Focus Board skipped without it
- **GEMINI_API_KEY** env var — optional, Inbox Highlights skipped without it
- **Gmail token** at `local-data/gmail_token_ivan.json` with `gmail.readonly` scope — optional, Inbox Highlights skipped without it

## Schedule

7:00 AM SGT daily via `com.ally.daily-pepper.plist`.

## Files

```
.claude/skills/daily-pepper/
├── SKILL.md
├── libraries/
│   ├── calendar_auth.py      # OAuth2 for Google Calendar
│   ├── calendar_reader.py    # Fetch + normalize events, free blocks
│   ├── gmail_pepper.py       # Fetch + Gemini-prioritize Gmail inbox
│   └── linear_reader.py      # Fetch + categorize Linear issues for Focus Board
├── templates/
│   └── pepper-config.json    # Slack user, calendars, work hours, Linear team
└── workflows/
    └── daily_pepper.py       # Main workflow
```
