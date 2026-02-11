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
                    "property": "Candidate",
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
        "Candidate": {
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
