"""
Bioworld LinkedIn — Publish Approved Workflow

Phase 4: Posts Ivan-approved articles to the Bioworld Ventures LinkedIn
company page via API, then updates Notion status to Published.

Usage:
    python3.11 .claude/skills/bioworld-linkedin/workflows/publish_approved.py
    python3.11 .claude/skills/bioworld-linkedin/workflows/publish_approved.py --dry-run

Requires LinkedIn API credentials in .env:
    LINKEDIN_ACCESS_TOKEN, LINKEDIN_REFRESH_TOKEN,
    LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET,
    BIOWORLD_LINKEDIN_ORG_ID
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from linkedin_publisher import publish_post, refresh_access_token, get_linkedin_config
from notion_dashboard import (
    get_articles_by_status,
    update_article_status,
    extract_article_data,
)

load_dotenv(PROJECT_ROOT / ".env")

HKT = timezone(timedelta(hours=8))


def main():
    parser = argparse.ArgumentParser(description="Publish approved posts to LinkedIn")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be posted without publishing")
    args = parser.parse_args()

    notion_key = os.environ.get("NOTION_KEY")
    content_db_id = os.environ.get("BIOWORLD_CONTENT_DB_ID")
    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("BIOWORLD_SLACK_CHANNEL", "")

    if not notion_key or not content_db_id:
        print("Error: Missing NOTION_KEY or BIOWORLD_CONTENT_DB_ID")
        sys.exit(1)

    linkedin = get_linkedin_config()

    if not args.dry_run:
        if not linkedin["access_token"] or not linkedin["org_id"]:
            print("Error: Missing LinkedIn API credentials.")
            print("  Required: LINKEDIN_ACCESS_TOKEN, BIOWORLD_LINKEDIN_ORG_ID")
            print("  Run with --dry-run to preview without posting.")
            sys.exit(1)

    print("=" * 60)
    print("BIOWORLD LINKEDIN — PUBLISH APPROVED")
    if args.dry_run:
        print("  MODE: DRY RUN (no actual posting)")
    print("=" * 60)

    # Get approved articles
    print("\nFetching approved articles...")
    pages = get_articles_by_status(notion_key, content_db_id, "Approved")
    print(f"  Found {len(pages)} approved articles")

    if not pages:
        print("\n  No approved articles to publish.")
        # Notify on Slack if channel is configured
        if slack_token and channel and not args.dry_run:
            try:
                from slack_sdk import WebClient
                client = WebClient(token=slack_token)
                client.chat_postMessage(
                    channel=channel,
                    text=":information_source: No approved posts this week. Approve articles in Notion to publish next Tuesday.",
                )
            except Exception:
                pass
        sys.exit(0)

    # Try to refresh token if we have refresh credentials
    if not args.dry_run and linkedin["refresh_token"] and linkedin["client_id"]:
        print("\nRefreshing LinkedIn access token...")
        refresh_result = refresh_access_token(
            linkedin["client_id"],
            linkedin["client_secret"],
            linkedin["refresh_token"],
        )
        if refresh_result["success"]:
            linkedin["access_token"] = refresh_result["access_token"]
            print("  Token refreshed successfully")
        else:
            print(f"  Token refresh failed: {refresh_result.get('error', 'unknown')}")
            print("  Proceeding with existing token...")

    # Publish each approved article
    published = 0
    failed = 0
    now_str = datetime.now(HKT).strftime("%Y-%m-%d %H:%M HKT")

    for page in pages:
        article = extract_article_data(page)
        draft = article.get("draft", "")

        if not draft:
            print(f"\n  SKIP: No draft text for '{article['title'][:60]}'")
            continue

        print(f"\n--- Publishing: {article['title'][:60]} ---")
        print(f"  Company: {article['company']}")
        print(f"  Draft length: {len(draft)} chars")

        if args.dry_run:
            print(f"\n  [DRY RUN] Would post:\n  {draft[:200]}...")
            published += 1
            continue

        result = publish_post(linkedin["access_token"], linkedin["org_id"], draft)

        if result["success"]:
            published += 1
            post_id = result.get("post_id", "")
            print(f"  Published! Post ID: {post_id}")

            # Update Notion
            extra_props = {
                "Notes": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"Published {now_str}"}}
                    ]
                }
            }
            update_article_status(notion_key, article["page_id"], "Published", extra_props)

            # Notify Slack
            if slack_token and channel:
                try:
                    from slack_sdk import WebClient
                    client = WebClient(token=slack_token)
                    client.chat_postMessage(
                        channel=channel,
                        text=f":white_check_mark: *Posted to LinkedIn:* {article['title']}\nCompany: {article['company']}\nPublished: {now_str}",
                    )
                except Exception:
                    pass
        else:
            failed += 1
            error = result.get("error", "Unknown error")
            print(f"  FAILED: {result.get('status')} — {error}")

            # Notify Slack of failure
            if slack_token and channel:
                try:
                    from slack_sdk import WebClient
                    client = WebClient(token=slack_token)
                    client.chat_postMessage(
                        channel=channel,
                        text=f":x: *Failed to post to LinkedIn:* {article['title']}\nError: {error}",
                    )
                except Exception:
                    pass

    # Summary
    print("\n" + "=" * 60)
    print("PUBLISH COMPLETE" if not args.dry_run else "DRY RUN COMPLETE")
    print("=" * 60)
    print(f"  Published: {published}")
    print(f"  Failed: {failed}")
    if not args.dry_run:
        print(f"  Check LinkedIn: https://www.linkedin.com/company/bioworld-ventures/")


if __name__ == "__main__":
    main()
