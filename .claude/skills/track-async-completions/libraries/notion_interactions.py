"""
Notion Interactions — Find candidates and create Interaction records.

Uses the same requests-based Notion API pattern as other skills.
"""

import requests

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


def _notion_headers(notion_key: str) -> dict:
    return {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_async_invited_candidates(notion_key: str, db_id: str) -> list[dict]:
    """
    Fetch all candidates with Screener = "To invite (Async)".

    Returns list of page dicts — the pool of candidates who were invited
    to async interviews. Used to scope fuzzy name matching.
    """
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    all_results = []
    start_cursor = None

    while True:
        payload = {
            "filter": {
                "property": "Screener",
                "status": {"equals": "To invite (Async)"},
            },
            "page_size": 100,
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=_notion_headers(notion_key), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")

    return all_results


def _normalize_name(name: str) -> set[str]:
    """Normalize a name into a set of lowercase word tokens."""
    return set(name.lower().split())


def fuzzy_match_candidate(email_name: str, pool: list[dict]) -> dict | None:
    """
    Fuzzy match a candidate name from an email against a pool of Notion pages.

    Strategy:
    1. Exact match (case-insensitive)
    2. All words from email name appear in Notion name (or vice versa)
    3. Accept only if exactly one candidate matches

    Returns the matched page dict, or None.
    """
    email_tokens = _normalize_name(email_name)
    if not email_tokens:
        return None

    # Build name → page mapping
    candidates = []
    for page in pool:
        notion_name = get_candidate_name(page)
        if not notion_name:
            continue
        notion_tokens = _normalize_name(notion_name)

        # Exact match (case-insensitive)
        if email_name.lower().strip() == notion_name.lower().strip():
            return page

        # All email tokens found in Notion name, or all Notion tokens found in email name
        if email_tokens.issubset(notion_tokens) or notion_tokens.issubset(email_tokens):
            candidates.append((page, notion_name))

    # Accept only single match to avoid ambiguity
    if len(candidates) == 1:
        return candidates[0][0]

    return None


def find_candidate_by_name(notion_key: str, db_id: str, full_name: str) -> dict | None:
    """
    Search Candidates DB for a candidate by Full Name (title field).

    Returns the first matching page dict, or None.
    """
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    payload = {
        "filter": {
            "property": "Full Name",
            "title": {"equals": full_name},
        },
        "page_size": 1,
    }
    resp = requests.post(url, headers=_notion_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def find_candidate_by_email(notion_key: str, db_id: str, email: str) -> dict | None:
    """
    Search Candidates DB for a candidate by Email.

    Returns the first matching page dict, or None.
    """
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    payload = {
        "filter": {
            "property": "Email",
            "email": {"equals": email},
        },
        "page_size": 1,
    }
    resp = requests.post(url, headers=_notion_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def get_candidate_name(page: dict) -> str:
    """Extract Full Name from a Notion candidate page."""
    props = page.get("properties", {})
    name_prop = props.get("Full Name", {})
    if name_prop.get("type") == "title":
        title_items = name_prop.get("title", [])
        if title_items:
            return title_items[0].get("plain_text", "")
    return ""


def interaction_exists(
    notion_key: str,
    interactions_db_id: str,
    candidate_page_id: str,
    interaction_type: str = "1st Round (Async)",
) -> bool:
    """
    Check if an Interaction already exists for this candidate + type.

    Prevents duplicate records.
    """
    url = f"{NOTION_BASE}/databases/{interactions_db_id}/query"
    payload = {
        "filter": {
            "and": [
                {
                    "property": "\U0001f465 Candidates DB",
                    "relation": {"contains": candidate_page_id},
                },
                {
                    "property": "Type",
                    "select": {"equals": interaction_type},
                },
            ]
        },
        "page_size": 1,
    }
    resp = requests.post(url, headers=_notion_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return len(results) > 0


def get_candidate_1r_status(page: dict) -> str | None:
    """Extract 1R status name from a Notion candidate page."""
    props = page.get("properties", {})
    r1_prop = props.get("1R", {})
    if r1_prop.get("type") == "status":
        status_obj = r1_prop.get("status")
        if status_obj:
            return status_obj.get("name")
    return None


def update_candidate_1r_status(
    notion_key: str,
    candidate_page_id: str,
    status_name: str,
) -> dict:
    """Update the 1R status field on a candidate page."""
    url = f"{NOTION_BASE}/pages/{candidate_page_id}"
    payload = {
        "properties": {
            "1R": {"status": {"name": status_name}},
        },
    }
    resp = requests.patch(url, headers=_notion_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_interaction(
    notion_key: str,
    interactions_db_id: str,
    candidate_page_id: str,
    candidate_name: str,
    assessment_link: str | None,
    interaction_date: str | None,
    interaction_type: str = "1st Round (Async)",
) -> dict:
    """
    Create an Interaction record in the Interactions DB.

    Args:
        interactions_db_id: Notion database ID for Interactions.
        candidate_page_id: Notion page ID of the matched candidate.
        candidate_name: For the title field.
        assessment_link: Hireflix admin URL.
        interaction_date: ISO date string (date only, e.g. "2026-02-10").
        interaction_type: Select value (default "1st Round (Async)").

    Returns:
        Created page response from Notion API.
    """
    url = f"{NOTION_BASE}/pages"

    properties = {
        "Name": {
            "title": [{"text": {"content": f"R1 Async - {candidate_name}"}}],
        },
        "\U0001f465 Candidates DB": {
            "relation": [{"id": candidate_page_id}],
        },
        "Type": {
            "select": {"name": interaction_type},
        },
    }

    if assessment_link:
        properties["Assessment Link"] = {"url": assessment_link}

    if interaction_date:
        # Extract date portion (YYYY-MM-DD) if full ISO datetime
        date_str = interaction_date[:10] if len(interaction_date) > 10 else interaction_date
        properties["Interaction Date"] = {"date": {"start": date_str}}

    payload = {
        "parent": {"database_id": interactions_db_id},
        "properties": properties,
    }

    resp = requests.post(url, headers=_notion_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()
