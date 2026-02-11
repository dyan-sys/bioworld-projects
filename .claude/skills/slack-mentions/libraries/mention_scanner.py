"""
Mention Scanner Library

Core Slack API interactions for discovering channels, scanning for mentions,
checking if mentions have been actioned, and building deep links.
"""

import os
import re

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_slack_client() -> WebClient:
    """Create a Slack WebClient from SLACK_BOT_TOKEN."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN environment variable not set")
    return WebClient(token=token)


def discover_channels(
    client: WebClient,
    channel_types: str = "public_channel,private_channel",
    exclude_ids: list[str] | None = None,
) -> list[dict]:
    """Discover all channels the bot is a member of.

    Returns list of dicts with 'id' and 'name' keys.
    """
    exclude_ids = set(exclude_ids or [])
    channels = []
    cursor = None

    while True:
        resp = client.conversations_list(
            types=channel_types,
            exclude_archived=True,
            limit=200,
            cursor=cursor or "",
        )

        for ch in resp.get("channels", []):
            if ch.get("is_member") and ch["id"] not in exclude_ids:
                channels.append({"id": ch["id"], "name": ch.get("name", ch["id"])})

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return channels


def scan_channel_mentions(
    client: WebClient,
    channel_id: str,
    user_id: str,
    oldest: float,
    latest: float,
    exclude_bots: bool = True,
) -> list[dict]:
    """Scan a channel for top-level messages that mention user_id.

    Returns list of message dicts that contain <@USER_ID> in text.
    """
    mention_pattern = f"<@{user_id}>"
    mentions = []
    cursor = None

    while True:
        resp = client.conversations_history(
            channel=channel_id,
            oldest=str(oldest),
            latest=str(latest),
            limit=200,
            cursor=cursor or "",
        )

        for msg in resp.get("messages", []):
            text = msg.get("text", "")

            # Skip bot messages if configured
            if exclude_bots and (msg.get("bot_id") or msg.get("subtype") == "bot_message"):
                continue

            # Skip self-mentions (user mentioning themselves)
            if msg.get("user") == user_id:
                continue

            if mention_pattern in text:
                mentions.append(msg)

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return mentions


def is_mention_actioned(
    client: WebClient,
    channel_id: str,
    message: dict,
    user_id: str,
) -> bool:
    """Check if a mention has been actioned (replied to or reacted to by user).

    Actioned means:
    1. User has a reaction on the message, OR
    2. User has replied in the thread
    """
    # Check reactions
    reactions = message.get("reactions", [])
    for reaction in reactions:
        if user_id in reaction.get("users", []):
            return True

    # Check thread replies (only if there's a thread)
    thread_ts = message.get("thread_ts") or message.get("ts")
    reply_count = message.get("reply_count", 0)

    if reply_count > 0 or message.get("thread_ts"):
        try:
            resp = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=100,
            )
            for reply in resp.get("messages", []):
                # Skip the parent message itself
                if reply.get("ts") == message.get("ts") and not reply.get("thread_ts"):
                    continue
                if reply.get("user") == user_id:
                    return True
        except SlackApiError:
            pass

    return False


def resolve_user_names(client: WebClient, user_ids: set[str]) -> dict[str, str]:
    """Resolve a set of user IDs to display names."""
    names = {}
    for uid in user_ids:
        try:
            resp = client.users_info(user=uid)
            user = resp.get("user", {})
            profile = user.get("profile", {})
            names[uid] = (
                profile.get("display_name")
                or profile.get("real_name")
                or user.get("name", uid)
            )
        except SlackApiError:
            names[uid] = uid
    return names


def build_slack_deep_link(channel_id: str, message_ts: str) -> str:
    """Build a Slack deep link to a specific message.

    Slack message links use the format: https://slack.com/archives/{channel}/p{ts}
    where ts has the dot removed.
    """
    ts_no_dot = message_ts.replace(".", "")
    return f"https://slack.com/archives/{channel_id}/p{ts_no_dot}"


def truncate_text(text: str, max_length: int = 120) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    # Clean up mention tags for readability
    clean = re.sub(r"<@(\w+)>", r"@\1", text)
    # Remove other Slack formatting noise
    clean = clean.replace("\n", " ").strip()
    if len(clean) > max_length:
        return clean[: max_length - 3] + "..."
    return clean
