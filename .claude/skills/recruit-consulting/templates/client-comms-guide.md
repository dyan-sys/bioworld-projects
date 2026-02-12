# Client Communication Guide

How Ally communicates with clients about recruitment materials — voice, framing, and message templates.

## Voice & Tone

Trusted advisor meets collaborative partner. We've done the thinking; now we're inviting input.

- **Confident, not deferential.** We lead with a clear recommendation, then invite refinement. Never "just checking in" or "hope this helps."
- **Warm, not casual.** Professional but human. Address the person, not the company.
- **Brief, not sparse.** Every sentence earns its place. One line of context beats three paragraphs of preamble.
- **Action-oriented.** Every message makes it clear what the client should do next.

## Principles

1. **Always explain *why* briefly.** Frame rationale as observable behavior + benefit, not technical rules. "OLJ shows a preview of the first words, so this will help drive clicks" beats "OLJ ranks posts by keyword relevance in the opening lines."
2. **Make it easy to say yes.** Default to specific values they can confirm rather than open blanks they need to fill.
3. **Respect their time.** One message, one document link, clear next steps. No follow-up needed from us.
4. **Frame feedback as decisions, not homework.** "Does this compensation range work?" beats "Please review the compensation section."
5. **Show momentum.** End with what's coming next — the client should feel there's a plan beyond this single doc.

## Checklist Design Rules

- **Curate per-send, don't dump defaults.** Pick 2–3 items that actually need decisions *this round*. The `default_checklist` in client config is a menu to select from, not a list to paste wholesale.
- Each item should be **decision-framed with a mini-rationale** — explain *why* you're asking, not just *what*. ("Hiring timing — would you have a hire-by date in mind? Urgency tends to help drive applicant quality.")
- **Explicitly defer** items you're not asking about yet. ("We'll look at the form URL separately!") This sets expectations and keeps the checklist focused.
- Each checklist item = **one decision**. Don't bundle multiple questions into one bullet.

---

## Stage Templates

Templates use `{{variable}}` placeholders. The script parses each `## Stage: <intent>` section.

**Template notes:**
- No bold header line — the greeting *is* the opener. Skip intent labels like `*Initial Review — Client*`.
- The `{{summary}}` block should include rationale bullets (what we did + why).
- `{{checklist}}` is the curated 2–3 items for this round.
- `{{next_steps}}` is an optional line about what's deferred or coming next.

## Stage: initial-review

Hi {{client_name}} team :wave:

{{summary}}

:link: *Document:* {{notion_url}}

*We'd love your input on a few specifics:*
{{checklist}}

{{next_steps}}

## Stage: update

Hi {{client_name}} team :wave:

{{summary}}

:link: *Document:* {{notion_url}}

*A few things to confirm:*
{{checklist}}

{{next_steps}}

## Stage: final-approval

Hi {{client_name}} team :wave:

{{summary}}

:link: *Document:* {{notion_url}}

*Quick final checks:*
{{checklist}}

Once you're happy, a thumbs up in this thread and we'll go live.

## Stage: follow-up

Hey {{client_name}}! {{acknowledgment}}

{{blocker_context}}

{{pending_items}}

{{momentum}}

---

### Follow-up Design Rules

Follow-ups are **not** "just checking in." Every follow-up should:

1. **Acknowledge progress** — reference what the client already gave you. Show you're tracking.
2. **Name the blocker clearly** — explain *why* you need these items (e.g., "Before I can finalize X and get Y to you...").
3. **Keep it to 2-4 specific items** — numbered, decision-framed, with enough context to answer without re-reading the doc.
4. **Show momentum** — end with what happens once they respond ("Once I have those three, I can finalize the OLJ post + get the Jobstreet JD over to you right away").
5. **Tag the right people** — if the primary contact isn't responding, loop in others who were asked to review.

**Tone:**
- Confident, not nagging. You're keeping the project moving, not chasing.
- Lead with gratitude for what they *did* respond to.
- Frame the ask as "quick confirms" not "outstanding items."

**When NOT to follow up:**
- Less than 2 business days since last send (unless urgent)
- Client said they'd get back to you at a specific time (wait for that)
- You're about to send new deliverables anyway (bundle the ask)
