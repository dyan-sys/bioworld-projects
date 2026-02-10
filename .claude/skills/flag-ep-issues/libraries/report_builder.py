"""
Report Builder Library

Formats Kimi analysis results into a Slack-friendly monospace report
and posts to #ally-jarvis via Incoming Webhook.

Adapted from check-service-status/libraries/status_checker.py (post_to_slack pattern).
"""

import os
from datetime import datetime, timedelta, timezone

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SGT = timezone(timedelta(hours=8))

FLAG_TYPE_LABELS = {
    "missed_item": "Missed Item",
    "stalled_progress": "Stalled Progress",
}


def build_report(analysis: dict, now_sgt: datetime) -> str:
    """
    Format Kimi analysis JSON into a Slack monospace report.

    Expected analysis shape:
    {
      "date": "2026-02-09",
      "channels": [
        {"channel": "#name", "ep_name": "...", "status": "FLAG|OK|NO_ACTIVITY",
         "flags": [...], "summary": "..."}
      ]
    }
    """
    date_str = analysis.get("date", "unknown")
    channels = analysis.get("channels", [])

    flagged = [c for c in channels if c.get("status") == "FLAG"]
    ok = [c for c in channels if c.get("status") == "OK"]
    no_activity = [c for c in channels if c.get("status") == "NO_ACTIVITY"]

    timestamp = now_sgt.strftime("%Y-%m-%d %H:%M SGT")
    lines = []

    # Header
    lines.append(f"*EP Channel Review* | {date_str} | {timestamp}")
    lines.append("")
    lines.append(
        f"Channels: {len(channels)} checked | "
        f"{len(flagged)} flagged | {len(ok)} OK | {len(no_activity)} no activity"
    )

    # Flagged issues
    if flagged:
        lines.append("")
        lines.append("*Flagged Issues:*")
        lines.append("```")
        for ch in flagged:
            lines.append(f"[FLAG] {ch['channel']} (EP: {ch.get('ep_name', '?')})")
            for flag in ch.get("flags", []):
                label = FLAG_TYPE_LABELS.get(flag.get("type", ""), flag.get("type", ""))
                lines.append(f"  - [{label}] {flag.get('detail', '')}")
            if ch.get("summary"):
                lines.append(f"  Summary: {ch['summary']}")
        lines.append("```")

    # OK channels
    if ok:
        lines.append("")
        lines.append("*OK Channels:*")
        lines.append("```")
        for ch in ok:
            lines.append(f"[OK] {ch['channel']}: {ch.get('summary', 'No issues')}")
        lines.append("```")

    # No activity channels
    if no_activity:
        lines.append("")
        lines.append("*No Activity:*")
        lines.append("```")
        for ch in no_activity:
            lines.append(f"[NO_ACTIVITY] {ch['channel']}: No messages for {date_str}")
        lines.append("```")

    lines.append("")
    return "\n".join(lines)


FALLBACK_DM_USER_ID = "U0975UFHDB8"


def _dm_fallback(report: str, reason: str) -> None:
    """Send report as a DM via bot token when webhook posting fails."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print(f"Slack: DM fallback also failed — no SLACK_BOT_TOKEN set.")
        return

    try:
        client = WebClient(token=token)
        client.chat_postMessage(
            channel=FALLBACK_DM_USER_ID,
            text=f"⚠️ _Webhook failed ({reason}) — sending here instead._\n\n{report}",
        )
        print(f"Slack: sent via DM fallback to {FALLBACK_DM_USER_ID}.")
    except SlackApiError as e:
        print(f"Slack: DM fallback also failed — {e}")


def post_to_slack(report: str) -> None:
    """Post report to #ally-jarvis via SLACK_WEBHOOK_URL_JARVIS.
    Falls back to DM if webhook is missing or fails."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL_JARVIS")
    if not webhook_url:
        _dm_fallback(report, "SLACK_WEBHOOK_URL_JARVIS not set")
        return

    try:
        resp = requests.post(webhook_url, json={"text": report}, timeout=15)
        resp.raise_for_status()
        print("Slack: posted successfully.")
    except requests.RequestException as e:
        print(f"Slack: webhook failed — {e}")
        _dm_fallback(report, str(e))
