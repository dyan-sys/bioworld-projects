# Background Check

Automated online background screening for candidates using Kimi web search. Checks LinkedIn consistency, news/legal records, social media, and professional contributions before candidates advance in the pipeline.

## Trigger

Run on-demand when candidates need background screening before advancing (typically after 2R Proceed). Not scheduled — background checks are sensitive and should be run deliberately.

## Usage

```bash
# Single candidate (dry run — receipt only, no Notion update)
python3.11 .claude/skills/background-check/workflows/background_check.py \
  --page-id <notion-page-uuid> --dry-run

# Single candidate (full — updates Notion)
python3.11 .claude/skills/background-check/workflows/background_check.py \
  --page-id <notion-page-uuid>

# Batch mode (default: 2R=Proceed, BG Check empty)
python3.11 .claude/skills/background-check/workflows/background_check.py \
  --limit 5

# Custom filter (e.g., check 1R candidates instead)
python3.11 .claude/skills/background-check/workflows/background_check.py \
  --status-filter "1R:Proceed" --limit 3
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--page-id` | No | Single candidate mode — Notion page UUID |
| `--limit` | No | Max candidates in batch mode (default: 10) |
| `--batch-size` | No | Candidates per batch before pausing (default: 3) |
| `--dry-run` | No | Save receipts only, skip Notion updates |
| `--status-filter` | No | Override default filter. Format: `STAGE:STATUS` (default: `2R:Proceed`) |

## How It Works

1. **Load candidate** — Name + location from Notion, resume text from `local-data/talent/resume_raw_txt/` (falls back to PDF extraction if not cached)
2. **Kimi Call 1** (no web search) — Generate 4-6 targeted search queries from candidate name, location, and employers
3. **Kimi Call 2** (with `$web_search`) — Execute searches and analyze findings across 4 categories
4. **Save receipt** → `local-data/talent/background_checks/{Name}_{timestamp}.json`
5. **Update Notion** → `BG Check` (select) + `BG Check Notes` (rich_text)

## Search Categories

| Category | What It Checks | Possible Ratings |
|----------|---------------|-----------------|
| LinkedIn Consistency | Resume vs LinkedIn match (titles, companies, dates) | Green / Yellow / Red |
| News / Legal | Lawsuits, fraud, criminal records, negative press | Green / Yellow / Red |
| Social Media | Inappropriate public content on social platforms | Green / Yellow / Red |
| Professional Contributions | Blogs, open source, talks (positive signals) | Green / Yellow only |

## Overall Recommendation

| Value | Meaning |
|-------|---------|
| `Clear` | All categories Green, confidence Medium or High |
| `Review Recommended` | Any category Yellow, or Low confidence (common name) |
| `Flag` | Any category Red |

## Common Name Handling

- Search queries include location and employer names for disambiguation
- Kimi is instructed to only report findings for the specific candidate
- Low-confidence results automatically escalate to "Review Recommended"

## Notion Properties Required

- **`BG Check`** — Select: `Clear`, `Review Recommended`, `Flag`
- **`BG Check Notes`** — Rich Text (max 2000 chars)

## Output

- Receipts: `local-data/talent/background_checks/{Name}_{timestamp}.json`

## Requirements

- `NOTION_KEY`, `NOTION_DB_ID`, `MOONSHOT_API_KEY` environment variables
- Python 3.11+ with `openai`, `httpx`, `h2`, `requests`, `python-dotenv`
- Notion database must have `BG Check` (select) and `BG Check Notes` (rich_text) properties
