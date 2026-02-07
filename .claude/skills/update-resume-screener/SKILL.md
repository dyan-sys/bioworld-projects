---
name: update-resume-screener
description: Process for adding new job-specific rubrics to the resume screening system when supporting new roles
---

# Update Resume Screener Skill

This skill documents the repeatable process for adding job-specific scoring rubrics to the resume screening system when Ally starts hiring for new roles.

## When to Use This Process

Use this process when:
- Launching a new job opening that requires different scoring criteria than existing roles
- The new role has distinct requirements (different skills, experience, or context knowledge)
- You want consistent, calibrated scoring for the new role

## Overview

The resume screening system supports multiple job-specific rubrics. Each job opening gets a unique Opening ID (e.g., `251007-CPL`) where the suffix (`CPL`) determines which scoring rubric to use. This process guides you through:

1. **Analyzing** the job description and requirements
2. **Creating** a calibrated scoring rubric
3. **Testing** with reference candidates
4. **Integrating** into the screening system
5. **Documenting** for future reference

---

## Step-by-Step Process

### Step 1: Gather Requirements

**Inputs needed:**
- ✅ Job description (JD) with requirements and responsibilities
- ✅ Job Opening ID format (e.g., `251007-CPL`)
- ✅ 1-2 reference candidates (resumes of candidates you'd consider "strong fits")
- ✅ Target score range for reference candidates (typically 75-85 for strong candidates)
- ✅ Priority criteria (what matters most for this role?)

**Questions to clarify:**
- What makes this role different from existing roles (EP, EPP, CPL)?
- What experience is required vs. nice-to-have?
- Are there any deal-breaker requirements (e.g., Mandarin for EPP, brand name companies for CPL)?
- What's the expected education level?
- Any age considerations or other demographic factors?

### Step 2: Design the Rubric Structure

**Base template:** Use an existing rubric as starting point
- For EA/operations roles: Start from `resume-scorer-v4.md` (EP)
- For product/technical roles: Start from `resume-scorer-epp.md` (EPP)
- For leadership/client-facing: Start from `resume-scorer-cpl.md` (CPL)

**Six buckets to adapt:**

#### 2.1 Education (max 6 raw → 0-4 equivalent)
- **University tier**: Adapt to candidate's country (Philippines, Malaysia, Singapore, etc.)
- **Honors/distinction**: Cum Laude, Dean's List, etc.
- **Degree relevance**: What majors are relevant to this role?

**Example adaptations:**
- EPP: Computer Science/Engineering relevant for product work
- CPL: Psychology relevant for coaching/people management

#### 2.2 Experience Trajectory (max 19 raw → 0-4 equivalent)
- **Years of experience** (0-11 points): How many years required for this role?
- **Depth of experience** (0-3 points): What scope/complexity matters?
- **Company tier & rigor** (0-3 points): Does brand name matter? Which companies are Tier 1?
- **Scope & complexity** (0-2 points): Multi-client? Cross-functional? Strategic?

**Thresholds:**
- Set minimum raw experience score (typically 8-10)
- Higher threshold = more selective role

#### 2.3 Skills (max 16 raw → 0-4 equivalent)
- **Core skill categories** (4-8 points each): What are the 2-4 most important skill clusters?
- **Tools & systems** (0-3 points): What software proficiency is needed?
- **Specialized skills** (0-3 points): Languages, certifications, domain expertise?

**Examples:**
- EP: EA skills, stakeholder management, project coordination
- EPP: Mandarin (0-3), vendor management, follow-up systems
- CPL: Client partnership, coaching, quality systems

**Thresholds:**
- Set minimum raw skills score (typically 5-10)
- Higher threshold = more specialized role

#### 2.4 Communication (max 4 raw → 0-4 equivalent)
- **Resume quality** (0-4 points): Professional presentation, clarity, grammar
- Usually consistent across all roles
- Threshold: typically 2.0 (MEETS standard)

#### 2.5 Context Knowledge (max 4 raw → 0-4 equivalent)
- **Domain knowledge** (0-2 points each): What industries or contexts matter?
- Balance two sub-categories at 0-2 points each

**Examples:**
- EP: US/EU business context, EA operations
- EPP: eCommerce operations (0-2), supply chain (0-2)
- CPL: Client success operations (0-2), US/EU founders (0-2)

#### 2.6 Other Factors (max 4 raw → 0-4 equivalent)
- **Company brands** (0-2.5 points): Tier 1 companies that signal quality
- **Awards & recognition** (0-1.5 points): Performance awards, certifications

**Priority weighting:**
- CPL heavily weights brand names (Athena = Tier 1)
- EP weights MBA and references
- EPP weights eCommerce experience

### Step 3: Set Thresholds

**Three critical thresholds** determine if candidate can proceed:

1. **Experience Threshold**: Raw experience score ≥ X
   - Conservative roles: ≥ 10.0 (EP, CPL)
   - Moderate roles: ≥ 8.0 (EPP)

2. **Skills Threshold**: Raw skills score ≥ Y
   - Specialized roles: ≥ 10.0 (EPP - needs Mandarin)
   - Broad roles: ≥ 8.0 (CPL)
   - General roles: ≥ 5.0 (EP)

3. **Communication Threshold**: Raw communication score ≥ 2.0
   - Usually 2.0 across all roles (MEETS standard)

**If ANY threshold fails → "DO NOT PROCEED" regardless of total score**

### Step 4: Define Overrides & Special Rules

**Age override** (if applicable):
- EP & EPP: Candidates >36 years capped at "PROCEED WITH CAUTION"
- Calculation: Estimated age = 22 + (current_year - graduation_year)
- Applied AFTER score calculation

**Other overrides:**
- Add any role-specific rules that override final recommendation
- Document reasoning clearly in rubric

### Step 5: Calibrate with Reference Candidates

**Goal:** Reference candidate should score in target range (typically 75-85 for strong fits)

**Process:**
1. Extract reference candidate's resume to `/tmp/reference_resume.txt`
2. Manually calculate their score bucket-by-bucket using draft rubric
3. Adjust scoring weights if score is too high/low:
   - **Score too high (>90)**: Increase max values or reduce weights in strong areas
   - **Score too low (<70)**: Decrease max values or increase weights in strong areas
   - **Score just right (75-85)**: Rubric is calibrated! ✅

**Example calibration (CPL):**
- Reference: Shariebel (Operations Manager at Athena, 11 years, 150+ team)
- Target: ~80
- Result: 84.03 ✅
- Education: 4.0/6, Experience: 19/19 (maxed), Skills: 14/16, Communication: 3/4, Context: 4/4 (maxed), Other: 3/4

**Calibration tips:**
- If experience maxes out (19/19), that's okay for senior roles
- Strong candidates should typically max 1-2 buckets, not all buckets
- Score distribution should reflect role priorities

### Step 6: Create Rubric File

**File location:** `.claude/skills/screen-resume/templates/resume-scorer-{jobcode}.md`

**Example:** `.claude/skills/screen-resume/templates/resume-scorer-cpl.md`

**File structure:**
```markdown
# Resume Scoring Rubric: {Job Title} ({JOB CODE})

## Role Context
[Describe the role, ideal backgrounds, key success factors]

## Scoring Structure
[Overview of 6 buckets and weights]

## CRITICAL THRESHOLDS (Must Pass to Proceed)
[Define 3 thresholds with reasoning]

## 1. EDUCATION (Max 6 raw → 0-4 equivalent)
[Detailed scoring criteria]

## 2. EXPERIENCE TRAJECTORY (Max 19 raw → 0-4 equivalent)
[Detailed scoring criteria]

## 3. SKILLS (Max 16 raw → 0-4 equivalent)
[Detailed scoring criteria]

## 4. COMMUNICATION (Max 4 raw → 0-4 equivalent)
[Detailed scoring criteria]

## 5. CONTEXT KNOWLEDGE (Max 4 raw → 0-4 equivalent)
[Detailed scoring criteria]

## 6. OTHER FACTORS (Max 4 raw → 0-4 equivalent)
[Detailed scoring criteria]

## FINAL SCORE CALCULATION
[Step-by-step calculation formula]

## RECOMMENDATION TIERS
[Tier 1 Strong, Tier 1 Moderate, Tier 2, Tier 3, Tier 4]

## OUTPUT FORMAT
[JSON schema for AI output]

## EVALUATION PRINCIPLES
[Key principles and calibration notes]
```

**Key sections to customize:**
- **Role Context**: What makes this role unique?
- **Company Tier & Rigor**: Which companies are Tier 1 for this role?
- **Skills**: Role-specific competencies
- **Context Knowledge**: Industry/domain expertise needed
- **Evaluation Principles**: Calibration guidance (e.g., "Target score of ~80 for Operations Manager with 10+ years at premium agencies")

### Step 7: Add Job Type Mapping

**File:** `.claude/skills/screen-resume/templates/job-type-mapping.json`

Add new entry:
```json
{
  "mappings": {
    "EP": { ... },
    "EPP": { ... },
    "NEWCODE": {
      "title": "New Job Title",
      "rubric": "resume-scorer-newcode.md"
    }
  }
}
```

**Job code format:** Extract from Opening ID
- Opening ID: `251007-CPL` → Job code: `CPL`
- Opening ID: `251003-EP` → Job code: `EP`
- Opening ID: `251006-EPP` → Job code: `EPP`

### Step 8: Test with Kimi Screener

**Test the new rubric with reference candidate:**

```bash
cd /Users/yikfaiivanli/Projects/ally-os

# Test with single candidate
python3.11 .claude/skills/screen-resume/workflows/resume_screener_kimi.py --page-id <reference_candidate_page_id>
```

**Verify:**
- ✅ Opening ID extracted correctly (e.g., `251007-CPL`)
- ✅ Job title displayed correctly (e.g., `Client Partnership Lead`)
- ✅ Correct rubric loaded (e.g., `resume-scorer-cpl.md`)
- ✅ Score in target range (e.g., 75-85 for strong candidate)
- ✅ Recommendation tier appropriate (e.g., `STRONG PROCEED`)
- ✅ Rationale makes sense and follows rubric logic

**Check output files:**
- `local-data/talent/resume_raw_txt/{CandidateName}.txt` - Resume text extracted
- `local-data/talent/resume_receipts/{CandidateName}_Kimi.json` - Full scoring details

**Review JSON receipt:**
```json
{
  "candidate_name": "...",
  "final_score": 84.03,
  "tier": "Tier 1 Moderate",
  "recommendation": "STRONG PROCEED",
  "bucket_scores": {
    "education": { "raw": 4.0, "max": 6.0, "equivalent_0_4": 2.67 },
    "experience_trajectory": { "raw": 19.0, "max": 19.0, "equivalent_0_4": 4.0 },
    ...
  }
}
```

**If score is off target:**
- Adjust bucket max values or scoring criteria in rubric
- Re-test until calibration is correct
- Document any adjustments in rubric's "Evaluation Principles" section

### Step 9: Test with Multiple Candidates

**Test with diverse candidate profiles:**
- ✅ Strong candidate (should score 75-85)
- ✅ Weak candidate (should score <60)
- ✅ Borderline candidate (should score 60-75)

**Verify rubric discriminates appropriately:**
- Strong candidates should pass all thresholds comfortably
- Weak candidates should fail thresholds or score in Tier 4
- Borderline candidates should get "PROCEED WITH QUESTIONS" or "PROCEED WITH CAUTION"

### Step 10: Update Documentation

**Update CLAUDE.md:**

Add to "Job-Specific Rubrics" table:
```markdown
| Job Type Code | Job Title | Rubric File |
|---------------|-----------|-------------|
| EP | Executive Partner | resume-scorer-v4.md |
| EPP | EPP Product Associate | resume-scorer-epp.md |
| CPL | Client Partnership Lead | resume-scorer-cpl.md |
| NEWCODE | New Job Title | resume-scorer-newcode.md |  # ADD THIS
```

Add to "Templates" section:
```markdown
#### Resume Scorer {NEWCODE} ({Job Title})
**File:** `.claude/skills/screen-resume/templates/resume-scorer-newcode.md`

{Job Title} rubric focusing on {key focus areas}:
- 6 buckets: Education, Experience, Skills, Communication, Context, Other
- Weighted scoring (0-100 scale)
- 3 thresholds: Experience ≥X, Skills ≥Y, Communication ≥2
- Key criteria: {list 2-3 distinctive criteria}
- Special rules: {age override, company tier priority, etc.}
- Target calibration: ~{target score} for {reference candidate description}
```

**Update `.claude/skills/screen-resume/SKILL.md`:**

Update "Job-Specific Rubrics" table (same as CLAUDE.md)

---

## Quick Reference: Files to Modify

When adding a new job-specific rubric, you'll touch these files:

| File | Action | Purpose |
|------|--------|---------|
| `templates/resume-scorer-{code}.md` | **CREATE** | New scoring rubric |
| `templates/job-type-mapping.json` | **EDIT** | Add job code mapping |
| `CLAUDE.md` | **EDIT** | Update documentation (2 sections) |
| `.claude/skills/screen-resume/SKILL.md` | **EDIT** | Update skill documentation |
| `local-data/talent/resume_receipts/` | **VERIFY** | Check test results |

**No code changes needed** - the screening system automatically detects new rubrics via the mapping file.

---

## Best Practices

### ✅ DO:
- **Start with reference candidates** - Easier to calibrate with real examples
- **Adapt existing rubrics** - Don't reinvent the wheel, copy structure from similar roles
- **Test thoroughly** - Verify with 3+ candidates before rolling out
- **Document calibration** - Add "Evaluation Principles" section explaining target scores
- **Be specific about company tiers** - List actual company names (e.g., "Athena, TaskUs, Boldly")
- **Balance bucket weights** - Avoid over-weighting one skill (like Mandarin in early EPP versions)

### ❌ DON'T:
- **Don't guess at scoring** - Calculate manually with reference candidate first
- **Don't over-weight optional skills** - Nice-to-haves shouldn't dominate score
- **Don't skip testing** - Always test before using in production
- **Don't forget documentation** - Future you will thank current you
- **Don't make thresholds too strict** - Most roles: Experience ≥8-10, Skills ≥5-10, Communication ≥2

---

## Troubleshooting

### Problem: Score too high (reference candidate scores >90)
**Solution:**
- Increase max values in buckets where they maxed out
- Reduce points for "nice-to-have" criteria
- Ensure thresholds are appropriate for role seniority

### Problem: Score too low (reference candidate scores <70)
**Solution:**
- Decrease max values in buckets where they scored low
- Increase points for their strong areas
- Check if thresholds are too strict

### Problem: Rubric not loading / using wrong rubric
**Solution:**
- Verify Opening ID format: `{number}-{CODE}` (e.g., `251007-CPL`)
- Check job-type-mapping.json has correct job code
- Verify rubric filename matches mapping exactly (case-sensitive)
- Check Notion Post relation is set correctly

### Problem: All candidates scoring similarly
**Solution:**
- Rubric may not be discriminating enough
- Add more granular scoring criteria
- Increase threshold requirements
- Check if max values are too high or too low

---

## Examples

### Example 1: CPL (Client Partnership Lead)

**Requirements:**
- 2+ years people management
- Operations Manager or senior EA background
- Client-facing leadership
- US/EU founder experience

**Key decisions:**
- **Priority: Brand names** - Athena, TaskUs = Tier 1 (3 points)
- **People management depth** - 150+ team = 3 points
- **No age override** - Not needed for leadership role
- **Target: 80-85** for Operations Manager with 10+ years at premium agencies

**Result:**
- Reference candidate (Shariebel): 84.03 ✅
- Rubric: `resume-scorer-cpl.md`
- Mapping: `"CPL": {"title": "Client Partnership Lead", "rubric": "resume-scorer-cpl.md"}`

### Example 2: EPP (Product Associate)

**Requirements:**
- Mandarin fluency (critical)
- eCommerce product coordination
- Vendor management
- China supplier experience

**Key decisions:**
- **Mandarin: 0-3 points** (initially 0-8, reduced after feedback)
- **eCommerce experience heavily weighted**
- **Age override: >36** caps at PROCEED WITH CAUTION
- **Target: 75-85** for product coordinator with 5+ years

**Result:**
- Reference candidate (LOW KAH WEI): 83.75 ✅
- Rubric: `resume-scorer-epp.md`
- Mapping: `"EPP": {"title": "EPP Product Associate", "rubric": "resume-scorer-epp.md"}`

---

## Version History

- **v1.0** (Feb 2026): Initial documentation of process
  - Based on implementations of EP, EPP, and CPL rubrics
  - Tested with Kimi screener (kimi-k2.5 thinking mode)
  - Calibrated with reference candidates scoring 75-85 range
