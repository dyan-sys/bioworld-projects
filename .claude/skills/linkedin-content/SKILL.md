# LinkedIn Content Engine

Generate LinkedIn post drafts by combining user creative direction with web research and Ally's voice.

## Trigger

Trigger when user mentions LinkedIn content, generating posts, content drafts, or LinkedIn strategy.

## Usage

```bash
# Full pipeline: research + draft
python3.11 .claude/skills/linkedin-content/workflows/generate_content.py \
  --brief "Delegation fails when execs don't trust the process" \
  --pillar delegation

# Dry run (research only, no draft)
python3.11 .claude/skills/linkedin-content/workflows/generate_content.py \
  --brief "Why most delegation advice is backwards" \
  --pillar delegation \
  --dry-run

# Skip research (generate from brief + strategy only)
python3.11 .claude/skills/linkedin-content/workflows/generate_content.py \
  --brief "At Ally we believe ownership means..." \
  --skip-research
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--brief` | Yes | Topic idea, angle, or observation (free text) |
| `--pillar` | No | Content pillar (delegation, focus, operations, ai-tools, life-at-ally, time-management, achievements). Auto-detected from brief if omitted. |
| `--dry-run` | No | Preview research without generating draft |
| `--skip-research` | No | Skip web search, generate from brief + strategy only |

## Pipeline

1. **Steering** — User provides brief and optional pillar
2. **Research** — Kimi + `$web_search` finds recent ideas and data points
3. **Synthesis** — Kimi drafts LinkedIn post using strategy, research, and voice guidelines

## Output

- Research: `local-data/linkedin/research/{date}_{slug}.json`
- Drafts: `local-data/linkedin/drafts/{date}_{slug}.md`

## Requirements

- `MOONSHOT_API_KEY` environment variable
- Python 3.11+ with `openai`, `httpx`, `h2`, `python-dotenv`

## Content Pillars

| Key | Name |
|-----|------|
| delegation | Delegation & Executive Leverage |
| focus | Focus & Priority Management |
| operations | How We Operate at Ally |
| ai-tools | Tools, AI, and the Modern EA |
| life-at-ally | Life at Ally |
| time-management | Time Management & Prioritization |
| achievements | Achievements & Outcomes |
