# Job Description Analysis Framework

When analyzing a JD for a CS agent role, evaluate across 4 dimensions:

## 1. Clarity & Structure (0-10)

**What to look for:**
- Is the role clearly defined? (What they'll do day-to-day)
- Are responsibilities specific and measurable?
- Is career progression mentioned?
- Is the reporting structure clear?
- Are success metrics or performance expectations stated?

**Red flags:**
- Vague language ("various duties", "other tasks as assigned")
- No clear scope or boundaries
- Contradictory requirements
- Wall of text with no structure
- Missing key context (team size, tools used, customer segment)

**Scoring guide:**
- 8-10: Crystal clear role definition, specific responsibilities, measurable outcomes
- 5-7: Generally clear but some vagueness, missing some context
- 2-4: Significant ambiguity, hard to understand what the job actually entails
- 0-1: Extremely vague or confusing

## 2. Candidate Sell (0-10)

**What to look for:**
- Does it excite strong candidates?
- Are benefits/perks compelling and specific?
- Is company culture/mission evident?
- Does it balance "what you'll do" with "what we offer"?
- Is there a compelling reason to apply beyond the paycheck?

**Red flags:**
- All "you will" with no "we offer"
- Generic benefits ("competitive salary", "great team")
- No mention of growth opportunities
- Transactional tone (just a task list)
- No company story or mission

**Scoring guide:**
- 8-10: Compelling narrative, specific benefits, clear value proposition
- 5-7: Some sell elements but could be stronger, somewhat generic
- 2-4: Mostly demands with little sell, uninspiring
- 0-1: No attempt to attract candidates, pure task list

## 3. Requirements Calibration (0-10)

**What to look for:**
- Are requirements realistic for the role level?
- Any unrealistic combos (entry-level + 5 years experience)?
- Is compensation range appropriate for requirements?
- Are "must-haves" truly essential vs "nice-to-haves"?
- Do requirements align with CS competency framework for the tier?

**Red flags:**
- Too many "must-haves" (kitchen sink requirements)
- Unrealistic experience expectations for role level
- Requirements that contradict each other
- No distinction between essential and preferred qualifications
- Compensation misaligned with requirements

**Scoring guide:**
- 8-10: Well-calibrated requirements, clear must-haves vs nice-to-haves, realistic expectations
- 5-7: Mostly reasonable but some overreach or unclear priorities
- 2-4: Significant calibration issues, unrealistic expectations
- 0-1: Completely unrealistic or contradictory requirements

## 4. Inclusive Language (0-10)

**What to look for:**
- Gender-neutral phrasing?
- Avoids unnecessary barriers to diverse backgrounds?
- Accessible language (no jargon without explanation)?
- Focuses on competencies not culture fit?
- Welcoming tone?

**Red flags:**
- Coded language ("rockstar", "ninja", "culture fit", "digital native")
- Aggressive or masculine tone ("crush goals", "dominate")
- Age bias ("recent grad", "digital native")
- Unnecessary degree requirements
- Cultural assumptions (US-centric holidays, idioms)

**Scoring guide:**
- 8-10: Consistently inclusive, welcoming to diverse candidates
- 5-7: Generally okay but some improvements possible
- 2-4: Multiple problematic phrases or barriers
- 0-1: Exclusionary language throughout

## Reference: CS Competency Framework

Always check requirements against the CS competency framework (`cs-competency-framework.json`) to ensure expectations align with the role tier:

- **Tier 1 Support**: Entry-level CS, focus on communication and basic troubleshooting
- **Tier 2 Technical**: Mid-level CS, technical depth and cross-functional collaboration
- **Account Management**: Senior CS, strategic thinking and relationship management

## Output Structure

Save analysis as JSON with this structure:

```json
{
  "client": "client-slug",
  "material_type": "job_description",
  "round": null,
  "date": "YYYY-MM-DD",
  "scores": {
    "clarity": 0-10,
    "sell": 0-10,
    "requirements": 0-10,
    "inclusive_language": 0-10
  },
  "strengths": ["specific strength 1", "specific strength 2"],
  "issues": [
    {
      "severity": "high|medium|low",
      "category": "clarity|sell|requirements|inclusive",
      "detail": "specific issue with line reference if possible"
    }
  ],
  "recommendations": [
    {
      "priority": "must-fix|should-fix|nice-to-have",
      "action": "specific actionable recommendation"
    }
  ],
  "sample_improved_questions": [],
  "overall_assessment": "2-3 sentence summary"
}
```

## Analysis Tips

1. **Be specific**: Reference exact phrases or sections when noting issues
2. **Be actionable**: Recommendations should be concrete rewrites, not vague suggestions
3. **Be balanced**: Note strengths as well as issues — lead with strengths
4. **Be calibrated**: Use the full 0-10 scale, don't cluster scores in middle
5. **Check competency alignment**: Explicitly reference which competencies are well/poorly addressed

## Document Formatting

When writing analysis documents, follow the tone and visual hierarchy conventions in SKILL.md:
- Supportive tone — validate what works before suggesting improvements
- 🟢 High impact / 🟡 Medium impact / ⚪ Nice-to-have color coding
- 💡 prefix on recommendations
- Emoji-coded H2 headings (🔍, ✅, 🔧, 📊, 📦)
- "Areas for Improvement" not "Key Issues"
- "Must-do / Should-do / Nice-to-have" not "Must-fix / Should-fix"
