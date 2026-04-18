"""
News Scanner Library for Bioworld LinkedIn Automation.

Uses Kimi (Moonshot AI) with $web_search to discover recent news about
portfolio companies and the broader biotech/medtech industry.

Reuses HTTP/2 + tool-call loop from linkedin-content/libraries/web_researcher.py.
"""

import json
import re
from pathlib import Path

import httpx
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def _build_kimi_client(moonshot_key: str) -> OpenAI:
    """Build OpenAI-compatible client for Moonshot API with HTTP/2."""
    transport = httpx.HTTPTransport(retries=3, http2=True)
    http_client = httpx.Client(timeout=600.0, transport=transport, trust_env=False)
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
    """Parse JSON from Kimi's response, handling potential extra text."""
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


def generate_search_queries(company_name: str, keywords: str,
                            moonshot_key: str) -> list[str]:
    """Generate 2-3 targeted search queries for a specific company."""
    client = _build_kimi_client(moonshot_key)

    response = client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate web search queries to find recent news about "
                    "biotech/medtech companies. Return a JSON array of 2-3 search "
                    "query strings. Focus on finding: FDA approvals, funding rounds, "
                    "partnerships, clinical trial results, product launches, executive "
                    "appointments. Respond with ONLY a JSON array, no other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Keywords: {keywords}\n\n"
                    "Generate 2-3 search queries to find the most recent, "
                    "newsworthy developments about this company."
                ),
            },
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

    return [f'"{company_name}" news 2026', f"{company_name} {keywords.split()[0]}"]


def search_company_news(company_name: str, queries: list[str],
                        moonshot_key: str) -> dict:
    """
    Search for news about a specific company using Kimi with $web_search.

    Returns dict with 'sources' list and 'synthesis' string.
    """
    research_prompt_path = TEMPLATE_DIR / "research-prompt.md"
    research_prompt = research_prompt_path.read_text(encoding="utf-8")

    client = _build_kimi_client(moonshot_key)

    user_content = (
        f"## Company: {company_name}\n\n"
        f"## Search Queries\n"
        + "\n".join(f"- {q}" for q in queries)
        + "\n\nSearch for each query and report the most significant recent news. "
        "Return your findings as the JSON format specified in the system prompt."
    )

    messages = [
        {"role": "system", "content": research_prompt},
        {"role": "user", "content": user_content},
    ]

    tools = [
        {"type": "builtin_function", "function": {"name": "$web_search"}}
    ]

    print(f"  [{company_name}", end="", flush=True)

    max_rounds = 10
    for _ in range(max_rounds):
        stream = client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=messages,
            tools=tools,
            stream=True,
        )

        content_parts = []
        tool_calls_data = {}
        finish_reason = None

        for chunk in stream:
            choice = chunk.choices[0]

            if hasattr(choice.delta, "reasoning_content") and choice.delta.reasoning_content:
                print(".", end="", flush=True)

            if choice.delta.content:
                content_parts.append(choice.delta.content)
                print(".", end="", flush=True)

            if choice.delta.tool_calls:
                for tc in choice.delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_data:
                        tool_calls_data[idx] = {
                            "id": tc.id or "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.id:
                        tool_calls_data[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_data[idx]["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_data[idx]["function"]["arguments"] += tc.function.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        if finish_reason == "tool_calls" and tool_calls_data:
            tool_calls_list = [tool_calls_data[i] for i in sorted(tool_calls_data.keys())]
            assistant_msg = {
                "role": "assistant",
                "content": "".join(content_parts) if content_parts else None,
                "tool_calls": tool_calls_list,
            }
            messages.append(assistant_msg)

            for tc in tool_calls_list:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": "Search completed.",
                })
            print("->", end="", flush=True)
            continue

        break

    print("]")

    raw_response = "".join(content_parts).strip()
    try:
        result = _parse_json_response(raw_response)
    except ValueError:
        result = {"sources": [], "synthesis": raw_response}

    return result


def search_industry_news(queries: list[str], moonshot_key: str) -> dict:
    """Search for general biotech/medtech industry news."""
    return search_company_news("Biotech/MedTech Industry", queries, moonshot_key)


def rank_articles(articles: list[dict], top_n: int = 5) -> list[dict]:
    """
    Rank articles by relevance score and return the top N.

    Each article dict should have a 'relevance_score' key (1-10).
    """
    sorted_articles = sorted(
        articles,
        key=lambda a: a.get("relevance_score", 0),
        reverse=True,
    )
    return sorted_articles[:top_n]
