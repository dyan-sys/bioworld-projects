---
name: mac-status
description: Trigger when user mentions checking Mac health, system performance, swap usage, memory pressure, or runaway processes
---

# Mac Status Skill

Quick diagnostic for an 8GB Mac. Checks memory pressure, swap, disk, top processes, and Ally job health — the same things you'd check manually when the machine feels sluggish.

## How to Run

```bash
python3.11 .claude/skills/mac-status/workflows/mac_status.py
```

## Output Sections

| Section | What it shows |
|---------|---------------|
| System Info | RAM, uptime |
| Memory | Swap usage, free pages, memory pressure level |
| Disk | Free space on `/` |
| Top CPU Processes | Top 10 by CPU % |
| Top Memory Processes | Top 10 by RSS |
| Ally Jobs | `launchctl list \| grep com.ally` status |

## Requirements

- Python 3.11+
- macOS (uses `sysctl`, `vm_stat`, `ps`, `df`, `launchctl`)
- No pip dependencies
