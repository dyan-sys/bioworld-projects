"""
Resume Screener Workflow (Codex CLI Version)

Screens candidates from Notion by:
1. Querying for candidates without a Claude Rating (most recent first)
2. Extracting resume text from PDF URLs
3. Scoring resumes using Codex CLI (piped via stdin)
4. Saving artifacts and updating Notion with scores
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Add project root to path for library imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from libraries.pdf_tools import extract_text_from_url

# Load .env file if present
load_dotenv(PROJECT_ROOT / ".env")

# Paths
DATA_DIR = PROJECT_ROOT / "data" / "talent"
RAW_TEXT_DIR = DATA_DIR / "resume_raw_txt"
RECEIPTS_DIR = DATA_DIR / "resume_receipts"
RUBRIC_PATH = PROJECT_ROOT / "templates" / "resume-scorer-v4.md"


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


def clean_name_for_filename(name: str) -> str:
    """Convert a candidate name to a safe filename."""
    cleaned = re.sub(r"[^\w\s-]", "", name)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned


def query_notion_candidates(notion_key: str, db_id: str, limit: int = 5) -> list[dict]:
    """
    Query Notion for candidates where Status is "New Application"
    and "Manus Rating" is empty, sorted by Date Created (most recent first).
    """
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
                    "property": "Status",
                    "status": {"equals": "New Application"},
                },
                {
                    "property": "Manus Rating",
                    "rich_text": {"is_empty": True},
                },
            ]
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

    return {
        "page_id": page.get("id"),
        "name": name,
        "resume_url": resume_url,
    }


def load_rubric() -> str:
    """Load the scoring rubric from the template file."""
    with open(RUBRIC_PATH, "r", encoding="utf-8") as f:
        return f.read()


def build_prompt(rubric: str, resume_text: str, candidate_name: str) -> str:
    """Build the full prompt for Codex CLI (piped via stdin)."""
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


def score_resume_via_codex(prompt: str) -> str:
    """
    Call Codex CLI with the prompt piped via stdin.

    Uses --full-auto to bypass confirmation prompts.
    """
    result = subprocess.run(
        [
            "codex",
            "exec",
            "--model", "gpt-5.1",
            "--full-auto",
        ],
        input=prompt,  # Pipe the prompt via stdin
        text=True,
        capture_output=True,
        timeout=300,  # 5 minute timeout
    )

    if result.returncode != 0:
        raise RuntimeError(f"Codex CLI failed: {result.stderr}")

    return result.stdout.strip()


def clean_json_output(text: str) -> str:
    """Strip markdown code blocks from Codex output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first line (```json)
        lines = lines[1:]
        # Remove last line if it is ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_json_response(response: str) -> dict:
    """Parse JSON from Codex's response, handling potential extra text."""
    # Clean markdown code blocks first
    cleaned = clean_json_output(response)

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from response
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

    # Build the full rationale text
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
    """Update Notion page with rating, recommendation, and rationale."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {
        "properties": {
            "Manus Rating": {
                "rich_text": [{"text": {"content": str(round(score, 1))}}]
            },
            "Manus Recommendation": {
                "select": {"name": recommendation}
            },
            "Manus Rationale": {
                "rich_text": [{"text": {"content": rationale[:2000]}}]
            },
        }
    }

    response = requests.patch(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()


def process_candidate(candidate: dict, rubric: str, notion_key: str) -> dict:
    """Process a single candidate: extract, score, save, update."""
    name = candidate["name"]
    page_id = candidate["page_id"]
    resume_url = candidate["resume_url"]
    clean_name = clean_name_for_filename(name)

    result = {"name": name, "status": "pending", "error": None}

    if not resume_url:
        result["status"] = "skipped"
        result["error"] = "No resume URL found"
        print(f"  [SKIP] No resume URL")
        return result

    try:
        # Extract text from PDF
        print(f"  [EXTRACT] Downloading and extracting PDF...")
        resume_text = extract_text_from_url(resume_url)

        # Save raw text
        text_path = RAW_TEXT_DIR / f"{clean_name}.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(resume_text)
        print(f"  [SAVE] Raw text -> {text_path.name}")

        # Build prompt and score via Codex CLI
        print(f"  [SCORE] Calling Codex CLI...")
        prompt = build_prompt(rubric, resume_text, name)
        raw_output = score_resume_via_codex(prompt)

        # Parse JSON response
        score_result = parse_json_response(raw_output)

        # Save receipt (include raw output for debugging)
        receipt_data = {
            "model": "Codex (gpt-5.1)",
            "parsed": score_result,
            "raw_output": raw_output,
        }
        receipt_path = RECEIPTS_DIR / f"{clean_name}_Codex.json"
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt_data, f, indent=2)
        print(f"  [SAVE] Receipt -> {receipt_path.name}")

        # Update Notion
        final_score = score_result.get("final_score", 0)
        recommendation = score_result.get("recommendation", "UNABLE TO ASSESS")
        rationale = format_detailed_rationale(score_result)
        print(f"  [UPDATE] Notion: Score={final_score}, Rec={recommendation}")
        update_notion_rating(notion_key, page_id, final_score, recommendation, rationale)

        result["status"] = "success"
        result["score"] = final_score
        result["recommendation"] = recommendation

    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["error"] = "Codex CLI timed out (5 min)"
        print(f"  [ERROR] Timeout")
    except requests.RequestException as e:
        result["status"] = "error"
        result["error"] = f"Network error: {e}"
        print(f"  [ERROR] {e}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"  [ERROR] {e}")

    return result


def main():
    """Main workflow entry point."""
    print("=" * 60)
    print("RESUME SCREENER WORKFLOW (Codex CLI)")
    print("=" * 60)

    # Ensure directories exist
    RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load environment
    print("\n[1/4] Loading environment...")
    try:
        notion_key, notion_db_id = load_env_keys()
        print("  NOTION_KEY and NOTION_DB_ID loaded.")
    except EnvironmentError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # Load rubric
    print("\n[2/4] Loading scoring rubric...")
    rubric = load_rubric()
    print(f"  Rubric loaded ({len(rubric):,} characters)")

    # Query Notion
    print("\n[3/4] Querying Notion for candidates...")
    candidates_raw = query_notion_candidates(notion_key, notion_db_id, limit=5)
    candidates = [get_candidate_info(c) for c in candidates_raw]
    print(f"  Found {len(candidates)} candidates to process")

    if not candidates:
        print("\n  No candidates to process. Exiting.")
        return

    # Process candidates
    print("\n[4/4] Processing candidates...")
    print("-" * 60)

    results = []
    for i, candidate in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}] {candidate['name']}")
        result = process_candidate(candidate, rubric, notion_key)
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
