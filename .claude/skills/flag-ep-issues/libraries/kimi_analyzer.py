"""
Kimi Analyzer Library

Sends batched channel transcripts to Moonshot AI (Kimi) for analysis.
Adapted from screen-resume/workflows/resume_screener_kimi.py — same HTTP/2
transport, streaming, and JSON parsing patterns.
"""

import json
import re
from pathlib import Path

import httpx
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def build_prompt(date_str: str, channel_transcripts: list[str]) -> str:
    """
    Load analysis-prompt.md and inject date + channel transcripts.
    """
    template_path = TEMPLATE_DIR / "analysis-prompt.md"
    template = template_path.read_text(encoding="utf-8")

    channels_block = "\n\n".join(channel_transcripts)

    prompt = template.replace("{{date}}", date_str)
    prompt = prompt.replace("{{channels}}", channels_block)
    return prompt


def analyze_via_kimi(prompt: str, moonshot_key: str) -> str:
    """
    Call Moonshot AI API using OpenAI SDK with streaming.

    Uses thinking mode (reasoning enabled) with HTTP/2 for VPN resilience.
    Same transport config as resume_screener_kimi.py.
    """
    transport = httpx.HTTPTransport(
        retries=3,
        http2=True,
    )

    http_client = httpx.Client(
        timeout=600.0,
        transport=transport,
        trust_env=False,
    )

    client = OpenAI(
        api_key=moonshot_key,
        base_url="https://api.moonshot.ai/v1",
        http_client=http_client,
    )

    stream = client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are an operations manager reviewing EP Slack channels. Respond with ONLY valid JSON, no markdown or extra text.",
            },
            {"role": "user", "content": prompt},
        ],
        stream=True,
    )

    print("  [Thinking", end="", flush=True)
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
    """Parse JSON from Kimi's response, handling potential extra text."""
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
