"""
Draft Generator Library for Bioworld LinkedIn Automation.

Uses Groq API (Llama 3.3 70B) to generate LinkedIn post drafts from article
summaries, matching Bioworld Ventures' posting style.
"""

import os
from pathlib import Path

import requests

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def load_templates() -> dict:
    """Load all template files for draft generation."""
    strategy_path = TEMPLATE_DIR / "content-strategy.md"
    system_prompt_path = TEMPLATE_DIR / "post-system-prompt.md"

    return {
        "strategy": strategy_path.read_text(encoding="utf-8"),
        "system_prompt": system_prompt_path.read_text(encoding="utf-8"),
    }


def generate_draft(article: dict, _unused_key: str = "") -> str:
    """
    Generate a LinkedIn post draft for a given article using Groq API.

    article dict keys:
        title, summary, source_url, company, source_type

    Returns the post text as a string.
    """
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        print("  [ERROR: GROQ_API_KEY not set]")
        return ""

    templates = load_templates()

    company = article.get("company", "")
    is_portfolio = company and company != "Industry News"

    if is_portfolio:
        context_line = (
            f"This is about our portfolio company {company}. "
            f"Frame the post as a portfolio highlight."
        )
    else:
        context_line = (
            "This is a broader industry news item. "
            "Frame it with Bioworld Ventures' perspective on the trend."
        )

    prompt = (
        f"## Article to Post About\n"
        f"**Title:** {article.get('title', '')}\n"
        f"**Company:** {company}\n"
        f"**Type:** {article.get('source_type', 'News')}\n"
        f"**Summary:** {article.get('summary', '')}\n"
        f"**Source URL:** {article.get('source_url', '')}\n\n"
        f"## Instructions\n"
        f"{context_line}\n\n"
        f"## Content Strategy\n{templates['strategy']}\n\n"
        f"Write the LinkedIn post now. Output ONLY the post text, nothing else. "
        f"No preamble, no explanation, just the ready-to-publish post."
    )

    # Add regeneration context if provided
    regen = article.get("regeneration_context", "")
    if regen:
        prompt += f"\n\n## Regeneration Context\n{regen}"

    print(f"  [Drafting: {article.get('title', '')[:50]}", end="", flush=True)

    try:
        resp = requests.post(
            GROQ_ENDPOINT,
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": templates["system_prompt"]},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 1024,
                "temperature": 0.7,
            },
            timeout=60,
        )
        resp.raise_for_status()
        print("]")
        return resp.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        print(f" ERROR: {e}]")
        return ""
