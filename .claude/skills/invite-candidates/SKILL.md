---
name: invite-candidates
description: Trigger when user mentions inviting candidates, sending interview invitations, drafting interview emails, or scheduling Round 1 interviews
---

# Invite Candidates Skill

Creates Gmail DRAFT emails for R1 interview invitations. Routes candidates to the correct HTML email template based on their Screener status using a config-driven mapping.

**SAFETY: This workflow NEVER sends emails. It only creates drafts. A human must review and send each draft manually from Gmail.**

## R1 Invite Routing

Configured in `templates/R1-invite-mapping.json`:

| Screener Status | Template | Interview Type |
|---|---|---|
| `To Invite` | `R1-Live-Invite.md` | Live interview (Calendly) |
| `To invite (Async)` | `R1-Async-Truffle-Invite.md` | Async interview (HireTruffle) |
| `To invite (Async Hireflix)` | `R1-Async-Hireflix-Invite.md` | Async interview (Hireflix) |

**Guard:** Only candidates with `1R = "Not Started"` are processed — prevents re-inviting candidates already emailed.

**Scope:** Candidates last edited within 120 hours (5 days).

**Adding new routes:** Edit `R1-invite-mapping.json` to add a new Screener status mapping. No code changes needed.

## How It Works

1. Loads routing config from `R1-invite-mapping.json`
2. Queries Candidates DB for matching Screener statuses with `1R = "Not Started"` guard
3. Selects the correct HTML email template per candidate's Screener status
4. Renders template with `{first_name}`, creates Gmail draft
5. Saves receipt JSON to `local-data/talent/invite_emails/`

## How to Run

### Batch Mode (default)

Process candidates matching configured statuses (default limit 10):

```bash
python3.11 .claude/skills/invite-candidates/workflows/invite_candidates.py
python3.11 .claude/skills/invite-candidates/workflows/invite_candidates.py --limit 20
```

### Single Candidate

Invite a specific candidate by Notion page ID:

```bash
python3.11 .claude/skills/invite-candidates/workflows/invite_candidates.py --page-id <notion_page_id>
```

### Dry Run (preview without creating drafts)

```bash
python3.11 .claude/skills/invite-candidates/workflows/invite_candidates.py --dry-run
```

## Data Output

```
local-data/talent/invite_emails/
├── R1-Live-{CandidateName}.json
├── R1-Async-Truffle-{CandidateName}.json
└── R1-Async-Hireflix-{CandidateName}.json
```

## Requirements

- Python 3.11+
- Environment variables: `NOTION_KEY`, `NOTION_DB_ID`
- Gmail OAuth2 credentials: `credentials.json` in project root (or set `GMAIL_CREDENTIALS_PATH`)
- Dependencies: `requests`, `python-dotenv`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`

### Gmail Setup (First Time)

1. Create a Google Cloud project and enable the Gmail API
2. Create OAuth2 credentials (Desktop app type)
3. Download `credentials.json` to the project root
4. Run the workflow — a browser window will open for OAuth consent
5. Token is saved to `local-data/gmail_token.json` for subsequent runs

## Edge Cases

- **No email:** Candidate is skipped with `[SKIP] No email address`
- **Unknown status:** Skipped if Screener status has no matching template in routing config
- **Empty name:** Greeting falls back to "Hi there,"
- **Dry run:** Skips Gmail auth, renders and saves receipts without creating drafts
- **Single mode:** Works regardless of guard field (skips if no template match)
- **Duplicate runs:** Creates duplicate drafts — check Gmail before re-running
