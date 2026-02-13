"""
Check Recruit Status Workflow

Queries the Notion Candidates DB and prints a Slack-friendly terminal
report with 8 sections: pipeline overview, candidate breakdown, EP channel
breakdown, EP conversion funnel, EP channel quality, hiring efficiency,
and screening backlog.

Usage:
    python3.11 check_recruit_status.py
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


def query_recent_candidates(headers: dict, db_id: str, since_days: int = 60) -> list[dict]:
    """Query candidates created in the last N days (default 60)."""
    cutoff = datetime.now(SGT) - timedelta(days=since_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%d")

    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    all_pages = []
    next_cursor = None

    while True:
        payload = {
            "page_size": 100,
            "filter": {
                "timestamp": "created_time",
                "created_time": {"on_or_after": cutoff_iso},
            },
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


def fetch_page(headers: dict, page_id: str) -> dict:
    """Fetch a single Notion page by ID."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


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

    # Created time (from page-level)
    created_time = page.get("created_time", "")

    # Parse created time to SGT
    created_sgt = None
    if created_time:
        created_sgt = datetime.fromisoformat(
            created_time.replace("Z", "+00:00")
        ).astimezone(SGT)

    # Kimi Rating (rich_text -> float)
    kimi_rating = _parse_rating(properties, "Kimi Rating")

    # Post relation ID (for opening breakdown)
    post_relation_id = None
    post_prop = properties.get("Post", {})
    if post_prop.get("type") == "relation":
        relations = post_prop.get("relation", [])
        if relations:
            post_relation_id = relations[0].get("id")

    # Screener (status) — break out invite type
    invite_type = None  # None | "sync" | "async"
    screener_prop = properties.get("Screener", {})
    if screener_prop.get("type") == "status" and screener_prop.get("status"):
        screener_name = screener_prop["status"].get("name", "")
        lower = screener_name.lower()
        if lower.startswith("to invite"):
            invite_type = "async" if "async" in lower else "sync"

    # 1R (status) — proceed if == "Proceed"
    r1_proceed = False
    r1_prop = properties.get("1R", {})
    if r1_prop.get("type") == "status" and r1_prop.get("status"):
        r1_name = r1_prop["status"].get("name", "")
        r1_proceed = r1_name == "Proceed"

    # 2R (status) — proceed if == "Proceed"
    r2_proceed = False
    r2_prop = properties.get("2R", {})
    if r2_prop.get("type") == "status" and r2_prop.get("status"):
        r2_name = r2_prop["status"].get("name", "")
        r2_proceed = r2_name == "Proceed"

    # R1 conducted (any status beyond "Not started")
    r1_conducted = False
    if r1_prop.get("type") == "status" and r1_prop.get("status"):
        r1_status_name = r1_prop["status"].get("name", "")
        r1_conducted = r1_status_name != "Not started"

    # R2 conducted (any status beyond "Not started")
    r2_conducted = False
    if r2_prop.get("type") == "status" and r2_prop.get("status"):
        r2_status_name = r2_prop["status"].get("name", "")
        r2_conducted = r2_status_name != "Not started"

    # Decision R / Alignment (any status beyond "Not started")
    alignment_conducted = False
    decision_prop = properties.get("Decision R", {})
    if decision_prop.get("type") == "status" and decision_prop.get("status"):
        decision_name = decision_prop["status"].get("name", "")
        alignment_conducted = decision_name != "Not started"

    # Offer status — hired if "Offer Accepted"
    hired = False
    offer_prop = properties.get("Offer", {})
    if offer_prop.get("type") == "status" and offer_prop.get("status"):
        offer_name = offer_prop["status"].get("name", "")
        hired = offer_name == "Offer Accepted"

    return {
        "name": name,
        "created_time": created_time,
        "created_sgt": created_sgt,
        "kimi_rating": kimi_rating,
        "post_relation_id": post_relation_id,
        "invite_type": invite_type,
        "r1_proceed": r1_proceed,
        "r2_proceed": r2_proceed,
        "r1_conducted": r1_conducted,
        "r2_conducted": r2_conducted,
        "alignment_conducted": alignment_conducted,
        "hired": hired,
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


def resolve_post_details(headers: dict, candidates: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve Post relation IDs to Opening names and Post Channels.

    Returns:
        (opening_names, post_channels) where each is {post_id: value}.
    """
    # Collect unique post IDs
    post_ids = set()
    for c in candidates:
        pid = c.get("post_relation_id")
        if pid:
            post_ids.add(pid)

    if not post_ids:
        return {}, {}

    opening_names = {}   # post_id -> opening name
    post_channels = {}   # post_id -> channel name
    print(f"  Resolving {len(post_ids)} post(s) to openings...", end="", flush=True)

    for post_id in post_ids:
        try:
            post_page = fetch_page(headers, post_id)
            post_props = post_page.get("properties", {})

            # Get Post Channel (select) from Post page
            channel_prop = post_props.get("Post Channel", {})
            if channel_prop.get("type") == "select" and channel_prop.get("select"):
                post_channels[post_id] = channel_prop["select"].get("name", "Unknown")
            else:
                post_channels[post_id] = "Unknown"

            # Get Opening relation from Post page
            opening_prop = post_props.get("Opening", {})
            if opening_prop.get("type") == "relation":
                relations = opening_prop.get("relation", [])
                if relations:
                    opening_id = relations[0].get("id")
                    opening_page = fetch_page(headers, opening_id)
                    opening_props = opening_page.get("properties", {})

                    # Get title from Opening
                    title_prop = opening_props.get("Opening ID & Name", {})
                    if title_prop.get("type") == "title":
                        title_items = title_prop.get("title", [])
                        if title_items:
                            opening_names[post_id] = title_items[0].get("plain_text", "Unknown Opening")
                            continue

            opening_names[post_id] = "Unknown Opening"
        except requests.RequestException:
            opening_names[post_id] = "(fetch error)"
            post_channels.setdefault(post_id, "(fetch error)")

    print(" done.")
    return opening_names, post_channels


def compute_pipeline_overview(candidates: list[dict], days: int) -> dict:
    """Compute pipeline overview using full completed calendar days (SGT)."""
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)

    # Rolling 24-hour windows
    cutoff_24h = now_sgt - timedelta(hours=24)
    cutoff_prior_24h = now_sgt - timedelta(hours=48)

    # Full calendar days: yesterday vs day before
    yesterday_start = today_start - timedelta(days=1)
    day_before_start = today_start - timedelta(days=2)

    # Full completed windows: last N days vs prior N days (excludes today)
    w_start = today_start - timedelta(days=days)
    w_prior_start = w_start - timedelta(days=days)

    m_start = today_start - timedelta(days=30)
    m_prior_start = m_start - timedelta(days=30)

    in_24h = 0
    in_prior_24h = 0
    yesterday = 0
    day_before = 0
    in_window = 0
    in_prior_window = 0
    in_30d = 0
    in_prior_30d = 0

    for c in candidates:
        created = c.get("created_sgt")
        if not created:
            continue
        # L24H tracking
        if created >= cutoff_24h:
            in_24h += 1
        if cutoff_prior_24h <= created < cutoff_24h:
            in_prior_24h += 1
        # Calendar day tracking
        if yesterday_start <= created < today_start:
            yesterday += 1
        if day_before_start <= created < yesterday_start:
            day_before += 1
        if w_start <= created < today_start:
            in_window += 1
        if w_prior_start <= created < w_start:
            in_prior_window += 1
        if m_start <= created < today_start:
            in_30d += 1
        if m_prior_start <= created < m_start:
            in_prior_30d += 1

    return {
        "24h": in_24h,
        "prior_24h": in_prior_24h,
        "yesterday": yesterday,
        "day_before": day_before,
        "in_window": in_window,
        "in_prior_window": in_prior_window,
        "in_30d": in_30d,
        "in_prior_30d": in_prior_30d,
    }


def compute_candidate_breakdown(
    candidates: list[dict], opening_names: dict[str | None, str]
) -> list[tuple[str, int]]:
    """Count candidates per opening for last 7 completed days, sorted desc."""
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today_start - timedelta(days=7)

    counter = Counter()
    for c in candidates:
        created = c.get("created_sgt")
        if not created or not (cutoff <= created < today_start):
            continue
        pid = c.get("post_relation_id")
        if pid and pid in opening_names:
            counter[opening_names[pid]] += 1
        else:
            counter["(No Post)"] += 1
    return counter.most_common()


def compute_channel_breakdown(
    candidates: list[dict],
    opening_names: dict[str, str],
    post_channels: dict[str, str],
    role_code: str = "EP",
) -> dict:
    """Count candidates by Post Channel for a specific role, for L24H, yesterday, and last 7d.

    Args:
        role_code: Job type code to filter on (matched in opening name, e.g. "EP" matches "251003-EP ...").
    """
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)

    # Rolling 24h
    cutoff_24h = now_sgt - timedelta(hours=24)

    # Calendar day windows
    yesterday_start = today_start - timedelta(days=1)
    cutoff_7d = today_start - timedelta(days=7)

    # Build set of post_ids that belong to the target role
    role_post_ids = set()
    for pid, name in opening_names.items():
        # Opening names look like "251003-EP Executive Partner (Full-Time)"
        # Extract the code after the dash: "EP", "EPP", "CPL", etc.
        parts = name.split()
        if parts:
            prefix = parts[0]  # e.g. "251003-EP"
            code = prefix.split("-", 1)[1] if "-" in prefix else ""
            if code == role_code:
                role_post_ids.add(pid)

    counter_24h = Counter()
    yesterday_counter = Counter()
    week_counter = Counter()

    for c in candidates:
        created = c.get("created_sgt")
        pid = c.get("post_relation_id")
        if not created or not pid or pid not in role_post_ids:
            continue

        channel = post_channels.get(pid, "Unknown")

        # L24H tracking
        if created >= cutoff_24h:
            counter_24h[channel] += 1

        # Calendar day tracking
        if yesterday_start <= created < today_start:
            yesterday_counter[channel] += 1
        if cutoff_7d <= created < today_start:
            week_counter[channel] += 1

    return {
        "24h": counter_24h,
        "yesterday": yesterday_counter,
        "7d": week_counter,
    }


def _get_ep_post_ids(opening_names: dict[str, str], role_code: str = "EP") -> set:
    """Return set of post_ids belonging to a role code."""
    role_post_ids = set()
    for pid, name in opening_names.items():
        parts = name.split()
        if parts:
            prefix = parts[0]
            code = prefix.split("-", 1)[1] if "-" in prefix else ""
            if code == role_code:
                role_post_ids.add(pid)
    return role_post_ids


def compute_conversion_funnel(
    candidates: list[dict],
    opening_names: dict[str, str],
) -> dict:
    """Compute EP conversion funnel for 7d, 30d, and 60d windows.

    Stages: Applied → Invited (sync/async) → R1 Proceeds → R2 Proceeds
    Returns counts per window.
    """
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoffs = {
        "7d": today_start - timedelta(days=7),
        "30d": today_start - timedelta(days=30),
        "60d": today_start - timedelta(days=60),
    }

    role_post_ids = _get_ep_post_ids(opening_names)

    def _funnel_counts(group: list[dict]) -> dict:
        applied = len(group)
        invite_sync = sum(1 for c in group if c["invite_type"] == "sync")
        invite_async = sum(1 for c in group if c["invite_type"] == "async")
        invited = invite_sync + invite_async
        r1_proceed = sum(1 for c in group if c["r1_proceed"])
        r2_proceed = sum(1 for c in group if c["r2_proceed"])
        return {
            "applied": applied,
            "invite_sync": invite_sync,
            "invite_async": invite_async,
            "invited": invited,
            "r1_proceed": r1_proceed,
            "r2_proceed": r2_proceed,
        }

    result = {}
    for label, cutoff in cutoffs.items():
        group = [
            c for c in candidates
            if c.get("created_sgt") and cutoff <= c["created_sgt"] < today_start
            and c.get("post_relation_id") in role_post_ids
        ]
        result[label] = _funnel_counts(group)

    return result


def compute_channel_quality(
    candidates: list[dict],
    opening_names: dict[str, str],
    post_channels: dict[str, str],
) -> list[dict]:
    """Compute per-channel invite and R1 rates for EP candidates (last 60d).

    Returns list of dicts sorted by applied desc:
        [{"channel": str, "applied": int, "invited": int, "r1_proceed": int}, ...]
    """
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_60d = today_start - timedelta(days=60)

    role_post_ids = _get_ep_post_ids(opening_names)

    channel_stats: dict[str, dict] = {}

    for c in candidates:
        created = c.get("created_sgt")
        pid = c.get("post_relation_id")
        if not created or not pid or pid not in role_post_ids:
            continue
        if not (cutoff_60d <= created < today_start):
            continue

        channel = post_channels.get(pid, "Unknown")
        if channel not in channel_stats:
            channel_stats[channel] = {"applied": 0, "invited": 0, "r1_proceed": 0, "r2_proceed": 0}

        channel_stats[channel]["applied"] += 1
        if c["invite_type"] is not None:
            channel_stats[channel]["invited"] += 1
        if c["r1_proceed"]:
            channel_stats[channel]["r1_proceed"] += 1
        if c["r2_proceed"]:
            channel_stats[channel]["r2_proceed"] += 1

    result = [
        {"channel": ch, **stats}
        for ch, stats in channel_stats.items()
    ]
    result.sort(key=lambda x: x["applied"], reverse=True)
    return result


def compute_screening_backlog(candidates: list[dict]) -> dict:
    """Compute Kimi screening backlog for last 24h and last 7d."""
    now_sgt = datetime.now(SGT)
    cutoff_24h = now_sgt - timedelta(hours=24)
    cutoff_7d = now_sgt - timedelta(days=7)

    def _kimi_stats(group):
        total = len(group)
        scored = sum(1 for c in group if c["kimi_rating"] is not None)
        return {
            "total": total,
            "scored": scored,
            "unscored": total - scored,
            "pct": (scored / total * 100) if total else 0,
        }

    last_24h = [c for c in candidates if c.get("created_sgt") and c["created_sgt"] >= cutoff_24h]
    last_7d = [c for c in candidates if c.get("created_sgt") and c["created_sgt"] >= cutoff_7d]

    return {
        "24h": _kimi_stats(last_24h),
        "7d": _kimi_stats(last_7d),
    }


def compute_hiring_efficiency(candidates: list[dict]) -> dict:
    """Compute hiring efficiency metrics for 30d, 60d, and 90d windows.

    Counts R1 interviews, R2 interviews, alignment (Decision R) interviews,
    and hires (Offer Accepted) per window, then derives per-hire ratios
    and a crude cost-of-hire estimate ($5 per R1/R2, $60 per alignment).
    """
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = {
        "30d": today_start - timedelta(days=30),
        "60d": today_start - timedelta(days=60),
        "90d": today_start - timedelta(days=90),
    }

    COST_R1 = 5
    COST_R2 = 5
    COST_ALIGNMENT = 60

    result = {}
    for label, cutoff in windows.items():
        group = [
            c for c in candidates
            if c.get("created_sgt") and cutoff <= c["created_sgt"] < today_start
        ]

        r1_count = sum(1 for c in group if c["r1_conducted"])
        r2_count = sum(1 for c in group if c["r2_conducted"])
        alignment_count = sum(1 for c in group if c["alignment_conducted"])
        hire_count = sum(1 for c in group if c["hired"])

        r1_cost = r1_count * COST_R1
        r2_cost = r2_count * COST_R2
        alignment_cost = alignment_count * COST_ALIGNMENT
        total_cost = r1_cost + r2_cost + alignment_cost

        result[label] = {
            "r1": r1_count,
            "r2": r2_count,
            "alignment": alignment_count,
            "hires": hire_count,
            "r1_per_hire": r1_count / hire_count if hire_count else None,
            "r2_per_hire": r2_count / hire_count if hire_count else None,
            "alignment_per_hire": alignment_count / hire_count if hire_count else None,
            "cost_r1": r1_cost,
            "cost_r2": r2_cost,
            "cost_alignment": alignment_cost,
            "cost_total": total_cost,
            "cost_per_hire": total_cost / hire_count if hire_count else None,
        }

    return result


def _bar(count: int, max_count: int, max_width: int = 15) -> str:
    """Render a simple bar chart string."""
    if max_count == 0:
        return ""
    width = round(count / max_count * max_width)
    return "\u2588" * width


def _trend(current: int, previous: int) -> str:
    """Return trend emoji + delta string."""
    diff = current - previous
    if diff > 0:
        return f"\U0001f7e2 +{diff}"   # green circle
    elif diff < 0:
        return f"\U0001f534 {diff}"     # red circle
    return "\u26aa ~"                    # white circle


def _pct(num: int, denom: int) -> str:
    """Format percentage with 2 significant digits, return '-' if denom is 0."""
    if denom == 0:
        return "-"
    val = num / denom * 100
    return f"{val:.2g}%"


def build_report(
    days: int,
    pipeline: dict,
    candidate_breakdown: list[tuple[str, int]],
    backlog: dict,
    channel_breakdown: dict | None = None,
    conversion_funnel: dict | None = None,
    channel_quality: list[dict] | None = None,
    hiring_efficiency: dict | None = None,
) -> str:
    """Build the full Slack-friendly report."""
    now_sgt = datetime.now(SGT)
    timestamp_str = now_sgt.strftime("%Y-%m-%d %H:%M SGT")

    day_trend = _trend(pipeline["yesterday"], pipeline["day_before"])
    window_trend = _trend(pipeline["in_window"], pipeline["in_prior_window"])
    month_trend = _trend(pipeline["in_30d"], pipeline["in_prior_30d"])

    out = StringIO()
    p = lambda line="": print(line, file=out)

    p(f"*Recruitment Pipeline* | {timestamp_str}")

    # 1. Pipeline Overview (full completed days only)
    p()
    p(f"*1. Pipeline Overview*")
    p(f"```")
    l24h_trend = _trend(pipeline['24h'], pipeline['prior_24h'])
    p(f"Last 24h     {pipeline['24h']:>5}  (prior 24h: {pipeline['prior_24h']})    {l24h_trend}")
    p(f"Yesterday    {pipeline['yesterday']:>5}  (day before: {pipeline['day_before']})  {day_trend}")
    p(f"Last {days}d      {pipeline['in_window']:>5}  (prior {days}d: {pipeline['in_prior_window']})    {window_trend}")
    p(f"Last 30d     {pipeline['in_30d']:>5}  (prior 30d: {pipeline['in_prior_30d']})   {month_trend}")
    p(f"```")

    # 2. Candidate Breakdown (last 7 completed days)
    p()
    p(f"*2. Candidate Breakdown (last 7d)*")
    p(f"```")
    if candidate_breakdown:
        max_count = candidate_breakdown[0][1]
        max_name_len = 30
        total = sum(count for _, count in candidate_breakdown)
        for name, count in candidate_breakdown:
            pct = count / total * 100 if total else 0
            bar = _bar(count, max_count)
            display = (name[:max_name_len - 1] + "\u2026") if len(name) > max_name_len else name
            p(f"{display:<{max_name_len}}  {count:>4}  {bar:<15} {pct:>3.0f}%")
    else:
        p("No candidates in the last 7 days.")
    p(f"```")

    # 3. EP Channel Breakdown
    if channel_breakdown:
        p()
        p(f"*3. EP Channel Breakdown*")
        p(f"```")
        counter_24h = channel_breakdown["24h"]
        week = channel_breakdown["7d"]
        yesterday = channel_breakdown["yesterday"]
        # Collect all channels across all periods
        all_channels = sorted(set(list(week.keys()) + list(yesterday.keys()) + list(counter_24h.keys())))
        if all_channels:
            week_total = sum(week.values())
            yest_total = sum(yesterday.values())
            l24h_total = sum(counter_24h.values())
            max_count = max(week.values()) if week else 0
            p(f"{'Channel':<15} {'Last 7d':>7} {'%':>5}  {'':15} {'Yest':>5} {'L24H':>5}")
            for ch in all_channels:
                w = week.get(ch, 0)
                y = yesterday.get(ch, 0)
                h24 = counter_24h.get(ch, 0)
                pct = w / week_total * 100 if week_total else 0
                bar = _bar(w, max_count)
                p(f"{ch:<15} {w:>7} {pct:>4.0f}%  {bar:<15} {y:>5} {h24:>5}")
            p(f"{'─' * 15} {'─' * 7} {'─' * 5}  {'':15} {'─' * 5} {'─' * 5}")
            p(f"{'Total':<15} {week_total:>7}  {'':4}  {'':15} {yest_total:>5} {l24h_total:>5}")
        else:
            p("No EP candidates with channel data.")
        p(f"```")

    # 5. EP Conversion Funnel
    if conversion_funnel:
        p()
        p(f"*5. EP Conversion Funnel*")
        p(f"```")
        windows = ["7d", "30d", "60d"]
        fw = {w: conversion_funnel[w] for w in windows}

        # Header
        hdr = f"{'':20}"
        for w in windows:
            hdr += f" {'Last '+w:>12}"
        p(hdr)

        # Funnel rows
        rows = [
            ("Applied", "applied"),
            ("  To Invite", "invite_sync"),
            ("  To Invite (Async)", "invite_async"),
            ("Invited to R1", "invited"),
            ("R1 Proceeds", "r1_proceed"),
            ("R2 Proceeds", "r2_proceed"),
        ]
        for label, key in rows:
            line = f"{label:<20}"
            for w in windows:
                c = fw[w][key]
                if key == "applied":
                    line += f" {c:>12}"
                else:
                    pct = _pct(c, fw[w]["applied"])
                    line += f" {c:>5}  {pct:>5}"
            p(line)

        # Stage-to-stage rates
        p()
        hdr2 = f"  {'Stage rates':<18}"
        for w in windows:
            hdr2 += f" {w:>12}"
        p(hdr2)
        stage_pairs = [
            ("Applied→Invited", "invited", "applied"),
            ("Invited→R1 Proceed", "r1_proceed", "invited"),
            ("R1→R2 Proceed", "r2_proceed", "r1_proceed"),
        ]
        for label, num_key, denom_key in stage_pairs:
            line = f"  {label:<18}"
            for w in windows:
                rate = _pct(fw[w][num_key], fw[w][denom_key])
                line += f" {rate:>12}"
            p(line)
        p(f"```")

    # 6. EP Channel Quality (last 60d)
    if channel_quality:
        p()
        p(f"*6. EP Channel Quality (last 60d)*")
        p(f"```")
        p(f"{'Channel':<15} {'Applied':>7}  {'Invited':>7}  {'Inv%':>5}  {'R1 Proc':>7}  {'R1%':>5}  {'R2 Proc':>7}  {'R2%':>5}")
        for row in channel_quality:
            inv_pct = _pct(row["invited"], row["applied"])
            r1_pct = _pct(row["r1_proceed"], row["applied"])
            r2_pct = _pct(row["r2_proceed"], row["applied"])
            p(f"{row['channel']:<15} {row['applied']:>7}  {row['invited']:>7}  {inv_pct:>5}  {row['r1_proceed']:>7}  {r1_pct:>5}  {row['r2_proceed']:>7}  {r2_pct:>5}")
        p(f"```")

    # 7. Hiring Efficiency
    if hiring_efficiency:
        p()
        p(f"*7. Hiring Efficiency [Under Review]*")
        p(f"```")
        windows = ["30d", "60d", "90d"]
        he = {w: hiring_efficiency[w] for w in windows}

        def _val(v):
            return f"{v:.1f}" if v is not None else "-"

        def _cost(v):
            return f"${v:,.0f}" if v is not None else "-"

        # Header
        hdr = f"{'':22}"
        for w in windows:
            hdr += f"  {'Last '+w:>10}"
        p(hdr)

        # Interview counts
        count_rows = [
            ("R1 Interviews", "r1"),
            ("R2 Interviews", "r2"),
            ("Alignment (Decision)", "alignment"),
            ("Hires", "hires"),
        ]
        for label, key in count_rows:
            line = f"{label:<22}"
            for w in windows:
                line += f"  {he[w][key]:>10}"
            p(line)

        # Per-hire ratios
        p()
        ratio_hdr = f"  {'Per Hire':<20}"
        for w in windows:
            ratio_hdr += f"  {w:>10}"
        p(ratio_hdr)
        ratio_rows = [
            ("R1 per Hire", "r1_per_hire"),
            ("R2 per Hire", "r2_per_hire"),
            ("Alignment per Hire", "alignment_per_hire"),
        ]
        for label, key in ratio_rows:
            line = f"  {label:<20}"
            for w in windows:
                line += f"  {_val(he[w][key]):>10}"
            p(line)

        # Cost breakdown
        p()
        cost_hdr = f"  {'Cost of Hire':<20}"
        for w in windows:
            cost_hdr += f"  {w:>10}"
        p(cost_hdr)
        cost_rows = [
            ("R1 ($5 ea)", "cost_r1"),
            ("R2 ($5 ea)", "cost_r2"),
            ("Alignment ($60 ea)", "cost_alignment"),
            ("Total Interview Cost", "cost_total"),
            ("Cost per Hire", "cost_per_hire"),
        ]
        for label, key in cost_rows:
            line = f"  {label:<20}"
            for w in windows:
                line += f"  {_cost(he[w][key]):>10}"
            p(line)

        p(f"```")

    # 8. Screening Backlog (Kimi)
    p()
    p(f"*8. Screening Backlog (Kimi)*")
    p(f"```")
    p(f"{'':10} {'Total':>5}  {'Scored':>6}  {'Unscored':>8}  {'Coverage':>8}")
    b24 = backlog["24h"]
    b7d = backlog["7d"]
    p(f"{'Last 24h':10} {b24['total']:>5}  {b24['scored']:>6}  {b24['unscored']:>8}  {b24['pct']:>7.0f}%")
    p(f"{'Last 7d':10} {b7d['total']:>5}  {b7d['scored']:>6}  {b7d['unscored']:>8}  {b7d['pct']:>7.0f}%")
    p(f"```")

    return out.getvalue()


def post_to_slack(report: str) -> None:
    """Post report to Slack via Incoming Webhook. Skips if SLACK_WEBHOOK_URL not set."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    try:
        resp = requests.post(webhook_url, json={"text": report}, timeout=15)
        resp.raise_for_status()
        print("Slack: posted successfully.")
    except requests.RequestException as e:
        print(f"Slack: failed to post — {e}")


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

    # Query recent candidates (last 90 days covers all metrics incl. hiring efficiency)
    print("Fetching candidates (last 90d)...", end="", flush=True)
    try:
        pages = query_recent_candidates(headers, db_id, since_days=90)
    except requests.RequestException as e:
        print(f"\nERROR: Could not query candidates: {e}")
        sys.exit(1)
    print(f" {len(pages)} found.")

    if not pages:
        print("No candidates found in the database.")
        return

    # Extract data
    candidates = [extract_candidate(p) for p in pages]

    # Resolve opening names and channels from Post relations
    opening_names, post_channels = resolve_post_details(headers, candidates)

    # Compute metrics
    pipeline = compute_pipeline_overview(candidates, args.days)
    candidate_breakdown = compute_candidate_breakdown(candidates, opening_names)
    channel_breakdown = compute_channel_breakdown(candidates, opening_names, post_channels, role_code="EP")
    conversion_funnel = compute_conversion_funnel(candidates, opening_names)
    channel_quality = compute_channel_quality(candidates, opening_names, post_channels)
    hiring_efficiency = compute_hiring_efficiency(candidates)
    backlog = compute_screening_backlog(candidates)

    # Build and print report
    report = build_report(
        args.days, pipeline, candidate_breakdown, backlog,
        channel_breakdown, conversion_funnel, channel_quality,
        hiring_efficiency,
    )
    print(report, end="")

    # Save to file with SGT timestamp
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now_sgt = datetime.now(SGT)
    filename = now_sgt.strftime("%Y-%m-%d_%H%M_SGT") + ".txt"
    report_path = REPORTS_DIR / filename
    report_path.write_text(report)
    print(f"Report saved to: {report_path.relative_to(PROJECT_ROOT)}")

    # Post to Slack (skips silently if SLACK_WEBHOOK_URL not set)
    post_to_slack(report)


if __name__ == "__main__":
    main()
