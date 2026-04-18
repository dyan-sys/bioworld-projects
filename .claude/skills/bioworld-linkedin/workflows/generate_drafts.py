"""
Bioworld LinkedIn — Generate Drafts Workflow

Phase 3: Generate LinkedIn post drafts for all Shortlisted articles.

Usage:
    python3.11 .claude/skills/bioworld-linkedin/workflows/generate_drafts.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from draft_generator import generate_draft
from notion_dashboard import (
    get_articles_by_status,
    update_article_draft,
    extract_article_data,
)

load_dotenv(PROJECT_ROOT / ".env")

HKT = timezone(timedelta(hours=8))


def current_week() -> str:
    now = datetime.now(HKT)
    return f"{now.year}-W{now.isocalendar()[1]:02d}"


def main():
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")
    notion_key = os.environ.get("NOTION_KEY")
    content_db_id = os.environ.get("BIOWORLD_CONTENT_DB_ID")

    missing = []
    if not moonshot_key:
        missing.append("MOONSHOT_API_KEY")
    if not notion_key:
        missing.append("NOTION_KEY")
    if not content_db_id:
        missing.append("BIOWORLD_CONTENT_DB_ID")
    if missing:
        print(f"Error: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    week_str = current_week()

    print("=" * 60)
    print("BIOWORLD LINKEDIN — DRAFT GENERATOR")
    print("=" * 60)
    print(f"  Week: {week_str}")

    # Get shortlisted articles
    print("\nFetching shortlisted articles...")
    pages = get_articles_by_status(notion_key, content_db_id, "Shortlisted")
    print(f"  Found {len(pages)} shortlisted articles")

    if not pages:
        print("\n  No shortlisted articles to draft. Run scan_news.py first.")
        sys.exit(0)

    # Generate drafts
    drafted = 0
    for page in pages:
        article = extract_article_data(page)
        print(f"\n--- Drafting: {article['title'][:60]} ---")

        draft_text = generate_draft(article, moonshot_key)

        if draft_text:
            update_article_draft(notion_key, article["page_id"], draft_text)
            drafted += 1
            print(f"  Draft saved ({len(draft_text)} chars)")

            # Preview
            preview = draft_text[:200] + "..." if len(draft_text) > 200 else draft_text
            print(f"\n  Preview:\n  {preview}")
        else:
            print("  WARNING: Empty draft generated, skipping.")

    # Summary
    print("\n" + "=" * 60)
    print("DRAFTS COMPLETE")
    print("=" * 60)
    print(f"  Drafted: {drafted}/{len(pages)}")
    print(f"\nNext: Run notify_approval.py to send to #bioworld-linkedin for Ivan's review.")


if __name__ == "__main__":
    main()
