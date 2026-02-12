---
name: cs-digest
description: Trigger when user mentions generating a CS digest, Customer Success report, or summarizing CS documents
---

# CS Digest Skill

Generates structured Customer Success digest reports from mixed text files (notes, emails, reports) via Kimi AI. On-demand only — no scheduling.

## How to Run

```bash
# Default (reads from local-data/cs-digest/input/, today's date)
python3.11 .claude/skills/cs-digest/workflows/generate_digest.py

# Specific date
python3.11 .claude/skills/cs-digest/workflows/generate_digest.py --date 2026-02-12

# Custom input folder
python3.11 .claude/skills/cs-digest/workflows/generate_digest.py --folder /path/to/files

# Dry run (preview prompt, no Kimi call)
python3.11 .claude/skills/cs-digest/workflows/generate_digest.py --dry-run
```

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--date` | Today (SGT) | Report date in YYYY-MM-DD format |
| `--folder` | `local-data/cs-digest/input/` | Path to folder containing input `.txt`/`.md` files |
| `--dry-run` | off | Preview the built prompt without calling Kimi |

## Workflow

1. **Load environment** — reads `MOONSHOT_API_KEY` from `.env`
2. **Read input files** — collects all `.txt` and `.md` files from the input folder
3. **Analyze via Kimi** — builds prompt from template + documents, streams to Kimi AI
4. **Save + display** — writes digest markdown and JSON receipt to reports dir

## Output

- `local-data/cs-digest/reports/{date}_digest.md` — the generated digest report
- `local-data/cs-digest/reports/{date}_receipt.json` — metadata + raw API response

## Digest Sections

| Section | Content |
|---------|---------|
| Executive Summary | 2–4 sentence overview of key takeaways |
| Key Updates | Notable changes, developments, grouped by client/topic |
| Action Items | Tasks, follow-ups, next steps with owners and deadlines |
| Client Health Signals | Positive/negative satisfaction, risk, or opportunity signals |
| Notes | Additional observations and context |

## Custom Output Format

To have Kimi follow a specific output style, save a sample as:

```
.claude/skills/cs-digest/templates/sample-output.md
```

It will be auto-injected into the prompt — no code change needed.

## Requirements

- Python 3.11+
- Environment variables: `MOONSHOT_API_KEY`
- Dependencies: `openai`, `httpx`, `h2`, `python-dotenv`
