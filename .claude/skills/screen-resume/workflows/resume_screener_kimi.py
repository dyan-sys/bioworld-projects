"""
Resume Screener Workflow (Kimi / Moonshot AI Version)

Screens candidates from Notion by:
1. Querying for candidates without a Kimi Rating (most recent first)
2. Extracting resume text from PDF URLs
3. Scoring resumes using Moonshot AI API (kimi-k2.5)
4. Saving artifacts and updating Notion with scores
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

# Add skill root to path for library imports
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/screen-resume/workflows -> project root
sys.path.insert(0, str(SKILL_ROOT))

from libraries.pdf_tools import extract_text_from_url
from libraries.rubric_registry import get_rubric_path

# Load .env file if present
load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_DIR = PROJECT_ROOT / "local-data" / "talent"
RAW_TEXT_DIR = DATA_DIR / "resume_raw_txt"
RECEIPTS_DIR = DATA_DIR / "resume_receipts"

# Moonshot AI configuration
MOONSHOT_MODEL = "kimi-k2.5"  # Using thinking mode with HTTP/2 for VPN resilience


def load_env_keys() -> tuple[str, str, str]:
    """Load required environment variables."""
    notion_key = os.environ.get("NOTION_KEY")
    notion_db_id = os.environ.get("NOTION_DB_ID")
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not notion_db_id:
        missing.append("NOTION_DB_ID")
    if not moonshot_key:
        missing.append("MOONSHOT_API_KEY")

    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    return notion_key, notion_db_id, moonshot_key


def clean_name_for_filename(name: str) -> str:
    """Convert a candidate name to a safe filename."""
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned


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


def query_notion_candidates(notion_key: str, db_id: str, limit: int = 5) -> list[dict]:
    """
    Query Notion for candidates matching all criteria:
    - Kimi Rating is empty (unscored)
    - Created in last 72 hours
    - Availability = "Full-time (40 hours/week)"
    - Time zone contains "Asia"
    Sorted by Date Created (most recent first).
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Kimi Rating",
                    "rich_text": {"is_empty": True},
                },
                {
                    "timestamp": "created_time",
                    "created_time": {"on_or_after": cutoff_iso},
                },
                {
                    "property": "Availability",
                    "select": {"equals": "Full-time (40 hours/week)"},
                },
                {
                    "property": "Time zone",
                    "multi_select": {"contains": "Asia"},
                },
            ],
        },
        "sorts": [
            {
                "property": "Date Created",
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
    """Extract candidate name and resume URL from a Notion page."""
    properties = page.get("properties", {})

    # Get candidate name from "Full Name" (title field)
    name = "Unknown"
    if "Full Name" in properties:
        name_prop = properties["Full Name"]
        if name_prop.get("type") == "title":
            title_items = name_prop.get("title", [])
            if title_items:
                name = title_items[0].get("plain_text", "Unknown")

    # Get resume URL from "Resume" property (files type)
    resume_url = None
    if "Resume" in properties:
        resume_prop = properties["Resume"]
        files = resume_prop.get("files", [])
        if files:
            file_obj = files[0]
            if file_obj.get("type") == "external":
                resume_url = file_obj.get("external", {}).get("url")
            elif file_obj.get("type") == "file":
                resume_url = file_obj.get("file", {}).get("url")

    # Get Post relation ID (job opening will be extracted from Post page)
    post_relation_id = None
    if "Post" in properties:
        post_prop = properties["Post"]
        if post_prop.get("type") == "relation":
            relations = post_prop.get("relation", [])
            if relations:
                # Get first related Post page ID
                post_relation_id = relations[0].get("id")

    # Get Target Rate (rich_text field)
    target_rate = ""
    if "Target Rate" in properties:
        rate_prop = properties["Target Rate"]
        if rate_prop.get("type") == "rich_text":
            rate_items = rate_prop.get("rich_text", [])
            if rate_items:
                target_rate = rate_items[0].get("plain_text", "")

    return {
        "page_id": page.get("id"),
        "name": name,
        "resume_url": resume_url,
        "post_relation_id": post_relation_id,
        "target_rate": target_rate,
    }


def get_job_opening_from_post(notion_key: str, post_page_id: str) -> str:
    """
    Fetch the job opening ID from a related Post page.

    Args:
        notion_key: Notion API key
        post_page_id: ID of the related Post page

    Returns:
        Job opening ID (e.g., '251003-EP') or None if not found
    """
    url = f"https://api.notion.com/v1/pages/{post_page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        page = response.json()
        properties = page.get("properties", {})

        # Extract "Opening ID" formula field
        if "Opening ID" in properties:
            opening_id_prop = properties["Opening ID"]
            if opening_id_prop.get("type") == "formula":
                formula = opening_id_prop.get("formula", {})
                if formula.get("type") == "string":
                    return formula.get("string")

        return None

    except requests.RequestException as e:
        print(f"  [WARNING] Failed to fetch Post page: {e}")
        return None


def load_rubric(opening_id: str = None) -> tuple[str, str]:
    """
    Load the appropriate rubric based on Opening ID.

    Args:
        opening_id: Opening ID from Post (e.g., "251003-EP")

    Returns:
        Tuple of (rubric_content, job_title)
    """
    rubric_path, job_title = get_rubric_path(opening_id)
    with open(rubric_path, "r", encoding="utf-8") as f:
        return f.read(), job_title


def build_prompt(rubric: str, resume_text: str, candidate_name: str) -> str:
    """Build the user message for Moonshot AI API."""
    return f"""You are an expert recruiter screening Executive Partner candidates.

Use the following scoring rubric to evaluate the candidate's resume. Follow the rubric exactly and calculate all scores as specified.

<rubric>
{rubric}
</rubric>

IMPORTANT: You MUST respond with ONLY valid JSON. No markdown, no explanation, no code fences, just the raw JSON object.

The JSON must have this exact structure:
{{
  "candidate_name": "<name>",
  "final_score": <0-100>,
  "tier": "<Tier 1 Strong|Tier 2 Viable|Tier 3 Below>",
  "recommendation": "<STRONG PROCEED|PROCEED|PROCEED WITH QUESTIONS|PROCEED WITH CAUTION|DO NOT PROCEED>",
  "threshold_assessment": {{
    "experience_raw": <number>,
    "experience_pass": <true|false>,
    "skills_raw": <number>,
    "skills_pass": <true|false>,
    "communication_raw": <number>,
    "communication_pass": <true|false>,
    "thresholds_passed": "<0/3|1/3|2/3|3/3>"
  }},
  "bucket_scores": {{
    "education": {{"raw": <number>, "max": 6.0, "equivalent_0_4": <number>}},
    "experience_trajectory": {{"raw": <number>, "max": 19.0, "equivalent_0_4": <number>}},
    "skills": {{"raw": <number>, "max": 14.0, "equivalent_0_4": <number>}},
    "communication": {{"raw": <number>, "max": 4.0, "equivalent_0_4": <number>}},
    "context_knowledge": {{"raw": <number>, "max": 4.0, "equivalent_0_4": <number>}},
    "other_factors": {{"raw": <number>, "max": 8.0, "equivalent_0_4": <number>}}
  }},
  "rationale_detailed": {{
    "key_strengths": "<Detailed paragraph listing all notable strengths with specific evidence from resume>",
    "key_gaps": "<Detailed paragraph listing all gaps and concerns, noting which thresholds failed and why>",
    "recommendation_reasoning": "<WHY this recommendation - explain the decision based on score + thresholds>",
    "interview_focus": "<What to probe in interview, or N/A if DO NOT PROCEED>"
  }}
}}

---

Please score the following resume for candidate: {candidate_name}

<resume>
{resume_text}
</resume>

Remember: Respond with ONLY the JSON object, no other text."""


def score_resume_via_moonshot(prompt: str, moonshot_key: str) -> str:
    """
    Call Moonshot AI API using OpenAI SDK with streaming.

    Uses thinking mode (reasoning enabled) with HTTP/2 for better VPN resilience.
    Handles both reasoning_content (thinking) and content (final answer) streams.
    """
    import httpx

    # Create custom transport with HTTP/2 for better VPN resilience
    transport = httpx.HTTPTransport(
        retries=3,
        http2=True,  # HTTP/2 is much more resilient to VPN timeouts
    )

    # Configure httpx client with HTTP/2 transport
    http_client = httpx.Client(
        timeout=600.0,  # 10 minute timeout
        transport=transport,
        trust_env=False,  # Bypass system proxy/VPN for direct connection
    )

    # Initialize OpenAI client with Moonshot base URL
    client = OpenAI(
        api_key=moonshot_key,
        base_url="https://api.moonshot.ai/v1",
        http_client=http_client,
    )

    # Stream response with thinking mode enabled (no extra_body parameter)
    stream = client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {"role": "system", "content": "You are an expert recruiter. Respond with ONLY valid JSON, no markdown or extra text."},
            {"role": "user", "content": prompt}
        ],
        stream=True,
    )

    # Collect streamed chunks, handling both reasoning and content
    print("  [Thinking", end="", flush=True)
    content_parts = []

    for chunk in stream:
        # Print dot for thinking activity (reasoning_content)
        if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
            print("·", end="", flush=True)

        # Collect the actual final JSON (content)
        if chunk.choices[0].delta.content:
            content_parts.append(chunk.choices[0].delta.content)
            print(".", end="", flush=True)

    print("]")

    return "".join(content_parts).strip()


def clean_json_output(text: str) -> str:
    """Strip markdown code blocks from API output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_json_response(response: str) -> dict:
    """Parse JSON from Moonshot's response, handling potential extra text."""
    cleaned = clean_json_output(response)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response: {cleaned[:500]}...")


def format_detailed_rationale(score_result: dict) -> str:
    """Format the detailed rationale into a single text block for Notion."""
    final_score = score_result.get("final_score", 0)
    recommendation = score_result.get("recommendation", "UNKNOWN")

    # Threshold summary
    thresh = score_result.get("threshold_assessment", {})
    thresh_passed = thresh.get("thresholds_passed", "?/3")
    thresh_details = []
    if not thresh.get("experience_pass", True):
        thresh_details.append("Experience FAIL")
    else:
        thresh_details.append("Experience PASS")
    if not thresh.get("skills_pass", True):
        thresh_details.append("Skills FAIL")
    else:
        thresh_details.append("Skills PASS")
    if not thresh.get("communication_pass", True):
        thresh_details.append("Communication FAIL")
    else:
        thresh_details.append("Communication PASS")
    thresh_str = ", ".join(thresh_details)

    # Bucket scores summary
    buckets = score_result.get("bucket_scores", {})
    bucket_parts = []
    bucket_map = [
        ("education", "Education"),
        ("experience_trajectory", "Experience"),
        ("skills", "Skills"),
        ("communication", "Communication"),
        ("context_knowledge", "Context"),
        ("other_factors", "Other"),
    ]
    for key, label in bucket_map:
        b = buckets.get(key, {})
        eq = b.get("equivalent_0_4", 0)
        bucket_parts.append(f"{label} {eq}/4")
    bucket_str = ", ".join(bucket_parts)

    # Detailed sections
    detailed = score_result.get("rationale_detailed", {})
    strengths = detailed.get("key_strengths", "N/A")
    gaps = detailed.get("key_gaps", "N/A")
    reasoning = detailed.get("recommendation_reasoning", "N/A")
    interview = detailed.get("interview_focus", "N/A")

    lines = [
        f"FINAL SCORE: {final_score}/100 | THRESHOLDS: {thresh_passed} ({thresh_str})",
        "",
        f"BUCKET SCORES: {bucket_str}",
        "",
        f"KEY STRENGTHS: {strengths}",
        "",
        f"KEY GAPS: {gaps}",
        "",
        f"WHY {recommendation}: {reasoning}",
        "",
        f"INTERVIEW FOCUS: {interview}",
    ]

    return "\n".join(lines)


def update_notion_rating(
    notion_key: str,
    page_id: str,
    score: float,
    recommendation: str,
    rationale: str,
) -> None:
    """Update Notion page with Kimi rating, recommendation, and rationale."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "properties": {
            "Kimi Rating": {
                "rich_text": [{"text": {"content": str(round(score, 1))}}]
            },
            "Kimi Recommendation": {
                "select": {"name": recommendation}
            },
            "Kimi Rationale": {
                "rich_text": [{"text": {"content": rationale[:2000]}}]
            },
        }
    }

    response = requests.patch(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()


def parse_target_rate(rate_text: str) -> dict | None:
    """
    Parse free-form target rate text into a structured dict.

    Handles patterns like:
    - "$800/month", "$1,200/mo", "$5.50/hr"
    - "PHP 25,000", "₱25000"
    - "MYR 3,500", "RM 3500", "RM3,500/month"
    - "$800-$1200/month" (uses lower bound)
    - "1200" (bare number, defaults to monthly)

    Returns:
        {"amount": float, "period": "monthly"|"hourly", "currency": "USD"|"PHP"|"MYR", "raw": str}
        or None if unparseable.
    """
    if not rate_text or not rate_text.strip():
        return None

    raw = rate_text.strip()
    text = raw.lower()

    # Detect currency
    currency = "USD"
    if "php" in text or "₱" in text:
        currency = "PHP"
    elif "myr" in text or re.search(r"\brm\s*[\d,]", text):
        currency = "MYR"

    # Detect period
    period = "monthly"  # default
    if re.search(r"(/hr|/hour|hourly|per\s*hour)", text):
        period = "hourly"

    # Extract numeric value(s)
    # Remove currency symbols and letters for number extraction
    cleaned = re.sub(r"[₱$]", "", text)
    # Find numbers (with optional commas and decimals)
    numbers = re.findall(r"[\d,]+\.?\d*", cleaned)

    if not numbers:
        return None

    # Use the first number (lower bound if range)
    try:
        amount = float(numbers[0].replace(",", ""))
    except ValueError:
        return None

    if amount <= 0:
        return None

    return {
        "amount": amount,
        "period": period,
        "currency": currency,
        "raw": raw,
    }


# Approximate local currency to USD conversion rates
PHP_TO_USD = 1 / 56
MYR_TO_USD = 1 / 4.5


def check_rate_in_bounds(parsed_rate: dict, rate_bounds: dict) -> tuple[bool, str]:
    """
    Check if a parsed rate falls within the configured bounds.

    Args:
        parsed_rate: Output from parse_target_rate()
        rate_bounds: {"monthly": {"min": N, "max": N}, "hourly": {"min": N, "max": N}}

    Returns:
        (in_bounds: bool, reason: str)
    """
    amount = parsed_rate["amount"]
    period = parsed_rate["period"]
    currency = parsed_rate["currency"]
    raw = parsed_rate["raw"]

    # Convert local currencies to USD equivalent
    usd_amount = amount
    if currency == "PHP":
        usd_amount = amount * PHP_TO_USD
    elif currency == "MYR":
        usd_amount = amount * MYR_TO_USD

    bounds = rate_bounds.get(period)
    if not bounds:
        return True, ""

    min_val = bounds.get("min", 0)
    max_val = bounds.get("max", float("inf"))

    currency_note = f" (~${usd_amount:.0f} USD)" if currency in ("PHP", "MYR") else ""

    if usd_amount > max_val:
        return False, f"Target rate {raw}{currency_note} exceeds {period} cap of ${max_val}"
    if usd_amount < min_val:
        return False, f"Target rate {raw}{currency_note} below {period} floor of ${min_val}"

    return True, ""


def get_rate_bounds_for_job(opening_id: str | None) -> dict:
    """
    Load rate bounds from job-type-mapping.json based on opening ID.

    Falls back to default bounds if job type is unknown.
    """
    from libraries.rubric_registry import (
        JOB_TYPE_MAPPINGS,
        DEFAULT_MAPPING,
        extract_job_type_from_opening_id,
    )

    job_type = extract_job_type_from_opening_id(opening_id)
    if job_type and job_type in JOB_TYPE_MAPPINGS:
        mapping = JOB_TYPE_MAPPINGS[job_type]
    else:
        mapping = DEFAULT_MAPPING

    return mapping.get("rate_bounds", {})


def update_notion_rating_skip(notion_key: str, page_id: str, reason: str) -> None:
    """Write skip status to Notion Kimi fields (no recommendation set)."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "properties": {
            "Kimi Rating": {
                "rich_text": [{"text": {"content": "Skipped - Out of Criteria"}}]
            },
            "Kimi Rationale": {
                "rich_text": [{"text": {"content": reason[:2000]}}]
            },
        }
    }

    response = requests.patch(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()


def process_candidate(candidate: dict, notion_key: str, moonshot_key: str) -> dict:
    """Process a single candidate: extract, score, save, update."""
    name = candidate["name"]
    page_id = candidate["page_id"]
    resume_url = candidate["resume_url"]
    post_relation_id = candidate.get("post_relation_id")
    clean_name = clean_name_for_filename(name)

    result = {"name": name, "status": "pending", "error": None}

    if not resume_url:
        result["status"] = "skipped"
        result["error"] = "No resume URL found"
        print(f"  [SKIP] No resume URL")
        return result

    try:
        # Get job opening from Post relation
        job_opening = None
        if post_relation_id:
            print(f"  [POST] Fetching job opening from Post relation...")
            job_opening = get_job_opening_from_post(notion_key, post_relation_id)
            if job_opening:
                print(f"  [POST] Found job opening: {job_opening}")
            else:
                print(f"  [POST] No Opening ID found in Post")
        else:
            print(f"  [POST] No Post relation set")

        # Check rate bounds (before PDF download to save bandwidth)
        target_rate_text = candidate.get("target_rate", "")
        if target_rate_text:
            parsed_rate = parse_target_rate(target_rate_text)
            if parsed_rate:
                rate_bounds = get_rate_bounds_for_job(job_opening)
                if rate_bounds:
                    in_bounds, reason = check_rate_in_bounds(parsed_rate, rate_bounds)
                    if not in_bounds:
                        update_notion_rating_skip(notion_key, page_id, reason)
                        result["status"] = "skipped"
                        result["error"] = reason
                        print(f"  [SKIP] {reason}")
                        return result
                print(f"  [RATE] {target_rate_text} → in bounds")
            else:
                print(f"  [RATE] Could not parse '{target_rate_text}' — proceeding anyway")
        else:
            print(f"  [RATE] No target rate set — proceeding")

        # Load rubric based on Opening ID
        print(f"  [RUBRIC] Opening ID: {job_opening or 'Not specified (using default)'}")
        rubric, job_title = load_rubric(job_opening)
        print(f"  [RUBRIC] Job Title: {job_title}")

        # Extract text from PDF
        print(f"  [EXTRACT] Downloading and extracting PDF...")
        resume_text = extract_text_from_url(resume_url)

        # Save raw text
        text_path = RAW_TEXT_DIR / f"{clean_name}.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(resume_text)
        print(f"  [SAVE] Raw text -> {text_path.name}")

        # Build prompt and score via Moonshot AI
        print(f"  [SCORE] Calling Moonshot AI ({MOONSHOT_MODEL})...")
        prompt = build_prompt(rubric, resume_text, name)
        raw_output = score_resume_via_moonshot(prompt, moonshot_key)

        # Parse JSON response
        score_result = parse_json_response(raw_output)

        # Save receipt
        receipt_data = {
            "model": f"Kimi ({MOONSHOT_MODEL})",
            "parsed": score_result,
            "raw_output": raw_output,
        }
        receipt_path = RECEIPTS_DIR / f"{clean_name}_Kimi.json"
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt_data, f, indent=2)
        print(f"  [SAVE] Receipt -> {receipt_path.name}")

        # Update Notion
        final_score = score_result.get("final_score", 0)
        recommendation = score_result.get("recommendation", "UNABLE TO ASSESS")
        rationale = format_detailed_rationale(score_result)

        # Note fallback rubric usage in rationale
        if job_title and "(Default)" in job_title and job_opening:
            rationale = f"NOTE: Opening {job_opening} has no specific rubric — scored using standard Executive Partner rubric.\n\n{rationale}"

        print(f"  [UPDATE] Notion: Score={final_score}, Rec={recommendation}")
        update_notion_rating(notion_key, page_id, final_score, recommendation, rationale)

        result["status"] = "success"
        result["score"] = final_score
        result["recommendation"] = recommendation

    except requests.RequestException as e:
        result["status"] = "error"
        result["error"] = f"API/Network error: {e}"
        print(f"  [ERROR] {e}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  [ERROR] {type(e).__name__}: {e}")

    return result


def main():
    """Main workflow entry point."""
    # Parse CLI arguments
    parser = argparse.ArgumentParser(
        description="Score candidate resumes using Kimi AI (Moonshot)"
    )
    parser.add_argument(
        '--page-id',
        help='Score a single candidate by Notion page ID'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Number of candidates to process in batch mode (default: 5)'
    )
    args = parser.parse_args()

    print("=" * 60)
    print("RESUME SCREENER WORKFLOW (Kimi / Moonshot AI)")
    print("=" * 60)

    # Ensure directories exist
    RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load environment
    print("\n[1/3] Loading environment...")
    try:
        notion_key, notion_db_id, moonshot_key = load_env_keys()
        print("  NOTION_KEY, NOTION_DB_ID, and MOONSHOT_API_KEY loaded.")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # Get candidates (single or batch mode)
    print("\n[2/3] Fetching candidates...")
    if args.page_id:
        # Single candidate mode
        print(f"  Mode: Single candidate (page_id={args.page_id})")
        page = fetch_notion_page(notion_key, args.page_id)
        candidates = [get_candidate_info(page)]
    else:
        # Batch mode: last 72h, full-time, Asia timezone, unscored
        print(f"  Mode: Batch (limit={args.limit})")
        print(f"  Filters: last 72h | Full-time | Asia timezone | Kimi unscored")
        candidates_raw = query_notion_candidates(notion_key, notion_db_id, limit=args.limit)
        candidates = [get_candidate_info(c) for c in candidates_raw]

    print(f"  Found {len(candidates)} candidates to process")

    if not candidates:
        print("\n  No candidates to process. Exiting.")
        return

    # Process candidates
    print("\n[3/3] Processing candidates...")
    print("-" * 60)

    results = []
    for i, candidate in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {candidate['name']}")
        result = process_candidate(candidate, notion_key, moonshot_key)
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    success = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"  Processed: {success}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")

    for r in results:
        status_icon = {"success": "+", "skipped": "-", "error": "!"}[r["status"]]
        if r["status"] == "success":
            print(f"  [{status_icon}] {r['name']}: Score={r.get('score')} | {r.get('recommendation')}")
        else:
            print(f"  [{status_icon}] {r['name']}: {r.get('error', '')}")


if __name__ == "__main__":
    main()
