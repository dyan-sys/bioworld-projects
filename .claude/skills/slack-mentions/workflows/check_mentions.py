"""
Check Slack Mentions Workflow

Scans all channels the bot is in for unactioned @ mentions of a monitored user,
filters out already-notified and actioned mentions, and sends a DM summary.

Usage:
    python3.11 check_mentions.py
    python3.11 check_mentions.py --dry-run
    python3.11 check_mentions.py --lookback-hours 24
    python3.11 check_mentions.py --user-id U0975UFHDB8
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from mention_scanner import (
    build_slack_deep_link,
    discover_channels,
    get_slack_client,
    is_mention_actioned,
    resolve_user_names,
    scan_channel_mentions,
    truncate_text,
)
from state_manager import (
    is_already_notified,
    load_state,
    mark_notified,
    prune_state,
    save_state,
)

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

SGT = timezone(timedelta(hours=8))
CONFIG_PATH = SKILL_ROOT / "templates" / "mention-config.json"


def load_config() -> dict:
    """Load mention monitoring config."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_time_sgt(ts: str) -> str:
    """Convert Slack timestamp to HH:MM SGT."""
    dt = datetime.fromtimestamp(float(ts), tz=SGT)
    return dt.strftime("%H:%M")


def build_dm_message(
    grouped_mentions: dict[str, list[dict]],
    user_names: dict[str, str],
    max_preview: int,
) -> str:
    """Build the DM message grouped by channel.

    grouped_mentions: {channel_name: [mention_dicts]}
    Each mention_dict has: ts, user, text, channel_id, channel_name
    """
    now_sgt = datetime.now(SGT)
    header = f"*Unactioned Mentions* | {now_sgt.strftime('%b %d, %Y %H:%M')} SGT"

    sections = [header, ""]
    total = 0

    for channel_name in sorted(grouped_mentions.keys()):
        mentions = grouped_mentions[channel_name]
        count = len(mentions)
        total += count
        sections.append(f"*#{channel_name}* ({count} mention{'s' if count != 1 else ''})")

        for m in sorted(mentions, key=lambda x: float(x["ts"])):
            time_str = format_time_sgt(m["ts"])
            sender = user_names.get(m["user"], m["user"])
            preview = truncate_text(m["text"], max_preview)
            link = build_slack_deep_link(m["channel_id"], m["ts"])
            sections.append(f"  [{time_str}] {sender}: {preview} (<{link}|View>)")

        sections.append("")

    sections.append("---")
    channel_count = len(grouped_mentions)
    sections.append(
        f"{total} unactioned mention{'s' if total != 1 else ''} "
        f"across {channel_count} channel{'s' if channel_count != 1 else ''}"
    )

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(
        description="Scan Slack channels for unactioned @ mentions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without sending DM",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=None,
        help="Override lookback window in hours (default: from config)",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Override monitored user ID (default: from config)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SLACK MENTION MONITOR")
    print("=" * 60)

    # Phase 1: Load config and state
    print("\n[1/4] Loading config and state...")

    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    if not slack_token:
        print("  ERROR: Missing SLACK_BOT_TOKEN environment variable")
        sys.exit(1)

    config = load_config()
    user_id = args.user_id or config["monitored_user_id"]
    lookback_hours = args.lookback_hours or config["lookback_hours"]
    max_preview = config.get("max_preview_length", 120)
    exclude_bots = config.get("exclude_bot_messages", True)
    channel_types = config.get("channel_types", "public_channel")
    exclude_channels = config.get("exclude_channels", [])

    state_path = PROJECT_ROOT / config["state_file"]
    state = load_state(state_path)
    retention = config.get("state_retention_hours", 48)
    state = prune_state(state, retention)

    old_count = len(state.get("notified", {}))
    print(f"  Monitored user: {user_id}")
    print(f"  Lookback: {lookback_hours}h")
    print(f"  State entries: {old_count} (after pruning >{retention}h)")
    if args.dry_run:
        print("  Mode: DRY RUN (no DM will be sent)")

    # Phase 2: Discover channels and scan for mentions
    print("\n[2/4] Discovering channels and scanning mentions...")
    client = get_slack_client()
    channels = discover_channels(client, channel_types, exclude_channels)
    print(f"  Found {len(channels)} channels")

    now = datetime.now(SGT)
    oldest = (now - timedelta(hours=lookback_hours)).timestamp()
    latest = now.timestamp()

    all_mentions = []  # list of (channel_info, message) tuples
    for ch in channels:
        try:
            mentions = scan_channel_mentions(
                client, ch["id"], user_id, oldest, latest, exclude_bots
            )
            if mentions:
                print(f"  #{ch['name']}: {len(mentions)} mention(s)")
                for m in mentions:
                    all_mentions.append((ch, m))
            # Don't log zero-mention channels to keep output clean
        except Exception as e:
            print(f"  #{ch['name']}: ERROR - {e}")

    print(f"  Total raw mentions: {len(all_mentions)}")

    # Phase 3: Filter actioned and already-notified, build DM
    print("\n[3/4] Filtering and building message...")

    skipped_actioned = 0
    skipped_notified = 0
    unactioned = []

    for ch, msg in all_mentions:
        ts = msg.get("ts", "")

        # Skip already notified
        if is_already_notified(state, ch["id"], ts):
            skipped_notified += 1
            continue

        # Check if actioned (has reaction or thread reply from user)
        if is_mention_actioned(client, ch["id"], msg, user_id):
            skipped_actioned += 1
            continue

        unactioned.append({
            "ts": ts,
            "user": msg.get("user", ""),
            "text": msg.get("text", ""),
            "channel_id": ch["id"],
            "channel_name": ch["name"],
        })

    print(f"  Skipped (already notified): {skipped_notified}")
    print(f"  Skipped (actioned): {skipped_actioned}")
    print(f"  Unactioned mentions: {len(unactioned)}")

    if not unactioned:
        now_sgt = datetime.now(SGT)
        channel_list = ", ".join(f"#{ch['name']}" for ch in sorted(channels, key=lambda c: c["name"]))
        all_clear_text = (
            f"As of {now_sgt.strftime('%b %d, %Y %H:%M')} SGT — "
            f"you're all caught up! No unactioned mentions across {len(channels)} channels.\n\n"
            f"_Monitoring: {channel_list}_"
        )
        print(f"\n  {all_clear_text}")

        if args.dry_run:
            print("  DRY RUN: Skipping DM send.")
        else:
            try:
                client.chat_postMessage(channel=user_id, text=all_clear_text, mrkdwn=True)
                print("  All-clear DM sent.")
            except Exception as e:
                print(f"  ERROR sending DM: {e}")

        state["last_run"] = now_sgt.isoformat()
        save_state(state, state_path)
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Channels scanned: {len(channels)}")
        print(f"  Unactioned mentions: 0")
        return

    # Resolve sender names
    sender_ids = {m["user"] for m in unactioned}
    user_names = resolve_user_names(client, sender_ids)

    # Group by channel
    grouped: dict[str, list[dict]] = {}
    for m in unactioned:
        grouped.setdefault(m["channel_name"], []).append(m)

    dm_text = build_dm_message(grouped, user_names, max_preview)

    # Print preview
    print()
    print(dm_text)

    # Phase 4: Send DM and update state
    print(f"\n[4/4] Sending DM to {user_id}...")

    if args.dry_run:
        print("  DRY RUN: Skipping DM send.")
    else:
        try:
            client.chat_postMessage(channel=user_id, text=dm_text, mrkdwn=True)
            print("  DM sent successfully.")
        except Exception as e:
            print(f"  ERROR sending DM: {e}")

    # Update state with newly notified mentions
    for m in unactioned:
        sender_name = user_names.get(m["user"], m["user"])
        mark_notified(
            state,
            m["channel_id"],
            m["ts"],
            m["channel_name"],
            sender_name,
            truncate_text(m["text"], max_preview),
        )

    state["last_run"] = datetime.now(SGT).isoformat()
    save_state(state, state_path)
    print(f"  State saved ({len(state['notified'])} entries)")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Channels scanned: {len(channels)}")
    print(f"  Unactioned mentions: {len(unactioned)}")
    print(f"  Channels with mentions: {len(grouped)}")


if __name__ == "__main__":
    main()
