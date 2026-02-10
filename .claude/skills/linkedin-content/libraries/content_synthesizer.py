"""
Content Synthesizer Library

Uses Kimi (Moonshot AI) to generate LinkedIn post drafts from user briefs,
research findings, and Ally's content strategy.

Same HTTP/2 transport and streaming patterns as web_researcher.py.
"""

import json
from pathlib import Path

import httpx
from openai import OpenAI

MOONSHOT_MODEL = "kimi-k2.5"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DRAFT_DIR = PROJECT_ROOT / "local-data" / "linkedin" / "drafts"


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


def load_templates() -> dict:
    """Load all template files needed for draft generation."""
    strategy_path = TEMPLATE_DIR / "content-strategy.md"
    system_prompt_path = TEMPLATE_DIR / "post-system-prompt.md"
    pillar_config_path = TEMPLATE_DIR / "pillar-config.json"

    return {
        "strategy": strategy_path.read_text(encoding="utf-8"),
        "system_prompt": system_prompt_path.read_text(encoding="utf-8"),
        "pillar_config": json.loads(pillar_config_path.read_text(encoding="utf-8")),
    }


def generate_draft(
    brief: str,
    pillar: str | None,
    research: dict | None,
    moonshot_key: str,
) -> dict:
    """
    Generate a LinkedIn post draft using Kimi.

    Uses thinking mode (streaming) with NO web search.
    Combines brief, research, strategy, and pillar context.
    """
    templates = load_templates()

    # Build pillar context
    pillar_context = ""
    if pillar and pillar in templates["pillar_config"]["pillars"]:
        p = templates["pillar_config"]["pillars"][pillar]
        pillar_context = f"\n## Content Pillar: {p['name']}\n{p['description']}\n"

    # Build research context
    research_context = ""
    if research:
        synthesis = research.get("synthesis", "")
        sources = research.get("sources", [])
        if synthesis:
            research_context = f"\n## Research Findings\n{synthesis}\n"
        if sources:
            research_context += "\n### Key Sources\n"
            for s in sources:
                insight = s.get("key_insight", "")
                title = s.get("title", "Untitled")
                research_context += f"- **{title}**: {insight}\n"

    # Compose the user message
    user_content = (
        f"## Brief\n{brief}\n"
        f"{pillar_context}"
        f"{research_context}\n"
        f"## Content Strategy Context\n{templates['strategy']}\n\n"
        "Write the LinkedIn post now."
    )

    client = _build_kimi_client(moonshot_key)

    stream = client.chat.completions.create(
        model=MOONSHOT_MODEL,
        messages=[
            {"role": "system", "content": templates["system_prompt"]},
            {"role": "user", "content": user_content},
        ],
        stream=True,
    )

    print("  [Drafting", end="", flush=True)
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

    post_text = "".join(content_parts).strip()

    # Collect source URLs
    source_urls = []
    if research:
        for s in research.get("sources", []):
            url = s.get("url", "")
            if url:
                source_urls.append(url)

    return {
        "post_text": post_text,
        "pillar": pillar,
        "brief": brief,
        "sources": source_urls,
    }


def save_draft(draft_data: dict, date_str: str, slug: str) -> Path:
    """Save draft as markdown with YAML frontmatter to local-data."""
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)

    sources_yaml = ""
    if draft_data.get("sources"):
        sources_yaml = "sources:\n"
        for url in draft_data["sources"]:
            sources_yaml += f"  - {url}\n"

    research_notes = ""
    if draft_data.get("research_synthesis"):
        research_notes = (
            "\n---\n## Research Notes\n"
            f"{draft_data['research_synthesis']}\n"
        )

    content = (
        f"---\n"
        f"date: {date_str}\n"
        f"pillar: {draft_data.get('pillar', 'auto')}\n"
        f"brief: \"{draft_data['brief']}\"\n"
        f"status: draft\n"
        f"{sources_yaml}"
        f"---\n\n"
        f"{draft_data['post_text']}"
        f"{research_notes}"
    )

    filepath = DRAFT_DIR / f"{date_str}_{slug}.md"
    filepath.write_text(content, encoding="utf-8")
    return filepath
