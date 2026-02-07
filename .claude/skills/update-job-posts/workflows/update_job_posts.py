"""
Update Job Posts Workflow

Creates job post pages in the Job Posts DB for each Open opening
in the Ally Openings DB, one post per Post Channel.

Usage:
    # Batch mode: process all Open openings
    python3.11 update_job_posts.py

    # Single opening
    python3.11 update_job_posts.py --opening-id <notion_page_id>

    # Dry run (preview without creating)
    python3.11 update_job_posts.py --dry-run
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.notion_helpers import (
    append_blocks,
    create_page,
    fetch_page,
    notion_headers,
    query_open_openings,
    update_page_properties,
)
from libraries.template_registry import get_template

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Database IDs
OPENINGS_DB_ID = "28c2b7ec45978030be21e73d34d126a0"
JOB_POSTS_DB_ID = "28c2b7ec459780c6a4b6c047caf8c5fe"


def load_env_keys() -> tuple[str]:
    """Load required environment variables."""
    notion_key = os.environ.get("NOTION_KEY")
    if not notion_key:
        raise EnvironmentError("Missing required environment variable: NOTION_KEY")
    return (notion_key,)


def _get_rich_text(properties: dict, prop_name: str) -> str | None:
    """Extract plain text from a rich_text property, or None if empty."""
    prop = properties.get(prop_name, {})
    if prop.get("type") == "rich_text":
        items = prop.get("rich_text", [])
        if items:
            return items[0].get("plain_text", "").strip() or None
    return None


def extract_opening_info(page: dict) -> dict:
    """
    Extract opening prefix, job code, channels, and metadata from an Openings DB page.

    Title format: "251003-EP Executive Partner (Rolling)"
    Prefix: "251003-EP"
    Job code: "EP"
    """
    properties = page.get("properties", {})

    # Get title from "Opening ID & Name"
    title = ""
    title_prop = properties.get("Opening ID & Name", {})
    if title_prop.get("type") == "title":
        title_items = title_prop.get("title", [])
        if title_items:
            title = title_items[0].get("plain_text", "")

    # Extract prefix and job code
    # "251003-EP Executive Partner (Rolling)" -> prefix="251003-EP", job_code="EP"
    parts = title.split(" ", 1)
    prefix = parts[0] if parts else ""
    job_code = prefix.rsplit("-", 1)[-1] if "-" in prefix else prefix

    # Get Post Channels (multi_select)
    channels = []
    channels_prop = properties.get("Post Channels", {})
    if channels_prop.get("type") == "multi_select":
        for option in channels_prop.get("multi_select", []):
            channels.append(option.get("name", ""))

    # Get Opening Base In-Take Form URL (rich_text in DB1)
    intake_form_url = _get_rich_text(properties, "Opening Base In-Take Form")

    # Additional fields for template variables
    job_title = _get_rich_text(properties, "Job Title")
    employment_type = _get_rich_text(properties, "Employment Type")
    advertised_range = _get_rich_text(properties, "Advertised Range")
    target_collab_window = _get_rich_text(properties, "Target Collaboration Window")

    return {
        "page_id": page.get("id"),
        "title": title,
        "prefix": prefix,
        "job_code": job_code,
        "channels": channels,
        "intake_form_url": intake_form_url,
        "job_title": job_title,
        "employment_type": employment_type,
        "advertised_range": advertised_range,
        "target_collab_window": target_collab_window,
    }


def create_job_post(
    headers: dict,
    opening_info: dict,
    channel: str,
    dry_run: bool = False,
) -> dict:
    """
    Create a single job post page in the Job Posts DB.

    Sequence: create page (properties only) → set Post ID → compute
    submission URL → load template with variables → append body blocks
    → read GEN PostID → update title.

    Returns dict with status info.
    """
    prefix = opening_info["prefix"]
    job_code = opening_info["job_code"]
    intake_form_url = opening_info.get("intake_form_url")

    result = {
        "channel": channel,
        "status": "pending",
        "page_id": None,
        "title": None,
        "error": None,
    }

    placeholder_title = f"{prefix}-{channel}-NEW"

    if dry_run:
        result["status"] = "dry_run"
        result["title"] = placeholder_title
        print(f"    [DRY RUN] Would create: {placeholder_title}")
        # Show template variables that would be used
        for field in ("job_title", "employment_type", "advertised_range", "target_collab_window"):
            val = opening_info.get(field)
            if val:
                print(f"    [DRY RUN] {field}: {val}")
        return result

    try:
        # Step 1: Create page — properties only, NO children
        payload = {
            "parent": {"database_id": JOB_POSTS_DB_ID},
            "properties": {
                "Job Post Title": {
                    "title": [{"text": {"content": placeholder_title}}],
                },
                "Opening": {
                    "relation": [{"id": opening_info["page_id"]}],
                },
                "Post Channel": {
                    "select": {"name": channel},
                },
                "Status": {
                    "status": {"name": "Drafting"},
                },
            },
        }

        if intake_form_url:
            payload["properties"]["Opening Base In-take form"] = {
                "url": intake_form_url,
            }
            print(f"    [INTAKE] Set form URL: {intake_form_url}")

        print(f"    [CREATE] Creating page...")
        created_page = create_page(headers, payload)
        new_page_id = created_page["id"]
        result["page_id"] = new_page_id
        print(f"    [CREATE] Page created: {new_page_id}")

        # Step 2: Set Post ID (page ID without dashes)
        post_id_value = new_page_id.replace("-", "")
        update_page_properties(headers, new_page_id, {
            "Post ID": {
                "rich_text": [{"text": {"content": post_id_value}}],
            },
        })
        print(f"    [POST ID] Set to: {post_id_value}")

        # Step 3: Compute submission form URL
        submission_form_url = ""
        if intake_form_url:
            submission_form_url = f"{intake_form_url}?id={post_id_value}"
            print(f"    [SUBMISSION] {submission_form_url}")

        # Step 4: Build template variables
        variables = {
            "job_title": opening_info.get("job_title") or "",
            "employment_type": opening_info.get("employment_type") or "",
            "advertised_range": opening_info.get("advertised_range") or "",
            "target_collab_window": opening_info.get("target_collab_window") or "",
            "submission_form_url": submission_form_url,
            "post_id": post_id_value,
            "prefix": prefix,
            "channel": channel,
        }

        # Step 5: Load template with variable substitution
        template = get_template(job_code, channel, variables=variables)
        body_blocks = template["body_blocks"]
        print(f"    [TEMPLATE] Using: {template['source']}")

        # Step 6: Append body blocks to page
        if body_blocks:
            append_blocks(headers, new_page_id, body_blocks)
            print(f"    [BLOCKS] Appended {len(body_blocks)} blocks")

        # Step 7: Read back page to get GEN PostID formula value
        gen_post_id = None
        for attempt in range(3):
            time.sleep(1)
            refreshed = fetch_page(headers, new_page_id)
            gen_prop = refreshed.get("properties", {}).get("GEN PostID", {})
            if gen_prop.get("type") == "formula":
                formula = gen_prop.get("formula", {})
                if formula.get("type") == "string" and formula.get("string"):
                    gen_post_id = formula["string"]
                    break
            print(f"    [RETRY] GEN PostID not ready (attempt {attempt + 1}/3)")

        # Update title to match GEN PostID
        if gen_post_id:
            final_title = gen_post_id
            print(f"    [TITLE] Updating to GEN PostID: {final_title}")
        else:
            short_id = post_id_value[:8]
            final_title = f"{prefix}-{channel}-{short_id}"
            print(f"    [TITLE] GEN PostID unavailable, using fallback: {final_title}")

        update_page_properties(headers, new_page_id, {
            "Job Post Title": {
                "title": [{"text": {"content": final_title}}],
            },
        })

        result["status"] = "success"
        result["title"] = final_title

    except requests.RequestException as e:
        result["status"] = "error"
        result["error"] = f"API error: {e}"
        print(f"    [ERROR] {e}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"    [ERROR] {type(e).__name__}: {e}")

    return result


def process_opening(headers: dict, opening: dict, dry_run: bool = False) -> list[dict]:
    """Process a single opening: create job posts for each channel."""
    info = extract_opening_info(opening)
    print(f"\n  Opening: {info['title']}")
    print(f"  Prefix: {info['prefix']} | Job Code: {info['job_code']}")
    print(f"  Channels: {', '.join(info['channels']) or '(none)'}")
    if info.get("intake_form_url"):
        print(f"  Intake Form: {info['intake_form_url']}")
    if info.get("job_title"):
        print(f"  Job Title: {info['job_title']}")
    if info.get("advertised_range"):
        print(f"  Advertised Range: {info['advertised_range']}")

    if not info["channels"]:
        print(f"  [SKIP] No Post Channels configured")
        return []

    results = []
    for channel in info["channels"]:
        print(f"\n  --- Channel: {channel} ---")
        result = create_job_post(
            headers=headers,
            opening_info=info,
            channel=channel,
            dry_run=dry_run,
        )
        results.append(result)

    return results


def main():
    """Main workflow entry point."""
    parser = argparse.ArgumentParser(
        description="Create job post pages for Open openings in Notion"
    )
    parser.add_argument(
        "--opening-id",
        help="Process a single opening by Notion page ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be created without making changes",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("UPDATE JOB POSTS WORKFLOW")
    print("=" * 60)

    if args.dry_run:
        print("[MODE] Dry run — no pages will be created")

    # Load environment
    print("\n[1/3] Loading environment...")
    try:
        (notion_key,) = load_env_keys()
        print("  NOTION_KEY loaded.")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    headers = notion_headers(notion_key)

    # Get openings
    print("\n[2/3] Fetching openings...")
    if args.opening_id:
        print(f"  Mode: Single opening (id={args.opening_id})")
        try:
            page = fetch_page(headers, args.opening_id)
            openings = [page]
        except requests.RequestException as e:
            print(f"  ERROR: Could not fetch opening: {e}")
            sys.exit(1)
    else:
        print("  Mode: Batch (all Open openings)")
        try:
            openings = query_open_openings(headers, OPENINGS_DB_ID)
        except requests.RequestException as e:
            print(f"  ERROR: Could not query openings: {e}")
            sys.exit(1)

    print(f"  Found {len(openings)} opening(s)")

    if not openings:
        print("\n  No openings to process. Exiting.")
        return

    # Process openings
    print("\n[3/3] Processing openings...")
    print("-" * 60)

    all_results = []
    for i, opening in enumerate(openings, 1):
        info = extract_opening_info(opening)
        print(f"\n[{i}/{len(openings)}] {info['title']}")
        results = process_opening(headers, opening, dry_run=args.dry_run)
        all_results.extend(results)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    success = sum(1 for r in all_results if r["status"] == "success")
    dry_run_count = sum(1 for r in all_results if r["status"] == "dry_run")
    errors = sum(1 for r in all_results if r["status"] == "error")
    total = len(all_results)

    if args.dry_run:
        print(f"  Would create: {dry_run_count} job post(s)")
    else:
        print(f"  Created: {success}")
        print(f"  Errors:  {errors}")
        print(f"  Total:   {total}")

    for r in all_results:
        icon = {"success": "+", "dry_run": "~", "error": "!"}[r["status"]]
        title = r.get("title", "?")
        if r["status"] == "error":
            print(f"  [{icon}] {r['channel']}: {r.get('error', '')}")
        else:
            print(f"  [{icon}] {title}")


if __name__ == "__main__":
    main()
