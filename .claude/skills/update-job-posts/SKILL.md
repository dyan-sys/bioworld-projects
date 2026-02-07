---
name: update-job-posts
description: Trigger when user mentions creating job posts, updating job postings, publishing openings, or syncing openings to job posts
---

# Update Job Posts Skill

Automatically creates job post pages in the Job Posts DB for each Open opening in the Ally Openings DB. Creates one post per Post Channel (OLJ, Jobstreet, Facebook, Internal, etc.) with platform-specific content from templates.

## How It Works

1. Queries the Ally Openings DB for openings with Status = "Open"
2. For each opening, reads the Post Channels (multi_select)
3. For each channel, loads a platform-specific template by (job_code, channel)
4. Creates a new page in the Job Posts DB with:
   - Opening relation linked
   - Post Channel set
   - Status set to "Drafting"
   - Template content as page body
5. Reads back the GEN PostID formula and updates the title to match
6. Sets Post ID to the page ID (no dashes)

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

Templates are organized by (job_code, channel) pairs. Each template is a markdown file that gets converted to Notion blocks.

| Job Code | Channels | Template Files |
|----------|----------|----------------|
| EP | OLJ, Jobstreet, Facebook, Internal | `EP-OLJ.md`, `EP-Jobstreet.md`, `EP-Facebook.md`, `EP-Internal.md` |
| EPP | OLJ, Jobstreet, Facebook, Internal | `EPP-OLJ.md`, `EPP-Jobstreet.md`, `EPP-Facebook.md`, `EPP-Internal.md` |

Fallback: `_default.md` is used when no specific template matches.

### Adding New Templates

1. Create a new markdown file in `templates/` named `{JOBCODE}-{Channel}.md`
2. Add the mapping in `libraries/template_registry.py` under `TEMPLATE_REGISTRY`

## Notion Databases

**Ally Openings DB** (source):
- `Opening ID & Name` (title): e.g., "251003-EP Executive Partner (Rolling)"
- `Post Channels` (multi_select): OLJ, Jobstreet, Facebook, Internal
- `Status` (status): filtered for "Open"

**Job Posts DB** (target):
- `Job Post Title` (title): set to GEN PostID formula value
- `Opening` (relation): linked to opening page
- `Post Channel` (select): channel name
- `Status` (status): set to "Drafting"
- `Post ID` (rich_text): page ID without dashes

## Requirements

- Python 3.11+
- Environment variable: `NOTION_KEY`
- Dependencies: `requests`, `python-dotenv`
