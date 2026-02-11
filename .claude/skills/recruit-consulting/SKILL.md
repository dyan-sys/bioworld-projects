# Client Recruitment Consulting Skill

## Overview

This skill enables AI-assisted review and improvement of client recruitment materials (job descriptions and interview templates) for CS agent roles. It provides a structured, repeatable process for consulting work with full audit trails.

## When to Use

**Trigger phrases:**
- "Review this job description"
- "Analyze this interview template"
- "Improve this JD for [client]"
- "Evaluate CS recruitment materials"

## Quick Start

```bash
# 1. Create client workspace
mkdir -p local-data/client-consulting/{client-slug}/{jd,interviews}

# 2. Save original material
# Paste JD or interview template into:
#   - local-data/client-consulting/{client-slug}/jd/original.md
#   - local-data/client-consulting/{client-slug}/interviews/r1-original.md

# 3. Ask Claude to analyze
"Analyze the JD for {client-slug}"
"Analyze the R1 interview template for {client-slug}"

# 4. Claude will:
#    - Read analysis framework
#    - Evaluate the material
#    - Save structured analysis JSON
#    - Provide verbal summary with recommendations

# 5. Improve and save
#    Edit the material based on recommendations, save to:
#    - local-data/client-consulting/{client-slug}/jd/improved.md
```

## Process Guide

### Phase 1: Setup Client Workspace

When a new client consulting project starts:

1. Create client directory:
   ```bash
   mkdir -p local-data/client-consulting/{client-slug}/{jd,interviews}
   ```

2. Use lowercase kebab-case for client slug (e.g., `acme-corp`, `startup-xyz`)

### Phase 2: Ingest Original Materials

Save client's original materials:

**Job Description:**
```
local-data/client-consulting/{client-slug}/jd/original.md
```

**Interview Templates:**
```
local-data/client-consulting/{client-slug}/interviews/r1-original.md
local-data/client-consulting/{client-slug}/interviews/r2-original.md
```

You can paste content directly or provide file paths for Claude to read.

### Phase 3: Analyze Materials

**For Job Descriptions:**

User says: `"Analyze the JD for {client-slug}"`

Claude will:
1. Read `templates/jd-analysis-framework.md`
2. Read `templates/cs-competency-framework.json`
3. Read the original JD
4. Evaluate across 4 dimensions:
   - Clarity & Structure
   - Candidate Sell
   - Requirements Calibration
   - Inclusive Language
5. Save analysis to `{client-slug}/jd/analysis.json`
6. Provide verbal summary with specific recommendations

**For Interview Templates:**

User says: `"Analyze the R1 interview template for {client-slug}"`

Claude will:
1. Read `templates/interview-analysis-framework.md`
2. Read `templates/cs-competency-framework.json`
3. Read the original template
4. Evaluate across 4 dimensions:
   - Question Quality
   - Rubric Alignment
   - Candidate Experience
   - Depth & Coverage
5. Save analysis to `{client-slug}/interviews/r1-analysis.json`
6. Provide verbal summary with improved question samples

### Phase 4: Improve Materials

Based on analysis recommendations:

**Option A: Manual editing**
- User edits the material in their preferred editor
- Save improved version to `improved.md` in the same directory

**Option B: Claude-assisted**
- User says: `"Help me rewrite the requirements section"`
- Claude provides specific rewrite suggestions
- User can ask for drafts or revisions

**Result:**
- `{client-slug}/jd/improved.md`
- `{client-slug}/interviews/r1-improved.md`

### Phase 5: Review and Iterate

Compare before/after:
- Original and improved versions side-by-side
- Use analysis JSON to verify all issues addressed
- Iterate if needed (save new versions with timestamps)

## Directory Structure

```
local-data/client-consulting/
└── {client-slug}/
    ├── jd/
    │   ├── original.md              # Client's original JD
    │   ├── analysis.json            # Claude's analysis
    │   └── improved.md              # Improved version
    └── interviews/
        ├── r1-original.md           # Original R1 template
        ├── r1-analysis.json         # Claude's R1 analysis
        ├── r1-improved.md           # Improved R1
        ├── r2-original.md           # Original R2 template
        ├── r2-analysis.json         # Claude's R2 analysis
        └── r2-improved.md           # Improved R2
```

## Analysis Dimensions

### Job Description Analysis

**1. Clarity & Structure (0-10)**
- Role definition clarity
- Specific, measurable responsibilities
- Career progression mentioned
- Clear success metrics

**2. Candidate Sell (0-10)**
- Compelling value proposition
- Specific benefits and perks
- Company culture/mission evident
- Balance of "you will" vs "we offer"

**3. Requirements Calibration (0-10)**
- Realistic expectations for role level
- Must-haves vs nice-to-haves clear
- Aligned with CS competency framework
- Compensation appropriate for requirements

**4. Inclusive Language (0-10)**
- Gender-neutral phrasing
- Avoids unnecessary barriers
- No coded language ("rockstar", "ninja")
- Accessible to diverse backgrounds

### Interview Template Analysis

**1. Question Quality (0-10)**
- Behavioral questions (STAR method)
- Open-ended, elicit specific examples
- Good follow-up guidance
- Avoids hypotheticals and leading questions

**2. Rubric Alignment (0-10)**
- Clear scoring rubric provided
- Competencies map to CS framework
- Objective evaluation criteria
- Multiple interviewers can score consistently

**3. Candidate Experience (0-10)**
- Logical flow, respectful of time
- Gives candidates space to showcase strengths
- Warm-up/rapport building
- Avoids bias traps

**4. Depth & Coverage (0-10)**
- Appropriate depth for round (R1=breadth, R2=depth)
- All key CS competencies covered
- Technical validation included
- Balanced past behavior + technical skills

## CS Competency Framework

All analysis references 4 core CS competencies across 3 tiers:

| Competency | Tier 1 Support | Tier 2 Technical | Account Management |
|------------|----------------|------------------|-------------------|
| Customer Communication | Clear communication, empathy, active listening | Explain complex issues simply, escalation judgment | Consultative communication, relationship building, upselling |
| Problem Solving | Troubleshooting frameworks, resourcefulness, pattern recognition | Root cause analysis, cross-functional collaboration, documentation | Strategic thinking, proactive prevention, data-driven decisions |
| Technical Aptitude | Basic software navigation, ticketing systems, knowledge base | API basics, logs interpretation, tool administration | Product expertise, integration understanding, technical scoping |
| Ownership & Initiative | Follow-through, accountability, proactive updates | Process improvement, knowledge sharing, mentorship | Strategic account planning, growth initiatives, executive presence |

## Analysis Output Format

All analysis is saved as JSON with this structure:

```json
{
  "client": "client-slug",
  "material_type": "job_description | interview_template",
  "round": null or 1 or 2,
  "date": "YYYY-MM-DD",
  "scores": {
    "dimension1": 7,
    "dimension2": 5,
    "dimension3": 8,
    "dimension4": 6
  },
  "strengths": [
    "Clear role definition with specific responsibilities",
    "Good technical requirements for Tier 2 role"
  ],
  "issues": [
    {
      "severity": "high",
      "category": "sell",
      "detail": "No mention of benefits or growth opportunities in entire JD"
    },
    {
      "severity": "medium",
      "category": "inclusive",
      "detail": "Uses 'rockstar' and 'culture fit' (lines 12, 34)"
    }
  ],
  "recommendations": [
    {
      "priority": "must-fix",
      "action": "Add a 'What We Offer' section with specific benefits, growth paths, and company mission"
    },
    {
      "priority": "should-fix",
      "action": "Replace 'rockstar' with 'highly skilled' and remove 'culture fit' language"
    }
  ],
  "sample_improved_questions": [
    "Tell me about a time when you had to troubleshoot a technical issue with limited information. What was your approach? (STAR format)",
    "Describe a situation where you had to explain a complex technical problem to a non-technical stakeholder. How did you ensure they understood?"
  ],
  "overall_assessment": "This JD has strong technical requirements and clear role definition (7/10 clarity) but significantly undersells the opportunity (5/10 sell) and has some inclusive language issues (6/10). Primary recommendation is to add a compelling 'What We Offer' section and remove coded language like 'rockstar'."
}
```

## Document Tone & Framing

When writing client-facing analysis documents (analysis.md, reviews, recommendations):

**Tone:**
- **Supportive and encouraging**, not critical. We're a consulting partner, not an auditor.
- **Validate first, then suggest.** Every section about improvements should acknowledge what the client already did well before recommending changes.
- Use "key challenge" or "key missing piece" — never "core issue" or "main problem."
- Use "Areas for Improvement" — never "Key Issues" or "Problems."
- Frame recommendations as building on their work: "The next step is..." not "You need to fix..."
- Close with collaboration language: "we'd love your feedback" / "starting points for discussion."

**Visual Hierarchy:**
- Add emojis to H2 section headings for scannability (e.g., 🔍 Executive Summary, ✅ What Works Well, 🔧 Areas for Improvement, 📊 Summary, 📦 Deliverables).
- Color-code impact levels with emoji dots:
  - 🟢 **High impact** (green = go do this)
  - 🟡 **Medium impact** (yellow = should do)
  - ⚪ **Nice-to-have** (grey = low priority)
- Prefix all recommendations with 💡 to visually separate "what is" from "what to do."
- Use the same color coding in summary tables.
- Priority labels: "Must-do" / "Should-do" / "Nice-to-have" (not "Must-fix" / "Should-fix").

**Structure pattern for each improvement item:**
1. H3 with the topic name
2. Color-coded impact level (🟢/🟡/⚪)
3. What the client already did well (validate)
4. What's missing or could be stronger
5. 💡 Recommendation with specific action

## Tips for Effective Analysis

1. **Be Specific**: Reference exact lines or phrases when noting issues
2. **Be Actionable**: Recommendations should be concrete, not vague ("Add X" vs "Could be better")
3. **Be Balanced**: Highlight strengths as well as issues — lead with strengths
4. **Use Full Scale**: Scores from 0-10, don't cluster around 5-7
5. **Check Competency Alignment**: Explicitly map requirements/questions to CS framework
6. **Consider Role Tier**: Expectations differ for Tier 1 vs Tier 2 vs Account Management

## Example Usage

```
User: "I need to review a JD for a new client, TechCorp"

You: "I'll help you analyze TechCorp's JD. First, let's set up the workspace."
     [Creates local-data/client-consulting/techcorp/jd/ directory]
     "Please paste the JD content or provide the file path."

User: [Pastes JD content]

You: [Reads jd-analysis-framework.md]
     [Reads cs-competency-framework.json]
     [Analyzes the JD]
     [Saves techcorp/jd/analysis.json]

     "Here's my analysis of TechCorp's JD:

     **Scores:**
     - Clarity: 8/10 - Very clear role definition
     - Sell: 4/10 - Weak value proposition
     - Requirements: 7/10 - Mostly calibrated but some overreach
     - Inclusive: 6/10 - Some problematic language

     **Key Issues:**
     - No benefits section (HIGH priority)
     - Uses 'rockstar' and 'ninja' (MEDIUM priority)
     - Asks for 5+ years for entry-level role (HIGH priority)

     **Recommendations:**
     1. MUST-FIX: Add 'What We Offer' section with growth paths, specific benefits
     2. MUST-FIX: Recalibrate to 2-3 years experience for this Tier 1 role
     3. SHOULD-FIX: Replace coded language with inclusive terms

     I've saved the full analysis to local-data/client-consulting/techcorp/jd/analysis.json"

User: "Help me rewrite the requirements section"

You: [Provides specific rewrite with proper calibration]
```

## Integration with Existing Skills

This skill complements existing Ally OS recruitment skills:

- **screen-resume**: Once you've improved client JDs, use screen-resume to evaluate candidates against new criteria
- **update-resume-screener**: Create custom rubrics for client roles
- **invite-candidates**: Use improved interview templates when inviting candidates

## Future Enhancements (Out of Scope)

- Notion integration for client project tracking
- Client feedback loop (track which recommendations worked)
- Automated before/after comparison reports
- Template library (successful improved versions)
- Multi-role support beyond CS (SDR, AM, etc.)

## Requirements

- No special dependencies (uses Claude Code directly)
- No API keys required
- Files stored locally in `local-data/client-consulting/`

## Related Files

**Analysis Frameworks:**
- `templates/jd-analysis-framework.md` - Job description evaluation criteria
- `templates/interview-analysis-framework.md` - Interview template evaluation criteria

**Reference Data:**
- `templates/cs-competency-framework.json` - CS role competencies by tier
- `templates/analysis-template.json` - JSON structure reference

## Support

For questions or improvements to this skill, reference the skill directory:
`.claude/skills/recruit-consulting/`
