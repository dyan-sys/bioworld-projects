---
description: Create job post pages for Open openings in Notion
argument-hint: [opening-url-or-id] [--dry-run]
allowed-tools: Bash(python3:*), Read, Grep, Glob
---

Create job post pages in the Job Posts DB for Open openings in the Ally Openings DB. One post is created per Post Channel with platform-specific template content.

Parse the following arguments: $ARGUMENTS

## Argument Parsing

The argument can be:
1. **A Notion URL** (contains `notion.so` or `notion.site`) — process that specific opening
2. **A Notion page ID** (32-char hex or UUID format) — process that specific opening
3. **`--dry-run`** — preview what would be created without making changes
4. **Empty** — process all Open openings (batch mode)

Arguments can be combined: a URL/ID with `--dry-run`.

## Execution

Extract the page ID from any Notion URL (the 32-char hex at the end of the URL path).

### Batch Mode (no URL/ID provided)

```bash
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py [--dry-run]
```

### Single Opening Mode (URL or ID provided)

```bash
python3.11 .claude/skills/update-job-posts/workflows/update_job_posts.py --opening-id <page_id> [--dry-run]
```

## After Completion

Report the results:
- How many job posts were created (or would be created in dry-run mode)
- Which openings and channels were processed
- Any errors encountered
