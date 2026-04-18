"""
Markdown Slide Parser

Parses .md slide files into structured slide data for Google Slides generation.
Pure Python — no API calls, fully testable offline.

Format:
- YAML-like frontmatter between opening and first `---`
- `---` separates slides
- `# H1` = slide title
- `<!-- layout: title|section|content|two_column|blank -->` = layout hint
- `<!-- notes: ... -->` = speaker notes
- `::: left` / `::: right` = two-column content
- Inline **bold** and *italic* tracked as offset ranges
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TextRun:
    """A segment of text with optional formatting."""

    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class SlideData:
    """Parsed data for a single slide."""

    title: str = ""
    body: str = ""
    body_items: list[str] = field(default_factory=list)
    body_item_types: list[str] = field(default_factory=list)  # "bullet" or "text"
    notes: str = ""
    layout: str = ""  # explicit layout hint; empty = auto-infer
    left_body: list[str] = field(default_factory=list)
    left_body_types: list[str] = field(default_factory=list)
    right_body: list[str] = field(default_factory=list)
    right_body_types: list[str] = field(default_factory=list)
    table: list[list[str]] | None = None
    title_runs: list[TextRun] = field(default_factory=list)
    body_runs: list[TextRun] = field(default_factory=list)


@dataclass
class Presentation:
    """Full parsed presentation."""

    metadata: dict[str, str] = field(default_factory=dict)
    slides: list[SlideData] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract YAML-like frontmatter. Returns (metadata, remaining_text)."""
    text = text.lstrip()
    if not text.startswith("---"):
        return {}, text

    # Find closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_block = text[3:end].strip()
    remainder = text[end + 4:]  # skip past the closing ---

    metadata = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon = line.find(":")
        if colon == -1:
            continue
        key = line[:colon].strip()
        val = line[colon + 1:].strip().strip('"').strip("'")
        metadata[key] = val

    return metadata, remainder


# ---------------------------------------------------------------------------
# Comment directives
# ---------------------------------------------------------------------------

_LAYOUT_RE = re.compile(r"<!--\s*layout:\s*(\w+)\s*-->", re.IGNORECASE)
_NOTES_RE = re.compile(r"<!--\s*notes:\s*(.*?)\s*-->", re.IGNORECASE | re.DOTALL)


def _extract_directives(lines: list[str]) -> tuple[str, str, list[str]]:
    """Extract layout and notes directives from slide lines.

    Returns (layout, notes, remaining_lines).
    """
    layout = ""
    notes = ""
    remaining = []

    for line in lines:
        m_layout = _LAYOUT_RE.search(line)
        if m_layout:
            layout = m_layout.group(1).lower()
            continue
        m_notes = _NOTES_RE.search(line)
        if m_notes:
            notes = m_notes.group(1).strip()
            continue
        remaining.append(line)

    return layout, notes, remaining


# ---------------------------------------------------------------------------
# Inline formatting
# ---------------------------------------------------------------------------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def strip_inline(text: str) -> str:
    """Strip **bold** and *italic* markers, returning plain text."""
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    return text


def parse_inline(text: str) -> list[TextRun]:
    """Parse inline **bold** and *italic* into TextRun segments."""
    runs: list[TextRun] = []
    pos = 0

    # Merge bold and italic patterns with positions
    markers: list[tuple[int, int, str, bool, bool]] = []
    for m in _BOLD_RE.finditer(text):
        markers.append((m.start(), m.end(), m.group(1), True, False))
    for m in _ITALIC_RE.finditer(text):
        # Skip if this overlaps with a bold marker
        overlaps = any(
            b_start <= m.start() < b_end or b_start < m.end() <= b_end
            for b_start, b_end, _, _, _ in markers
        )
        if not overlaps:
            markers.append((m.start(), m.end(), m.group(1), False, True))

    markers.sort(key=lambda x: x[0])

    for start, end, inner, is_bold, is_italic in markers:
        if start > pos:
            runs.append(TextRun(text=text[pos:start]))
        runs.append(TextRun(text=inner, bold=is_bold, italic=is_italic))
        pos = end

    if pos < len(text):
        runs.append(TextRun(text=text[pos:]))

    return runs if runs else [TextRun(text=text)]


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

def _parse_table(lines: list[str]) -> list[list[str]] | None:
    """Parse a simple markdown table into a 2D list."""
    table_lines = [l for l in lines if l.strip().startswith("|")]
    if len(table_lines) < 2:
        return None

    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # Skip separator rows (---|---)
        if all(re.match(r"^[-:]+$", c) for c in cells):
            continue
        rows.append(cells)

    return rows if len(rows) >= 2 else None


# ---------------------------------------------------------------------------
# Two-column parsing
# ---------------------------------------------------------------------------

def _parse_two_column(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split lines at ::: left / ::: right markers.

    Returns (left_items, right_items, non_column_lines).
    """
    left: list[str] = []
    right: list[str] = []
    other: list[str] = []
    current: list[str] | None = None

    for line in lines:
        stripped = line.strip().lower()
        if stripped == "::: left":
            current = left
            continue
        elif stripped == "::: right":
            current = right
            continue

        if current is not None:
            current.append(line)
        else:
            other.append(line)

    return left, right, other


# ---------------------------------------------------------------------------
# Single slide parsing
# ---------------------------------------------------------------------------

def _strip_bullet(line: str) -> str:
    """Strip leading bullet marker (-, *, numbered) from a line."""
    stripped = line.strip()
    # Unordered: - or *
    if stripped.startswith(("- ", "* ")):
        return stripped[2:]
    # Ordered: 1. 2. etc.
    m = re.match(r"^\d+\.\s+", stripped)
    if m:
        return stripped[m.end():]
    return stripped


def _parse_single_slide(lines: list[str], index: int) -> SlideData:
    """Parse a block of lines into a SlideData."""
    layout, notes, lines = _extract_directives(lines)

    # Check for two-column content
    has_columns = any(l.strip().lower() in ("::: left", "::: right") for l in lines)

    slide = SlideData(layout=layout, notes=notes)

    if has_columns:
        left_lines, right_lines, other_lines = _parse_two_column(lines)

        # Title from other_lines (first H1)
        for line in other_lines:
            if line.strip().startswith("# "):
                slide.title = line.strip()[2:].strip()
                slide.title_runs = parse_inline(slide.title)
                break

        # Parse left/right items
        for line in left_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("## "):
                if stripped.startswith("## "):
                    slide.left_body.append(stripped[3:].strip())
                    slide.left_body_types.append("text")
                continue
            if stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", stripped):
                slide.left_body.append(_strip_bullet(line))
                slide.left_body_types.append("bullet")
            elif stripped:
                slide.left_body.append(stripped)
                slide.left_body_types.append("text")

        for line in right_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("## "):
                if stripped.startswith("## "):
                    slide.right_body.append(stripped[3:].strip())
                    slide.right_body_types.append("text")
                continue
            if stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", stripped):
                slide.right_body.append(_strip_bullet(line))
                slide.right_body_types.append("bullet")
            elif stripped:
                slide.right_body.append(stripped)
                slide.right_body_types.append("text")

        if not slide.layout:
            slide.layout = "two_column"
        return slide

    # Non-column slide
    title_found = False
    body_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not title_found:
            slide.title = stripped[2:].strip()
            slide.title_runs = parse_inline(slide.title)
            title_found = True
        else:
            body_lines.append(line)

    # Check for table
    table = _parse_table(body_lines)
    if table:
        slide.table = table
        # Remove table lines from body
        body_lines = [l for l in body_lines if not l.strip().startswith("|")]

    # Parse body items (bullets and plain text)
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            # Sub-heading — treat as a body item
            slide.body_items.append(stripped[3:].strip())
            slide.body_item_types.append("text")
        elif stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", stripped):
            slide.body_items.append(_strip_bullet(line))
            slide.body_item_types.append("bullet")
        else:
            slide.body_items.append(stripped)
            slide.body_item_types.append("text")

    # Build body text (joined items, with inline markers stripped)
    raw_body = "\n".join(slide.body_items)
    slide.body = strip_inline(raw_body)
    slide.body_runs = parse_inline(raw_body)

    # Auto-infer layout if not set
    if not slide.layout:
        slide.layout = _infer_layout(slide, index)

    return slide


def _infer_layout(slide: SlideData, index: int) -> str:
    """Infer layout from slide content when no explicit hint given."""
    if index == 0:
        return "title"
    if slide.title and not slide.body_items and not slide.table:
        return "section"
    if slide.title and (slide.body_items or slide.table):
        return "content"
    if not slide.title and not slide.body_items:
        return "blank"
    return "content"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_markdown_file(path: str | Path) -> Presentation:
    """Parse a markdown slide file into a Presentation.

    Args:
        path: Path to the .md file.

    Returns:
        Presentation with metadata and list of SlideData.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_markdown(text)


def parse_markdown(text: str) -> Presentation:
    """Parse markdown text into a Presentation.

    Args:
        text: Raw markdown string.

    Returns:
        Presentation with metadata and list of SlideData.
    """
    metadata, body = _parse_frontmatter(text)

    # Split on --- slide delimiters (must be on its own line)
    slide_blocks = re.split(r"\n---\s*\n", body)

    slides: list[SlideData] = []
    for i, block in enumerate(slide_blocks):
        lines = block.splitlines()
        # Skip empty blocks
        if not any(l.strip() for l in lines):
            continue
        slides.append(_parse_single_slide(lines, i))

    return Presentation(metadata=metadata, slides=slides)
