"""/ally-invite handler: preview -> confirm -> execute."""

import json
import logging
import os
import subprocess

from .access_control import check_access, get_user_display_name
from .cooldown import check_cooldown, record_run
from .skill_runner import run_skill, parse_summary_block, parse_candidate_lines

logger = logging.getLogger(__name__)

SKILL_ID = "invite-candidates"
SCRIPT_PATH = ".claude/skills/invite-candidates/workflows/invite_candidates.py"


def register(app, config: dict, project_root: str):
    """Register /ally-invite command and its button actions."""

    cmd_config = config["commands"]["ally-invite"]

    @app.command("/ally-invite")
    def handle_invite(ack, command, respond):
        ack()

        user_id = command["user_id"]

        # Access check
        if not check_access(user_id, "ally-invite", config):
            respond(
                text=":no_entry: You don't have access to `/ally-invite`.",
                response_type="ephemeral",
            )
            return

        # Parse optional limit from command text
        text = (command.get("text") or "").strip()
        limit = cmd_config["options"]["default_limit"]
        if text:
            try:
                limit = int(text)
                limit = min(limit, cmd_config["options"]["max_limit"])
                limit = max(limit, 1)
            except ValueError:
                respond(
                    text=f":warning: Invalid limit `{text}`. Usage: `/ally-invite [limit]` (default: {cmd_config['options']['default_limit']})",
                    response_type="ephemeral",
                )
                return

        # Cooldown check
        cooldown_info = check_cooldown(
            SKILL_ID, cmd_config["cooldown_minutes"], project_root
        )
        if cooldown_info:
            user_name = get_user_display_name(
                cooldown_info["last_run_by"], config
            )
            respond(
                blocks=_build_cooldown_warning(
                    cooldown_info, user_name, limit
                ),
                text="Cooldown warning",
                response_type="ephemeral",
            )
            return

        # Run dry-run preview
        _run_preview(respond, limit, project_root)

    @app.action("invite_confirm")
    def handle_confirm(ack, body, respond):
        ack()

        user_id = body["user"]["id"]
        if not check_access(user_id, "ally-invite", config):
            respond(
                text=":no_entry: Access denied.",
                response_type="ephemeral",
                replace_original=False,
            )
            return

        # Extract limit from action value
        action_value = json.loads(body["actions"][0]["value"])
        limit = action_value["limit"]

        # Update message to show "Running..."
        respond(
            text=":hourglass_flowing_sand: Creating Gmail drafts...",
            response_type="ephemeral",
            replace_original=True,
        )

        # Execute real run
        try:
            exit_code, stdout, stderr = run_skill(
                SCRIPT_PATH, ["--limit", str(limit)], project_root,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            respond(
                text=":x: Invite script timed out after 180s.",
                response_type="ephemeral",
                replace_original=True,
            )
            return

        if exit_code != 0:
            logger.error("invite_candidates.py failed: %s", stderr[-500:] if stderr else "no stderr")
            respond(
                text=f":x: Invite script failed (exit {exit_code}).\n```{stderr[-300:] if stderr else 'No error output'}```",
                response_type="ephemeral",
                replace_original=True,
            )
            record_run(SKILL_ID, user_id, "failed", {}, project_root)
            return

        # Parse results
        summary = parse_summary_block(stdout) or "No summary available."
        candidates = parse_candidate_lines(stdout)

        # Count outcomes
        drafted = sum(1 for c in candidates if c["icon"] == "+")
        skipped = sum(1 for c in candidates if c["icon"] == "-")
        errors = sum(1 for c in candidates if c["icon"] == "!")

        record_run(SKILL_ID, user_id, "success", {
            "drafted": drafted, "skipped": skipped, "errors": errors,
        }, project_root)

        # Build result message
        icon = ":white_check_mark:" if errors == 0 else ":warning:"
        lines = [f"{icon} *Invite drafts created*"]
        lines.append(f"Drafted: {drafted} | Skipped: {skipped} | Errors: {errors}")
        lines.append("")
        for c in candidates:
            emoji = {"+": ":envelope:", "~": ":eyes:", "-": ":fast_forward:", "!": ":x:"}
            lines.append(f"{emoji.get(c['icon'], '')} {c['text']}")
        if drafted > 0:
            lines.append("")
            lines.append("Check your Gmail Drafts folder to review and send.")

        respond(
            text="\n".join(lines),
            response_type="ephemeral",
            replace_original=True,
        )

    @app.action("invite_cancel")
    def handle_cancel(ack, respond):
        ack()
        respond(
            text=":x: Cancelled.",
            response_type="ephemeral",
            replace_original=True,
        )

    @app.action("invite_cooldown_override")
    def handle_cooldown_override(ack, body, respond):
        ack()

        user_id = body["user"]["id"]
        if not check_access(user_id, "ally-invite", config):
            respond(
                text=":no_entry: Access denied.",
                response_type="ephemeral",
                replace_original=False,
            )
            return

        action_value = json.loads(body["actions"][0]["value"])
        limit = action_value["limit"]

        # Run preview (bypassing cooldown)
        respond(
            text=":hourglass_flowing_sand: Running preview...",
            response_type="ephemeral",
            replace_original=True,
        )
        _run_preview(respond, limit, project_root)


def _run_preview(respond, limit: int, project_root: str):
    """Run dry-run and show preview with Confirm/Cancel buttons."""
    try:
        exit_code, stdout, stderr = run_skill(
            SCRIPT_PATH, ["--dry-run", "--limit", str(limit)], project_root,
        )
    except subprocess.TimeoutExpired:
        respond(
            text=":x: Dry-run timed out after 120s.",
            response_type="ephemeral",
            replace_original=True,
        )
        return

    if exit_code != 0:
        logger.error("invite dry-run failed: %s", stderr[-500:] if stderr else "no stderr")
        respond(
            text=f":x: Dry-run failed (exit {exit_code}).\n```{stderr[-300:] if stderr else 'No error output'}```",
            response_type="ephemeral",
            replace_original=True,
        )
        return

    # Parse candidates from dry-run output
    candidates = parse_candidate_lines(stdout)
    preview_count = sum(1 for c in candidates if c["icon"] == "~")
    skip_count = sum(1 for c in candidates if c["icon"] == "-")

    if not candidates:
        respond(
            text=":inbox_tray: No candidates found to invite.",
            response_type="ephemeral",
            replace_original=True,
        )
        return

    # Build Block Kit preview
    blocks = _build_preview_blocks(candidates, preview_count, skip_count, limit)
    respond(
        blocks=blocks,
        text=f"Preview: {preview_count} candidates to invite",
        response_type="ephemeral",
        replace_original=True,
    )


def _build_preview_blocks(candidates: list[dict], preview_count: int,
                          skip_count: int, limit: int) -> list[dict]:
    """Build Block Kit message for dry-run preview."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Invite Candidates Preview",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{preview_count}* candidates ready | *{skip_count}* will be skipped",
            },
        },
        {"type": "divider"},
    ]

    # List candidates (cap at 15 to avoid Slack block limits)
    display = candidates[:15]
    for c in display:
        emoji = {"~": ":envelope:", "-": ":fast_forward:", "!": ":x:"}.get(c["icon"], "")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} {c['text']}",
            },
        })
    if len(candidates) > 15:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"_...and {len(candidates) - 15} more_",
            },
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Confirm & Create Drafts"},
                "style": "primary",
                "action_id": "invite_confirm",
                "value": json.dumps({"limit": limit}),
                "confirm": {
                    "title": {"type": "plain_text", "text": "Create Gmail Drafts?"},
                    "text": {
                        "type": "mrkdwn",
                        "text": f"This will create {preview_count} draft email(s) in Gmail.",
                    },
                    "confirm": {"type": "plain_text", "text": "Create Drafts"},
                    "deny": {"type": "plain_text", "text": "Go Back"},
                },
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Cancel"},
                "action_id": "invite_cancel",
            },
        ],
    })

    return blocks


def _build_cooldown_warning(cooldown_info: dict, user_name: str,
                            limit: int) -> list[dict]:
    """Build Block Kit cooldown warning with Run Anyway button."""
    minutes_ago = cooldown_info["minutes_ago"]
    meta = cooldown_info.get("metadata", {})
    drafted = meta.get("drafted", "?")
    result = cooldown_info.get("result", "unknown")

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":hourglass: *Cooldown active*\n"
                    f"Last run *{minutes_ago}m ago* by {user_name} "
                    f"({result}, {drafted} drafted)"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Run Anyway"},
                    "action_id": "invite_cooldown_override",
                    "value": json.dumps({"limit": limit}),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Cancel"},
                    "action_id": "invite_cancel",
                },
            ],
        },
    ]
