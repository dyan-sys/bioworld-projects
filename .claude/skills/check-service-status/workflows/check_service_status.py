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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
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
        health = assess_job_health(job_id, job_config, status_files, artifact_results)
        results.append(health)

    # Build report
    now_sgt = datetime.now(SGT)
    report = build_status_report(results, now_sgt)
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
