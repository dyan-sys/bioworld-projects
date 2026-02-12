# Track Async Interview Completions & Calendly Bookings

Reads completion/booking emails from Gmail (Hireflix, HireTruffle, Calendly), matches candidates in Notion, and takes per-config actions:
- **create_interaction**: Creates an Interaction record + updates 1R status (Hireflix/HireTruffle)
- **status_update_only**: Updates 1R status only, no Interaction record (Calendly → "Scheduled")

## Quick Start

```bash
# 1. Discover — inspect raw Hireflix emails
python3.11 .claude/skills/track-recruitment-events/workflows/track_async_completions.py --discover

# 2. Dry run — preview matches without creating records
python3.11 .claude/skills/track-recruitment-events/workflows/track_async_completions.py --dry-run

# 3. Create Interaction records
python3.11 .claude/skills/track-recruitment-events/workflows/track_async_completions.py

# 4. Force-link an unmatched candidate
python3.11 .claude/skills/track-recruitment-events/workflows/track_async_completions.py --message-id <gmail_id> --page-id <notion_page_id>
```

## How It Works

1. Authenticates Gmail with `compose + readonly` scopes (shared auth with invite-candidates)
2. Loads all platform configs from `templates/platform-config.json`
3. Searches Gmail using each config's search query (deduped by message ID)
4. Parses each email by trying all configs in order until one matches
5. Loads candidate pools per unique `candidate_pool_statuses` set
6. Matches candidate: email-based (`match_by_email`) → pool-scoped fuzzy name
7. Guards on 1R status (`guard_1r_status`)
8. Executes action: `create_interaction` (dedup + create + 1R update) or `status_update_only` (1R update only)
9. Saves receipt to `local-data/talent/async_completions/`

## Candidate Matching

Two strategies, controlled by config:
- **Fuzzy name** (default): Match `candidate_name` from email against a pool scoped by `candidate_pool_statuses`
- **Email-first** (`match_by_email: true`): Search Candidates DB by Email property, fall back to fuzzy name

For unmatched candidates, use `--message-id` + `--page-id` to force-link.

## Dedup

Two layers prevent duplicate records:
1. **Local receipts**: Keyed by Gmail message ID in `local-data/talent/async_completions/`
2. **Notion query**: Checks for existing Interaction with same Candidate + Type

## CLI Options

| Flag | Description |
|------|-------------|
| `--discover` | Print raw email structure for inspection |
| `--dry-run` | Preview without creating Notion records |
| `--days N` | Lookback window (default: 7) |
| `--limit N` | Max emails to process (default: 10) |
| `--message-id` | Process a specific Gmail message ID |
| `--page-id` | Force-link to a Notion candidate page (with --message-id) |

## Configuration

Email parsing is config-driven via `templates/platform-config.json`. Multiple config entries are supported — the parser tries each in order until one matches. To tune patterns (e.g., if a platform changes their email format), edit the JSON — no code changes needed.

### Per-Config Behavior Fields

| Field | Description | Default |
|-------|-------------|---------|
| `candidate_pool_statuses` | Screener statuses to build the candidate pool | (required) |
| `action` | `create_interaction` or `status_update_only` | `create_interaction` |
| `target_1r_status` | 1R status to set after processing | `Async Done - Awaiting Review` |
| `guard_1r_status` | Expected current 1R status (guard check) | `Invitation Sent` |
| `match_by_email` | If true, try email match before fuzzy name | `false` |
| `body_email_pattern` | Regex to extract invitee email from body | (none) |

### Active Configs

| Config Key | Source | Action | Status |
|------------|--------|--------|--------|
| `hireflix` | `no-reply@hireflix.com` completion emails | `create_interaction` | Active |
| `hiretruffle` | HireTruffle notification emails | `create_interaction` | **PLACEHOLDER** — patterns need updating |
| `calendly` | `notifications@calendly.com` booking emails | `status_update_only` | **PLACEHOLDER** — tune patterns after `--discover` |

### Calendly Booking Tracking

Detects Calendly "New Event" emails for R1 Live interviews and sets 1R → "Scheduled".

- **Pool:** Candidates with `Screener = "To Invite"` (live interview path)
- **Match:** Email-first (Calendly includes invitee email), fallback to fuzzy name
- **Action:** `status_update_only` — no Interaction record, just 1R status update
- **Limitation:** Reschedules/cancellations are not auto-tracked (Gmail parsing constraint)

Activated Feb 2026 — patterns tuned from real Calendly emails, dry-run verified.

### Activating HireTruffle Completion Tracking

When HireTruffle notification emails are enabled:

1. Enable "For all completed interviews" in HireTruffle Settings > Notifications
2. Notifications go to `recruitment@withally.com`
3. Wait for the first completion email to arrive
4. Run `--discover` to inspect the email format
5. Update `hiretruffle` patterns in `platform-config.json` to match the real format (sender, subject pattern, body patterns, assessment link pattern)
6. Remove the `_status` field from the config entry
7. Run `--dry-run` to verify parsing works

## Requirements

- Gmail OAuth2 credentials (shared with invite-candidates skill)
- First run with new scopes triggers browser re-auth
- Environment variables: `NOTION_KEY`, `NOTION_DB_ID`
- Python 3.11+
- Dependencies: `requests`, `python-dotenv`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`

## Notion Databases

- **Candidates DB**: env var `NOTION_DB_ID`
- **Interactions DB**: `28c2b7ec459780c9bf6ffb86f3b9aa9c`

## Interaction Record Fields

| Field | Value |
|-------|-------|
| `Name` (title) | `R1 Async - {Candidate Name}` |
| `Candidate` (relation) | Link to candidate page |
| `Type` (select) | `1st Round (Async)` |
| `Assessment Link` (url) | Hireflix admin interview URL |
| `Interaction Date` (date) | Date from completion email |
