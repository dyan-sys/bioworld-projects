# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ally OS is an automation platform for talent operations. The repository is organized by skills:

- `.claude/skills/` - Automation skills (each skill contains its own libraries, templates, and workflows)
- `local-data/` - Output artifacts (not committed to git)

## Development Setup

```bash
# Python Requirements
# Requires Python 3.11+ with OpenSSL 3.x for API compatibility
python3.11 --version  # Should show Python 3.11.x with OpenSSL 3.x

# Install dependencies
pip install -r requirements.txt

# Environment variables (create .env file)
NOTION_KEY=secret_xxx        # Notion integration token
NOTION_DB_ID=xxx             # Notion database ID
MOONSHOT_API_KEY=xxx         # Moonshot AI API key (for Kimi screener)
```

## Resume Screening Skill

Located in `.claude/skills/screen-resume/`:

### Screener Selection Guidance

**Recommended: Kimi (Moonshot AI)**
- Most accurate scoring against resume-scorer-v4.md rubric
- Properly distinguishes EA experience from general VA work
- Fair assessment of transferable skills
- Balanced evaluation across all buckets
- Uses thinking mode with HTTP/2 for VPN resilience

**Alternative: Claude CLI**
- Tends to be overly strict across all criteria
- May undervalue transferable skills
- Best for conservative filtering

**Performance Comparison (Tested Jan 2026):**
- Kimi: Most balanced, closest to rubric intent
- Claude: Most conservative, may miss qualified candidates

### Workflows

All screeners support two modes:
- **Batch mode**: Process multiple unscored candidates (`--limit N`, default 5)
- **Single-candidate mode**: Score one candidate by page ID (`--page-id <id>`)

#### Resume Screener (Claude CLI)
**File:** `.claude/skills/screen-resume/workflows/resume_screener.py`

Scores candidates using Claude CLI via subprocess. Writes to Notion fields:
- `Claude Rating` (rich_text)
- `Claude Recommendation` (select)
- `Claude Rationale` (rich_text)

```bash
# Batch mode
python3.11 .claude/skills/screen-resume/workflows/resume_screener.py --limit 5

# Single candidate
python3.11 .claude/skills/screen-resume/workflows/resume_screener.py --page-id <notion_page_id>
```

#### Resume Screener (Kimi AI)
**File:** `.claude/skills/screen-resume/workflows/resume_screener_kimi.py`

Scores candidates using Moonshot AI API (kimi-k2.5 with instant mode). Writes to Notion fields:
- `Kimi Rating` (rich_text)
- `Kimi Recommendation` (select)
- `Kimi Rationale` (rich_text)

```bash
# Batch mode
python3.11 .claude/skills/screen-resume/workflows/resume_screener_kimi.py --limit 5

# Single candidate
python3.11 .claude/skills/screen-resume/workflows/resume_screener_kimi.py --page-id <notion_page_id>
```

**Required:**
- Environment variable: `MOONSHOT_API_KEY`
- Python 3.11+ with OpenSSL 3.x
- Uses OpenAI SDK v2.17.0+ with streaming support
- Configured with `trust_env=False` to bypass VPN/proxy (avoids timeout issues)

**Model Configuration:**
- Using `kimi-k2.5` with **thinking mode enabled** (reasoning traces included)
- HTTP/2 transport with 3 retries for VPN resilience
- Handles both `reasoning_content` (thinking) and `content` (final JSON) streams
- Visual feedback: `·` for thinking activity, `.` for content generation

**Performance Notes:**
- **Most Accurate Screener**: Closest adherence to resume-scorer-v4.md rubric (tested Jan 2026)
- Correctly distinguishes EA vs VA experience per rubric guidelines
- Fair assessment of transferable skills (teaching, training, stakeholder management)
- Appropriate communication scoring (neither too harsh nor too generous)
- Recognizes context knowledge in marketing/e-commerce domains
- Balanced scoring: not overly strict like Claude

**Technical Details:**
- Requires `h2` package for HTTP/2: `pip3.11 install h2`
- Thinking mode provides deeper analysis than instant mode
- Successfully completes via VPN with HTTP/2 transport (no timeouts)

### Job-Specific Rubrics

The Kimi screener supports multiple job-specific rubrics based on Opening ID from the Post relation:

| Job Type Code | Job Title | Rubric File |
|---------------|-----------|-------------|
| EP | Executive Partner | resume-scorer-v4.md |
| EPP | EPP Product Associate | resume-scorer-epp.md (TBD) |

**How It Works:**
1. Screener reads "Post" relation from candidate's Notion page
2. Fetches the related Post page to extract "Opening ID" (e.g., "251003-EP")
3. Extracts job type code from Opening ID (e.g., "EP" from "251003-EP")
4. Maps job type to rubric using `job-type-mapping.json`
5. Loads and applies job-specific scoring criteria
6. Logs Opening ID and job title during processing

**Fallback Behavior:**
- Candidates without a Post relation use the Executive Partner rubric (default)
- Unknown job type codes trigger a warning and fall back to Executive Partner rubric

**Adding New Job Types:**
1. Edit `templates/job-type-mapping.json` to add new mapping
2. Create corresponding rubric file in `templates/` (e.g., `resume-scorer-newrole.md`)

**Note:** This approach bypasses the "Job Opening" rollup field due to Notion API limitations with formula rollups.

### Libraries

#### pdf_tools
**File:** `.claude/skills/screen-resume/libraries/pdf_tools.py`

- `extract_text_from_url(url)` - Downloads PDF to RAM, extracts text
- Handles Google Drive links automatically (converts to direct download URL)

### Templates

#### Resume Scorer V4
**File:** `.claude/skills/screen-resume/templates/resume-scorer-v4.md`

Comprehensive scoring rubric for Executive Partner candidates:
- 6 buckets: Education, Experience, Skills, Communication, Context, Other
- Weighted scoring (0-100 scale)
- 3 thresholds: Experience ≥10, Skills ≥5, Communication ≥2
- Recommendation tiers: STRONG PROCEED → DO NOT PROCEED

### Data Architecture

```
local-data/talent/
├── resume_raw_txt/           # Extracted resume text
│   └── {CandidateName}.txt
└── resume_receipts/          # Full scoring JSON
    ├── {CandidateName}_Claude.json
    └── {CandidateName}_Kimi.json
```

## Update Job Posts Skill

Located in `.claude/skills/update-job-posts/`:

Creates job post pages in the Job Posts DB for each Open opening in the Ally Openings DB, one per Post Channel (OLJ, Jobstreet, Facebook, Internal) with platform-specific template content.

### Workflow

**File:** `.claude/skills/update-job-posts/workflows/update_job_posts.py`

```bash
# Batch mode: all Open openings
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py

# Single opening
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py --opening-id <notion_page_id>

# Dry run (preview without creating)
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py --dry-run
```

**Required:**
- Environment variable: `NOTION_KEY`
- Python 3.11+
- Dependencies: `requests`, `python-dotenv`

### How It Works

1. Queries Ally Openings DB for Status = "Open"
2. Extracts job code from title prefix (e.g., "EP" from "251003-EP")
3. For each Post Channel, loads template by (job_code, channel)
4. Creates page in Job Posts DB with: relation, channel, status, body blocks
5. Reads back GEN PostID formula and updates title to match
6. Sets Post ID to page ID (no dashes)

### Notion Databases

**Ally Openings DB** (`28c2b7ec45978030be21e73d34d126a0`):
- `Opening ID & Name` (title)
- `Post Channels` (multi_select): OLJ, Jobstreet, Facebook, Internal
- `Status` (status): filter for "Open"

**Job Posts DB** (`28c2b7ec459780c6a4b6c047caf8c5fe`):
- `Job Post Title` (title): set to GEN PostID formula value
- `Opening` (relation): linked to opening
- `Post Channel` (select): channel name
- `Status` (status): set to "Drafting"
- `Post ID` (rich_text): page ID without dashes

### Templates

Platform-specific markdown templates in `templates/`:
- EP: `EP-OLJ.md`, `EP-Jobstreet.md`, `EP-Facebook.md`, `EP-Internal.md`
- EPP: `EPP-OLJ.md`, `EPP-Jobstreet.md`, `EPP-Facebook.md`, `EPP-Internal.md`
- Fallback: `_default.md`

**Adding New Templates:**
1. Create `{JOBCODE}-{Channel}.md` in `templates/`
2. Add mapping in `libraries/template_registry.py`

## Notion Database Schema

Required properties for candidate database:
- `Full Name` (title)
- `Resume` (files)
- `Claude Rating` (rich_text)
- `Claude Recommendation` (select)
- `Claude Rationale` (rich_text)
- `Kimi Rating` (rich_text)
- `Kimi Recommendation` (select)
- `Kimi Rationale` (rich_text)
- `Status` (status)
- `Date Created` (created_time)
