"""
CS Digest Workflow

Reads text files from an input folder, sends them to Kimi AI for analysis,
and produces a structured Customer Success digest report.

Usage:
    python3.11 generate_digest.py
    python3.11 generate_digest.py --date 2026-02-12
    python3.11 generate_digest.py --folder /path/to/files
    python3.11 generate_digest.py --dry-run
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
from kimi_analyzer import analyze_via_kimi, build_prompt
from report_builder import (
    format_documents_block,
    read_input_files,
    save_receipt,
    save_report,
)

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

SGT = timezone(timedelta(hours=8))


def today_sgt() -> str:
    """Return today's date in YYYY-MM-DD format (SGT)."""
    return datetime.now(SGT).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a CS digest report from text files via Kimi AI"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Report date in YYYY-MM-DD format (default: today in SGT)",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Input folder path (default: local-data/cs-digest/input/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview prompt without calling Kimi",
    )
    args = parser.parse_args()

    date_str = args.date or today_sgt()

    print("=" * 60)
    print("CS DIGEST REPORT")
    print("=" * 60)
    print(f"  Date: {date_str}")
    if args.dry_run:
        print("  Mode: DRY RUN (no Kimi call)")

    # Phase 1: Load environment
    print("\n[1/4] Loading environment...")
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")
    if not moonshot_key and not args.dry_run:
        print("  ERROR: Missing MOONSHOT_API_KEY environment variable")
        sys.exit(1)
    if moonshot_key:
        print("  MOONSHOT_API_KEY loaded.")
    else:
        print("  MOONSHOT_API_KEY not set (not needed for dry run).")

    # Phase 2: Read input files
    print("\n[2/4] Reading input files...")
    try:
        files = read_input_files(args.folder)
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    print(f"  Total: {len(files)} file(s)")

    # Phase 3: Build prompt and analyze via Kimi
    print("\n[3/4] Analyzing via Kimi AI...")
    documents_block = format_documents_block(files)
    prompt = build_prompt(date_str, documents_block)
    print(f"  Prompt length: {len(prompt)} chars")

    if args.dry_run:
        print("\n--- DRY RUN: Prompt Preview ---")
        print(prompt[:2000])
        if len(prompt) > 2000:
            print(f"\n... ({len(prompt) - 2000} more chars)")
        print("--- End Preview ---")
        print("\nDry run complete. No Kimi call made.")
        return

    raw_response = analyze_via_kimi(prompt, moonshot_key)

    # Phase 4: Save and display
    print("\n[4/4] Saving report...")
    receipt_path = save_receipt(raw_response, date_str, files)
    report_path = save_report(raw_response, date_str)

    print(f"  Receipt: {receipt_path.relative_to(PROJECT_ROOT)}")
    print(f"  Report:  {report_path.relative_to(PROJECT_ROOT)}")

    print("\n" + "=" * 60)
    print("DIGEST REPORT")
    print("=" * 60)
    print()
    print(raw_response)
    print()
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
