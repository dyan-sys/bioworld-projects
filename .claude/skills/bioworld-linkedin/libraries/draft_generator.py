"""
Draft Generator Library for Bioworld LinkedIn Automation.

Uses Claude CLI to generate LinkedIn post drafts from article
summaries, matching Bioworld Ventures' posting style.
"""

import subprocess
from pathlib import Path

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
    Generate a LinkedIn post draft for a given article using Claude CLI.

    article dict keys:
        title, summary, source_url, company, source_type

    Returns the post text as a string.
    """
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
        f"{templates['system_prompt']}\n\n"
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

    print(f"  [Drafting: {article.get('title', '')[:50]}", end="", flush=True)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--print"],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            print(f" ERROR]")
            return ""

        print("]")
        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        print(" TIMEOUT]")
        return ""
    except FileNotFoundError:
        print(" CLI NOT FOUND]")
        return ""
