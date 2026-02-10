"""
Balance Checker Library

Fetches Moonshot API balance, persists daily snapshots, computes spend deltas,
and counts daily API calls from receipt files.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests

SGT = timezone(timedelta(hours=8))
BALANCE_URL = "https://api.moonshot.ai/v1/users/me/balance"


def fetch_balance(api_key: str) -> dict:
    """Fetch balance from Moonshot API.

    Returns the balance data dict with keys: available_balance, cash_balance,
    voucher_balance. Raises on network/auth errors.
    """
    resp = requests.get(
        BALANCE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    return body.get("data", body)


def load_snapshot(date: str, snapshot_dir: Path) -> dict | None:
    """Load a balance snapshot for a given date. Returns None if not found."""
    path = snapshot_dir / f"{date}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_snapshot(balances: dict, date: str, snapshot_dir: Path) -> Path:
    """Save balance snapshot for today. Returns the path written.

    Args:
        balances: dict with keys "screening" and "ep_review", each a balance data dict.
        date: YYYY-MM-DD string.
        snapshot_dir: Directory for snapshot files.
    """
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    now_sgt = datetime.now(SGT)
    snapshot = {
        "date": date,
        "timestamp": now_sgt.isoformat(),
        "keys": balances,
    }
    path = snapshot_dir / f"{date}.json"
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return path


def count_api_calls(date: str, project_root: Path) -> dict:
    """Count today's Kimi API calls from receipt/review files.

    Returns {"screening": int, "ep_review": int}.
    """
    screening_count = 0
    receipts_dir = project_root / "local-data" / "talent" / "resume_receipts"
    if receipts_dir.exists():
        for f in receipts_dir.iterdir():
            if f.name.endswith("_Kimi.json") and f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=SGT)
                if mtime.strftime("%Y-%m-%d") == date:
                    screening_count += 1

    ep_count = 0
    ep_review = project_root / "local-data" / "talent" / "ep_reviews" / f"{date}_review.json"
    if ep_review.exists():
        ep_count = 1

    return {"screening": screening_count, "ep_review": ep_count}


def build_balance_section(
    balances: dict,
    prev_snapshot: dict | None,
    call_counts: dict,
) -> str:
    """Build Slack mrkdwn section for API usage.

    Args:
        balances: {"screening": {balance_data}, "ep_review": {balance_data}}
        prev_snapshot: Previous day's snapshot dict (or None)
        call_counts: {"screening": int, "ep_review": int}
    """
    out = StringIO()
    p = lambda line="": print(line, file=out)

    p("*API Usage* | Moonshot (Kimi)")
    p()
    p("```")
    p(f"{'Key':<13} {'Balance':>10} {'Spent Today':>13} {'Calls Today':>13}")

    prev_keys = prev_snapshot.get("keys", {}) if prev_snapshot else {}

    for key, label in [("screening", "Screening"), ("ep_review", "EP Review")]:
        bal_data = balances.get(key)
        if bal_data is None:
            p(f"{label:<13} {'error':>10} {'—':>13} {'—':>13}")
            continue

        available = bal_data.get("available_balance", 0)
        bal_str = f"¥{available:.2f}"

        prev_data = prev_keys.get(key)
        if prev_data is not None:
            prev_available = prev_data.get("available_balance", 0)
            spent = prev_available - available
            spent_str = f"¥{spent:.2f}"
        else:
            spent_str = "—"

        calls = call_counts.get(key, 0)

        p(f"{label:<13} {bal_str:>10} {spent_str:>13} {calls:>13}")

    p("```")
    return out.getvalue()
