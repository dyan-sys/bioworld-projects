"""
Flag EP Issues Workflow

Reviews EP Slack channel conversations for the previous day, sends a batched
analysis request to Kimi (Moonshot AI), and posts flagged issues to #ally-jarvis.

Usage:
    python3.11 flag_ep_issues.py
    python3.11 flag_ep_issues.py --date 2026-02-09
    python3.11 flag_ep_issues.py --channel C0XXXXXX
    python3.11 flag_ep_issues.py --dry-run
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
from kimi_analyzer import analyze_via_kimi, build_prompt, parse_json_response
from report_builder import build_report, post_to_slack
from slack_reader import format_conversations, get_slack_client

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

SGT = timezone(timedelta(hours=8))
DATA_DIR = PROJECT_ROOT / "local-data" / "talent" / "ep_reviews"
REGISTRY_PATH = SKILL_ROOT / "templates" / "channel-registry.json"


def load_channel_registry(channel_filter: str = None) -> list[dict]:
    """Load channel registry, optionally filtering to a single channel."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)

    channels = registry.get("channels", [])

    if channel_filter:
        channels = [c for c in channels if c["id"] == channel_filter]
        if not channels:
            raise ValueError(
                f"Channel {channel_filter} not found in registry. "
                f"Available: {[c['id'] for c in registry.get('channels', [])]}"
            )

    return channels


def get_yesterday_sgt() -> str:
    """Return yesterday's date in YYYY-MM-DD format (SGT)."""
    now_sgt = datetime.now(SGT)
    yesterday = now_sgt - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(
        description="Review EP Slack channels and flag issues via Kimi AI"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD format (default: yesterday in SGT)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Process a single channel by Slack channel ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without posting to Slack",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("EP CHANNEL ISSUE FLAGGING")
    print("=" * 60)

    # Ensure output directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Load environment
    print("\n[1/4] Loading environment...")
    moonshot_key = os.environ.get("MOONSHOT_API_KEY_EP") or os.environ.get("MOONSHOT_API_KEY")
    slack_token = os.environ.get("SLACK_BOT_TOKEN")

    missing = []
    if not moonshot_key:
        missing.append("MOONSHOT_API_KEY")
    if not slack_token:
        missing.append("SLACK_BOT_TOKEN")
    if missing:
        print(f"  ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    print("  MOONSHOT_API_KEY and SLACK_BOT_TOKEN loaded.")

    # Load channel registry
    try:
        channels = load_channel_registry(args.channel)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    date_str = args.date or get_yesterday_sgt()
    print(f"  Target date: {date_str}")
    print(f"  Channels: {len(channels)} ({', '.join(c['name'] for c in channels)})")
    if args.dry_run:
        print("  Mode: DRY RUN (no Slack posting)")

    # Phase 2: Read Slack conversations
    print("\n[2/4] Reading Slack conversations...")
    client = get_slack_client()
    transcripts = []

    for ch in channels:
        print(f"  [{ch['name']}] Fetching messages for {date_str}...")
        try:
            transcript = format_conversations(
                client, ch["id"], ch["name"], date_str
            )
            transcripts.append(transcript)
            msg_count = transcript.count("\n") - 2  # rough line count minus header/footer
            if "[No messages]" in transcript:
                print(f"  [{ch['name']}] No messages found")
            else:
                print(f"  [{ch['name']}] ~{msg_count} lines of conversation")
        except Exception as e:
            print(f"  [{ch['name']}] ERROR: {e}")
            transcripts.append(
                f"=== {ch['name']} ({date_str}) ===\n[Error fetching messages: {e}]\n"
            )

    # Phase 3: Analyze via Kimi
    print("\n[3/4] Analyzing via Kimi AI...")
    prompt = build_prompt(date_str, transcripts)
    print(f"  Prompt length: {len(prompt)} chars")

    raw_response = analyze_via_kimi(prompt, moonshot_key)
    analysis = parse_json_response(raw_response)

    # Save raw artifacts
    review_path = DATA_DIR / f"{date_str}_review.json"
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump({"raw_response": raw_response, "parsed": analysis}, f, indent=2)
    print(f"  Review saved to: {review_path.relative_to(PROJECT_ROOT)}")

    # Phase 4: Build report and post
    print("\n[4/4] Building report...")
    now_sgt = datetime.now(SGT)
    report = build_report(analysis, now_sgt)

    # Save report
    report_path = DATA_DIR / f"{date_str}_report.txt"
    report_path.write_text(report)
    print(f"  Report saved to: {report_path.relative_to(PROJECT_ROOT)}")

    # Print report
    print()
    print(report)

    # Post to Slack
    if args.dry_run:
        print("DRY RUN: Skipping Slack post.")
    else:
        post_to_slack(report)

    # Summary
    channel_results = analysis.get("channels", [])
    flagged = sum(1 for c in channel_results if c.get("status") == "FLAG")
    ok = sum(1 for c in channel_results if c.get("status") == "OK")
    no_act = sum(1 for c in channel_results if c.get("status") == "NO_ACTIVITY")

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Flagged:     {flagged}")
    print(f"  OK:          {ok}")
    print(f"  No Activity: {no_act}")


if __name__ == "__main__":
    main()
