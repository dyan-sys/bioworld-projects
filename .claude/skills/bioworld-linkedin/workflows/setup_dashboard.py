"""
Setup: Bioworld LinkedIn — Content Hub

One-time script to create the Notion dashboard:
  1. Parent page under a given Notion page
  2. Content Pipeline database (article workflow)
  3. Portfolio Brands database (company tracking)
  4. Seeds 12 portfolio companies

Usage:
    python3.11 .claude/skills/bioworld-linkedin/workflows/setup_dashboard.py \\
        --parent-id <notion_page_id>

After running, add the printed database IDs to your .env:
    BIOWORLD_CONTENT_DB_ID=...
    BIOWORLD_BRANDS_DB_ID=...
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from notion_dashboard import (
    create_parent_page,
    create_content_db,
    create_brands_db,
    seed_brands,
)

load_dotenv(PROJECT_ROOT / ".env")


def main():
    parser = argparse.ArgumentParser(
        description="Create Bioworld LinkedIn Content Hub in Notion"
    )
    parser.add_argument(
        "--parent-id",
        required=True,
        help="Notion page ID where the dashboard will be created",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Create databases only, skip seeding portfolio companies",
    )
    args = parser.parse_args()

    api_key = os.environ.get("BIOWORLD_NOTION_KEY") or os.environ.get("NOTION_KEY")
    if not api_key:
        print("Error: NOTION_KEY not set in .env")
        sys.exit(1)

    parent_id = args.parent_id.replace("-", "").strip()

    # Step 1: Create parent page
    print("Creating parent page: Bioworld LinkedIn — Content Hub...")
    parent_page = create_parent_page(api_key, parent_id)
    hub_page_id = parent_page["id"]
    hub_url = parent_page.get("url", f"https://notion.so/{hub_page_id.replace('-', '')}")
    print(f"  Page created: {hub_url}")

    # Step 2: Create Content Pipeline database
    print("\nCreating Content Pipeline database...")
    content_db = create_content_db(api_key, hub_page_id)
    content_db_id = content_db["id"]
    print(f"  Content Pipeline DB: {content_db_id}")

    # Step 3: Create Portfolio Brands database
    print("\nCreating Portfolio Brands database...")
    brands_db = create_brands_db(api_key, hub_page_id)
    brands_db_id = brands_db["id"]
    print(f"  Portfolio Brands DB: {brands_db_id}")

    # Step 4: Seed portfolio companies
    if not args.no_seed:
        print("\nSeeding portfolio companies...")
        seed_brands(api_key, brands_db_id)

    # Print env vars
    print("\n" + "=" * 60)
    print("Add these to your .env file:")
    print(f"  BIOWORLD_CONTENT_DB_ID={content_db_id.replace('-', '')}")
    print(f"  BIOWORLD_BRANDS_DB_ID={brands_db_id.replace('-', '')}")
    print("=" * 60)
    print(f"\nDashboard: {hub_url}")
    print("\nNext steps:")
    print("  1. Open the dashboard in Notion")
    print("  2. Create filtered views (tabs) on the Content Pipeline:")
    print("     - This Week: filter by Week = current week")
    print("     - Pending Approval: filter by Status = Pending Approval")
    print("     - Published: filter by Status = Published")
    print("     - All Articles: no filter, sort by Discovered Date desc")
    print("  3. Add LinkedIn URLs to each brand in Portfolio Brands")


if __name__ == "__main__":
    main()
