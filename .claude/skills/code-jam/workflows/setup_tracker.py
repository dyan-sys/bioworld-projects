"""
Setup: Claude Code Jam — Project Tracker
Creates a Notion database to track EA progress across Code Jam sessions.

Usage:
    python3 .claude/skills/ally-bot/workflows/setup_code_jam_tracker.py --parent-id <notion_page_id>

The parent page ID can be copied from any Notion page URL:
    https://www.notion.so/Page-Title-<PAGE_ID>
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# EAs to pre-populate (edit as needed)
EA_NAMES = [
    "EA 1",
    "EA 2",
    "EA 3",
    "EA 4",
    "EA 5",
    "EA 6",
    "EA 7",
    "EA 8",
    "EA 9",
]


def headers() -> dict:
    key = os.environ.get("NOTION_KEY")
    if not key:
        print("Error: NOTION_KEY not set in .env")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_database(parent_page_id: str) -> dict:
    """Create the Claude Code Jam tracker database."""
    url = f"{NOTION_API_BASE}/databases"

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🧩"},
        "title": [
            {
                "type": "text",
                "text": {"content": "Claude Code Jam — Project Tracker"},
            }
        ],
        "properties": {
            "EA Name": {"title": {}},
            "Project / Idea": {"rich_text": {}},
            "Jam Session": {
                "select": {
                    "options": [
                        {"name": "Jam 1", "color": "purple"},
                        {"name": "Jam 2", "color": "blue"},
                        {"name": "Jam 3", "color": "green"},
                        {"name": "Jam 4", "color": "yellow"},
                        {"name": "Jam 5", "color": "orange"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "Not Started", "color": "default"},
                        {"name": "Trying", "color": "yellow"},
                        {"name": "Stuck", "color": "red"},
                        {"name": "Got Help", "color": "blue"},
                        {"name": "Done ✅", "color": "green"},
                    ]
                }
            },
            "What They Tried": {"rich_text": {}},
            "Where They're Stuck": {"rich_text": {}},
            "Next Step": {"rich_text": {}},
            "Notes": {"rich_text": {}},
        },
    }

    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    if not resp.ok:
        print(f"Error creating database: {resp.status_code} {resp.text}")
        sys.exit(1)

    return resp.json()


def add_ea_row(db_id: str, ea_name: str, jam_session: str = "Jam 1") -> dict:
    """Add one EA row to the tracker database."""
    url = f"{NOTION_API_BASE}/pages"

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "EA Name": {
                "title": [{"type": "text", "text": {"content": ea_name}}]
            },
            "Jam Session": {"select": {"name": jam_session}},
            "Status": {"select": {"name": "Not Started"}},
        },
    }

    resp = requests.post(url, headers=headers(), json=payload, timeout=30)
    if not resp.ok:
        print(f"  Warning: could not add row for {ea_name}: {resp.status_code}")
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Create Claude Code Jam tracker in Notion")
    parser.add_argument(
        "--parent-id",
        required=True,
        help="Notion page ID where the database will be created",
    )
    parser.add_argument(
        "--jam",
        default="Jam 1",
        help="Which jam session to pre-populate (default: Jam 1)",
    )
    parser.add_argument(
        "--no-rows",
        action="store_true",
        help="Create database structure only, skip pre-populating EA rows",
    )
    args = parser.parse_args()

    parent_id = args.parent_id.replace("-", "").strip()

    print("Creating Claude Code Jam tracker database...")
    db = create_database(parent_id)
    db_id = db["id"]
    db_url = db.get("url", f"https://notion.so/{db_id.replace('-', '')}")

    print(f"✅ Database created: {db_url}")

    if not args.no_rows:
        print(f"\nPre-populating {len(EA_NAMES)} EA rows for {args.jam}...")
        for name in EA_NAMES:
            add_ea_row(db_id, name, args.jam)
            print(f"  ✅ {name}")

    print(f"\nDone! Open your tracker here:\n{db_url}")


if __name__ == "__main__":
    main()
