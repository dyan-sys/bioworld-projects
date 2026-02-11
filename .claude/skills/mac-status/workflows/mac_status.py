#!/usr/bin/env python3
"""Mac system health diagnostic — memory, swap, disk, top processes, Ally jobs."""

import subprocess
import re


def run(cmd: str) -> str:
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── System Info ──────────────────────────────────────────────

def print_system_info():
    section("System Info")
    ram_bytes = int(run("sysctl -n hw.memsize"))
    ram_gb = ram_bytes / (1024 ** 3)
    print(f"  RAM:    {ram_gb:.0f} GB")

    uptime = run("uptime")
    # Extract the uptime portion (everything before "load averages")
    match = re.search(r"up\s+(.+?),\s+\d+\s+user", uptime)
    if match:
        print(f"  Uptime: {match.group(1).strip()}")
    else:
        print(f"  Uptime: {uptime}")


# ── Memory ───────────────────────────────────────────────────

def print_memory():
    section("Memory")

    # Swap
    swap_info = run("sysctl vm.swapusage")
    match = re.search(r"used\s*=\s*([\d.]+)([MG])", swap_info)
    if match:
        val, unit = float(match.group(1)), match.group(2)
        swap_used = val if unit == "G" else val / 1024
        marker = " ⚠" if swap_used > 2.0 else ""
        print(f"  Swap used:  {val:.1f} {unit}{marker}")
    else:
        print(f"  Swap: {swap_info}")

    total_match = re.search(r"total\s*=\s*([\d.]+)([MG])", swap_info)
    if total_match:
        val, unit = float(total_match.group(1)), total_match.group(2)
        print(f"  Swap total: {val:.1f} {unit}")

    # vm_stat for page info
    vm = run("vm_stat")
    page_size = 16384  # default on Apple Silicon
    ps_match = re.search(r"page size of (\d+) bytes", vm)
    if ps_match:
        page_size = int(ps_match.group(1))

    free_match = re.search(r"Pages free:\s+(\d+)", vm)
    if free_match:
        free_mb = int(free_match.group(1)) * page_size / (1024 ** 2)
        print(f"  Free pages: {free_mb:.0f} MB")

    # Memory pressure (extract free percentage from last line)
    pressure_out = run("memory_pressure 2>/dev/null")
    pct_match = re.search(r"free percentage:\s*(\d+)%", pressure_out)
    if pct_match:
        pct = int(pct_match.group(1))
        if pct > 20:
            level = "normal"
        elif pct > 5:
            level = "warn"
        else:
            level = "critical"
        marker = " ⚠" if level != "normal" else ""
        print(f"  Pressure:   {pct}% free ({level}){marker}")
    else:
        print("  Pressure:   (unavailable)")


# ── Disk ─────────────────────────────────────────────────────

def print_disk():
    section("Disk")
    df_out = run("df -h /")
    lines = df_out.split("\n")
    if len(lines) >= 2:
        parts = lines[1].split()
        # Filesystem Size Used Avail Capacity
        if len(parts) >= 5:
            print(f"  Total: {parts[1]}   Used: {parts[2]}   Free: {parts[3]}   ({parts[4]} used)")


# ── Top CPU Processes ────────────────────────────────────────

def print_top_cpu():
    section("Top CPU Processes")
    ps_out = run("ps -Arceo pid,pcpu,rss,comm | head -11")
    lines = ps_out.split("\n")
    print(f"  {'PID':>7}  {'CPU%':>6}  {'RSS MB':>8}  COMMAND")
    print(f"  {'-'*7}  {'-'*6}  {'-'*8}  {'-'*20}")
    for line in lines[1:]:
        parts = line.split(None, 3)
        if len(parts) >= 4:
            pid, cpu, rss_kb, cmd = parts[0], parts[1], parts[2], parts[3]
            rss_mb = int(rss_kb) / 1024
            # Shorten command path to basename
            cmd_short = cmd.split("/")[-1][:30]
            print(f"  {pid:>7}  {cpu:>6}  {rss_mb:>8.1f}  {cmd_short}")


# ── Top Memory Processes ─────────────────────────────────────

def print_top_memory():
    section("Top Memory Processes")
    ps_out = run("ps -Ameo pid,pcpu,rss,comm | sort -k3 -rn | head -10")
    lines = ps_out.split("\n")
    print(f"  {'PID':>7}  {'CPU%':>6}  {'RSS MB':>8}  COMMAND")
    print(f"  {'-'*7}  {'-'*6}  {'-'*8}  {'-'*20}")
    for line in lines:
        parts = line.split(None, 3)
        if len(parts) >= 4:
            pid, cpu, rss_kb, cmd = parts[0], parts[1], parts[2], parts[3]
            rss_mb = int(rss_kb) / 1024
            cmd_short = cmd.split("/")[-1][:30]
            print(f"  {pid:>7}  {cpu:>6}  {rss_mb:>8.1f}  {cmd_short}")


# ── Ally Jobs ────────────────────────────────────────────────

def print_ally_jobs():
    section("Ally Scheduled Jobs")
    jobs = run("launchctl list 2>/dev/null | grep com.ally")
    if not jobs:
        print("  No com.ally.* jobs registered with launchctl.")
        return

    print(f"  {'PID':>7}  {'Exit':>6}  LABEL")
    print(f"  {'-'*7}  {'-'*6}  {'-'*30}")
    for line in jobs.split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            pid, exit_code, label = parts[0].strip(), parts[1].strip(), parts[2].strip()
            pid_display = pid if pid != "-" else "  -"
            print(f"  {pid_display:>7}  {exit_code:>6}  {label}")


# ── Main ─────────────────────────────────────────────────────

def main():
    print("Mac Health Diagnostic")
    print_system_info()
    print_memory()
    print_disk()
    print_top_cpu()
    print_top_memory()
    print_ally_jobs()
    print()


if __name__ == "__main__":
    main()
