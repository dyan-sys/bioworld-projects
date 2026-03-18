"""
Process EP Invoices

Reconciles EP invoice submissions against the time tracker sheet,
then submits matched payments via Airwallex API.

Usage:
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --dry-run
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --contractor-code EP001
    python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --period 2026-02
"""

import argparse
import json
import os
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

# ── Paths ──────────────────────────────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SKILL_ROOT.parents[2]

load_dotenv(PROJECT_ROOT / ".env")

CONFIG_PATH = SKILL_ROOT / "templates" / "ep-invoice-config.json"
RECEIPTS_DIR = PROJECT_ROOT / "local-data" / "invoices"
TOKEN_PATH = PROJECT_ROOT / "google_token_sheets.json"

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

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


# ── Google Sheets auth ─────────────────────────────────────────────────────
def get_sheets_service():
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

    return build("sheets", "v4", credentials=creds)


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


def submit_payment(base_url: str, token: str, beneficiary_id: str, amount: float, currency: str, transfer_method: str, reason: str, purpose: str, reference: str, description: str, dry_run: bool) -> dict:
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
        "description": description,
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


def reconcile(tracker_rows: list[dict], invoice_rows: list[dict], cfg: dict, billing_period: str) -> tuple[list, list, list]:
    """
    Match tracker vs invoices by contractor_code for the given billing period (YYYY-MM).
    Returns: (matched, mismatches, missing_invoices)
    """
    tc = cfg["time_tracker"]["columns"]
    ic = cfg["invoice_submissions"]["columns"]
    tolerance = cfg["matching"].get("amount_tolerance", 0.01)
    excluded = set(cfg["matching"].get("excluded_contractors", []))

    # Build invoice lookup by contractor code, filtered to billing period
    invoice_lookup: dict[str, dict] = {}
    for row in invoice_rows:
        code = row.get(ic["contractor_code"], "").strip()
        period = row.get(ic["period"], "").strip()
        if code and period == billing_period:
            invoice_lookup[code] = row

    matched = []
    mismatches = []
    missing_invoices = []

    for row in tracker_rows:
        code = row.get(tc["contractor_code"], "").strip()
        first_name = row.get(tc["first_name"], "").strip()
        last_name = row.get(tc["last_name"], "").strip()
        ep_name = f"{first_name} {last_name}".strip() or code

        if code in excluded:
            continue

        # Amount is in the column named after the billing period (e.g. "2026-02")
        tracker_amount = parse_amount(row.get(billing_period, ""))

        if not code:
            continue

        if tracker_amount is None:
            # No entry for this period — EP may not have worked that month
            continue

        if tracker_amount == 0:
            continue

        if code not in invoice_lookup:
            missing_invoices.append({
                "contractor_code": code,
                "ep_name": ep_name,
                "tracker_amount": tracker_amount,
                "period": billing_period,
                "reason": "No invoice submitted for this period",
            })
            continue

        inv = invoice_lookup[code]
        invoice_amount = parse_amount(inv.get(ic["amount"], ""))

        if invoice_amount is None:
            mismatches.append({
                "contractor_code": code,
                "ep_name": ep_name,
                "tracker_amount": tracker_amount,
                "invoice_amount": None,
                "period": billing_period,
                "reason": f"Could not parse invoice amount: '{inv.get(ic['amount'])}'",
            })
            continue

        if abs(tracker_amount - invoice_amount) > tolerance:
            mismatches.append({
                "contractor_code": code,
                "ep_name": ep_name,
                "tracker_amount": tracker_amount,
                "invoice_amount": invoice_amount,
                "period": billing_period,
                "reason": f"Amount mismatch — tracker: {tracker_amount}, invoice: {invoice_amount}",
            })
            continue

        matched.append({
            "contractor_code": code,
            "ep_name": ep_name,
            "email": inv.get(ic["email"], "").strip(),
            "amount": tracker_amount,
            "period": billing_period,
        })

    return matched, mismatches, missing_invoices


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
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no Slack post, no pending file saved")
    parser.add_argument("--confirm", action="store_true", help="Submit payments from the saved pending approval file")
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

        # Filter to current month only
        current_month = datetime.now().strftime("%Y-%m")
        transfers = [t for t in transfers if t.get("created_at", "").startswith(current_month)]

        # Group by status
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
            emoji = status_emoji.get(status, ":grey_question:")
            print(f"{status} ({len(items)})")
            for t in items:
                name = t.get("beneficiary", {}).get("bank_details", {}).get("account_name", "—")
                ref = t.get("reference", "—")
                amount = t.get("transfer_amount", 0)
                currency = t.get("transfer_currency", "")
                date = t.get("created_at", "")[:10]
                print(f"  {date}  {ref:<35}  {currency} {amount:>10,.2f}  {name}")
            print()

        # Post to Slack
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
            print(f"  Run without --confirm first to generate the approval summary.")
            sys.exit(1)

        pending = json.loads(pending_path.read_text())
        matched = pending["matched"]
        billing_period = pending["billing_period"]
        currency = pending["currency"]
        issues = pending.get("issues", [])

        print(f"\nConfirming payment for billing period: {billing_period}")
        print(f"Submitting {len(matched)} payment(s) to Airwallex...\n")

        airwallex_env = cfg["airwallex"].get("environment", "production")
        base_url = AIRWALLEX_URLS.get(airwallex_env, AIRWALLEX_URLS["production"])
        token = airwallex_login(base_url, airwallex_client_id, airwallex_api_key)

        match_field = cfg["airwallex"].get("beneficiary_match_field", "nickname")
        reason = cfg["airwallex"].get("payment_reason", "EP Invoice Payment")
        purpose = cfg["airwallex"].get("purpose_of_transfer", "PROFESSIONAL_BUSINESS_SERVICES")
        default_ref_template = cfg["airwallex"].get("reference_template", "CLI-{contractor_code}-{period_compact}-EP")
        default_desc_template = cfg["airwallex"].get("description_template", "CLI-{contractor_code}-{period_compact}-EP")
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
                payment_errors.append({"contractor_code": code, "ep_name": name, "amount": amount,
                                       "reason": f"Beneficiary not found for '{code}'"})
                print(f"  [SKIP] {name} ({code}) — beneficiary not found")
                continue

            try:
                override = ep_overrides.get(code, {})
                ref_tmpl = override.get("reference_template", default_ref_template)
                desc_tmpl = override.get("description_template", default_desc_template)
                fmt = {"contractor_code": code, "ep_name": name, "period": billing_period, "period_compact": period_compact}
                reference = ref_tmpl.format(**fmt)
                transfer_methods = beneficiary.get("transfer_methods", [])
                transfer_method = transfer_methods[0] if transfer_methods else "LOCAL"
                result = submit_payment(
                    base_url, token,
                    beneficiary_id=beneficiary["id"],
                    amount=amount,
                    currency=currency,
                    transfer_method=transfer_method,
                    reason="professional_business_services",
                    purpose="professional_business_services",
                    reference=reference,
                    description=reference,
                    dry_run=False,
                )
                print(f"  [PAID] {name} ({code}) — {currency} {amount:.2f}")
                payment_receipts.append({
                    "contractor_code": code, "ep_name": name, "email": ep["email"],
                    "amount": amount, "currency": currency, "period": billing_period,
                    "beneficiary_id": beneficiary["id"], "airwallex_response": result,
                    "timestamp": datetime.now().isoformat(),
                })
            except requests.HTTPError as e:
                error_body = ""
                try:
                    error_body = e.response.json()
                except Exception:
                    error_body = e.response.text if e.response else ""
                payment_errors.append({"contractor_code": code, "ep_name": name, "amount": amount,
                                       "reason": f"Payment failed: {e}"})
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

        # Remove pending file now that it's been processed
        pending_path.unlink(missing_ok=True)
        print("\nDone.")
        return

    # ── PHASE 1: Reconcile and post for approval ─────────────────────────
    if args.dry_run:
        print("\n[DRY RUN MODE] No Slack post, no pending file saved.\n")

    print(f"Billing period: {billing_period}\n")

    print("Reading Google Sheets...")
    sheets = get_sheets_service()

    tracker_rows = read_sheet(
        sheets,
        cfg["time_tracker"]["sheet_id"],
        cfg["time_tracker"]["tab_name"],
        header_row=cfg["time_tracker"].get("header_row", 1),
    )
    print(f"  Time tracker:        {len(tracker_rows)} row(s)")

    invoice_rows = read_sheet(
        sheets,
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

    print(f"\nReconciling...")
    matched, mismatches, missing_invoices = reconcile(tracker_rows, invoice_rows, cfg, billing_period)
    issues = mismatches + missing_invoices

    print(f"  Matched:          {len(matched)}")
    print(f"  Mismatches:       {len(mismatches)}")
    print(f"  Missing invoices: {len(missing_invoices)}")

    currency = cfg["airwallex"].get("currency", "USD")
    total = sum(ep["amount"] for ep in matched)

    if not args.dry_run:
        # Post issues to Slack
        if issues and slack_webhook:
            lines = [f"{slack_tag} :warning: *EP Invoice Issues — {billing_period}*\n"]
            for issue in issues:
                lines.append(f"• *{issue['ep_name']}* ({issue['contractor_code']}): {issue['reason']}")
            lines.append("\nThese EPs have been skipped.")
            post_to_slack(slack_webhook, "\n".join(lines))

        # Post approval request to Slack
        if matched and slack_webhook:
            lines = [
                f"{slack_tag} :memo: *EP Invoice Approval — {billing_period}*",
                f"Reconciliation complete. *{len(matched)} payment(s) ready* — {currency} {total:,.2f} total\n",
                f"*Review list:*",
            ]
            for i, ep in enumerate(matched, 1):
                lines.append(f"{i}. *{ep['ep_name']}* ({ep['contractor_code']}) — {currency} {ep['amount']:,.2f}")
            lines.append(f"\n---")
            lines.append(f"Everything looks good? Tell Claude: *Process invoices on Airwallex*")
            lines.append(f"Something's off? Tell Claude: *Skip [number or ContractorCode] and process the rest*")
            post_to_slack(slack_webhook, "\n".join(lines))
            print(f"\n  [SLACK] Approval request posted to Slack")

        # Save pending file
        if matched:
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
        # Dry run: just print what would happen
        if matched:
            print(f"\n[DRY RUN] Would post approval request to Slack for {len(matched)} payment(s):")
            for ep in matched:
                print(f"  {ep['ep_name']} ({ep['contractor_code']}) — {currency} {ep['amount']:,.2f}")

    if not matched:
        print("\nNo matched EPs to pay. Exiting.")
        return

    print(f"\nTotal ready to pay: {currency} {total:,.2f} across {len(matched)} EP(s)")
    if not args.dry_run:
        print(f"Review the Slack message in #ep-billing, then run:")
        print(f"  python3 .claude/skills/process-ep-invoices/workflows/process_ep_invoices.py --confirm")
    print("\nDone.")


if __name__ == "__main__":
    main()
