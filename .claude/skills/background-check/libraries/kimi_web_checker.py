"""
Background Check Library

Three-step pattern:
  1. generate_search_queries() — Kimi generates targeted queries (no web search)
  2. gemini_search_and_analyze() — Gemini with Google Search grounding searches + analyzes
  3. save_receipt() — Save results to local-data

Uses Kimi for query generation (good at disambiguation) and Gemini with
Google Search grounding for the actual search + analysis (uses google.com's
real index — catches Facebook groups, forums, complaint sites, etc.).
"""

import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from google import genai
from google.genai import types
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
GEMINI_MODEL = "gemini-2.5-flash"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "local-data" / "talent" / "background_checks"


def _build_kimi_client(moonshot_key: str) -> OpenAI:
    """Build OpenAI-compatible client for Moonshot API with HTTP/2."""
    transport = httpx.HTTPTransport(
        retries=3,
        http2=True,
    )
    http_client = httpx.Client(
        timeout=600.0,
        transport=transport,
        trust_env=False,
    )
    return OpenAI(
        api_key=moonshot_key,
        base_url="https://api.moonshot.ai/v1",
        http_client=http_client,
    )


def _clean_json_output(text: str) -> str:
    """Strip markdown code blocks from API output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _parse_json_response(response: str) -> dict:
    """Parse JSON from AI response, handling potential extra text."""
    cleaned = _clean_json_output(response)

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


def generate_search_queries(candidate_data: dict, moonshot_key: str) -> list[str]:
    """
    Generate targeted search queries for a candidate background check.

    Step 1 — Kimi generates queries from candidate info (no web search).

    Args:
        candidate_data: Dict with 'name', 'location', 'employers', 'resume_text'
        moonshot_key: Moonshot API key

    Returns:
        List of 4-6 search query strings
    """
    prompt_path = TEMPLATE_DIR / "query-generation-prompt.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    name = candidate_data["name"]
    location = candidate_data.get("location", "")
    employers = candidate_data.get("employers", "")
    resume_excerpt = candidate_data.get("resume_text", "")[:2000]

    user_content = (
        f"Candidate: {name}\n"
        f"Location: {location or 'Not specified'}\n"
        f"Key employers: {employers or 'See resume excerpt'}\n\n"
        f"Resume excerpt (first 2000 chars):\n{resume_excerpt}"
    )

    client = _build_kimi_client(moonshot_key)

    response = client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    raw = response.choices[0].message.content.strip()
    cleaned = _clean_json_output(raw)

    try:
        queries = json.loads(cleaned)
        if isinstance(queries, list):
            return queries
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Last resort: generate basic queries from name
    fallback = [
        f'"{name}" LinkedIn',
        f'"{name}" lawsuit OR fraud OR criminal',
        f'"{name}" Facebook OR Instagram',
    ]
    if location:
        fallback[0] += f" {location}"
    return fallback


def gemini_search_and_analyze(
    candidate_data: dict,
    queries: list[str],
    gemini_api_key: str,
) -> dict:
    """
    Search and analyze using Gemini with Google Search grounding.

    Step 2 — Gemini uses Google's actual search index to find and analyze
    information about the candidate. Single call that searches + analyzes.

    Args:
        candidate_data: Dict with 'name', 'resume_text'
        queries: Search queries from generate_search_queries()
        gemini_api_key: Google AI Studio API key

    Returns:
        Dict with 'result' (parsed analysis), 'sources' (grounding chunks),
        'search_queries' (queries Gemini actually used), 'raw_response'
    """
    prompt_path = TEMPLATE_DIR / "background-check-prompt.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    name = candidate_data["name"]
    resume_excerpt = candidate_data.get("resume_text", "")[:3000]

    user_content = (
        f"## Candidate\n{name}\n\n"
        f"## Resume Excerpt\n{resume_excerpt}\n\n"
        f"## Search Queries to Investigate\n"
        + "\n".join(f"- {q}" for q in queries)
        + "\n\nSearch for each query using Google Search and analyze the findings."
    )

    client = genai.Client(api_key=gemini_api_key)

    google_search_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    config = types.GenerateContentConfig(
        tools=[google_search_tool],
        system_instruction=system_prompt,
    )

    print("  [Gemini+Google", end="", flush=True)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_content,
        config=config,
    )

    print(".]")

    raw_response = response.text.strip()

    # Extract grounding metadata
    sources = []
    search_queries_used = []

    grounding_metadata = getattr(
        response.candidates[0], "grounding_metadata", None
    )
    if grounding_metadata:
        search_queries_used = list(
            getattr(grounding_metadata, "web_search_queries", []) or []
        )
        for chunk in getattr(grounding_metadata, "grounding_chunks", []) or []:
            web = getattr(chunk, "web", None)
            if web:
                sources.append(
                    {
                        "title": getattr(web, "title", ""),
                        "uri": getattr(web, "uri", ""),
                    }
                )

    # Parse the structured JSON response
    try:
        result = _parse_json_response(raw_response)
    except ValueError:
        result = {
            "categories": {},
            "overall_recommendation": "Review Recommended",
            "confidence": "Low",
            "confidence_reasoning": "Could not parse structured response from AI",
            "summary": raw_response[:500],
        }

    return {
        "result": result,
        "sources": sources,
        "search_queries_used": search_queries_used,
        "raw_response": raw_response,
    }


def save_receipt(receipt_data: dict, candidate_name: str) -> Path:
    """
    Save background check receipt to local-data.

    Args:
        receipt_data: Full receipt dict to save
        candidate_name: Candidate name for filename

    Returns:
        Path to saved receipt file
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    clean_name = re.sub(r"[^\w\s-]", "", candidate_name)
    clean_name = re.sub(r"\s+", "_", clean_name).strip("_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filepath = DATA_DIR / f"{clean_name}_{timestamp}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(receipt_data, f, indent=2, ensure_ascii=False)

    return filepath
