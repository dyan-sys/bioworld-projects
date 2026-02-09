"""
Invite Candidates Workflow

Queries the Notion Candidates DB for candidates with Screener status = "To Invite",
then creates Gmail DRAFT emails inviting them to a Round 1 interview.

SAFETY: This workflow NEVER sends emails. It only creates drafts.
The user must manually review and send each draft from Gmail.

Usage:
    # Batch mode: all "To Invite" candidates (default limit 10)
    python3.11 invite_candidates.py

    # Custom limit
    python3.11 invite_candidates.py --limit 20

    # Single candidate by page ID
    python3.11 invite_candidates.py --page-id <notion_page_id>

    # Dry run (preview emails without creating drafts)
    python3.11 invite_candidates.py --dry-run
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.gmail_auth import get_gmail_service

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Template config loaded from R1-invite-mapping.json
TEMPLATES_DIR = SKILL_ROOT / "templates"
MAPPING_PATH = TEMPLATES_DIR / "R1-invite-mapping.json"

with open(MAPPING_PATH, "r", encoding="utf-8") as _f:
    _mapping = json.load(_f)

INVITE_TEMPLATES = _mapping["mappings"]
STATUS_FIELD = _mapping["status_field"]
GUARD_FIELD = _mapping["guard_field"]
GUARD_VALUE = _mapping["guard_value"]

# Output directory for rendered email receipts
INVITE_RECEIPTS_DIR = PROJECT_ROOT / "local-data" / "talent" / "invite_emails"


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


def query_to_invite_candidates(notion_key: str, db_id: str, limit: int = 10) -> list[dict]:
    """
    Query Notion for candidates matching:
    - Screener = "To Invite" OR "To invite (Async)"
    - 1R = "Not Started" (not yet invited)
    - Last edited in last 120 hours (5 days)
    Sorted by last edited time (most recent first).
    Uses last_edited_time instead of created_time so candidates who applied
    earlier but were recently screened and marked "To Invite" are included.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=120)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    # Build OR filter from all mapped statuses
    status_filters = [
        {"property": STATUS_FIELD, "status": {"equals": status}}
        for status in INVITE_TEMPLATES
    ]

    payload = {
        "filter": {
            "and": [
                {"or": status_filters},
                {
                    "property": GUARD_FIELD,
                    "status": {"equals": GUARD_VALUE},
                },
                {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {"on_or_after": cutoff_iso},
                },
            ],
        },
        "sorts": [
            {
                "timestamp": "last_edited_time",
                "direction": "descending",
            }
        ],
        "page_size": limit,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("results", [])


def get_candidate_info(page: dict) -> dict:
    """Extract candidate name and email from a Notion page."""
    properties = page.get("properties", {})

    # Get candidate name from "Full Name" (title field)
    name = ""
    if "Full Name" in properties:
        name_prop = properties["Full Name"]
        if name_prop.get("type") == "title":
            title_items = name_prop.get("title", [])
            if title_items:
                name = title_items[0].get("plain_text", "")

    # Get email from "Email" property (email type)
    email = None
    if "Email" in properties:
        email_prop = properties["Email"]
        if email_prop.get("type") == "email":
            email = email_prop.get("email")

    # Get Screener status for informational logging
    screener_status = None
    if "Screener" in properties:
        screener_prop = properties["Screener"]
        if screener_prop.get("type") == "status":
            status_obj = screener_prop.get("status")
            if status_obj:
                screener_status = status_obj.get("name")

    return {
        "page_id": page.get("id"),
        "name": name,
        "email": email,
        "screener_status": screener_status,
    }


def clean_name_for_filename(name: str) -> str:
    """Convert a candidate name to a safe filename."""
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip("_")


def save_email_receipt(name: str, email: str, subject: str, body: str, status: str, receipt_prefix: str = "R1-Live", draft_id: str | None = None) -> Path:
    """Save rendered email to local-data/talent/invite_emails/ as a JSON receipt."""
    INVITE_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    sgt = timezone(timedelta(hours=8))
    now = datetime.now(sgt)
    clean_name = clean_name_for_filename(name) if name else "unknown"
    filename = f"{receipt_prefix}-{clean_name}.json"
    filepath = INVITE_RECEIPTS_DIR / filename

    receipt = {
        "candidate_name": name,
        "email": email,
        "subject": subject,
        "body": body,
        "status": status,
        "draft_id": draft_id,
        "rendered_at": now.isoformat(),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)

    return filepath


def derive_first_name(full_name: str) -> str:
    """Derive first name from full name, falling back to 'there' if empty."""
    if not full_name or not full_name.strip():
        return "there"
    return full_name.strip().split()[0]


def load_template(template_filename: str) -> tuple[str, str]:
    """
    Load an email template file by name.

    Returns:
        Tuple of (subject_line, body_text).
        Subject is parsed from the first line (after "Subject: " prefix).
    """
    path = TEMPLATES_DIR / template_filename
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n", 1)
    subject_line = lines[0]
    body = lines[1].lstrip("\n") if len(lines) > 1 else ""

    # Strip "Subject: " prefix
    if subject_line.startswith("Subject: "):
        subject_line = subject_line[len("Subject: "):]

    return subject_line, body


def render_email(subject: str, body: str, first_name: str) -> tuple[str, str]:
    """Replace {first_name} placeholder in subject and body."""
    return (
        subject.replace("{first_name}", first_name),
        body.replace("{first_name}", first_name),
    )


def create_gmail_draft(service, to_email: str, subject: str, body: str) -> dict:
    """
    Create a Gmail draft (NEVER sends).

    Args:
        service: Authenticated Gmail API service.
        to_email: Recipient email address.
        subject: Email subject line.
        body: Email body (HTML).

    Returns:
        Gmail API draft response.
    """
    message = MIMEText(body, "html")
    message["to"] = to_email
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft_body = {"message": {"raw": raw}}

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return draft


def process_candidate(
    candidate: dict,
    gmail_service=None,
    dry_run: bool = False,
) -> dict:
    """Process a single candidate: select template by screener status, render email, create Gmail draft."""
    name = candidate["name"]
    email = candidate["email"]
    screener_status = candidate.get("screener_status")

    result = {"name": name, "email": email, "status": "pending", "error": None}

    if screener_status:
        print(f"  [STATUS] Screener: {screener_status}")

    if not email:
        result["status"] = "skipped"
        result["error"] = "No email address"
        print(f"  [SKIP] No email address")
        return result

    # Select template based on screener status — skip if no matching template
    tpl_config = INVITE_TEMPLATES.get(screener_status)
    if not tpl_config:
        result["status"] = "skipped"
        result["error"] = f"No template for Screener status: {screener_status}"
        print(f"  [SKIP] No template for Screener status: {screener_status}")
        return result
    subject_template, body_template = load_template(tpl_config["template"])
    receipt_prefix = tpl_config["receipt_prefix"]
    print(f"  [TEMPLATE] {tpl_config['template']}")

    # Render email
    first_name = derive_first_name(name)
    subject, body = render_email(subject_template, body_template, first_name)

    if dry_run:
        result["status"] = "dry_run"
        print(f"  [DRY RUN] To: {email}")
        print(f"  [DRY RUN] Subject: {subject}")
        print(f"  [DRY RUN] Body preview:")
        # Print first 3 non-empty lines of body
        preview_lines = [l for l in body.strip().split("\n") if l.strip()][:3]
        for line in preview_lines:
            print(f"    {line}")
        print(f"    ...")
        # Save receipt even in dry-run
        receipt_path = save_email_receipt(name, email, subject, body, status="dry_run", receipt_prefix=receipt_prefix)
        print(f"  [SAVE] {receipt_path.name}")
        return result

    try:
        draft = create_gmail_draft(gmail_service, email, subject, body)
        draft_id = draft.get("id", "unknown")
        result["status"] = "drafted"
        result["draft_id"] = draft_id
        print(f"  [DRAFT] Created draft {draft_id} -> {email}")
        receipt_path = save_email_receipt(name, email, subject, body, status="drafted", receipt_prefix=receipt_prefix, draft_id=draft_id)
        print(f"  [SAVE] {receipt_path.name}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  [ERROR] {type(e).__name__}: {e}")

    return result


def main():
    """Main workflow entry point."""
    parser = argparse.ArgumentParser(
        description="Create Gmail draft emails for candidates marked 'To Invite'"
    )
    parser.add_argument(
        "--page-id",
        help="Invite a single candidate by Notion page ID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of candidates to process in batch mode (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview emails without creating Gmail drafts",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("INVITE CANDIDATES WORKFLOW")
    print("=" * 60)
    print("SAFETY: This workflow creates DRAFTS only. Never sends.")

    if args.dry_run:
        print("[MODE] Dry run — no Gmail drafts will be created")

    # Phase 1: Load environment
    print("\n[1/3] Loading environment...")
    try:
        notion_key, notion_db_id = load_env_keys()
        print("  NOTION_KEY and NOTION_DB_ID loaded.")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # Authenticate Gmail (skip in dry-run mode)
    gmail_service = None
    if not args.dry_run:
        print("  Authenticating Gmail...")
        try:
            gmail_service = get_gmail_service()
            print("  Gmail authenticated.")
        except FileNotFoundError as e:
            print(f"  ERROR: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"  ERROR: Gmail auth failed: {e}")
            sys.exit(1)

    # Verify templates exist
    print("  Checking email templates...")
    for tpl_cfg in INVITE_TEMPLATES.values():
        tpl_path = TEMPLATES_DIR / tpl_cfg["template"]
        if not tpl_path.exists():
            print(f"  ERROR: Template not found: {tpl_path}")
            sys.exit(1)
    print(f"  Templates: {', '.join(t['template'] for t in INVITE_TEMPLATES.values())}")

    # Phase 2: Fetch candidates
    print("\n[2/3] Fetching candidates...")
    if args.page_id:
        print(f"  Mode: Single candidate (page_id={args.page_id})")
        page = fetch_notion_page(notion_key, args.page_id)
        candidates = [get_candidate_info(page)]
    else:
        print(f"  Mode: Batch (limit={args.limit})")
        statuses = ", ".join(f'"{s}"' for s in INVITE_TEMPLATES)
        print(f"  Filter: {STATUS_FIELD} in ({statuses}) AND {GUARD_FIELD} = \"{GUARD_VALUE}\" AND edited last 120h")
        candidates_raw = query_to_invite_candidates(notion_key, notion_db_id, limit=args.limit)
        candidates = [get_candidate_info(c) for c in candidates_raw]

    print(f"  Found {len(candidates)} candidate(s)")

    if not candidates:
        print("\n  No candidates to process. Exiting.")
        return

    # Phase 3: Process candidates
    print("\n[3/3] Processing candidates...")
    if not args.dry_run:
        print("  WARNING: Re-running creates duplicate drafts (no Notion status tracking).")
    print("-" * 60)

    results = []
    for i, candidate in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {candidate['name'] or '(no name)'}")
        result = process_candidate(
            candidate,
            gmail_service=gmail_service,
            dry_run=args.dry_run,
        )
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    drafted = sum(1 for r in results if r["status"] == "drafted")
    dry_run_count = sum(1 for r in results if r["status"] == "dry_run")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")

    if args.dry_run:
        print(f"  Previewed: {dry_run_count}")
    else:
        print(f"  Drafted:   {drafted}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")

    for r in results:
        icon = {"drafted": "+", "dry_run": "~", "skipped": "-", "error": "!"}[r["status"]]
        if r["status"] in ("drafted", "dry_run"):
            print(f"  [{icon}] {r['name']} -> {r.get('email', 'N/A')}")
        else:
            print(f"  [{icon}] {r['name']}: {r.get('error', '')}")

    if not args.dry_run and drafted > 0:
        print(f"\n  Check your Gmail Drafts folder for {drafted} new draft(s).")


if __name__ == "__main__":
    main()
