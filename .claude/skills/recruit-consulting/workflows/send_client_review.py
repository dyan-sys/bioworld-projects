"""
Send Client Review via Notion + Slack

Two-phase workflow for sending recruitment materials to clients:
  Phase 1 (--create-page): Creates a Notion page with the material content
  Phase 2 (--send): Posts a structured review message to Slack with the Notion link

Usage:
    # List available files for a client
    python3.11 send_client_review.py --client care-n-bloom --list-files

    # Phase 1: Create Notion page
    python3.11 send_client_review.py --client care-n-bloom \
        --create-page --file <path> --intent update

    # (User manually publishes page to web in Notion)

    # Phase 2: Post to Slack (with summary)
    python3.11 send_client_review.py --client care-n-bloom \
        --send --page-id <id> --summary "Updated comp range based on your feedback"

    # Dry run (either phase)
    python3.11 send_client_review.py --client care-n-bloom \
        --create-page --file <path> --intent update --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Path setup
SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
TEMPLATES_DIR = SKILL_ROOT / "templates"
CLIENT_DATA_DIR = PROJECT_ROOT / "local-data" / "client-consulting"

# Import markdown_to_notion_blocks from update-job-posts skill
UPDATE_POSTS_SKILL = PROJECT_ROOT / ".claude" / "skills" / "update-job-posts"
sys.path.insert(0, str(UPDATE_POSTS_SKILL))
from libraries.template_registry import markdown_to_notion_blocks

# Notion API
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_TIMEOUT = 30

# Load .env
load_dotenv(PROJECT_ROOT / ".env")


def notion_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def load_client_config(slug: str) -> dict:
    """Load and validate client config from client-config.json."""
    config_path = TEMPLATES_DIR / "client-config.json"
    if not config_path.exists():
        print(f"Error: config not found — {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        all_configs = json.load(f)

    if slug not in all_configs:
        print(f"Error: unknown client '{slug}'. Available: {', '.join(all_configs.keys())}")
        sys.exit(1)

    config = all_configs[slug]
    required = ["display_name", "notion_parent_page_id", "slack_channel_id"]
    for key in required:
        if not config.get(key) or config[key].startswith("<"):
            print(f"Error: client-config.json '{slug}.{key}' is not set")
            sys.exit(1)

    return config


def list_files(slug: str) -> list[Path]:
    """List .md files in the client's jd/ and interviews/ directories."""
    client_dir = CLIENT_DATA_DIR / slug
    files = []
    for subdir in ["jd", "interviews"]:
        d = client_dir / subdir
        if d.exists():
            files.extend(sorted(d.glob("*.md")))
    return files


def create_notion_page(api_key: str, parent_page_id: str, title: str, md_content: str) -> dict:
    """Create a child page under the parent with markdown content as blocks."""
    headers = notion_headers(api_key)
    blocks = markdown_to_notion_blocks(md_content)

    # Create page with title (first batch of blocks in children, max 100)
    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": [{"text": {"content": title}}],
        },
        "children": blocks[:100],
    }

    resp = requests.post(
        f"{NOTION_API_BASE}/pages", headers=headers, json=payload, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    page = resp.json()

    # Append remaining blocks if >100
    if len(blocks) > 100:
        page_id = page["id"]
        for i in range(100, len(blocks), 100):
            batch = blocks[i : i + 100]
            requests.patch(
                f"{NOTION_API_BASE}/blocks/{page_id}/children",
                headers=headers,
                json={"children": batch},
                timeout=REQUEST_TIMEOUT,
            ).raise_for_status()

    return {"id": page["id"], "url": page["url"], "block_count": len(blocks)}


def get_page_url(api_key: str, page_id: str) -> str:
    """Fetch page and return its internal Notion URL."""
    headers = notion_headers(api_key)
    resp = requests.get(
        f"{NOTION_API_BASE}/pages/{page_id}", headers=headers, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json().get("url", f"https://notion.so/{page_id.replace('-', '')}")


INTENT_LABELS = {
    "update": "Updated Draft",
    "initial-review": "Initial Review",
    "final-approval": "Final Approval",
}


def load_stage_templates() -> dict[str, str]:
    """Parse client-comms-guide.md and return {intent: template_body} mapping."""
    guide_path = TEMPLATES_DIR / "client-comms-guide.md"
    if not guide_path.exists():
        return {}

    text = guide_path.read_text(encoding="utf-8")
    templates = {}
    current_intent = None
    current_lines = []

    for line in text.split("\n"):
        if line.startswith("## Stage: "):
            # Save previous stage
            if current_intent is not None:
                templates[current_intent] = "\n".join(current_lines).strip()
            current_intent = line[len("## Stage: "):].strip()
            current_lines = []
        elif current_intent is not None:
            current_lines.append(line)

    # Save last stage
    if current_intent is not None:
        templates[current_intent] = "\n".join(current_lines).strip()

    return templates


def build_message(
    client_name: str,
    intent: str,
    checklist: list[str],
    notion_url: str,
    summary: str | None = None,
    next_steps: str | None = None,
) -> str:
    """Build the Slack review message from stage template."""
    intent_label = INTENT_LABELS.get(intent, intent.replace("-", " ").title())
    checklist_text = "\n".join(f"• {item}" for item in checklist)
    summary_text = summary or "We've prepared materials for your review."
    next_steps_text = next_steps or ""

    templates = load_stage_templates()
    template = templates.get(intent)

    if template:
        rendered = (
            template
            .replace("{{intent_label}}", intent_label)
            .replace("{{client_name}}", client_name)
            .replace("{{summary}}", summary_text)
            .replace("{{notion_url}}", notion_url)
            .replace("{{checklist}}", checklist_text)
            .replace("{{next_steps}}", next_steps_text)
        )
        # Clean up blank lines from empty optional variables
        while "\n\n\n" in rendered:
            rendered = rendered.replace("\n\n\n", "\n\n")
        return rendered.strip()

    # Fallback if template not found
    return (
        f"*{intent_label} — {client_name}*\n"
        f"\n"
        f"{summary_text}\n"
        f"\n"
        f":link: *Document:* {notion_url}\n"
        f"\n"
        f"*Areas to confirm:*\n"
        f"{checklist_text}\n"
        f"\n"
        f"Let us know in this thread — happy to adjust anything."
    )


def post_to_slack(token: str, channel: str, message: str) -> dict:
    """Post message to Slack via chat.postMessage."""
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    client = WebClient(token=token)
    try:
        resp = client.chat_postMessage(channel=channel, text=message)
        return {"ts": resp["ts"], "channel": resp["channel"]}
    except SlackApiError as e:
        print(f"Error posting to Slack: {e.response['error']}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Send client review via Notion + Slack")
    parser.add_argument("--client", required=True, help="Client slug from client-config.json")

    # Modes
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-page", action="store_true", help="Phase 1: create Notion page")
    mode.add_argument("--send", action="store_true", help="Phase 2: post to Slack")
    mode.add_argument("--list-files", action="store_true", help="List available .md files")

    # Phase 1 args
    parser.add_argument("--file", type=Path, help="Path to .md file (Phase 1)")
    parser.add_argument("--intent", help="Review intent: update, initial-review, final-approval")

    # Phase 2 args
    parser.add_argument("--page-id", help="Notion page ID from Phase 1")
    parser.add_argument("--summary", help="1-2 sentence context line for the Slack message")
    parser.add_argument("--next-steps", help="What's deferred or coming next (e.g., \"We'll look at the form URL separately!\")")
    parser.add_argument("--checklist", nargs="+", help="Custom checklist items (curated for this round)")
    parser.add_argument("--channel", help="Override Slack channel ID from config")

    # Shared
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")

    args = parser.parse_args()

    # --- List files mode ---
    if args.list_files:
        files = list_files(args.client)
        if not files:
            print(f"No .md files found for '{args.client}'")
            return
        print(f"Available files for '{args.client}':")
        for f in files:
            rel = f.relative_to(PROJECT_ROOT)
            print(f"  {rel}")
        return

    # Load config for create-page and send modes
    config = load_client_config(args.client)

    # --- Phase 1: Create Notion page ---
    if args.create_page:
        if not args.file:
            print("Error: --file is required with --create-page")
            sys.exit(1)
        if not args.intent:
            print("Error: --intent is required with --create-page")
            sys.exit(1)

        file_path = args.file.resolve()
        if not file_path.exists():
            print(f"Error: file not found — {file_path}")
            sys.exit(1)

        md_content = file_path.read_text(encoding="utf-8")
        title = f"[{args.intent.upper()}] {config['display_name']} — {file_path.stem}"
        blocks = markdown_to_notion_blocks(md_content)

        if args.dry_run:
            print("=== DRY RUN — Phase 1: Create Notion Page ===\n")
            print(f"  Parent page: {config['notion_parent_page_id']}")
            print(f"  Title: {title}")
            print(f"  Source file: {file_path}")
            print(f"  Block count: {len(blocks)}")
            return

        notion_key = os.environ.get("NOTION_KEY")
        if not notion_key:
            print("Error: NOTION_KEY not set in .env")
            sys.exit(1)

        result = create_notion_page(
            notion_key, config["notion_parent_page_id"], title, md_content
        )
        print(f"Page created: {result['url']}")
        print(f"  ID: {result['id']}")
        print(f"  Blocks: {result['block_count']}")
        print(f"\nNext — run Phase 2 to post to Slack:")
        print(f"  python3.11 {Path(__file__).name} --client {args.client} --send --page-id {result['id']}")

    # --- Phase 2: Post to Slack ---
    if args.send:
        if not args.page_id:
            print("Error: --page-id is required with --send")
            sys.exit(1)

        checklist = args.checklist or config.get("default_checklist", [])
        channel = args.channel or config["slack_channel_id"]
        intent = args.intent or "update"

        if args.dry_run:
            print("=== DRY RUN — Phase 2: Post to Slack ===\n")
            print(f"  Channel: {channel}")
            print(f"  Intent: {intent}")
            print(f"  Page ID: {args.page_id}")
            notion_url = f"https://notion.so/{args.page_id.replace('-', '')}"
            message = build_message(
                config["display_name"], intent, checklist, notion_url,
                args.summary, args.next_steps,
            )
            print(f"\n--- Message preview ---\n{message}\n--- End preview ---")
            return

        notion_key = os.environ.get("NOTION_KEY")
        if not notion_key:
            print("Error: NOTION_KEY not set in .env")
            sys.exit(1)

        slack_token = os.environ.get("SLACK_BOT_TOKEN")
        if not slack_token:
            print("Error: SLACK_BOT_TOKEN not set in .env")
            sys.exit(1)

        notion_url = get_page_url(notion_key, args.page_id)

        message = build_message(
            config["display_name"], intent, checklist, notion_url,
            args.summary, args.next_steps,
        )
        result = post_to_slack(slack_token, channel, message)
        print(f"Message posted to #{channel} (ts={result['ts']})")
        print(f"  Notion link: {notion_url}")


if __name__ == "__main__":
    main()
