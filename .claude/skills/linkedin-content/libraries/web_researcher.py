"""
Web Researcher Library

Uses Kimi (Moonshot AI) with $web_search builtin tool to find and synthesize
recent, relevant ideas for LinkedIn content.

Adapted from flag-ep-issues/libraries/kimi_analyzer.py — same HTTP/2 transport,
streaming, and JSON parsing patterns.
"""

import json
import re
from pathlib import Path

import httpx
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "local-data" / "linkedin" / "research"


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
    """Parse JSON from Kimi's response, handling potential extra text."""
    cleaned = _clean_json_output(response)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the response
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response: {cleaned[:500]}...")


def _load_pillar_config() -> dict:
    """Load pillar configuration from templates."""
    config_path = TEMPLATE_DIR / "pillar-config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_search_queries(brief: str, pillar: str | None, moonshot_key: str) -> list[str]:
    """
    Generate targeted search queries from the user's brief.

    Call 1 — no web search, just query generation.
    """
    pillar_config = _load_pillar_config()

    pillar_context = ""
    if pillar and pillar in pillar_config["pillars"]:
        p = pillar_config["pillars"][pillar]
        pillar_context = (
            f"\nContent pillar: {p['name']} — {p['description']}\n"
            f"Seed topics: {', '.join(p['search_seeds'])}"
        )

    client = _build_kimi_client(moonshot_key)

    response = client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate web search queries for LinkedIn content research. "
                    "Return a JSON array of 2-3 search query strings. "
                    "Queries should find recent articles with original thinking, data, "
                    "or contrarian takes. Respond with ONLY a JSON array, no other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Brief: {brief}\n{pillar_context}\n\n"
                    "Generate 2-3 targeted search queries that will find interesting, "
                    "recent content related to this brief. Focus on finding practical "
                    "insights, not generic advice."
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

    # Fallback: extract strings from response
    json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Last resort: use pillar seeds + brief keywords
    fallback = [brief]
    if pillar and pillar in pillar_config["pillars"]:
        fallback.extend(pillar_config["pillars"][pillar]["search_seeds"][:2])
    return fallback


def research_topic(brief: str, queries: list[str], moonshot_key: str) -> dict:
    """
    Research the topic using Kimi with $web_search.

    Call 2 — with web search tool enabled. Handles the tool_calls loop
    where Kimi may call $web_search multiple times.
    """
    research_prompt_path = TEMPLATE_DIR / "research-prompt.md"
    research_prompt = research_prompt_path.read_text(encoding="utf-8")

    client = _build_kimi_client(moonshot_key)

    user_content = (
        f"## Brief\n{brief}\n\n"
        f"## Search Queries to Investigate\n"
        + "\n".join(f"- {q}" for q in queries)
        + "\n\nSearch for each query and synthesize the findings."
    )

    messages = [
        {"role": "system", "content": research_prompt},
        {"role": "user", "content": user_content},
    ]

    tools = [
        {
            "type": "builtin_function",
            "function": {"name": "$web_search"},
        }
    ]

    print("  [Researching", end="", flush=True)

    # Tool-call loop: Kimi may call $web_search multiple times
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

            if (
                hasattr(choice.delta, "reasoning_content")
                and choice.delta.reasoning_content
            ):
                print("·", end="", flush=True)

            if choice.delta.content:
                content_parts.append(choice.delta.content)
                print(".", end="", flush=True)

            # Accumulate tool calls
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
            # Kimi wants to use web search — append assistant message with tool_calls
            tool_calls_list = [tool_calls_data[i] for i in sorted(tool_calls_data.keys())]
            assistant_msg = {
                "role": "assistant",
                "content": "".join(content_parts) if content_parts else None,
                "tool_calls": tool_calls_list,
            }
            messages.append(assistant_msg)

            # Add tool results (Kimi handles $web_search internally,
            # we just need to acknowledge the calls)
            for tc in tool_calls_list:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": "Search completed.",
                })
            print("→", end="", flush=True)
            continue

        # Done — either "stop" or content returned
        break

    print("]")

    raw_response = "".join(content_parts).strip()
    try:
        result = _parse_json_response(raw_response)
    except ValueError:
        # If JSON parsing fails, return raw text as synthesis
        result = {
            "sources": [],
            "synthesis": raw_response,
        }

    result["raw_response"] = raw_response
    return result


def save_research(research_data: dict, date_str: str, slug: str) -> Path:
    """Save research results to local-data."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{date_str}_{slug}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(research_data, f, indent=2, ensure_ascii=False)
    return filepath
