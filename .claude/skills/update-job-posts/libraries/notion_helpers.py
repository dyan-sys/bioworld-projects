"""
Notion API helpers for the update-job-posts skill.

Reusable functions for querying, creating, and updating Notion pages.
"""

import time

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_TIMEOUT = 30
BLOCK_APPEND_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15]  # seconds between retry 1→2, 2→3

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectionError,
)


def _request_with_retry(method: str, url: str, headers: dict, timeout: int = REQUEST_TIMEOUT, **kwargs) -> requests.Response:
    """
    Make an HTTP request with retry on transient failures.

    Retries on ReadTimeout, ConnectionError, 429 (rate limit), and 5xx errors.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt - 1]
                    print(f"    [RETRY] HTTP {response.status_code}, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
            response.raise_for_status()
            return response
        except RETRYABLE_EXCEPTIONS as exc:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt - 1]
                print(f"    [RETRY] {type(exc).__name__}, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                raise
    # Unreachable, but satisfies type checker
    raise RuntimeError("Exhausted retries")


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

        response = _request_with_retry("POST", url, headers=headers, json=payload)
        data = response.json()

        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def fetch_page(headers: dict, page_id: str) -> dict:
    """Fetch a single Notion page by ID."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    response = _request_with_retry("GET", url, headers=headers)
    return response.json()


def create_page(headers: dict, payload: dict) -> dict:
    """
    Create a new page in a Notion database.

    payload should include 'parent', 'properties', and optionally 'children' (body blocks).
    Returns the created page object.
    """
    url = f"{NOTION_API_BASE}/pages"
    response = _request_with_retry("POST", url, headers=headers, json=payload)
    return response.json()


def update_page_properties(headers: dict, page_id: str, properties: dict) -> dict:
    """
    Update properties on an existing Notion page.

    properties is a dict of property name -> property value object.
    """
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    payload = {"properties": properties}
    response = _request_with_retry("PATCH", url, headers=headers, json=payload)
    return response.json()


def append_blocks(headers: dict, page_id: str, blocks: list[dict]) -> None:
    """
    Append children blocks to an existing Notion page.

    Batches in groups of 100 (Notion API limit per request).
    """
    url = f"{NOTION_API_BASE}/blocks/{page_id}/children"
    batch_size = 100

    for i in range(0, len(blocks), batch_size):
        batch = blocks[i : i + batch_size]
        payload = {"children": batch}
        _request_with_retry("PATCH", url, headers=headers, timeout=BLOCK_APPEND_TIMEOUT, json=payload)
