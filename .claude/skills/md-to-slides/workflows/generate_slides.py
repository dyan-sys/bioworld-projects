"""
Generate Google Slides from Markdown

CLI entry point for the md-to-slides skill.

Usage:
    python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md
    python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --title "My Deck"
    python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --dry-run
    python3.11 .claude/skills/md-to-slides/workflows/generate_slides.py --input deck.md --validate
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add skill root to path for library imports
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SKILL_ROOT.parents[2]
sys.path.insert(0, str(SKILL_ROOT))

from libraries.md_parser import parse_markdown_file
from libraries.slides_builder import generate_presentation


def load_config() -> dict:
    """Load slide-config.json."""
    config_path = SKILL_ROOT / "templates" / "slide-config.json"
    if not config_path.exists():
        print(f"Error: Config not found at {config_path}")
        sys.exit(1)
    return json.loads(config_path.read_text())


def save_receipt(receipt: dict) -> Path:
    """Save generation receipt to local-data/slides/."""
    receipts_dir = PROJECT_ROOT / "local-data" / "slides"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    slug = receipt.get("title", "untitled").lower()
    slug = "".join(c if c.isalnum() or c in "-_ " else "" for c in slug)
    slug = slug.strip().replace(" ", "-")[:50]
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{date_str}_{slug}.json"

    path = receipts_dir / filename
    path.write_text(json.dumps(receipt, indent=2))
    return path


def cmd_validate(input_path: str) -> None:
    """Validate markdown file structure and print diagnostics."""
    pres = parse_markdown_file(input_path)

    print(f"File: {input_path}")
    print(f"Metadata: {pres.metadata}")
    print(f"Slides: {len(pres.slides)}")
    print()

    for i, slide in enumerate(pres.slides):
        print(f"  Slide {i + 1}:")
        print(f"    Layout:  {slide.layout}")
        print(f"    Title:   {slide.title or '(none)'}")
        if slide.body_items:
            print(f"    Body:    {len(slide.body_items)} items")
            for item in slide.body_items:
                print(f"      - {item}")
        if slide.left_body:
            print(f"    Left:    {len(slide.left_body)} items")
        if slide.right_body:
            print(f"    Right:   {len(slide.right_body)} items")
        if slide.table:
            print(f"    Table:   {len(slide.table)} rows x {len(slide.table[0])} cols")
        if slide.notes:
            print(f"    Notes:   {slide.notes[:60]}...")
        print()

    print("Validation passed." if pres.slides else "Warning: no slides found.")


def cmd_dry_run(input_path: str, title: str | None) -> None:
    """Parse and display what would be generated, without API calls."""
    pres = parse_markdown_file(input_path)
    config = load_config()

    effective_title = title or pres.metadata.get("title", "Untitled Presentation")

    print(f"DRY RUN — no API calls will be made\n")
    print(f"Title:     {effective_title}")
    print(f"Template:  {config['template_presentation_id']}")
    print(f"Slides:    {len(pres.slides)}")
    print()

    for i, slide in enumerate(pres.slides):
        layout_key = slide.layout or config["default_layout"]
        layout_display = config["layout_mapping"].get(layout_key, f"?{layout_key}")
        print(f"  [{i + 1}] {layout_display}: {slide.title or '(no title)'}")
        if slide.body_items:
            for item in slide.body_items[:3]:
                print(f"      - {item}")
            if len(slide.body_items) > 3:
                print(f"      ... +{len(slide.body_items) - 3} more")

    print(f"\nDry run complete. Use without --dry-run to generate.")


def cmd_generate(input_path: str, title: str | None) -> None:
    """Generate a Google Slides presentation."""
    from libraries.slides_auth import get_slides_services

    pres = parse_markdown_file(input_path)
    config = load_config()

    if config["template_presentation_id"] == "<PASTE_TEMPLATE_ID_HERE>":
        print("Error: template_presentation_id not configured in slide-config.json")
        print("Create a template deck in Google Slides and paste its ID.")
        sys.exit(1)

    effective_title = title or pres.metadata.get("title", "Untitled Presentation")

    if not pres.slides:
        print("Error: no slides found in input file.")
        sys.exit(1)

    slides_service, drive_service = get_slides_services()

    url = generate_presentation(
        slides_service=slides_service,
        drive_service=drive_service,
        template_id=config["template_presentation_id"],
        layout_mapping=config["layout_mapping"],
        default_layout=config["default_layout"],
        slides_data=pres.slides,
        title=effective_title,
    )

    # Save receipt
    receipt = {
        "title": effective_title,
        "input_file": str(Path(input_path).resolve()),
        "template_id": config["template_presentation_id"],
        "presentation_url": url,
        "slide_count": len(pres.slides),
        "generated_at": datetime.now().isoformat(),
    }
    receipt_path = save_receipt(receipt)
    print(f"Receipt saved: {receipt_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Google Slides from Markdown"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to the .md slide file",
    )
    parser.add_argument(
        "--title", "-t",
        help="Override presentation title (default: from frontmatter)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse only, show what would be generated (no API calls)",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate markdown structure and print diagnostics",
    )

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    if args.validate:
        cmd_validate(args.input)
    elif args.dry_run:
        cmd_dry_run(args.input, args.title)
    else:
        cmd_generate(args.input, args.title)


if __name__ == "__main__":
    main()
