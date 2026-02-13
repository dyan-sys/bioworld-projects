"""
Daily Pepper — Morning Calendar Summary Bot

Fetches today's Google Calendar events and sends a simple overview as a Slack DM.

Usage:
    python3.11 daily_pepper.py
    python3.11 daily_pepper.py --dry-run
    python3.11 daily_pepper.py --date 2026-02-14
    python3.11 daily_pepper.py --dry-run --date 2026-02-14
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
from calendar_auth import get_calendar_service
from calendar_reader import compute_free_blocks, fetch_todays_events
from linear_reader import get_focus_board

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

SGT = timezone(timedelta(hours=8))
CONFIG_PATH = SKILL_ROOT / "templates" / "pepper-config.json"


def load_config() -> dict:
    """Load Daily Pepper config."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_time(dt: datetime) -> str:
    """Format datetime as HH:MM."""
    return dt.strftime("%H:%M")


def build_summary(
    events: list[dict],
    target_date: datetime,
    show_free_blocks: bool = True,
    work_start: int = 9,
    work_end: int = 18,
) -> str:
    """Build the Slack DM message from events."""
    day_label = target_date.strftime("%a, %b %d %Y")
    lines = [f":sunny: *Daily Pepper* | {day_label}", ""]

    if not events:
        lines.append("No events on your calendar today. Wide open!")
        return "\n".join(lines)

    count = len(events)
    lines.append(f":clipboard: {count} event{'s' if count != 1 else ''} today")
    lines.append("")

    for ev in events:
        if ev["is_all_day"]:
            time_col = "All day"
        else:
            time_col = f"{format_time(ev['start'])} - {format_time(ev['end'])}"

        title = ev["title"]
        if ev.get("location"):
            title += f" -- {ev['location']}"

        lines.append(f"  {time_col}  {title}")

    if show_free_blocks:
        free = compute_free_blocks(events, work_start, work_end, target_date)
        if free:
            lines.append("")
            blocks_str = ", ".join(
                f"{s}-{e}" if e != "onwards" else f"{s} onwards" for s, e in free
            )
            lines.append(f":clock1: Free blocks: {blocks_str}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Daily Pepper — morning calendar summary bot"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview summary without sending Slack DM",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD format (default: today SGT)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("DAILY PEPPER")
    print("=" * 60)

    # Phase 1: Config + Auth
    print("\n[1/5] Loading config and authenticating...")

    config = load_config()
    slack_user_id = config["slack_user_id"]
    calendar_ids = config.get("calendar_ids", ["primary"])
    work_hours = config.get("work_hours", {"start": 9, "end": 18})
    show_free_blocks = config.get("show_free_blocks", True)

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=SGT)
    else:
        target_date = datetime.now(SGT)

    print(f"  Target date: {target_date.strftime('%Y-%m-%d')} SGT")
    print(f"  Calendars: {', '.join(calendar_ids)}")
    if args.dry_run:
        print("  Mode: DRY RUN (no DM will be sent)")

    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    if not slack_token and not args.dry_run:
        print("  ERROR: Missing SLACK_BOT_TOKEN environment variable")
        sys.exit(1)

    service = get_calendar_service()
    print("  Google Calendar authenticated.")

    # Phase 2: Fetch events
    print("\n[2/5] Fetching calendar events...")

    events = fetch_todays_events(service, calendar_ids, target_date)
    print(f"  Found {len(events)} event(s)")

    for ev in events:
        if ev["is_all_day"]:
            print(f"    [All day] {ev['title']}")
        else:
            print(f"    [{format_time(ev['start'])}-{format_time(ev['end'])}] {ev['title']}")

    # Phase 3: Fetch Linear issues
    print("\n[3/5] Fetching Linear focus board...")

    linear_section = ""
    linear_team_id = config.get("linear_team_id")
    linear_api_key = os.environ.get("LINEAR_API_KEY")

    if not linear_team_id:
        print("  Skipped: no linear_team_id in config")
    elif not linear_api_key:
        print("  Skipped: LINEAR_API_KEY not set")
    else:
        try:
            linear_section = get_focus_board(linear_team_id, linear_api_key)
            if linear_section:
                print("  Focus board loaded.")
            else:
                print("  No issues matched (both buckets empty).")
        except Exception as e:
            print(f"  WARNING: Linear fetch failed: {e}")

    # Phase 4: Build summary
    print("\n[4/5] Building summary message...")

    message = build_summary(
        events,
        target_date,
        show_free_blocks=show_free_blocks,
        work_start=work_hours["start"],
        work_end=work_hours["end"],
    )

    if linear_section:
        message += "\n" + linear_section

    print()
    print(message)

    # Phase 5: Send DM
    print(f"\n[5/5] Sending DM to {slack_user_id}...")

    if args.dry_run:
        print("  DRY RUN: Skipping DM send.")
    else:
        from slack_sdk import WebClient

        client = WebClient(token=slack_token)
        try:
            client.chat_postMessage(
                channel=slack_user_id, text=message, mrkdwn=True
            )
            print("  DM sent successfully.")
        except Exception as e:
            print(f"  ERROR sending DM: {e}")
            sys.exit(1)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Date: {target_date.strftime('%Y-%m-%d')}")
    print(f"  Events: {len(events)}")
    all_day = sum(1 for e in events if e["is_all_day"])
    timed = len(events) - all_day
    print(f"  All-day: {all_day}, Timed: {timed}")
    if args.dry_run:
        print("  DM: skipped (dry run)")
    else:
        print("  DM: sent")


if __name__ == "__main__":
    main()
