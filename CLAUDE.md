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
| EPP | EPP Product Associate | resume-scorer-epp.md |
| CPL | Client Partnership Lead | resume-scorer-cpl.md |

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

#### Resume Scorer V4 (Executive Partner)
**File:** `.claude/skills/screen-resume/templates/resume-scorer-v4.md`

Comprehensive scoring rubric for Executive Partner candidates:
- 6 buckets: Education, Experience, Skills, Communication, Context, Other
- Weighted scoring (0-100 scale)
- 3 thresholds: Experience ≥10, Skills ≥5, Communication ≥2
- Age override: >36 caps recommendation at PROCEED WITH CAUTION
- Recommendation tiers: STRONG PROCEED → DO NOT PROCEED

#### Resume Scorer EPP (Product Associate)
**File:** `.claude/skills/screen-resume/templates/resume-scorer-epp.md`

Product Associate rubric focusing on eCommerce operations:
- 6 buckets: Education, Experience, Skills, Communication, Context, Other
- Weighted scoring (0-100 scale)
- 3 thresholds: Experience ≥8, Skills ≥10, Communication ≥2
- Key criteria: Mandarin fluency (0-3 pts), vendor management, eCommerce experience
- Age override: >36 caps recommendation at PROCEED WITH CAUTION
- Adapted for international universities (Philippines, Malaysia, etc.)

#### Resume Scorer CPL (Client Partnership Lead)
**File:** `.claude/skills/screen-resume/templates/resume-scorer-cpl.md`

Client Partnership Lead rubric for operations leadership:
- 6 buckets: Education, Experience, Skills, Communication, Context, Other
- Weighted scoring (0-100 scale)
- 3 thresholds: Experience ≥10, Skills ≥8, Communication ≥2
- Priority: Brand name companies (Athena, TaskUs, etc.), people management depth
- Key criteria: 2+ years coaching/management, client success operations, US/EU exposure
- Target calibration: ~80-85 for strong Operations Manager with 10+ years at premium agencies

### Data Architecture

```
local-data/talent/
├── resume_raw_txt/           # Extracted resume text
│   └── {CandidateName}.txt
└── resume_receipts/          # Full scoring JSON
    ├── {CandidateName}_Claude.json
    └── {CandidateName}_Kimi.json
```

## Update Resume Screener Skill

Located in `.claude/skills/update-resume-screener/`:

Documents the repeatable process for adding new job-specific scoring rubrics when Ally launches new roles. This is a process documentation skill, not an automated workflow.

### When to Use

Use this process when:
- Launching a new job opening that requires different scoring criteria than existing roles (EP, EPP, CPL)
- The new role has distinct requirements (different skills, experience, or context knowledge)
- You want consistent, calibrated scoring for the new role

### Process Overview

**10-step process:**
1. Gather requirements (JD, Opening ID, reference candidates, target score)
2. Design rubric structure (adapt from existing EP/EPP/CPL rubrics)
3. Set thresholds (experience, skills, communication minimums)
4. Define overrides (age, company tier, special rules)
5. Calibrate with reference candidates (target: 75-85 for strong fits)
6. Create rubric file (`templates/resume-scorer-{code}.md`)
7. Add job type mapping (`templates/job-type-mapping.json`)
8. Test with Kimi screener (verify scoring and rubric loading)
9. Test with diverse candidates (strong, weak, borderline)
10. Update documentation (CLAUDE.md, SKILL.md)

### Key Principles

- **Start with reference candidates** - Easier to calibrate with real examples
- **Adapt existing rubrics** - Copy structure from similar roles (EP for operations, EPP for product, CPL for leadership)
- **Balance bucket weights** - Avoid over-weighting optional skills
- **Test thoroughly** - Verify with 3+ candidates before production use
- **Document calibration** - Add target scores and reference candidate details

### Files Modified

When adding a new rubric:
- `templates/resume-scorer-{code}.md` - CREATE new rubric
- `templates/job-type-mapping.json` - EDIT to add mapping
- `CLAUDE.md` - EDIT to update documentation (2 sections)
- `.claude/skills/screen-resume/SKILL.md` - EDIT to update skill docs

No code changes needed - screening system auto-detects new rubrics.

### Examples

**CPL (Client Partnership Lead):**
- Priority: Brand name companies (Athena, TaskUs)
- Target: 80-85 for Operations Manager with 10+ years
- Reference: Shariebel scored 84.03 ✅

**EPP (Product Associate):**
- Priority: Mandarin fluency (0-3 pts), eCommerce experience
- Target: 75-85 for product coordinator with 5+ years
- Reference: LOW KAH WEI scored 83.75 ✅

See `.claude/skills/update-resume-screener/SKILL.md` for detailed step-by-step guide.

## Update Job Posts Skill

Located in `.claude/skills/update-job-posts/`:

Creates job post pages in the Job Posts DB for each Open opening in the Ally Openings DB, one per Post Channel (OLJ, Jobstreet, Facebook, Internal) with platform-specific template content and `{{variable}}` substitution.

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
2. Extracts job code, metadata fields (job title, employment type, advertised range, local range, collaboration window, intake form URL)
3. For each Post Channel:
   a. Creates page in Job Posts DB (properties only, no body)
   b. Sets Post ID (page ID without dashes)
   c. Computes submission form URL = intake_form_url + "?id=" + post_id
   d. Computes hiring target date (today + 14 days in SGT)
   e. Loads template with `{{variable}}` substitution
   f. Appends body blocks to the page
   g. Loads email reply template (if exists) and writes to "Reply Email Template" field
   h. Reads back GEN PostID formula and updates title to match

### Template Variables

| Variable | Source |
|----------|--------|
| `{{job_title}}` | Openings DB "Job Title" |
| `{{employment_type}}` | Openings DB "Employment Type" |
| `{{advertised_range}}` | Openings DB "Advertised Range" |
| `{{advertised_range_local}}` | Openings DB "Advertised Range (Local)" — falls back to USD range if empty |
| `{{target_collab_window}}` | Openings DB "Target Collaboration Window" |
| `{{hiring_target_date}}` | Computed: today + 14 days in SGT (e.g., "Feb 22, 2026") |
| `{{submission_form_url}}` | Computed: intake_form_url + "?id=" + post_id |
| `{{post_id}}` | Page ID without dashes |
| `{{prefix}}` | Opening prefix (e.g., "251003-EP") |
| `{{channel}}` | Channel name |

### Email Reply Templates

Jobstreet posts include a pre-formatted reply email written to the "Reply Email Template" rich_text field. Templates follow the naming convention `{JOBCODE}-{Channel}-email.md`.

- `EP-Jobstreet-email.md` — EP reply with local pay range and submission URL
- `EPP-Jobstreet-email.md` — EPP reply with Mandarin requirement note

### Notion Databases

**Ally Openings DB** (`28c2b7ec45978030be21e73d34d126a0`):
- `Opening ID & Name` (title)
- `Post Channels` (multi_select): OLJ, Jobstreet, Facebook, Internal
- `Status` (status): filter for "Open"
- `Opening Base In-Take Form` (rich_text): base URL for intake form
- `Job Title` (rich_text): advertised job title
- `Employment Type` (rich_text): e.g., "Full-Time"
- `Advertised Range` (rich_text): e.g., "USD $1,000 - $1,200 per month"
- `Advertised Range (Local)` (rich_text): e.g., "PHP 55,000 - PHP 70,000 per month"
- `Target Collaboration Window` (rich_text): e.g., "Asia / US Time Zone"

**Job Posts DB** (`28c2b7ec459780c6a4b6c047caf8c5fe`):
- `Job Post Title` (title): set to GEN PostID formula value
- `Opening` (relation): linked to opening
- `Post Channel` (select): channel name
- `Status` (status): set to "Drafting"
- `Post ID` (rich_text): page ID without dashes
- `Opening Base In-take form` (url): intake form URL
- `Reply Email Template` (rich_text): pre-formatted reply email for Jobstreet

### Templates

Platform-specific markdown templates in `templates/`, each with two sections:
1. **Platform Metadata** — Form fields for the person posting
2. **Job Post Copy** — The actual post content with `{{variable}}` placeholders

- EP: `EP-OLJ.md`, `EP-Jobstreet.md`, `EP-Facebook.md`, `EP-Internal.md`
- EPP: `EPP-OLJ.md`, `EPP-Jobstreet.md`, `EPP-Facebook.md`, `EPP-Internal.md`
- Fallback: `_default.md`

**Channel-specific behavior:**
- **Jobstreet**: Uses "by invitation only" instead of submission URL in post body; uses `{{advertised_range_local}}` for platform pay range
- **OLJ, Facebook, Internal**: Shows `{{submission_form_url}}` directly in post body

**Adding New Templates:**
1. Create `{JOBCODE}-{Channel}.md` in `templates/`
2. Add mapping in `libraries/template_registry.py`

## Check Recruit Status Skill

Located in `.claude/skills/check-recruit-status/`:

Queries the Notion Candidates DB and prints a terminal report with 4 key metrics for daily recruitment monitoring.

### Workflow

**File:** `.claude/skills/check-recruit-status/workflows/check_recruit_status.py`

```bash
# Default (7-day window)
python3.11 .claude/skills/check-recruit-status/workflows/check_recruit_status.py

# Custom window
python3.11 .claude/skills/check-recruit-status/workflows/check_recruit_status.py --days 14
```

**Required:**
- Environment variables: `NOTION_KEY`, `NOTION_DB_ID`
- Python 3.11+
- Dependencies: `requests`, `python-dotenv`

### Metrics

1. **Pipeline Overview** — Total candidates, new in window (configurable days), new today
2. **Status Breakdown** — Count per status with bar chart and percentage, sorted by count
3. **Screening Backlog** — Kimi/Claude scored vs unscored with coverage percentage
4. **Quality Distribution** — Kimi recommendation tier counts (STRONG PROCEED → DO NOT PROCEED)

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
