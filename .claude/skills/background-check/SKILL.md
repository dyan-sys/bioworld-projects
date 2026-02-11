# Background Check

Automated online background screening for candidates using Google Custom Search + Kimi AI analysis. Checks LinkedIn consistency, news/legal records, social media, and professional contributions before candidates advance in the pipeline.

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
3. **Google Custom Search** — Execute each query against Google's index (same coverage as google.com)
4. **Kimi Call 2** (analysis only) — Analyze Google results across 4 categories, return structured JSON
5. **Save receipt** → `local-data/talent/background_checks/{Name}_{timestamp}.json`
6. **Update Notion** → `BG Check` (select) + `BG Check Notes` (rich_text)

## Search Categories

| Category | What It Checks | Possible Ratings |
|----------|---------------|-----------------|
| LinkedIn Consistency | Resume vs LinkedIn match (titles, companies, dates) | Green / Yellow / Red |
| News / Legal | Lawsuits, fraud, criminal records, negative press, FB group complaints | Green / Yellow / Red |
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
- Receipts include full Google search results for auditability

## Requirements

- `NOTION_KEY`, `NOTION_DB_ID`, `MOONSHOT_API_KEY` environment variables
- `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_ID` environment variables
- Python 3.11+ with `openai`, `httpx`, `h2`, `requests`, `python-dotenv`
- Notion database must have `BG Check` (select) and `BG Check Notes` (rich_text) properties

## Google Custom Search Setup

1. Create a Google Cloud project at https://console.cloud.google.com/
2. Enable the "Custom Search API"
3. Create an API key (restrict to Custom Search API only)
4. Create a Programmable Search Engine at https://programmablesearchengine.google.com/
   - Set "Search the entire web" = ON
5. Add `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_ID` to `.env`

Free tier: 100 queries/day. Paid: $5 per 1,000 queries (~$0.025/candidate).
