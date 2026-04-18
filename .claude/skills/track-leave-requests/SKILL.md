# Track Leave Requests Skill

Processes new EP leave submissions from the Ally HRIS Google Sheet, posts a notification to `#people-ops-private` on Slack, adds the leave to the Team Calendar, and marks each submission as Accepted in the sheet.

**Run on-demand whenever you want to process new submissions.**

## How it works

1. Reads the **Leave_Tracker** tab in Ally HRIS Google Sheet
2. Finds rows where **Status is blank** (new, unprocessed submissions)
3. For each new submission:
   - Posts notification to `#people-ops-private` Slack with full details
   - Creates an event in the Team Calendar
   - Updates Status → `Accepted` in the sheet
4. Posts a summary to Slack when done

## Trigger phrases

| What you say | What it does |
|---|---|
| "Process leave requests" | Run — pick up all new submissions and record them |
| "Dry run leave requests" | Preview only — no sheet updates, no calendar events, no Slack posts |
| "Cancel leave for [email]" | Set the most recent Accepted leave for that EP to Cancelled |

When triggered, always run from the project root: `cd /Users/dyancueto/ally-os`

## How to run

### Process new submissions
```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/track-leave-requests/workflows/track_leave_requests.py
```

### Dry run (preview only)
```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/track-leave-requests/workflows/track_leave_requests.py --dry-run
```

## Leave types

| Type | Invoice impact |
|---|---|
| 🕓 Planned Leave | Deducted from invoice |
| ⚡ Emergency Leave | Deducted from invoice |
| 🌴 Paid Holiday Leave | Paid — not deducted |

## Configuration

Edit `templates/leave-config.json` to set:

| Key | What it controls |
|---|---|
| `hris_sheet.sheet_id` | Google Sheet ID for Ally HRIS |
| `hris_sheet.tab_name` | Tab name (default: `Leave_Tracker`) |
| `hris_sheet.columns.*` | Exact column header names |
| `hris_sheet.status_accepted_value` | Value written to Status when processed (default: `Accepted`) |
| `leave_types.deducted` | Leave types that deduct from invoice |
| `leave_types.paid` | Leave types that are paid (not deducted) |
| `calendar.calendar_id` | Google Calendar ID for the Team Calendar |
| `slack.webhook_url_env` | Env var name holding the Slack webhook |
| `slack.tag` | Slack handle to tag on notifications |

## Requirements

- Python 3+
- Environment variables: `SLACK_WEBHOOK_URL_PEOPLE_OPS`, `GOOGLE_SHEETS_CREDENTIALS_PATH` (or uses `credentials.json`)
- Google Sheets API and Google Calendar API enabled on your Google Cloud project
- Dependencies: `requests`, `python-dotenv`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`

### First-time setup
This skill needs broader Google permissions than the invoice skill. On first run it will open a browser to re-authenticate. You'll need to approve:
- Google Sheets (read + write)
- Google Calendar (create events)

A new token file `google_token_hris.json` will be saved to the project root.

## Sheet columns expected

| Column | Description |
|---|---|
| Timestamp | Auto-filled by Google Form |
| Email Address | EP's email |
| Type of Leave | One of the three leave types |
| Leave Dates and Hours Off | Free text — e.g. "March 20, 8 hours" |
| Notes (optional) | Any additional context |
| Have you informed CPL then your client about this leave? | Checkbox response |
| Status | Blank = new. Set to `Accepted` after processing. |

## Edge cases

- Status already set → skipped (not reprocessed)
- Missing email → still processed, shown as "Unknown" in Slack
- Calendar event uses submission date as the event date; actual leave dates are in the event description
- Duplicate runs are safe — already-Accepted rows are skipped
