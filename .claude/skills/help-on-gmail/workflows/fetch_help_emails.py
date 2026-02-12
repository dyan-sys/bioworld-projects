"""
Fetch emails labeled ally-os-help from Gmail.

Reuses get_gmail_service from invite-candidates (shared OAuth2 helper)
and reader utilities from track-recruitment-events.

Outputs a JSON array to stdout for Claude Code to consume.
"""

import argparse
import json
import sys
from pathlib import Path

# Project root: 4 levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Add skill paths so we can import shared helpers
sys.path.insert(
    0, str(PROJECT_ROOT / ".claude" / "skills" / "invite-candidates" / "libraries")
)
sys.path.insert(
    0,
    str(
        PROJECT_ROOT
        / ".claude"
        / "skills"
        / "track-recruitment-events"
        / "libraries"
    ),
)

from gmail_auth import get_gmail_service  # noqa: E402
from gmail_reader import (  # noqa: E402
    extract_email_body,
    get_full_message,
    get_message_headers,
    search_messages,
)

CREDENTIALS_PATH = PROJECT_ROOT / "Google-credentials.json"
TOKEN_PATH = PROJECT_ROOT / "local-data" / "gmail_token_ivan_help.json"
# gmail.modify covers read + label management + draft creation, but NOT send.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def fetch_help_emails(limit: int = 10, unread_only: bool = False) -> list[dict]:
    """Fetch emails with the ally-os-help label."""
    service = get_gmail_service(
        credentials_path=CREDENTIALS_PATH, token_path=TOKEN_PATH, scopes=SCOPES
    )

    query = "label:ally-os-help"
    if unread_only:
        query += " is:unread"

    raw_messages = search_messages(service, query, max_results=limit)

    if not raw_messages:
        return []

    emails = []
    for msg_stub in raw_messages:
        msg = get_full_message(service, msg_stub["id"])
        headers = get_message_headers(msg)
        body = extract_email_body(msg)

        emails.append(
            {
                "message_id": msg["id"],
                "thread_id": msg["threadId"],
                "subject": headers.get("subject", "(no subject)"),
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "date": headers.get("date", ""),
                "body_text": body.get("text", ""),
                "snippet": msg.get("snippet", ""),
            }
        )

    return emails


def main():
    parser = argparse.ArgumentParser(description="Fetch ally-os-help emails from Gmail")
    parser.add_argument(
        "--limit", type=int, default=10, help="Max emails to fetch (default: 10)"
    )
    parser.add_argument(
        "--unread-only", action="store_true", help="Only fetch unread emails"
    )
    args = parser.parse_args()

    emails = fetch_help_emails(limit=args.limit, unread_only=args.unread_only)
    print(json.dumps(emails, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
