# Track AI Spend

Automatically tracks monthly AI subscription costs by parsing billing/receipt emails from Gmail and upserting rows into a Notion "AI Spend" ledger database. Ledger-style: auto-inserted "Spend" rows (negative outflow) and manually-added "Reimbursement" rows (positive inflow). Footer Sum on AUD Amount = net balance.

## Quick Start

```bash
# Phase 1: Discover billing email format
python3.11 .claude/skills/track-ai-spend/workflows/track_ai_spend.py --discover --days 90

# Normal: process previous month
python3.11 .claude/skills/track-ai-spend/workflows/track_ai_spend.py

# Specific month
python3.11 .claude/skills/track-ai-spend/workflows/track_ai_spend.py --month 2026-01

# Current month (partial)
python3.11 .claude/skills/track-ai-spend/workflows/track_ai_spend.py --current

# Dry run (no Notion write)
python3.11 .claude/skills/track-ai-spend/workflows/track_ai_spend.py --dry-run
```

## Architecture

- **Gmail integration**: Uses `ivan@withally.com` OAuth token (separate from recruitment@). Billing receipts are forwarded from personal email.
- **Config-driven parsing**: `billing-config.json` defines per-service Gmail search queries and charge regex patterns.
- **Body-date extraction**: Since emails are forwarded, the "Paid" date is extracted from the email body (not headers) for correct month bucketing.
- **Notion upsert**: Queries by `Month` title to update existing rows (no duplicates). Creates receipt details as page body on first insert.
- **Ledger model**: Script creates `Type: Spend` rows with negative AUD Amount (outflow). `Type: Reimbursement` rows are added manually with positive AUD Amount (inflow). Footer Sum = net balance.
- **Local receipts**: Dedup by Gmail message ID in `local-data/ai-spend/`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NOTION_KEY` | Yes | Notion integration token |
| `NOTION_SPEND_DB_ID` | Yes | Notion database ID for "AI Spend" database |

## Notion Database Schema

| Property | Type | Description |
|----------|------|-------------|
| `Month` | title | `2026-01 \| Anthropic Claude` (spend) or description (reimbursements) |
| `Type` | select | `Spend` (auto) or `Reimbursement` (manual) |
| `Date` | date | Transaction date (from "Paid" date in receipt) |
| `Charge` | number | Raw amount from receipt, always positive (e.g. 34.00) |
| `Currency` | select | Original currency code (AUD, USD, etc.) |
| `AUD Amount` | number | Negative for spend (outflow), positive for reimbursements (inflow) |
| `Updated At` | rich_text | ISO timestamp of last script run |
| `Notes` | rich_text | Warnings, partial data |

**Footer Sum on `AUD Amount` = net balance** (negative = still owed).

### Page Body (auto-created on first insert)
Each spend row includes receipt details as bulleted list: receipt number, invoice number, paid date, amount, payment method, email subject, Gmail message ID.

### Adding Reimbursements
Manually add a row in Notion:
- **Month**: description (e.g. "Reimbursement from Isabelle — Jan 2026")
- **Date**: date of the transfer
- **Type**: `Reimbursement`
- **AUD Amount**: positive value (e.g. `200.00`) — inflow reduces the negative balance

## Scheduling

Runs on the 8th, 18th, and 28th of each month at 08:00 SGT via launchd (`com.ally.ai-spend.plist`). Uses `--current` flag so it always processes the current month (upserts, so repeated runs just update the same row).

## Gmail Setup

Uses `ivan@withally.com` with a separate OAuth token at `local-data/gmail_token_ivan.json`. Billing receipts are auto-forwarded from `livan627@gmail.com`.

## Billing Config

`templates/billing-config.json` — amount_pattern captures (currency_prefix, amount):

```json
{
  "anthropic": {
    "gmail_search_query": "subject:\"receipt from Anthropic\"",
    "amount_pattern": "([A-Z]{1,2})\\$([\\d,]+\\.\\d{2})"
  }
}
```
