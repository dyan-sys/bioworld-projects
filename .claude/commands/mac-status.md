---
description: Check Mac system health (memory, swap, disk, top processes, Ally jobs)
allowed-tools: Bash(python3:*)
---

Run a Mac health diagnostic that checks memory pressure, swap usage, disk space, top CPU/memory processes, and Ally scheduled job status.

## Execution

```bash
python3.11 .claude/skills/mac-status/workflows/mac_status.py
```

## After Completion

The script prints a formatted summary to the terminal. Flag anything concerning:
- Memory pressure above "normal"
- Swap usage over 2 GB
- Disk free below 10 GB
- Any single process using >50% CPU or >4 GB RSS
- Ally jobs that failed to register with launchctl
