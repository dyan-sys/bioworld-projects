"""
Client Pipeline Update — Draft Generator

Queries Notion for candidates tagged to a specific role (via Post → Opening),
groups by screening tier, and writes a draft pipeline update note.

Usage:
    python3.11 client_pipeline_update.py --client care-n-bloom --role CBCS
    python3.11 client_pipeline_update.py --client care-n-bloom --role CBCS --days 30
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATES_DIR = SKILL_ROOT / "templates"
CLIENT_DATA_DIR = PROJECT_ROOT / "local-data" / "client-consulting"

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Constants
NOTION_API_BASE = "https://api.notion.com/v1"
SGT = timezone(timedelta(hours=8))

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15]
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectionError,
)

# Tier ordering for display
TIER_ORDER = [
    "STRONG PROCEED",
    "PROCEED",
    "PROCEED WITH QUESTIONS",
    "PROCEED WITH CAUTION",
    "DO NOT PROCEED",
]


def _notion_request(method: str, url: str, headers: dict, timeout: int = 30, **kwargs) -> requests.Response:
    """Make a Notion API request with retry on transient failures."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt - 1]
                    print(f"  [RETRY] HTTP {response.status_code}, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
            response.raise_for_status()
            return response
        except RETRYABLE_EXCEPTIONS as exc:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt - 1]
                print(f"  [RETRY] {type(exc).__name__}, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exhausted retries")


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
        raise EnvironmentError(f"Missing: {', '.join(missing)}")
    return notion_key, db_id


def notion_headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def load_client_config(client_slug: str) -> dict:
    """Load client config from client-config.json."""
    config_path = TEMPLATES_DIR / "client-config.json"
    with open(config_path) as f:
        all_configs = json.load(f)
    if client_slug not in all_configs:
        raise ValueError(f"Client '{client_slug}' not found in client-config.json. Available: {list(all_configs.keys())}")
    return all_configs[client_slug]


def query_scored_candidates(headers: dict, db_id: str, since_days: int) -> list[dict]:
    """Query candidates with Kimi ratings created in the last N days."""
    cutoff = datetime.now(SGT) - timedelta(days=since_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%d")

    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    all_pages = []
    cursor = None

    while True:
        payload = {
            "page_size": 100,
            "filter": {
                "and": [
                    {"timestamp": "created_time", "created_time": {"on_or_after": cutoff_iso}},
                    {"property": "Kimi Rating", "rich_text": {"is_not_empty": True}},
                ]
            },
            "sorts": [{"property": "Date Created", "direction": "descending"}],
        }
        if cursor:
            payload["start_cursor"] = cursor

        response = _notion_request("POST", url, headers=headers, json=payload)
        data = response.json()
        all_pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return all_pages


def query_total_candidates(headers: dict, db_id: str, since_days: int) -> int:
    """Count all candidates created in the last N days (scored or not)."""
    cutoff = datetime.now(SGT) - timedelta(days=since_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%d")

    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    total = 0
    cursor = None

    while True:
        payload = {
            "page_size": 100,
            "filter": {
                "timestamp": "created_time",
                "created_time": {"on_or_after": cutoff_iso},
            },
        }
        if cursor:
            payload["start_cursor"] = cursor

        response = _notion_request("POST", url, headers=headers, json=payload)
        data = response.json()
        total += len(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return total


def extract_candidate(page: dict) -> dict:
    """Extract relevant fields from a Notion candidate page."""
    props = page["properties"]

    # Full Name
    name = "Unknown"
    n = props.get("Full Name", {})
    if n.get("type") == "title" and n.get("title"):
        name = n["title"][0].get("plain_text", "Unknown")

    # Kimi Rating
    kimi_rating = None
    kr = props.get("Kimi Rating", {})
    if kr.get("type") == "rich_text" and kr.get("rich_text"):
        txt = kr["rich_text"][0].get("plain_text", "").strip()
        try:
            kimi_rating = float(txt)
        except ValueError:
            pass

    # Kimi Recommendation
    kimi_rec = None
    krec = props.get("Kimi Recommendation", {})
    if krec.get("type") == "select" and krec.get("select"):
        kimi_rec = krec["select"].get("name")

    # Post relation ID
    post_id = None
    pp = props.get("Post", {})
    if pp.get("type") == "relation" and pp.get("relation"):
        post_id = pp["relation"][0].get("id")

    # Notion page URL
    page_url = page.get("url", "")

    return {
        "name": name,
        "kimi_rating": kimi_rating,
        "kimi_rec": kimi_rec,
        "post_id": post_id,
        "page_url": page_url,
    }


def resolve_opening_map(headers: dict, post_ids: set) -> dict:
    """Resolve Post IDs → Opening names. Returns {post_id: opening_name}."""
    opening_map = {}
    total = len(post_ids)
    print(f"  Resolving {total} post(s) to openings...", end="", flush=True)

    for pid in post_ids:
        try:
            post_page = _notion_request("GET", f"{NOTION_API_BASE}/pages/{pid}", headers=headers).json()
            post_props = post_page.get("properties", {})

            opening_prop = post_props.get("Opening", {})
            if opening_prop.get("type") == "relation" and opening_prop.get("relation"):
                oid = opening_prop["relation"][0]["id"]
                opening_page = _notion_request("GET", f"{NOTION_API_BASE}/pages/{oid}", headers=headers).json()
                opening_props = opening_page.get("properties", {})

                title_prop = opening_props.get("Opening ID & Name", {})
                if title_prop.get("type") == "title" and title_prop.get("title"):
                    opening_map[pid] = title_prop["title"][0].get("plain_text", "Unknown")
                    continue

            opening_map[pid] = "Unknown"
        except requests.RequestException:
            opening_map[pid] = "(error)"

    print(" done.")
    return opening_map


def filter_by_role(candidates: list[dict], opening_map: dict, role_code: str) -> list[dict]:
    """Filter candidates whose Opening name contains the role code."""
    filtered = []
    for c in candidates:
        pid = c["post_id"]
        opening = opening_map.get(pid, "")
        if role_code in opening:
            filtered.append(c)
    return filtered


def build_tier_breakdown(candidates: list[dict]) -> dict:
    """Group candidates by recommendation tier."""
    tiers = {t: [] for t in TIER_ORDER}
    tiers["(unscored)"] = []

    for c in candidates:
        rec = c["kimi_rec"]
        if rec in tiers:
            tiers[rec].append(c)
        else:
            tiers["(unscored)"].append(c)

    # Sort each tier by score descending
    for tier_list in tiers.values():
        tier_list.sort(key=lambda x: x["kimi_rating"] or 0, reverse=True)

    return tiers


def render_draft(client_config: dict, role_code: str, total_apps: int,
                 candidates: list[dict], tiers: dict, template_path: Path) -> str:
    """Render the pipeline update draft from template."""
    with open(template_path) as f:
        template = f.read()

    now_sgt = datetime.now(SGT)
    date_str = now_sgt.strftime("%d %b %Y")
    client_name = client_config["display_name"]
    scored_count = sum(1 for c in candidates if c["kimi_rec"] is not None)
    processing_count = sum(1 for c in candidates if c["kimi_rec"] is None)

    # Build tier summary lines
    tier_lines = []
    for tier_name in TIER_ORDER:
        count = len(tiers[tier_name])
        tier_lines.append(f"- **{tier_name.title()}** ({count})")

    # Build top candidates table (STRONG PROCEED + PROCEED)
    top_candidates = tiers["STRONG PROCEED"] + tiers["PROCEED"]
    top_table_lines = []
    if top_candidates:
        top_table_lines.append("| # | Candidate | Score | Tier |")
        top_table_lines.append("|---|-----------|-------|------|")
        for i, c in enumerate(top_candidates, 1):
            score = f"{c['kimi_rating']:.1f}" if c["kimi_rating"] is not None else "N/A"
            top_table_lines.append(f"| {i} | {c['name']} | {score} | {c['kimi_rec']} |")
    else:
        top_table_lines.append("_No candidates in the top tiers yet._")

    r1_ready = len(tiers["STRONG PROCEED"]) + len(tiers["PROCEED"])

    # Substitute placeholders
    draft = template
    draft = draft.replace("{{DATE}}", date_str)
    draft = draft.replace("{{CLIENT_NAME}}", client_name)
    draft = draft.replace("{{ROLE_CODE}}", role_code)
    draft = draft.replace("{{TOTAL_APPLICATIONS}}", str(total_apps))
    draft = draft.replace("{{SCORED_COUNT}}", str(scored_count))
    draft = draft.replace("{{PROCESSING_COUNT}}", str(processing_count))
    draft = draft.replace("{{TIER_SUMMARY}}", "\n".join(tier_lines))
    draft = draft.replace("{{TOP_CANDIDATES_TABLE}}", "\n".join(top_table_lines))
    draft = draft.replace("{{R1_READY_COUNT}}", str(r1_ready))

    return draft


def main():
    parser = argparse.ArgumentParser(description="Generate a client pipeline update draft")
    parser.add_argument("--client", required=True, help="Client slug (e.g., care-n-bloom)")
    parser.add_argument("--role", required=True, help="Role code to filter by (e.g., CBCS)")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    args = parser.parse_args()

    # Load config
    try:
        client_config = load_client_config(args.client)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    try:
        notion_key, db_id = load_env()
    except EnvironmentError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    headers = notion_headers(notion_key)

    # Query candidates
    print(f"Fetching scored candidates (last {args.days}d)...", end="", flush=True)
    pages = query_scored_candidates(headers, db_id, args.days)
    print(f" {len(pages)} found.")

    candidates = [extract_candidate(p) for p in pages]

    # Resolve post → opening mapping
    unique_posts = set(c["post_id"] for c in candidates if c["post_id"])
    opening_map = resolve_opening_map(headers, unique_posts)

    # Filter by role
    role_candidates = filter_by_role(candidates, opening_map, args.role)
    print(f"  {args.role} candidates: {len(role_candidates)}")

    if not role_candidates:
        print(f"No {args.role} candidates found. Check the role code.")
        sys.exit(0)

    # Build tier breakdown
    tiers = build_tier_breakdown(role_candidates)

    # Print summary to terminal
    print(f"\n{'='*60}")
    print(f"  {args.role} Pipeline — {client_config['display_name']}")
    print(f"{'='*60}")
    for tier_name in TIER_ORDER:
        count = len(tiers[tier_name])
        names = ", ".join(c["name"] for c in tiers[tier_name][:5])
        suffix = "..." if len(tiers[tier_name]) > 5 else ""
        print(f"  {tier_name:<25} {count:>3}   {names}{suffix}")
    unscored = len(tiers["(unscored)"])
    if unscored:
        print(f"  {'(still processing)':<25} {unscored:>3}")
    print(f"  {'TOTAL':<25} {len(role_candidates):>3}")

    # Render draft from template
    template_path = TEMPLATES_DIR / "pipeline-update.md"
    if not template_path.exists():
        print(f"\nWARNING: Template not found at {template_path}")
        sys.exit(1)

    # Use total scored + unscored as a proxy for total applications
    # (The real total is higher since some candidates haven't been processed at all)
    total_apps = len(role_candidates)
    draft = render_draft(client_config, args.role, total_apps, role_candidates, tiers, template_path)

    # Write draft
    output_dir = CLIENT_DATA_DIR / args.client / "pipeline-updates"
    output_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(SGT).strftime("%Y-%m-%d")
    output_path = output_dir / f"{now_str}_{args.role.lower()}.md"
    with open(output_path, "w") as f:
        f.write(draft)

    print(f"\nDraft written to: {output_path}")
    print("Review and edit before sending.")


if __name__ == "__main__":
    main()
