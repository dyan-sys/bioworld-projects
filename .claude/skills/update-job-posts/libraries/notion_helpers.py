"""
Notion API helpers for the update-job-posts skill.

Reusable functions for querying, creating, and updating Notion pages.
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


def query_open_openings(headers: dict, db_id: str) -> list[dict]:
    """
    Query the Ally Openings DB for all openings with Status = 'Open'.

    Returns list of page objects.
    """
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    payload = {
        "filter": {
            "property": "Status",
            "status": {"equals": "Open"},
        },
    }

    results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def fetch_page(headers: dict, page_id: str) -> dict:
    """Fetch a single Notion page by ID."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def create_page(headers: dict, payload: dict) -> dict:
    """
    Create a new page in a Notion database.

    payload should include 'parent', 'properties', and optionally 'children' (body blocks).
    Returns the created page object.
    """
    url = f"{NOTION_API_BASE}/pages"
    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def update_page_properties(headers: dict, page_id: str, properties: dict) -> dict:
    """
    Update properties on an existing Notion page.

    properties is a dict of property name -> property value object.
    """
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    payload = {"properties": properties}
    response = requests.patch(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()
