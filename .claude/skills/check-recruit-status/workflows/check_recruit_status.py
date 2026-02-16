"""
Check Recruit Status Workflow

Queries the Notion Candidates DB and prints a Slack-friendly terminal
report with 7 sections: pipeline overview, daily EP applications by channel,
candidate breakdown, EP conversion funnel, EP channel quality,
hiring efficiency, and screening backlog.

Usage:
    python3.11 check_recruit_status.py
    python3.11 check_recruit_status.py --days 14
"""

import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import httpx
import requests
from dotenv import load_dotenv
from openai import OpenAI

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# Constants
NOTION_API_BASE = "https://api.notion.com/v1"
SGT = timezone(timedelta(hours=8))  # Singapore Time (UTC+8)
REPORTS_DIR = PROJECT_ROOT / "local-data" / "talent" / "pipeline_reports"

# Retry settings for Notion API
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15]  # seconds between retry 1→2, 2→3
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectionError,
)


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

        response = _notion_request("POST", url, headers=headers, json=payload)
        data = response.json()

        all_pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        next_cursor = data.get("next_cursor")

    return all_pages


def fetch_page(headers: dict, page_id: str) -> dict:
    """Fetch a single Notion page by ID."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    response = _notion_request("GET", url, headers=headers)
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

    # Kimi Rating (rich_text -> float + raw text for skip detection)
    kimi_rating = _parse_rating(properties, "Kimi Rating")
    kimi_rating_raw = _parse_rich_text(properties, "Kimi Rating")

    # Kimi Recommendation (select)
    kimi_recommendation = None
    kimi_rec_prop = properties.get("Kimi Recommendation", {})
    if kimi_rec_prop.get("type") == "select" and kimi_rec_prop.get("select"):
        kimi_recommendation = kimi_rec_prop["select"].get("name")

    # Kimi Rationale (rich_text — used to parse skip reasons)
    kimi_rationale = _parse_rich_text(properties, "Kimi Rationale")

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
        "kimi_rating_raw": kimi_rating_raw,
        "kimi_recommendation": kimi_recommendation,
        "kimi_rationale": kimi_rationale,
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


def _parse_rich_text(properties: dict, prop_name: str) -> str:
    """Extract plain text from a rich_text property (empty string if absent)."""
    prop = properties.get(prop_name, {})
    if prop.get("type") == "rich_text":
        items = prop.get("rich_text", [])
        if items:
            return items[0].get("plain_text", "").strip()
    return ""


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


def compute_daily_channel_volume(
    candidates: list[dict],
    opening_names: dict[str, str],
    post_channels: dict[str, str],
    days: int = 7,
) -> dict:
    """Compute daily EP application counts by channel for the last N completed days.

    Returns:
        {"dates": [str], "channels": [str], "grid": {date_str: Counter}, "totals": Counter}
    """
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)

    role_post_ids = _get_ep_post_ids(opening_names)

    # Build date buckets for last N completed days (excludes today)
    date_starts = [today_start - timedelta(days=i) for i in range(days, 0, -1)]

    grid: dict[str, Counter] = {}
    all_channels: set[str] = set()

    for d in date_starts:
        date_str = d.strftime("%Y-%m-%d")
        next_d = d + timedelta(days=1)
        counter: Counter = Counter()

        for c in candidates:
            created = c.get("created_sgt")
            pid = c.get("post_relation_id")
            if not created or not pid or pid not in role_post_ids:
                continue
            if d <= created < next_d:
                channel = post_channels.get(pid, "Unknown")
                counter[channel] += 1
                all_channels.add(channel)

        grid[date_str] = counter

    # Sort channels by total volume desc
    channel_totals: Counter = Counter()
    for counter in grid.values():
        channel_totals.update(counter)

    sorted_channels = [ch for ch, _ in channel_totals.most_common()]
    date_strings = [d.strftime("%Y-%m-%d") for d in date_starts]

    return {
        "dates": date_strings,
        "channels": sorted_channels,
        "grid": grid,
        "totals": channel_totals,
    }


def _classify_screening(c: dict) -> tuple[str, str]:
    """Classify a candidate's screening state.

    Returns (status, skip_reason) where:
        status: "scored" | "skipped" | "pending"
        skip_reason: "" for scored/pending, or reason string for skipped
    """
    raw = c.get("kimi_rating_raw", "")
    if c["kimi_rating"] is not None:
        return "scored", ""
    if raw.lower().startswith("skipped"):
        # Parse skip reason from rationale
        rationale = c.get("kimi_rationale", "")
        if "no resume" in rationale.lower():
            return "skipped", "No resume"
        if "target rate" in rationale.lower() or "exceeds" in rationale.lower() or "below" in rationale.lower():
            return "skipped", "Rate out of bounds"
        return "skipped", "Other"
    return "pending", ""


def compute_screening_backlog(candidates: list[dict]) -> dict:
    """Compute Kimi screening backlog for last 24h and last 7d.

    Breaks down into scored / skipped (with reasons) / pending,
    plus recommendation tier distribution for scored candidates.
    """
    now_sgt = datetime.now(SGT)
    cutoff_24h = now_sgt - timedelta(hours=24)
    cutoff_7d = now_sgt - timedelta(days=7)

    def _kimi_stats(group):
        total = len(group)
        scored = 0
        skipped = 0
        pending = 0
        skip_reasons: Counter = Counter()
        tiers: Counter = Counter()

        for c in group:
            status, reason = _classify_screening(c)
            if status == "scored":
                scored += 1
                rec = c.get("kimi_recommendation") or "Unknown"
                tiers[rec] += 1
            elif status == "skipped":
                skipped += 1
                skip_reasons[reason] += 1
            else:
                pending += 1

        processed = scored + skipped
        return {
            "total": total,
            "scored": scored,
            "skipped": skipped,
            "pending": pending,
            "processed_pct": (processed / total * 100) if total else 0,
            "skip_reasons": skip_reasons,
            "tiers": tiers,
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
    COST_R2 = 10
    COST_ALIGNMENT = 80

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
    conversion_funnel: dict | None = None,
    channel_quality: list[dict] | None = None,
    hiring_efficiency: dict | None = None,
    daily_channel_volume: dict | None = None,
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

    # 2. Daily EP Applications by Channel (last 7d)
    if daily_channel_volume and daily_channel_volume["channels"]:
        p()
        p(f"*2. Daily EP Applications by Channel (last 7d)*")
        p(f"```")
        dates = daily_channel_volume["dates"]
        channels = daily_channel_volume["channels"]
        grid = daily_channel_volume["grid"]
        totals = daily_channel_volume["totals"]

        day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        col_w = max(max((len(ch) for ch in channels), default=5), 5)

        # Header
        hdr = f"{'Date':<10} {'Day':<3}"
        for ch in channels:
            hdr += f"  {ch:>{col_w}}"
        hdr += f"  {'Total':>{col_w}}"
        p(hdr)

        # Daily rows
        grand_total = 0
        for date_str in dates:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            dow = day_names[dt.weekday()]
            row_counter = grid[date_str]
            row_total = sum(row_counter.values())
            grand_total += row_total

            line = f"{date_str:<10} {dow:<3}"
            for ch in channels:
                v = row_counter.get(ch, 0)
                line += f"  {v:>{col_w}}"
            line += f"  {row_total:>{col_w}}"
            p(line)

        # Separator + totals
        sep_w = 10 + 1 + 3 + (col_w + 2) * (len(channels) + 1)
        p(f"{'─' * sep_w}")
        total_line = f"{'Total':<10} {'':3}"
        for ch in channels:
            total_line += f"  {totals.get(ch, 0):>{col_w}}"
        total_line += f"  {grand_total:>{col_w}}"
        p(total_line)

        # Avg per day
        n_days = len(dates)
        avg_line = f"{'Avg/day':<10} {'':3}"
        for ch in channels:
            avg = totals.get(ch, 0) / n_days if n_days else 0
            avg_line += f"  {avg:>{col_w}.1f}"
        avg_total = grand_total / n_days if n_days else 0
        avg_line += f"  {avg_total:>{col_w}.1f}"
        p(avg_line)
        p(f"```")

    # 3. Candidate Breakdown (last 7 completed days)
    p()
    p(f"*3. Candidate Breakdown (last 7d)*")
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

    # 4. EP Conversion Funnel
    if conversion_funnel:
        p()
        p(f"*4. EP Conversion Funnel*")
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

    # 5. EP Channel Quality (last 60d)
    if channel_quality:
        p()
        p(f"*5. EP Channel Quality (last 60d)*")
        p(f"```")
        p(f"{'Channel':<15} {'Applied':>7}  {'Invited':>7}  {'Inv%':>5}  {'R1 Proc':>7}  {'R1%':>5}  {'R2 Proc':>7}  {'R2%':>5}")
        for row in channel_quality:
            inv_pct = _pct(row["invited"], row["applied"])
            r1_pct = _pct(row["r1_proceed"], row["applied"])
            r2_pct = _pct(row["r2_proceed"], row["applied"])
            p(f"{row['channel']:<15} {row['applied']:>7}  {row['invited']:>7}  {inv_pct:>5}  {row['r1_proceed']:>7}  {r1_pct:>5}  {row['r2_proceed']:>7}  {r2_pct:>5}")
        p(f"```")

    # 6. Hiring Efficiency
    if hiring_efficiency:
        p()
        p(f"*6. Hiring Efficiency [Under Review]*")
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
            ("R2 ($10 ea)", "cost_r2"),
            ("Alignment ($80 ea)", "cost_alignment"),
            ("Total Interview Cost", "cost_total"),
            ("Cost per Hire", "cost_per_hire"),
        ]
        for label, key in cost_rows:
            line = f"  {label:<20}"
            for w in windows:
                line += f"  {_cost(he[w][key]):>10}"
            p(line)

        p(f"```")

    # 7. Screening Backlog (Kimi)
    p()
    p(f"*7. Screening Backlog (Kimi)*")
    p(f"```")
    p(f"{'':10} {'Total':>5}  {'Scored':>6}  {'Skipped':>7}  {'Pending':>7}  {'Processed':>9}")
    b24 = backlog["24h"]
    b7d = backlog["7d"]
    p(f"{'Last 24h':10} {b24['total']:>5}  {b24['scored']:>6}  {b24['skipped']:>7}  {b24['pending']:>7}  {b24['processed_pct']:>8.0f}%")
    p(f"{'Last 7d':10} {b7d['total']:>5}  {b7d['scored']:>6}  {b7d['skipped']:>7}  {b7d['pending']:>7}  {b7d['processed_pct']:>8.0f}%")
    p(f"```")

    # Skip reasons (7d)
    if b7d["skip_reasons"]:
        p(f"```")
        p(f"Skip reasons (7d):")
        for reason, count in b7d["skip_reasons"].most_common():
            p(f"  {reason:<25} {count:>4}")
        p(f"```")

    # Recommendation tier distribution (7d)
    if b7d["tiers"]:
        tier_order = [
            "STRONG PROCEED",
            "PROCEED",
            "PROCEED WITH QUESTIONS",
            "PROCEED WITH CAUTION",
            "DO NOT PROCEED",
        ]
        max_tier = max(b7d["tiers"].values()) if b7d["tiers"] else 0
        p(f"```")
        p(f"Scored tiers (7d):")
        for tier in tier_order:
            count = b7d["tiers"].get(tier, 0)
            if count > 0:
                bar = _bar(count, max_tier, max_width=12)
                p(f"  {tier:<25} {count:>4}  {bar}")
        # Any tiers not in the expected list
        for tier, count in b7d["tiers"].most_common():
            if tier not in tier_order and count > 0:
                bar = _bar(count, max_tier, max_width=12)
                p(f"  {tier:<25} {count:>4}  {bar}")
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


INSIGHTS_PROMPT = """\
You are a recruitment operations analyst. Below is today's recruitment pipeline report.

Analyze the data and identify exactly 3 areas we should investigate to ultimately hire more people. For each area:
- Give it a short bold title with a relevant emoji
- Write 2-3 sentences: what the data shows, why it matters, and what to investigate

Be specific — cite actual numbers from the report. Keep it concise and actionable. Format for Slack (use *bold* not **bold**).

Report:
{report}
"""


def generate_insights(report: str) -> str | None:
    """Call Kimi to analyze the pipeline report and return top 3 insights.

    Returns formatted insights string, or None if MOONSHOT_API_KEY is not set.
    """
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")
    if not moonshot_key:
        print("Insights: skipped (MOONSHOT_API_KEY not set)")
        return None

    transport = httpx.HTTPTransport(retries=3, http2=True)
    http_client = httpx.Client(timeout=120.0, transport=transport, trust_env=False)

    client = OpenAI(
        api_key=moonshot_key,
        base_url="https://api.moonshot.ai/v1",
        http_client=http_client,
    )

    prompt = INSIGHTS_PROMPT.format(report=report)

    print("Generating insights...", end="", flush=True)
    stream = client.chat.completions.create(
        model="kimi-k2.5",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a sharp recruitment operations analyst. "
                    "You give concise, data-backed insights to help hiring teams improve."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        stream=True,
    )

    content_parts = []
    for chunk in stream:
        if (
            hasattr(chunk.choices[0].delta, "reasoning_content")
            and chunk.choices[0].delta.reasoning_content
        ):
            print("·", end="", flush=True)
        if chunk.choices[0].delta.content:
            content_parts.append(chunk.choices[0].delta.content)
            print(".", end="", flush=True)
    print(" done.")

    raw = "".join(content_parts).strip()
    if not raw:
        return None

    # Wrap in a section header
    return (
        "\n" + "─" * 50 + "\n\n"
        "*8. 🔍 Key Insights — Top 3 Areas to Improve Hiring*\n\n"
        + raw + "\n"
    )


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
    parser.add_argument(
        "--insights",
        action="store_true",
        default=False,
        help="Append AI-generated insights (top 3 areas to improve hiring)",
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
    daily_channel_volume = compute_daily_channel_volume(candidates, opening_names, post_channels, days=args.days)
    conversion_funnel = compute_conversion_funnel(candidates, opening_names)
    channel_quality = compute_channel_quality(candidates, opening_names, post_channels)
    hiring_efficiency = compute_hiring_efficiency(candidates)
    backlog = compute_screening_backlog(candidates)

    # Build and print report
    report = build_report(
        args.days, pipeline, candidate_breakdown, backlog,
        conversion_funnel, channel_quality,
        hiring_efficiency, daily_channel_volume,
    )
    print(report, end="")

    # Generate LLM insights — auto on Mondays, or manually via --insights
    run_insights = args.insights or datetime.now(SGT).weekday() == 0  # 0 = Monday
    if run_insights:
        insights = generate_insights(report)
        if insights:
            report += insights
            print(insights)

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
