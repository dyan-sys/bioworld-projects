"""
Background Check Workflow

Screens candidates' online presence using Kimi web search to flag
red flags before they advance in the pipeline.

Steps per candidate:
1. Load candidate data from Notion + resume text from local files
2. Kimi Call 1 — Generate targeted search queries (no web search)
3. Kimi Call 2 — Execute searches and analyze findings (with $web_search)
4. Save receipt to local-data/talent/background_checks/
5. Update Notion with BG Check status and notes
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Add skill root to path for library imports
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.kimi_web_checker import (
    MOONSHOT_MODEL,
    generate_search_queries,
    run_background_check,
    save_receipt,
)

# Load .env file if present
load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_DIR = PROJECT_ROOT / "local-data" / "talent"
RAW_TEXT_DIR = DATA_DIR / "resume_raw_txt"
BG_CHECK_DIR = DATA_DIR / "background_checks"


def load_env_keys() -> tuple[str, str, str]:
    """Load required environment variables."""
    notion_key = os.environ.get("NOTION_KEY")
    notion_db_id = os.environ.get("NOTION_DB_ID")
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not notion_db_id:
        missing.append("NOTION_DB_ID")
    if not moonshot_key:
        missing.append("MOONSHOT_API_KEY")

    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return notion_key, notion_db_id, moonshot_key


def clean_name_for_filename(name: str) -> str:
    """Convert a candidate name to a safe filename."""
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip("_")


def fetch_notion_page(notion_key: str, page_id: str) -> dict:
    """Fetch a single Notion page by ID."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_status_filter(filter_str: str) -> tuple[str, str]:
    """
    Parse a status filter string like '2R:Proceed' into (stage, status).

    Returns:
        Tuple of (property_name, status_value)
    """
    parts = filter_str.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid status filter '{filter_str}'. Expected format: STAGE:STATUS (e.g., '2R:Proceed')"
        )
    return parts[0].strip(), parts[1].strip()


def query_notion_candidates(
    notion_key: str,
    db_id: str,
    limit: int = 10,
    status_filter: tuple[str, str] | None = None,
) -> list[dict]:
    """
    Query Notion for candidates ready for background check.

    Default filter: 2R = "Proceed" AND BG Check is empty.
    """
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # Build filter conditions
    stage_prop, stage_value = status_filter or ("2R", "Proceed")

    filters = [
        {
            "property": stage_prop,
            "select": {"equals": stage_value},
        },
        {
            "property": "BG Check",
            "select": {"is_empty": True},
        },
    ]

    payload = {
        "filter": {"and": filters},
        "sorts": [
            {
                "property": "Date Created",
                "direction": "descending",
            }
        ],
        "page_size": min(limit, 100),
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("results", [])


def get_candidate_info(page: dict) -> dict:
    """Extract candidate name, resume URL, and metadata from a Notion page."""
    properties = page.get("properties", {})

    # Get candidate name from "Full Name" (title field)
    name = "Unknown"
    if "Full Name" in properties:
        name_prop = properties["Full Name"]
        if name_prop.get("type") == "title":
            title_items = name_prop.get("title", [])
            if title_items:
                name = title_items[0].get("plain_text", "Unknown")

    # Get resume URL from "Resume" property (files type)
    resume_url = None
    if "Resume" in properties:
        resume_prop = properties["Resume"]
        files = resume_prop.get("files", [])
        if files:
            file_obj = files[0]
            if file_obj.get("type") == "external":
                resume_url = file_obj.get("external", {}).get("url")
            elif file_obj.get("type") == "file":
                resume_url = file_obj.get("file", {}).get("url")

    # Get Location (rich_text field)
    location = ""
    if "Location" in properties:
        loc_prop = properties["Location"]
        if loc_prop.get("type") == "rich_text":
            loc_items = loc_prop.get("rich_text", [])
            if loc_items:
                location = loc_items[0].get("plain_text", "")

    return {
        "page_id": page.get("id"),
        "name": name,
        "resume_url": resume_url,
        "location": location,
    }


def load_resume_text(candidate_name: str, resume_url: str | None) -> str | None:
    """
    Load resume text from local file, falling back to PDF extraction.

    Checks local-data/talent/resume_raw_txt/{name}.txt first. If not found
    and a resume URL is available, extracts text from the PDF.
    """
    clean_name = clean_name_for_filename(candidate_name)
    text_path = RAW_TEXT_DIR / f"{clean_name}.txt"

    if text_path.exists():
        return text_path.read_text(encoding="utf-8")

    if not resume_url:
        return None

    # Fallback: extract from PDF using screen-resume's pdf_tools
    try:
        pdf_tools_path = (
            PROJECT_ROOT / ".claude" / "skills" / "screen-resume" / "libraries"
        )
        sys.path.insert(0, str(pdf_tools_path))
        from pdf_tools import extract_text_from_url

        print(f"  [EXTRACT] Downloading resume PDF...")
        text = extract_text_from_url(resume_url)

        # Save for future use
        RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
        text_path.write_text(text, encoding="utf-8")
        print(f"  [SAVE] Raw text -> {text_path.name}")

        return text
    except Exception as e:
        print(f"  [WARNING] Could not extract resume text: {e}")
        return None


def extract_employers_from_resume(resume_text: str) -> str:
    """
    Extract likely employer names from resume text.

    Simple heuristic: look for lines that seem like company names
    near employment-related keywords.
    """
    if not resume_text:
        return ""

    # Take the first 2000 chars (usually covers work experience section)
    text = resume_text[:2000]

    # Common patterns: lines following "Experience" headers, or lines with dates
    # This is a rough heuristic — Kimi Call 1 will do the real work
    lines = text.split("\n")
    employers = []
    for line in lines:
        line = line.strip()
        # Lines with date ranges often contain company names
        if re.search(r"\b(20\d{2}|19\d{2})\s*[-–—]\s*(20\d{2}|present|current)", line, re.I):
            # Strip the date part to get company/title info
            cleaned = re.sub(r"\b(20\d{2}|19\d{2})\s*[-–—]\s*(20\d{2}|present|current)\b", "", line, flags=re.I)
            cleaned = cleaned.strip(" |·•–—-,")
            if cleaned and len(cleaned) > 3:
                employers.append(cleaned)

    return "; ".join(employers[:5]) if employers else ""


def format_bg_check_notes(result: dict) -> str:
    """
    Format background check result into a concise text for Notion rich_text.

    Max 2000 chars (Notion rich_text limit).
    """
    parts = []

    # Overall
    recommendation = result.get("overall_recommendation", "Unknown")
    confidence = result.get("confidence", "Unknown")
    parts.append(f"RESULT: {recommendation} (Confidence: {confidence})")

    # Summary
    summary = result.get("summary", "")
    if summary:
        parts.append(f"\n{summary}")

    # Per-category breakdown
    categories = result.get("categories", {})
    cat_labels = {
        "linkedin_consistency": "LinkedIn",
        "news_legal": "News/Legal",
        "social_media": "Social Media",
        "professional_contributions": "Professional",
    }

    for key, label in cat_labels.items():
        cat = categories.get(key, {})
        if cat:
            rating = cat.get("rating", "N/A")
            findings = cat.get("findings", "")
            parts.append(f"\n{label}: {rating} — {findings}")

    # Confidence reasoning
    conf_reason = result.get("confidence_reasoning", "")
    if conf_reason:
        parts.append(f"\nConfidence note: {conf_reason}")

    text = "\n".join(parts)
    return text[:2000]


def update_notion_bg_check(
    notion_key: str,
    page_id: str,
    recommendation: str,
    notes: str,
) -> None:
    """Update Notion page with BG Check status and notes."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "properties": {
            "BG Check": {
                "select": {"name": recommendation},
            },
            "BG Check Notes": {
                "rich_text": [{"text": {"content": notes}}],
            },
        }
    }

    response = requests.patch(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()


def process_candidate(
    candidate: dict,
    notion_key: str,
    moonshot_key: str,
    dry_run: bool = False,
) -> dict:
    """Process a single candidate: load data, search, analyze, save, update."""
    name = candidate["name"]
    page_id = candidate["page_id"]
    resume_url = candidate.get("resume_url")
    location = candidate.get("location", "")

    result = {"name": name, "status": "pending", "error": None}

    try:
        # Load resume text
        print(f"  [RESUME] Loading resume text...")
        resume_text = load_resume_text(name, resume_url)
        if not resume_text:
            result["status"] = "skipped"
            result["error"] = "No resume text available"
            print(f"  [SKIP] No resume text found and no resume URL")
            return result

        # Extract employer hints from resume
        employers = extract_employers_from_resume(resume_text)
        if employers:
            print(f"  [INFO] Employers detected: {employers[:100]}")

        candidate_data = {
            "name": name,
            "location": location,
            "employers": employers,
            "resume_text": resume_text,
        }

        # Call 1: Generate search queries
        print(f"  [QUERIES] Generating search queries...")
        queries = generate_search_queries(candidate_data, moonshot_key)
        print(f"  [QUERIES] Generated {len(queries)} queries:")
        for q in queries:
            print(f"    - {q}")

        # Call 2: Run background check with web search
        print(f"  [CHECK] Running background check with web search...")
        check_result = run_background_check(candidate_data, queries, moonshot_key)

        # Remove raw_response for Notion (keep in receipt)
        raw_response = check_result.pop("raw_response", "")

        recommendation = check_result.get("overall_recommendation", "Review Recommended")
        confidence = check_result.get("confidence", "Unknown")
        print(f"  [RESULT] {recommendation} (Confidence: {confidence})")

        # Save receipt
        receipt_data = {
            "candidate_name": name,
            "page_id": page_id,
            "queries": queries,
            "result": check_result,
            "raw_response": raw_response,
            "model": f"Kimi ({MOONSHOT_MODEL})",
        }
        receipt_path = save_receipt(receipt_data, name)
        print(f"  [SAVE] Receipt -> {receipt_path.name}")

        # Update Notion (unless dry run)
        if dry_run:
            print(f"  [DRY RUN] Would update Notion: BG Check={recommendation}")
        else:
            notes = format_bg_check_notes(check_result)
            print(f"  [UPDATE] Notion: BG Check={recommendation}")
            update_notion_bg_check(notion_key, page_id, recommendation, notes)

        result["status"] = "success"
        result["recommendation"] = recommendation
        result["confidence"] = confidence

    except requests.RequestException as e:
        result["status"] = "error"
        result["error"] = f"API/Network error: {e}"
        print(f"  [ERROR] {e}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  [ERROR] {type(e).__name__}: {e}")

    return result


def main():
    """Main workflow entry point."""
    parser = argparse.ArgumentParser(
        description="Run background checks on candidates using Kimi web search"
    )
    parser.add_argument(
        "--page-id",
        help="Check a single candidate by Notion page ID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Total candidates to process in batch mode (default: 10)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=3,
        help="Candidates per batch before pausing (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Save receipts only, skip Notion updates",
    )
    parser.add_argument(
        "--status-filter",
        default=None,
        help='Override default filter (e.g., "1R:Proceed"). Default: "2R:Proceed"',
    )
    args = parser.parse_args()

    print("=" * 60)
    print("BACKGROUND CHECK WORKFLOW (Kimi Web Search)")
    print("=" * 60)

    # Ensure directories exist
    BG_CHECK_DIR.mkdir(parents=True, exist_ok=True)

    # Load environment
    print("\n[1/3] Loading environment...")
    try:
        notion_key, notion_db_id, moonshot_key = load_env_keys()
        print("  NOTION_KEY, NOTION_DB_ID, and MOONSHOT_API_KEY loaded.")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    if args.dry_run:
        print("  MODE: Dry run (receipts only, no Notion updates)")

    # Parse status filter
    status_filter = None
    if args.status_filter:
        try:
            status_filter = parse_status_filter(args.status_filter)
            print(f"  Filter override: {status_filter[0]}={status_filter[1]}")
        except ValueError as e:
            print(f"  ERROR: {e}")
            sys.exit(1)

    # Get candidates
    print("\n[2/3] Fetching candidates...")
    if args.page_id:
        print(f"  Mode: Single candidate (page_id={args.page_id})")
        page = fetch_notion_page(notion_key, args.page_id)
        candidates = [get_candidate_info(page)]
    else:
        filter_desc = f"{status_filter[0]}={status_filter[1]}" if status_filter else "2R=Proceed"
        print(f"  Mode: Batch (limit={args.limit})")
        print(f"  Filters: {filter_desc} | BG Check empty")
        candidates_raw = query_notion_candidates(
            notion_key, notion_db_id, limit=args.limit, status_filter=status_filter
        )
        candidates = [get_candidate_info(c) for c in candidates_raw]

    print(f"  Found {len(candidates)} candidates to process")

    if not candidates:
        print("\n  No candidates to process. Exiting.")
        return

    # Process candidates in batches
    batch_size = args.batch_size if not args.page_id else len(candidates)
    total = len(candidates)
    num_batches = (total + batch_size - 1) // batch_size
    print(
        f"\n[3/3] Processing {total} candidates in batches of {batch_size} "
        f"({num_batches} batch{'es' if num_batches != 1 else ''})..."
    )
    print("-" * 60)

    results = []
    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch = candidates[start:end]

        if batch_idx > 0:
            print(f"\n  -- pausing 15s between batches --")
            time.sleep(15)

        print(f"\n  Batch {batch_idx + 1}/{num_batches} ({len(batch)} candidates)")

        for i, candidate in enumerate(batch, start + 1):
            print(f"\n[{i}/{total}] {candidate['name']}")
            result = process_candidate(
                candidate, notion_key, moonshot_key, dry_run=args.dry_run
            )
            results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    success = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"  Processed: {success}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")

    for r in results:
        status_icon = {"success": "+", "skipped": "-", "error": "!"}[r["status"]]
        if r["status"] == "success":
            rec = r.get("recommendation", "?")
            conf = r.get("confidence", "?")
            print(f"  [{status_icon}] {r['name']}: {rec} (Confidence: {conf})")
        else:
            print(f"  [{status_icon}] {r['name']}: {r.get('error', '')}")


if __name__ == "__main__":
    main()
