# Background Check

Automated online background screening for candidates using Serper.dev (Google Search) + Gemini AI analysis. Checks LinkedIn consistency, news/legal records, social media, and professional contributions before candidates advance in the pipeline.

## Trigger

**Scheduled:** Daily at 2pm and 9pm SGT via `com.ally.socials-check.plist`. Batch mode processes up to 10 candidates (batch-size 3) who have 2R=Proceed, empty Socials Check, and were last edited in the past 5 days.

**On-demand:** Can also be run manually for single candidates via `--page-id` (bypasses the date filter).

## Usage

```bash
# Single candidate (dry run — receipt only, no Notion update)
python3.11 .claude/skills/background-check/workflows/background_check.py \
  --page-id <notion-page-uuid> --dry-run

# Single candidate (full — updates Notion)
python3.11 .claude/skills/background-check/workflows/background_check.py \
  --page-id <notion-page-uuid>

# Batch mode (default: 2R=Proceed, Socials Check empty)
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
2. **Extract data** — Parse email prefix, school, job title, and employers from resume text
3. **Deterministic queries** — Generate ~15-18 targeted search queries from templates using candidate data (site: operators for LinkedIn, Facebook groups, Instagram, TikTok, freelance platforms, etc.)
4. **Serper.dev search** — Execute queries against Google via Serper API (full `site:` operator support, unlike Gemini grounding)
5. **Gemini analysis** — Analyze deduplicated search results across 4 categories, return structured JSON
6. **Save receipt** → `local-data/talent/background_checks/{Name}_{timestamp}.json`
7. **Update Notion** → `Socials Check` (select) + `Socials Check Notes` (rich_text)

## Query Coverage

The deterministic template generates queries for:
- LinkedIn (`site:linkedin.com/in` with name variations)
- Facebook profile + group posts (`site:facebook.com` with scam/beware/FFO keywords)
- Instagram, TikTok, Threads (via email prefix or name)
- News/legal (lawsuit, fraud, criminal, scam, estafa)
- Philippines-specific (NBI, court, criminal record)
- Employer cross-reference (name + each employer)
- Education verification (name + school)
- Professional contributions (blog, github, portfolio)
- Freelance platforms (`site:onlinejobs.ph`, `site:upwork.com`)
- Regional forums/news (rappler, inquirer, philstar, reddit)

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
- Gemini is instructed to only report findings for the specific candidate
- Low-confidence results automatically escalate to "Review Recommended"

## Notion Properties Required

- **`Socials Check`** — Select: `Clear`, `Review Recommended`, `Flag`
- **`Socials Check Notes`** — Rich Text (max 2000 chars)

## Output

- Receipts: `local-data/talent/background_checks/{Name}_{timestamp}.json`
- Receipts include full Serper search results and extracted candidate data for auditability

## Requirements

- `NOTION_KEY`, `NOTION_DB_ID`, `SERPER_API_KEY`, `GEMINI_API_KEY` environment variables
- Python 3.11+ with `google-genai`, `requests`, `python-dotenv`
- Notion database must have `Socials Check` (select) and `Socials Check Notes` (rich_text) properties

## Serper.dev Setup

1. Sign up at https://serper.dev/
2. Get your API key from the dashboard
3. Add `SERPER_API_KEY=xxx` to `.env`

Free tier: 2,500 queries. Paid: $1 per 1,000 queries (~$0.015/candidate at ~15 queries each).
