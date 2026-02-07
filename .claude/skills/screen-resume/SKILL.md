---
name: screen-resume
description: Trigger when user mentions screening resumes, scoring candidates, running the resume screener, or evaluating candidates against the scoring rubric
---

# Resume Screening Skill

This project has an automated resume screening pipeline that scores Executive Partner candidates against a weighted rubric and writes results to Notion.

## Recommended Screener

**Use Kimi (Moonshot AI) for primary screening** - Most accurate against resume-scorer-v4.md rubric based on comparative testing (Jan 2026). Properly distinguishes EA experience from VA work, fairly assesses transferable skills, and provides balanced evaluation across all scoring buckets.

## Screener Variants

| Model | Script | Notion Fields | API | Accuracy |
|-------|--------|---------------|-----|----------|
| **Kimi** ⭐ | `workflows/resume_screener_kimi.py` | `Kimi Rating`, `Kimi Recommendation`, `Kimi Rationale` | Moonshot AI (`kimi-k2.5` thinking mode) | **Most Accurate** |
| **Claude** | `workflows/resume_screener.py` | `Claude Rating`, `Claude Recommendation`, `Claude Rationale` | Claude CLI (subprocess) | Most Conservative |

## Scoring Rubrics

### Job-Specific Rubrics

The Kimi screener automatically selects the appropriate rubric based on the Opening ID from the Post relation:

| Job Type Code | Job Title | Rubric File |
|---------------|-----------|-------------|
| EP | Executive Partner | `resume-scorer-v4.md` (default) |
| EPP | EPP Product Associate | `resume-scorer-epp.md` (TBD) |

**How it works:**
1. Screener reads the "Post" relation from candidate
2. Fetches the Post page and extracts "Opening ID" (e.g., "251003-EP")
3. Extracts job type code (e.g., "EP") from Opening ID
4. Looks up job type in `templates/job-type-mapping.json`
5. Loads the corresponding rubric file

**How to add new job types:**
1. Create a new rubric file in `templates/` (e.g., `resume-scorer-newrole.md`)
2. Edit `templates/job-type-mapping.json` to add the mapping:
   ```json
   "NEWTYPE": {
     "title": "New Role Title",
     "rubric": "resume-scorer-newrole.md"
   }
   ```
3. Run screener - it will automatically use the correct rubric per candidate

**Fallback behavior:**
- Candidates without a Post relation use the Executive Partner rubric
- Unknown job type codes trigger a warning and use the Executive Partner rubric

### Executive Partner Rubric (resume-scorer-v4.md)

Six weighted buckets scored 0-100:

| Bucket | Weight | Threshold |
|--------|--------|-----------|
| Education | 20% | None |
| Experience & Trajectory | 20% | >= 10.0 raw |
| Skills | 20% | >= 5.0 raw |
| Communication | 20% | >= 2.0 raw |
| Context Knowledge | 10% | None |
| Other Factors | 10% | None |

Recommendation tiers: **STRONG PROCEED** > **PROCEED** > **PROCEED WITH RESERVATIONS** > **DO NOT PROCEED**

## Data Outputs

```
local-data/talent/
├── resume_raw_txt/           # Extracted resume text
│   └── {CandidateName}.txt
└── resume_receipts/          # Full scoring JSON receipts
    ├── {CandidateName}_Claude.json
    └── {CandidateName}_Kimi.json
```

## Requirements

**Python:**
- Python 3.11+ with OpenSSL 3.x (required for API compatibility)
- OpenAI SDK v2.17.0+ (for Kimi screener)

**Environment Variables:**
All screeners require `NOTION_KEY` and `NOTION_DB_ID`. Additionally:
- Kimi screener requires `MOONSHOT_API_KEY`
- Claude screener requires Claude CLI to be installed

**Kimi Screener Configuration:**
- Uses `kimi-k2.5` model in **thinking mode** (reasoning enabled for deeper analysis)
- HTTP/2 transport with 3 retries for VPN resilience
- Configured with `trust_env=False` to bypass VPN/proxy (prevents timeout issues)
- Handles both reasoning traces and final JSON output
- **Requires:** `pip3.11 install h2` for HTTP/2 support

**Why Kimi is Most Accurate (Comparative Testing - Jan 2026):**
- ✅ Correctly identifies zero EA experience vs inflated VA experience (per rubric guidelines)
- ✅ Fair assessment of transferable skills (teaching, training, stakeholder management)
- ✅ Appropriate communication scoring (MEETS threshold = 2.0)
- ✅ Recognizes marketing/e-commerce context knowledge
- ✅ Complete scoring of age, MBA, and other factors
- ✅ Balanced: not overly harsh like Claude

## How to Run

All screeners support two modes:

### Batch Mode (default)
Processes multiple unscored candidates from Notion database:

```bash
# Process next 5 unscored candidates (default)
python3.11 workflows/resume_screener_kimi.py

# Process specific number of candidates
python3.11 workflows/resume_screener_kimi.py --limit 10
python3.11 workflows/resume_screener.py --limit 3
```

### Single-Candidate Mode
Score a specific candidate by Notion page ID:

```bash
# Score one candidate by page ID
python3.11 workflows/resume_screener_kimi.py --page-id 2ff2b7ec-4597-8158-a012-ff2dcc2a252c
python3.11 workflows/resume_screener.py --page-id abc123...
```

Each script extracts resume text, scores against the rubric, saves a receipt JSON, and updates the Notion page.
