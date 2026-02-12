"""
Gmail Reader — Search and read Gmail messages.

Imports get_gmail_service from the invite-candidates skill (shared auth).
"""

import base64
from email.utils import parsedate_to_datetime


def search_messages(service, query: str, max_results: int = 10) -> list[dict]:
    """
    Search Gmail for messages matching query.

    Returns list of message metadata dicts with 'id' and 'threadId'.
    """
    results = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return results.get("messages", [])


def get_full_message(service, message_id: str) -> dict:
    """Fetch a full Gmail message by ID."""
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def get_message_headers(message: dict) -> dict[str, str]:
    """Extract headers as a dict from a Gmail message."""
    headers = {}
    payload = message.get("payload", {})
    for header in payload.get("headers", []):
        headers[header["name"].lower()] = header["value"]
    return headers


def get_message_date(message: dict) -> str | None:
    """Extract send date from message headers. Returns ISO format string."""
    headers = get_message_headers(message)
    date_str = headers.get("date")
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str


def extract_email_body(message: dict) -> dict[str, str]:
    """
    Extract plain text and HTML body from a Gmail message.

    Returns dict with 'text' and 'html' keys.
    """
    payload = message.get("payload", {})
    result = {"text": "", "html": ""}

    def _decode_part(part: dict) -> tuple[str, str]:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")
        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            return mime, decoded
        return mime, ""

    # Simple message (no parts)
    if not payload.get("parts"):
        mime, content = _decode_part(payload)
        if "html" in mime:
            result["html"] = content
        else:
            result["text"] = content
        return result

    # Multipart message
    for part in payload.get("parts", []):
        mime, content = _decode_part(part)
        if mime == "text/plain" and not result["text"]:
            result["text"] = content
        elif mime == "text/html" and not result["html"]:
            result["html"] = content

        # Handle nested multipart
        for sub in part.get("parts", []):
            mime, content = _decode_part(sub)
            if mime == "text/plain" and not result["text"]:
                result["text"] = content
            elif mime == "text/html" and not result["html"]:
                result["html"] = content

    return result
