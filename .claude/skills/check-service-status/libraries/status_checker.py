"""
Status Checker Library

Core logic for checking scheduled job health by reading status files
and running artifact checks.
"""

import glob
import json
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import requests

SGT = timezone(timedelta(hours=8))


def load_job_registry(path: Path) -> dict:
    """Load and return the job registry JSON."""
    with open(path) as f:
        registry = json.load(f)
    if "jobs" not in registry:
        raise ValueError("job-registry.json missing 'jobs' key")
    return registry["jobs"]


def find_status_files(job_id: str, date: str, status_dir: Path) -> list[dict]:
    """Find all status JSON files for a job on a given date.

    Args:
        job_id: Job identifier (e.g., "pipeline-report")
        date: Date string in YYYY-MM-DD format
        status_dir: Path to local-data/service-status/

    Returns:
        List of parsed status dicts, sorted by started_at desc.
    """
    pattern = str(status_dir / f"{job_id}_{date}_*.json")
    files = glob.glob(pattern)
    results = []
    for f in sorted(files, reverse=True):
        try:
            with open(f) as fh:
                results.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _expand_date_pattern(pattern: str, date: str) -> str:
    """Replace {YYYY-MM-DD} placeholder with actual date."""
    return pattern.replace("{YYYY-MM-DD}", date)


def check_artifact(check_config: dict, project_root: Path, date: str) -> dict:
    """Run a single artifact check.

    Returns:
        {"type": str, "passed": bool, "detail": str}
    """
    check_type = check_config["type"]
    directory = project_root / check_config["directory"]
    pattern = _expand_date_pattern(check_config["pattern"], date)

    if check_type == "file_exists":
        matches = glob.glob(str(directory / pattern))
        if matches:
            filename = os.path.basename(matches[0])
            return {"type": "file_exists", "passed": True, "detail": f"Found: {filename}"}
        return {"type": "file_exists", "passed": False, "detail": f"No file matching {pattern}"}

    elif check_type == "log_contains":
        search_string = check_config["search_string"]
        matches = glob.glob(str(directory / pattern))
        if not matches:
            return {"type": "log_contains", "passed": False, "detail": f"No log matching {pattern}"}
        # Check the most recent matching log
        log_path = sorted(matches, reverse=True)[0]
        try:
            with open(log_path) as fh:
                content = fh.read()
            if search_string in content:
                return {"type": "log_contains", "passed": True, "detail": f'Log contains "{search_string}"'}
            return {"type": "log_contains", "passed": False, "detail": f'Log missing "{search_string}"'}
        except OSError as e:
            return {"type": "log_contains", "passed": False, "detail": f"Cannot read log: {e}"}

    return {"type": check_type, "passed": False, "detail": f"Unknown check type: {check_type}"}


def assess_job_health(
    job_id: str,
    job_config: dict,
    status_files: list[dict],
    artifact_results: list[dict],
) -> dict:
    """Determine overall health for a job.

    Returns:
        {"job_id": str, "label": str, "health": str, "status": dict|None,
         "artifacts": list, "detail": str}
    """
    label = job_config["label"]

    if not status_files:
        return {
            "job_id": job_id,
            "label": label,
            "health": "MISSED",
            "status": None,
            "artifacts": artifact_results,
            "detail": "No status file found — job did not run",
        }

    latest = status_files[0]
    exit_code = latest.get("exit_code", -1)

    if exit_code != 0:
        detail = f"Exit code {exit_code} ({latest.get('status', 'unknown')})"
        return {
            "job_id": job_id,
            "label": label,
            "health": "FAIL",
            "status": latest,
            "artifacts": artifact_results,
            "detail": detail,
        }

    all_passed = all(a["passed"] for a in artifact_results)
    if all_passed:
        return {
            "job_id": job_id,
            "label": label,
            "health": "OK",
            "status": latest,
            "artifacts": artifact_results,
            "detail": "All checks passed",
        }
    else:
        failed = [a for a in artifact_results if not a["passed"]]
        detail = f"{len(failed)} artifact check(s) failed"
        return {
            "job_id": job_id,
            "label": label,
            "health": "WARN",
            "status": latest,
            "artifacts": artifact_results,
            "detail": detail,
        }


def _format_time_sgt(iso_str: str | None) -> str:
    """Convert ISO timestamp to HH:MM SGT display string."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(SGT)
        return dt.strftime("%H:%M SGT")
    except (ValueError, TypeError):
        return "-"


def _health_icon(health: str) -> str:
    """Return a text icon for health status."""
    return {
        "OK": "[OK]",
        "WARN": "[WARN]",
        "FAIL": "[FAIL]",
        "MISSED": "[MISSED]",
    }.get(health, "[?]")


def build_status_report(results: list[dict], timestamp: datetime) -> str:
    """Build a Slack-formatted status report.

    Args:
        results: List of job health dicts from assess_job_health()
        timestamp: Report generation timestamp
    """
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M SGT")
    out = StringIO()
    p = lambda line="": print(line, file=out)

    p(f"*Service Status* | {ts_str}")
    p()
    p("```")
    p(f"{'Job':<25} {'Status':<8} {'Time':<12} {'Duration':<10}")

    for r in results:
        health = r["health"]
        status = r["status"]
        if status:
            time_str = _format_time_sgt(status.get("started_at"))
            duration = status.get("duration_seconds")
            dur_str = f"{duration}s" if duration is not None else "-"
        else:
            time_str = "-"
            dur_str = "-"
        p(f"{r['label']:<25} {health:<8} {time_str:<12} {dur_str:<10}")

    p("```")

    # Details section
    p()
    p("Details:")
    for r in results:
        p(f"  {r['job_id']}:")
        if r["health"] == "MISSED":
            p(f"    [MISSED] {r['detail']}")
        elif r["health"] == "FAIL":
            p(f"    [FAIL] {r['detail']}")
        for a in r.get("artifacts", []):
            icon = "[OK]" if a["passed"] else "[FAIL]"
            p(f"    {icon} {a['detail']}")

    return out.getvalue()


def post_to_slack(report: str) -> None:
    """Post report to Slack via Incoming Webhook. Uses SLACK_WEBHOOK_URL_JARVIS,
    falling back to SLACK_WEBHOOK_URL. Skips if neither is set."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL_JARVIS") or os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    try:
        resp = requests.post(webhook_url, json={"text": report}, timeout=15)
        resp.raise_for_status()
        print("Slack: posted successfully.")
    except requests.RequestException as e:
        print(f"Slack: failed to post — {e}")
