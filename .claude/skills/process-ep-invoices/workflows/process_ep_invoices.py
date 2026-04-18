"""
Process EP Invoices

Reconciles EP invoice submissions against the time tracker sheet,
then submits matched payments via Airwallex API.

Supports reimbursements (e.g. Claude Code subscriptions) as additional line items
on top of EP hourly services. Reimbursements are logged to the HRIS Reimbursements tab.

Runs bank detail verification during Step 1 — flags mismatches silently if all clear.

Usage:
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --dry-run
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --contractor-code EP001
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --period 2026-02
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --confirm
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --status
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Paths ──────────────────────────────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SKILL_ROOT.parents[2]

load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = SKILL_ROOT / "templates" / "ep-invoice-config.json"
RECEIPTS_DIR = PROJECT_ROOT / "local-data" / "invoices"

# New token file — includes write + drive scopes (re-auth required if upgrading)
TOKEN_PATH = PROJECT_ROOT / "google_token_ep_invoices.json"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",   # read + write
    "https://www.googleapis.com/auth/drive.readonly",  # download invoice PDFs
]

AIRWALLEX_URLS = {
    "production": "https://api.airwallex.com",
    "demo": "https://api-demo.airwallex.com",
}


# ── Config ─────────────────────────────────────────────────────────────────
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Config not found: {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text())


# ── Billing period ─────────────────────────────────────────────────────────
def get_billing_period(override: str | None) -> str:
    """Returns billing period as YYYY-MM. Defaults to previous month."""
    if override:
        return override
    first_of_month = datetime.now().replace(day=1)
    prev_month = first_of_month - timedelta(days=1)
    return prev_month.strftime("%Y-%m")


# ── Google auth ────────────────────────────────────────────────────────────
def get_google_services():
    """Returns (sheets_service, drive_service) with combined scopes."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SHEETS_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_path = os.getenv("GMAIL_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json"))
            if not Path(creds_path).exists():
                print(f"[ERROR] Google credentials not found at {creds_path}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SHEETS_SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def read_sheet(service, sheet_id: str, tab_name: str, header_row: int = 1) -> list[dict]:
    """Read a sheet tab and return list of dicts. header_row is 1-indexed."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=tab_name)
        .execute()
    )
    rows = result.get("values", [])
    if not rows or len(rows) < header_row:
        return []
    headers = rows[header_row - 1]
    return [
        {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        for row in rows[header_row:]
    ]


# ── HRIS: Reimbursements tab ───────────────────────────────────────────────
REIMBURSEMENTS_HEADERS = ["Period", "Contractor Code", "EP Name", "Description", "Amount (USD)", "Logged At"]


def ensure_reimbursements_tab(sheets_service, sheet_id: str, tab_name: str) -> None:
    """Create Reimbursements tab with headers if it doesn't exist."""
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]

    if tab_name not in existing:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
        print(f"  [HRIS] Created tab '{tab_name}'")

        sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            body={"values": [REIMBURSEMENTS_HEADERS]},
        ).execute()


def write_reimbursements_to_hris(
    sheets_service, sheet_id: str, tab_name: str, reimbursements: list[dict]
) -> None:
    """Append reimbursement rows to HRIS Reimbursements tab, skipping duplicates (period + contractor_code)."""
    if not reimbursements:
        return

    ensure_reimbursements_tab(sheets_service, sheet_id, tab_name)

    # Read existing rows to detect duplicates
    existing = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab_name}'!A:B"
    ).execute().get("values", [])
    # existing rows: col A = Period, col B = Contractor Code (skip header row 1)
    already_logged = {
        (row[0].strip(), row[1].strip())
        for row in existing[1:]
        if len(row) >= 2
    }

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    skipped = 0
    for r in reimbursements:
        key = (r["period"], r["contractor_code"])
        if key in already_logged:
            skipped += 1
            print(f"  [SKIP] {r['ep_name']} ({r['contractor_code']}) already logged for {r['period']}")
            continue
        rows.append([
            r["period"],
            r["contractor_code"],
            r["ep_name"],
            r["description"] or "Reimbursement",
            round(r["amount"], 2),
            now,
        ])

    if skipped:
        print(f"  [HRIS] Skipped {skipped} duplicate(s)")

    if not rows:
        print("  [HRIS] Nothing new to log.")
        return

    append_result = sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    # Reset formatting on newly added rows to plain black text on white background
    updated_range = append_result.get("updates", {}).get("updatedRange", "")
    sheet_meta = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_id_int = next(
        (s["properties"]["sheetId"] for s in sheet_meta["sheets"]
         if s["properties"]["title"] == tab_name),
        None,
    )
    if sheet_id_int is not None and updated_range:
        # Parse start row from range like 'Reimbursements'!A5:F6
        import re as _re
        m = _re.search(r"\$?[A-Z]+\$?(\d+):\$?[A-Z]+\$?(\d+)", updated_range)
        if m:
            start_row = int(m.group(1)) - 1  # 0-indexed
            end_row = int(m.group(2))        # exclusive
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id_int,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(REIMBURSEMENTS_HEADERS),
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                                "textFormat": {
                                    "foregroundColor": {"red": 0, "green": 0, "blue": 0},
                                    "bold": False,
                                },
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                }]},
            ).execute()

    print(f"  [HRIS] Logged {len(rows)} reimbursement(s) to '{tab_name}'")


# ── Bank verification ──────────────────────────────────────────────────────
def extract_drive_file_id(url: str) -> str | None:
    """Extract Google Drive file ID from various URL formats."""
    for pattern in [r"/file/d/([a-zA-Z0-9_-]+)", r"id=([a-zA-Z0-9_-]+)", r"/d/([a-zA-Z0-9_-]+)"]:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def download_pdf_from_drive(drive_service, file_id: str) -> bytes | None:
    """Download a file from Google Drive by file ID."""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception as e:
        print(f"  [WARN] Could not download Drive file {file_id}: {e}")
        return None


def extract_bank_details_from_pdf(pdf_bytes: bytes) -> dict | None:
    """Use Claude Haiku to extract bank details from an invoice PDF."""
    try:
        import anthropic
    except ImportError:
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract the bank payment details from this invoice. "
                                "Return ONLY valid JSON with these exact keys (use null if not found): "
                                '{"bank_name": "", "bank_address": "", "swift": "", '
                                '"account_name": "", "account_number": "", "routing_number": null}'
                            ),
                        },
                    ],
                }
            ],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
        return json.loads(text)
    except Exception as e:
        print(f"  [WARN] Could not extract bank details from PDF: {e}")
        return None


def get_airwallex_bank_details(beneficiary: dict) -> dict:
    """Normalise bank details from an Airwallex beneficiary object."""
    bank = beneficiary.get("beneficiary", {}).get("bank_details", {})
    return {
        "bank_name": bank.get("bank_name", ""),
        "account_name": bank.get("account_name", ""),
        "account_number": bank.get("account_number", ""),
        "swift": bank.get("bic") or bank.get("swift_code", ""),
        "routing_number": bank.get("account_routing_value1", ""),
        "local_clearing_system": bank.get("local_clearing_system", ""),
        "bank_country_code": bank.get("bank_country_code", ""),
    }


def get_transfer_method(beneficiary: dict) -> str:
    """Returns the correct Airwallex transfer_method for a beneficiary.
    Airwallex always uses LOCAL as the method; ACH routing is handled
    internally via local_clearing_system in bank_details.
    """
    return "LOCAL"


def compare_bank_details(pdf_bank: dict, airwallex_bank: dict) -> tuple[bool, str]:
    """
    Compare invoice PDF bank details against Airwallex.
    Primary: account_number. Secondary: account_name.
    Returns (is_match, reason).
    """
    pdf_acc = (pdf_bank.get("account_number") or "").strip().replace(" ", "")
    aws_acc = (airwallex_bank.get("account_number") or "").strip().replace(" ", "")

    if not pdf_acc or not aws_acc:
        return True, "Could not compare (missing account number in one source)"

    if pdf_acc.lower() != aws_acc.lower():
        return False, f"Account number mismatch — invoice: {pdf_acc}, Airwallex: {aws_acc}"

    # Account numbers match — also check account name
    pdf_name = (pdf_bank.get("account_name") or "").strip().lower()
    aws_name = (airwallex_bank.get("account_name") or "").strip().lower()
    if pdf_name and aws_name and pdf_name != aws_name:
        return False, (
            f"Account name mismatch — invoice: '{pdf_bank['account_name']}', "
            f"Airwallex: '{airwallex_bank['account_name']}'"
        )

    return True, "OK"


def run_bank_verification(
    invoice_lookup: dict,
    drive_service,
    beneficiaries: list[dict],
    cfg: dict,
    ep_name_lookup: dict,
) -> list[dict]:
    """
    Check bank details on invoice PDFs against Airwallex for all EPs.
    Returns list of mismatches only (empty = all clear).
    """
    if not cfg.get("bank_verification", {}).get("enabled", True):
        return []

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("  [SKIP] Bank verification skipped — ANTHROPIC_API_KEY not set")
        return []

    ic = cfg["invoice_submissions"]["columns"]
    match_field = cfg["airwallex"].get("beneficiary_match_field", "nickname")
    excluded = set(cfg["matching"].get("excluded_contractors", []))

    mismatches = []
    checked = 0

    for code, inv in invoice_lookup.items():
        if code in excluded:
            continue

        pdf_url = inv.get(ic.get("invoice_pdf", ""), "").strip()
        if not pdf_url:
            continue

        file_id = extract_drive_file_id(pdf_url)
        if not file_id:
            print(f"  [WARN] Could not parse Drive URL for {code}: {pdf_url}")
            continue

        pdf_bytes = download_pdf_from_drive(drive_service, file_id)
        if not pdf_bytes:
            continue

        pdf_bank = extract_bank_details_from_pdf(pdf_bytes)
        if not pdf_bank:
            continue

        beneficiary = find_beneficiary(beneficiaries, code, match_field)
        if not beneficiary:
            continue

        aws_bank = get_airwallex_bank_details(beneficiary)
        is_match, reason = compare_bank_details(pdf_bank, aws_bank)
        checked += 1

        if not is_match:
            bank_changed = inv.get(ic.get("bank_changed", ""), "").strip()
            ep_name = ep_name_lookup.get(code, code)
            mismatches.append({
                "contractor_code": code,
                "ep_name": ep_name,
                "bank_changed_flag": bank_changed,
                "reason": reason,
            })
            print(f"  [BANK MISMATCH] {code} ({ep_name}): {reason}")
        else:
            print(f"  [BANK OK] {code}")

    if checked:
        print(f"  Bank check complete: {checked} checked, {len(mismatches)} mismatch(es)")

    return mismatches


# ── Airwallex ──────────────────────────────────────────────────────────────
def airwallex_login(base_url: str, client_id: str, api_key: str) -> str:
    resp = requests.post(
        f"{base_url}/api/v1/authentication/login",
        headers={"x-client-id": client_id, "x-api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        print("[ERROR] Airwallex login succeeded but returned no token.")
        sys.exit(1)
    return token


def get_beneficiaries(base_url: str, token: str) -> list[dict]:
    beneficiaries = []
    page = 0
    while True:
        resp = requests.get(
            f"{base_url}/api/v1/beneficiaries",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_num": page, "page_size": 100},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        beneficiaries.extend(items)
        if len(items) < 100:
            break
        page += 1
    return beneficiaries


def find_beneficiary(beneficiaries: list[dict], contractor_code: str, match_field: str) -> dict | None:
    for b in beneficiaries:
        if b.get(match_field, "").strip().lower() == contractor_code.strip().lower():
            return b
    return None


def submit_payment(
    base_url: str, token: str, beneficiary_id: str, amount: float, currency: str,
    transfer_method: str, reason: str, purpose: str, reference: str,
    dry_run: bool,
) -> dict:
    payload = {
        "request_id": str(uuid.uuid4()),
        "transfer_amount": round(amount, 2),
        "source_currency": currency,
        "transfer_currency": currency,
        "transfer_method": transfer_method,
        "beneficiary_id": beneficiary_id,
        "reason": reason,
        "purpose_of_transfer": purpose,
        "reference": reference,
        "remarks": reference,
    }
    if dry_run:
        return {"dry_run": True, "payload": payload}

    resp = requests.post(
        f"{base_url}/api/v1/transfers/create",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ── Slack ──────────────────────────────────────────────────────────────────
def post_to_slack(webhook_url: str, text: str) -> None:
    resp = requests.post(webhook_url, json={"text": text}, timeout=15)
    if resp.status_code != 200:
        print(f"[WARNING] Slack post failed: {resp.status_code} {resp.text}")


# ── Reconciliation ─────────────────────────────────────────────────────────
def parse_amount(value: str) -> float | None:
    try:
        cleaned = value.replace(",", "").replace("$", "").replace("USD", "").replace("SGD", "").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def normalize_period(period: str) -> str:
    """Normalize period to YYYY-MM. Handles both '2026-03' and '202603'."""
    p = period.strip().replace("-", "")
    if len(p) == 6 and p.isdigit():
        return f"{p[:4]}-{p[4:]}"
    return period.strip()


def build_invoice_lookup(invoice_rows: list[dict], ic: dict, billing_period: str, new_only: bool = False) -> dict:
    """Build {contractor_code: row} lookup filtered to billing_period. Normalizes period format.
    If new_only=True, skips rows that already have a Status value (already processed).
    """
    lookup = {}
    for row in invoice_rows:
        code = row.get(ic["contractor_code"], "").strip()
        period = normalize_period(row.get(ic["period"], ""))
        if not code or period != billing_period:
            continue
        if new_only and row.get(ic.get("status", "Status"), "").strip():
            continue
        lookup[code] = row
    return lookup


def reconcile(
    tracker_rows: list[dict],
    invoice_lookup: dict,
    cfg: dict,
    billing_period: str,
) -> tuple[list, list]:
    """
    Submission-driven reconciliation: only processes EPs who submitted an invoice.
    EPs in the tracker with no submission are silently skipped.
    Expected total = EP services (from tracker) + reimbursements (from invoice form).
    Returns: (matched, mismatches)
    """
    tc = cfg["time_tracker"]["columns"]
    ic = cfg["invoice_submissions"]["columns"]
    tolerance = cfg["matching"].get("amount_tolerance", 0.01)
    excluded = set(cfg["matching"].get("excluded_contractors", []))

    # Build tracker lookup by contractor code
    tracker_lookup: dict[str, dict] = {}
    for row in tracker_rows:
        code = row.get(tc["contractor_code"], "").strip()
        if code and code not in excluded:
            tracker_lookup[code] = row

    matched = []
    mismatches = []

    for code, inv in invoice_lookup.items():
        # Skip invalid or excluded contractor codes
        if not code or code == "#N/A" or code in excluded:
            continue

        ic_full_name = inv.get(ic.get("full_name", "Full Name"), "").strip()
        ep_name = ic_full_name or code

        invoice_amount = parse_amount(inv.get(ic["amount"], ""))
        if invoice_amount is None:
            mismatches.append({
                "contractor_code": code,
                "ep_name": ep_name,
                "period": billing_period,
                "reason": f"Could not parse invoice amount: '{inv.get(ic['amount'])}'",
            })
            continue

        # Reimbursements (optional line items beyond EP services)
        reimb_amount = parse_amount(inv.get(ic.get("reimbursement_amount", ""), "")) or 0.0
        reimb_desc = inv.get(ic.get("reimbursement_description", ""), "").strip().splitlines()[0].strip() if inv.get(ic.get("reimbursement_description", ""), "") else ""

        # Validate against tracker if EP is a standard contractor (warning only — does not block payment)
        # Tracker total already includes reimbursements, so compare directly against invoice total.
        tracker_warning = None
        tracker_row = tracker_lookup.get(code)
        if tracker_row is not None:
            tracker_amount = parse_amount(tracker_row.get(billing_period, ""))
            if tracker_amount is not None and tracker_amount > 0:
                if abs(tracker_amount - invoice_amount) > tolerance:
                    tracker_warning = (
                        f"Tracker vs invoice discrepancy — tracker: {tracker_amount:.2f}, "
                        f"invoice: {invoice_amount:.2f}"
                    )

        matched.append({
            "contractor_code": code,
            "ep_name": ep_name,
            "email": inv.get(ic["email"], "").strip(),
            "amount": invoice_amount,
            "ep_services_amount": round(invoice_amount - reimb_amount, 2),
            "reimbursement_amount": reimb_amount,
            "reimbursement_description": reimb_desc,
            "tracker_warning": tracker_warning,
            "period": billing_period,
        })

    return matched, mismatches


# ── Receipts ───────────────────────────────────────────────────────────────
def save_receipts(billing_period: str, payments: list[dict], issues: list[dict]) -> None:
    folder = RECEIPTS_DIR / billing_period
    folder.mkdir(parents=True, exist_ok=True)

    if payments:
        path = folder / f"payment-receipt-{billing_period}.json"
        path.write_text(json.dumps(payments, indent=2))
        print(f"  [RECEIPT] Payments → {path}")

    if issues:
        path = folder / f"mismatch-report-{billing_period}.json"
        path.write_text(json.dumps(issues, indent=2))
        print(f"  [RECEIPT] Issues → {path}")


# ── Main ───────────────────────────────────────────────────────────────────
def get_pending_path(billing_period: str) -> Path:
    return RECEIPTS_DIR / billing_period / f"pending-approval-{billing_period}.json"


def main():
    parser = argparse.ArgumentParser(description="Process EP invoices and submit payments via Airwallex")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no writes, no Slack post")
    parser.add_argument("--post", action="store_true", help="Step 2 — reconcile and post Slack approval summary")
    parser.add_argument("--confirm", action="store_true", help="Step 3 — submit payments from pending approval file")
    parser.add_argument("--status", action="store_true", help="Show status of recent Airwallex transfers")
    parser.add_argument("--contractor-code", help="Process a single EP by contractor code")
    parser.add_argument("--period", help="Override billing period as YYYY-MM (default: previous month)")
    args = parser.parse_args()

    cfg = load_config()
    billing_period = get_billing_period(args.period)

    airwallex_client_id = os.getenv("AIRWALLEX_CLIENT_ID", "")
    airwallex_api_key = os.getenv("AIRWALLEX_API_KEY", "")
    slack_webhook = os.getenv(cfg["slack"]["webhook_url_env"], "")
    slack_tag = cfg["slack"].get("tag", "")

    if not airwallex_client_id or not airwallex_api_key:
        print("[ERROR] AIRWALLEX_CLIENT_ID and AIRWALLEX_API_KEY must be set in .env")
        sys.exit(1)

    # ── STATUS CHECK ─────────────────────────────────────────────────────
    if args.status:
        airwallex_env = cfg["airwallex"].get("environment", "production")
        base_url = AIRWALLEX_URLS.get(airwallex_env, AIRWALLEX_URLS["production"])
        token = airwallex_login(base_url, airwallex_client_id, airwallex_api_key)

        resp = requests.get(
            f"{base_url}/api/v1/transfers",
            headers={"Authorization": f"Bearer {token}"},
            params={"page_num": 0, "page_size": 50},
            timeout=30,
        )
        resp.raise_for_status()
        transfers = resp.json().get("items", [])

        current_month = datetime.now().strftime("%Y-%m")
        transfers = [t for t in transfers if t.get("created_at", "").startswith(current_month)]

        groups = {}
        for t in transfers:
            s = t.get("status", "UNKNOWN")
            groups.setdefault(s, []).append(t)

        status_emoji = {
            "PENDING": ":hourglass_flowing_sand:",
            "SUBMITTED": ":arrows_counterclockwise:",
            "APPROVAL_PENDING": ":memo:",
            "APPROVAL_RECALLED": ":x:",
            "REJECTED": ":x:",
            "CANCELLED": ":no_entry:",
            "COMPLETED": ":white_check_mark:",
        }

        print(f"\nAirwallex Transfer Status — {current_month} ({len(transfers)} transfer(s))\n")
        for status, items in sorted(groups.items()):
            print(f"{status} ({len(items)})")
            for t in items:
                name = t.get("beneficiary", {}).get("bank_details", {}).get("account_name", "—")
                ref = t.get("reference", "—")
                amount = t.get("transfer_amount", 0)
                currency = t.get("transfer_currency", "")
                date = t.get("created_at", "")[:10]
                print(f"  {date}  {ref:<35}  {currency} {amount:>10,.2f}  {name}")
            print()

        if slack_webhook:
            lines = [f"{slack_tag} :bar_chart: *Airwallex Transfer Status — {current_month}*\n"]
            for status, items in sorted(groups.items()):
                emoji = status_emoji.get(status, ":grey_question:")
                lines.append(f"{emoji} *{status}* ({len(items)})")
                for t in items:
                    ref = t.get("reference", "—")
                    amount = t.get("transfer_amount", 0)
                    currency = t.get("transfer_currency", "")
                    date = t.get("created_at", "")[:10]
                    lines.append(f"  {date} · {ref} · {currency} {amount:,.2f}")
                lines.append("")
            post_to_slack(slack_webhook, "\n".join(lines))
            print("  [SLACK] Status posted")
        return

    # ── PHASE 2: Confirm and submit ──────────────────────────────────────
    if args.confirm:
        pending_path = get_pending_path(billing_period)
        if not pending_path.exists():
            print(f"[ERROR] No pending approval file found at {pending_path}")
            print("  Run without --confirm first to generate the approval summary.")
            sys.exit(1)

        pending = json.loads(pending_path.read_text())
        matched = pending["matched"]
        billing_period = pending["billing_period"]
        currency = pending["currency"]
        issues = pending.get("issues", [])

        if args.contractor_code:
            matched = [ep for ep in matched if ep["contractor_code"] == args.contractor_code]
            if not matched:
                print(f"[ERROR] No pending payment found for contractor code: {args.contractor_code}")
                sys.exit(1)
            print(f"  Filtered to: {args.contractor_code}")

        print(f"\nConfirming payment for billing period: {billing_period}")
        print(f"Submitting {len(matched)} payment(s) to Airwallex...\n")

        airwallex_env = cfg["airwallex"].get("environment", "production")
        base_url = AIRWALLEX_URLS.get(airwallex_env, AIRWALLEX_URLS["production"])
        token = airwallex_login(base_url, airwallex_client_id, airwallex_api_key)

        match_field = cfg["airwallex"].get("beneficiary_match_field", "nickname")
        default_ref_template = cfg["airwallex"].get("reference_template", "CLI-{contractor_code}-{period_compact}-EP")
        ep_overrides = cfg["airwallex"].get("ep_overrides", {})
        period_compact = billing_period.replace("-", "")

        beneficiaries = get_beneficiaries(base_url, token)

        payment_receipts = []
        payment_errors = []

        for ep in matched:
            code = ep["contractor_code"]
            name = ep["ep_name"]
            amount = ep["amount"]

            beneficiary = find_beneficiary(beneficiaries, code, match_field)
            if not beneficiary:
                payment_errors.append({
                    "contractor_code": code, "ep_name": name, "amount": amount,
                    "reason": f"Beneficiary not found for '{code}'",
                })
                print(f"  [SKIP] {name} ({code}) — beneficiary not found")
                continue

            try:
                override = ep_overrides.get(code, {})
                ref_tmpl = override.get("reference_template", default_ref_template)
                fmt = {
                    "contractor_code": code,
                    "ep_name": name,
                    "period": billing_period,
                    "period_compact": period_compact,
                }
                reference = ref_tmpl.format(**fmt)
                transfer_method = get_transfer_method(beneficiary)

                result = submit_payment(
                    base_url, token,
                    beneficiary_id=beneficiary["id"],
                    amount=amount,
                    currency=currency,
                    transfer_method=transfer_method,
                    reason="professional_business_services",
                    purpose="professional_business_services",
                    reference=reference,
                    dry_run=False,
                )
                print(f"  [PAID] {name} ({code}) — {currency} {amount:.2f}")
                payment_receipts.append({
                    "contractor_code": code,
                    "ep_name": name,
                    "email": ep["email"],
                    "amount": amount,
                    "ep_services_amount": ep.get("ep_services_amount", amount),
                    "reimbursement_amount": ep.get("reimbursement_amount", 0.0),
                    "reimbursement_description": ep.get("reimbursement_description", ""),
                    "currency": currency,
                    "period": billing_period,
                    "beneficiary_id": beneficiary["id"],
                    "airwallex_response": result,
                    "timestamp": datetime.now().isoformat(),
                })
            except requests.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.response.json()
                except Exception:
                    error_body = e.response.text if e.response else ""
                payment_errors.append({
                    "contractor_code": code, "ep_name": name, "amount": amount,
                    "reason": f"Payment failed: {e}",
                })
                print(f"  [ERROR] {name} ({code}) — {e}")
                print(f"          Airwallex response: {error_body}")

        total_paid = sum(r["amount"] for r in payment_receipts)
        summary_lines = [
            f":white_check_mark: *EP Payments Submitted — {billing_period}*",
            f"• Paid: {len(payment_receipts)} ({currency} {total_paid:,.2f})",
            f"• Skipped (reconciliation issues): {len(issues)}",
            f"• Skipped (payment errors): {len(payment_errors)}",
            f"\nPayments are pending Ivan's approval in Airwallex.",
        ]
        if payment_errors and slack_webhook:
            err_lines = [f"{slack_tag} :x: *EP Payment Errors — {billing_period}*\n"]
            for err in payment_errors:
                err_lines.append(f"• *{err['ep_name']}* ({err['contractor_code']}): {err['reason']}")
            post_to_slack(slack_webhook, "\n".join(err_lines))

        if slack_webhook:
            post_to_slack(slack_webhook, "\n".join(summary_lines))
            print(f"\n  [SLACK] Summary posted")

        print("\n" + "\n".join(summary_lines))
        save_receipts(billing_period, payment_receipts, issues + payment_errors)

        # If filtered by contractor code, remove only processed EPs from pending.
        # Otherwise delete the full pending file.
        processed_codes = {r["contractor_code"] for r in payment_receipts}
        if args.contractor_code:
            remaining = [ep for ep in pending["matched"] if ep["contractor_code"] not in processed_codes]
            if remaining:
                pending["matched"] = remaining
                pending_path.write_text(json.dumps(pending, indent=2))
                print(f"  [PENDING] {len(remaining)} EP(s) still in queue → {pending_path}")
            else:
                pending_path.unlink(missing_ok=True)
                print("  [PENDING] All EPs processed — pending file cleared.")
        else:
            pending_path.unlink(missing_ok=True)

        print("\nDone.")
        return

    # ── STEP 1 (default): Parse submissions → log reimbursements to HRIS ───
    if not args.post and not args.confirm and not args.status:
        if args.dry_run:
            print("\n[DRY RUN MODE] No writes to HRIS.\n")

        print(f"Billing period: {billing_period}\n")
        print("Authenticating with Google...")
        sheets_service, _ = get_google_services()

        print("Reading invoice submissions...")
        invoice_rows = read_sheet(
            sheets_service,
            cfg["invoice_submissions"]["sheet_id"],
            cfg["invoice_submissions"]["tab_name"],
            header_row=cfg["invoice_submissions"].get("header_row", 1),
        )

        ic = cfg["invoice_submissions"]["columns"]
        excluded = set(cfg["matching"].get("excluded_contractors", []))

        if args.contractor_code:
            invoice_rows = [r for r in invoice_rows if r.get(ic["contractor_code"], "").strip() == args.contractor_code]

        invoice_lookup = build_invoice_lookup(invoice_rows, ic, billing_period, new_only=True)

        # Filter to valid contractor codes only
        valid = {
            code: inv for code, inv in invoice_lookup.items()
            if code and code != "#N/A" and code not in excluded
        }

        print(f"  {len(valid)} new submission(s) (no Status) for {billing_period}\n")

        if not valid:
            print("No valid submissions found for this period. Exiting.")
            return

        # Print all submissions
        currency = cfg["airwallex"].get("currency", "USD")
        for code, inv in valid.items():
            name = inv.get(ic.get("full_name", "Full Name"), code).strip()
            amount = inv.get(ic["amount"], "—")
            reimb = inv.get(ic.get("reimbursement_amount", ""), "").strip()
            reimb_desc = inv.get(ic.get("reimbursement_description", ""), "").strip()
            reimb_val = parse_amount(reimb) if reimb else None
            reimb_note = f"  (incl. {currency} {reimb_val:.2f} — {reimb_desc})" if reimb_val and reimb_val > 0 else ""
            print(f"  {name} ({code}) — {currency} {amount}{reimb_note}")

        # Collect reimbursements to log
        reimbursements_to_log = []
        for code, inv in valid.items():
            name = inv.get(ic.get("full_name", "Full Name"), code).strip()
            raw_reimb = inv.get(ic.get("reimbursement_amount", ""), "").strip()
            reimb_amount = parse_amount(raw_reimb) if raw_reimb else None
            reimb_desc = inv.get(ic.get("reimbursement_description", ""), "").strip()
            if reimb_amount and reimb_amount > 0:
                reimbursements_to_log.append({
                    "period": billing_period,
                    "contractor_code": code,
                    "ep_name": name,
                    "description": reimb_desc or "Reimbursement",
                    "amount": reimb_amount,
                })

        if not reimbursements_to_log:
            print("\nNo reimbursements to log for this period.")
        elif args.dry_run:
            print(f"\n[DRY RUN] Would log {len(reimbursements_to_log)} reimbursement(s) to HRIS:")
            for r in reimbursements_to_log:
                print(f"  {r['ep_name']} ({r['contractor_code']}) — {currency} {r['amount']:.2f}: {r['description']}")
        else:
            print(f"\nLogging {len(reimbursements_to_log)} reimbursement(s) to HRIS...")
            hris_cfg = cfg.get("hris", {})
            write_reimbursements_to_hris(
                sheets_service,
                hris_cfg.get("sheet_id", cfg["time_tracker"]["sheet_id"]),
                hris_cfg.get("reimbursements_tab", "Reimbursements"),
                reimbursements_to_log,
            )
            print("\nReimbursements logged. Verify in the HRIS Reimbursements tab, then run:")
            print("  python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --post")

        print("\nDone.")
        return

    # ── STEP 2 (--post): Reconcile, bank check, post Slack approval ────────
    if args.post:
        if args.dry_run:
            print("\n[DRY RUN MODE] No Slack post, no files saved.\n")

        print(f"Billing period: {billing_period}\n")
        print("Authenticating with Google...")
        sheets_service, drive_service = get_google_services()

        print("Reading Google Sheets...")
        tracker_rows = read_sheet(
            sheets_service,
            cfg["time_tracker"]["sheet_id"],
            cfg["time_tracker"]["tab_name"],
            header_row=cfg["time_tracker"].get("header_row", 1),
        )
        print(f"  Time tracker:        {len(tracker_rows)} row(s)")

        invoice_rows = read_sheet(
            sheets_service,
            cfg["invoice_submissions"]["sheet_id"],
            cfg["invoice_submissions"]["tab_name"],
            header_row=cfg["invoice_submissions"].get("header_row", 1),
        )
        print(f"  Invoice submissions: {len(invoice_rows)} row(s)")

        if args.contractor_code:
            tc_col = cfg["time_tracker"]["columns"]["contractor_code"]
            ic_col = cfg["invoice_submissions"]["columns"]["contractor_code"]
            tracker_rows = [r for r in tracker_rows if r.get(tc_col, "").strip() == args.contractor_code]
            invoice_rows = [r for r in invoice_rows if r.get(ic_col, "").strip() == args.contractor_code]
            print(f"  Filtered to: {args.contractor_code}")

        ic = cfg["invoice_submissions"]["columns"]
        invoice_lookup = build_invoice_lookup(invoice_rows, ic, billing_period, new_only=True)

        print(f"\nReconciling...")
        matched, mismatches = reconcile(tracker_rows, invoice_lookup, cfg, billing_period)
        issues = mismatches

        print(f"  Matched:    {len(matched)}")
        print(f"  Mismatches: {len(mismatches)}")

        currency = cfg["airwallex"].get("currency", "USD")
        total = sum(ep["amount"] for ep in matched)

        if not matched:
            print("\nNo matched EPs to pay. Exiting.")
            return

        # Bank verification (silent unless mismatch found)
        bank_issues = []
        if not args.dry_run:
            tc = cfg["time_tracker"]["columns"]
            ep_name_lookup = {
                row.get(tc["contractor_code"], "").strip(): (
                    f"{row.get(tc['first_name'], '').strip()} {row.get(tc['last_name'], '').strip()}".strip()
                )
                for row in tracker_rows
                if row.get(tc["contractor_code"], "").strip()
            }

            print("\nChecking bank details against Airwallex...")
            airwallex_env = cfg["airwallex"].get("environment", "production")
            base_url = AIRWALLEX_URLS.get(airwallex_env, AIRWALLEX_URLS["production"])
            token = airwallex_login(base_url, airwallex_client_id, airwallex_api_key)
            beneficiaries = get_beneficiaries(base_url, token)

            bank_issues = run_bank_verification(
                invoice_lookup, drive_service, beneficiaries, cfg, ep_name_lookup
            )
        else:
            print("\n[DRY RUN] Bank verification skipped.")

        if not args.dry_run:
            # Post bank mismatches (only if any)
            if bank_issues and slack_webhook:
                lines = [f"{slack_tag} :bank: *Bank Detail Mismatch — {billing_period}*\n"]
                for issue in bank_issues:
                    flagged = issue.get("bank_changed_flag", "").lower()
                    flag_note = (
                        " _(flagged bank change on form)_" if "yes" in flagged
                        else " _(did NOT flag bank change on form)_"
                    )
                    lines.append(
                        f"• *{issue['ep_name']}* ({issue['contractor_code']}){flag_note}: {issue['reason']}"
                    )
                lines.append("\nPlease verify before approving payment.")
                post_to_slack(slack_webhook, "\n".join(lines))

            # Post reconciliation issues
            if issues and slack_webhook:
                lines = [f"{slack_tag} :warning: *EP Invoice Issues — {billing_period}*\n"]
                for issue in issues:
                    lines.append(f"• *{issue['ep_name']}* ({issue['contractor_code']}): {issue['reason']}")
                lines.append("\nThese EPs have been skipped.")
                post_to_slack(slack_webhook, "\n".join(lines))

            # Post approval request
            if matched and slack_webhook:
                lines = [
                    f"{slack_tag} :memo: *EP Invoice Approval — {billing_period}*",
                    f"Reconciliation complete. *{len(matched)} payment(s) ready* — {currency} {total:,.2f} total\n",
                    "*Review list:*",
                ]
                for i, ep in enumerate(matched, 1):
                    reimb = ep.get("reimbursement_amount", 0)
                    if reimb > 0:
                        desc = ep.get("reimbursement_description") or "reimbursement"
                        line = (
                            f"{i}. *{ep['ep_name']}* ({ep['contractor_code']}) — "
                            f"{currency} {ep['amount']:,.2f} "
                            f"_(services: {ep['ep_services_amount']:,.2f} + {desc}: {reimb:,.2f})_"
                        )
                    else:
                        line = f"{i}. *{ep['ep_name']}* ({ep['contractor_code']}) — {currency} {ep['amount']:,.2f}"
                    if ep.get("tracker_warning"):
                        line += f"\n   :warning: _{ep['tracker_warning']}_"
                    lines.append(line)
                lines.append("\n---")
                lines.append("Everything looks good? Tell Claude: *Process invoices on Airwallex*")
                lines.append("Something's off? Tell Claude: *Skip [number or ContractorCode] and process the rest*")
                post_to_slack(slack_webhook, "\n".join(lines))
                print(f"\n  [SLACK] Approval request posted")

            # Save pending file
            pending_path = get_pending_path(billing_period)
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.write_text(json.dumps({
                "billing_period": billing_period,
                "currency": currency,
                "matched": matched,
                "issues": issues,
                "created_at": datetime.now().isoformat(),
            }, indent=2))
            print(f"  [PENDING] Saved → {pending_path}")
        else:
            # Dry run: print the exact Slack message that would be sent
            preview_lines = [
                f"[PREVIEW — not posted to Slack]\n",
                f"@Dyan :memo: *EP Invoice Approval — {billing_period}*",
                f"Reconciliation complete. *{len(matched)} payment(s) ready* — {currency} {total:,.2f} total\n",
                "*Review list:*",
            ]
            for i, ep in enumerate(matched, 1):
                reimb = ep.get("reimbursement_amount", 0)
                if reimb > 0:
                    desc = ep.get("reimbursement_description") or "reimbursement"
                    line = (
                        f"{i}. *{ep['ep_name']}* ({ep['contractor_code']}) — "
                        f"{currency} {ep['amount']:,.2f} "
                        f"_(services: {ep['ep_services_amount']:,.2f} + {desc}: {reimb:,.2f})_"
                    )
                else:
                    line = f"{i}. *{ep['ep_name']}* ({ep['contractor_code']}) — {currency} {ep['amount']:,.2f}"
                if ep.get("tracker_warning"):
                    line += f"\n   ⚠ {ep['tracker_warning']}"
                preview_lines.append(line)
            preview_lines.append("\n---")
            preview_lines.append("Everything looks good? Tell Claude: *Process invoices on Airwallex*")
            preview_lines.append("Something's off? Tell Claude: *Skip [number or ContractorCode] and process the rest*")
            print("\n" + "\n".join(preview_lines))

        print(f"\nTotal ready to pay: {currency} {total:,.2f} across {len(matched)} EP(s)")
        if not args.dry_run:
            print("Review the Slack message, then run:")
            print("  python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --confirm")
        print("\nDone.")
        return


if __name__ == "__main__":
    main()
