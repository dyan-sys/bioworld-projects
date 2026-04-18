"""AllyBot FAQ handler — answers EP questions via DM or @mention."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOKEN_PATH = PROJECT_ROOT / "google_token_hris.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.events",
]

CALENDAR_ID = "dyan@withally.com"
ALL_HANDS_TITLE = "Ally All-Hands Meeting"

FALLBACK_MSG = (
    "Hi! I can help you with:\n"
    "• *When is the next all-hands?*\n\n"
    "More FAQs coming soon! In the meantime, check my Home tab for forms and resources."
)


# ── Google Calendar ─────────────────────────────────────────────────────────

def _get_calendar():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
        else:
            logger.error("No valid Google credentials. Run track-leave-requests first to authenticate.")
            return None
    return build("calendar", "v3", credentials=creds)


def _get_next_all_hands():
    cal = _get_calendar()
    if not cal:
        return None, None

    now = datetime.now(timezone.utc).isoformat()
    result = cal.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
        q=ALL_HANDS_TITLE,
    ).execute()

    for event in result.get("items", []):
        if ALL_HANDS_TITLE.lower() in event.get("summary", "").lower():
            start = event["start"].get("dateTime", event["start"].get("date"))
            return event["summary"], start

    return None, None


def _format_reply(summary: str, start: str) -> str:
    try:
        dt = datetime.fromisoformat(start)
        formatted = dt.strftime("%A, %B %-d at %-I:%M %p")
        return f"The next *{summary}* is on *{formatted}* 🗓"
    except Exception:
        return f"The next *{summary}* is on *{start}* 🗓"


# ── Question routing ────────────────────────────────────────────────────────

def _is_all_hands_question(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in ["all-hands", "all hands", "allhands", "all hand"])


def _answer(text: str, say, thread_ts=None):
    """Route the question and reply. Returns True if answered."""
    clean = re.sub(r"<@[^>]+>", "", text).strip()

    if _is_all_hands_question(clean):
        summary, start = _get_next_all_hands()
        if summary:
            reply = _format_reply(summary, start)
        else:
            reply = "I couldn't find an upcoming All-Hands on the calendar. It may not be scheduled yet."
        say(text=reply, thread_ts=thread_ts)
        return True

    return False


# ── Slack registration ──────────────────────────────────────────────────────

def register(app):
    """Register FAQ message handlers."""

    @app.event("app_mention")
    def handle_mention(event, say):
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        if not _answer(text, say, thread_ts):
            say(text=FALLBACK_MSG, thread_ts=thread_ts)

    @app.event("message")
    def handle_dm(event, say):
        # Only respond to DMs, ignore bot messages and channel posts
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id") or event.get("subtype"):
            return
        text = event.get("text", "")
        if not _answer(text, say):
            say(text=FALLBACK_MSG)
