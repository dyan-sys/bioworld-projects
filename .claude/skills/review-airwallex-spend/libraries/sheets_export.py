"""
Google Sheets export for Airwallex spend review.

Creates (or updates) a spreadsheet styled as a dashboard:
- Overview: KPI tiles + category breakdown table with bars
- Subscriptions: recurring card vendors (the primary review surface)
- EP Payments: all EP payouts
- Other Spend: vendor invoices, reimbursements, FX, fees, refunds
- All Vendors: every vendor in one filterable table
- All Transactions: raw individual transactions

All data tabs get: frozen header, basic filter, conditional formatting on
status/decision columns, color scale on amount columns.

Auth uses the same Google credentials/token as process-ep-invoices
(reuses google_token_ep_invoices.json so no re-auth).
"""

import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parents[4]
TOKEN_PATH = PROJECT_ROOT / "google_token_ep_invoices.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ── Color palette ──────────────────────────────────────────────────────────
NAVY = {"red": 0.10, "green": 0.10, "blue": 0.18}
WHITE = {"red": 1, "green": 1, "blue": 1}
LIGHT_GREY = {"red": 0.96, "green": 0.96, "blue": 0.97}
SOFT_BLUE = {"red": 0.85, "green": 0.91, "blue": 0.98}
SOFT_GREEN = {"red": 0.84, "green": 0.93, "blue": 0.84}
SOFT_AMBER = {"red": 1.0, "green": 0.95, "blue": 0.78}
SOFT_RED = {"red": 0.98, "green": 0.83, "blue": 0.83}
SOFT_GREY = {"red": 0.90, "green": 0.90, "blue": 0.92}


# ── Auth ───────────────────────────────────────────────────────────────────
def get_services():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_path = os.getenv("GMAIL_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json"))
            if not Path(creds_path).exists():
                print(f"[ERROR] Google credentials not found at {creds_path}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds), build("drive", "v3", credentials=creds)


def create_spreadsheet(sheets, drive, title: str) -> str:
    body = {"properties": {"title": title}}
    return sheets.spreadsheets().create(body=body).execute()["spreadsheetId"]


# ── Tab management ─────────────────────────────────────────────────────────
def ensure_tab(sheets, sheet_id: str, tab_name: str) -> int:
    """Returns the sheetId (int) of the tab. Creates if missing."""
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    if tab_name not in existing:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    return existing[tab_name]


def clear_and_write(sheets, sheet_id: str, tab_name: str, rows: list[list]) -> None:
    sheets.spreadsheets().values().clear(spreadsheetId=sheet_id, range=tab_name).execute()
    if rows:
        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=tab_name,
            valueInputOption="USER_ENTERED",  # so SPARKLINE formulas render
            body={"values": rows},
        ).execute()


def delete_default_sheet(sheets, sheet_id: str, default_name: str = "Sheet1") -> None:
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    if len(meta["sheets"]) <= 1:
        return
    for s in meta["sheets"]:
        if s["properties"]["title"] == default_name:
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]},
            ).execute()
            return


# ── Formatting helpers ─────────────────────────────────────────────────────
def clear_formatting_request(sheet_id_int: int) -> dict:
    """Wipe all conditional formatting + filters on a sheet (used before re-applying)."""
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id_int},
            "fields": "title",  # no-op; we use this slot for sequencing only
        }
    }


def get_existing_filters_and_cf(sheets, sheet_id: str, sheet_id_int: int) -> list[dict]:
    """Build requests to delete existing basic filter, conditional formats, AND banded ranges
    on a tab. Required before re-applying formatting on subsequent runs."""
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id, ranges=[], includeGridData=False).execute()
    requests = []
    for s in meta["sheets"]:
        if s["properties"]["sheetId"] != sheet_id_int:
            continue
        if "basicFilter" in s:
            requests.append({"clearBasicFilter": {"sheetId": sheet_id_int}})
        n_cf = len(s.get("conditionalFormats", []) or [])
        for _ in range(n_cf):
            requests.append({"deleteConditionalFormatRule": {"sheetId": sheet_id_int, "index": 0}})
        # Delete existing banded ranges (can't re-add over them)
        for banded in s.get("bandedRanges", []) or []:
            requests.append({"deleteBanding": {"bandedRangeId": banded["bandedRangeId"]}})
        # Delete merged cells (so we can re-merge in different shapes)
        for merge in s.get("merges", []) or []:
            requests.append({"unmergeCells": {"range": merge}})
    return requests


def header_format_request(sheet_id_int: int, num_cols: int) -> list[dict]:
    return [
        # Header row: navy bg, white bold text
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id_int, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": num_cols},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": NAVY,
                    "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 11},
                    "verticalAlignment": "MIDDLE",
                    "padding": {"top": 6, "bottom": 6, "left": 8, "right": 8},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,padding)",
            }
        },
        # Freeze header
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id_int, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Banded rows for readability
        {
            "addBanding": {
                "bandedRange": {
                    "range": {"sheetId": sheet_id_int, "startRowIndex": 0, "startColumnIndex": 0, "endColumnIndex": num_cols},
                    "rowProperties": {
                        "headerColor": NAVY,
                        "firstBandColor": WHITE,
                        "secondBandColor": LIGHT_GREY,
                    },
                }
            }
        },
    ]


def status_conditional_format_requests(sheet_id_int: int, status_col: int, num_rows: int) -> list[dict]:
    """Color rows in the status column: ACTIVE green, STOPPED amber, ONE_OFF grey."""
    rules = []
    for value, color in [("ACTIVE", SOFT_GREEN), ("STOPPED", SOFT_AMBER), ("ONE_OFF", SOFT_GREY)]:
        rules.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id_int, "startRowIndex": 1, "endRowIndex": num_rows, "startColumnIndex": status_col, "endColumnIndex": status_col + 1}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
                        "format": {"backgroundColor": color, "textFormat": {"bold": True}},
                    },
                },
                "index": 0,
            }
        })
    return rules


def decision_conditional_format_requests(sheet_id_int: int, decision_col: int, num_rows: int) -> list[dict]:
    """Color decision cells: keep=green, cancel=red, renegotiate=amber."""
    rules = []
    for keyword, color in [("keep", SOFT_GREEN), ("cancel", SOFT_RED), ("renegotiate", SOFT_AMBER)]:
        rules.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id_int, "startRowIndex": 1, "endRowIndex": num_rows, "startColumnIndex": decision_col, "endColumnIndex": decision_col + 1}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": keyword}]},
                        "format": {"backgroundColor": color, "textFormat": {"bold": True}},
                    },
                },
                "index": 0,
            }
        })
    return rules


def amount_color_scale_request(sheet_id_int: int, col: int, num_rows: int) -> dict:
    """Add a color scale to a numeric column (red→white→green by sign)."""
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id_int, "startRowIndex": 1, "endRowIndex": num_rows, "startColumnIndex": col, "endColumnIndex": col + 1}],
                "gradientRule": {
                    "minpoint": {"color": SOFT_RED, "type": "MIN"},
                    "midpoint": {"color": WHITE, "type": "NUMBER", "value": "0"},
                    "maxpoint": {"color": SOFT_GREEN, "type": "MAX"},
                },
            },
            "index": 0,
        }
    }


def basic_filter_request(sheet_id_int: int, num_cols: int, num_rows: int) -> dict:
    return {
        "setBasicFilter": {
            "filter": {
                "range": {"sheetId": sheet_id_int, "startRowIndex": 0, "endRowIndex": num_rows, "startColumnIndex": 0, "endColumnIndex": num_cols},
            }
        }
    }


def auto_resize_request(sheet_id_int: int, num_cols: int) -> dict:
    return {
        "autoResizeDimensions": {
            "dimensions": {"sheetId": sheet_id_int, "dimension": "COLUMNS", "startIndex": 0, "endIndex": num_cols},
        }
    }


def write_data_tab(sheets, sheet_id: str, tab_name: str, rows: list[list], status_col: int | None = None, decision_col: int | None = None, amount_cols: list[int] | None = None) -> None:
    """Write rows + apply standard data-tab formatting (header, filter, conditional formats)."""
    sheet_id_int = ensure_tab(sheets, sheet_id, tab_name)
    # Clear existing filter + conditional formats (so re-runs don't stack them)
    clear_reqs = get_existing_filters_and_cf(sheets, sheet_id, sheet_id_int)
    if clear_reqs:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": clear_reqs}).execute()

    clear_and_write(sheets, sheet_id, tab_name, rows)

    if not rows:
        return

    num_cols = len(rows[0])
    num_rows = len(rows)

    requests = header_format_request(sheet_id_int, num_cols)
    requests.append(basic_filter_request(sheet_id_int, num_cols, num_rows))
    if status_col is not None:
        requests.extend(status_conditional_format_requests(sheet_id_int, status_col, num_rows))
    if decision_col is not None:
        requests.extend(decision_conditional_format_requests(sheet_id_int, decision_col, num_rows))
    if amount_cols:
        for c in amount_cols:
            requests.append(amount_color_scale_request(sheet_id_int, c, num_rows))
    requests.append(auto_resize_request(sheet_id_int, num_cols))

    sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": requests}).execute()


# ── Overview dashboard ─────────────────────────────────────────────────────
def write_overview_dashboard(sheets, sheet_id: str, vendor_rows: list[dict], transactions: list[dict], label: str, cards: list[dict] | None = None) -> None:
    """Build the Overview tab as a real dashboard with KPI tiles + category breakdown."""
    tab_name = "Overview"
    sheet_id_int = ensure_tab(sheets, sheet_id, tab_name)

    # Clear formatting first
    clear_reqs = get_existing_filters_and_cf(sheets, sheet_id, sheet_id_int)
    if clear_reqs:
        sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": clear_reqs}).execute()

    # Aggregate stats
    by_cat = defaultdict(lambda: {"vendors": 0, "txns": 0, "amounts": defaultdict(float)})
    for v in vendor_rows:
        cat = v.get("category", "Other")
        by_cat[cat]["vendors"] += 1
        by_cat[cat]["txns"] += v["charge_count"]
        for cur, amt in v.get("amounts_by_currency", {}).items():
            by_cat[cat]["amounts"][cur] += amt

    # KPI numbers
    active_subs = [v for v in vendor_rows if v.get("category") == "Card transactions" and v["status"] == "ACTIVE"]
    stopped_subs = [v for v in vendor_rows if v.get("category") == "Card transactions" and v["status"] == "STOPPED"]
    active_eps = [v for v in vendor_rows if v.get("category") == "EP Payment" and v["status"] == "ACTIVE"]
    annual_sub_runrate = sum(abs(v["annual_run_rate"]) for v in active_subs)
    annual_ep_runrate = sum(abs(v["annual_run_rate"]) for v in active_eps)
    total_card_spend = sum(abs(v["total_amount"]) for v in vendor_rows if v.get("category") == "Card transactions")

    # ── Build the rows array ──
    # Layout (1-indexed rows, columns A-G):
    # Row 1: title banner (merged A1:G1)
    # Row 2: subtitle (merged A2:G2)
    # Row 3: empty
    # Row 4-6: 4 KPI tiles in cols A:B, C:D, E:F, G (will merge after write)
    # Row 8: section header "Category breakdown"
    # Row 9: table headers
    # Row 10+: category rows

    rows = [
        ["AIRWALLEX SPEND REVIEW", "", "", "", "", "", ""],
        [f"{label}  ·  generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", "", "", "", "", "", ""],
        ["", "", "", "", "", "", ""],
        # KPI labels
        ["ACTIVE SUBSCRIPTIONS", "", "STOPPED SUBSCRIPTIONS", "", "ACTIVE EPs", "", "TOTAL CARD SPEND"],
        # KPI big values
        [f"{len(active_subs)}", "", f"{len(stopped_subs)}", "", f"{len(active_eps)}", "", f"USD {total_card_spend:,.0f}"],
        # KPI sub-text
        [f"USD {annual_sub_runrate:,.0f}/year", "", "potential cancellations", "", f"USD {annual_ep_runrate:,.0f}/year", "", f"({len(transactions)} transactions)"],
        ["", "", "", "", "", "", ""],
        ["CATEGORY BREAKDOWN", "", "", "", "", "", ""],
        ["Category", "Vendors", "Transactions", "Net amount(s)", "Spend bar", "", ""],
    ]

    # Find max abs amount across categories for the bar scale
    cat_totals = []
    for cat in by_cat:
        info = by_cat[cat]
        # Take USD amount if available, else sum of absolute amounts across currencies
        usd_amt = info["amounts"].get("USD", 0)
        magnitude = abs(usd_amt) if usd_amt else sum(abs(a) for a in info["amounts"].values())
        cat_totals.append((cat, magnitude))
    max_mag = max((m for _, m in cat_totals), default=1) or 1

    # Order categories by absolute USD spend for visual prominence
    ordered = sorted(by_cat.keys(), key=lambda c: -abs(by_cat[c]["amounts"].get("USD", sum(by_cat[c]["amounts"].values()) or 0)))

    for cat in ordered:
        info = by_cat[cat]
        amt_str = "; ".join(f"{cur} {amt:,.2f}" for cur, amt in sorted(info["amounts"].items()))
        usd_amt = info["amounts"].get("USD", 0)
        magnitude = abs(usd_amt) if usd_amt else sum(abs(a) for a in info["amounts"].values())
        # SPARKLINE bar — column E shows a horizontal bar proportional to spend
        bar_formula = f'=SPARKLINE({magnitude},{{"charttype","bar";"max",{max_mag};"color1","#4a6fa5"}})' if magnitude > 0 else ""
        rows.append([cat, info["vendors"], info["txns"], amt_str, bar_formula, "", ""])

    # Top 10 active subscriptions section
    rows.append(["", "", "", "", "", "", ""])
    rows.append(["TOP ACTIVE SUBSCRIPTIONS BY ANNUAL COST", "", "", "", "", "", ""])
    rows.append(["Vendor", "Charges", "Months", "Total", "Annual run-rate", "", ""])
    top_subs = sorted(active_subs, key=lambda r: abs(r["annual_run_rate"]), reverse=True)[:10]
    for v in top_subs:
        cur = v["currency"].split()[0] if v["currency"] else ""
        rows.append([v["vendor"], v["charge_count"], v["months_active"], f"{cur} {v['total_amount']:,.2f}", f"{cur} {v['annual_run_rate']:,.2f}", "", ""])
    if not top_subs:
        rows.append(["(none — fund a card and activity will appear here)", "", "", "", "", "", ""])

    # All subscriptions consolidated — Active vs Stopped shown via column instead of separate sections
    all_subs = active_subs + stopped_subs
    all_subs.sort(key=lambda r: abs(r["annual_run_rate"]) if r["status"] in ("ACTIVE", "STOPPED") else abs(r["total_amount"]), reverse=True)
    top_stopped = sorted(stopped_subs, key=lambda r: abs(r["total_amount"]), reverse=True)[:10]  # kept for section_header_rows arithmetic below
    rows.append(["", "", "", "", "", "", ""])
    rows.append(["ALL RECURRING SUBSCRIPTIONS — KEEP OR CANCEL?", "", "", "", "", "", ""])
    rows.append(["Vendor", "Active?", "Charges", "Months", "Total", "Annual run-rate", ""])
    for v in all_subs[:25]:
        cur = v["currency"].split()[0] if v["currency"] else ""
        rows.append([
            v["vendor"],
            "Yes" if v["status"] == "ACTIVE" else "No",
            v["charge_count"],
            v["months_active"],
            f"{cur} {v['total_amount']:,.2f}",
            f"{cur} {v['annual_run_rate']:,.2f}",
            "",
        ])
    if not all_subs:
        rows.append(["(no recurring subscriptions detected yet)", "", "", "", "", "", ""])

    # Cards section
    cards = cards or []
    rows.append(["", "", "", "", "", "", ""])
    rows.append(["AIRWALLEX CARDS", "", "", "", "", "", ""])
    rows.append(["Card name", "Holder", "Status", "Monthly limit", "Last 4", "Expires (mo)", "Notes"])
    for c in cards:
        rows.append([
            c.get("name", ""),
            c.get("holder", ""),
            c.get("status", ""),
            f"{c.get('limit_currency', '')} {c.get('monthly_limit', '')}/mo",
            c.get("last_four", "") or "—",
            c.get("expires_in_months", ""),
            "Main card" if c.get("is_main") else "",
        ])
    if not cards:
        rows.append(["(no cards configured — add to spend-config.json)", "", "", "", "", "", ""])

    clear_and_write(sheets, sheet_id, tab_name, rows)

    # ── Apply formatting ──
    requests = []

    # Title banner: row 1, merge A1:G1, navy bg, white huge text
    requests.append({"mergeCells": {"range": {"sheetId": sheet_id_int, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}})
    requests.append({"repeatCell": {
        "range": {"sheetId": sheet_id_int, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 7},
        "cell": {"userEnteredFormat": {
            "backgroundColor": NAVY,
            "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 18},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "padding": {"top": 12, "bottom": 12, "left": 12, "right": 12},
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,padding)",
    }})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id_int, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 56},
        "fields": "pixelSize",
    }})

    # Subtitle row
    requests.append({"mergeCells": {"range": {"sheetId": sheet_id_int, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}})
    requests.append({"repeatCell": {
        "range": {"sheetId": sheet_id_int, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 7},
        "cell": {"userEnteredFormat": {
            "backgroundColor": NAVY,
            "textFormat": {"foregroundColor": {"red": 0.7, "green": 0.7, "blue": 0.75}, "fontSize": 10},
            "horizontalAlignment": "CENTER",
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
    }})

    # KPI tiles — 4 tiles spanning cols A:B, C:D, E:F, G (single col)
    # Rows 4-6 (zero-indexed 3-5): label, value, subtext
    tile_cols = [(0, 2), (2, 4), (4, 6), (6, 7)]
    tile_colors = [SOFT_BLUE, SOFT_AMBER, SOFT_GREEN, SOFT_GREY]
    for (start_col, end_col), color in zip(tile_cols, tile_colors):
        # Merge each row of the tile across its columns
        for row_idx in [3, 4, 5]:
            requests.append({"mergeCells": {"range": {"sheetId": sheet_id_int, "startRowIndex": row_idx, "endRowIndex": row_idx + 1, "startColumnIndex": start_col, "endColumnIndex": end_col}, "mergeType": "MERGE_ALL"}})
        # Background color for entire tile
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id_int, "startRowIndex": 3, "endRowIndex": 6, "startColumnIndex": start_col, "endColumnIndex": end_col},
            "cell": {"userEnteredFormat": {"backgroundColor": color, "horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)",
        }})
        # Label row (small, uppercase already)
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id_int, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": start_col, "endColumnIndex": end_col},
            "cell": {"userEnteredFormat": {"textFormat": {"fontSize": 10, "bold": True, "foregroundColor": {"red": 0.3, "green": 0.3, "blue": 0.4}}, "padding": {"top": 8, "left": 8, "right": 8}}},
            "fields": "userEnteredFormat(textFormat,padding)",
        }})
        # Big value row
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id_int, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": start_col, "endColumnIndex": end_col},
            "cell": {"userEnteredFormat": {"textFormat": {"fontSize": 24, "bold": True, "foregroundColor": NAVY}}},
            "fields": "userEnteredFormat(textFormat)",
        }})
        # Subtext row
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id_int, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": start_col, "endColumnIndex": end_col},
            "cell": {"userEnteredFormat": {"textFormat": {"fontSize": 10, "italic": True, "foregroundColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}, "padding": {"bottom": 8}}},
            "fields": "userEnteredFormat(textFormat,padding)",
        }})

    # Tile row heights
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id_int, "dimension": "ROWS", "startIndex": 3, "endIndex": 4},
        "properties": {"pixelSize": 30}, "fields": "pixelSize"}})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id_int, "dimension": "ROWS", "startIndex": 4, "endIndex": 5},
        "properties": {"pixelSize": 50}, "fields": "pixelSize"}})
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": sheet_id_int, "dimension": "ROWS", "startIndex": 5, "endIndex": 6},
        "properties": {"pixelSize": 28}, "fields": "pixelSize"}})

    # Section headers (rows 8, top subs section, top stopped section)
    n_categories = len(ordered)
    section_header_rows = [
        7,  # "CATEGORY BREAKDOWN"
        7 + 1 + 1 + n_categories + 1,  # "TOP ACTIVE SUBSCRIPTIONS BY ANNUAL COST"
    ]
    # Compute remaining sections dynamically based on row counts
    n_top = max(len(top_subs), 1)
    n_all_subs = max(len(all_subs[:25]), 1)
    section_header_rows.append(section_header_rows[1] + 1 + 1 + n_top + 1)  # ALL RECURRING SUBSCRIPTIONS
    section_header_rows.append(section_header_rows[2] + 1 + 1 + n_all_subs + 1)  # AIRWALLEX CARDS

    for r in section_header_rows:
        requests.append({"mergeCells": {"range": {"sheetId": sheet_id_int, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": 7}, "mergeType": "MERGE_ALL"}})
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id_int, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": 7},
            "cell": {"userEnteredFormat": {
                "backgroundColor": NAVY,
                "textFormat": {"foregroundColor": WHITE, "bold": True, "fontSize": 12},
                "padding": {"top": 6, "bottom": 6, "left": 12},
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,padding)",
        }})

    # Table header rows for each section (the row right after each section header)
    table_header_rows = [r + 1 for r in section_header_rows]
    for r in table_header_rows:
        requests.append({"repeatCell": {
            "range": {"sheetId": sheet_id_int, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": 7},
            "cell": {"userEnteredFormat": {
                "backgroundColor": LIGHT_GREY,
                "textFormat": {"bold": True, "fontSize": 10},
                "padding": {"top": 4, "bottom": 4, "left": 8},
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,padding)",
        }})

    # Hide gridlines
    requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheet_id_int, "gridProperties": {"hideGridlines": True}},
        "fields": "gridProperties.hideGridlines",
    }})

    # Column widths
    for col_idx, width in [(0, 250), (1, 100), (2, 130), (3, 200), (4, 200), (5, 100), (6, 200)]:
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id_int, "dimension": "COLUMNS", "startIndex": col_idx, "endIndex": col_idx + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})

    sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": requests}).execute()


# ── Data tab content builders ──────────────────────────────────────────────
def build_card_transactions_rows(vendor_rows: list[dict]) -> list[list]:
    """Combined Card Transactions tab — summary columns + per-month spend columns appended.
    Replaces the previous separate 'Card Transactions' and 'Monthly Subscriptions' tabs."""
    subs = [v for v in vendor_rows if v.get("category") == "Card transactions"]
    subs.sort(key=lambda r: abs(r["annual_run_rate"]) if r["status"] in ("ACTIVE", "STOPPED") else abs(r["total_amount"]), reverse=True)

    # Collect all months across all card vendors
    all_months = set()
    for v in subs:
        for t in v.get("transactions", []):
            if t.get("date"):
                all_months.add(t["date"][:7])
    months_sorted = sorted(all_months)

    base_headers = [
        "Vendor", "Status", "Charges", "Months", "Total (USD)", "Avg charge (USD)",
        "Annual run-rate (USD)", "Last seen", "Decision (keep / cancel / renegotiate)", "Notes",
    ]
    rows = [base_headers + months_sorted]

    for v in subs:
        per_month = defaultdict(float)
        for t in v.get("transactions", []):
            if t.get("date"):
                per_month[t["date"][:7]] += t.get("amount", 0)

        base = [
            v["vendor"], v["status"], v["charge_count"], v["months_active"],
            round(v["total_amount"], 2), round(v["avg_charge"], 2),
            round(v["annual_run_rate"], 2) if v["status"] in ("ACTIVE", "STOPPED") else "",
            v["last_seen"], "", "",
        ]
        month_cells = [round(per_month[m], 2) if m in per_month else "" for m in months_sorted]
        rows.append(base + month_cells)
    return rows


def build_ep_payments_rows(vendor_rows: list[dict]) -> list[list]:
    eps = [v for v in vendor_rows if v.get("category") == "EP Payment"]
    eps.sort(key=lambda r: abs(r["total_amount"]), reverse=True)
    rows = [["EP", "Status", "Currency", "Charges", "Months", "Total", "Avg charge", "Annual run-rate", "First seen", "Last seen", "Notes"]]
    for v in eps:
        cur = v["currency"].split()[0] if v["currency"] else ""
        rows.append([
            v["vendor"], v["status"], cur, v["charge_count"], v["months_active"],
            round(v["total_amount"], 2), round(v["avg_charge"], 2),
            round(v["annual_run_rate"], 2) if v["status"] in ("ACTIVE", "STOPPED") else "",
            v["first_seen"], v["last_seen"], "",
        ])
    return rows


def build_other_spend_rows(vendor_rows: list[dict]) -> list[list]:
    excluded = {"EP Payment", "Card transactions"}
    others = [v for v in vendor_rows if v.get("category") not in excluded]
    others.sort(key=lambda r: (r.get("category", ""), -abs(r["total_amount"])))
    rows = [["Category", "Vendor", "Status", "Currency", "Charges", "Months", "Total", "Avg charge", "First seen", "Last seen", "Decision", "Notes"]]
    for v in others:
        cur = v["currency"].split()[0] if v["currency"] else ""
        rows.append([
            v.get("category", "Other"), v["vendor"], v["status"], cur,
            v["charge_count"], v["months_active"],
            round(v["total_amount"], 2), round(v["avg_charge"], 2),
            v["first_seen"], v["last_seen"], "", "",
        ])
    return rows


def build_all_vendors_rows(vendor_rows: list[dict]) -> list[list]:
    rows = [["Category", "Vendor", "Status", "Source", "Currency", "Charges", "Months", "Total", "Avg charge", "Annual run-rate", "First seen", "Last seen", "Decision", "Notes"]]
    for v in sorted(vendor_rows, key=lambda r: -abs(r["total_amount"])):
        cur = v["currency"].split()[0] if v["currency"] else ""
        rows.append([
            v.get("category", "Other"), v["vendor"], v["status"], v["source"], cur,
            v["charge_count"], v["months_active"],
            round(v["total_amount"], 2), round(v["avg_charge"], 2),
            round(v["annual_run_rate"], 2) if v["status"] in ("ACTIVE", "STOPPED") else "",
            v["first_seen"], v["last_seen"], "", "",
        ])
    return rows


def build_all_transactions_rows(transactions: list[dict]) -> list[list]:
    rows = [["Date", "Category", "Source", "Vendor", "Raw description", "Amount", "Currency", "Status", "Type", "ID"]]
    for t in sorted(transactions, key=lambda x: x.get("date", ""), reverse=True):
        rows.append([
            t.get("date", ""), t.get("category", ""), t.get("source", ""), t.get("vendor", ""),
            (t.get("raw_vendor") or "")[:200],
            round(float(t.get("amount", 0)), 2),
            t.get("currency", ""), t.get("status", ""), t.get("notes", ""), t.get("id", ""),
        ])
    return rows


# ── Cards tab ──────────────────────────────────────────────────────────────
def build_cards_rows(cards: list[dict], total_card_spend_usd: float) -> list[list]:
    """User-provided card metadata. Spend is total card spend (can't be attributed
    per-card without Admin API access — annotated accordingly)."""
    rows = [["Card Name", "Holder", "Last 4", "Status", "Monthly Limit", "Limit Currency", "Expires (months)", "Notes"]]
    for c in cards:
        notes = "Main card" if c.get("is_main") else ""
        rows.append([
            c.get("name", ""),
            c.get("holder", ""),
            c.get("last_four", ""),
            c.get("status", ""),
            c.get("monthly_limit", ""),
            c.get("limit_currency", ""),
            c.get("expires_in_months", ""),
            notes,
        ])
    rows.append([])
    rows.append(["Note", f"Per-card spend attribution requires Admin API access. Total card spend across all cards over the window: USD {total_card_spend_usd:,.2f}", "", "", "", "", "", ""])
    return rows


# ── Monthly subscriptions pivot ────────────────────────────────────────────
def build_monthly_pivot_rows(vendor_rows: list[dict]) -> list[list]:
    """Pivot: rows = card vendor, cols = months, cells = total spend that month.
    Lets you see at a glance which subscriptions are still being charged each month."""
    card_vendors = [v for v in vendor_rows if v.get("category") == "Card transactions"]

    # Collect all months across all card vendors, sorted
    all_months = set()
    for v in card_vendors:
        for t in v.get("transactions", []):
            if t.get("date"):
                all_months.add(t["date"][:7])
    months_sorted = sorted(all_months)

    if not months_sorted:
        return [["Vendor", "Status", "Last seen", "(no card transactions in window)"]]

    header = ["Vendor", "Status", "Last seen", "Total"] + months_sorted
    rows = [header]

    # Sort vendors by total spend descending
    card_vendors.sort(key=lambda r: abs(r["total_amount"]), reverse=True)

    for v in card_vendors:
        per_month = defaultdict(float)
        for t in v.get("transactions", []):
            if t.get("date"):
                per_month[t["date"][:7]] += t.get("amount", 0)

        cur = v["currency"].split()[0] if v["currency"] else ""
        row = [v["vendor"], v["status"], v["last_seen"], round(v["total_amount"], 2)]
        for m in months_sorted:
            row.append(round(per_month.get(m, 0), 2) if m in per_month else "")
        rows.append(row)

    return rows


# ── Top-level export ───────────────────────────────────────────────────────
def export(vendor_rows: list[dict], transactions: list[dict], label: str, existing_sheet_id: str | None = None, cards: list[dict] | None = None) -> str:
    sheets, drive = get_services()
    cards = cards or []

    if existing_sheet_id:
        sheet_id = existing_sheet_id
        print(f"  Updating existing sheet: {sheet_id}")
    else:
        title = f"Airwallex Spend Review — {label}"
        sheet_id = create_spreadsheet(sheets, drive, title)
        print(f"  Created new spreadsheet: {title}")

    # Total card spend (USD) for the cards tab footnote
    total_card_spend = sum(abs(v["total_amount"]) for v in vendor_rows if v.get("category") == "Card transactions")

    print("  Writing Overview dashboard...")
    write_overview_dashboard(sheets, sheet_id, vendor_rows, transactions, label, cards)

    print("  Writing Cards tab...")
    cards_rows = build_cards_rows(cards, total_card_spend)
    write_data_tab(sheets, sheet_id, "Cards", cards_rows, status_col=3)

    print("  Writing Card Transactions tab (with monthly columns merged in)...")
    sub_rows = build_card_transactions_rows(vendor_rows)
    write_data_tab(sheets, sheet_id, "Card Transactions", sub_rows,
                   status_col=1, decision_col=8, amount_cols=[4, 5, 6])

    print("  Writing EP Payments tab...")
    ep_rows = build_ep_payments_rows(vendor_rows)
    write_data_tab(sheets, sheet_id, "EP Payments", ep_rows,
                   status_col=1, amount_cols=[5, 6, 7])

    print("  Writing Other Spend tab...")
    other_rows = build_other_spend_rows(vendor_rows)
    write_data_tab(sheets, sheet_id, "Other Spend", other_rows,
                   status_col=2, decision_col=10, amount_cols=[6, 7])

    print("  Writing All Vendors tab...")
    all_rows = build_all_vendors_rows(vendor_rows)
    write_data_tab(sheets, sheet_id, "All Vendors", all_rows,
                   status_col=2, decision_col=12, amount_cols=[7, 8, 9])

    print("  Writing All Transactions tab...")
    txn_rows = build_all_transactions_rows(transactions)
    write_data_tab(sheets, sheet_id, "All Transactions", txn_rows,
                   amount_cols=[5])

    # Delete obsolete tabs from prior runs (so the dashboard stays clean)
    meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in meta["sheets"]:
        title = s["properties"]["title"]
        if title in ("Subscriptions", "Monthly Subscriptions"):
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]},
            ).execute()
            print(f"  Removed obsolete tab: '{title}'")

    if not existing_sheet_id:
        delete_default_sheet(sheets, sheet_id)

    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"
