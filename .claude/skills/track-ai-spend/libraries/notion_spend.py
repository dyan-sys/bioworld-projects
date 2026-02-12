"""
Notion Spend Database — Query and upsert monthly AI spend rows.

Ledger-style schema:
  Month (title)         — "2026-02 | Anthropic Claude" for spend, description for reimbursements
  Type (select)         — "Spend" (auto) or "Reimbursement" (manual)
  Date (date)           — transaction date (from "Paid" date in receipt)
  Charge (number)       — raw amount from receipt (always positive)
  Currency (select)     — original currency code (e.g. "AUD", "USD")
  AUD Amount (number)   — negative for spend (outflow), positive for reimbursements (inflow)
  Updated At (rich_text)
  Notes (rich_text)

Footer Sum on AUD Amount = net balance (negative = still owed).
"""

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_TIMEOUT = 30


def notion_headers(api_key: str) -> dict:
    """Return standard Notion API request headers."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def find_row_by_title(api_key: str, db_id: str, title: str) -> dict | None:
    """
    Find an existing row in the spend DB by Month title (exact match).

    Returns the page object if found, None otherwise.
    """
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    headers = notion_headers(api_key)
    payload = {
        "filter": {
            "property": "Month",
            "title": {"equals": title},
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None


def _build_receipt_blocks(details: dict) -> list[dict]:
    """Build Notion page body blocks from receipt details."""
    blocks = []

    # Header
    blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Receipt Details"}}],
        },
    })

    # Details as bulleted list
    items = []
    if details.get("receipt_number"):
        items.append(f"Receipt #: {details['receipt_number']}")
    if details.get("invoice_number"):
        items.append(f"Invoice #: {details['invoice_number']}")
    if details.get("paid_date"):
        items.append(f"Paid: {details['paid_date']}")
    if details.get("amount_display"):
        items.append(f"Amount: {details['amount_display']}")
    if details.get("payment_method"):
        items.append(f"Payment: {details['payment_method']}")
    if details.get("email_subject"):
        items.append(f"Email: {details['email_subject']}")
    if details.get("gmail_message_id"):
        items.append(f"Gmail ID: {details['gmail_message_id']}")

    for item in items:
        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": item}}],
            },
        })

    return blocks


def upsert_spend_row(
    api_key: str,
    db_id: str,
    title: str,
    charge: float,
    currency: str,
    aud_amount: float,
    updated_at: str,
    paid_date_iso: str | None = None,
    notes: str = "",
    receipt_details: dict | None = None,
) -> dict:
    """
    Create or update a spend row.

    Args:
        title: row title, e.g. "2026-02 | Anthropic Claude"
        charge: raw amount from receipt (always positive)
        currency: original currency code (e.g. "AUD", "USD")
        aud_amount: amount in AUD — stored as negative (spend = outflow)
        updated_at: ISO timestamp
        paid_date_iso: transaction date in ISO format (YYYY-MM-DD), for Date column
        notes: optional notes/warnings
        receipt_details: optional dict of receipt info for page body

    Returns the Notion page object.
    """
    headers = notion_headers(api_key)
    existing = find_row_by_title(api_key, db_id, title)

    # Build properties — AUD Amount is negative for spend (outflow)
    properties = {
        "Month": {"title": [{"text": {"content": title}}]},
        "Type": {"select": {"name": "Spend"}},
        "Charge": {"number": charge},
        "Currency": {"select": {"name": currency}},
        "AUD Amount": {"number": -abs(aud_amount)},
        "Updated At": {"rich_text": [{"text": {"content": updated_at}}]},
    }

    if paid_date_iso:
        properties["Date"] = {"date": {"start": paid_date_iso}}

    if notes:
        properties["Notes"] = {"rich_text": [{"text": {"content": notes[:2000]}}]}

    if existing:
        page_id = existing["id"]
        url = f"{NOTION_API_BASE}/pages/{page_id}"
        response = requests.patch(
            url, headers=headers, json={"properties": properties}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    else:
        # Create new row with optional page body
        url = f"{NOTION_API_BASE}/pages"
        payload = {
            "parent": {"database_id": db_id},
            "properties": properties,
        }

        if receipt_details:
            payload["children"] = _build_receipt_blocks(receipt_details)

        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
