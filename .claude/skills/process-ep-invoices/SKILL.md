# Process EP Invoices Skill

Automates the monthly EP (Executive Partner) invoice reconciliation and payment process. Reads hours from the time tracker Google Sheet, matches them against EP invoice submissions, validates amounts, flags mismatches to Slack, and submits matched payments via the Airwallex API.

**Runs on days 1–3 of each month (post-pay cycle).**

## How it works

1. Reads the **time tracker sheet** (summary tab) — contractor code, EP name, total amount, billing period
2. Reads the **invoice submission sheet** (Google Form responses) — contractor code, EP name, email, invoice amount, period
3. Matches records by **contractor code**
4. Validates: invoice amount == time tracker total (within tolerance)
5. **Mismatches** → flagged to Slack, skipped from payment
6. **Missing invoices** (EP in time tracker but no invoice submitted) → flagged to Slack, skipped
7. **Matched** → payment submitted to Airwallex via API using the beneficiary linked to the contractor code
8. Posts a full summary to Slack when done
9. Saves receipt JSON to `local-data/invoices/`

## Trigger phrases

| What you say | What it does |
|---|---|
| "Run EP invoices" | Step 1 — parse submissions, log reimbursements to HRIS |
| "Post EP invoices" | Step 2 — reconcile, bank check, post Slack approval summary |
| "Process invoices on Airwallex" | Step 3 — submit pending payments to Airwallex for Ivan's approval |
| "Dry run EP invoices" | Preview only — no writes, no Slack, no payments |
| "Check Airwallex status" / "Status Check" | Show this month's transfer statuses — posts to Slack |

When triggered, always run from the project root: `cd /Users/dyancueto/ally-os`

## How to run

### Step 1 — Parse submissions, log reimbursements (say: "Run EP invoices")

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py
```

Reads all submitted invoices for the period, logs reimbursements to HRIS Reimbursements tab. Confirm the tab looks correct, then run Step 2.

### Step 2 — Reconcile and post for approval (say: "Post EP invoices")

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --post
```

Reconciles submissions against the time tracker, runs bank verification, posts approval summary to Slack. Review Slack, then run Step 3.

### Step 3 — Submit to Airwallex (say: "Process invoices on Airwallex")

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --confirm
```

Submits payments. Ivan approves in Airwallex. Posts confirmation to Slack.

### Dry run (say: "Dry run EP invoices")

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --dry-run
```

### Single EP (by contractor code)

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --contractor-code EP001
```

### Override billing period

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --period 2026-01
```

## Configuration

Edit `templates/ep-invoice-config.json` to set:

| Key | What it controls |
|-----|-----------------|
| `time_tracker.sheet_id` | Google Sheet ID of the daily time tracker |
| `time_tracker.tab_name` | Tab name of the summary view |
| `time_tracker.columns.*` | Exact column header names in that tab |
| `invoice_submissions.sheet_id` | Google Sheet ID of the invoice form responses |
| `invoice_submissions.tab_name` | Tab name (usually "Form Responses 1") |
| `invoice_submissions.columns.*` | Exact column header names |
| `matching.amount_tolerance` | Allowed variance in SGD before flagging mismatch (default: 0.01) |
| `slack.webhook_url_env` | Name of the env var holding the Slack webhook |
| `slack.tag` | Slack handle to tag on alerts (e.g. `@Dyan`) |
| `airwallex.environment` | `"production"` or `"demo"` |
| `airwallex.currency` | Payment currency (e.g. `"SGD"`) |
| `airwallex.beneficiary_match_field` | Field on Airwallex beneficiary to match contractor code against (`"nickname"` or `"beneficiary_id"`) |

## Requirements

- Python 3+
- Environment variables: `AIRWALLEX_CLIENT_ID`, `AIRWALLEX_API_KEY`, `GOOGLE_SHEETS_CREDENTIALS_PATH` (or uses `credentials.json`)
- Google Sheets API enabled on your Google Cloud project
- EPs already set up as beneficiaries in Airwallex with contractor code in the `nickname` field
- Dependencies: `requests`, `python-dotenv`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`

## Output

```
local-data/invoices/
└── 2026-03/
    ├── payment-receipt-2026-03.json     # All submitted payments
    └── mismatch-report-2026-03.json     # All flagged mismatches
```

## Edge Cases

- EP in time tracker but no invoice submitted → flagged to Slack, skipped
- Invoice submitted but not in time tracker → flagged to Slack, skipped
- Amount mismatch beyond tolerance → flagged to Slack, skipped
- Airwallex beneficiary not found for contractor code → flagged to Slack, skipped
- Dry run: no payments submitted, no receipts written
- Duplicate runs: will attempt to create duplicate payments — always dry-run first
