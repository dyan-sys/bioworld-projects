"""Shared subprocess runner + output utilities for skill execution."""

import os
import subprocess


PYTHON = "/opt/homebrew/bin/python3.11"


def run_skill(script_path: str, args: list[str], project_root: str,
              timeout: int = 120) -> tuple[int, str, str]:
    """Run a skill script as subprocess.

    Returns (exit_code, stdout, stderr).
    """
    cmd = [PYTHON, script_path] + args
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def parse_summary_block(stdout: str) -> str | None:
    """Extract the SUMMARY section from skill stdout.

    Returns everything after the SUMMARY header line, or None if not found.
    """
    marker = "SUMMARY"
    lines = stdout.split("\n")
    found = False
    summary_lines = []

    for line in lines:
        if not found and marker in line and line.strip() == marker:
            found = True
            continue
        if found:
            # Skip separator lines
            if line.strip() and all(c == "=" for c in line.strip()):
                continue
            summary_lines.append(line)

    if not found:
        return None
    return "\n".join(summary_lines).strip()


def parse_candidate_lines(stdout: str) -> list[dict]:
    """Parse [+]/[~]/[-]/[!] candidate lines from invite output.

    Returns list of dicts with keys: icon, name, detail
    """
    results = []
    for line in stdout.split("\n"):
        line = line.strip()
        for icon in ("+", "~", "-", "!"):
            prefix = f"[{icon}]"
            if line.startswith(prefix):
                rest = line[len(prefix):].strip()
                # Format: "Name -> email" or "Name: reason"
                results.append({"icon": icon, "text": rest})
                break
    return results
