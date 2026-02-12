"""
Kimi Analyzer Library — CS Digest

Sends concatenated CS documents to Moonshot AI (Kimi) for analysis.
Adapted from flag-ep-issues/libraries/kimi_analyzer.py — same HTTP/2
transport, streaming, and thinking-dot patterns.

Output is markdown (not JSON) since the digest is human-consumed.
"""

from pathlib import Path

import httpx
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def build_prompt(date_str: str, documents_block: str) -> str:
    """
    Load analysis-prompt.md and inject date, documents, and optional output format.

    If templates/sample-output.md exists, its content is injected into the
    {{output_format}} placeholder so Kimi follows the user's preferred structure.
    """
    template_path = TEMPLATE_DIR / "analysis-prompt.md"
    template = template_path.read_text(encoding="utf-8")

    # Check for optional sample output format
    sample_output_path = TEMPLATE_DIR / "sample-output.md"
    if sample_output_path.exists():
        sample = sample_output_path.read_text(encoding="utf-8").strip()
        output_format = (
            "\n## Reference Output Format\n\n"
            "The following is a sample of the desired output style and structure. "
            "Follow this format closely:\n\n" + sample
        )
    else:
        output_format = ""

    prompt = template.replace("{{date}}", date_str)
    prompt = prompt.replace("{{documents}}", documents_block)
    prompt = prompt.replace("{{output_format}}", output_format)
    return prompt


def analyze_via_kimi(prompt: str, moonshot_key: str) -> str:
    """
    Call Moonshot AI API using OpenAI SDK with streaming.

    Uses thinking mode (reasoning enabled) with HTTP/2 for VPN resilience.
    Returns raw markdown text.
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
                "content": (
                    "You are a Customer Success analyst. "
                    "Produce a clear, structured markdown digest report."
                ),
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
