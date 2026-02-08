---
name: check-recruit-status
description: Trigger when user mentions checking recruitment status, pipeline metrics, screening backlog, or candidate stats
---

# Check Recruit Status Skill

Queries the Notion Candidates DB and prints a terminal report with 4 key metrics for daily recruitment monitoring.

## Metrics

1. **Pipeline Overview** - Total candidates, new in window, new today
2. **Status Breakdown** - Count per status with bar chart
3. **Screening Backlog** - Kimi/Claude scored vs unscored coverage
4. **Quality Distribution** - Kimi recommendation tier counts

## How to Run

```bash
# Default (7-day window)
python3.11 .claude/skills/check-recruit-status/workflows/check_recruit_status.py

# Custom window
python3.11 .claude/skills/check-recruit-status/workflows/check_recruit_status.py --days 14
```

## Requirements

- Python 3.11+
- Environment variables: `NOTION_KEY`, `NOTION_DB_ID`
- Dependencies: `requests`, `python-dotenv`
