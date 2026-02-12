"""
Track AI Spend

Parses billing/receipt emails from Gmail for AI services,
extracts charge amounts + currency, and upserts monthly rows
into a Notion database.

Usage:
    # Discovery mode — inspect raw billing email format
    python3.11 track_ai_spend.py --discover --days 90

    # Default: process previous month
    python3.11 track_ai_spend.py

    # Current month (partial)
    python3.11 track_ai_spend.py --current

    # Specific month
    python3.11 track_ai_spend.py --month 2026-01

    # Dry run (no Notion write)
    python3.11 track_ai_spend.py --dry-run
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Import gmail_auth from invite-candidates skill
INVITE_SKILL = PROJECT_ROOT / ".claude" / "skills" / "invite-candidates"
sys.path.insert(0, str(INVITE_SKILL))
from libraries.gmail_auth import get_gmail_service  # noqa: E402

# Swap to track-async-completions for gmail_reader, then to our own skill root
sys.path.remove(str(INVITE_SKILL))
for mod_name in [k for k in sys.modules if k == "libraries" or k.startswith("libraries.")]:
    del sys.modules[mod_name]

ASYNC_SKILL = PROJECT_ROOT / ".claude" / "skills" / "track-recruitment-events"
sys.path.insert(0, str(ASYNC_SKILL))
from libraries.gmail_reader import (  # noqa: E402
    get_full_message,
    get_message_headers,
    get_message_date,
    extract_email_body,
)

# Now swap to our own skill root
sys.path.remove(str(ASYNC_SKILL))
for mod_name in [k for k in sys.modules if k == "libraries" or k.startswith("libraries.")]:
    del sys.modules[mod_name]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.gmail_billing import (  # noqa: E402
    load_billing_config,
    search_billing_emails_days,
    extract_charge,
    extract_paid_date,
)
from libraries.notion_spend import upsert_spend_row  # noqa: E402

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Constants — uses ivan@withally.com (personal work email where billing receipts arrive)
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]
GMAIL_TOKEN_PATH = PROJECT_ROOT / "local-data" / "gmail_token_ivan.json"
RECEIPTS_DIR = PROJECT_ROOT / "local-data" / "ai-spend"


def load_env_keys() -> tuple[str, str]:
    """Load required environment variables."""
    notion_key = os.environ.get("NOTION_KEY")
    spend_db_id = os.environ.get("NOTION_SPEND_DB_ID")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not spend_db_id:
        missing.append("NOTION_SPEND_DB_ID")

    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    return notion_key, spend_db_id


def save_receipt(gmail_message_id: str, service_name: str, data: dict) -> Path:
    """Save a processing receipt."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{service_name}_{gmail_message_id}.json"
    filepath = RECEIPTS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


def get_target_month(args) -> tuple[int, int, str]:
    """
    Determine target year, month, and label from CLI args.

    Returns (year, month, label) e.g. (2026, 1, "2026-01").
    """
    now = datetime.now()

    if args.month:
        parts = args.month.split("-")
        year, month = int(parts[0]), int(parts[1])
    elif args.current:
        year, month = now.year, now.month
    else:
        # Previous month (default)
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1

    label = f"{year}-{month:02d}"
    return year, month, label


def _build_full_text(subject: str, body: dict) -> str:
    """Build searchable plain text from email subject + body."""
    html_text = body.get("html", "")
    plain_text = body.get("text", "")
    if html_text:
        plain_from_html = re.sub(r"<[^>]+>", " ", html_text)
        plain_from_html = re.sub(r"\s+", " ", plain_from_html).strip()
        return f"{subject} {plain_from_html}"
    return f"{subject} {plain_text}"


def run_discover(service, configs: dict, days: int):
    """Discovery mode — search all configured sources and print raw email structure."""
    print("\n[DISCOVER] Searching Gmail across all billing configs...")

    for name, config in configs.items():
        query = config["gmail_search_query"]
        print(f"\n  [{name}] Query: {query} newer_than:{days}d")

        msgs = search_billing_emails_days(service, query, days)
        print(f"  [{name}] Found {len(msgs)} message(s)")

        for i, msg_ref in enumerate(msgs, 1):
            msg = get_full_message(service, msg_ref["id"])
            headers = get_message_headers(msg)
            body = extract_email_body(msg)
            date = get_message_date(msg)
            subject = headers.get("subject", "")
            full_text = _build_full_text(subject, body)

            print(f"\n  {'─'*50}")
            print(f"  [{name} #{i}] Message ID: {msg_ref['id']}")
            print(f"    From:    {headers.get('from', 'N/A')}")
            print(f"    Subject: {subject}")
            print(f"    Date:    {date}")

            # Try parsing charge
            result = extract_charge(full_text, config["amount_pattern"])
            if result:
                amount, currency = result
                print(f"    [CHARGE] {currency} {amount:.2f}")
            else:
                print(f"    [CHARGE] NOT FOUND — pattern may need refinement")

            # Try parsing paid date
            paid_date = extract_paid_date(full_text)
            if paid_date:
                print(f"    [PAID]   {paid_date[0]}-{paid_date[1]:02d}")
            else:
                print(f"    [PAID]   NOT FOUND")

            # Show body excerpt
            excerpt = full_text[:300] if full_text else "(empty)"
            print(f"    Body excerpt: {excerpt}...")

    print(f"\n{'='*60}")
    print("TIP: Refine amount_pattern in billing-config.json based on the above.")


def process_month(service, configs: dict, year: int, month: int, month_label: str,
                  notion_key: str | None, spend_db_id: str | None, dry_run: bool):
    """Process billing emails for a specific month."""
    print(f"\n[PROCESS] Target month: {month_label}")

    # Aggregate charges across all configs for the month
    total_charge = 0.0
    total_currency = None
    notes_parts: list[str] = []
    found_any = False

    for name, config in configs.items():
        query = config["gmail_search_query"]
        print(f"\n  [{name}] Searching Gmail...")

        # Search broadly (last 90 days) since forwarded emails have the
        # forward date in headers, not the billing date. We filter by the
        # "Paid" date in the body instead.
        msgs = search_billing_emails_days(service, query, days=90)
        print(f"    Found {len(msgs)} email(s) in last 90 days")

        if not msgs:
            notes_parts.append(f"{name}: no email found")
            continue

        # Find email whose "Paid" date matches target month
        for msg_ref in msgs:
            msg_id = msg_ref["id"]
            msg = get_full_message(service, msg_id)
            headers = get_message_headers(msg)
            body = extract_email_body(msg)
            subject = headers.get("subject", "")
            full_text = _build_full_text(subject, body)

            # Extract billing date from body ("Paid January 23, 2026")
            paid_date = extract_paid_date(full_text)
            if not paid_date:
                print(f"    [{msg_id}] No 'Paid' date found — skipping")
                continue

            paid_year, paid_month = paid_date
            paid_label = f"{paid_year}-{paid_month:02d}"

            if paid_year != year or paid_month != month:
                print(f"    [{msg_id}] Paid {paid_label} — not target month, skipping")
                continue

            result = extract_charge(full_text, config["amount_pattern"])
            if result:
                amount, currency = result
                print(f"    [{msg_id}] Paid {paid_label} — {currency} {amount:.2f}")
                total_charge += amount
                total_currency = currency
                found_any = True

                # Save receipt
                receipt_data = {
                    "service": name,
                    "month": month_label,
                    "charge": amount,
                    "currency": currency,
                    "gmail_message_id": msg_id,
                    "paid_date": paid_label,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
                if not dry_run:
                    save_receipt(msg_id, name, receipt_data)
            else:
                print(f"    [{msg_id}] Paid {paid_label} — charge NOT FOUND")
                notes_parts.append(f"{name}: email found but charge not parsed")

    if not found_any:
        notes_parts.append("no charges found for this month")

    # For AUD charges, AUD Amount = Charge. For other currencies,
    # AUD Amount is left equal to Charge (user can manually adjust).
    aud_amount = round(total_charge, 2)
    notes = "; ".join(notes_parts) if notes_parts else ""
    currency_label = total_currency or "AUD"
    updated_at = datetime.now(timezone.utc).isoformat()

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"  Month:    {month_label}")
    print(f"  Charge:   {currency_label} {total_charge:.2f}")
    print(f"  AUD Amount: {aud_amount:.2f}")
    if notes:
        print(f"  Notes:    {notes}")

    # Upsert to Notion
    if dry_run:
        print(f"\n  [DRY RUN] Would upsert row for {month_label}")
    else:
        if not notion_key or not spend_db_id:
            print(f"\n  [SKIP] NOTION_KEY or NOTION_SPEND_DB_ID not set — skipping Notion upsert")
            return

        print(f"\n  [NOTION] Upserting row for {month_label}...")
        try:
            page = upsert_spend_row(
                api_key=notion_key,
                db_id=spend_db_id,
                month=month_label,
                charge=total_charge,
                currency=currency_label,
                aud_amount=aud_amount,
                updated_at=updated_at,
                notes=notes,
            )
            print(f"  [NOTION] Done — page ID: {page.get('id')}")
        except Exception as e:
            print(f"  [NOTION] ERROR: {type(e).__name__}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Track AI subscription spend from Gmail billing emails")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discovery mode: print raw billing email structure for inspection",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview amounts without writing to Notion",
    )
    parser.add_argument(
        "--month",
        help="Target month in YYYY-MM format (default: previous month)",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Process current month (partial)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Lookback window in days for discover mode (default: 90)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("TRACK AI SPEND")
    print("=" * 60)

    if args.dry_run:
        print("[MODE] Dry run — no Notion writes")
    if args.discover:
        print("[MODE] Discovery — inspecting raw billing email format")

    # Load billing config
    configs = load_billing_config()
    print(f"  Loaded {len(configs)} service config(s): {', '.join(configs.keys())}")

    # Authenticate Gmail (ivan@withally.com — separate token from recruitment@)
    print("\n[1/3] Authenticating Gmail (ivan@withally.com)...")
    try:
        service = get_gmail_service(scopes=GMAIL_SCOPES, token_path=GMAIL_TOKEN_PATH)
        print("  Gmail authenticated (readonly scope, ivan@ token).")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR: Gmail auth failed: {e}")
        sys.exit(1)

    # Discovery mode
    if args.discover:
        run_discover(service, configs, args.days)
        return

    # Load Notion keys
    print("\n[2/3] Loading environment...")
    notion_key = None
    spend_db_id = None
    try:
        notion_key, spend_db_id = load_env_keys()
        print(f"  NOTION_KEY loaded.")
        print(f"  Spend DB: {spend_db_id}")
    except EnvironmentError as e:
        if args.dry_run:
            print(f"  WARNING: {e} (continuing in dry-run mode)")
        else:
            print(f"  ERROR: {e}")
            sys.exit(1)

    # Determine target month
    year, month, month_label = get_target_month(args)

    # Process
    print(f"\n[3/3] Processing billing emails for {month_label}...")
    process_month(service, configs, year, month, month_label,
                  notion_key, spend_db_id, args.dry_run)


if __name__ == "__main__":
    main()
