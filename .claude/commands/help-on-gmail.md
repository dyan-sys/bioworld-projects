---
description: Check and triage ally-os-help emails from Gmail
argument-hint: [--limit N] [--unread-only]
allowed-tools: Bash(python3:*), Read, WebSearch, WebFetch, AskUserQuestion
---

Fetch emails labeled `ally-os-help` from ivan@withally.com, analyze each one interactively, and take action based on user direction.

Parse the following arguments: $ARGUMENTS

## Argument Parsing

1. **`--limit N`** — Max emails to fetch (default: 10)
2. **`--unread-only`** — Only fetch unread emails
3. **Empty** — Fetch up to 10 emails (read + unread)

## Step 1: Fetch Emails

```bash
python3.11 .claude/skills/help-on-gmail/workflows/fetch_help_emails.py [--limit N] [--unread-only]
```

Parse the JSON output. If the array is empty, tell the user: **"Inbox zero for ally-os-help — no emails need attention."** and stop.

## Step 2: Process Each Email

For each email in the JSON array, do the following:

### 2a. Present & Analyze

Display a summary:
- **From:** sender name and email
- **Date:** when it was sent
- **Subject:** email subject line
- A concise summary of the email content (who is writing, what they need, key asks or issues)
- Initial analysis: what kind of help is needed, key considerations, suggested approaches

If the email references something that could benefit from web research (a product, company, technical topic, etc.), mention that you can look it up.

### 2b. Ask for Direction

Ask the user: **"What's your direction and objective for this email?"**

Offer these options as suggestions:
- **Draft a reply** — you'll compose a reply and create it as a Gmail draft
- **Research first** — do web research before deciding
- **Skip** — move to the next email
- Or any custom instruction

### 2c. Execute

Based on the user's response:

**If drafting a reply:**
1. Compose the reply based on the user's direction and objective
2. Present the draft to the user for review
3. Once approved, create the draft in Gmail:
```bash
python3.11 -c "
import sys; sys.path.insert(0, '.claude/skills/invite-candidates/libraries'); sys.path.insert(0, '.claude/skills/help-on-gmail/libraries')
from gmail_auth import get_gmail_service
from gmail_helpers import create_reply_draft
service = get_gmail_service(token_path='local-data/gmail_token_ivan_help.json', scopes=['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.compose'])
import html; body = html.escape('''REPLY_BODY_HERE''').replace(chr(10), '<br>')
result = create_reply_draft(service, 'MESSAGE_ID', 'THREAD_ID', 'TO_ADDRESS', 'SUBJECT', body)
print(f\"Draft created: ID {result['id']}\")
"
```
Replace MESSAGE_ID, THREAD_ID, TO_ADDRESS, SUBJECT, and REPLY_BODY_HERE with actual values from the email being processed.

**If researching:**
- Use WebSearch to find relevant information
- Present findings to the user
- Then ask for direction again (draft reply, skip, or custom)

**If skipping:**
- Move to the next email

### 2d. Label Cleanup

After processing each email (except skip), ask: **"Remove the ally-os-help label from this email?"**

If yes:
```bash
python3.11 -c "
import sys; sys.path.insert(0, '.claude/skills/invite-candidates/libraries'); sys.path.insert(0, '.claude/skills/help-on-gmail/libraries')
from gmail_auth import get_gmail_service
from gmail_helpers import remove_label
service = get_gmail_service(token_path='local-data/gmail_token_ivan_help.json', scopes=['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.compose'])
result = remove_label(service, 'MESSAGE_ID', 'ally-os-help')
print('Label removed' if result else 'Label not found')
"
```

## After All Emails

Summarize what was done:
- How many emails were processed
- Actions taken (drafts created, researched, skipped)
- Any emails still labeled ally-os-help
