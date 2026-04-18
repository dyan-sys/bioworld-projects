# Review Airwallex Spend Skill

Pulls **all** Airwallex transactions (card purchases, wallet financial transactions, and outgoing transfers) over a configurable window, groups them by merchant/beneficiary, flags likely recurring subscriptions, and writes a CSV plus a terminal summary so you can spot what to cancel or renegotiate.

**On-demand only — no scheduling.**

## How it works

1. Authenticates with Airwallex using `AIRWALLEX_CLIENT_ID` / `AIRWALLEX_API_KEY`
2. Pulls three transaction sources in parallel:
   - **Card transactions** — `/api/v1/issuing/transactions` (SaaS, software, vendor cards)
   - **Wallet financial transactions** — `/api/v1/financial_transactions` (fees, top-ups, FX)
   - **Outgoing transfers** — `/api/v1/transfers` (beneficiary payouts incl. EPs)
3. Normalises each to a common shape (date, source, vendor, currency, amount AUD-equivalent if FX rate present, status)
4. Groups by vendor, computes:
   - Total spend
   - Number of charges
   - Avg charge
   - First / last seen
   - **Recurrence flag** — same vendor charged ≥3 times across ≥3 distinct months → `RECURRING`
5. **Pattern-extracts vendor names from messy descriptions** — e.g. all 22 "COMPOUND WO XXXX PAYOUT FOR CREDIT CARD..." entries collapse to one "Compound credit card payout" vendor; "Pay 1166 USD to Angelica De Jesus (REF...)" extracts to just "Angelica De Jesus" so multiple months of payouts to the same person group together.
6. **Dedupes wallet PAYOUT entries against the transfers endpoint** (they overlap 1:1) — keeps the wallet entry which has richer context.
7. **Classifies each vendor** as `ACTIVE` (recurring + charged within `active_window_days` — default 45), `STOPPED` (was recurring, now silent), or `ONE_OFF` (below the recurrence threshold).
8. Writes:
   - `report.html` — **the main artifact** — full interactive dashboard, opens in browser. Sections: source totals, type breakdown, active subscriptions, stopped subscriptions, full vendor table with click-to-expand transaction lists and decision input (saved to localStorage).
   - `transactions.csv` — every transaction, raw
   - `by-vendor.csv` — grouped sheet (status + decision columns)
   - `summary.txt` — terminal summary captured to file

## Trigger phrases

| What you say | What it does |
|---|---|
| "Review Airwallex spend" | Default — last 12 months, all sources, writes CSVs + prints summary |
| "Airwallex spend last 6 months" | Override window |
| "Airwallex spend YTD" | Year to date |

## How to run

```bash
cd /Users/dyancueto/ally-os && python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py
```

The HTML report opens in your default browser automatically.

### Options

```bash
# Custom window (months back from today)
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --months 6

# Year to date
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --ytd

# Specific date range
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --from 2025-04-01 --to 2026-04-15

# Also export to Google Sheets (creates a new spreadsheet, opens in browser)
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --sheet

# Update an existing Google Sheet (avoids creating a new one each run)
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --sheet --sheet-id 1ABC...XYZ

# Don't auto-open the HTML in browser
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --no-open

# Only one source
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --source wallet
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --source transfers

# Filter to only recurring vendors in the terminal summary
python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --recurring-only
```

### Trigger phrases (with Google Sheets)

| What you say | What it does |
|---|---|
| "Review Airwallex spend" | HTML report only |
| "Review Airwallex spend to a Google Sheet" | HTML + new Google Sheet |
| "Update the Airwallex spend sheet" | HTML + update existing sheet (use `--sheet-id` from saved URL) |

## Reviewing the output

The HTML report (`report.html`) is the main artifact. It auto-opens in your browser. Structure:

1. **Activity by source** — totals across cards / wallet / transfers
2. **Activity by transaction type** — breaks wallet activity into PAYOUT, ISSUING_CAPTURE (settled card spend), DEPOSIT, FEE, CONVERSION_BUY/SELL
3. **Categories overview** — totals per category, click row to jump to its detail section
4. **One section per category** with its own vendor table and click-to-expand transactions:
   - **EP Payment** — Recurring monthly payouts to Executive Partners (the bulk of outgoing money). Reference suffix `-EP` or `-CPL`.
   - **Card spend (subscriptions)** — Settled card transactions where SaaS subscriptions live. Merchant detail not exposed by API unless Issuing is enabled as a product.
   - **Vendor invoice** — One-off or recurring vendor invoices (Agentiwise, Jolly Commerce, etc.). Reference contains `INV-…`.
   - **Reimbursement** — Reimbursements paid out (e.g. Ivan's expense reports).
   - **Compound CC settlement (incoming)** — Money flowing INTO the wallet from the Compound credit card product. Not an expense.
   - **Other deposit** — Top-ups and other incoming wallet credits.
   - **FX conversion** — Currency conversions (BUY/SELL pairs).
   - **Fee** — Airwallex platform fees and third-party fees.
   - **Refund / adjustment** — Refunds for failed/cancelled payouts.
   - **Other** — Uncategorised. Add a rule to `categorise()` in the workflow if you need it cleaner.

Each vendor row has a status badge (`ACTIVE` / `STOPPED` / `ONE_OFF`), an annual run-rate column, and a `decision` text field. The decision field saves to browser localStorage and survives re-runs of the report.

Or use the CSVs — `by-vendor.csv` is the grouped review sheet. Columns:

| Column | Meaning |
|---|---|
| `vendor` | Merchant name (cards) / beneficiary name (transfers) / description (wallet) |
| `source` | `card` / `wallet` / `transfer` (or `mixed` if vendor appears in multiple) |
| `total_amount` | Sum across the window, in original currency (mixed currencies marked) |
| `currency` | Predominant currency for this vendor |
| `charge_count` | Number of charges |
| `avg_charge` | Average charge size |
| `months_active` | Distinct months this vendor was charged in |
| `recurrence` | `RECURRING` if ≥3 charges across ≥3 months, else `ONE_OFF` |
| `first_seen` / `last_seen` | Bounds of activity |
| `decision` | **Empty for you to fill** — `keep` / `cancel` / `renegotiate` |
| `notes` | Empty for you |

Recurring vendors are the easiest cancellation targets. The `annual_run_rate` column extrapolates monthly spend × 12.

## Configuration

Edit `templates/spend-config.json`:

| Key | What it controls |
|-----|-----------------|
| `airwallex.environment` | `"production"` or `"demo"` |
| `airwallex.page_size` | API page size (default 100, max 200) |
| `recurrence.min_charges` | Min charges to flag RECURRING (default 3) |
| `recurrence.min_months` | Min distinct months (default 3) |
| `output.top_vendors_in_summary` | How many to print (default 20) |
| `output.skip_zero_amount` | Skip transactions with amount 0 (default true) |
| `vendor_normalisation` | Map raw merchant strings → cleaner names (e.g. `"AWS*amazon"` → `"AWS"`) |

## Requirements

- Python 3.11
- Env vars (in priority order — first one set wins):
  - `AIRWALLEX_ADMIN_CLIENT_ID` / `AIRWALLEX_ADMIN_API_KEY` — **preferred**, dedicated Admin-role key for card transaction reads
  - `AIRWALLEX_CLIENT_ID` / `AIRWALLEX_API_KEY` — fallback (the existing `process-ep-invoices` key); without Admin role, card transactions return `401 Admin permissions required` and the skill silently degrades to wallet+transfers only
- Dependency: `requests`, `python-dotenv`

### Card merchant memory

The script auto-discovers merchants for ISSUING_CAPTURE entries via `/api/v1/balances/history` (last ~5 days only) and back-propagates to all historical charges of the same amount. Discovered mappings persist in `local-data/airwallex-spend/merchant-memory.json` so each run adds more — over 1-2 months of running, all your subscriptions will be labelled.

You can also **manually edit that file** to label amounts the API hasn't surfaced yet. Format:

```json
{
  "USD|12.0":  "Calendly",
  "USD|26.88": "Notion",
  "USD|99.0":  "LinkedIn Premium"
}
```

Key format is `<currency>|<amount>` (use the exact amount with no leading zeros). Manually-added entries are merged in alongside auto-discovered ones (auto-discovered always wins on conflict, so your labels won't override fresh data).

### Why a separate admin key

The existing key used by `process-ep-invoices` only needs scopes for transfers + beneficiaries. Card transaction reads require **Admin role** in Airwallex, which is a meaningful privilege escalation (Admin keys can also modify beneficiaries, submit transfers without approval, etc.). To minimise blast radius:

1. Create a dedicated key in Airwallex (Settings → API → API keys → Create) named e.g. `ally-os-spend-review`
2. Set role to **Admin**
3. Grant only **read** scopes — un-tick anything write-related you don't need
4. Add an IP allowlist if your environment has a stable IP
5. Add to `.env` as `AIRWALLEX_ADMIN_CLIENT_ID` and `AIRWALLEX_ADMIN_API_KEY`

## Output

```
local-data/airwallex-spend/
└── 2025-04_2026-04/
    ├── transactions.csv         # Every transaction, raw
    ├── by-vendor.csv            # Grouped review sheet
    └── summary.txt              # Terminal summary captured to file
```

## Edge Cases

- Mixed currencies for one vendor → marked `MIXED` in currency column, totals shown per currency in summary
- Card transactions in pending state → included with `status=PENDING`
- Refunds (negative amounts) → included; net total reflects refunds
- Transfer to EPs already covered by `process-ep-invoices` → still shown here for completeness; filter with `--source cards,wallet` if you want to exclude them
- API pagination: walks all pages automatically
- If an endpoint returns 404 (account doesn't have issuing/cards enabled) → skipped silently with a note in the summary
