"""
Gmail helpers for the help-on-gmail skill.

Provides reply draft creation and label management.
Reuses get_gmail_service from invite-candidates (shared OAuth2 helper).
"""

import base64
import sys
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(
    0, str(PROJECT_ROOT / ".claude" / "skills" / "invite-candidates" / "libraries")
)

from gmail_auth import get_gmail_service  # noqa: E402

TOKEN_PATH = PROJECT_ROOT / "local-data" / "gmail_token_ivan_help.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
]

# Cache label name → ID lookups within a session
_label_cache: dict[str, str] = {}


def _get_service():
    return get_gmail_service(token_path=TOKEN_PATH, scopes=SCOPES)


def create_reply_draft(
    service,
    message_id: str,
    thread_id: str,
    to: str,
    subject: str,
    body_html: str,
) -> dict:
    """
    Create a Gmail draft reply in the same thread.

    Returns the created draft resource dict.
    """
    msg = MIMEText(body_html, "html")
    msg["To"] = to
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    msg["In-Reply-To"] = message_id
    msg["References"] = message_id

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    draft = (
        service.users()
        .drafts()
        .create(
            userId="me",
            body={
                "message": {
                    "raw": raw,
                    "threadId": thread_id,
                },
            },
        )
        .execute()
    )
    return draft


def get_label_id(service, label_name: str) -> str | None:
    """
    Resolve a Gmail label name to its ID. Cached per session.

    Returns None if the label doesn't exist.
    """
    if label_name in _label_cache:
        return _label_cache[label_name]

    results = service.users().labels().list(userId="me").execute()
    for label in results.get("labels", []):
        if label["name"].lower() == label_name.lower():
            _label_cache[label_name] = label["id"]
            return label["id"]
    return None


def remove_label(service, message_id: str, label_name: str) -> bool:
    """
    Remove a label from a Gmail message by label name.

    Returns True if successful, False if label not found.
    """
    label_id = get_label_id(service, label_name)
    if not label_id:
        return False

    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": [label_id]},
    ).execute()
    return True


if __name__ == "__main__":
    # Quick test: list labels to verify auth works
    import json

    service = _get_service()
    results = service.users().labels().list(userId="me").execute()
    labels = [l["name"] for l in results.get("labels", [])]
    print(json.dumps(sorted(labels), indent=2))
