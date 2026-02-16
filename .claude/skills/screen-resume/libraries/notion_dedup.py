"""
Duplicate / previous-application detection for the Candidates DB.

Queries Notion for other candidate pages matching the same name or email,
excluding the current page. Returns a formatted note to prepend to the
scoring rationale so reviewers immediately see prior history.
"""

import requests
from datetime import datetime

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


def _headers(notion_key: str) -> dict:
    return {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _query_by_name(notion_key: str, db_id: str, full_name: str) -> list[dict]:
    """Find all candidates with an exact Full Name match."""
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    payload = {
        "filter": {
            "property": "Full Name",
            "title": {"equals": full_name},
        },
        "page_size": 10,
    }
    resp = requests.post(url, headers=_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _query_by_email(notion_key: str, db_id: str, email: str) -> list[dict]:
    """Find all candidates with an exact Email match."""
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    payload = {
        "filter": {
            "property": "Email",
            "email": {"equals": email},
        },
        "page_size": 10,
    }
    resp = requests.post(url, headers=_headers(notion_key), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _extract_page_summary(page: dict) -> dict:
    """Pull key fields from a candidate page for the dedup note."""
    props = page.get("properties", {})

    # Created date
    created = page.get("created_time", "")[:10]  # YYYY-MM-DD

    # Status
    status = ""
    status_prop = props.get("Status", {})
    if status_prop.get("type") == "status" and status_prop.get("status"):
        status = status_prop["status"].get("name", "")

    # Kimi score + recommendation
    kimi_rating = ""
    kimi_prop = props.get("Kimi Rating", {})
    if kimi_prop.get("type") == "rich_text":
        items = kimi_prop.get("rich_text", [])
        if items:
            kimi_rating = items[0].get("plain_text", "")

    kimi_rec = ""
    kimi_rec_prop = props.get("Kimi Recommendation", {})
    if kimi_rec_prop.get("type") == "select" and kimi_rec_prop.get("select"):
        kimi_rec = kimi_rec_prop["select"].get("name", "")

    # Claude score + recommendation
    claude_rating = ""
    claude_prop = props.get("Claude Rating", {})
    if claude_prop.get("type") == "rich_text":
        items = claude_prop.get("rich_text", [])
        if items:
            claude_rating = items[0].get("plain_text", "")

    claude_rec = ""
    claude_rec_prop = props.get("Claude Recommendation", {})
    if claude_rec_prop.get("type") == "select" and claude_rec_prop.get("select"):
        claude_rec = claude_rec_prop["select"].get("name", "")

    # Post (job opening) — relation, just note if present
    post_ids = []
    post_prop = props.get("Post", {})
    if post_prop.get("type") == "relation":
        post_ids = [r.get("id", "") for r in post_prop.get("relation", [])]

    return {
        "page_id": page.get("id", "").replace("-", ""),
        "created": created,
        "status": status,
        "kimi_rating": kimi_rating,
        "kimi_rec": kimi_rec,
        "claude_rating": claude_rating,
        "claude_rec": claude_rec,
        "has_post": bool(post_ids),
    }


def check_previous_applications(
    notion_key: str,
    db_id: str,
    candidate_name: str,
    current_page_id: str,
    candidate_email: str | None = None,
) -> str | None:
    """
    Check if this candidate has applied before (other pages with same name/email).

    Args:
        notion_key: Notion API key.
        db_id: Candidates database ID.
        candidate_name: Full name of the candidate being scored.
        current_page_id: Page ID of the current candidate (excluded from results).
        candidate_email: Email if available (stronger dedup signal).

    Returns:
        A formatted note string to prepend to the rationale, or None if no prior
        applications found.
    """
    # Normalize current page ID (Notion sometimes returns with/without dashes)
    current_normalized = current_page_id.replace("-", "")

    seen_ids = {current_normalized}
    prior_pages = []

    # Search by name
    try:
        name_matches = _query_by_name(notion_key, db_id, candidate_name)
        for page in name_matches:
            pid = page.get("id", "").replace("-", "")
            if pid not in seen_ids:
                seen_ids.add(pid)
                prior_pages.append(page)
    except Exception as e:
        print(f"  [DEDUP] Name query failed: {e}")

    # Search by email (if available)
    if candidate_email:
        try:
            email_matches = _query_by_email(notion_key, db_id, candidate_email)
            for page in email_matches:
                pid = page.get("id", "").replace("-", "")
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    prior_pages.append(page)
        except Exception as e:
            print(f"  [DEDUP] Email query failed: {e}")

    if not prior_pages:
        return None

    # Build the note
    summaries = [_extract_page_summary(p) for p in prior_pages]

    lines = [f"PREVIOUS APPLICATION ({len(summaries)} prior record{'s' if len(summaries) > 1 else ''} found):"]
    for s in summaries:
        parts = [f"Applied {s['created']}"]
        if s["status"]:
            parts.append(f"Status: {s['status']}")
        if s["kimi_rating"]:
            score_str = f"Kimi {s['kimi_rating']}"
            if s["kimi_rec"]:
                score_str += f" ({s['kimi_rec']})"
            parts.append(score_str)
        if s["claude_rating"]:
            score_str = f"Claude {s['claude_rating']}"
            if s["claude_rec"]:
                score_str += f" ({s['claude_rec']})"
            parts.append(score_str)
        lines.append(f"  - {' | '.join(parts)}")

    return "\n".join(lines)
