"""
Check Recruit Status Workflow

Queries the Notion Candidates DB and prints a terminal report with
4 key metrics: pipeline overview, status breakdown, screening backlog,
and quality distribution.

Usage:
    # Default (7-day window)
    python3.11 check_recruit_status.py

    # Custom window
    python3.11 check_recruit_status.py --days 14
"""

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests
from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Constants
NOTION_API_BASE = "https://api.notion.com/v1"
SGT = timezone(timedelta(hours=8))  # Singapore Time (UTC+8)
REPORTS_DIR = PROJECT_ROOT / "local-data" / "talent" / "pipeline_reports"

# Recommendation tiers in display order
REC_TIERS = [
    "STRONG PROCEED",
    "PROCEED",
    "PROCEED WITH QUESTIONS",
    "PROCEED WITH CAUTION",
    "DO NOT PROCEED",
]


def load_env() -> tuple[str, str]:
    """Load required environment variables."""
    notion_key = os.environ.get("NOTION_KEY")
    db_id = os.environ.get("NOTION_DB_ID")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not db_id:
        missing.append("NOTION_DB_ID")

    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    return notion_key, db_id


def notion_headers(key: str) -> dict:
    """Build Notion API request headers."""
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def query_all_candidates(headers: dict, db_id: str) -> list[dict]:
    """Query all candidates from the Notion DB with pagination."""
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    all_pages = []
    next_cursor = None

    while True:
        payload = {
            "page_size": 100,
            "sorts": [{"property": "Date Created", "direction": "descending"}],
        }
        if next_cursor:
            payload["start_cursor"] = next_cursor

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        all_pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")

    return all_pages


def extract_candidate(page: dict) -> dict:
    """Extract relevant fields from a raw Notion page."""
    properties = page.get("properties", {})

    # Full Name (title)
    name = "Unknown"
    name_prop = properties.get("Full Name", {})
    if name_prop.get("type") == "title":
        title_items = name_prop.get("title", [])
        if title_items:
            name = title_items[0].get("plain_text", "Unknown")

    # Status
    status = "(No Status)"
    status_prop = properties.get("Status", {})
    if status_prop.get("type") == "status":
        status_obj = status_prop.get("status")
        if status_obj and status_obj.get("name"):
            status = status_obj["name"]

    # Created time (from page-level, not property)
    created_time = page.get("created_time", "")

    # Kimi Rating (rich_text -> float)
    kimi_rating = _parse_rating(properties, "Kimi Rating")

    # Kimi Recommendation (select)
    kimi_rec = _parse_select(properties, "Kimi Recommendation")

    # Claude Rating (rich_text -> float)
    claude_rating = _parse_rating(properties, "Claude Rating")

    # Claude Recommendation (select)
    claude_rec = _parse_select(properties, "Claude Recommendation")

    return {
        "name": name,
        "status": status,
        "created_time": created_time,
        "kimi_rating": kimi_rating,
        "kimi_rec": kimi_rec,
        "claude_rating": claude_rating,
        "claude_rec": claude_rec,
    }


def _parse_rating(properties: dict, prop_name: str) -> float | None:
    """Extract a float rating from a rich_text property."""
    prop = properties.get(prop_name, {})
    if prop.get("type") == "rich_text":
        items = prop.get("rich_text", [])
        if items:
            text = items[0].get("plain_text", "").strip()
            if text:
                try:
                    return float(text)
                except ValueError:
                    return None
    return None


def _parse_select(properties: dict, prop_name: str) -> str | None:
    """Extract name from a select property."""
    prop = properties.get(prop_name, {})
    if prop.get("type") == "select":
        select_obj = prop.get("select")
        if select_obj and select_obj.get("name"):
            return select_obj["name"]
    return None


def compute_pipeline_overview(candidates: list[dict], days: int) -> dict:
    """Compute pipeline overview: total, new in window, new today."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    new_in_window = 0
    new_today = 0

    for c in candidates:
        ct = c.get("created_time", "")
        if not ct:
            continue
        created = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        if created >= window_start:
            new_in_window += 1
        if created >= today_start:
            new_today += 1

    return {
        "total": len(candidates),
        "new_in_window": new_in_window,
        "new_today": new_today,
    }


def compute_status_breakdown(candidates: list[dict]) -> list[tuple[str, int]]:
    """Count candidates per status, sorted by count descending."""
    counter = Counter(c["status"] for c in candidates)
    return counter.most_common()


def compute_screening_backlog(candidates: list[dict]) -> dict:
    """Compute screening coverage for Kimi and Claude."""
    total = len(candidates)
    kimi_scored = sum(1 for c in candidates if c["kimi_rating"] is not None)
    claude_scored = sum(1 for c in candidates if c["claude_rating"] is not None)
    both_scored = sum(1 for c in candidates if c["kimi_rating"] is not None and c["claude_rating"] is not None)
    neither_scored = sum(1 for c in candidates if c["kimi_rating"] is None and c["claude_rating"] is None)

    return {
        "total": total,
        "kimi_scored": kimi_scored,
        "kimi_unscored": total - kimi_scored,
        "kimi_pct": (kimi_scored / total * 100) if total else 0,
        "claude_scored": claude_scored,
        "claude_unscored": total - claude_scored,
        "claude_pct": (claude_scored / total * 100) if total else 0,
        "both_scored": both_scored,
        "neither_scored": neither_scored,
    }


def compute_quality_distribution(candidates: list[dict]) -> list[tuple[str, int]]:
    """Count Kimi recommendation tiers in display order."""
    counter = Counter()
    for c in candidates:
        rec = c.get("kimi_rec")
        if rec:
            counter[rec] += 1

    # Return in fixed tier order, including zeros
    return [(tier, counter.get(tier, 0)) for tier in REC_TIERS]


def _bar(count: int, max_count: int, max_width: int = 20) -> str:
    """Render a simple bar chart string."""
    if max_count == 0:
        return ""
    width = round(count / max_count * max_width)
    return "|" * width


def build_report(
    days: int,
    pipeline: dict,
    status_breakdown: list[tuple[str, int]],
    backlog: dict,
    quality: list[tuple[str, int]],
) -> str:
    """Build the full report as a string."""
    now_sgt = datetime.now(SGT)
    timestamp_str = now_sgt.strftime("%Y-%m-%d %H:%M SGT")

    out = StringIO()
    p = lambda line="": print(line, file=out)

    p()
    p("=" * 60)
    p("  RECRUITMENT PIPELINE STATUS")
    p(f"  {timestamp_str} | Window: {days} days")
    p("=" * 60)

    # 1. Pipeline Overview
    p()
    p("  1. PIPELINE OVERVIEW")
    p("  ---")
    p(f"  Total Candidates:    {pipeline['total']:>5}")
    p(f"  New (last {days} days):  {pipeline['new_in_window']:>5}")
    p(f"  New Today:           {pipeline['new_today']:>5}")

    # 2. Status Breakdown
    p()
    p("  2. STATUS BREAKDOWN")
    p("  ---")
    if status_breakdown:
        max_count = status_breakdown[0][1]  # already sorted desc
        max_label_len = max(len(s) for s, _ in status_breakdown)
        for status, count in status_breakdown:
            pct = count / pipeline["total"] * 100 if pipeline["total"] else 0
            bar = _bar(count, max_count)
            p(f"  {status:<{max_label_len}}  {count:>4}  {bar:<20}  {pct:>3.0f}%")

    # 3. Screening Backlog
    p()
    p("  3. SCREENING BACKLOG")
    p("  ---")
    p(f"  {'':16} {'Scored':>7}  {'Unscored':>8}  {'Coverage':>8}")
    p(f"  {'Kimi:':16} {backlog['kimi_scored']:>7}  {backlog['kimi_unscored']:>8}  {backlog['kimi_pct']:>7.0f}%")
    p(f"  {'Claude:':16} {backlog['claude_scored']:>7}  {backlog['claude_unscored']:>8}  {backlog['claude_pct']:>7.0f}%")
    p()
    p(f"  Both scored:        {backlog['both_scored']:>5}")
    p(f"  Neither scored:     {backlog['neither_scored']:>5}")

    # 4. Quality Distribution
    p()
    p("  4. QUALITY DISTRIBUTION (Kimi)")
    p("  ---")
    scored_recs = [count for _, count in quality]
    max_q = max(scored_recs) if scored_recs else 0
    total_scored = sum(scored_recs)
    for tier, count in quality:
        pct = count / total_scored * 100 if total_scored else 0
        bar = _bar(count, max_q)
        p(f"  {tier:<24}  {count:>4}  {bar:<20}  {pct:>3.0f}%")

    p()
    p("=" * 60)
    p()

    return out.getvalue()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check recruitment pipeline status from Notion"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Window in days for 'new candidates' metric (default: 7)",
    )
    args = parser.parse_args()

    # Load environment
    try:
        notion_key, db_id = load_env()
    except EnvironmentError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    headers = notion_headers(notion_key)

    # Query all candidates
    print("Fetching candidates from Notion...", end="", flush=True)
    try:
        pages = query_all_candidates(headers, db_id)
    except requests.RequestException as e:
        print(f"\nERROR: Could not query candidates: {e}")
        sys.exit(1)
    print(f" {len(pages)} found.")

    if not pages:
        print("No candidates found in the database.")
        return

    # Extract data
    candidates = [extract_candidate(p) for p in pages]

    # Compute metrics
    pipeline = compute_pipeline_overview(candidates, args.days)
    status_breakdown = compute_status_breakdown(candidates)
    backlog = compute_screening_backlog(candidates)
    quality = compute_quality_distribution(candidates)

    # Build and print report
    report = build_report(args.days, pipeline, status_breakdown, backlog, quality)
    print(report, end="")

    # Save to file with SGT timestamp
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now_sgt = datetime.now(SGT)
    filename = now_sgt.strftime("%Y-%m-%d_%H%M_SGT") + ".txt"
    report_path = REPORTS_DIR / filename
    report_path.write_text(report)
    print(f"Report saved to: {report_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
