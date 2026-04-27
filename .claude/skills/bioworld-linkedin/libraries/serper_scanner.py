"""
Serper + Claude CLI News Scanner.

Uses Serper.dev (Google Search API) to find articles, then Claude CLI
to analyze and score them. Designed for local execution.

Free tier: 2,500 searches/month at serper.dev.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import requests

SERPER_ENDPOINT = "https://google.serper.dev/search"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def serper_search(queries: list[str], serper_api_key: str,
                  results_per_query: int = 5) -> list[dict]:
    """
    Run Google searches via Serper.dev API.

    Returns deduplicated list of {title, url, snippet, query}.
    """
    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json",
    }

    all_results = []
    seen_urls = set()

    for query in queries:
        payload = {"q": query, "num": results_per_query}

        try:
            resp = requests.post(
                SERPER_ENDPOINT, headers=headers, json=payload, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"    [WARN] Serper query failed: {query[:60]}... — {e}")
            continue

        for item in data.get("organic", []):
            link = item.get("link", "")
            if link and link not in seen_urls:
                seen_urls.add(link)
                is_linkedin = "linkedin.com" in link
                all_results.append({
                    "title": item.get("title", ""),
                    "url": link,
                    "snippet": item.get("snippet", ""),
                    "query": query,
                    "is_linkedin": is_linkedin,
                })

    return all_results


def generate_search_queries_serper(company_name: str, keywords: str) -> list[str]:
    """Generate search queries for a company — last 3 months only."""
    from datetime import datetime, timedelta
    three_months_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    date_filter = f"after:{three_months_ago}"

    base_terms = keywords.split()[:3]
    keyword_str = " ".join(base_terms) if base_terms else company_name

    return [
        f'site:linkedin.com "{company_name}" post {date_filter}',
        f'"{company_name}" news {date_filter}',
        f'"{company_name}" FDA OR funding OR partnership OR launch {date_filter}',
        f'{keyword_str} latest development {date_filter}',
    ]


def analyze_with_claude(company_name: str, search_results: list[dict]) -> dict:
    """
    Use Claude CLI to analyze search results and extract structured article data.

    Returns dict with 'sources' list and 'synthesis' string.
    """
    if not search_results:
        return {"sources": [], "synthesis": f"No search results found for {company_name}."}

    research_prompt_path = TEMPLATE_DIR / "research-prompt.md"
    research_prompt = research_prompt_path.read_text(encoding="utf-8")

    results_text = ""
    for i, r in enumerate(search_results, 1):
        linkedin_tag = " [LINKEDIN POST]" if r.get("is_linkedin") else ""
        results_text += (
            f"\n{i}. **{r['title']}**{linkedin_tag}\n"
            f"   URL: {r['url']}\n"
            f"   Snippet: {r['snippet']}\n"
        )

    prompt = (
        f"{research_prompt}\n\n"
        f"## Company: {company_name}\n\n"
        f"## Search Results\n{results_text}\n\n"
        "Analyze these search results. For each relevant article, extract:\n"
        "- title, url, key_insight (one sentence), source_type, relevance_score (1-10)\n\n"
        "Return your analysis as JSON with 'sources' array and 'synthesis' paragraph.\n"
        "Return ONLY valid JSON, no other text."
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--print"],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            return {"sources": [], "synthesis": f"Claude analysis failed: {result.stderr[:200]}"}

        output = result.stdout.strip()
        return _parse_json_response(output)

    except subprocess.TimeoutExpired:
        return {"sources": [], "synthesis": "Claude analysis timed out."}
    except FileNotFoundError:
        return {"sources": [], "synthesis": "Claude CLI not found. Install claude-code."}


def search_company_news_serper(company_name: str, keywords: str,
                               serper_api_key: str) -> dict:
    """
    Full pipeline: generate queries → Serper search → Claude analysis.

    Returns dict with 'sources' and 'synthesis'.
    """
    print(f"  [{company_name}", end="", flush=True)

    queries = generate_search_queries_serper(company_name, keywords)
    print(".", end="", flush=True)

    results = serper_search(queries, serper_api_key)
    print(f".{len(results)} results", end="", flush=True)

    analysis = analyze_with_claude(company_name, results)
    print("]")

    return analysis


def search_industry_news_serper(serper_api_key: str) -> dict:
    """Search for general biotech/medtech industry news via Serper."""
    config_path = TEMPLATE_DIR / "brand-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    queries = config.get("industry_searches", [])

    print(f"  [Industry News", end="", flush=True)
    results = serper_search(queries, serper_api_key)
    print(f".{len(results)} results", end="", flush=True)

    analysis = analyze_with_claude("Biotech/MedTech Industry", results)
    print("]")

    return analysis


def _parse_json_response(response: str) -> dict:
    """Parse JSON from Claude's response."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return {"sources": [], "synthesis": text}
