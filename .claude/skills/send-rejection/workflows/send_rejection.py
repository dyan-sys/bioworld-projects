"""
Send Rejection Workflow

Queries the Notion Candidates DB for candidates with status matching rejection mapping,
then creates Gmail DRAFT emails telling them they were not selected.

SAFETY: This workflow NEVER sends emails. It only creates drafts.
The user must manually review and send each draft from Gmail.

Usage:
    # Batch mode: candidates matching mapping (default limit 10)
    python3.11 send_rejection.py

    # Custom limit
    python3.11 send_rejection.py --limit 20

    # Single candidate by page ID
    python3.11 send_rejection.py --page-id <notion_page_id>

    # Dry run (preview emails without creating drafts)
    python3.11 send_rejection.py --dry-run
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

# Template config loaded from rejection-mapping.json
TEMPLATES_DIR = SKILL_ROOT / "templates"
MAPPING_PATH = TEMPLATES_DIR / "rejection-mapping.json"

with open(MAPPING_PATH, "r", encoding="utf-8") as _f:
    _mapping = json.load(_f)

STATUS_FIELD = _mapping.get("status_field", "Screener")
INTERACTIONS_STATUS_FIELD = _mapping.get("interactions_status_field", "Rec Proceed to Next R?")
INTERACTIONS_STATUS_VALUES = _mapping.get("interactions_status_values", ["No"])
GUARD_FIELD = _mapping.get("guard_field", "")
GUARD_VALUE = _mapping.get("guard_value", "")
CANDIDATE_RELATION_FIELD = _mapping.get("candidate_relation_field", "👥 Candidates DB")

# Candidates DB: status value → template config
CANDIDATES_TEMPLATES = _mapping.get("candidates_mappings", {})
# Interactions DB: single template for all "No" rows
INTERACTIONS_TEMPLATE = _mapping.get("interactions_template", {})
# Unified lookup used by process_candidate
REJECTION_TEMPLATES = {**CANDIDATES_TEMPLATES, **{v: INTERACTIONS_TEMPLATE for v in INTERACTIONS_STATUS_VALUES}}

# Output directory for rendered email receipts
REJECTION_RECEIPTS_DIR = PROJECT_ROOT / "local-data" / "talent" / "rejection_emails"

DEFAULT_JOB_TITLE = "Virtual Executive Assistant"


def load_env_keys() -> tuple[str, str]:
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
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def get_job_title_from_post(notion_key: str, post_page_id: str, cache: dict) -> str:
    try:
        post_page = fetch_notion_page(notion_key, post_page_id)
        post_props = post_page.get("properties", {})

        opening_id = None
        if "Opening" in post_props:
            opening_prop = post_props["Opening"]
            if opening_prop.get("type") == "relation":
                relations = opening_prop.get("relation", [])
                if relations:
                    opening_id = relations[0].get("id")

        if not opening_id:
            return DEFAULT_JOB_TITLE

        if opening_id in cache:
            return cache[opening_id]

        opening_page = fetch_notion_page(notion_key, opening_id)
        opening_props = opening_page.get("properties", {})

        job_title = None
        if "Job Title" in opening_props:
            jt_prop = opening_props["Job Title"]
            if jt_prop.get("type") == "rich_text":
                rich_text = jt_prop.get("rich_text", [])
                if rich_text:
                    job_title = rich_text[0].get("plain_text", "").strip()

        resolved = job_title if job_title else DEFAULT_JOB_TITLE
        cache[opening_id] = resolved
        return resolved
    except Exception as e:
        print(f"  [WARNING] Job title lookup failed: {e}")
        return DEFAULT_JOB_TITLE


def query_rejection_candidates(notion_key: str, db_id: str, limit: int = 10) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    status_filters = [
        {"property": STATUS_FIELD, "status": {"equals": status}}
        for status in CANDIDATES_TEMPLATES
    ]

    and_filters = [
        {"or": status_filters},
        {
            "timestamp": "last_edited_time",
            "last_edited_time": {"on_or_after": cutoff_iso},
        },
    ]

    if GUARD_FIELD and GUARD_VALUE:
        and_filters.insert(1, {"property": GUARD_FIELD, "status": {"equals": GUARD_VALUE}})

    payload = {
        "filter": {"and": and_filters},
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


def query_interactions_no_proceed(notion_key: str, interactions_db_id: str, limit: int = 10) -> list[dict]:
    """Query Interactions DB for rows where INTERACTIONS_STATUS_FIELD = 'No' (or mapped values)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    url = f"https://api.notion.com/v1/databases/{interactions_db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    status_filters = [
        {"property": INTERACTIONS_STATUS_FIELD, "select": {"equals": status}}
        for status in INTERACTIONS_STATUS_VALUES
    ]

    and_filters = [
        {"or": status_filters},
        {
            "property": "Interaction Date",
            "date": {"on_or_after": cutoff_iso},
        },
    ]

    if GUARD_FIELD and GUARD_VALUE:
        and_filters.append({"property": GUARD_FIELD, "select": {"equals": GUARD_VALUE}})

    payload = {
        "filter": {"and": and_filters},
        "sorts": [
            {
                "property": "Interaction Date",
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
    properties = page.get("properties", {})

    name = ""
    if "Full Name" in properties:
        name_prop = properties["Full Name"]
        if name_prop.get("type") == "title":
            title_items = name_prop.get("title", [])
            if title_items:
                name = title_items[0].get("plain_text", "")

    email = None
    if "Email" in properties:
        email_prop = properties["Email"]
        if email_prop.get("type") == "email":
            email = email_prop.get("email")

    status_value = None
    if STATUS_FIELD in properties:
        prop = properties[STATUS_FIELD]
        if prop.get("type") == "status" and prop.get("status"):
            status_value = prop["status"].get("name")

    post_relation_id = None
    if "Post" in properties:
        post_prop = properties["Post"]
        if post_prop.get("type") == "relation":
            relations = post_prop.get("relation", [])
            if relations:
                post_relation_id = relations[0].get("id")

    return {
        "page_id": page.get("id"),
        "name": name,
        "email": email,
        "status_value": status_value,
        "post_relation_id": post_relation_id,
    }


def clean_name_for_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip("_")


def save_email_receipt(name: str, email: str, subject: str, body: str, status: str, receipt_prefix: str = "Rejection", draft_id: str | None = None) -> Path:
    REJECTION_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    sgt = timezone(timedelta(hours=8))
    now = datetime.now(sgt)
    clean_name = clean_name_for_filename(name) if name else "unknown"
    filename = f"{receipt_prefix}-{clean_name}.json"
    filepath = REJECTION_RECEIPTS_DIR / filename

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
    if not full_name or not full_name.strip():
        return "there"
    return full_name.strip().split()[0]


def load_template(template_filename: str) -> tuple[str, str]:
    path = TEMPLATES_DIR / template_filename
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n", 1)
    subject_line = lines[0]
    body = lines[1].lstrip("\n") if len(lines) > 1 else ""

    if subject_line.startswith("Subject: "):
        subject_line = subject_line[len("Subject: "):]

    return subject_line, body


def render_email(subject: str, body: str, first_name: str, job_title: str = DEFAULT_JOB_TITLE) -> tuple[str, str]:
    return (
        subject.replace("{first_name}", first_name).replace("{job_title}", job_title),
        body.replace("{first_name}", first_name).replace("{job_title}", job_title),
    )


def update_notion_rejection_sent(notion_key: str, page_id: str) -> None:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {"properties": {"Rejection Email Sent?": {"checkbox": True}}}
    response = requests.patch(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()


def create_gmail_draft(service, to_email: str, subject: str, body: str) -> dict:
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
    notion_key: str = None,
    title_cache: dict = None,
) -> dict:
    name = candidate["name"]
    email = candidate["email"]
    status_value = candidate.get("status_value")

    result = {"name": name, "email": email, "status": "pending", "error": None}

    if status_value:
        print(f"  [STATUS] {STATUS_FIELD}: {status_value}")

    if not email:
        result["status"] = "skipped"
        result["error"] = "No email address"
        print(f"  [SKIP] No email address")
        return result

    template_cfg = REJECTION_TEMPLATES.get(status_value)
    if not template_cfg:
        result["status"] = "skipped"
        result["error"] = f"No template for status: {status_value}"
        print(f"  [SKIP] No template for status: {status_value}")
        return result

    subject_template, body_template = load_template(template_cfg["template"])
    receipt_prefix = template_cfg.get("receipt_prefix", "Rejection")
    print(f"  [TEMPLATE] {template_cfg['template']}")

    job_title = DEFAULT_JOB_TITLE
    post_relation_id = candidate.get("post_relation_id")
    if post_relation_id and notion_key and title_cache is not None:
        job_title = get_job_title_from_post(notion_key, post_relation_id, title_cache)
    print(f"  [JOB TITLE] {job_title}")

    first_name = derive_first_name(name)
    subject, body = render_email(subject_template, body_template, first_name, job_title)

    if dry_run:
        result["status"] = "dry_run"
        print(f"  [DRY RUN] To: {email}")
        print(f"  [DRY RUN] Subject: {subject}")
        preview_lines = [l for l in body.strip().split("\n") if l.strip()][:3]
        for line in preview_lines:
            print(f"    {line}")
        print(f"    ...")
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
        if notion_key and candidate.get("page_id"):
            try:
                update_notion_rejection_sent(notion_key, candidate["page_id"])
                print(f"  [NOTION] 'Rejection email sent' marked Yes")
            except Exception as e:
                print(f"  [WARNING] Notion update failed: {e}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  [ERROR] {type(e).__name__}: {e}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Create Gmail draft rejection emails")
    parser.add_argument("--source", choices=["candidates", "interactions"], default="interactions", help="Data source to query: candidates or interactions")
    parser.add_argument("--page-id", help="Process a single candidate by Notion page ID")
    parser.add_argument("--limit", type=int, default=10, help="Number of candidates to process (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Preview emails without creating Gmail drafts")
    args = parser.parse_args()

    print("=" * 60)
    print("SEND REJECTION WORKFLOW")
    print("=" * 60)
    print("SAFETY: This workflow creates DRAFTS only. Never sends.")

    if args.dry_run:
        print("[MODE] Dry run — no Gmail drafts will be created")

    try:
        notion_key, notion_db_id = load_env_keys()
        print("  NOTION_KEY and NOTION_DB_ID loaded.")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

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

    print("  Checking email templates...")
    for tpl_cfg in REJECTION_TEMPLATES.values():
        tpl_path = TEMPLATES_DIR / tpl_cfg["template"]
        if not tpl_path.exists():
            print(f"  ERROR: Template not found: {tpl_path}")
            sys.exit(1)
    print(f"  Templates: {', '.join(t['template'] for t in REJECTION_TEMPLATES.values())}")

    print("\n[2/3] Fetching candidates...")
    candidates = []

    if args.source == "interactions":
        interactions_db_id = os.environ.get("INTERACTIONS_DB_ID")
        if not interactions_db_id:
            print("  ERROR: INTERACTIONS_DB_ID not set for interactions source")
            sys.exit(1)

    if args.page_id:
        if args.source == "candidates":
            print(f"  Mode: Single candidate (page_id={args.page_id}) from Candidates DB")
            page = fetch_notion_page(notion_key, args.page_id)
            candidates = [get_candidate_info(page)]
        else:
            print(f"  Mode: Single interaction (page_id={args.page_id}) from Interactions DB")
            interaction = fetch_notion_page(notion_key, args.page_id)
            candidate_relation = interaction.get("properties", {}).get(CANDIDATE_RELATION_FIELD, {}).get("relation", [])
            if not candidate_relation:
                print(f"  ERROR: No candidate relation found in interaction page {args.page_id}")
                sys.exit(1)
            candidate_page_id = candidate_relation[0].get("id")
            if not candidate_page_id:
                print(f"  ERROR: Candidate relation has no ID")
                sys.exit(1)
            candidate_page = fetch_notion_page(notion_key, candidate_page_id)
            candidate_info = get_candidate_info(candidate_page)
            candidate_info["status_value"] = None
            status_property = interaction.get("properties", {}).get(INTERACTIONS_STATUS_FIELD, {})
            if status_property.get("type") == "select" and status_property.get("select"):
                candidate_info["status_value"] = status_property["select"].get("name")
            candidates = [candidate_info]
    else:
        if args.source == "candidates":
            print(f"  Mode: Batch (limit={args.limit}) from Candidates DB")
            status_list = ", ".join(f'"{s}"' for s in CANDIDATES_TEMPLATES)
            guard_clause = f" AND {GUARD_FIELD} = \"{GUARD_VALUE}\"" if GUARD_FIELD and GUARD_VALUE else ""
            print(f"  Filter: {STATUS_FIELD} in ({status_list}){guard_clause} AND edited last 7 days")
            candidates_raw = query_rejection_candidates(notion_key, notion_db_id, limit=args.limit)
            candidates = [get_candidate_info(c) for c in candidates_raw]
        else:
            print(f"  Mode: Batch (limit={args.limit}) from Interactions DB")
            status_list = ", ".join(f'"{s}"' for s in INTERACTIONS_STATUS_VALUES)
            guard_clause = f" AND {GUARD_FIELD} = \"{GUARD_VALUE}\"" if GUARD_FIELD and GUARD_VALUE else ""
            print(f"  Filter: {INTERACTIONS_STATUS_FIELD} in ({status_list}){guard_clause} AND Interaction Date last 7 days")
            interactions = query_interactions_no_proceed(notion_key, interactions_db_id, limit=args.limit)
            print(f"  [DEBUG] Interactions DB returned {len(interactions)} raw row(s)")
            for interaction in interactions:
                relation = interaction.get("properties", {}).get(CANDIDATE_RELATION_FIELD, {}).get("relation", [])
                if not relation:
                    print(f"  [SKIP] Interaction {interaction.get('id')} has no candidate relation")
                    continue
                candidate_page_id = relation[0].get("id")
                if not candidate_page_id:
                    print(f"  [SKIP] Interaction {interaction.get('id')} candidate relation has no page id")
                    continue
                candidate_page = fetch_notion_page(notion_key, candidate_page_id)
                candidate_info = get_candidate_info(candidate_page)
                status_property = interaction.get("properties", {}).get(INTERACTIONS_STATUS_FIELD, {})
                status_value = None
                if status_property.get("type") == "select" and status_property.get("select"):
                    status_value = status_property["select"].get("name")
                candidate_info["status_value"] = status_value
                candidates.append(candidate_info)

    print(f"  Found {len(candidates)} candidate(s)")

    if not candidates:
        print("\n  No candidates to process. Exiting.")
        return

    print("\n[3/3] Processing candidates...")
    if not args.dry_run:
        print("  WARNING: Re-running creates duplicate drafts (no Notion status tracking).")
    print("-" * 60)

    title_cache = {}
    results = []
    for i, candidate in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {candidate['name'] or '(no name)'}")
        result = process_candidate(
            candidate,
            gmail_service=gmail_service,
            dry_run=args.dry_run,
            notion_key=notion_key,
            title_cache=title_cache,
        )
        results.append(result)

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
