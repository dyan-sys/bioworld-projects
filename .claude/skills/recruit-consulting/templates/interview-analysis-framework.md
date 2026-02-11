# Interview Template Analysis Framework

When analyzing an interview template (R1 or R2), evaluate across 4 dimensions:

## 1. Question Quality (0-10)

**What to look for:**
- Do questions elicit specific, behavioral answers?
- Good mix of technical, situational, cultural fit?
- Open-ended questions that require storytelling?
- Follow-up question guidance?
- Questions probe for specifics (STAR method: Situation, Task, Action, Result)?

**Red flags:**
- Yes/no questions without follow-ups
- Leading questions ("Don't you think that...")
- Purely hypothetical ("What would you do if...") without context
- Questions with obvious "right answers"
- No probing for specific examples

**Scoring guide:**
- 8-10: Behavioral questions with clear follow-up guidance, elicit specific examples
- 5-7: Mostly open-ended but some weak questions or missing follow-ups
- 2-4: Many hypothetical or closed questions, limited depth
- 0-1: Mostly yes/no or leading questions

## 2. Rubric Alignment (0-10)

**What to look for:**
- Is there a clear scoring rubric?
- Are competencies tied to role requirements and CS framework?
- Can multiple interviewers score consistently?
- Are answers objectively evaluable?
- Clear definitions of strong/weak answers?

**Red flags:**
- No rubric at all
- Subjective criteria ("good communication", "culture fit")
- No scoring guidance per question
- Rubric doesn't map to CS competency framework
- Different interviewers would score wildly differently

**Scoring guide:**
- 8-10: Detailed rubric with specific scoring criteria per competency
- 5-7: Basic rubric but some subjective elements
- 2-4: Minimal rubric or mostly subjective
- 0-1: No rubric or entirely subjective

## 3. Candidate Experience (0-10)

**What to look for:**
- Is the flow logical and respectful of candidate time?
- Does it give candidates space to showcase their strengths?
- Clear time expectations?
- Warm-up/rapport building included?
- Avoids bias traps (questions that favor certain backgrounds)?
- Candidates leave feeling fairly evaluated?

**Red flags:**
- Interrogation style (no rapport building)
- Trick questions or gotchas
- Excessive length (>60min for R1, >90min for R2)
- Questions assume specific background (US education, tech company experience)
- No time for candidate questions
- Abrupt or cold tone

**Scoring guide:**
- 8-10: Well-paced, respectful, gives candidates room to shine
- 5-7: Adequate but could be more welcoming or structured
- 2-4: Poor experience, too long, or overly aggressive
- 0-1: Hostile or disrespectful interview design

## 4. Depth & Coverage (0-10)

**What to look for:**
- Does it probe deep enough for the round?
  - R1: Breadth across competencies, basic fit screening
  - R2: Depth on 2-3 key competencies, technical validation
- Are key CS competencies covered (communication, problem-solving, technical aptitude, ownership)?
- Appropriate depth for role tier (Tier 1 vs Tier 2 vs Account Mgmt)?
- Balance of past behavior and technical skills?

**Red flags:**
- R1 going too deep (save for R2)
- R2 staying too surface-level
- Missing critical competencies for the role
- All questions on one competency (no coverage balance)
- No technical validation for technical roles

**Scoring guide:**
- 8-10: Appropriate depth for round, all key competencies covered
- 5-7: Mostly good coverage but some gaps or depth issues
- 2-4: Significant gaps or wrong depth for round
- 0-1: Missing critical areas or entirely wrong scope

## Reference: CS Competency Framework

Map interview questions to the CS competency framework (`cs-competency-framework.json`):

- **Customer Communication**: Empathy, clarity, active listening
- **Problem Solving**: Troubleshooting, resourcefulness, analytical thinking
- **Technical Aptitude**: Tool proficiency, technical learning, system thinking
- **Ownership & Initiative**: Accountability, proactiveness, follow-through

Ensure each competency is addressed with at least one behavioral question.

## Round-Specific Guidelines

**Round 1 (Breadth Screening)**
- Goal: Filter for basic fit across all competencies
- Duration: 30-45 minutes
- Coverage: All 4 CS competencies at surface level
- Technical: Basic validation (can use tools, navigate systems)
- Output: Go/no-go decision with specific concerns flagged

**Round 2 (Depth Validation)**
- Goal: Deep dive on 2-3 critical competencies for the role
- Duration: 60-90 minutes
- Coverage: Deep behavioral + technical validation
- Technical: Hands-on scenarios, troubleshooting simulations
- Output: Hire/no-hire with detailed competency assessment

## Output Structure

Save analysis as JSON with this structure:

```json
{
  "client": "client-slug",
  "material_type": "interview_template",
  "round": 1 or 2,
  "date": "YYYY-MM-DD",
  "scores": {
    "question_quality": 0-10,
    "rubric_alignment": 0-10,
    "candidate_experience": 0-10,
    "depth_coverage": 0-10
  },
  "strengths": ["specific strength 1", "specific strength 2"],
  "issues": [
    {
      "severity": "high|medium|low",
      "category": "questions|rubric|experience|coverage",
      "detail": "specific issue with question reference if possible"
    }
  ],
  "recommendations": [
    {
      "priority": "must-fix|should-fix|nice-to-have",
      "action": "specific actionable recommendation"
    }
  ],
  "sample_improved_questions": [
    "Example improved question 1",
    "Example improved question 2",
    "Example improved question 3"
  ],
  "overall_assessment": "2-3 sentence summary"
}
```

## Analysis Tips

1. **Map to competencies**: Explicitly note which CS competencies each question addresses
2. **Provide examples**: Include 2-3 sample improved questions in your recommendations
3. **Check round appropriateness**: R1 should be broad, R2 should be deep
4. **Evaluate rubric usability**: Could a different interviewer score consistently?
5. **Consider candidate perspective**: Would this feel like a fair evaluation?
6. **Balance technical and behavioral**: CS roles need both, ensure coverage
