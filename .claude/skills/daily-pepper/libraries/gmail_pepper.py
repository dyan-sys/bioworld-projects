"""
Gmail Pepper — Fetch recent emails and prioritize via Gemini for Daily Pepper.

Reuses shared Gmail auth and reader utilities.
"""

import json
import os
import sys
from pathlib import Path

# Shared libraries from other skills
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "invite-candidates" / "libraries"))
from gmail_auth import get_gmail_service

sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "skills" / "track-recruitment-events" / "libraries"))
from gmail_reader import search_messages, get_full_message, get_message_headers, extract_email_body


GMAIL_TOKEN_PATH = PROJECT_ROOT / "local-data" / "gmail_token_ivan.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def fetch_recent_emails(max_results: int = 20) -> list[dict]:
    """Fetch emails from the last 24 hours.

    Returns list of dicts with: from, subject, snippet (first ~200 chars of body).
    """
    service = get_gmail_service(
        token_path=GMAIL_TOKEN_PATH,
        scopes=GMAIL_SCOPES,
    )

    messages = search_messages(service, query="newer_than:1d in:inbox", max_results=max_results)
    if not messages:
        return []

    emails = []
    for msg_meta in messages:
        full = get_full_message(service, msg_meta["id"])
        headers = get_message_headers(full)

        sender = headers.get("from", "Unknown")
        subject = headers.get("subject", "(no subject)")

        body = extract_email_body(full)
        text = body.get("text", "") or body.get("html", "")
        snippet = text[:200].replace("\n", " ").strip()

        emails.append({
            "id": msg_meta["id"],
            "from": sender,
            "subject": subject,
            "snippet": snippet,
        })

    return emails


def prioritize_with_gemini(emails: list[dict]) -> list[dict]:
    """Send emails to Gemini for prioritization.

    Returns list of dicts with: bucket, from, subject, reason.
    Buckets: "needs_attention" (top 3) and "worth_knowing" (top 3).
    """
    from google import genai
    from google.genai.types import HttpOptions

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(
        api_key=api_key,
        http_options=HttpOptions(timeout=30_000),
    )

    email_list = "\n\n".join(
        f"Email {i+1}:\nFrom: {e['from']}\nSubject: {e['subject']}\nPreview: {e['snippet']}"
        for i, e in enumerate(emails)
    )

    prompt = f"""You are triaging an inbox for a talent operations professional.

Below are {len(emails)} recent emails. Pick the most important ones and categorize them into exactly two buckets:

1. **Needs Attention** (up to 3): Requires a response, action, or decision soon.
2. **Worth Knowing** (up to 3): Informational but important to be aware of.

Pick up to 6 total. If fewer than 6 emails exist, distribute across both buckets as best you can.

For each selected email, provide:
- "index": the email number (1-based, matching the list above)
- "bucket": "needs_attention" or "worth_knowing"
- "from": sender display name only (e.g. "Cherie Wong", not the full email address)
- "subject": original subject line
- "reason": one short sentence explaining why it matters

Return ONLY a JSON array, no other text.

--- EMAILS ---
{email_list}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    text = response.text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()

    prioritized = json.loads(text)

    # Map Gemini's 1-based index back to Gmail message ID
    for item in prioritized:
        idx = item.get("index")
        if idx and 1 <= idx <= len(emails):
            item["message_id"] = emails[idx - 1]["id"]

    return prioritized


def format_inbox_highlights(prioritized: list[dict]) -> str:
    """Format prioritized emails into a Slack mrkdwn section.

    Returns empty string if no emails.
    """
    if not prioritized:
        return ""

    needs = [e for e in prioritized if e.get("bucket") == "needs_attention"]
    worth = [e for e in prioritized if e.get("bucket") == "worth_knowing"]

    if not needs and not worth:
        return ""

    lines = ["\n:email: *Inbox Highlights*", ""]

    def _email_line(email: dict, emoji: str) -> str:
        sender = email.get("from", "Unknown")
        subject = email.get("subject", "(no subject)")
        if len(subject) > 50:
            subject = subject[:47] + "..."
        msg_id = email.get("message_id")
        if msg_id:
            url = f"https://mail.google.com/mail/u/0/#inbox/{msg_id}"
            return f"  {emoji} {sender} — <{url}|{subject}>"
        return f"  {emoji} {sender} — {subject}"

    if needs:
        lines.append("_Needs Attention:_")
        for e in needs:
            lines.append(_email_line(e, ":red_circle:"))

    if worth:
        if needs:
            lines.append("")
        lines.append("_Worth Knowing:_")
        for e in worth:
            lines.append(_email_line(e, ":large_blue_circle:"))

    return "\n".join(lines)


def get_inbox_highlights() -> str:
    """High-level entry point: fetch → prioritize → format.

    Returns formatted mrkdwn string, or empty string on failure.
    """
    emails = fetch_recent_emails()
    if not emails:
        return ""

    prioritized = prioritize_with_gemini(emails)
    return format_inbox_highlights(prioritized)
