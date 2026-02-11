"""
Kimi Web Checker Library

Uses Kimi (Moonshot AI) with $web_search builtin tool to perform candidate
background checks — searching for online presence, verifying resume claims,
and flagging red flags.

Two-call pattern:
  Call 1 — generate_search_queries(): No web search, generates targeted queries
  Call 2 — run_background_check(): With $web_search, executes searches and analyzes

Adapted from linkedin-content/libraries/web_researcher.py — same HTTP/2 transport,
streaming, tool-call loop, and JSON parsing patterns.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
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


def generate_search_queries(candidate_data: dict, moonshot_key: str) -> list[str]:
    """
    Generate targeted search queries for a candidate background check.

    Call 1 — no web search, just query generation from candidate info.

    Args:
        candidate_data: Dict with 'name', 'location', 'employers', 'resume_text'
        moonshot_key: Moonshot API key

    Returns:
        List of 4-6 search query strings
    """
    prompt_path = TEMPLATE_DIR / "query-generation-prompt.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # Build context from candidate data
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

    # Fallback: extract array from response
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


def run_background_check(
    candidate_data: dict, queries: list[str], moonshot_key: str
) -> dict:
    """
    Run background check using Kimi with $web_search.

    Call 2 — with web search tool enabled. Handles the tool_calls loop
    where Kimi may call $web_search multiple times.

    Args:
        candidate_data: Dict with 'name', 'resume_text'
        queries: Search queries from generate_search_queries()
        moonshot_key: Moonshot API key

    Returns:
        Parsed background check result dict
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
        + "\n\nSearch for each query and analyze the findings."
    )

    client = _build_kimi_client(moonshot_key)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    tools = [
        {
            "type": "builtin_function",
            "function": {"name": "$web_search"},
        }
    ]

    print("  [Searching", end="", flush=True)

    # Tool-call loop (non-streaming to avoid thinking mode issues with
    # reasoning_content in assistant tool-call messages). Kimi may call
    # $web_search multiple times before returning final content.
    max_rounds = 15
    final_content = ""
    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=messages,
            tools=tools,
            stream=False,
        )

        choice = response.choices[0]
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls" and choice.message.tool_calls:
            # Kimi wants to use web search — echo back the assistant message.
            # kimi-k2.5 requires non-empty reasoning_content in assistant
            # tool-call messages (thinking mode is always on).
            tool_calls_list = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]
            assistant_msg = {
                "role": "assistant",
                "content": choice.message.content or "",
                "reasoning_content": "Performing web search.",
                "tool_calls": tool_calls_list,
            }
            messages.append(assistant_msg)

            # Add tool results (Kimi handles $web_search internally)
            for tc in tool_calls_list:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "Search completed.",
                    }
                )
            print("→", end="", flush=True)
            continue

        # Done — final content returned
        final_content = choice.message.content or ""
        print(".", end="", flush=True)
        break

    print("]")

    raw_response = final_content.strip()
    try:
        result = _parse_json_response(raw_response)
    except ValueError:
        # If JSON parsing fails, return a structured error result
        result = {
            "categories": {},
            "overall_recommendation": "Review Recommended",
            "confidence": "Low",
            "confidence_reasoning": "Could not parse structured response from AI",
            "summary": raw_response[:500],
        }

    result["raw_response"] = raw_response
    return result


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
