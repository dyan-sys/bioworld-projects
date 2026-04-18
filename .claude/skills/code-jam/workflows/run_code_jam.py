"""
Code Jam — Generate Slides & Notion Tracker

Generates a Google Slides deck for a Claude Code Jam session and optionally
creates/updates the Notion project tracker database.

Usage:
    # Basic: generate slides for Jam 2 with 5 EPs
    python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 2 --eps "Ana,Beth,Carol,Dana,Eve"

    # With Notion tracker setup (first time only)
    python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 1 --eps "Ana,Beth,Carol,Dana,Eve" --setup-tracker --parent-id <notion_page_id>

    # Update an existing deck in-place
    python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 2 --eps "Ana,Beth" --update <slides_url>

    # Dry run (generate markdown only, no API calls)
    python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 1 --eps "Ana,Beth" --dry-run
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = Path(__file__).resolve().parents[1]
SLIDES_WORKFLOW = PROJECT_ROOT / ".claude/skills/md-to-slides/workflows/generate_slides.py"
TRACKER_WORKFLOW = PROJECT_ROOT / ".claude/skills/code-jam/workflows/setup_tracker.py"
POST_PROCESS = PROJECT_ROOT / ".claude/skills/code-jam/workflows/post_process.py"

DEFAULT_EPS = [f"EP {i}" for i in range(1, 10)]  # EP 1–9


def render_template(jam_number: int, ep_names: list[str]) -> str:
    template_path = SKILL_ROOT / "templates/jam-deck.md.template"
    template = template_path.read_text()
    return template.format(
        jam_number=jam_number,
        next_jam_number=jam_number + 1,
        ep_count=len(ep_names),
    )


def extract_pres_id(output: str) -> str | None:
    """Extract presentation ID from slides generator stdout."""
    match = re.search(r"docs\.google\.com/presentation/d/([A-Za-z0-9_-]+)", output)
    return match.group(1) if match else None


def main():
    parser = argparse.ArgumentParser(description="Generate Claude Code Jam slides")
    parser.add_argument("--jam", type=int, default=1, help="Jam session number (default: 1)")
    parser.add_argument(
        "--eps",
        type=str,
        default=None,
        help="Comma-separated EP names (e.g. 'Ana,Beth,Carol'). Defaults to EP 1–9.",
    )
    parser.add_argument("--update", type=str, default=None, help="Update existing deck URL or ID")
    parser.add_argument("--dry-run", action="store_true", help="Generate markdown only, no API calls")
    parser.add_argument("--setup-tracker", action="store_true", help="Also create the Notion tracker")
    parser.add_argument("--parent-id", type=str, default=None, help="Notion parent page ID (required for --setup-tracker)")
    parser.add_argument("--theme", type=str, default="dark", choices=["dark", "light"], help="Slide theme (default: dark)")
    args = parser.parse_args()

    ep_names = [n.strip() for n in args.eps.split(",")] if args.eps else DEFAULT_EPS

    print(f"🧩 Claude Code Jam {args.jam}")
    print(f"   EPs: {', '.join(ep_names)}")
    print(f"   Theme: {args.theme}")
    print()

    # Render markdown
    md_content = render_template(args.jam, ep_names)
    output_path = PROJECT_ROOT / f"local-data/code-jam-{args.jam}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content)
    print(f"✅ Markdown written: {output_path}")

    if args.dry_run:
        print("\nDry run — skipping API calls.")
        print(f"Preview your markdown at: {output_path}")
        return

    # Generate slides
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json"))
    env = {**os.environ, "GOOGLE_CREDENTIALS_PATH": creds_path}

    cmd = [
        sys.executable,
        str(SLIDES_WORKFLOW),
        "--input", str(output_path),
        "--theme", args.theme,
        "--title", f"Claude Code Jam {args.jam}",
    ]
    if args.update:
        cmd += ["--update", args.update]

    print("\nGenerating slides...")
    result = subprocess.run(cmd, env=env, cwd=str(PROJECT_ROOT), capture_output=False, text=True)
    if result.returncode != 0:
        print("\n❌ Slides generation failed.")
        sys.exit(1)

    # Find the generated presentation ID from receipt
    pres_id = None
    receipts = sorted((PROJECT_ROOT / "local-data/slides").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if receipts:
        receipt = json.loads(receipts[0].read_text())
        url = receipt.get("presentation_url", "")
        pres_id = extract_pres_id(url)

    # Post-process: apply accent colors to bold/italic title text
    if pres_id:
        print("\nApplying accent colors...")
        subprocess.run(
            [sys.executable, str(POST_PROCESS), "--pres-id", pres_id],
            env=env, cwd=str(PROJECT_ROOT),
        )
    else:
        print("\n⚠️  Could not find presentation ID for post-processing.")

    # Setup Notion tracker (optional)
    if args.setup_tracker:
        if not args.parent_id:
            print("\n⚠️  --parent-id required for --setup-tracker. Skipping tracker setup.")
        else:
            print("\nSetting up Notion tracker...")
            tracker_cmd = [
                sys.executable,
                str(TRACKER_WORKFLOW),
                "--parent-id", args.parent_id,
                "--jam", f"Jam {args.jam}",
            ]
            if args.eps:
                tracker_cmd += ["--eas", args.eps]
            subprocess.run(tracker_cmd, cwd=str(PROJECT_ROOT))


if __name__ == "__main__":
    main()
