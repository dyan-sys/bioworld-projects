"""
Tavily News Scanner — AI-native search for Bioworld LinkedIn.

Uses Tavily API (tavily.com) which returns pre-analyzed, summarized
search results in a single call. Purpose-built for AI agents.

Free tier: 1,000 searches/month.
"""

import json
from pathlib import Path

import requests

TAVILY_ENDPOINT = "https://api.tavily.com/search"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def tavily_search(query: str, tavily_api_key: str, max_results: int = 5) -> list[dict]:
    """
    Run a single Tavily search query.

    Returns list of {title, url, content, score}.
    """
    payload = {
        "api_key": tavily_api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": True,
    }

    try:
        resp = requests.post(TAVILY_ENDPOINT, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"    [WARN] Tavily search failed: {query[:60]}... — {e}")
        return []

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "score": item.get("score", 0),
        })

    return results


def search_company_news_tavily(company_name: str, keywords: str,
                                tavily_api_key: str) -> dict:
    """
    Search for news about a company using Tavily.

    Returns dict with 'sources' list and 'synthesis' string.
    """
    print(f"  [{company_name}", end="", flush=True)

    base_terms = keywords.split()[:3]
    keyword_str = " ".join(base_terms) if base_terms else company_name

    queries = [
        f'"{company_name}" latest news 2026',
        f'{company_name} {keyword_str} FDA OR funding OR partnership',
    ]

    all_results = []
    seen_urls = set()

    for query in queries:
        results = tavily_search(query, tavily_api_key, max_results=5)
        print(".", end="", flush=True)
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_results.append(r)

    print(f".{len(all_results)} results]")

    # Convert to standard source format with scoring
    sources = []
    for r in all_results:
        # Tavily provides a relevance score 0-1, convert to 1-10
        relevance = min(10, max(1, int(r.get("score", 0.5) * 10)))
        content = r.get("content", "")

        # Detect source type from content
        source_type = "News"
        content_lower = content.lower()
        if "fda" in content_lower or "cleared" in content_lower or "approved" in content_lower:
            source_type = "Regulatory"
        elif "funding" in content_lower or "raised" in content_lower or "million" in content_lower:
            source_type = "Funding"
        elif "partner" in content_lower or "collaborat" in content_lower or "acquir" in content_lower:
            source_type = "Partnership"
        elif "press release" in content_lower or "announces" in content_lower:
            source_type = "Press Release"

        sources.append({
            "title": r["title"],
            "url": r["url"],
            "key_insight": content[:300] if content else "",
            "source_type": source_type,
            "relevance_score": relevance,
        })

    # Sort by relevance
    sources.sort(key=lambda s: s["relevance_score"], reverse=True)

    # Build synthesis from top results
    synthesis_parts = []
    for s in sources[:5]:
        if s.get("key_insight"):
            synthesis_parts.append(f"- {s['title']}: {s['key_insight'][:150]}")

    synthesis = f"Found {len(sources)} articles about {company_name}.\n" + "\n".join(synthesis_parts)

    return {"sources": sources, "synthesis": synthesis}


def search_industry_news_tavily(tavily_api_key: str) -> dict:
    """Search for general biotech/medtech industry news via Tavily."""
    config_path = TEMPLATE_DIR / "brand-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    queries = config.get("industry_searches", [])

    print(f"  [Industry News", end="", flush=True)

    all_results = []
    seen_urls = set()

    for query in queries:
        results = tavily_search(query, tavily_api_key, max_results=3)
        print(".", end="", flush=True)
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_results.append(r)

    print(f".{len(all_results)} results]")

    sources = []
    for r in all_results:
        relevance = min(10, max(1, int(r.get("score", 0.5) * 10)))
        sources.append({
            "title": r["title"],
            "url": r["url"],
            "key_insight": r.get("content", "")[:300],
            "source_type": "News",
            "relevance_score": relevance,
        })

    sources.sort(key=lambda s: s["relevance_score"], reverse=True)
    synthesis = f"Found {len(sources)} industry articles."

    return {"sources": sources, "synthesis": synthesis}
