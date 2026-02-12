# Markdown to Google Slides

Converts `.md` slide layout files into styled Google Slides presentations. Design (fonts, colors, backgrounds, logos) lives in a Google Slides **template deck** — editable via the Slides UI, no code changes needed.

## Quick Start

```bash
# Validate markdown structure
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --validate

# Dry run (parse only, no API calls)
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --dry-run

# Generate presentation
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md

# Override title
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --title "Custom Title"
```

## Markdown Format

YAML frontmatter + `---` slide delimiters:

```markdown
---
title: Quarterly Business Review
subtitle: Q1 2026 Results
date: 2026-04-15
---

# Quarterly Business Review
Q1 2026 Results
<!-- layout: title -->
<!-- notes: Welcome everyone. -->

---

# Revenue Summary
<!-- layout: section -->

---

# Q1 Highlights
- Revenue up 23% YoY
- Enterprise grew 31%
- Churn reduced to 4.2%
<!-- notes: Emphasize enterprise growth. -->

---

# Revenue by Segment

::: left
## Build
- Enterprise features
- API v2 launch

::: right
## Optimize
- Reduce onboarding time
- Automate billing
<!-- layout: two_column -->
```

### Rules

| Element | Syntax | Notes |
|---------|--------|-------|
| Slide delimiter | `---` on its own line | First `---` closes frontmatter |
| Title | `# H1` | First H1 per slide = slide title |
| Body bullets | `- item` or `* item` | Rendered as bullet list in body placeholder |
| Sub-heading | `## H2` | Treated as body text |
| Layout hint | `<!-- layout: name -->` | `title`, `section`, `content`, `two_column`, `blank` |
| Speaker notes | `<!-- notes: text -->` | Inserted into slide notes |
| Two-column | `::: left` / `::: right` | Splits body into left/right columns |
| Bold | `**text**` | Applied via Slides API text styling |
| Italic | `*text*` | Applied via Slides API text styling |

### Layout Auto-Inference

When no `<!-- layout: -->` hint is given:
- First slide → `title`
- H1 only (no body) → `section`
- H1 + body → `content`
- No title, no body → `blank`

## Template Deck Setup

Create a Google Slides presentation with these 5 layouts in the Slide Master:

| Layout (Slides UI name) | Placeholders | Maps to `layout:` |
|---|---|---|
| Title Slide | CENTERED_TITLE + SUBTITLE | `title` |
| Section Header | TITLE | `section` |
| Title and Body | TITLE + BODY | `content` |
| Two Column | TITLE + BODY + BODY | `two_column` |
| Blank | (none) | `blank` |

**To update design:** Open template deck → Slide > Edit master → change fonts/colors/backgrounds/logos → save. Next generation picks up changes automatically.

After creating the template, paste its ID into `templates/slide-config.json`.

## Configuration

`templates/slide-config.json`:
```json
{
  "template_presentation_id": "<PASTE_TEMPLATE_ID_HERE>",
  "layout_mapping": {
    "title": "Title Slide",
    "section": "Section Header",
    "content": "Title and Body",
    "two_column": "Two Column",
    "blank": "Blank"
  },
  "default_layout": "content"
}
```

The `layout_mapping` keys are the logical names used in `<!-- layout: -->` hints. Values are the `displayName` of layouts in the template's Slide Master. Adjust values if your template uses different layout names.

## Prerequisites

1. **Google Slides API** and **Google Drive API** enabled in Google Cloud Console (same project as Gmail)
2. `credentials.json` at project root (same OAuth2 client as Gmail)
3. Template deck created in Google Slides with the 5 layouts above
4. Template ID pasted into `slide-config.json`

First run opens a browser for OAuth consent. Token saved to `local-data/slides_token.json`.

## Architecture

```
.claude/skills/md-to-slides/
├── SKILL.md
├── libraries/
│   ├── slides_auth.py       # OAuth2 for Slides + Drive API
│   ├── md_parser.py         # Parse .md → structured slide data
│   └── slides_builder.py    # Clone template, populate via API
├── templates/
│   └── slide-config.json    # Template deck ID + layout mapping
└── workflows/
    └── generate_slides.py   # CLI entry point
```

- **md_parser.py** — Pure Python, no API calls. Parses frontmatter, slide delimiters, layout hints, speaker notes, two-column content, inline formatting.
- **slides_auth.py** — OAuth2 module (follows `gmail_auth.py` pattern). Scopes: `presentations` + `drive.file`.
- **slides_builder.py** — Clones template via Drive API, maps layouts, creates slides, populates placeholders via Slides API.
- **generate_slides.py** — CLI with `--input`, `--title`, `--dry-run`, `--validate`. Saves receipt JSON to `local-data/slides/`.

## Output

- Generated presentation URL printed to stdout
- Receipt JSON saved to `local-data/slides/{date}_{slug}.json`
