# Help on Gmail

Interactive email triage skill. Fetches emails labeled `ally-os-help` from Gmail, presents each to the user with analysis, and executes actions (draft reply, research, skip) based on user direction.

## Trigger

Run on-demand when user mentions checking help emails, ally-os-help, or Gmail help queue. Not scheduled — requires interactive user presence.

## Usage

```
/help-on-gmail
/help-on-gmail --unread-only
/help-on-gmail --limit 5
```

## How It Works

1. **Fetch** — `fetch_help_emails.py` searches Gmail for `label:ally-os-help`, returns JSON array
2. **Present** — Claude Code summarizes each email (who, what, key asks)
3. **Analyze** — Provides initial analysis (what kind of help, considerations, options)
4. **Ask** — "What's your direction and objective for this email?"
5. **Execute** — Based on user response:
   - **Draft reply** → creates Gmail draft in the same thread
   - **Research** → web search, then present findings
   - **Skip** → move to next email
   - **Custom** → follow user's instructions
6. **Label cleanup** — After processing, ask if user wants to remove the `ally-os-help` label

## Authentication

- Token: `local-data/gmail_token_ivan_help.json` (separate from readonly token)
- Scopes: `gmail.modify` (read, label management, draft creation)
- No send function exists in the code — sending is blocked at the code level
- First run triggers browser OAuth consent for ivan@withally.com
- Credentials: shared `Google-credentials.json` in project root

## Output

No persistent artifacts — interactive session only. Gmail drafts are created directly in the user's Gmail account.

## Requirements

- `Google-credentials.json` in project root (Google OAuth2 client)
- Python 3.11+ with `google-auth`, `google-auth-oauthlib`, `google-api-python-client`
