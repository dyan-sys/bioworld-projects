# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ally OS is an automation platform for talent operations. The repository is organized by skills:

- `skills/` - Automation skills (each skill contains its own libraries, templates, and workflows)
- `local-data/` - Output artifacts (not committed to git)

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Environment variables (create .env file)
NOTION_KEY=secret_xxx        # Notion integration token
NOTION_DB_ID=xxx             # Notion database ID
```

## Resume Screening Skill

Located in `skills/screen_resume/`:

### Workflows

#### Resume Screener (Claude CLI)
**File:** `skills/screen_resume/workflows/resume_screener.py`

Scores candidates using Claude CLI via subprocess. Writes to Notion fields:
- `Claude Rating` (rich_text)
- `Claude Recommendation` (select)
- `Claude Rationale` (rich_text)

```bash
python skills/screen_resume/workflows/resume_screener.py
```

#### Resume Screener (Codex CLI)
**File:** `skills/screen_resume/workflows/resume_screener_codex.py`

Scores candidates using OpenAI Codex CLI (gpt-5.1). Writes to Notion fields:
- `Manus Rating` (rich_text)
- `Manus Recommendation` (select)
- `Manus Rationale` (rich_text)

```bash
python skills/screen_resume/workflows/resume_screener_codex.py
```

#### Resume Screener (Kimi AI)
**File:** `skills/screen_resume/workflows/resume_screener_kimi.py`

Scores candidates using Moonshot AI API (kimi-k2.5). Writes to Notion fields:
- `Kimi Rating` (rich_text)
- `Kimi Recommendation` (select)
- `Kimi Rationale` (rich_text)

```bash
python skills/screen_resume/workflows/resume_screener_kimi.py
```

**Required environment variable:** `MOONSHOT_API_KEY`

### Libraries

#### pdf_tools
**File:** `skills/screen_resume/libraries/pdf_tools.py`

- `extract_text_from_url(url)` - Downloads PDF to RAM, extracts text
- Handles Google Drive links automatically (converts to direct download URL)

### Templates

#### Resume Scorer V4
**File:** `skills/screen_resume/templates/resume-scorer-v4.md`

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
