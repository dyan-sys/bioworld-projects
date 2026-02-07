---
name: update-job-posts
description: Trigger when user mentions creating job posts, updating job postings, publishing openings, or syncing openings to job posts
---

# Update Job Posts Skill

Automatically creates job post pages in the Job Posts DB for each Open opening in the Ally Openings DB. Creates one post per Post Channel (OLJ, Jobstreet, Facebook, Internal, etc.) with platform-specific content from templates. Templates support `{{variable}}` substitution for dynamic content.

## How It Works

1. Queries the Ally Openings DB for openings with Status = "Open"
2. For each opening, extracts metadata: prefix, job code, channels, job title, employment type, advertised range, target collaboration window, intake form URL
3. For each channel:
   a. Creates a new page in the Job Posts DB (properties only, no body)
   b. Sets Post ID (page ID without dashes)
   c. Computes submission form URL = intake_form_url + "?id=" + post_id
   d. Loads platform-specific template with `{{variable}}` substitution
   e. Appends template body blocks to the page
   f. Reads GEN PostID formula and updates the title to match

## How to Run

### Batch Mode (all Open openings)

```bash
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py
```

### Single Opening

```bash
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py --opening-id <notion_page_id>
```

### Dry Run (preview without creating)

```bash
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py --dry-run
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py --opening-id <id> --dry-run
```

## Templates

Templates are organized by (job_code, channel) pairs. Each template is a markdown file with two sections:

1. **Platform Metadata** — Form fields for the person posting (job title, location, pay range, etc.)
2. **External/Internal Job Post** — The actual job post copy

| Job Code | Channels | Template Files |
|----------|----------|----------------|
| EP | OLJ, Jobstreet, Facebook, Internal | `EP-OLJ.md`, `EP-Jobstreet.md`, `EP-Facebook.md`, `EP-Internal.md` |
| EPP | OLJ, Jobstreet, Facebook, Internal | `EPP-OLJ.md`, `EPP-Jobstreet.md`, `EPP-Facebook.md`, `EPP-Internal.md` |

Fallback: `_default.md` is used when no specific template matches.

### Template Variables

Templates use `{{variable}}` placeholders that are replaced at render time:

| Variable | Source |
|----------|--------|
| `{{job_title}}` | Openings DB "Job Title" |
| `{{employment_type}}` | Openings DB "Employment Type" |
| `{{advertised_range}}` | Openings DB "Advertised Range" |
| `{{target_collab_window}}` | Openings DB "Target Collaboration Window" |
| `{{submission_form_url}}` | Computed: intake_form_url + "?id=" + post_id |
| `{{post_id}}` | Page ID without dashes |
| `{{prefix}}` | Opening prefix (e.g., "251003-EP") |
| `{{channel}}` | Channel name |

Missing or null values resolve to empty string.

### Adding New Templates

1. Create a new markdown file in `templates/` named `{JOBCODE}-{Channel}.md`
2. Add the mapping in `libraries/template_registry.py` under `TEMPLATE_REGISTRY`
3. Use `{{variable}}` placeholders for dynamic content

## Notion Databases

**Ally Openings DB** (source):
- `Opening ID & Name` (title): e.g., "251003-EP Executive Partner (Rolling)"
- `Post Channels` (multi_select): OLJ, Jobstreet, Facebook, Internal
- `Status` (status): filtered for "Open"
- `Opening Base In-Take Form` (rich_text): base URL for intake form
- `Job Title` (rich_text): advertised job title
- `Employment Type` (rich_text): e.g., "Full-Time"
- `Advertised Range` (rich_text): e.g., "$1,100 USD - $1,200 USD"
- `Target Collaboration Window` (rich_text): e.g., "9:00 AM - 6:00 PM HKT"

**Job Posts DB** (target):
- `Job Post Title` (title): set to GEN PostID formula value
- `Opening` (relation): linked to opening page
- `Post Channel` (select): channel name
- `Status` (status): set to "Drafting"
- `Post ID` (rich_text): page ID without dashes
- `Opening Base In-take form` (url): intake form URL

## Requirements

- Python 3.11+
- Environment variable: `NOTION_KEY`
- Dependencies: `requests`, `python-dotenv`
