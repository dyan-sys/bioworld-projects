"""
Review Airwallex Spend

Pulls all transactions from Airwallex (cards, wallet, transfers) over a window,
groups by vendor, flags recurring subscriptions, writes CSVs and prints summary.

Usage:
    python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py
    python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --months 6
    python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --ytd
    python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --from 2025-04-01 --to 2026-04-15
    python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --source cards
    python3 .claude/skills/review-airwallex-spend/workflows/review_spend.py --recurring-only
"""

import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SKILL_ROOT.parents[2]

load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = SKILL_ROOT / "templates" / "spend-config.json"
OUTPUT_ROOT = PROJECT_ROOT / "local-data" / "airwallex-spend"
# Persistent merchant lookup — accumulates across runs since balances/history only shows ~5 days
MERCHANT_MEMORY_PATH = OUTPUT_ROOT / "merchant-memory.json"
# Optional: card transaction CSV exported from Airwallex dashboard (gives full merchant detail)
CARD_TXN_CSV_PATH = OUTPUT_ROOT / "card-transactions-import.json"

AIRWALLEX_URLS = {
    "production": "https://api.airwallex.com",
    "demo": "https://api-demo.airwallex.com",
}


# ── Config / auth ──────────────────────────────────────────────────────────
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Config not found: {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


def airwallex_login(base_url: str, client_id: str, api_key: str) -> str:
    resp = requests.post(
        f"{base_url}/api/v1/authentication/login",
        headers={"x-client-id": client_id, "x-api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        print("[ERROR] Airwallex login succeeded but returned no token.")
        sys.exit(1)
    return token


# ── Window resolution ──────────────────────────────────────────────────────
def resolve_window(args) -> tuple[datetime, datetime, str]:
    """Returns (from_dt, to_dt, label) — UTC datetimes."""
    today = datetime.now(timezone.utc)
    end = today.replace(hour=23, minute=59, second=59, microsecond=0)

    if args.ytd:
        start = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif args.from_date and args.to_date:
        start = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(args.to_date).replace(
            hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc
        )
    else:
        months = args.months or 12
        start = (today - timedelta(days=int(months * 30.44))).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    label = f"{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}"
    return start, end, label


# ── Pagination helper ──────────────────────────────────────────────────────
PERMISSION_ISSUES: list[str] = []  # Collected so summary can flag them prominently


def paginate(base_url: str, token: str, path: str, params: dict, page_size: int) -> list[dict]:
    """Generic pagination — Airwallex uses page_num/page_size on most list endpoints.
    Returns aggregated items list. Stops on 404 with empty list."""
    items = []
    page = 0
    while True:
        q = {**params, "page_num": page, "page_size": page_size}
        try:
            resp = requests.get(
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=q,
                timeout=60,
            )
        except requests.RequestException as e:
            print(f"  [WARN] {path} request failed on page {page}: {e}")
            break

        if resp.status_code == 404:
            print(f"  [INFO] {path} returned 404 — endpoint not enabled on this account, skipping.")
            PERMISSION_ISSUES.append(f"{path} → 404 (endpoint not enabled)")
            return []
        if resp.status_code in (401, 403):
            msg = resp.text[:200]
            print(f"  [WARN] {path} returned {resp.status_code}: {msg}")
            PERMISSION_ISSUES.append(f"{path} → {resp.status_code} {msg}")
            return []
        if not resp.ok:
            print(f"  [WARN] {path} returned {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        page_items = data.get("items", [])
        items.extend(page_items)
        if len(page_items) < page_size:
            break
        page += 1
        if page > 200:
            print(f"  [WARN] {path} hit safety limit (200 pages), stopping.")
            break
    return items


# ── Source fetchers ────────────────────────────────────────────────────────
def fetch_card_transactions(base_url: str, token: str, start: datetime, end: datetime, page_size: int) -> list[dict]:
    """Card transactions — tries Borderless cards endpoint first (the product Ally uses),
    falls back to Issuing endpoint (different product, usually 403).
    Both paths require Admin-role API key."""
    print("  Pulling card transactions...")
    params = {
        "from_created_at": start.strftime("%Y-%m-%dT%H:%M:%S+0000"),
        "to_created_at": end.strftime("%Y-%m-%dT%H:%M:%S+0000"),
    }
    # Try Borderless cards endpoint first (Airwallex's own multi-currency cards)
    items = paginate(base_url, token, "/api/v1/cards/transactions", params, page_size)
    if items:
        print(f"    {len(items)} card transaction(s) (cards/transactions)")
        return items
    # Fallback: Issuing API (for fintechs issuing cards to their customers — usually not what we want)
    items = paginate(base_url, token, "/api/v1/issuing/transactions", params, page_size)
    if items:
        print(f"    {len(items)} card transaction(s) (issuing/transactions)")
    else:
        print(f"    0 card transaction(s)")
    return items


def fetch_financial_transactions(base_url: str, token: str, start: datetime, end: datetime, page_size: int) -> list[dict]:
    """Wallet financial transactions."""
    print("  Pulling wallet financial transactions...")
    params = {
        "from_created_at": start.strftime("%Y-%m-%dT%H:%M:%S+0000"),
        "to_created_at": end.strftime("%Y-%m-%dT%H:%M:%S+0000"),
    }
    items = paginate(base_url, token, "/api/v1/financial_transactions", params, page_size)
    print(f"    {len(items)} financial transaction(s)")
    return items


def fetch_balance_history_merchants(base_url: str, token: str) -> dict:
    """Pulls /api/v1/balances/history across all wallet currencies.
    This endpoint returns merchant names in the description field for ISSUING_CAPTURE
    entries, but is capped to ~5 days of recent activity.
    Returns: dict mapping (currency, abs_amount) → merchant_name (most recent wins),
    so we can back-propagate to all historical charges of the same amount."""
    print("  Pulling balance history (for merchant lookup)...")
    # Get list of currencies with non-zero balance — those are the only ones with history
    try:
        r = requests.get(f"{base_url}/api/v1/balances/current",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        r.raise_for_status()
        balances = r.json()
        currencies = [b["currency"] for b in balances if (b.get("available_amount") or 0) != 0 or (b.get("total_amount") or 0) != 0]
    except Exception as e:
        print(f"    [WARN] balances/current failed: {e}")
        return {}

    merchant_map: dict = {}
    sample_count = 0
    for cur in currencies:
        try:
            r = requests.get(f"{base_url}/api/v1/balances/history",
                             headers={"Authorization": f"Bearer {token}"},
                             params={"currency": cur, "page_size": 100}, timeout=30)
            if not r.ok:
                continue
            for item in r.json().get("items", []):
                if item.get("transaction_type") != "ISSUING_CAPTURE":
                    continue
                desc = (item.get("description") or "").strip()
                if not desc:
                    continue
                # Clean merchant name — strip city/country tail, e.g. "GITHUB, INC., GITHUB.COM, USA" → "GITHUB, INC."
                merchant = desc.split(",")[0].strip().title()
                key = (cur, round(abs(item.get("amount", 0)), 2))
                # Most recent wins — but since we walk one query, just don't overwrite
                if key not in merchant_map:
                    merchant_map[key] = merchant
                    sample_count += 1
        except Exception as e:
            print(f"    [WARN] balances/history for {cur} failed: {e}")
    print(f"    Discovered {sample_count} merchant→amount mapping(s) from recent activity")
    return merchant_map


def load_merchant_memory() -> dict:
    """Load persisted merchant mappings from prior runs.
    Stored as JSON with string keys "currency|amount" → merchant_name.
    IMPORTANT: amount must be parsed as float to match the lookup key format
    used in normalise_financial_txn (which is `(currency_str, float_amount)`)."""
    if not MERCHANT_MEMORY_PATH.exists():
        return {}
    try:
        raw = json.loads(MERCHANT_MEMORY_PATH.read_text())
        out = {}
        for k, v in raw.items():
            if "|" not in k:
                continue
            cur, amt_str = k.split("|", 1)
            try:
                out[(cur, round(float(amt_str), 2))] = v
            except ValueError:
                continue
        return out
    except Exception as e:
        print(f"    [WARN] Could not load merchant memory: {e}")
        return {}


def save_merchant_memory(combined: dict) -> None:
    MERCHANT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Normalise amount as float string so reload matches reliably
    serialised = {f"{cur}|{float(amt)}": name for (cur, amt), name in combined.items()}
    MERCHANT_MEMORY_PATH.write_text(json.dumps(serialised, indent=2, sort_keys=True))


def fetch_transfers(base_url: str, token: str, start: datetime, end: datetime, page_size: int) -> list[dict]:
    """Outgoing transfers / payouts."""
    print("  Pulling transfers...")
    params = {
        "request_id_from": "",  # ignored
        "from_created_at": start.strftime("%Y-%m-%dT%H:%M:%S+0000"),
        "to_created_at": end.strftime("%Y-%m-%dT%H:%M:%S+0000"),
    }
    # /api/v1/transfers doesn't reliably support from/to filters historically — fetch all and filter client-side
    items = paginate(base_url, token, "/api/v1/transfers", {}, page_size)
    # client-side filter
    filtered = []
    for t in items:
        created = t.get("created_at", "")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            continue
        if start <= dt <= end:
            filtered.append(t)
    print(f"    {len(filtered)} transfer(s) in window (of {len(items)} total)")
    return filtered


# ── Normalisation ──────────────────────────────────────────────────────────
def parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalise_card_txn(t: dict, normalisation: dict) -> dict | None:
    """Normalise a card transaction from either the Borderless or Issuing endpoint.
    Both shapes carry merchant info — that's the whole point of using these endpoints
    over financial_transactions which strips it."""
    merchant = (t.get("merchant") or {})
    # Borderless endpoint: merchant.name; Issuing endpoint: merchant.name. Both work.
    raw_vendor = (
        merchant.get("name")
        or merchant.get("merchant_name")
        or t.get("merchant_name")
        or t.get("description")
        or "Unknown card merchant"
    )
    vendor = normalise_vendor(raw_vendor, normalisation)

    # Amount can be flat or nested
    amount_obj = t.get("billing_amount") or t.get("transaction_amount")
    if isinstance(amount_obj, dict):
        amount = float(amount_obj.get("value") or 0)
        currency = amount_obj.get("currency") or ""
    else:
        amount = float(amount_obj or t.get("amount") or 0)
        currency = t.get("billing_currency") or t.get("transaction_currency") or t.get("currency") or ""

    # Card spend should be negative (outflow). Some endpoints return positive values for purchases.
    if amount > 0 and t.get("transaction_type") in (None, "PURCHASE", "CAPTURE", "ISSUING_CAPTURE"):
        amount = -abs(amount)

    notes = (
        merchant.get("category_name")
        or merchant.get("category")
        or merchant.get("category_code")
        or t.get("transaction_type")
        or ""
    )
    return {
        "source": "card",
        "date": (t.get("transaction_date") or t.get("posted_date") or t.get("created_at") or "")[:10],
        "vendor": vendor,
        "raw_vendor": raw_vendor,
        "amount": amount,
        "currency": currency,
        "status": t.get("status") or t.get("transaction_status") or "",
        "id": t.get("id") or t.get("transaction_id") or "",
        "notes": notes,
        "category": "Card transactions",
    }


def normalise_financial_txn(t: dict, normalisation: dict) -> dict | None:
    """Normalise a wallet/financial transaction.

    Skips ISSUING_AUTHORISATION_HOLD and ISSUING_AUTHORISATION_RELEASE — these
    are pre-authorisation pairs that net to zero and inflate the count.
    Real card spend is captured by ISSUING_CAPTURE (status=SETTLED).
    Also skips CANCELLED status entries.
    """
    txn_type = t.get("transaction_type") or ""
    status = t.get("status") or ""

    # Filter out auth holds/releases — these come in pairs and never represent real spend
    if txn_type in ("ISSUING_AUTHORISATION_HOLD", "ISSUING_AUTHORISATION_RELEASE"):
        return None
    if status == "CANCELLED":
        return None

    amount = float(t.get("amount") or 0)
    currency = t.get("currency") or ""

    # Special handling for ISSUING_CAPTURE (settled card spend):
    # financial_transactions strips merchant info, so we look up merchant name from
    # balances/history (passed in via merchant_map). Same-amount recurring charges almost
    # always come from the same merchant, so a recent merchant label backfills all historical
    # entries of that amount. Falls back to amount-clustering label when no match.
    if txn_type == "ISSUING_CAPTURE":
        amt_label = f"{currency} {abs(amount):.2f}"
        # Lookup priority:
        # 1. Per-transaction CSV match by (currency, amount, ±5-day date window)
        #    — disambiguates same-amount merchants (e.g., 5 SaaS at $20/mo)
        # 2. Amount-only memory (good for unique amounts)
        # 3. Fall back to amount-bucket label "Card · USD X.XX"
        date_str = (t.get("transaction_date") or t.get("created_at") or "")[:10]
        per_txn_index = normalisation.get("__txn_index__", {}) if isinstance(normalisation, dict) else {}
        # Index is (currency, amount) → list of (date, merchant) — search for nearest date
        candidates = per_txn_index.get((currency, round(abs(amount), 2)), [])
        precise = None
        if candidates and date_str:
            try:
                api_dt = datetime.strptime(date_str, "%Y-%m-%d")
                best_diff = 999
                for c_date, c_merchant in candidates:
                    try:
                        c_dt = datetime.strptime(c_date, "%Y-%m-%d")
                        diff = abs((api_dt - c_dt).days)
                        if diff < best_diff and diff <= 5:
                            best_diff = diff
                            precise = c_merchant
                    except ValueError:
                        continue
            except ValueError:
                pass
        if precise:
            raw_vendor = precise
            vendor = precise
        else:
            merchant_map = normalisation.get("__merchant_map__", {}) if isinstance(normalisation, dict) else {}
            looked_up = merchant_map.get((currency, round(abs(amount), 2)))
            if looked_up:
                raw_vendor = looked_up
                vendor = looked_up
            else:
                raw_vendor = f"Card · {amt_label}"
                vendor = raw_vendor
    else:
        # Vendor labelling: prefer description, then transaction_type (more specific than source_type)
        raw_vendor = t.get("description") or txn_type or t.get("source_type") or "Wallet transaction"
        vendor = normalise_vendor(raw_vendor, normalisation)
    notes = f"{t.get('source_type') or ''} / {txn_type}".strip(" /")
    return {
        "source": "wallet",
        "date": (t.get("transaction_date") or t.get("created_at") or "")[:10],
        "vendor": vendor,
        "raw_vendor": raw_vendor,
        "amount": amount,
        "currency": currency,
        "status": status,
        "id": t.get("id") or "",
        "notes": notes,
        "category": categorise(raw_vendor, notes),
    }


def normalise_transfer(t: dict, normalisation: dict) -> dict | None:
    bene = (t.get("beneficiary") or {})
    bank = (bene.get("bank_details") or {})
    raw_vendor = bank.get("account_name") or bene.get("nickname") or t.get("reference") or "Transfer"
    vendor = normalise_vendor(raw_vendor, normalisation)
    amount = float(t.get("transfer_amount") or t.get("source_amount") or 0)
    notes = t.get("reference") or ""
    return {
        "source": "transfer",
        "date": (t.get("created_at") or "")[:10],
        "vendor": vendor,
        "raw_vendor": raw_vendor,
        "amount": amount,
        "currency": t.get("transfer_currency") or t.get("source_currency") or "",
        "status": t.get("status") or "",
        "id": t.get("id") or t.get("short_reference_id") or "",
        "notes": notes,
        "category": categorise(raw_vendor, notes),
    }


# Pattern rules for collapsing transaction-specific tokens into vendor names.
# Each tuple is (regex, replacement-template using \g<groupname> or literal string).
# Order matters — first match wins.
PATTERN_RULES: list[tuple[re.Pattern, str]] = [
    # "Pay 1234.56 USD to <name> (REF...)" → "<name>"
    (re.compile(r"^Pay\s+[\d.,]+\s+[A-Z]{3}\s+to\s+(?P<name>.+?)\s*\(.*\)\s*$"), r"\g<name>"),
    # "Pay 1234.56 USD to <name>" (no ref)
    (re.compile(r"^Pay\s+[\d.,]+\s+[A-Z]{3}\s+to\s+(?P<name>.+?)\s*$"), r"\g<name>"),
    # COMPOUND credit card payouts (each has unique ID, all collapse to one)
    (re.compile(r"^COMPOUND\s+WO\s+\w+\s+PAYOUT\s+FOR\s+CREDIT\s+CARD.*$", re.I),
     "Compound credit card payout"),
    # Compound (lowercase) variant
    (re.compile(r"^Compound\s+Wo\s+\w+\s*$"), "Compound credit card payout"),
    # Fees
    (re.compile(r"^Fee\s+for\s+payout\s+\S+", re.I), "Airwallex payout fee"),
    (re.compile(r"^Third-party\s+fee.*$", re.I), "Third-party payout fee"),
    # Refunds
    (re.compile(r"^Refund\s+for\s+failed\s+payment\s+\S+", re.I), "Refund (failed payment)"),
    (re.compile(r"^Refund\s+for.*$", re.I), "Refund"),
    # Generic invoice numbers like "INV-310FTV10-0001"
    (re.compile(r"^INV-[A-Z0-9-]+$"), "Vendor invoice (uncategorised)"),
]


# ── Categorisation ─────────────────────────────────────────────────────────
# Stable ordered list — controls the order categories appear in the HTML report.
CATEGORY_ORDER = [
    "EP Payment",
    "Card transactions",
    "Vendor invoice",
    "Reimbursement",
    "Compound CC settlement (incoming)",
    "Other deposit",
    "FX conversion",
    "Fee",
    "Refund / adjustment",
    "Other",
]


def categorise(raw_vendor: str, notes: str) -> str:
    rv = (raw_vendor or "").strip()
    nt = (notes or "").strip()
    combined = f"{rv} || {nt}"
    notes_upper = nt.upper()

    if "ISSUING_CAPTURE" in notes_upper:
        return "Card transactions"
    if "CONVERSION" in notes_upper:
        return "FX conversion"
    if "FEE" in notes_upper or rv.lower().startswith("fee for") or "third-party fee" in rv.lower():
        return "Fee"
    if rv.lower().startswith("refund"):
        return "Refund / adjustment"
    if "Reimbursement" in combined:
        return "Reimbursement"
    if rv.upper().startswith("COMPOUND") or "COMPOUND" in rv.upper() and "DEPOSIT" in notes_upper:
        return "Compound CC settlement (incoming)"
    if "DEPOSIT" in notes_upper:
        return "Other deposit"
    # EP Payment markers in the reference: -EP, -CPL, -EP-P2 etc.
    if re.search(r"-(EP|CPL)(-|\b|\))", combined, re.I):
        return "EP Payment"
    # Vendor invoice
    if re.search(r"\bINV-[A-Z0-9-]+", combined, re.I):
        return "Vendor invoice"
    return "Other"


def normalise_vendor(raw: str, mapping: dict) -> str:
    s = (raw or "").strip()
    if not s:
        return "Unknown"
    # User-defined exact map first (highest precedence)
    if s in mapping:
        return mapping[s]
    # User-defined case-insensitive contains map
    s_lower = s.lower()
    for needle, replacement in mapping.items():
        if needle.lower() in s_lower:
            return replacement
    # Built-in pattern rules
    for pattern, replacement in PATTERN_RULES:
        m = pattern.match(s)
        if m:
            try:
                return m.expand(replacement).strip()
            except (re.error, IndexError):
                return replacement
    return s


# ── Dedup ──────────────────────────────────────────────────────────────────
def dedupe_wallet_vs_transfers(transactions: list[dict]) -> list[dict]:
    """Wallet PAYOUT entries duplicate the transfers endpoint 1:1.
    When both sources are present, keep the wallet entry (richer context)
    and drop the matching transfer.
    Also: when card transactions are pulled (with merchant info), the wallet's
    ISSUING_CAPTURE entries become duplicates — drop the wallet ones since
    the card source has merchant detail.
    Match key: (date, currency, abs(amount))."""
    wallet_payout_keys = set()
    card_keys = set()
    for t in transactions:
        if t["source"] == "wallet" and "PAYOUT" in (t.get("notes") or "").upper():
            key = (t["date"], t["vendor"].lower(), t["currency"], round(abs(t["amount"]), 2))
            wallet_payout_keys.add(key)
        if t["source"] == "card":
            key = (t["date"], t["currency"], round(abs(t["amount"]), 2))
            card_keys.add(key)

    out = []
    dropped_t = 0
    dropped_w = 0
    for t in transactions:
        if t["source"] == "transfer":
            key = (t["date"], t["vendor"].lower(), t["currency"], round(abs(t["amount"]), 2))
            if key in wallet_payout_keys:
                dropped_t += 1
                continue
        if t["source"] == "wallet" and "ISSUING_CAPTURE" in (t.get("notes") or "").upper():
            key = (t["date"], t["currency"], round(abs(t["amount"]), 2))
            if key in card_keys:
                dropped_w += 1
                continue
        out.append(t)
    if dropped_t:
        print(f"  Deduped {dropped_t} transfer(s) that matched wallet PAYOUT entries.")
    if dropped_w:
        print(f"  Deduped {dropped_w} wallet ISSUING_CAPTURE(s) that matched card transactions.")
    return out


# ── Grouping ───────────────────────────────────────────────────────────────
def classify_status(last_seen: str, charge_count: int, months_active: int, cfg: dict, today: datetime) -> str:
    """ACTIVE = recurring AND charged within `active_window_days`.
    STOPPED = recurring but quiet >active_window_days.
    ONE_OFF = below recurrence threshold."""
    min_charges = cfg["recurrence"]["min_charges"]
    min_months = cfg["recurrence"]["min_months"]
    active_days = cfg["recurrence"].get("active_window_days", 45)

    if charge_count < min_charges or months_active < min_months:
        return "ONE_OFF"
    if not last_seen:
        return "STOPPED"
    try:
        last_dt = datetime.strptime(last_seen, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return "STOPPED"
    if (today - last_dt).days <= active_days:
        return "ACTIVE"
    return "STOPPED"


def group_by_vendor(transactions: list[dict], cfg: dict) -> list[dict]:
    """Aggregate transactions by vendor. Each row keeps full transaction list under `transactions` key."""
    groups = defaultdict(list)
    for t in transactions:
        groups[t["vendor"]].append(t)

    out = []
    today = datetime.now(timezone.utc)

    for vendor, txns in groups.items():
        sources = {t["source"] for t in txns}
        months = {t["date"][:7] for t in txns if t["date"]}
        # Vendor's primary category = most common across its transactions
        cats = [t.get("category") or "Other" for t in txns]
        category = max(set(cats), key=cats.count)
        amounts_by_currency = defaultdict(float)
        for t in txns:
            amounts_by_currency[t["currency"]] += t["amount"]

        if amounts_by_currency:
            predominant = max(amounts_by_currency.items(), key=lambda kv: abs(kv[1]))[0]
            total = amounts_by_currency[predominant]
            currency_label = predominant if len(amounts_by_currency) == 1 else f"{predominant} (MIXED)"
        else:
            total = 0
            currency_label = ""

        dates = sorted([t["date"] for t in txns if t["date"]])
        first_seen = dates[0] if dates else ""
        last_seen = dates[-1] if dates else ""
        status = classify_status(last_seen, len(txns), len(months), cfg, today)
        is_recurring = status in ("ACTIVE", "STOPPED")
        annual_run_rate = (total / max(len(months), 1)) * 12 if is_recurring else 0
        recurrence = "RECURRING" if is_recurring else "ONE_OFF"

        out.append({
            "vendor": vendor,
            "category": category,
            "source": "mixed" if len(sources) > 1 else next(iter(sources)),
            "status": status,  # ACTIVE / STOPPED / ONE_OFF
            "total_amount": round(total, 2),
            "currency": currency_label,
            "charge_count": len(txns),
            "avg_charge": round(total / len(txns), 2) if txns else 0,
            "months_active": len(months),
            "recurrence": recurrence,
            "annual_run_rate": round(annual_run_rate, 2),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "decision": "",
            "notes": "",
            "transactions": sorted(txns, key=lambda x: x["date"], reverse=True),
            "amounts_by_currency": dict(amounts_by_currency),
        })

    out.sort(key=lambda r: abs(r["total_amount"]), reverse=True)
    return out


# ── CSV writers ────────────────────────────────────────────────────────────
def write_transactions_csv(path: Path, transactions: list[dict]) -> None:
    fieldnames = ["date", "source", "vendor", "raw_vendor", "amount", "currency", "status", "id", "notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in sorted(transactions, key=lambda x: x["date"], reverse=True):
            w.writerow({k: t.get(k, "") for k in fieldnames})


def write_vendor_csv(path: Path, vendor_rows: list[dict]) -> None:
    fieldnames = [
        "vendor", "category", "status", "source", "total_amount", "currency", "charge_count", "avg_charge",
        "months_active", "recurrence", "annual_run_rate", "first_seen", "last_seen",
        "decision", "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in vendor_rows:
            w.writerow(r)


# ── HTML report ────────────────────────────────────────────────────────────
# Short blurb shown under each category heading, explaining what's in it.
CATEGORY_DESCRIPTIONS = {
    "EP Payment": "Recurring monthly payouts to Executive Partners (the bulk of outgoing money). Reference suffix -EP or -CPL.",
    "Card transactions": "Settled card transactions on Airwallex-issued cards. Merchant names are not exposed by the API, so each row here is grouped by exact charge amount — recurring monthly charges of the same amount are almost always one subscription. Use the decision column to label which merchant each amount maps to (Fathom, LinkedIn, Notion, etc.).",
    "Vendor invoice": "One-off or recurring vendor invoices (software vendors, contractors not on EP roster). Reference contains INV-…",
    "Reimbursement": "Reimbursements paid out (e.g. Ivan's expense reports).",
    "Compound CC settlement (incoming)": "Money flowing INTO the wallet from the Compound credit card product (merchant settlements). Not an expense — track for reconciliation.",
    "Other deposit": "Top-ups and other incoming wallet credits.",
    "FX conversion": "Currency conversions between wallet sub-accounts. Net to zero across BUY/SELL pairs.",
    "Fee": "Airwallex platform fees and third-party fees on payouts.",
    "Refund / adjustment": "Refunds for failed/cancelled payouts. Money returning to the wallet.",
    "Other": "Uncategorised. Review and consider adding a rule in spend-config.json or PATTERN_RULES.",
}


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Airwallex Spend Review — __LABEL__</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    margin: 0;
    background: #f7f7f9;
    color: #1a1a1a;
  }
  header {
    background: #1a1a2e;
    color: #fff;
    padding: 24px 32px;
  }
  header h1 { margin: 0; font-size: 22px; }
  header .meta { opacity: 0.7; font-size: 13px; margin-top: 4px; }
  main { padding: 24px 32px; max-width: 1400px; margin: 0 auto; }
  section { background: #fff; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
  section h2 { margin-top: 0; font-size: 16px; color: #1a1a2e; border-bottom: 1px solid #e5e5ea; padding-bottom: 8px; }
  .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 12px; }
  .stat { background: #f7f7f9; padding: 12px 14px; border-radius: 8px; }
  .stat .label { font-size: 11px; text-transform: uppercase; color: #666; letter-spacing: 0.5px; }
  .stat .value { font-size: 18px; font-weight: 600; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #eee; vertical-align: top; }
  th { background: #f7f7f9; font-weight: 600; cursor: pointer; user-select: none; position: sticky; top: 0; z-index: 1; }
  th:hover { background: #eee; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .badge.ACTIVE { background: #d4edda; color: #155724; }
  .badge.STOPPED { background: #fff3cd; color: #856404; }
  .badge.ONE_OFF { background: #e2e3e5; color: #383d41; }
  .badge.RECURRING { background: #cce5ff; color: #004085; }
  .badge.MIXED { background: #f8d7da; color: #721c24; }
  details { margin-top: 6px; }
  details summary { cursor: pointer; padding: 6px 0; color: #555; font-size: 12px; }
  details summary:hover { color: #1a1a2e; }
  .nested-table { background: #fafafa; padding: 8px; border-radius: 6px; margin-top: 6px; }
  .nested-table table { font-size: 12px; }
  .negative { color: #c00; }
  .positive { color: #060; }
  .filter { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
  .filter input { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; flex: 1; min-width: 200px; font-size: 13px; }
  .filter button { padding: 6px 12px; border: 1px solid #ddd; background: #fff; border-radius: 6px; cursor: pointer; font-size: 12px; }
  .filter button.active { background: #1a1a2e; color: #fff; border-color: #1a1a2e; }
  .decision-input { width: 100%; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; }
  footer { padding: 16px 32px; color: #888; font-size: 12px; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>Airwallex Spend Review — __LABEL__</h1>
  <div class="meta">__GENERATED_AT__ · __VENDOR_COUNT__ vendors · __TXN_COUNT__ transactions (after dedup)</div>
</header>
<main>

<section>
  <h2>Activity by source</h2>
  <div class="stat-grid">
    __SOURCE_STATS__
  </div>
</section>

<section>
  <h2>Activity by transaction type (wallet)</h2>
  <table id="type-table">
    <thead><tr><th>Type</th><th class="num">Count</th><th>Net amount(s)</th></tr></thead>
    <tbody>__TYPE_ROWS__</tbody>
  </table>
</section>

<section>
  <h2>Categories overview</h2>
  <p style="color:#666;font-size:13px;margin-top:4px;">Net flow per category over the window. Click a row to jump to its detail table below.</p>
  <table id="overview-table">
    <thead><tr>
      <th>Category</th><th class="num">Vendors</th><th class="num">Transactions</th><th>Net amount(s)</th>
    </tr></thead>
    <tbody>__OVERVIEW_ROWS__</tbody>
  </table>
</section>

__CATEGORY_SECTIONS__

</main>
<footer>
  Generated by review-airwallex-spend skill · Decisions you type are saved to localStorage in your browser.
</footer>
<script>
  // Persist decision values to localStorage so they survive re-runs of this report
  document.querySelectorAll('.decision-input').forEach(inp => {
    const key = 'airwallex-decision-__LABEL__-' + inp.dataset.vendor;
    const saved = localStorage.getItem(key);
    if (saved) inp.value = saved;
    inp.addEventListener('input', () => localStorage.setItem(key, inp.value));
  });

  // Vendor row click toggles detail row (works across all category tables)
  document.querySelectorAll('tr.vendor-row').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', (e) => {
      if (e.target.tagName === 'INPUT') return;
      const next = row.nextElementSibling;
      if (next && next.classList.contains('detail-row')) {
        const expanded = next.dataset.expanded === '1';
        next.dataset.expanded = expanded ? '0' : '1';
        next.style.display = expanded ? 'none' : '';
      }
    });
  });
  // Overview row click jumps to corresponding category section
  document.querySelectorAll('#overview-table tr[data-cat]').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => {
      const id = 'cat-' + row.dataset.cat;
      const target = document.getElementById(id);
      if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
    });
  });
</script>
</body>
</html>
"""


def fmt_amount(amount: float, currency: str) -> str:
    cls = "negative" if amount < 0 else ("positive" if amount > 0 else "")
    return f'<span class="num {cls}">{currency} {amount:,.2f}</span>'


def fmt_amounts_by_currency(amounts: dict) -> str:
    return ", ".join(fmt_amount(amt, cur) for cur, amt in sorted(amounts.items()))


def write_html_report(path: Path, vendor_rows: list[dict], transactions: list[dict], cfg: dict, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    active_days = cfg["recurrence"].get("active_window_days", 45)

    # Source stats
    by_source: dict[str, dict] = defaultdict(lambda: {"count": 0, "by_currency": defaultdict(float)})
    for t in transactions:
        by_source[t["source"]]["count"] += 1
        if t["currency"]:
            by_source[t["source"]]["by_currency"][t["currency"]] += t["amount"]
    source_stats = []
    for src, info in sorted(by_source.items()):
        cur_str = "<br>".join(f"{cur} {amt:,.2f}" for cur, amt in sorted(info["by_currency"].items()))
        source_stats.append(
            f'<div class="stat"><div class="label">{html.escape(src)} ({info["count"]} txn)</div>'
            f'<div class="value">{cur_str}</div></div>'
        )

    # Wallet activity by transaction type
    by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "by_currency": defaultdict(float)})
    for t in transactions:
        if t["source"] != "wallet":
            continue
        notes = t.get("notes") or "OTHER"
        by_type[notes]["count"] += 1
        if t["currency"]:
            by_type[notes]["by_currency"][t["currency"]] += t["amount"]
    type_rows = []
    for typ, info in sorted(by_type.items(), key=lambda kv: -kv[1]["count"]):
        cur_str = "<br>".join(f'{fmt_amount(amt, cur)}' for cur, amt in sorted(info["by_currency"].items()))
        type_rows.append(
            f'<tr><td>{html.escape(typ)}</td><td class="num">{info["count"]}</td><td>{cur_str}</td></tr>'
        )

    # Group vendors by category
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for v in vendor_rows:
        by_cat[v.get("category", "Other")].append(v)

    # Per-category aggregates for overview table
    overview_rows = []
    for cat in CATEGORY_ORDER:
        if cat not in by_cat:
            continue
        vs = by_cat[cat]
        cat_amounts = defaultdict(float)
        txn_count = 0
        for v in vs:
            txn_count += v["charge_count"]
            for cur, amt in v.get("amounts_by_currency", {}).items():
                cat_amounts[cur] += amt
        cat_amount_html = "<br>".join(fmt_amount(amt, cur) for cur, amt in sorted(cat_amounts.items()))
        cat_id = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-")
        overview_rows.append(
            f'<tr data-cat="{cat_id}">'
            f'<td><strong>{html.escape(cat)}</strong></td>'
            f'<td class="num">{len(vs)}</td>'
            f'<td class="num">{txn_count}</td>'
            f'<td>{cat_amount_html}</td></tr>'
        )

    # One section per category — vendor table inside, click row to expand
    category_sections = []
    for cat in CATEGORY_ORDER:
        if cat not in by_cat:
            continue
        vs = sorted(by_cat[cat], key=lambda r: abs(r["total_amount"]), reverse=True)
        cat_id = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-")
        cat_desc = CATEGORY_DESCRIPTIONS.get(cat, "")

        # Card subscriptions need a "what is this?" placeholder; everything else gets keep/cancel
        is_card_cat = cat == "Card transactions"
        placeholder = "merchant name? + keep/cancel" if is_card_cat else "keep / cancel / renegotiate"

        rows_html = []
        for v in vs:
            cur = v["currency"].split()[0] if v["currency"] else ""
            mixed_badge = '<span class="badge MIXED" title="Multiple currencies">MIXED</span>' if "MIXED" in v["currency"] else ""
            run_rate_cell = fmt_amount(v["annual_run_rate"], cur) if v["status"] in ("ACTIVE", "STOPPED") else '<span style="color:#aaa;">—</span>'
            rows_html.append(
                f'<tr class="vendor-row" data-vendor="{html.escape(v["vendor"])}" data-status="{v["status"]}">'
                f'<td><strong>{html.escape(v["vendor"])}</strong> {mixed_badge}</td>'
                f'<td><span class="badge {v["status"]}">{v["status"]}</span></td>'
                f'<td class="num">{v["charge_count"]}</td>'
                f'<td class="num">{v["months_active"]}</td>'
                f'<td>{fmt_amount(v["total_amount"], cur)}</td>'
                f'<td>{fmt_amount(v["avg_charge"], cur)}</td>'
                f'<td>{run_rate_cell}</td>'
                f'<td>{html.escape(v["first_seen"])}</td>'
                f'<td>{html.escape(v["last_seen"])}</td>'
                f'<td><input type="text" class="decision-input" data-vendor="{html.escape(v["vendor"])}" '
                f'placeholder="{placeholder}"></td>'
                f'</tr>'
            )
            # detail row with every transaction
            detail_inner = ['<table><thead><tr><th>Date</th><th>Source</th><th>Description (raw)</th><th>Type</th><th>Status</th><th class="num">Amount</th></tr></thead><tbody>']
            for t in v["transactions"]:
                detail_inner.append(
                    f'<tr><td>{html.escape(t["date"])}</td>'
                    f'<td>{html.escape(t["source"])}</td>'
                    f'<td>{html.escape((t.get("raw_vendor") or "")[:80])}</td>'
                    f'<td style="font-size:11px;color:#888">{html.escape(t.get("notes") or "")}</td>'
                    f'<td style="font-size:11px;color:#888">{html.escape(t.get("status") or "")}</td>'
                    f'<td>{fmt_amount(t["amount"], t["currency"])}</td></tr>'
                )
            detail_inner.append("</tbody></table>")
            rows_html.append(
                f'<tr class="detail-row" data-expanded="0" style="display:none;">'
                f'<td colspan="10"><div class="nested-table">{"".join(detail_inner)}</div></td></tr>'
            )

        category_sections.append(f"""
<section id="cat-{cat_id}">
  <h2>{html.escape(cat)} <span style="font-weight:400;font-size:13px;color:#888;">— {len(vs)} vendor(s)</span></h2>
  <p style="color:#666;font-size:13px;margin-top:0;">{html.escape(cat_desc)}</p>
  <table>
    <thead><tr>
      <th>Vendor</th><th>Status</th><th class="num">Charges</th><th class="num">Months</th>
      <th class="num">Total</th><th class="num">Avg</th><th class="num">Annual run-rate</th>
      <th>First seen</th><th>Last seen</th><th>Decision</th>
    </tr></thead>
    <tbody>{"".join(rows_html)}</tbody>
  </table>
</section>
""")

    html_out = (HTML_TEMPLATE
        .replace("__LABEL__", html.escape(label))
        .replace("__GENERATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__VENDOR_COUNT__", str(len(vendor_rows)))
        .replace("__TXN_COUNT__", str(len(transactions)))
        .replace("__ACTIVE_DAYS__", str(active_days))
        .replace("__SOURCE_STATS__", "".join(source_stats))
        .replace("__TYPE_ROWS__", "".join(type_rows))
        .replace("__OVERVIEW_ROWS__", "".join(overview_rows))
        .replace("__CATEGORY_SECTIONS__", "".join(category_sections))
    )
    path.write_text(html_out)


# ── Summary printer ────────────────────────────────────────────────────────
def print_summary(
    vendor_rows: list[dict],
    transactions: list[dict],
    cfg: dict,
    label: str,
    csv_path: Path,
    vendor_path: Path,
    recurring_only: bool,
) -> str:
    """Prints summary to stdout AND returns it as a string for capture."""
    lines = []

    def p(s: str = ""):
        print(s)
        lines.append(s)

    p("")
    p("=" * 78)
    p(f"AIRWALLEX SPEND REVIEW — {label}")
    p("=" * 78)

    # By source
    by_source = defaultdict(lambda: {"count": 0, "by_currency": defaultdict(float)})
    for t in transactions:
        by_source[t["source"]]["count"] += 1
        if t["currency"]:
            by_source[t["source"]]["by_currency"][t["currency"]] += t["amount"]

    p("")
    p("By source:")
    for src, info in sorted(by_source.items()):
        cur_str = ", ".join(f"{cur} {amt:,.2f}" for cur, amt in sorted(info["by_currency"].items()))
        p(f"  {src:<10} {info['count']:>5} txn(s)   {cur_str}")

    # By transaction type (wallet only — exposes card spend vs payouts vs FX)
    by_type = defaultdict(lambda: {"count": 0, "by_currency": defaultdict(float)})
    for t in transactions:
        if t["source"] != "wallet":
            continue
        notes = t.get("notes") or "OTHER"
        by_type[notes]["count"] += 1
        if t["currency"]:
            by_type[notes]["by_currency"][t["currency"]] += t["amount"]
    if by_type:
        p("")
        p("Wallet activity by type:")
        for typ, info in sorted(by_type.items(), key=lambda kv: -kv[1]["count"]):
            cur_str = ", ".join(f"{cur} {amt:,.2f}" for cur, amt in sorted(info["by_currency"].items()))
            p(f"  {typ:<50} {info['count']:>5}   {cur_str}")

    # Recurring subscriptions
    recurring = [r for r in vendor_rows if r["recurrence"] == "RECURRING"]
    recurring.sort(key=lambda r: abs(r["annual_run_rate"]), reverse=True)
    p("")
    p(f"Recurring subscriptions ({len(recurring)} vendors):")
    if recurring:
        p(f"  {'VENDOR':<40}  {'CHARGES':>7}  {'MONTHS':>6}  {'TOTAL':>14}  {'ANNUAL RUN':>14}")
        for r in recurring:
            vendor_disp = r["vendor"][:40]
            cur = r["currency"].split()[0] if r["currency"] else ""
            p(
                f"  {vendor_disp:<40}  {r['charge_count']:>7}  {r['months_active']:>6}  "
                f"{cur} {r['total_amount']:>10,.2f}  {cur} {r['annual_run_rate']:>10,.2f}"
            )
    else:
        p("  (none detected)")

    # Top vendors
    top_n = cfg["output"]["top_vendors_in_summary"]
    rows_for_top = recurring if recurring_only else vendor_rows
    p("")
    p(f"Top {min(top_n, len(rows_for_top))} vendors by absolute spend:")
    p(f"  {'VENDOR':<40}  {'SRC':<8}  {'CHARGES':>7}  {'TOTAL':>16}  {'TYPE':<10}")
    for r in rows_for_top[:top_n]:
        vendor_disp = r["vendor"][:40]
        cur = r["currency"].split()[0] if r["currency"] else ""
        p(
            f"  {vendor_disp:<40}  {r['source']:<8}  {r['charge_count']:>7}  "
            f"{cur} {r['total_amount']:>12,.2f}  {r['recurrence']:<10}"
        )

    # Note: /api/v1/cards/* and /api/v1/issuing/* require Admin role and aren't accessible.
    # The script routes around this using /api/v1/balances/history which exposes merchant names
    # for the last ~5 days, persisted across runs in merchant-memory.json so coverage grows.
    # Suppress the noisy permission issues block — it's expected and not actionable.

    p("")
    p(f"Wrote: {csv_path}")
    p(f"Wrote: {vendor_path}")
    p("")
    p("Open the by-vendor CSV in Numbers/Sheets and fill the 'decision' column")
    p("with keep / cancel / renegotiate to track your review.")
    p("")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Review Airwallex spend across cards, wallet, transfers")
    parser.add_argument("--months", type=int, help="Months back from today (default 12)")
    parser.add_argument("--ytd", action="store_true", help="Year to date")
    parser.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    parser.add_argument(
        "--source",
        help="Comma-separated subset: cards,wallet,transfers (default: all three)",
    )
    parser.add_argument("--recurring-only", action="store_true", help="Show only RECURRING vendors in the top list")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open the HTML report in browser")
    parser.add_argument("--sheet", action="store_true", help="Also export to Google Sheets")
    parser.add_argument("--sheet-id", help="Existing Google Sheet ID to update (default: create new)")
    args = parser.parse_args()

    cfg = load_config()

    # Prefer the dedicated Admin key for this skill (so process-ep-invoices keeps using
    # its lower-privileged key). Falls back to the shared key if the admin one isn't set.
    client_id = os.getenv("AIRWALLEX_ADMIN_CLIENT_ID") or os.getenv("AIRWALLEX_CLIENT_ID", "")
    api_key = os.getenv("AIRWALLEX_ADMIN_API_KEY") or os.getenv("AIRWALLEX_API_KEY", "")
    using_admin = bool(os.getenv("AIRWALLEX_ADMIN_CLIENT_ID"))
    if not client_id or not api_key:
        print("[ERROR] Set AIRWALLEX_ADMIN_CLIENT_ID/_API_KEY (preferred) or AIRWALLEX_CLIENT_ID/_API_KEY in .env")
        sys.exit(1)
    if using_admin:
        print(f"Using dedicated admin key: {client_id}")
    else:
        print(f"Using shared key: {client_id}  (set AIRWALLEX_ADMIN_CLIENT_ID/_API_KEY to use a separate admin key)")

    base_url = AIRWALLEX_URLS.get(cfg["airwallex"]["environment"], AIRWALLEX_URLS["production"])
    page_size = cfg["airwallex"].get("page_size", 100)

    start, end, label = resolve_window(args)
    print(f"Window: {start.date()} → {end.date()}")

    sources = (args.source or "cards,wallet,transfers").split(",")
    sources = [s.strip().lower() for s in sources]

    print("Logging in to Airwallex...")
    token = airwallex_login(base_url, client_id, api_key)

    raw = {"cards": [], "wallet": [], "transfers": []}

    if "cards" in sources:
        raw["cards"] = fetch_card_transactions(base_url, token, start, end, page_size)
    if "wallet" in sources:
        raw["wallet"] = fetch_financial_transactions(base_url, token, start, end, page_size)
    if "transfers" in sources:
        raw["transfers"] = fetch_transfers(base_url, token, start, end, page_size)

    # Pull merchant lookup from balances/history (last ~5 days, capped by Airwallex)
    fresh_merchant_map = fetch_balance_history_merchants(base_url, token) if "wallet" in sources else {}
    # Merge with persisted memory from prior runs — accumulates across months
    persisted = load_merchant_memory()
    merchant_map = {**persisted, **fresh_merchant_map}  # fresh wins on conflict
    new_keys = set(fresh_merchant_map) - set(persisted)
    if new_keys:
        print(f"    Added {len(new_keys)} new merchant(s) to memory: {', '.join(fresh_merchant_map[k] for k in new_keys)}")
    print(f"    Total memory: {len(merchant_map)} merchant→amount mapping(s)")
    save_merchant_memory(merchant_map)

    normalisation = dict(cfg.get("vendor_normalisation", {}))
    normalisation["__merchant_map__"] = merchant_map  # smuggled in for normalise_financial_txn
    # Per-transaction lookup from CSV import — index by (currency, amount) → list of (date, merchant)
    # so we can do nearest-date matching (CSV uses transaction date, API uses settlement date)
    txn_index: dict = {}
    if CARD_TXN_CSV_PATH.exists():
        try:
            raw_lookup = json.loads(CARD_TXN_CSV_PATH.read_text())
            for key, val in raw_lookup.items():
                if "|" not in key:
                    continue
                parts = key.split("|")
                if len(parts) != 3:
                    continue
                date, cur, amt_str = parts
                try:
                    amt = round(float(amt_str), 2)
                except ValueError:
                    continue
                merchant = val.get("merchant") if isinstance(val, dict) else val
                txn_index.setdefault((cur, amt), []).append((date, merchant))
            n_total = sum(len(v) for v in txn_index.values())
            print(f"  Loaded {n_total} CSV transactions across {len(txn_index)} amount buckets for date-tolerant merchant matching")
        except Exception as e:
            print(f"  [WARN] Could not load card transaction CSV cache: {e}")
    normalisation["__txn_index__"] = txn_index
    skip_zero = cfg["output"].get("skip_zero_amount", True)

    transactions = []
    for t in raw["cards"]:
        norm = normalise_card_txn(t, normalisation)
        if norm and (not skip_zero or norm["amount"] != 0):
            transactions.append(norm)
    for t in raw["wallet"]:
        norm = normalise_financial_txn(t, normalisation)
        if norm and (not skip_zero or norm["amount"] != 0):
            transactions.append(norm)
    for t in raw["transfers"]:
        norm = normalise_transfer(t, normalisation)
        if norm and (not skip_zero or norm["amount"] != 0):
            transactions.append(norm)

    if not transactions:
        print("\n[INFO] No transactions found in window across selected sources.")
        sys.exit(0)

    print(f"\nNormalised {len(transactions)} transaction(s) across {len(sources)} source(s).")
    transactions = dedupe_wallet_vs_transfers(transactions)
    print(f"After dedup: {len(transactions)} transaction(s).")
    vendor_rows = group_by_vendor(transactions, cfg)
    print(f"Grouped into {len(vendor_rows)} vendor(s).")

    out_dir = OUTPUT_ROOT / label
    csv_path = out_dir / "transactions.csv"
    vendor_path = out_dir / "by-vendor.csv"
    summary_path = out_dir / "summary.txt"
    html_path = out_dir / "report.html"

    write_transactions_csv(csv_path, transactions)
    write_vendor_csv(vendor_path, vendor_rows)
    write_html_report(html_path, vendor_rows, transactions, cfg, label)

    summary_text = print_summary(
        vendor_rows, transactions, cfg, label, csv_path, vendor_path,
        recurring_only=args.recurring_only,
    )
    summary_path.write_text(summary_text)

    print(f"\nHTML report: {html_path}")
    if not args.no_open:
        try:
            subprocess.run(["open", str(html_path)], check=False)
            print("  (opened in browser)")
        except Exception:
            pass

    # Optional: also export to Google Sheets for shareable review
    if args.sheet:
        print("\nExporting to Google Sheets...")
        # Lazy import — only needed if --sheet is set
        sys.path.insert(0, str(SKILL_ROOT))
        from libraries import sheets_export
        # Resolve target sheet: explicit --sheet-id wins, then config default, else create new
        target_sheet_id = args.sheet_id or cfg["output"].get("default_sheet_id")
        try:
            url = sheets_export.export(vendor_rows, transactions, label, existing_sheet_id=target_sheet_id, cards=cfg.get("cards", []))
            print(f"\nGoogle Sheet: {url}")
            if not args.no_open:
                subprocess.run(["open", url], check=False)
        except Exception as e:
            print(f"[ERROR] Sheet export failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
