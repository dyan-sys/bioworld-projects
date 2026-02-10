"""
Scheduled Update Job Posts Wrapper

Reads posting-plan.json to determine which channels to post for today,
then dispatches to the main update_job_posts workflow with the appropriate
channel filter.

Designed to be called via run-job.sh on a schedule (Mon + Thu at 08:00 SGT).

Usage:
    python3.11 scheduled_update_job_posts.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SKILL_ROOT))

from workflows.update_job_posts import (
    extract_opening_info,
    load_env_keys,
    process_opening,
)
from libraries.notion_helpers import (
    notion_headers,
    query_open_openings,
)

SGT = timezone(timedelta(hours=8))

# Day name -> ISO weekday (Mon=1 .. Sun=7)
DAY_NAME_TO_ISO = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}

OPENINGS_DB_ID = "28c2b7ec45978030be21e73d34d126a0"


def load_posting_plan() -> dict:
    """Load posting-plan.json from templates directory."""
    plan_path = SKILL_ROOT / "templates" / "posting-plan.json"
    with open(plan_path) as f:
        return json.load(f)


def get_scheduled_channels(plan: dict, today_iso_weekday: int) -> list[str]:
    """Return list of channels scheduled for the given ISO weekday."""
    channels = []
    for schedule in plan.get("schedules", []):
        for day_name in schedule.get("days", []):
            if DAY_NAME_TO_ISO.get(day_name.lower()) == today_iso_weekday:
                channels.append(schedule["channel"])
                break
    return channels


def main():
    now_sgt = datetime.now(SGT)
    today_weekday = now_sgt.isoweekday()  # Mon=1 .. Sun=7
    day_name = now_sgt.strftime("%A")

    print("=" * 60)
    print("SCHEDULED JOB POSTS")
    print("=" * 60)
    print(f"Date: {now_sgt.strftime('%Y-%m-%d %H:%M SGT')} ({day_name})")

    # Load posting plan
    plan = load_posting_plan()
    channels = get_scheduled_channels(plan, today_weekday)

    if not channels:
        print(f"\nNo channels scheduled for {day_name}. Nothing to do.")
        return

    print(f"Channels scheduled today: {', '.join(channels)}")

    # Load environment (dotenv already loaded by update_job_posts import)
    print("\nLoading environment...")
    try:
        (notion_key,) = load_env_keys()
    except EnvironmentError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    headers = notion_headers(notion_key)

    # Fetch openings once
    print("Fetching Open openings...")
    try:
        openings = query_open_openings(headers, OPENINGS_DB_ID)
    except Exception as e:
        print(f"ERROR: Could not query openings: {e}")
        sys.exit(1)

    print(f"Found {len(openings)} opening(s)")

    if not openings:
        print("\nNo openings to process.")
        return

    # Process each channel
    total_created = 0
    total_errors = 0

    for channel in channels:
        print(f"\n{'=' * 60}")
        print(f"CHANNEL: {channel}")
        print(f"{'=' * 60}")

        channel_results = []
        for i, opening in enumerate(openings, 1):
            info = extract_opening_info(opening)
            print(f"\n[{i}/{len(openings)}] {info['title']}")
            results = process_opening(headers, opening, channel_filter=channel)
            channel_results.extend(results)

        created = sum(1 for r in channel_results if r["status"] == "success")
        errors = sum(1 for r in channel_results if r["status"] == "error")
        total_created += created
        total_errors += errors
        print(f"\n  {channel}: {created} created, {errors} error(s)")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Channels processed: {', '.join(channels)}")
    print(f"  Total posts created: {total_created}")
    print(f"  Total errors: {total_errors}")


if __name__ == "__main__":
    main()
