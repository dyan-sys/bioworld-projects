"""
Import Airwallex card transaction CSV (exported from the dashboard).

Backfills merchant-memory.json with (currency, amount) → merchant_name mappings,
since the API only exposes ~5 days of merchant history.

Usage:
    python3 .claude/skills/review-airwallex-spend/workflows/import_csv.py path/to/data.csv
    python3 .claude/skills/review-airwallex-spend/workflows/import_csv.py path/to/folder/

If a folder is given, all *.csv files inside are imported.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MERCHANT_MEMORY_PATH = PROJECT_ROOT / "local-data" / "airwallex-spend" / "merchant-memory.json"
# Per-transaction lookup keyed by (date|currency|amount) — disambiguates merchants
# that share the same monthly amount (e.g., 5 different SaaS at $20/mo)
CARD_TXN_LOOKUP_PATH = PROJECT_ROOT / "local-data" / "airwallex-spend" / "card-transactions-import.json"

# Possible column names Airwallex uses (varies by region/account tier)
COL_MERCHANT_USER = "Merchant (user entered)"
COL_MERCHANT_RAW = "Merchant (from transaction)"
COL_AMOUNT = "Billing amount"
COL_CURRENCY = "Billing currency"
COL_STATUS = "Transaction status"
COL_CARD = "Card name"
COL_DATE = "Transaction date UTC"


def clean_merchant(raw: str) -> str:
    """Drop city/country tail. 'GITHUB, INC., GITHUB.COM, USA' → 'GITHUB, INC.'"""
    if not raw:
        return ""
    return raw.split(",")[0].strip().title() if "," in raw else raw.strip().title()


def collect_csv_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.csv"))
    print(f"[ERROR] Path not found: {path}")
    sys.exit(1)


def load_existing_memory() -> dict:
    if not MERCHANT_MEMORY_PATH.exists():
        return {}
    try:
        return json.loads(MERCHANT_MEMORY_PATH.read_text())
    except Exception:
        return {}


def save_memory(memory: dict) -> None:
    MERCHANT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MERCHANT_MEMORY_PATH.write_text(json.dumps(memory, indent=2, sort_keys=True))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    paths = collect_csv_files(Path(sys.argv[1]))
    if not paths:
        print("[ERROR] No CSV files found")
        sys.exit(1)

    print(f"Reading {len(paths)} CSV file(s)...")

    # (currency, amount) → list of (merchant, count)
    candidates: dict = defaultdict(Counter)
    # (date, currency, amount) → {merchant, card} — per-transaction lookup, disambiguates same-amount merchants
    txn_lookup: dict = {}
    rows_processed = 0

    for p in paths:
        with p.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get(COL_STATUS) and row[COL_STATUS] not in ("Succeeded", "Settled"):
                    continue
                amt_str = row.get(COL_AMOUNT, "").strip()
                cur = row.get(COL_CURRENCY, "").strip()
                date = (row.get(COL_DATE) or "").strip()[:10]
                if not amt_str or not cur or not date:
                    continue
                try:
                    amt = round(abs(float(amt_str)), 2)
                except ValueError:
                    continue
                merchant = (row.get(COL_MERCHANT_USER) or "").strip()
                if not merchant:
                    merchant = clean_merchant(row.get(COL_MERCHANT_RAW, ""))
                if not merchant:
                    continue
                candidates[(cur, amt)][merchant] += 1
                # Per-transaction key for precise lookup
                txn_key = f"{date}|{cur}|{float(amt)}"
                txn_lookup[txn_key] = {"merchant": merchant, "card": row.get(COL_CARD, "")}
                rows_processed += 1

    print(f"  Processed {rows_processed} transaction(s) → {len(candidates)} unique (currency, amount) buckets")
    print(f"  Built {len(txn_lookup)} per-transaction lookups (disambiguates same-amount merchants)")

    # Save the per-transaction lookup
    CARD_TXN_LOOKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    CARD_TXN_LOOKUP_PATH.write_text(json.dumps(txn_lookup, indent=2, sort_keys=True))

    # Resolve each bucket → most common merchant name
    new_memory = {}
    ambiguous = []
    for (cur, amt), counter in candidates.items():
        # If multiple merchants for same amount, pick most common; flag ambiguous
        if len(counter) > 1:
            ambiguous.append((cur, amt, dict(counter)))
        merchant, _ = counter.most_common(1)[0]
        key = f"{cur}|{float(amt)}"
        new_memory[key] = merchant

    # Merge with existing memory — CSV wins (authoritative)
    existing = load_existing_memory()
    overwritten = []
    for key, val in new_memory.items():
        if key in existing and existing[key] != val:
            overwritten.append((key, existing[key], val))

    merged = {**existing, **new_memory}
    save_memory(merged)

    # Summary
    print()
    print(f"Merchant memory now has {len(merged)} mappings ({len(merged) - len(existing)} new from CSV)")
    if overwritten:
        print(f"\n{len(overwritten)} entries overwritten (CSV wins):")
        for key, old, new in overwritten[:10]:
            print(f"  {key}: '{old}' → '{new}'")

    if ambiguous:
        print(f"\n[INFO] {len(ambiguous)} amount(s) had multiple merchants — kept most common:")
        for cur, amt, counts in ambiguous[:10]:
            print(f"  {cur} {amt}: {counts}")
        print("  These amounts are ambiguous — the dashboard will show the dominant merchant.")
        print("  Edit merchant-memory.json manually to override if needed.")

    print(f"\nSaved to: {MERCHANT_MEMORY_PATH}")
    print("Re-run 'Review Airwallex spend' to see merchants in the dashboard.")


if __name__ == "__main__":
    main()
