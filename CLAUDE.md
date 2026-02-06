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

**Alternative: Manus (Codex)**
- Slightly overvalues non-EA experience
- Good for second opinions

**Alternative: Claude CLI**
- Tends to be overly strict across all criteria
- May undervalue transferable skills
- Best for conservative filtering

**Performance Comparison (Tested Jan 2026):**
- Kimi: Most balanced, closest to rubric intent
- Manus: 2nd best, slightly generous on experience
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

#### Resume Screener (Codex CLI)
**File:** `.claude/skills/screen-resume/workflows/resume_screener_codex.py`

Scores candidates using OpenAI Codex CLI (gpt-5.1). Writes to Notion fields:
- `Manus Rating` (rich_text)
- `Manus Recommendation` (select)
- `Manus Rationale` (rich_text)

```bash
# Batch mode
python3.11 .claude/skills/screen-resume/workflows/resume_screener_codex.py --limit 5

# Single candidate
python3.11 .claude/skills/screen-resume/workflows/resume_screener_codex.py --page-id <notion_page_id>
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
- Balanced scoring: not overly strict like Claude, not overly generous like Manus

**Technical Details:**
- Requires `h2` package for HTTP/2: `pip3.11 install h2`
- Thinking mode provides deeper analysis than instant mode
- Successfully completes via VPN with HTTP/2 transport (no timeouts)

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
    ├── {CandidateName}_Codex.json
    └── {CandidateName}_Kimi.json
```

## Notion Database Schema

Required properties for candidate database:
- `Full Name` (title)
- `Resume` (files)
- `Claude Rating` (rich_text)
- `Claude Recommendation` (select)
- `Claude Rationale` (rich_text)
- `Manus Rating` (rich_text)
- `Manus Recommendation` (select)
- `Manus Rationale` (rich_text)
- `Kimi Rating` (rich_text)
- `Kimi Recommendation` (select)
- `Kimi Rationale` (rich_text)
- `Status` (status) - for Codex query filter
- `Date Created` (created_time)
