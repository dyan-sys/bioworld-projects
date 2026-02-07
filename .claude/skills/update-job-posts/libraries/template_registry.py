"""
Template registry for job post content.

Maps (job_code, channel) pairs to template files and converts
markdown templates to Notion block arrays.
"""

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

TEMPLATE_REGISTRY = {
    ("ep", "olj"):       {"file": "EP-OLJ.md"},
    ("ep", "jobstreet"): {"file": "EP-Jobstreet.md"},
    ("ep", "facebook"):  {"file": "EP-Facebook.md"},
    ("ep", "internal"):  {"file": "EP-Internal.md"},
    ("epp", "olj"):       {"file": "EPP-OLJ.md"},
    ("epp", "jobstreet"): {"file": "EPP-Jobstreet.md"},
    ("epp", "facebook"):  {"file": "EPP-Facebook.md"},
    ("epp", "internal"):  {"file": "EPP-Internal.md"},
}

DEFAULT_TEMPLATE = "_default.md"


def markdown_to_notion_blocks(md_text: str) -> list[dict]:
    """
    Convert simple markdown to Notion block objects.

    Supports: headings (h1-h3), bullet lists, dividers (---), paragraphs.
    """
    blocks = []
    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # Divider
        if stripped in ("---", "***", "___"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # Headings
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            heading_type = f"heading_{level}"
            blocks.append({
                "object": "block",
                "type": heading_type,
                heading_type: {
                    "rich_text": [{"type": "text", "text": {"content": text}}],
                },
            })
            i += 1
            continue

        # Bullet list item
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            text = bullet_match.group(1)
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": text}}],
                },
            })
            i += 1
            continue

        # Paragraph (default)
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": stripped}}],
            },
        })
        i += 1

    return blocks


def get_template(job_code: str, channel: str) -> dict:
    """
    Load a template by (job_code, channel) and convert to Notion blocks.

    Args:
        job_code: Job type code (e.g., "EP", "EPP") — case-insensitive
        channel: Post channel name (e.g., "OLJ", "Jobstreet") — case-insensitive

    Returns:
        dict with "body_blocks" (list of Notion block objects) and "source" (filename)
    """
    key = (job_code.lower(), channel.lower())
    entry = TEMPLATE_REGISTRY.get(key)

    if entry:
        filename = entry["file"]
    else:
        print(f"  [WARNING] No template for ({job_code}, {channel}), using default")
        filename = DEFAULT_TEMPLATE

    filepath = TEMPLATES_DIR / filename
    if not filepath.exists():
        print(f"  [WARNING] Template file not found: {filename}, using default")
        filepath = TEMPLATES_DIR / DEFAULT_TEMPLATE

    if not filepath.exists():
        print(f"  [ERROR] Default template not found: {DEFAULT_TEMPLATE}")
        return {"body_blocks": [], "source": "none"}

    md_text = filepath.read_text(encoding="utf-8")
    blocks = markdown_to_notion_blocks(md_text)

    return {"body_blocks": blocks, "source": filename}
