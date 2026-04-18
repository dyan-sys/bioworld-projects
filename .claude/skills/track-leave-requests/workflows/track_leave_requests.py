"""
Track Leave Requests

Reads new EP leave submissions from the Ally HRIS Google Sheet (Leave_Tracker tab),
posts a notification to #people-ops-private on Slack, adds an event to the Team Calendar,
and marks each submission as Accepted in the sheet.

Usage:
    python3 .claude/skills/track-leave-requests/workflows/track_leave_requests.py
    python3 .claude/skills/track-leave-requests/workflows/track_leave_requests.py --dry-run
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── Paths ──────────────────────────────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SKILL_ROOT.parents[2]

load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = SKILL_ROOT / "templates" / "leave-config.json"
TOKEN_PATH = PROJECT_ROOT / "google_token_hris.json"
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.events",
]

LEAVE_EMOJI = {
    "Planned Leave": "🕓",
    "Emergency Leave": "⚡",
    "Paid Holiday Leave": "🌴",
}


# ── Config ─────────────────────────────────────────────────────────────────
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Config not found: {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


# ── Google Auth ────────────────────────────────────────────────────────────
def get_google_services():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                print(f"[ERROR] credentials.json not found at {CREDENTIALS_PATH}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    sheets = build("sheets", "v4", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return sheets, calendar


# ── Sheets ─────────────────────────────────────────────────────────────────
def read_sheet(sheets, sheet_id: str, tab_name: str) -> tuple[list[str], list[list]]:
    result = sheets.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'"
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return [], []
    headers = rows[0]
    return headers, rows[1:]


def update_status(sheets, sheet_id: str, tab_name: str, row_num: int, col_index: int, value: str, dry_run: bool):
    if dry_run:
        return
    col_letter = chr(ord("A") + col_index)
    range_notation = f"'{tab_name}'!{col_letter}{row_num}"
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_notation,
        valueInputOption="RAW",
        body={"values": [[value]]}
    ).execute()


# ── Calendar ───────────────────────────────────────────────────────────────
def parse_name_from_email(email: str) -> str:
    local = email.split("@")[0]
    return local.capitalize()


def format_hours(hours: float) -> str:
    if hours == 1:
        return "1 hr"
    if hours == int(hours):
        return f"{int(hours)} hrs"
    return f"{hours:.1f} hrs"


_MONTH_PREFIX = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "August",
    "sep": "September", "oct": "October", "nov": "November", "dec": "December",
}


def _normalize_month(date_str: str) -> str:
    """Normalize typo'd month names like 'Marc' → 'March' by matching first 3 chars."""
    words = date_str.split()
    if words:
        prefix = words[0][:3].lower()
        if prefix in _MONTH_PREFIX:
            words[0] = _MONTH_PREFIX[prefix]
            return " ".join(words)
    return date_str


def parse_leave_lines(leave_text: str, submission_date: str) -> list[dict]:
    """
    Parse lines like:
      March 19 | OFF 6PM to 8PM
      March 20 | OFF 2PM TO 8PM
    Returns list of {date, hours, hours_str} dicts.
    Falls back to submission date with no hours if format not recognised.
    """
    try:
        ref_year = datetime.strptime(submission_date[:10], "%Y-%m-%d").year
    except Exception:
        ref_year = datetime.now().year

    results = []
    for line in leave_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split("|", 1)
        if len(parts) < 2:
            continue

        date_str = _normalize_month(parts[0].strip())
        time_str = parts[1].strip()

        # Parse date — handle both "March 19" and "Mar 19"
        event_date = None
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                event_date = datetime.strptime(f"{date_str} {ref_year}", fmt).date()
                break
            except ValueError:
                continue
        if event_date is None:
            continue

        # Parse time range e.g. "OFF 6PM to 8PM" or "2PM TO 8PM"
        m = re.search(
            r"(\d+(?::\d+)?)\s*(AM|PM)\s+(?:to)\s+(\d+(?::\d+)?)\s*(AM|PM)",
            time_str, re.IGNORECASE
        )
        if not m:
            results.append({"date": event_date, "hours": None, "hours_str": ""})
            continue

        def to_minutes(h_str, ampm):
            if ":" in h_str:
                h, mn = map(int, h_str.split(":"))
            else:
                h, mn = int(h_str), 0
            if ampm.upper() == "PM" and h != 12:
                h += 12
            elif ampm.upper() == "AM" and h == 12:
                h = 0
            return h * 60 + mn

        start = to_minutes(m.group(1), m.group(2))
        end = to_minutes(m.group(3), m.group(4))
        duration_mins = end - start
        if duration_mins < 0:
            duration_mins += 24 * 60
        hours = min(duration_mins / 60, 8)
        results.append({"date": event_date, "hours": hours, "hours_str": format_hours(hours)})

    # Fallback: if nothing parsed, use submission date
    if not results:
        try:
            fallback_date = datetime.strptime(submission_date[:10], "%Y-%m-%d").date()
        except Exception:
            fallback_date = datetime.now().date()
        results.append({"date": fallback_date, "hours": None, "hours_str": ""})

    return results


def create_calendar_event(calendar, calendar_id: str, ep_email: str, leave_type: str,
                           leave_dates_hours: str, notes: str, submission_date: str,
                           dry_run: bool) -> list[str]:
    name = parse_name_from_email(ep_email)
    description_base = [
        f"EP: {ep_email}",
        f"Type: {leave_type}",
        f"Dates & Hours: {leave_dates_hours}",
    ]
    if notes:
        description_base.append(f"Notes: {notes}")

    leave_lines = parse_leave_lines(leave_dates_hours, submission_date)
    links = []

    for entry in leave_lines:
        event_date = entry["date"]
        hours_str = entry["hours_str"]
        summary = f"OFF | {name} {hours_str}".strip()

        event = {
            "summary": summary,
            "description": "\n".join(description_base),
            "colorId": "8",  # Graphite
            "start": {"date": str(event_date)},
            "end": {"date": str(event_date + timedelta(days=1))},
        }

        if dry_run:
            links.append(f"[DRY RUN] Would create: '{summary}' on {event_date}")
            continue

        result = calendar.events().insert(calendarId=calendar_id, body=event).execute()
        links.append(result.get("htmlLink", ""))

    return links


# ── Slack ──────────────────────────────────────────────────────────────────
def post_to_slack(webhook_url: str, text: str) -> None:
    resp = requests.post(webhook_url, json={"text": text}, timeout=15)
    if resp.status_code != 200:
        print(f"[WARNING] Slack post failed: {resp.status_code} {resp.text}")


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Track EP leave requests")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no sheet updates, no calendar events, no Slack posts")
    parser.add_argument("--cancel-email", help="Cancel the most recent Accepted leave request for this email address")
    args = parser.parse_args()

    if args.dry_run:
        print("\n[DRY RUN MODE] No changes will be made.\n")

    cfg = load_config()

    # ── CANCEL MODE ──────────────────────────────────────────────────────────
    if args.cancel_email:
        sheet_cfg = cfg["hris_sheet"]
        sheet_id = sheet_cfg["sheet_id"]
        tab_name = sheet_cfg["tab_name"]
        cols = sheet_cfg["columns"]

        print("Authenticating with Google...")
        sheets, _ = get_google_services()

        print(f"Reading {tab_name}...")
        headers, rows = read_sheet(sheets, sheet_id, tab_name)

        def col_idx(name):
            try:
                return headers.index(name)
            except ValueError:
                return None

        idx_email = col_idx(cols["email"])
        idx_status = col_idx(cols["status"])
        idx_leave_type = col_idx(cols["leave_type"])
        idx_leave_dates = col_idx(cols["leave_dates_hours"])

        target = args.cancel_email.strip().lower()
        match = None
        for i, row in enumerate(rows):
            def cell(idx):
                if idx is None:
                    return ""
                return row[idx].strip() if idx < len(row) else ""
            if cell(idx_email).lower() == target and cell(idx_status) == sheet_cfg["status_accepted_value"]:
                match = {"row_num": i + 2, "leave_type": cell(idx_leave_type), "leave_dates": cell(idx_leave_dates)}

        if not match:
            print(f"[ERROR] No Accepted leave request found for: {args.cancel_email}")
            sys.exit(1)

        update_status(sheets, sheet_id, tab_name, match["row_num"], idx_status, "Cancelled", args.dry_run)
        print(f"  ✓ Status → Cancelled for {args.cancel_email} ({match['leave_type']} — {match['leave_dates']})")
        return
    sheet_cfg = cfg["hris_sheet"]
    sheet_id = sheet_cfg["sheet_id"]
    tab_name = sheet_cfg["tab_name"]
    cols = sheet_cfg["columns"]
    status_value = sheet_cfg["status_accepted_value"]
    deducted_types = cfg["leave_types"]["deducted"]
    calendar_id = cfg["calendar"]["calendar_id"]
    slack_webhook = os.getenv(cfg["slack"]["webhook_url_env"], "")
    slack_tag = cfg["slack"].get("tag", "")

    print("Authenticating with Google...")
    sheets, calendar = get_google_services()

    print(f"Reading {tab_name}...")
    headers, rows = read_sheet(sheets, sheet_id, tab_name)

    if not headers:
        print("No data found in sheet.")
        return

    # Map column names to indices
    def col_idx(name):
        try:
            return headers.index(name)
        except ValueError:
            return None

    idx_timestamp = col_idx(cols["timestamp"])
    idx_email = col_idx(cols["email"])
    idx_leave_type = col_idx(cols["leave_type"])
    idx_leave_dates = col_idx(cols["leave_dates_hours"])
    idx_notes = col_idx(cols["notes"])
    idx_informed = col_idx(cols["informed_cpl"])
    idx_status = col_idx(cols["status"])

    if idx_status is None:
        print(f"[ERROR] Could not find '{cols['status']}' column in sheet.")
        sys.exit(1)

    # Find new submissions (Status is blank)
    new_submissions = []
    for i, row in enumerate(rows):
        def cell(idx):
            if idx is None:
                return ""
            return row[idx].strip() if idx < len(row) else ""

        status = cell(idx_status)
        if status:
            continue  # already processed

        new_submissions.append({
            "row_num": i + 2,  # +1 for header, +1 for 1-based indexing
            "timestamp": cell(idx_timestamp),
            "email": cell(idx_email),
            "leave_type": cell(idx_leave_type),
            "leave_dates_hours": cell(idx_leave_dates),
            "notes": cell(idx_notes),
            "informed_cpl": cell(idx_informed),
        })

    print(f"Found {len(new_submissions)} new submission(s)\n")

    if not new_submissions:
        print("No new leave requests to process.")
        return

    processed = []
    errors = []

    for sub in new_submissions:
        email = sub["email"] or "Unknown"
        leave_type = sub["leave_type"] or "Unknown"
        leave_dates = sub["leave_dates_hours"]
        notes = sub["notes"]
        informed = sub["informed_cpl"]
        timestamp = sub["timestamp"]
        emoji = LEAVE_EMOJI.get(leave_type, "📅")
        is_deducted = any(d.lower() in leave_type.lower() for d in deducted_types)

        print(f"Processing: {email} — {leave_type}")

        try:
            # Add to Google Calendar (one event per leave day)
            event_links = create_calendar_event(
                calendar, calendar_id, email, leave_type,
                leave_dates, notes, timestamp, args.dry_run
            )

            # Format dates & hours from parsed leave lines
            leave_lines = parse_leave_lines(leave_dates, timestamp)
            dates_summary = ", ".join(
                f"{entry['date'].strftime('%b %d')} — {entry['hours_str']}" if entry['hours_str']
                else entry['date'].strftime('%b %d')
                for entry in leave_lines
            )

            # Post to Slack
            lines = [
                f"{emoji} *New Leave Request*",
                f"*From:* {email}",
                f"*Type:* {leave_type}",
                f"*Dates & Hours:* {dates_summary}",
                f"*Date submitted:* {timestamp[:10] if timestamp else '—'}",
            ]
            if event_links and not args.dry_run:
                lines.append(f"*Calendar:* <{event_links[0]}|View event>")

            if args.dry_run:
                print(f"  [SLACK PREVIEW]\n    " + "\n    ".join(lines))
            else:
                post_to_slack(slack_webhook, "\n".join(lines))

            # Update Status in sheet
            update_status(sheets, sheet_id, tab_name, sub["row_num"], idx_status, status_value, args.dry_run)

            print(f"  ✓ Slack posted, calendar event created, status → {status_value}")
            processed.append(sub)

        except Exception as e:
            print(f"  [ERROR] {email}: {e}")
            errors.append({"email": email, "error": str(e)})

    # Summary
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Processed: {len(processed)}")
    if errors:
        print(f"  Errors:    {len(errors)}")
        for err in errors:
            print(f"    - {err['email']}: {err['error']}")

    if processed and not args.dry_run and slack_webhook:
        summary = f":white_check_mark: *Leave Requests Processed — {datetime.now().strftime('%Y-%m-%d')}*\n"
        summary += f"Recorded {len(processed)} new leave request(s) and added to Team Calendar."
        if errors:
            summary += f"\n⚠️ {len(errors)} error(s) — check logs."
        post_to_slack(slack_webhook, summary)


if __name__ == "__main__":
    main()
