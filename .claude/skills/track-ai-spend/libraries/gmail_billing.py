"""
Gmail Billing Email Reader — Search and parse billing/receipt emails.

Reuses get_gmail_service from invite-candidates skill (shared OAuth).
Uses gmail_reader from track-recruitment-events for message fetching.
"""

import base64
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


def extract_paid_date(text: str) -> tuple[int, int, int] | None:
    """
    Extract billing date from "Paid <Month> <Day>, <Year>" in email body.

    Receipts forwarded from personal email have the forward date in headers,
    so we need to parse the actual billing date from the body.

    Returns (year, month, day) tuple or None.
    """
    match = re.search(
        r"Paid\s+(\w+)\s+(\d{1,2}),\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    month_name = match.group(1).lower()
    day = int(match.group(2))
    year = int(match.group(3))
    month_num = MONTH_NAMES.get(month_name)
    if not month_num:
        return None

    return year, month_num, day


# Map currency symbol prefixes to ISO codes
CURRENCY_PREFIX_MAP = {
    "A": "AUD",
    "US": "USD",
    "CA": "CAD",
    "NZ": "NZD",
    "HK": "HKD",
    "S": "SGD",
}


def extract_receipt_details(text: str, subject: str) -> dict:
    """
    Extract receipt metadata from email text.

    Returns dict with receipt_number, invoice_number, payment_method, paid_date_str.
    """
    details = {}

    # Receipt number from subject: "receipt from Anthropic, PBC #2298-0017-5136"
    m = re.search(r"#([\d-]+)", subject)
    if m:
        details["receipt_number"] = m.group(1)

    # Invoice number from body: "Invoice number   E3170EB9-0005"
    m = re.search(r"Invoice\s+number\s+([A-Z0-9]+-\d+)", text, re.IGNORECASE)
    if m:
        details["invoice_number"] = m.group(1)

    # Payment method: "Visa - 85" or similar
    m = re.search(r"Payment\s+method\s+.*?(Visa|Mastercard|Amex)\s*[-–]\s*(\d+)", text, re.IGNORECASE)
    if m:
        details["payment_method"] = f"{m.group(1)} ending {m.group(2)}"

    # Full paid date string: "Paid January 23, 2026"
    m = re.search(r"Paid\s+(\w+\s+\d{1,2},\s+\d{4})", text, re.IGNORECASE)
    if m:
        details["paid_date"] = m.group(1)

    return details


def download_pdf_attachments(service, message: dict, output_dir: Path) -> list[Path]:
    """
    Download all PDF attachments from a Gmail message to output_dir.

    Returns list of saved file paths.
    """
    saved = []
    payload = message.get("payload", {})
    msg_id = message["id"]
    parts = payload.get("parts", [])

    for part in parts:
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        if mime_type != "application/pdf" or not filename:
            continue

        body = part.get("body", {})
        att_id = body.get("attachmentId")
        if not att_id:
            continue

        att = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=msg_id, id=att_id)
            .execute()
        )
        data = att.get("data", "")
        pdf_bytes = base64.urlsafe_b64decode(data)

        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        with open(filepath, "wb") as f:
            f.write(pdf_bytes)
        saved.append(filepath)

    return saved


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
