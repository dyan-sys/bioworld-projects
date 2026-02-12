"""
Background Check Library

Three-step pattern:
  1. generate_search_queries() — Deterministic template generates ~15-18 queries
  2. serper_search() — Serper.dev executes queries against Google (full site: support)
  3. kimi_analyze() — Kimi k2.5 analyzes search results (analysis only, no web search)
  4. save_receipt() — Save results to local-data

Uses deterministic query templates (better coverage than AI-generated queries),
Serper.dev for real Google results with full site: operator support, and Kimi k2.5
for analysis only.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import httpx
import requests
from openai import OpenAI

KIMI_MODEL = "kimi-k2.5"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "local-data" / "talent" / "background_checks"

SERPER_ENDPOINT = "https://google.serper.dev/search"


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


def _name_variations(name: str) -> list[str]:
    """Generate quoted name variations for search queries."""
    parts = name.strip().split()
    variations = [f'"{name}"']
    if len(parts) >= 3:
        # First + Last (skip middle)
        variations.append(f'"{parts[0]} {parts[-1]}"')
    return variations


def generate_search_queries(candidate_data: dict) -> list[str]:
    """
    Generate targeted search queries using deterministic templates.

    Produces ~15-18 queries covering LinkedIn, Facebook (profile + groups),
    Instagram, TikTok, Threads, news/legal, Philippines-specific checks,
    employer cross-reference, education, professional contributions,
    freelance platforms, and regional forums.

    Args:
        candidate_data: Dict with 'name', 'location', 'employers',
            'email_prefix', 'school', 'job_title'

    Returns:
        List of search query strings
    """
    name = candidate_data["name"]
    location = candidate_data.get("location", "")
    employers = candidate_data.get("employers", "")
    email_prefix = candidate_data.get("email_prefix", "")
    school = candidate_data.get("school", "")
    job_title = candidate_data.get("job_title", "")

    names = _name_variations(name)
    primary = names[0]  # Always quoted full name
    name_or = " OR ".join(names)

    queries = []

    # --- LinkedIn ---
    queries.append(f"site:linkedin.com/in {name_or}")
    if location:
        queries.append(f"site:linkedin.com {primary} {location}")

    # --- Facebook profile + group posts ---
    queries.append(f"site:facebook.com {name_or}")
    queries.append(
        f"site:facebook.com {primary} scam OR beware OR \"do not hire\" OR FFO OR fraud"
    )

    # --- Social media handles (from email prefix) ---
    if email_prefix:
        queries.append(
            f"site:instagram.com {email_prefix} OR site:tiktok.com/@{email_prefix} "
            f"OR site:threads.net/@{email_prefix}"
        )
    else:
        queries.append(
            f"site:instagram.com {primary} OR site:tiktok.com {primary} "
            f"OR site:threads.net {primary}"
        )

    # --- News / Legal ---
    queries.append(f"{primary} lawsuit OR fraud OR criminal OR scam OR estafa")
    if location:
        queries.append(f"{primary} {location} complaint OR arrested OR convicted")

    # --- Philippines-specific ---
    queries.append(f"{primary} NBI OR court OR \"criminal record\" Philippines")

    # --- Employer cross-reference ---
    employer_list = [e.strip() for e in employers.split(";") if e.strip()]
    for emp in employer_list[:3]:
        queries.append(f"{primary} \"{emp}\"")

    # --- Education verification ---
    if school:
        queries.append(f"{primary} \"{school}\"")

    # --- Professional contributions ---
    queries.append(f"{primary} blog OR github OR portfolio OR conference")
    if job_title:
        queries.append(f"{primary} {job_title}")

    # --- Freelance platforms ---
    queries.append(
        f"site:onlinejobs.ph {primary} OR site:upwork.com {primary}"
    )

    # --- Regional forums / news ---
    queries.append(
        f"{primary} site:rappler.com OR site:inquirer.net OR site:philstar.com OR site:reddit.com"
    )

    return queries


def serper_search(
    queries: list[str],
    serper_api_key: str,
    results_per_query: int = 10,
) -> list[dict]:
    """
    Execute search queries via Serper.dev and return deduplicated results.

    Args:
        queries: List of search query strings
        serper_api_key: Serper.dev API key
        results_per_query: Number of results per query (default: 10)

    Returns:
        List of dicts with 'title', 'link', 'snippet', 'query'
    """
    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json",
    }

    all_results = []
    seen_urls = set()

    for query in queries:
        payload = {
            "q": query,
            "num": results_per_query,
        }

        try:
            resp = requests.post(
                SERPER_ENDPOINT, headers=headers, json=payload, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"    [WARN] Serper query failed: {query[:60]}... — {e}")
            continue

        organic = data.get("organic", [])
        for item in organic:
            link = item.get("link", "")
            if link and link not in seen_urls:
                seen_urls.add(link)
                all_results.append({
                    "title": item.get("title", ""),
                    "link": link,
                    "snippet": item.get("snippet", ""),
                    "query": query,
                })

    return all_results


def kimi_analyze(
    candidate_data: dict,
    search_results: list[dict],
    moonshot_key: str,
) -> dict:
    """
    Analyze search results using Kimi k2.5 (analysis only, no web search).

    Args:
        candidate_data: Dict with 'name', 'resume_text'
        search_results: Deduplicated results from serper_search()
        moonshot_key: Moonshot API key

    Returns:
        Dict with 'result' (parsed analysis), 'raw_response'
    """
    prompt_path = TEMPLATE_DIR / "background-check-prompt.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    name = candidate_data["name"]
    resume_excerpt = candidate_data.get("resume_text", "")[:1500]

    # Format search results — title, link, snippet only
    results_text = ""
    for i, r in enumerate(search_results, 1):
        results_text += f"{i}. {r['title']}\n   {r['link']}\n   {r.get('snippet', '')}\n\n"

    if not results_text:
        results_text = "(No search results found.)\n"

    user_content = (
        f"Candidate: {name}\n\n"
        f"Resume excerpt:\n{resume_excerpt}\n\n"
        f"Search results ({len(search_results)}):\n\n"
        f"{results_text}"
    )

    client = _build_kimi_client(moonshot_key)

    print("  [Kimi", end="", flush=True)

    response = client.chat.completions.create(
        model=KIMI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    print(".]")

    raw_response = response.choices[0].message.content.strip()

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
