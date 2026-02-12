---
description: Check and triage ally-os-help emails from Gmail
argument-hint: [--limit N] [--unread-only]
allowed-tools: Bash(python3:*), Read, WebSearch, WebFetch, AskUserQuestion, ToolSearch, mcp__claude_ai_Linear__create_issue, mcp__claude_ai_Linear__list_users, mcp__claude_ai_Linear__list_projects, mcp__claude_ai_Linear__list_issue_labels, mcp__claude_ai_Linear__list_teams
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
- **Create a Linear ticket** — create a task in Linear with context from the email
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
service = get_gmail_service(credentials_path='Google-credentials.json', token_path='local-data/gmail_token_ivan_help.json', scopes=['https://www.googleapis.com/auth/gmail.modify'])
import html; body = html.escape('''REPLY_BODY_HERE''').replace(chr(10), '<br>')
result = create_reply_draft(service, 'MESSAGE_ID', 'THREAD_ID', 'TO_ADDRESS', 'SUBJECT', body)
print(f\"Draft created: ID {result['id']}\")
"
```
Replace MESSAGE_ID, THREAD_ID, TO_ADDRESS, SUBJECT, and REPLY_BODY_HERE with actual values from the email being processed.

**If creating a Linear ticket:**
1. Use ToolSearch to load the Linear MCP tools (`+linear create issue`)
2. Propose a ticket with:
   - **Title**: concise summary derived from the email subject/content
   - **Description**: include key context from the email — who sent it, what they need, any deadlines or action items. Quote relevant parts of the email body. Include the sender's email address for reference.
3. Ask the user: **"What's the approach for this ticket?"** — let them refine the description, add acceptance criteria, or provide additional context
4. Ask the user: **"Want to assign this to someone?"** — if yes, use `mcp__claude_ai_Linear__list_users` to show available team members and let the user pick
5. Ask the user: **"Which project should this go under?"** — if yes, use `mcp__claude_ai_Linear__list_projects` to show available projects and let the user pick. If they say none/skip, leave it unset.
6. Create the issue using `mcp__claude_ai_Linear__create_issue` with:
   - `teamId`: `f3fb95e8-5a4d-4949-b49e-4cf4c95f81d9` (With Ally)
   - The agreed title, description, assignee (if any), and project (if any)
6. Report the created ticket URL/ID to the user

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
service = get_gmail_service(credentials_path='Google-credentials.json', token_path='local-data/gmail_token_ivan_help.json', scopes=['https://www.googleapis.com/auth/gmail.modify'])
result = remove_label(service, 'MESSAGE_ID', 'ally-os-help')
print('Label removed' if result else 'Label not found')
"
```

## After All Emails

Summarize what was done:
- How many emails were processed
- Actions taken (drafts created, Linear tickets created, researched, skipped)
- Any emails still labeled ally-os-help
