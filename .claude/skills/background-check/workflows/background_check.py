"""
Background Check Workflow

Screens candidates' online presence using Serper.dev (Google search) +
Kimi k2.5 (analysis only) to flag red flags before they advance in the pipeline.

Steps per candidate:
1. Load candidate data from Notion + resume text from local files
2. Deterministic template — Generate ~15-18 targeted search queries
3. Serper.dev — Execute queries against Google (full site: operator support)
4. Kimi k2.5 — Analyze search results (no web search)
5. Save receipt to local-data/talent/background_checks/
6. Update Notion with Socials Check status and notes
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Add skill root to path for library imports
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.kimi_web_checker import (
    KIMI_MODEL,
    generate_search_queries,
    kimi_analyze,
    save_receipt,
    serper_search,
)

# Load .env file if present
load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_DIR = PROJECT_ROOT / "local-data" / "talent"
RAW_TEXT_DIR = DATA_DIR / "resume_raw_txt"
BG_CHECK_DIR = DATA_DIR / "background_checks"


def load_env_keys() -> dict:
    """Load required environment variables."""
    keys = {
        "notion_key": os.environ.get("NOTION_KEY"),
        "notion_db_id": os.environ.get("NOTION_DB_ID"),
        "serper_api_key": os.environ.get("SERPER_API_KEY"),
        "moonshot_key": os.environ.get("MOONSHOT_API_KEY"),
    }

    missing = [name for name, val in keys.items() if not val]
    if missing:
        var_names = {
            "notion_key": "NOTION_KEY",
            "notion_db_id": "NOTION_DB_ID",
            "serper_api_key": "SERPER_API_KEY",
            "moonshot_key": "MOONSHOT_API_KEY",
        }
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(var_names[k] for k in missing)}"
        )

    return keys


def clean_name_for_filename(name: str) -> str:
    """Convert a candidate name to a safe filename."""
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip("_")


def extract_email_prefix(resume_text: str) -> str:
    """Extract email prefix (part before @) from resume text."""
    if not resume_text:
        return ""
    # Handle spaced-out PDF text: e.g. "j o h n @ g m a i l . c o m"
    collapsed = re.sub(r"(?<=\w) (?=\w)", "", resume_text[:3000])
    match = re.search(r"([\w.+-]+)@[\w.-]+\.\w{2,}", collapsed)
    if match:
        return match.group(1).lower()
    # Try original text too
    match = re.search(r"([\w.+-]+)@[\w.-]+\.\w{2,}", resume_text[:3000])
    if match:
        return match.group(1).lower()
    return ""


def extract_school(resume_text: str) -> str:
    """Extract the most prominent school/university name from resume text."""
    if not resume_text:
        return ""
    patterns = [
        r"(?:University|College|Institute|School|Academia|Polytechnic)\s+(?:of\s+)?[\w\s]+",
        r"[\w\s]+(?:University|College|Institute|Polytechnic)",
    ]
    for pattern in patterns:
        match = re.search(pattern, resume_text, re.IGNORECASE)
        if match:
            school = match.group().strip()
            # Clean up: remove leading common words that aren't part of the name
            school = re.sub(r"^(?:at|from|in)\s+", "", school, flags=re.IGNORECASE)
            if len(school) > 5:
                return school[:80]
    return ""


def extract_job_title(resume_text: str) -> str:
    """Extract the most recent/prominent job title from resume text."""
    if not resume_text:
        return ""
    # Look for common title patterns near the top of the resume
    title_patterns = [
        r"(?:Senior|Lead|Junior|Sr\.|Jr\.)?\s*(?:Software|Web|Full[ -]?Stack|Front[ -]?End|Back[ -]?End|Data|DevOps|Cloud|QA|UI/?UX|Mobile|Android|iOS)\s+(?:Engineer|Developer|Architect|Analyst|Scientist|Designer|Specialist)",
        r"(?:Project|Product|Program|Account|Operations|Marketing|HR|Finance)\s+(?:Manager|Director|Lead|Coordinator|Officer|Specialist|Analyst)",
        r"(?:Virtual|Executive|Administrative|Office)\s+(?:Assistant|Secretary|Manager|Coordinator)",
        r"(?:Customer\s+(?:Service|Support|Success)|Technical\s+Support)\s+(?:Representative|Specialist|Agent|Lead|Manager)",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, resume_text[:2000], re.IGNORECASE)
        if match:
            return match.group().strip()[:60]
    return ""


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
    """Parse a status filter string like '2R:Proceed' into (stage, status)."""
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
    recent_days: int | None = 5,
) -> list[dict]:
    """
    Query Notion for candidates ready for background check.

    Default filter: 2R = "Proceed" AND Socials Check is empty.
    In batch mode, also filters to candidates edited in the last `recent_days` days.
    Pass recent_days=None to skip the date filter (e.g. for single-candidate mode).
    """
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    stage_prop, stage_value = status_filter or ("2R", "Proceed")

    filters = [
        {
            "property": stage_prop,
            "status": {"equals": stage_value},
        },
        {
            "property": "Socials Check",
            "select": {"is_empty": True},
        },
    ]

    if recent_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)
        cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        filters.append(
            {
                "timestamp": "last_edited_time",
                "last_edited_time": {"on_or_after": cutoff_iso},
            }
        )

    payload = {
        "filter": {"and": filters},
        "sorts": [
            {
                "timestamp": "last_edited_time",
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

    name = "Unknown"
    if "Full Name" in properties:
        name_prop = properties["Full Name"]
        if name_prop.get("type") == "title":
            title_items = name_prop.get("title", [])
            if title_items:
                name = title_items[0].get("plain_text", "Unknown")

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
    """
    clean_name = clean_name_for_filename(candidate_name)
    text_path = RAW_TEXT_DIR / f"{clean_name}.txt"

    if text_path.exists():
        return text_path.read_text(encoding="utf-8")

    if not resume_url:
        return None

    try:
        pdf_tools_path = (
            PROJECT_ROOT / ".claude" / "skills" / "screen-resume" / "libraries"
        )
        sys.path.insert(0, str(pdf_tools_path))
        from pdf_tools import extract_text_from_url

        print(f"  [EXTRACT] Downloading resume PDF...")
        text = extract_text_from_url(resume_url)

        RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
        text_path.write_text(text, encoding="utf-8")
        print(f"  [SAVE] Raw text -> {text_path.name}")

        return text
    except Exception as e:
        print(f"  [WARNING] Could not extract resume text: {e}")
        return None


def extract_employers_from_resume(resume_text: str) -> str:
    """Extract likely employer names from resume text."""
    if not resume_text:
        return ""

    text = resume_text[:2000]
    lines = text.split("\n")
    employers = []
    for line in lines:
        line = line.strip()
        if re.search(r"\b(20\d{2}|19\d{2})\s*[-–—]\s*(20\d{2}|present|current)", line, re.I):
            cleaned = re.sub(r"\b(20\d{2}|19\d{2})\s*[-–—]\s*(20\d{2}|present|current)\b", "", line, flags=re.I)
            cleaned = cleaned.strip(" |·•–—-,")
            if cleaned and len(cleaned) > 3:
                employers.append(cleaned)

    return "; ".join(employers[:5]) if employers else ""


def format_bg_check_notes(result: dict) -> str:
    """Format background check result for Notion rich_text (max 2000 chars)."""
    parts = []

    recommendation = result.get("overall_recommendation", "Unknown")
    confidence = result.get("confidence", "Unknown")
    parts.append(f"RESULT: {recommendation} (Confidence: {confidence})")

    summary = result.get("summary", "")
    if summary:
        parts.append(f"\n{summary}")

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
    """Update Notion page with Socials Check status and notes."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "properties": {
            "Socials Check": {
                "select": {"name": recommendation},
            },
            "Socials Check Notes": {
                "rich_text": [{"text": {"content": notes}}],
            },
        }
    }

    response = requests.patch(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()


def process_candidate(
    candidate: dict,
    env_keys: dict,
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

        # Extract structured data from resume
        employers = extract_employers_from_resume(resume_text)
        email_prefix = extract_email_prefix(resume_text)
        school = extract_school(resume_text)
        job_title = extract_job_title(resume_text)

        if employers:
            print(f"  [INFO] Employers: {employers[:100]}")
        if email_prefix:
            print(f"  [INFO] Email prefix: {email_prefix}")
        if school:
            print(f"  [INFO] School: {school}")
        if job_title:
            print(f"  [INFO] Job title: {job_title}")

        candidate_data = {
            "name": name,
            "location": location,
            "employers": employers,
            "email_prefix": email_prefix,
            "school": school,
            "job_title": job_title,
            "resume_text": resume_text,
        }

        # Step 1: Generate search queries (deterministic template)
        print(f"  [QUERIES] Generating search queries...")
        queries = generate_search_queries(candidate_data)
        print(f"  [QUERIES] Generated {len(queries)} queries:")
        for q in queries:
            print(f"    - {q}")

        # Step 2: Search via Serper.dev (skip if serper file already exists)
        serper_dir = BG_CHECK_DIR / "serper"
        serper_dir.mkdir(parents=True, exist_ok=True)
        serper_file = serper_dir / f"{clean_name_for_filename(name)}.json"

        if serper_file.exists():
            print(f"  [SEARCH] Loading cached Serper results from serper/{serper_file.name}")
            with open(serper_file, "r", encoding="utf-8") as f:
                serper_payload = json.load(f)
            search_results = serper_payload["results"]
            print(f"  [SEARCH] {len(search_results)} cached results")
        else:
            print(f"  [SEARCH] Querying Serper.dev...")
            search_results = serper_search(queries, env_keys["serper_api_key"])
            print(f"  [SEARCH] {len(search_results)} unique results from Serper")

            serper_payload = {
                "candidate": name,
                "results": [
                    {"title": r["title"], "link": r["link"], "snippet": r["snippet"]}
                    for r in search_results
                ],
            }
            with open(serper_file, "w", encoding="utf-8") as f:
                json.dump(serper_payload, f, indent=2, ensure_ascii=False)
            print(f"  [SAVE] Serper results -> serper/{serper_file.name}")

        # Step 3: Analyze with Kimi k2.5 (cap at 15 results to stay within limits)
        analysis_results = search_results[:15]
        if len(search_results) > 15:
            print(f"  [ANALYZE] Sending top 25 of {len(search_results)} results to Kimi")
        print(f"  [ANALYZE] Kimi analysis...")
        kimi_result = kimi_analyze(
            candidate_data, analysis_results, env_keys["moonshot_key"]
        )

        check_result = kimi_result["result"]
        raw_response = kimi_result["raw_response"]

        recommendation = check_result.get("overall_recommendation", "Review Recommended")
        confidence = check_result.get("confidence", "Unknown")
        print(f"  [RESULT] {recommendation} (Confidence: {confidence})")

        # Save receipt
        receipt_data = {
            "candidate_name": name,
            "page_id": page_id,
            "candidate_data_extracted": {
                "location": location,
                "employers": employers,
                "email_prefix": email_prefix,
                "school": school,
                "job_title": job_title,
            },
            "queries_generated": queries,
            "serper_results": search_results,
            "result": check_result,
            "raw_response": raw_response,
            "models": {
                "query_generation": "Deterministic template",
                "search": "Serper.dev (Google Search)",
                "analysis": f"Kimi ({KIMI_MODEL})",
            },
        }
        receipt_path = save_receipt(receipt_data, name)
        print(f"  [SAVE] Receipt -> {receipt_path.name}")

        # Update Notion (unless dry run)
        if dry_run:
            print(f"  [DRY RUN] Would update Notion: Socials Check={recommendation}")
        else:
            notes = format_bg_check_notes(check_result)
            print(f"  [UPDATE] Notion: Socials Check={recommendation}")
            update_notion_bg_check(env_keys["notion_key"], page_id, recommendation, notes)

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
        description="Run background checks using Serper.dev + Kimi analysis"
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
    print("BACKGROUND CHECK (Serper.dev + Kimi Analysis)")
    print("=" * 60)

    # Ensure directories exist
    BG_CHECK_DIR.mkdir(parents=True, exist_ok=True)

    # Load environment
    print("\n[1/3] Loading environment...")
    try:
        env_keys = load_env_keys()
        print("  NOTION_KEY, NOTION_DB_ID, SERPER_API_KEY, MOONSHOT_API_KEY loaded.")
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
        page = fetch_notion_page(env_keys["notion_key"], args.page_id)
        candidates = [get_candidate_info(page)]
    else:
        filter_desc = f"{status_filter[0]}={status_filter[1]}" if status_filter else "2R=Proceed"
        print(f"  Mode: Batch (limit={args.limit})")
        print(f"  Filters: {filter_desc} | Socials Check empty | edited in last 5 days")
        candidates_raw = query_notion_candidates(
            env_keys["notion_key"],
            env_keys["notion_db_id"],
            limit=args.limit,
            status_filter=status_filter,
            recent_days=5,
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
            result = process_candidate(candidate, env_keys, dry_run=args.dry_run)
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
