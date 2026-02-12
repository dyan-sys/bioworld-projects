# Track AI Spend

Automatically tracks monthly AI subscription costs by parsing billing/receipt emails from Gmail and upserting rows into a Notion "AI Spend" database. Separates raw charge from AUD amount for currency flexibility.

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
- **Notion upsert**: Queries by `Month` title to update existing rows (no duplicates). Does NOT touch `Reimbursed (AUD)` — that's manual.
- **Local receipts**: Dedup by Gmail message ID in `local-data/ai-spend/`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `NOTION_KEY` | Yes | Notion integration token |
| `NOTION_SPEND_DB_ID` | Yes | Notion database ID for "AI Spend" database |

## Notion Database Schema

| Property | Type | Description |
|----------|------|-------------|
| `Month` | title | `2026-02` |
| `Charge` | number | Raw amount from receipt (e.g. 34.00) |
| `Currency` | select | Original currency code (AUD, USD, etc.) |
| `AUD Amount` | number | Amount in AUD (= Charge when currency is AUD) |
| `Reimbursed (AUD)` | number | Manual entry — how much reimbursed |
| `Balance (AUD)` | **formula** | `= prop("AUD Amount") - prop("Reimbursed (AUD)")` |
| `Updated At` | rich_text | ISO timestamp of last script run |
| `Notes` | rich_text | Warnings, partial data |

Use database footer **Sum** on `AUD Amount`, `Reimbursed (AUD)`, and `Balance (AUD)` to see totals at a glance.

## Scheduling

Runs on the 2nd of each month at 08:00 SGT via launchd (`com.ally.ai-spend.plist`).

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
