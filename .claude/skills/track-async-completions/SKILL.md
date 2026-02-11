# Track Async Interview Completions

Reads async interview completion emails from Gmail (Hireflix and HireTruffle), matches candidates in the Notion Candidates DB, and creates Interaction records in the Interactions DB.

## Quick Start

```bash
# 1. Discover — inspect raw Hireflix emails
python3.11 .claude/skills/track-async-completions/workflows/track_async_completions.py --discover

# 2. Dry run — preview matches without creating records
python3.11 .claude/skills/track-async-completions/workflows/track_async_completions.py --dry-run

# 3. Create Interaction records
python3.11 .claude/skills/track-async-completions/workflows/track_async_completions.py

# 4. Force-link an unmatched candidate
python3.11 .claude/skills/track-async-completions/workflows/track_async_completions.py --message-id <gmail_id> --page-id <notion_page_id>
```

## How It Works

1. Authenticates Gmail with `compose + readonly` scopes (shared auth with invite-candidates)
2. Loads all platform configs from `templates/platform-config.json`
3. Searches Gmail using each config's search query (deduped by message ID)
4. Parses each email by trying all configs in order until one matches
5. Matches candidate in Notion Candidates DB by Full Name (pool-scoped fuzzy matching)
6. Checks for existing Interaction record (dedup)
7. Creates Interaction record with assessment link
8. Saves receipt to `local-data/talent/async_completions/`

## Candidate Matching

Primary match is by **Full Name** (title field in Candidates DB), since Hireflix completion emails don't contain the candidate's email address.

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

Email parsing is config-driven via `templates/platform-config.json`. Multiple config entries are supported — the parser tries each in order until one matches. To tune patterns (e.g., if Hireflix changes their email format), edit the JSON — no code changes needed.

### Active Configs

| Config Key | Source | Status |
|------------|--------|--------|
| `hireflix` | `no-reply@hireflix.com` completion emails | Active |
| `hiretruffle` | HireTruffle notification emails to `recruitment@withally.com` | **PLACEHOLDER** — patterns need updating |

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
