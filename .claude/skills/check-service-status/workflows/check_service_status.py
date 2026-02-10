"""
Check Service Status Workflow

Reads job-registry.json and status files written by run-job.sh to determine
whether scheduled jobs ran successfully. Posts a summary to Slack.

Usage:
    python3.11 check_service_status.py
    python3.11 check_service_status.py --job pipeline-report
    python3.11 check_service_status.py --date 2026-02-09
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from balance_checker import (
    build_balance_section,
    count_api_calls,
    fetch_balance,
    load_snapshot,
    save_snapshot,
)
from status_checker import (
    assess_job_health,
    build_status_report,
    check_artifact,
    find_status_files,
    load_job_registry,
    post_to_slack,
)

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

SGT = timezone(timedelta(hours=8))
STATUS_DIR = PROJECT_ROOT / "local-data" / "service-status"
REPORTS_DIR = STATUS_DIR / "reports"
REGISTRY_PATH = SKILL_ROOT / "templates" / "job-registry.json"


BALANCE_SNAPSHOT_DIR = STATUS_DIR / "api-balance"


def _build_api_balance_section(check_date: str) -> str | None:
    """Fetch Moonshot API balances and build the report section.

    Returns the formatted section string, or None if both keys fail.
    """
    key_screening = os.environ.get("MOONSHOT_API_KEY")
    key_ep = os.environ.get("MOONSHOT_API_KEY_EP") or key_screening

    if not key_screening and not key_ep:
        return None

    balances = {}
    for key_name, api_key in [("screening", key_screening), ("ep_review", key_ep)]:
        if not api_key:
            continue
        try:
            balances[key_name] = fetch_balance(api_key)
        except Exception as e:
            print(f"WARNING: Failed to fetch balance for {key_name}: {e}")

    if not balances:
        return None

    # Save today's snapshot
    try:
        save_snapshot(balances, check_date, BALANCE_SNAPSHOT_DIR)
    except Exception as e:
        print(f"WARNING: Failed to save balance snapshot: {e}")

    # Load yesterday's snapshot for delta
    from datetime import date as date_cls

    yesterday = (date_cls.fromisoformat(check_date) - timedelta(days=1)).isoformat()
    prev_snapshot = load_snapshot(yesterday, BALANCE_SNAPSHOT_DIR)

    # Count API calls
    call_counts = count_api_calls(check_date, PROJECT_ROOT)

    return build_balance_section(balances, prev_snapshot, call_counts)


def main():
    parser = argparse.ArgumentParser(
        description="Check health of scheduled jobs"
    )
    parser.add_argument(
        "--job",
        type=str,
        default=None,
        help="Check a single job by ID (default: all jobs)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Check a specific date in YYYY-MM-DD format (default: today UTC)",
    )
    args = parser.parse_args()

    # Load registry
    try:
        jobs = load_job_registry(REGISTRY_PATH)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Determine date to check
    if args.date:
        check_date = args.date
    else:
        # Use today's UTC date (matches run-job.sh timestamp format)
        check_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Filter to single job if requested
    if args.job:
        if args.job not in jobs:
            print(f"ERROR: Unknown job '{args.job}'. Available: {', '.join(jobs.keys())}")
            sys.exit(1)
        jobs = {args.job: jobs[args.job]}

    print(f"Checking service status for {check_date}...")
    print(f"Jobs to check: {', '.join(jobs.keys())}")
    print()

    results = []
    for job_id, job_config in jobs.items():
        # Find status files
        status_files = find_status_files(job_id, check_date, STATUS_DIR)

        # Run artifact checks
        artifact_results = []
        for check in job_config.get("artifact_checks", []):
            result = check_artifact(check, PROJECT_ROOT, check_date)
            artifact_results.append(result)

        # Assess health
        health = assess_job_health(job_id, job_config, status_files, artifact_results, check_date=check_date)
        results.append(health)

    # Build report
    now_sgt = datetime.now(SGT)
    report = build_status_report(results, now_sgt)

    # API balance section
    balance_section = _build_api_balance_section(check_date)
    if balance_section:
        report += "\n" + balance_section

    print(report, end="")

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = now_sgt.strftime("%Y-%m-%d_%H%M_SGT") + ".txt"
    report_path = REPORTS_DIR / filename
    report_path.write_text(report)
    print(f"Report saved to: {report_path.relative_to(PROJECT_ROOT)}")

    # Post to Slack
    post_to_slack(report)


if __name__ == "__main__":
    main()
