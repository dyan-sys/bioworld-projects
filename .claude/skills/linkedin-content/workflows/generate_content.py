"""
LinkedIn Content Engine — Generate Content Workflow

3-phase pipeline: Steering → Research → Draft

Usage:
    python3.11 generate_content.py --brief "Why delegation fails"
    python3.11 generate_content.py --brief "Why delegation fails" --pillar delegation
    python3.11 generate_content.py --brief "Why delegation fails" --dry-run
    python3.11 generate_content.py --brief "At Ally we believe..." --skip-research
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from content_synthesizer import generate_draft, save_draft
from web_researcher import generate_search_queries, research_topic, save_research

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

SGT = timezone(timedelta(hours=8))

# Valid pillar keys
VALID_PILLARS = [
    "delegation", "focus", "operations", "ai-tools",
    "life-at-ally", "time-management", "achievements",
]


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:50].rstrip("-")


def main():
    parser = argparse.ArgumentParser(
        description="Generate LinkedIn content: research + draft pipeline"
    )
    parser.add_argument(
        "--brief",
        type=str,
        required=True,
        help="Topic idea, angle, or observation (free text)",
    )
    parser.add_argument(
        "--pillar",
        type=str,
        default=None,
        choices=VALID_PILLARS,
        help="Content pillar to focus on (auto-detected if omitted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Research only — don't generate draft",
    )
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip web search, generate from brief + strategy only",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("LINKEDIN CONTENT ENGINE")
    print("=" * 60)

    # Check environment
    moonshot_key = os.environ.get("MOONSHOT_API_KEY")
    if not moonshot_key:
        print("\n  ERROR: Missing MOONSHOT_API_KEY environment variable")
        sys.exit(1)

    date_str = datetime.now(SGT).strftime("%Y-%m-%d")
    slug = slugify(args.brief)
    pillar = args.pillar

    print(f"\n  Date:    {date_str}")
    print(f"  Brief:   {args.brief}")
    print(f"  Pillar:  {pillar or '(auto-detect)'}")
    if args.dry_run:
        print("  Mode:    DRY RUN (research only)")
    elif args.skip_research:
        print("  Mode:    SKIP RESEARCH (brief + strategy only)")

    # Phase 1: Generate search queries
    research_data = None

    if not args.skip_research:
        print(f"\n[1/3] Generating search queries...")
        queries = generate_search_queries(args.brief, pillar, moonshot_key)
        print(f"  Queries: {len(queries)}")
        for i, q in enumerate(queries, 1):
            print(f"    {i}. {q}")

        # Phase 2: Research
        print(f"\n[2/3] Researching topic via Kimi + web search...")
        research_data = research_topic(args.brief, queries, moonshot_key)

        # Attach metadata
        research_data["date"] = date_str
        research_data["brief"] = args.brief
        research_data["pillar"] = pillar
        research_data["queries"] = queries

        # Save research
        research_path = save_research(research_data, date_str, slug)
        print(f"  Research saved: {research_path.relative_to(PROJECT_ROOT)}")

        # Show summary
        sources = research_data.get("sources", [])
        print(f"  Sources found: {len(sources)}")
        for s in sources:
            title = s.get("title", "Untitled")
            print(f"    - {title}")

        synthesis = research_data.get("synthesis", "")
        if synthesis:
            preview = synthesis[:200] + "..." if len(synthesis) > 200 else synthesis
            print(f"  Synthesis preview: {preview}")

        if args.dry_run:
            print("\n" + "=" * 60)
            print("DRY RUN COMPLETE — research saved, no draft generated.")
            print("=" * 60)
            return
    else:
        print(f"\n[1/3] Skipping search queries (--skip-research)")
        print(f"[2/3] Skipping web research (--skip-research)")

    # Phase 3: Generate draft
    print(f"\n[3/3] Generating LinkedIn post draft...")
    draft_data = generate_draft(args.brief, pillar, research_data, moonshot_key)

    # Attach research synthesis for notes section
    if research_data:
        draft_data["research_synthesis"] = research_data.get("synthesis", "")

    # Save draft
    draft_path = save_draft(draft_data, date_str, slug)
    print(f"  Draft saved: {draft_path.relative_to(PROJECT_ROOT)}")

    # Print the draft
    post_text = draft_data["post_text"]
    char_count = len(post_text)
    print(f"\n  Post length: {char_count} characters")

    print("\n" + "-" * 60)
    print("DRAFT POST")
    print("-" * 60)
    print()
    print(post_text)
    print()
    print("-" * 60)

    # Summary
    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"  Draft file: {draft_path.relative_to(PROJECT_ROOT)}")
    if research_data:
        print(f"  Research:   local-data/linkedin/research/{date_str}_{slug}.json")
    print(f"  Characters: {char_count}")
    if char_count < 800:
        print("  Note: Post is on the short side — consider expanding.")
    elif char_count > 1800:
        print("  Note: Post is on the long side — consider trimming.")


if __name__ == "__main__":
    main()
