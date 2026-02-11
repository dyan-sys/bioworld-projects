# Jobstreet Format Guide

Rules for adapting a job description into Jobstreet posting format. Use Ally's EP-Jobstreet.md and EPP-Jobstreet.md as structural references.

## Platform Metadata Block

The post starts with a metadata block for the person filling out the Jobstreet form fields:

```
# Platform Metadata — Jobstreet

- Job title: {job title}
- Location: {city/region and country code, e.g., Metro Manila PH}
- Workplace option: {Fully remote / Hybrid / On-site}
- Work type: {Full-Time / Part-Time / Contract}
- Pay type: {Monthly / Hourly}
- Pay range (Currency): {USD / PHP / MYR}
- Pay range: {range, e.g., $1,000 - $1,200}
- Pay shown on ad: {Show range on the ad / Don't show}
```

**Notes:**
- Location should match Jobstreet's location format (city/region + country code)
- Pay range currency should match the target market (PHP for Philippines, MYR for Malaysia, USD for international)

## Job Summary

A single line shown in Jobstreet search results. Uses pipe-delimited highlights:

```
# Job Summary

{X} Active Openings | Hire by {date} | {Key selling point 1} | {Key selling point 2}
```

**Notes:**
- Keep it short — this is preview text in search results
- Front-load the most compelling details
- Separated from the post body by `---`

## Post Structure

After the Job Summary and `---` separator, the external post begins.

### Header Block

```
# EXTERNAL JOB POST

## {Job Title}

{emoji} {Employment Type} | Remote | Starting rate {salary range}
{optional: location/language requirements line}
{optional: hire-by date line}
```

**Notes:**
- The `# EXTERNAL JOB POST` header is a label for the person posting (not shown to candidates on Jobstreet)
- Use relevant emojis in the subheading line (e.g., `💼` for job details, `📍` for location, `🗓` for dates)
- Additional requirement lines (language, location preference) go here

### Hook Paragraph

1-2 short paragraphs right after the header, separated by `---`:

```
---

{Compelling 1-liner about the role — what makes it exciting}

{1 sentence about the ideal candidate profile}

---
```

### Content Sections

Sections use `##` markdown headings with emoji prefixes. Separated by `---` horizontal rules.

Standard section order:

| Section | Heading | Content |
|---------|---------|---------|
| About | `## ✨ About {Company}` | Company overview (2-3 short paragraphs) |
| The Role | `## 🧭 The Role` | Role summary (1-2 paragraphs, bold key phrases) |
| What You'll Do | `## 📋 What You'll Do` | Responsibilities (numbered groups or bullets) |
| What Success Looks Like | `## 📈 What Success Looks Like` (optional) | 30/60/90 day milestones |
| What We're Looking For | `## 🎯 What We're Looking For` | Requirements (bold category labels) |
| What You'll Get / Why You'll Love It | `## 💡 What You'll Get` | Benefits/perks |
| Job Details | `### 💼 JOB DETAILS` | Summary box (see below) |
| How to Apply | `### How to Apply` | Application instructions |

**Notes:**
- "What Success Looks Like" is optional — include if the source JD has milestone/onboarding content
- "What You'll Get" can also be "Why You'll Love Working With {Company}" — match the source JD's tone
- Section emojis: use them consistently but don't overdo it. One per heading.

### What You'll Do — Grouped Format

For roles with distinct responsibility areas, use numbered groups with bold titles:

```
## 📋 What You'll Do

1. **{Area 1}**
   - {Responsibility}
   - {Responsibility}
2. **{Area 2}**
   - {Responsibility}
   - {Responsibility}
```

For simpler roles, a flat bullet list works fine (like EP-Jobstreet.md).

### What We're Looking For — Labeled Format

Use bold category labels for requirements:

```
## 🎯 What We're Looking For

- **Language Skills:** {requirement}
- **Experience:** {requirement}
- **Operational Mindset:** {requirement}
- **Soft Skills:** {requirement}
```

### Job Details Box

A summary box near the bottom with key facts:

```
### 💼 JOB DETAILS

**Employment Type:** {Full-Time / Part-Time} ({hours} per week)

**Work Setup:** Remote / Work from Home

**Working Hours:** {schedule/timezone}

**Pay:** Starting at {salary range}
```

**Notes:**
- This is a quick-reference summary — information here should also appear in the body
- Separated by `---` above and below

### Application Section

```
### How to Apply

Click **Apply Now** on JobStreet.

Shortlisted candidates will be asked to complete a screening questionnaire by invitation only, including a short video introduction.
```

**Notes:**
- Jobstreet uses "Apply Now" button — do NOT include external submission URLs in the post body
- The "by invitation only" line sets expectations that not all applicants will be screened
- If the client has a different screening process, adapt the second line accordingly

### Closing Line

A motivational one-liner at the very end of the post:

```
---

If you {positive trait related to role} — this is your next big step.

Apply today and {call to action tied to the company's mission}.
```

## Formatting Rules

| Element | Jobstreet Convention |
|---------|---------------------|
| Section dividers | `---` horizontal rules |
| Section headings | `##` with emoji prefix (e.g., `## 🧭 The Role`) |
| Sub-sections | `###` (e.g., `### 💼 JOB DETAILS`) |
| Bullet lists | `- Item` (single dash) |
| Numbered lists | `1. Item` with `- Sub-item` indented |
| Bold text | `**text**` for emphasis (category labels, key phrases, role titles) |
| Emojis | One per section heading — use sparingly and consistently |
| Dashes in text | `--` (double dash) for em-dashes in prose |

## What NOT to Include

- No `[N]` numbered section headings (that's OLJ format)
- No em-dash `—` as section dividers (use `---`)
- No external submission URLs in the post body (Jobstreet uses its own Apply button)
- No "Applications sent outside this link will not be reviewed" gatekeeper text

## Transformation Checklist

When adapting a generic/improved JD to Jobstreet format:

1. Extract metadata fields and populate the Platform Metadata block
2. Write a Job Summary line for search results
3. Create the header block with job title, employment details, and hire-by date
4. Write 1-2 hook paragraphs
5. Map content sections into `##` emoji-headed structure
6. Add bold category labels to "What We're Looking For" items
7. Consider grouping "What You'll Do" by area if the role has distinct responsibility clusters
8. Add the Job Details summary box
9. Write the application section using "Click **Apply Now** on JobStreet"
10. Add a motivational closing line
11. Ensure `---` horizontal rules separate all major sections
12. Remove any OLJ-specific elements (external URLs, `[N]` headings, em-dash dividers)
