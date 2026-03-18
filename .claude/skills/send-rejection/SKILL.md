# Send Rejection Skill

Creates Gmail DRAFT emails for candidates who have already been interviewed and are being rejected. Routes candidates to the correct rejection email template based on a configured status field, so hiring leads can review and send manually.

**SAFETY: This workflow NEVER sends emails. It only creates drafts. A human must review and send each draft manually from Gmail.**

## Rejection routing (config-driven)

Configured in `templates/rejection-mapping.json`:

| Status field value | Template | Type |
|---|---|---|
| `Rejected (R1)` | `R1-Rejection.md` | Round 1 rejection |
| `Rejected (R2)` | `R2-Rejection.md` | Round 2 rejection |

`status_field` and `guard_field` are customizable in mapping.

## How it works

1. Loads routing config from `rejection-mapping.json`
2. Queries Notion Candidates DB for matching status values (and optional guard filter)
3. Selects the correct HTML email template per candidate status
4. Renders template with `{first_name}` and `{job_title}`
5. Creates Gmail draft (`gmail.users().drafts().create`) or dry-run
6. Saves receipt JSON to `local-data/talent/rejection_emails/`

## How to run

### Batch mode (default)

```bash
python3.11 .claude/skills/send-rejection/workflows/send_rejection.py
python3.11 .claude/skills/send-rejection/workflows/send_rejection.py --limit 20
```

### Data source

By default, this runs against the Candidates DB (status field from `rejection-mapping.json`).

To run from Interactions DB (e.g., `Rec Proceed to Next R?`), set `INTERACTIONS_DB_ID` in `.env` and use:

```bash
python3.11 .claude/skills/send-rejection/workflows/send_rejection.py --source interactions
```

### Single candidate

```bash
python3.11 .claude/skills/send-rejection/workflows/send_rejection.py --page-id <notion_page_id>
```

### Dry run

```bash
python3.11 .claude/skills/send-rejection/workflows/send_rejection.py --dry-run
```

## Requirements

- Python 3.11+
- Environment variables: `NOTION_KEY`, `NOTION_DB_ID`
- Gmail OAuth2 credentials: `credentials.json` or `GMAIL_CREDENTIALS_PATH`
- Dependencies: `requests`, `python-dotenv`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`

## Output

```
local-data/talent/rejection_emails/
├── R1-Rejection-{CandidateName}.json
└── R2-Rejection-{CandidateName}.json
```

## Edge Cases

- No email: skipped
- Unknown status: skipped
- Empty name: uses `Hi there,` fallback
- Dry run: no Gmail draft created
- Duplicate runs can create duplicate drafts
