"""
Bioworld LinkedIn — Notify Approval Workflow

Posts draft previews to #bioworld-linkedin Slack channel for Ivan's review.
Updates article status from Draft Ready -> Pending Approval.

Usage:
    python3.11 .claude/skills/bioworld-linkedin/workflows/notify_approval.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from notion_dashboard import (
    get_articles_by_status,
    update_article_status,
    extract_article_data,
)

load_dotenv(PROJECT_ROOT / ".env")


def post_approval_request(client: WebClient, channel: str, article: dict) -> bool:
    """Post a single article draft to Slack for approval."""
    notion_url = article.get("notion_url", "")
    company = article.get("company", "Unknown")
    draft = article.get("draft", "No draft available")
    title = article.get("title", "Untitled")
    source_url = article.get("source_url", "")

    # Truncate draft for Slack preview
    draft_preview = draft[:1500] if len(draft) > 1500 else draft

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Draft for Review: {title[:100]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Company:*\n{company}"},
                {"type": "mrkdwn", "text": f"*Source:*\n<{source_url}|Article Link>"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Draft Post:*\n```{draft_preview}```",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Review in Notion:* <{notion_url}|Open in Notion>\n"
                    "Change status to *Approved* or *Rejected* in Notion."
                ),
            },
        },
    ]

    try:
        client.chat_postMessage(
            channel=channel,
            text=f"Draft for review: {title}",
            blocks=blocks,
        )
        return True
    except SlackApiError as e:
        print(f"  ERROR posting to Slack: {e.response['error']}")
        return False


def main():
    notion_key = os.environ.get("BIOWORLD_NOTION_KEY") or os.environ.get("NOTION_KEY")
    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    content_db_id = os.environ.get("BIOWORLD_CONTENT_DB_ID")
    channel = os.environ.get("BIOWORLD_SLACK_CHANNEL", "")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not slack_token:
        missing.append("SLACK_BOT_TOKEN")
    if not content_db_id:
        missing.append("BIOWORLD_CONTENT_DB_ID")
    if not channel:
        missing.append("BIOWORLD_SLACK_CHANNEL")
    if missing:
        print(f"Error: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print("=" * 60)
    print("BIOWORLD LINKEDIN — APPROVAL NOTIFICATION")
    print("=" * 60)

    # Get draft-ready articles
    print("\nFetching Draft Ready articles...")
    pages = get_articles_by_status(notion_key, content_db_id, "Draft Ready")
    print(f"  Found {len(pages)} articles ready for approval")

    if not pages:
        print("\n  No drafts to send for approval. Run generate_drafts.py first.")
        sys.exit(0)

    client = WebClient(token=slack_token)

    # Send summary header
    try:
        client.chat_postMessage(
            channel=channel,
            text=f":memo: *{len(pages)} LinkedIn draft(s) ready for review*\nPlease review in Notion and set status to Approved or Rejected.",
        )
    except SlackApiError as e:
        print(f"ERROR: Could not post to #{channel}: {e.response['error']}")
        sys.exit(1)

    # Post each draft
    notified = 0
    for page in pages:
        article = extract_article_data(page)
        print(f"\n  Notifying: {article['title'][:60]}...")

        if post_approval_request(client, channel, article):
            update_article_status(notion_key, article["page_id"], "Pending Approval")
            notified += 1
            print(f"    Status -> Pending Approval")

    # Summary
    print("\n" + "=" * 60)
    print("NOTIFICATIONS SENT")
    print("=" * 60)
    print(f"  Notified: {notified}/{len(pages)}")
    print(f"  Channel: #{channel}")
    print(f"\nIvan should review in Notion and change status to Approved or Rejected.")
    print(f"Once approved, run publish_approved.py to post to LinkedIn.")


if __name__ == "__main__":
    main()
