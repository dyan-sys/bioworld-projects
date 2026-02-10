"""
Slack Reader Library

Reads channel history from Slack using the slack_sdk WebClient.
Resolves user IDs to display names and formats conversations as readable transcripts.
"""

import os
from datetime import datetime, timedelta, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SGT = timezone(timedelta(hours=8))


def get_slack_client() -> WebClient:
    """Create a Slack WebClient from SLACK_BOT_TOKEN."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise EnvironmentError("Missing required environment variable: SLACK_BOT_TOKEN")
    return WebClient(token=token)


def get_date_range_utc(date_str: str) -> tuple[float, float]:
    """
    Convert a YYYY-MM-DD date string (interpreted as SGT) to Unix timestamp range.

    Returns (start_ts, end_ts) covering the full day in SGT.
    """
    day_start_sgt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=SGT)
    day_end_sgt = day_start_sgt + timedelta(days=1)
    return day_start_sgt.timestamp(), day_end_sgt.timestamp()


def fetch_channel_messages(
    client: WebClient, channel_id: str, oldest: float, latest: float
) -> list[dict]:
    """
    Fetch all messages from a channel in the given time range.
    Handles pagination via cursor.
    """
    messages = []
    cursor = None

    while True:
        kwargs = {
            "channel": channel_id,
            "oldest": str(oldest),
            "latest": str(latest),
            "limit": 200,
            "inclusive": True,
        }
        if cursor:
            kwargs["cursor"] = cursor

        resp = client.conversations_history(**kwargs)
        messages.extend(resp.get("messages", []))

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    # API returns newest first; reverse to chronological
    messages.reverse()
    return messages


def fetch_thread_replies(
    client: WebClient, channel_id: str, thread_ts: str
) -> list[dict]:
    """
    Fetch all replies in a thread. Handles pagination.
    Returns replies excluding the parent message.
    """
    replies = []
    cursor = None

    while True:
        kwargs = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor

        resp = client.conversations_replies(**kwargs)
        batch = resp.get("messages", [])
        replies.extend(batch)

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    # First message is the parent; skip it
    return replies[1:] if replies else []


def resolve_user_names(client: WebClient, user_ids: set[str]) -> dict[str, str]:
    """
    Batch-resolve Slack user IDs to display names.
    Returns {user_id: display_name} mapping.
    """
    names = {}
    for uid in user_ids:
        try:
            resp = client.users_info(user=uid)
            profile = resp["user"].get("profile", {})
            name = (
                profile.get("display_name")
                or profile.get("real_name")
                or resp["user"].get("name", uid)
            )
            names[uid] = name
        except SlackApiError:
            names[uid] = uid
    return names


def format_conversations(
    client: WebClient,
    channel_id: str,
    channel_name: str,
    date_str: str,
) -> str:
    """
    Fetch and format a channel's messages for a given date into a readable transcript.

    Returns a formatted string like:
        === #ep-client-a (2026-02-09) ===
        [08:30] John: Good morning
        [08:31] Client: Hi John, can you send the report?
          └─ [08:45] John: Sure, sending now
    """
    oldest, latest = get_date_range_utc(date_str)
    messages = fetch_channel_messages(client, channel_id, oldest, latest)

    if not messages:
        return f"=== {channel_name} ({date_str}) ===\n[No messages]\n"

    # Collect all user IDs for name resolution
    user_ids = set()
    for msg in messages:
        if msg.get("user"):
            user_ids.add(msg["user"])
        if msg.get("reply_count", 0) > 0:
            # We'll fetch thread replies and collect their user IDs too
            pass

    # Fetch threads and collect more user IDs
    threads = {}
    for msg in messages:
        if msg.get("reply_count", 0) > 0:
            replies = fetch_thread_replies(client, channel_id, msg["ts"])
            threads[msg["ts"]] = replies
            for reply in replies:
                if reply.get("user"):
                    user_ids.add(reply["user"])

    # Resolve names
    names = resolve_user_names(client, user_ids)

    # Format output
    lines = [f"=== {channel_name} ({date_str}) ==="]

    for msg in messages:
        ts = datetime.fromtimestamp(float(msg["ts"]), tz=SGT)
        time_str = ts.strftime("%H:%M")
        user = names.get(msg.get("user", ""), msg.get("user", "bot"))
        text = msg.get("text", "").replace("\n", "\n    ")
        lines.append(f"[{time_str}] {user}: {text}")

        # Append thread replies indented
        if msg["ts"] in threads:
            for reply in threads[msg["ts"]]:
                rts = datetime.fromtimestamp(float(reply["ts"]), tz=SGT)
                rtime = rts.strftime("%H:%M")
                ruser = names.get(reply.get("user", ""), reply.get("user", "bot"))
                rtext = reply.get("text", "").replace("\n", "\n      ")
                lines.append(f"  └─ [{rtime}] {ruser}: {rtext}")

    lines.append("")  # trailing newline
    return "\n".join(lines)
