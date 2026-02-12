"""
Gmail Billing Email Reader — Search and parse billing/receipt emails.

Reuses get_gmail_service from invite-candidates skill (shared OAuth).
Uses gmail_reader from track-recruitment-events for message fetching.
"""

import json
import re
from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def load_billing_config() -> dict:
    """Load billing-config.json with per-service parsing rules."""
    config_path = TEMPLATES_DIR / "billing-config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_billing_emails(
    service,
    gmail_search_query: str,
    year: int,
    month: int,
    max_results: int = 10,
) -> list[dict]:
    """
    Search Gmail for billing emails within a specific month.

    Adds date range filter (after/before) to the config's search query.
    Returns list of message metadata dicts with 'id' and 'threadId'.
    """
    # Build date range: after:YYYY/M/1 before:YYYY/M+1/1
    after_date = f"{year}/{month}/1"
    if month == 12:
        before_date = f"{year + 1}/1/1"
    else:
        before_date = f"{year}/{month + 1}/1"

    query = f"{gmail_search_query} after:{after_date} before:{before_date}"

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return results.get("messages", [])


def search_billing_emails_days(
    service,
    gmail_search_query: str,
    days: int,
    max_results: int = 20,
) -> list[dict]:
    """Search Gmail for billing emails within last N days (for discover mode)."""
    query = f"{gmail_search_query} newer_than:{days}d"

    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return results.get("messages", [])


MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def extract_paid_date(text: str) -> tuple[int, int] | None:
    """
    Extract billing month from "Paid <Month> <Day>, <Year>" in email body.

    Receipts forwarded from personal email have the forward date in headers,
    so we need to parse the actual billing date from the body.

    Returns (year, month) tuple or None.
    """
    match = re.search(
        r"Paid\s+(\w+)\s+\d{1,2},\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    month_name = match.group(1).lower()
    year = int(match.group(2))
    month_num = MONTH_NAMES.get(month_name)
    if not month_num:
        return None

    return year, month_num


# Map currency symbol prefixes to ISO codes
CURRENCY_PREFIX_MAP = {
    "A": "AUD",
    "US": "USD",
    "CA": "CAD",
    "NZ": "NZD",
    "HK": "HKD",
    "S": "SGD",
}


def extract_charge(text: str, amount_pattern: str) -> tuple[float, str] | None:
    """
    Extract charge amount and currency from text.

    The pattern should have two capture groups: (currency_prefix, amount).
    e.g. pattern r"([A-Z]{1,2})\\$([\\d,]+\\.\\d{2})" matches "A$34.00"

    Returns (amount, currency_code) tuple or None.
    """
    match = re.search(amount_pattern, text, re.IGNORECASE)
    if not match:
        return None

    groups = match.groups()
    if len(groups) >= 2:
        prefix = groups[0].upper()
        amount_str = groups[1]
        currency = CURRENCY_PREFIX_MAP.get(prefix, prefix)
        amount = float(amount_str.replace(",", ""))
        return amount, currency

    return None
