---
description: Check recruitment pipeline status and metrics
argument-hint: [--days N]
allowed-tools: Bash(python3:*), Read
---

Check recruitment pipeline status by querying the Notion Candidates DB and printing a terminal report with pipeline overview, status breakdown, screening backlog, and quality distribution.

Parse the following arguments: $ARGUMENTS

## Argument Parsing

The argument can be:
1. **`--days N`** — Set the window for "new candidates" metric (default: 7)
2. **Empty** — Use default 7-day window

## Execution

```bash
python3.11 .claude/skills/check-recruit-status/workflows/check_recruit_status.py [--days N]
```

## After Completion

The script prints the full report to the terminal. Summarize any notable findings:
- Pipeline growth trends
- Screening backlog status
- Quality distribution highlights
