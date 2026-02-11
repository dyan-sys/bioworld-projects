# OLJ (OnlineJobs.ph) Format Guide

Rules for adapting a job description into OnlineJobs.ph posting format. Use Ally's EP-OLJ.md as the structural reference.

## Platform Metadata Block

The post starts with a metadata block for the person filling out the OLJ form fields:

```
# Platform Metadata — OnlineJobs.ph

- Job title: {job title}
- Category: {category, e.g., Virtual Assistant, Customer Service}
- Salary: {salary range}
- Employment type: {Full-Time / Part-Time / Contract}
- Schedule: {working hours / timezone}
- Location: Remote ({country})
```

**Notes:**
- Category should match OLJ's dropdown options (Virtual Assistant, Customer Service, etc.)
- Salary uses the range shown to candidates
- Location is always "Remote" with the target country in parentheses

## Post Structure

After the metadata block, a `---` horizontal rule separates metadata from the post body.

### Opening Banner

One line of pipe-delimited highlights:

```
Full Time | Remote | {X} Openings | Hire by {date} | {timezone}
```

### Hook Section

Separated by em-dash (`—`) dividers:

1. **Tagline** — One punchy question or statement targeting the ideal candidate
2. **Value pitch** — 1-2 short sentences on what makes this role compelling
3. **Application URL** — Direct link to the submission form (standalone line)

```
—

{Tagline — one question or statement}

{1-2 sentences on why this role is compelling}

{submission URL}

—
```

### Numbered Content Sections

All body sections use `[N]` numbered headings (not markdown `##`). Sections are separated by em-dash (`—`) dividers.

Standard section order:

| Section | Heading | Content |
|---------|---------|---------|
| [1] | About {Company} | Company overview (2-3 short paragraphs) |
| [2] | The Role | Role summary (2 short paragraphs) |
| [3] | What You'll Do | Bullet list of responsibilities |
| [4] | What We're Looking For | Bullet list of requirements |
| [5] | What You'll Get | Bullet list of benefits/perks |
| [6] | HOW TO APPLY | Application instructions with URL |
| [7] | OTHER OPEN POSITIONS (optional) | Cross-promotion |

**Notes:**
- Section [6] heading is ALL CAPS
- Section [7] is optional — include only if the client has other openings to promote

### Application Section ([6])

```
[6] HOW TO APPLY

Submit your application here:
{submission URL}

You will be asked to:

1. {Step 1, e.g., Upload your CV or LinkedIn profile}
2. {Step 2, e.g., Record a short Loom video (2-3 mins) covering:}
- {Sub-point}
- {Sub-point}

Applications sent outside this link will not be reviewed.
```

**Notes:**
- Always include the external submission URL
- List the specific steps candidates will be asked to complete
- Close with a gatekeeper line ("Applications sent outside this link will not be reviewed")
- If the client doesn't use an external form, adapt to "Apply via OnlineJobs.ph" with instructions

## Formatting Rules

| Element | OLJ Convention |
|---------|---------------|
| Section dividers | Em-dash `—` on its own line |
| Section headings | `[N] Heading Text` |
| Bullet lists | `- Item` (single dash) |
| Numbered lists | `1. Item` |
| Bold text | `**text**` (sparingly — mainly for role titles in [2]) |
| Horizontal rule | `---` only between metadata and post body |
| Emojis | **None** — OLJ posts do not use emojis |

## What NOT to Include

- No `##` markdown headings (use `[N]` format instead)
- No emoji section headings
- No "Job Summary" field (that's Jobstreet-specific)
- No "Job Details" summary box
- No "Click Apply Now on {platform}" — OLJ uses external URLs
- No `---` horizontal rules within the post body (use `—` dividers)

## Transformation Checklist

When adapting a generic/improved JD to OLJ format:

1. Extract metadata fields and populate the Platform Metadata block
2. Write a hook tagline specific to the role and target candidate
3. Map content sections into the `[N]` numbered structure
4. Convert any markdown headings to `[N]` format
5. Remove emojis from headings
6. Replace `---` dividers with `—` in the post body
7. Ensure the application section has the external URL and numbered steps
8. Check bullet lists use `- ` format (not `*` or `+`)
9. Verify section order follows the standard sequence
10. Remove any Jobstreet-specific elements (Job Summary, Job Details box)
