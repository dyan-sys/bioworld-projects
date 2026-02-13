# Markdown to Google Slides

Converts `.md` slide layout files into styled Google Slides presentations. Design (fonts, colors, backgrounds, logos) lives in a Google Slides **template deck** — editable via the Slides UI, no code changes needed.

## Quick Start

```bash
# Generate presentation (dark theme, default)
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md

# Choose theme
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --theme light

# Update an existing deck in-place (preserves URL)
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --update <url_or_id>

# Dry run (parse only, no API calls)
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --dry-run

# Validate markdown structure
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --validate

# Override title
python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --title "Custom Title"
```

## Themes

Two templates available. Default is **dark**.

| Theme | Description |
|-------|-------------|
| `dark` | Dark background, Instrument Serif + DM Sans, light text |
| `light` | Light background, standard Google Slides theme |

Select with `--theme dark` or `--theme light`. Template IDs are stored in `slide-config.json` under `templates`.

## Naming Convention

All generated decks are named `"Title (YYYY-MM-DD)"` for easy versioning in Drive. Output goes to the `MD to Slides` folder in Google Drive.

## Markdown Format

YAML frontmatter + `---` slide delimiters:

```markdown
---
title: Quarterly Business Review
author: Team
---

# Quarterly Business Review
Q1 2026 Results
<!-- notes: Welcome everyone. -->

---

<!-- layout: section -->

# Revenue Summary

---

# Q1 Highlights
- Revenue up 23% YoY
- Enterprise grew 31%
- Churn reduced to 4.2%
<!-- notes: Emphasize enterprise growth. -->

---

<!-- layout: two_column -->

# Revenue by Segment

::: left
- Enterprise features
- API v2 launch

::: right
- Reduce onboarding time
- Automate billing

---

<!-- layout: agenda -->

# Today's Agenda
- 👋 About You
- 💡 Our Approach
- 🔋 Deep Dive
- 📚 Best Practices
- 🔄 Next Steps
```

### Syntax Reference

| Element | Syntax | Notes |
|---------|--------|-------|
| Slide delimiter | `---` on its own line | First `---` closes frontmatter |
| Title | `# H1` | First H1 per slide = slide title |
| Body bullets | `- item` or `* item` | Rendered as bullet list in body placeholder |
| Sub-heading | `## H2` | Treated as body text |
| Layout hint | `<!-- layout: name -->` | See layout types below |
| Speaker notes | `<!-- notes: text -->` | Inserted into slide notes |
| Two-column | `::: left` / `::: right` | Splits body into left/right columns |
| Bold | `**text**` | Applied via Slides API text styling |
| Italic | `*text*` | Applied via Slides API text styling |
| Table | Markdown table syntax | Auto-detected, placed on slide with styled header |

### Layout Types

| Layout | Hint | Placeholders | Use for |
|--------|------|--------------|---------|
| Title Slide | `title` | CENTERED_TITLE + SUBTITLE | Opening slide |
| Section Header | `section` | TITLE | Section dividers |
| Content | `content` | TITLE + BODY | Standard content (default) |
| Two Column | `two_column` | TITLE + BODY + BODY | Side-by-side content |
| Blank | `blank` | (none) | Tables, custom content |
| Agenda | `agenda` | (custom shapes) | Icon boxes for agenda/overview |

### Layout Auto-Inference

When no `<!-- layout: -->` hint is given:
- First slide → `title`
- H1 only (no body) → `section`
- H1 + body → `content`
- No title, no body → `blank`

### Agenda Layout

The `agenda` layout creates rounded boxes with emoji icons and short titles — no bullet lists. Format:

```markdown
<!-- layout: agenda -->
# Slide Title
- 👋 About You
- 💡 Our Approach
- 🔋 Deep Dive
```

Each bullet becomes a box. First emoji character becomes the icon (large, centered above label). Uses theme colors so it adapts to both light and dark templates.

## Style Philosophy

**The template drives the visual identity.** The code only applies structural formatting:
- Bullet points on body text
- Line spacing and paragraph spacing
- Table header bold

It does **not** override fonts, sizes, or colors from the template. This means swapping templates "just works" — no need to re-tune styling per theme.

Optional overrides available in `slide-config.json` under `styles` if needed (font_family, font_size, color as hex, bold).

## Update Mode

To update an existing deck in-place (same URL, no new file):

```bash
python3.11 .../generate_slides.py --input deck.md --update <url_or_id>
```

Accepts a full Google Slides URL or just the presentation ID. Deletes all existing slides and rebuilds from the markdown. Renames the deck with the new date stamp.

## Configuration

`templates/slide-config.json`:
```json
{
  "templates": {
    "dark": "<template_id>",
    "light": "<template_id>"
  },
  "default_theme": "dark",
  "layout_mapping": {
    "title": "Title slide",
    "section": "Section header",
    "content": "Title and body",
    "two_column": "Title and two columns",
    "blank": "Blank",
    "agenda": "Blank"
  },
  "default_layout": "content",
  "drive_folder": "MD to Slides",
  "styles": {
    "body": {
      "line_spacing": 150,
      "space_above": 6,
      "bullet_preset": "BULLET_DISC_CIRCLE_SQUARE"
    },
    "table": {
      "header_bold": true
    }
  }
}
```

The `layout_mapping` values must match the `displayName` of layouts in the template's Slide Master.

## Prerequisites

1. **Google Slides API** and **Google Drive API** enabled in Google Cloud Console
2. `Google-credentials.json` at project root (same OAuth2 client as Gmail)
3. Template decks created in Google Slides with the required layouts
4. Template IDs configured in `slide-config.json`

First run opens a browser for OAuth consent. Token saved to `local-data/slides_token.json`.

## Architecture

```
.claude/skills/md-to-slides/
├── SKILL.md
├── libraries/
│   ├── slides_auth.py       # OAuth2 for Slides + Drive API
│   ├── md_parser.py         # Parse .md → structured slide data
│   └── slides_builder.py    # Clone template, populate + style via API
├── templates/
│   └── slide-config.json    # Template IDs, layout mapping, styles
└── workflows/
    └── generate_slides.py   # CLI entry point
```

## Output

- Generated presentation URL printed to stdout
- Decks saved to `MD to Slides` folder in Google Drive
- Receipt JSON saved to `local-data/slides/{date}_{slug}.json`
- Receipt includes: title, theme, template_id, URL, slide count, mode (create/update)

## Editing Existing Decks via API

When manipulating slides directly through the Google Slides API (outside the markdown→slides pipeline), follow these rules:

### Text replacement destroys formatting

`deleteText` + `insertText` wipes all styles (font, size, bold, color, alignment). After any text replacement on existing slides, **always** re-apply formatting with `updateTextStyle` and `updateParagraphStyle`.

Dark theme font reference for re-application:
- Titles: Instrument Serif
- Body / labels: DM Sans, 14pt
- Emojis: Noto Color Emoji

### Always verify visually

Fetch slide thumbnails via the API after making changes. Formatting issues aren't obvious from text data alone.

```python
thumb = slides_svc.presentations().pages().getThumbnail(
    presentationId=DECK_ID,
    pageObjectId=slide_object_id,
    thumbnailProperties_thumbnailSize='LARGE'
).execute()
```

### Inspect before adding slides

When adding slides to an existing (non-markdown-generated) deck:
1. Fetch available layouts first (`layoutProperties.displayName`) and their placeholder types
2. Check existing slide styling to match fonts, sizes, colors
3. Use `placeholderIdMappings` in `createSlide` to get stable IDs for text insertion

### Reordering shifts indices

`updateSlidesPosition` uses object IDs, but each move shifts all subsequent indices. Do sequential batch updates (one move per `batchUpdate` call), not one big batch with multiple moves.

### Emoji sizing in card layouts

~24pt Noto Color Emoji with 12pt `spaceAbove` on the emoji paragraph works well for rounded-rectangle card layouts. Larger emojis (32pt+) push content into card edges even with `contentAlignment: MIDDLE`.
