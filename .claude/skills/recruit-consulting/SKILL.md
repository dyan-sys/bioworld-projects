# Client Recruitment Consulting Skill

## Overview

This skill enables AI-assisted review, improvement, and delivery of client recruitment materials (job descriptions and interview templates) for CS agent roles. The primary working surface is Notion, with local files kept as synced backups.

## When to Use

**Trigger phrases:**
- "Review this job description"
- "Improve this JD for [client]"
- "Work on the interview templates for [client]"
- "Prepare deliverables for [client]"
- "Adapt the intake form blurb for [client]"

## Workflow

The workflow is iterative and Notion-first:

```
Ingest → Review & Improve (iterative) → Deliver (Notion + Slack)
```

There is no mandatory formal scoring phase. The value is in improving the materials and delivering them to the client — not in producing analysis artifacts.

## Quick Start

```bash
# 1. Create client workspace (local backup)
mkdir -p local-data/client-consulting/{client-slug}/{jd,interviews}

# 2. Save original material locally
#   - local-data/client-consulting/{client-slug}/jd/original.md
#   - local-data/client-consulting/{client-slug}/interviews/r1-original.md

# 3. Work in Notion (primary surface)
#    Create/edit pages directly in the client's shared Notion space
#    Sync local files periodically as backups

# 4. Deliver
#    Move docs to EXT page, draft Slack update, send via webhook
```

## Process Guide

### Phase 1: Setup

1. Create local client directory:
   ```bash
   mkdir -p local-data/client-consulting/{client-slug}/{jd,interviews}
   ```
2. Use lowercase kebab-case for client slug (e.g., `care-n-bloom`, `acme-corp`)
3. Save original materials locally as `original.md` for the audit trail
4. Set up the shared Notion space (typically an EXT page with "Outputs from Ally" and "Inputs from Client" sections)

### Phase 2: Review & Improve (Iterative)

This is the core loop. Work directly in Notion, responding to user feedback in real time.

**For Job Descriptions:**
- Review for clarity, candidate sell, requirements calibration, inclusive language
- Run a **platform discoverability check** — does the job title match how candidates actually search on the target platform? (see Platform Checks below)
- Improve structure, copy, and framing
- Apply platform-specific formatting via the `adapt-client-jd` skill when posting to OLJ, Jobstreet, etc.

**For Interview Templates:**
- Review question quality, rubric alignment, candidate experience, depth & coverage
- Split monolithic interview guides into structured rounds (R1 screening, R2 deep dive)
- **Cross-pollinate from Ally's own templates** — adapt proven questions and structures from Ally's internal interview templates for client use (e.g., growth/agency questions, live case simulations)
- Add scoring rubrics (BE/ME/AE/EE framework), interviewer scripts, and priority ordering
- Ensure each round has a clear purpose: R1 = rule-out (validate non-negotiables), R2 = rule-in (validate depth through simulation)

**Iterative refinement pattern:**
- User reviews in Notion, gives feedback (move section, add question, change format, remove column)
- Claude makes the change directly in Notion
- Repeat until the user is satisfied
- Sync to local files when a stable version is reached

### Phase 3: Deliver

Once materials are ready:

1. **Move documents to the EXT Notion page** — use `notion-move-pages` to physically nest docs under "Outputs from Ally" (not just inline mention links)
2. **Draft a Slack update** for the client team channel — summarize deliverables, include Notion links, invite feedback
3. **Send via webhook** — typically `SLACK_WEBHOOK_URL_JARVIS` for #ally-jarvis

**Slack message guidelines:**
- Lead with what was delivered, not what was analyzed
- Use Slack link format: `<https://notion.so/page-id|Document Title>`
- Close with a specific ask (e.g., "feedback on the assessment strategy so we can align before finalizing templates")
- Keep it warm and collaborative, not formal

## Candidate Intake Form Blurb

When setting up application forms for a client role, adapt the standard Ally intake blurb for the client's brand. The template and adaptation guide are in `templates/candidate-intake-form-blurb.md`.

**Key steps:**
1. Read the template for the default Ally-branded blurb
2. Read the client's improved JD (for company positioning and role hook)
3. Replace Ally branding with the client's company name and identity
4. Add the specific role title and a one-line company positioning
5. Include a brief role hook that signals the type of candidate they're looking for
6. Keep the standard form/CV/video instructions as-is

## Platform Discoverability Checks

When reviewing JDs for platform posting (OLJ, Jobstreet), assess whether the job title matches candidate search behavior:

- Filipino CS candidates on OLJ/Jobstreet search for: "Customer Support Specialist", "Customer Service Representative", "Email Support", "Chat Support"
- Emerging terms like "Customer Experience Specialist" may not match search patterns in the PH remote work market
- OLJ category dropdown is "Customer Service" — title should work within that frame
- Reference the `adapt-client-jd` skill for platform-specific formatting rules

Flag title mismatches as a recommendation — don't change unilaterally without client confirmation.

## Notion as Primary Working Surface

**Notion is the source of truth** for client-facing materials. Local files are synced backups.

Key Notion operations used in this skill:
- `notion-fetch` — read page content
- `notion-update-page` with `replace_content` — full page rewrites (best for fixing formatting across a page)
- `notion-update-page` with `replace_content_range` — targeted edits (use unique start/end snippets)
- `notion-update-page` with `insert_content_after` — adding new sections
- `notion-move-pages` — physically moving docs between parent pages (e.g., Internal → EXT)
- `notion-create-pages` — creating new pages under a parent

**Notion formatting tips:**
- Use `<table>` format for tables (not pipe tables) — pipe tables render but `<table>` gives better control
- Use `<callout>` for highlighted blocks
- Use `<mention-page>` for inline clickable links to other pages
- Use `<page>` tags in content to reference child pages (required when doing `replace_content` to avoid accidental deletion of nested pages)

## Cross-Pollination from Ally Templates

Ally's own interview templates are a valuable source for client work:

- **R1 growth/agency questions** — Ally's EP R1 includes self-driven growth questions that adapt well for client screening rounds
- **Scoring frameworks** — BE/ME/AE/EE rubrics, competency tables, priority ordering
- **Interview structure** — segment timing, opener scripts, closing scripts, post-interview checklists

When adapting, adjust the competencies and scenarios to match the client's role context — don't copy verbatim.

## Document Tone & Framing

When writing client-facing documents (analysis docs, reviews, recommendations):

**Tone:**
- **Supportive and encouraging**, not critical. We're a consulting partner, not an auditor.
- **Validate first, then suggest.** Acknowledge what the client already did well before recommending changes.
- Use "key challenge" or "key missing piece" — never "core issue" or "main problem."
- Use "Areas for Improvement" — never "Key Issues" or "Problems."
- Frame recommendations as building on their work: "The next step is..." not "You need to fix..."
- Close with collaboration language: "we'd love your feedback" / "starting points for discussion."

**Visual Hierarchy:**
- Add emojis to H2 section headings for scannability (e.g., 🔍 Executive Summary, ✅ What Works Well, 🔧 Areas for Improvement, 📊 Summary, 📦 Deliverables).
- Color-code impact levels:
  - 🟢 **High impact** (green = go do this)
  - 🟡 **Medium impact** (yellow = should do)
  - ⚪ **Nice-to-have** (grey = low priority)
- Prefix recommendations with 💡 to visually separate "what is" from "what to do."
- Priority labels: "Must-do" / "Should-do" / "Nice-to-have"

**Structure pattern for each improvement item:**
1. H3 with the topic name
2. Color-coded impact level (🟢/🟡/⚪)
3. What the client already did well (validate)
4. What's missing or could be stronger
5. 💡 Recommendation with specific action

## CS Competency Framework

All analysis references 4 core CS competencies across 3 tiers:

| Competency | Tier 1 Support | Tier 2 Technical | Account Management |
|------------|----------------|------------------|-------------------|
| Customer Communication | Clear communication, empathy, active listening | Explain complex issues simply, escalation judgment | Consultative communication, relationship building, upselling |
| Problem Solving | Troubleshooting frameworks, resourcefulness, pattern recognition | Root cause analysis, cross-functional collaboration, documentation | Strategic thinking, proactive prevention, data-driven decisions |
| Technical Aptitude | Basic software navigation, ticketing systems, knowledge base | API basics, logs interpretation, tool administration | Product expertise, integration understanding, technical scoping |
| Ownership & Initiative | Follow-through, accountability, proactive updates | Process improvement, knowledge sharing, mentorship | Strategic account planning, growth initiatives, executive presence |

## Directory Structure

```
local-data/client-consulting/
└── {client-slug}/
    ├── jd/
    │   ├── original.md              # Client's original JD
    │   └── improved.md              # Improved version (synced from Notion)
    └── interviews/
        ├── r1-original.md           # Original R1 template
        ├── r1-improved.md           # Improved R1 (synced from Notion)
        ├── r2-original.md           # Original R2 template
        └── r2-improved.md           # Improved R2 (synced from Notion)
```

## Integration with Existing Skills

- **adapt-client-jd**: Apply platform-specific formatting when posting JDs to OLJ, Jobstreet, etc.
- **screen-resume**: Once you've improved client JDs, use screen-resume to evaluate candidates against new criteria
- **update-resume-screener**: Create custom rubrics for client roles
- **invite-candidates**: Use improved interview templates when inviting candidates

## Requirements

- No special dependencies (uses Claude Code directly)
- Notion MCP tools for page editing and management
- Slack webhook for client delivery notifications
- Files stored locally in `local-data/client-consulting/` as backups

## Related Files

**Analysis Frameworks (optional, for formal reviews):**
- `templates/jd-analysis-framework.md` - Job description evaluation criteria
- `templates/interview-analysis-framework.md` - Interview template evaluation criteria

**Reference Data:**
- `templates/cs-competency-framework.json` - CS role competencies by tier

## Support

For questions or improvements to this skill, reference the skill directory:
`.claude/skills/recruit-consulting/`
