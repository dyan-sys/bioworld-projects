"""
Notion Spend Database — Query and upsert monthly AI spend rows.

Schema:
  Month (title)         — "2026-02"
  Charge (number)       — raw amount from receipt (e.g. 20.00)
  Currency (select)     — original currency code (e.g. "AUD", "USD")
  AUD Amount (number)   — amount in AUD (= Charge when currency is AUD)
  Reimbursed (AUD) (number) — manual entry, how much has been reimbursed
  Balance (AUD) (formula)   — = AUD Amount - Reimbursed (AUD)
  Updated At (rich_text)
  Notes (rich_text)
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


def find_month_row(api_key: str, db_id: str, month: str) -> dict | None:
    """
    Find an existing row in the spend DB by Month title.

    Returns the page object if found, None otherwise.
    """
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    headers = notion_headers(api_key)
    payload = {
        "filter": {
            "property": "Month",
            "title": {"equals": month},
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0] if results else None


def upsert_spend_row(
    api_key: str,
    db_id: str,
    month: str,
    charge: float,
    currency: str,
    aud_amount: float,
    updated_at: str,
    notes: str = "",
) -> dict:
    """
    Create or update a spend row for the given month.

    Args:
        month: e.g. "2026-02"
        charge: raw amount from receipt
        currency: original currency code (e.g. "AUD", "USD")
        aud_amount: amount in AUD (same as charge when currency is AUD)
        updated_at: ISO timestamp
        notes: optional notes/warnings

    Does NOT touch Reimbursed (AUD) — that's manual entry.
    Returns the Notion page object.
    """
    headers = notion_headers(api_key)
    existing = find_month_row(api_key, db_id, month)

    # Build properties (only script-managed fields)
    properties = {
        "Month": {"title": [{"text": {"content": month}}]},
        "Charge": {"number": charge},
        "Currency": {"select": {"name": currency}},
        "AUD Amount": {"number": aud_amount},
        "Updated At": {"rich_text": [{"text": {"content": updated_at}}]},
    }

    if notes:
        properties["Notes"] = {"rich_text": [{"text": {"content": notes[:2000]}}]}

    if existing:
        # Update existing row — don't overwrite Reimbursed (AUD)
        page_id = existing["id"]
        url = f"{NOTION_API_BASE}/pages/{page_id}"
        response = requests.patch(
            url, headers=headers, json={"properties": properties}, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
    else:
        # Create new row
        url = f"{NOTION_API_BASE}/pages"
        payload = {
            "parent": {"database_id": db_id},
            "properties": properties,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
