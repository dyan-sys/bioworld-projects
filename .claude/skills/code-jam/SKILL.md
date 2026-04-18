---
name: code-jam
description: Trigger when user mentions running a Code Jam, generating Code Jam slides, setting up a Code Jam session, or creating the Code Jam Notion tracker
---

# Code Jam Skill

Generates a Google Slides deck for a Claude Code Jam session and optionally creates/updates the Notion project tracker.

## How to Run

```bash
# Generate slides for Jam 2 with specific EA names
python3 .claude/skills/code-jam/workflows/run_code_jam.py \
  --jam 2 \
  --eas "Ana,Beth,Carol,Dana,Eve"

# Jam 1 with defaults (EA 1–9 placeholders)
python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 1

# Generate slides + create Notion tracker (first time only)
python3 .claude/skills/code-jam/workflows/run_code_jam.py \
  --jam 1 \
  --eas "Ana,Beth,Carol,Dana,Eve" \
  --setup-tracker \
  --parent-id <notion_page_id>

# Update an existing deck in-place (preserves URL)
python3 .claude/skills/code-jam/workflows/run_code_jam.py \
  --jam 2 \
  --eas "Ana,Beth,Carol" \
  --update <slides_url_or_id>

# Dry run: generate markdown only, no API calls
python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 1 --dry-run

# Create Notion tracker only (no slides)
python3 .claude/skills/code-jam/workflows/setup_tracker.py \
  --parent-id <notion_page_id> \
  --jam "Jam 1" \
  --eas "Ana,Beth,Carol,Dana,Eve"
```

## Arguments

| Argument | Default | Description |
|---|---|---|
| `--jam` | `1` | Jam session number |
| `--eas` | EA 1–9 | Comma-separated EA names |
| `--theme` | `dark` | Slide theme (`dark` or `light`) |
| `--update` | — | Update existing deck URL/ID in-place |
| `--dry-run` | — | Generate markdown only, skip API calls |
| `--setup-tracker` | — | Also create Notion tracker database |
| `--parent-id` | — | Notion page ID for tracker (required with `--setup-tracker`) |

## Slide Structure

Each jam deck contains:
1. Title slide
2. Agenda
3. Opening / Ground Rules
4. Jam Vision — Why We're Doing This
5. How Today Works
6. Founder Segment (Ivan)
7. The Future of EAs with AI (two-column)
8. EA Lightning Shares — Sharing Template
9. One slide per presenting EA (dynamic, based on `--eas`)
10. Synthesis — Top Blockers (live-fill)
11. Close — What Counts as Progress
12. See You at Jam N+1

## Notion Tracker Schema

The `setup_tracker.py` script creates a **Claude Code Jam — Project Tracker** database with:

| Field | Type | Options |
|---|---|---|
| EA Name | Title | — |
| Project / Idea | Text | — |
| Jam Session | Select | Jam 1–5 |
| Status | Select | Not Started / Trying / Stuck / Got Help / Done ✅ |
| What They Tried | Text | — |
| Where They're Stuck | Text | — |
| Next Step | Text | — |
| Notes | Text | — |

## Requirements

- Google Slides API + Drive API enabled in Google Cloud Console (project 7483221578)
- `credentials.json` at project root (or `GOOGLE_CREDENTIALS_PATH` env var)
- `NOTION_KEY` in `.env` (required for tracker setup only)
- Dependencies: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `requests`, `python-dotenv`

## Files

```
.claude/skills/code-jam/
├── SKILL.md
├── templates/
│   └── jam-deck.md.template   # Parameterized slide template
└── workflows/
    ├── run_code_jam.py         # Main entry point (slides + optional tracker)
    └── setup_tracker.py        # Notion tracker setup only
```
