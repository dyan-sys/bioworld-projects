"""
Track Async Interview Completions & Calendly Bookings

Reads completion/booking emails from Gmail (Hireflix, HireTruffle, Calendly),
matches candidates in Notion, and takes per-config actions:
- create_interaction: Create Interaction record + update 1R status
- status_update_only: Update 1R status only (e.g., Calendly → "Scheduled")

Usage:
    # Discovery mode — inspect raw email format
    python3.11 track_async_completions.py --discover

    # Default: last 7 days, up to 10 emails
    python3.11 track_async_completions.py

    # Dry run (preview without creating Notion records)
    python3.11 track_async_completions.py --dry-run

    # Custom lookback and limit
    python3.11 track_async_completions.py --days 3 --limit 5

    # Force-link a specific Gmail message to a candidate
    python3.11 track_async_completions.py --message-id <gmail_id> --page-id <notion_page_id>
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Import gmail_auth from invite-candidates skill. Both skills have a
# `libraries/` package, so we import gmail_auth first, then swap sys.path
# and clear the cached `libraries` module so Python rediscovers ours.
INVITE_SKILL = PROJECT_ROOT / ".claude" / "skills" / "invite-candidates"
sys.path.insert(0, str(INVITE_SKILL))
from libraries.gmail_auth import get_gmail_service  # noqa: E402

# Swap to our own skill root and clear cached libraries package
sys.path.remove(str(INVITE_SKILL))
for mod_name in [k for k in sys.modules if k == "libraries" or k.startswith("libraries.")]:
    del sys.modules[mod_name]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.gmail_reader import (  # noqa: E402
    search_messages,
    get_full_message,
    get_message_headers,
    get_message_date,
    extract_email_body,
)
from libraries.email_parser import (  # noqa: E402
    load_all_platform_configs,
    parse_completion_email_multi,
)
from libraries.notion_interactions import (  # noqa: E402
    fetch_invited_candidates,
    fuzzy_match_candidate,
    find_candidate_by_email,
    get_candidate_name,
    get_candidate_1r_status,
    update_candidate_1r_status,
    interaction_exists,
    create_interaction,
)

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Constants
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]
INTERACTIONS_DB_ID = "28c2b7ec459780c9bf6ffb86f3b9aa9c"
RECEIPTS_DIR = PROJECT_ROOT / "local-data" / "talent" / "async_completions"


def load_env_keys() -> tuple[str, str]:
    """Load required environment variables."""
    notion_key = os.environ.get("NOTION_KEY")
    notion_db_id = os.environ.get("NOTION_DB_ID")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not notion_db_id:
        missing.append("NOTION_DB_ID")

    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    return notion_key, notion_db_id


def receipt_exists(gmail_message_id: str) -> bool:
    """Check if a receipt file already exists for this Gmail message."""
    if not RECEIPTS_DIR.exists():
        return False
    pattern = f"*_{gmail_message_id}.json"
    return any(RECEIPTS_DIR.glob(pattern))


def save_receipt(gmail_message_id: str, candidate_name: str, data: dict) -> Path:
    """Save a processing receipt."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    clean_name = re.sub(r"[^\w\s-]", "", candidate_name)
    clean_name = re.sub(r"\s+", "_", clean_name).strip("_")
    filename = f"{clean_name}_{gmail_message_id}.json"
    filepath = RECEIPTS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return filepath


def run_discover(service, configs: dict[str, dict], days: int, limit: int):
    """Discovery mode — search all configured sources and print raw email structure."""
    print("\n[DISCOVER] Searching Gmail across all configs...")

    # Collect unique messages from all config search queries
    seen_ids = set()
    all_messages = []
    for name, config in configs.items():
        query = config["gmail_search_query"]
        if days:
            query += f" newer_than:{days}d"
        print(f"  [{name}] Query: {query}")
        msgs = search_messages(service, query, max_results=limit)
        print(f"  [{name}] Found {len(msgs)} message(s)")
        for m in msgs:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                all_messages.append(m)

    print(f"\n  Total unique messages: {len(all_messages)}\n")

    for i, msg_ref in enumerate(all_messages, 1):
        msg = get_full_message(service, msg_ref["id"])
        headers = get_message_headers(msg)
        body = extract_email_body(msg)
        date = get_message_date(msg)

        print(f"{'='*60}")
        print(f"[{i}] Message ID: {msg_ref['id']}")
        print(f"  From:    {headers.get('from', 'N/A')}")
        print(f"  Subject: {headers.get('subject', 'N/A')}")
        print(f"  Date:    {date}")
        print(f"  Snippet: {msg.get('snippet', '')[:120]}")

        # Try parsing with all configs
        subject = headers.get("subject", "")
        parsed = parse_completion_email_multi(subject, body.get("html", ""))
        if parsed:
            print(f"  [PARSED] via config: {parsed['matched_config']}")
            print(f"    Candidate: {parsed['candidate_name']}")
            print(f"    Job Title: {parsed['job_title']}")
            print(f"    Link:      {parsed['assessment_link'] or 'NOT FOUND'}")
        else:
            print(f"  [NOT PARSED] No config matched this email")

        # Show body excerpt
        html_text = body.get("html", "")
        if html_text:
            # Strip tags for readability
            plain = re.sub(r"<[^>]+>", " ", html_text)
            plain = re.sub(r"\s+", " ", plain).strip()
            print(f"  Body excerpt: {plain[:200]}...")
        print()


def process_email(
    service,
    msg_ref: dict,
    all_configs: dict[str, dict],
    notion_key: str,
    candidates_db_id: str,
    candidate_pools: dict[str, list[dict]],
    dry_run: bool = False,
    force_page_id: str | None = None,
) -> dict:
    """
    Process a single completion/booking email.

    Uses per-config behavior fields to determine matching strategy and action.
    Returns a result dict with status and details.
    """
    msg_id = msg_ref["id"]
    result = {"gmail_message_id": msg_id, "status": "pending"}

    # Check local receipt dedup
    if not force_page_id and receipt_exists(msg_id):
        result["status"] = "skipped"
        result["reason"] = "Receipt already exists"
        return result

    # Fetch full message
    msg = get_full_message(service, msg_id)
    headers = get_message_headers(msg)
    body = extract_email_body(msg)
    date = get_message_date(msg)
    subject = headers.get("subject", "")

    result["subject"] = subject
    result["date"] = date

    # Parse email — try all configs
    parsed = parse_completion_email_multi(subject, body.get("html", ""))
    if not parsed:
        result["status"] = "skipped"
        result["reason"] = f"Could not parse email: {subject}"
        return result

    # Resolve effective config for behavior fields
    config_key = parsed.get("matched_config", "")
    effective_config = all_configs.get(config_key, {})

    candidate_name = parsed.get("candidate_name")
    assessment_link = parsed.get("assessment_link")
    invitee_email = parsed.get("invitee_email")
    action = effective_config.get("action", "create_interaction")
    guard_status = effective_config.get("guard_1r_status", "Invitation Sent")
    target_status = effective_config.get("target_1r_status", "Async Done - Awaiting Review")

    result["candidate_name"] = candidate_name
    result["job_title"] = parsed.get("job_title")
    result["assessment_link"] = assessment_link
    result["matched_config"] = config_key
    result["action"] = action
    print(f"  Config:    {config_key}")
    print(f"  Candidate: {candidate_name or 'N/A'}")
    print(f"  Email:     {invitee_email or 'N/A'}")
    print(f"  Job Title: {parsed.get('job_title')}")
    print(f"  Link:      {assessment_link or 'NOT FOUND'}")

    # Match candidate in Notion
    candidate_page = None

    if force_page_id:
        print(f"  [FORCE] Using page ID: {force_page_id}")
        try:
            url = f"https://api.notion.com/v1/pages/{force_page_id}"
            resp = requests.get(url, headers={
                "Authorization": f"Bearer {notion_key}",
                "Notion-Version": "2022-06-28",
            }, timeout=30)
            resp.raise_for_status()
            candidate_page = resp.json()
        except Exception as e:
            result["status"] = "error"
            result["reason"] = f"Failed to fetch page {force_page_id}: {e}"
            return result
    else:
        # Email-based matching (primary for Calendly-style configs)
        if effective_config.get("match_by_email") and invitee_email:
            print(f"  [MATCH] Searching by email: {invitee_email}")
            candidate_page = find_candidate_by_email(notion_key, candidates_db_id, invitee_email)
            if candidate_page:
                print(f"  [MATCH] Email match found")

        # Fall back to pool-based fuzzy name matching
        if not candidate_page and candidate_name:
            pool_key = _pool_key(effective_config.get("candidate_pool_statuses", []))
            pool = candidate_pools.get(pool_key, [])
            if pool:
                print(f"  [MATCH] Fuzzy matching against {len(pool)} invited candidates...")
                candidate_page = fuzzy_match_candidate(candidate_name, pool)
                if candidate_page:
                    print(f"  [MATCH] Pool match found")
                else:
                    print(f"  [MATCH] No match in invited pool")

    if not candidate_page:
        label = invitee_email or candidate_name or "unknown"
        result["status"] = "unmatched"
        result["reason"] = f"No match for: {label}"
        return result

    candidate_page_id = candidate_page["id"]
    matched_name = get_candidate_name(candidate_page)
    result["notion_page_id"] = candidate_page_id
    result["matched_name"] = matched_name
    print(f"  [MATCH] Found: {matched_name} ({candidate_page_id})")

    # 1R guard: verify candidate was actually invited
    if not force_page_id:
        current_1r = get_candidate_1r_status(candidate_page)
        if current_1r != guard_status:
            result["status"] = "skipped"
            result["reason"] = f"1R status is '{current_1r}', expected '{guard_status}'"
            print(f"  [GUARD] 1R = '{current_1r}' (expected '{guard_status}') — skipping")
            return result

    # Branch by action type
    if action == "status_update_only":
        return _action_status_update(
            msg_id, candidate_name or matched_name, matched_name,
            candidate_page_id, target_status, notion_key, result, dry_run,
        )
    else:
        return _action_create_interaction(
            msg_id, candidate_name or matched_name, matched_name,
            candidate_page_id, assessment_link, date, target_status,
            parsed, effective_config, notion_key, result, dry_run,
        )


def _action_status_update(
    msg_id: str, candidate_name: str, matched_name: str,
    candidate_page_id: str, target_status: str,
    notion_key: str, result: dict, dry_run: bool,
) -> dict:
    """Action: update 1R status only (no Interaction record)."""
    if dry_run:
        result["status"] = "dry_run"
        print(f"  [DRY RUN] Would set 1R → '{target_status}'")
        return result

    try:
        update_candidate_1r_status(notion_key, candidate_page_id, target_status)
        result["status"] = "updated"
        result["1r_updated"] = target_status
        print(f"  [1R] Set to '{target_status}'")

        receipt_data = {**result, "processed_at": datetime.now(timezone.utc).isoformat()}
        receipt_path = save_receipt(msg_id, candidate_name, receipt_data)
        print(f"  [SAVE] {receipt_path.name}")
    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)
        print(f"  [ERROR] {type(e).__name__}: {e}")

    return result


def _action_create_interaction(
    msg_id: str, candidate_name: str, matched_name: str,
    candidate_page_id: str, assessment_link: str | None,
    date: str | None, target_status: str,
    parsed: dict, effective_config: dict,
    notion_key: str, result: dict, dry_run: bool,
) -> dict:
    """Action: create Interaction record + update 1R status."""
    interaction_type = parsed.get("interaction_type") or effective_config.get("interaction_type") or "1st Round (Async)"

    # Dedup check in Notion
    if interaction_exists(notion_key, INTERACTIONS_DB_ID, candidate_page_id, interaction_type):
        result["status"] = "skipped"
        result["reason"] = "Interaction already exists in Notion"
        print(f"  [SKIP] Interaction already exists")
        receipt_data = {**result, "processed_at": datetime.now(timezone.utc).isoformat()}
        save_receipt(msg_id, candidate_name, receipt_data)
        return result

    if dry_run:
        result["status"] = "dry_run"
        print(f"  [DRY RUN] Would create Interaction: R1 Async - {matched_name}")
        print(f"  [DRY RUN] Would set 1R → '{target_status}'")
        return result

    try:
        interaction_date = None
        if date:
            try:
                dt = datetime.fromisoformat(date)
                interaction_date = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        page = create_interaction(
            notion_key=notion_key,
            interactions_db_id=INTERACTIONS_DB_ID,
            candidate_page_id=candidate_page_id,
            candidate_name=matched_name,
            assessment_link=assessment_link,
            interaction_date=interaction_date,
            interaction_type=interaction_type,
        )
        result["status"] = "created"
        result["interaction_page_id"] = page.get("id")
        print(f"  [CREATED] Interaction: {page.get('id')}")

        update_candidate_1r_status(notion_key, candidate_page_id, target_status)
        result["1r_updated"] = target_status
        print(f"  [1R] Set to '{target_status}'")

        receipt_data = {**result, "processed_at": datetime.now(timezone.utc).isoformat()}
        receipt_path = save_receipt(msg_id, candidate_name, receipt_data)
        print(f"  [SAVE] {receipt_path.name}")
    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)
        print(f"  [ERROR] {type(e).__name__}: {e}")

    return result


def _pool_key(statuses: list[str]) -> str:
    """Create a hashable key from a list of statuses."""
    return "|".join(sorted(statuses))


def main():
    parser = argparse.ArgumentParser(
        description="Track Hireflix async interview completions"
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discovery mode: print raw email structure for inspection",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview matches without creating Notion records",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum emails to process (default: 10)",
    )
    parser.add_argument(
        "--message-id",
        help="Process a specific Gmail message ID",
    )
    parser.add_argument(
        "--page-id",
        help="Force-link to a specific Notion candidate page ID (use with --message-id)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("TRACK ASYNC INTERVIEW COMPLETIONS")
    print("=" * 60)

    if args.dry_run:
        print("[MODE] Dry run — no Notion records will be created")
    if args.discover:
        print("[MODE] Discovery — inspecting raw email format")

    # Load all configs
    all_configs = load_all_platform_configs()
    print(f"  Loaded {len(all_configs)} config(s): {', '.join(all_configs.keys())}")

    # Authenticate Gmail
    print("\n[1/3] Authenticating Gmail...")
    try:
        service = get_gmail_service(scopes=GMAIL_SCOPES)
        print("  Gmail authenticated (compose + readonly scopes).")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR: Gmail auth failed: {e}")
        sys.exit(1)

    # Discovery mode
    if args.discover:
        run_discover(service, all_configs, args.days, args.limit)
        return

    # Load Notion keys
    print("\n[2/3] Loading environment...")
    try:
        notion_key, candidates_db_id = load_env_keys()
        print(f"  NOTION_KEY loaded.")
        print(f"  Candidates DB: {candidates_db_id}")
        print(f"  Interactions DB: {INTERACTIONS_DB_ID}")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # Load candidate pools — one per unique set of statuses across all configs
    print("  Loading candidate pools...")
    candidate_pools: dict[str, list[dict]] = {}
    for cfg_name, cfg in all_configs.items():
        statuses = cfg.get("candidate_pool_statuses", [])
        if not statuses:
            continue
        key = _pool_key(statuses)
        if key not in candidate_pools:
            pool = fetch_invited_candidates(notion_key, candidates_db_id, statuses)
            candidate_pools[key] = pool
            print(f"  Pool [{key}]: {len(pool)} candidates")

    # Fetch emails
    print(f"\n[3/3] Processing emails (last {args.days} days, limit {args.limit})...")

    if args.message_id:
        # Single message mode
        print(f"  Mode: Single message ({args.message_id})")
        if args.page_id:
            print(f"  Force-link to: {args.page_id}")
        messages = [{"id": args.message_id}]
    else:
        # Search Gmail across all configs
        seen_ids = set()
        messages = []
        for name, cfg in all_configs.items():
            query = cfg["gmail_search_query"]
            query += f" newer_than:{args.days}d"
            print(f"  [{name}] Query: {query}")
            msgs = search_messages(service, query, max_results=args.limit)
            for m in msgs:
                if m["id"] not in seen_ids:
                    seen_ids.add(m["id"])
                    messages.append(m)
            print(f"  [{name}] Found {len(msgs)} email(s)")
        print(f"  Total unique: {len(messages)}")

    if not messages:
        print("\n  No emails to process. Exiting.")
        return

    print("-" * 60)

    results = []
    for i, msg_ref in enumerate(messages, 1):
        print(f"\n[{i}/{len(messages)}] Message ID: {msg_ref['id']}")
        result = process_email(
            service=service,
            msg_ref=msg_ref,
            all_configs=all_configs,
            notion_key=notion_key,
            candidates_db_id=candidates_db_id,
            candidate_pools=candidate_pools,
            dry_run=args.dry_run,
            force_page_id=args.page_id if args.message_id else None,
        )
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    created = sum(1 for r in results if r["status"] == "created")
    updated = sum(1 for r in results if r["status"] == "updated")
    dry_run_count = sum(1 for r in results if r["status"] == "dry_run")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    unmatched = sum(1 for r in results if r["status"] == "unmatched")
    errors = sum(1 for r in results if r["status"] == "error")

    if args.dry_run:
        print(f"  Would process: {dry_run_count}")
    else:
        print(f"  Created:     {created}")
        print(f"  Updated:     {updated}")
    print(f"  Skipped:     {skipped}")
    print(f"  Unmatched:   {unmatched}")
    print(f"  Errors:      {errors}")

    for r in results:
        name = r.get("candidate_name", r.get("subject", r["gmail_message_id"]))
        icon = {
            "created": "+",
            "updated": "^",
            "dry_run": "~",
            "skipped": "-",
            "unmatched": "?",
            "error": "!",
            "pending": ".",
        }.get(r["status"], ".")
        if r["status"] in ("created", "updated", "dry_run"):
            print(f"  [{icon}] {name} -> {r.get('matched_name', 'N/A')} ({r.get('action', '')})")
        else:
            print(f"  [{icon}] {name}: {r.get('reason', '')}")

    if not args.dry_run and unmatched > 0:
        print(f"\n  Tip: Use --message-id <id> --page-id <notion_id> to force-link unmatched candidates.")


if __name__ == "__main__":
    main()
