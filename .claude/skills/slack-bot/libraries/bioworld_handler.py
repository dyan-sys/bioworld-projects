"""
Bioworld LinkedIn Approval Handler for Ally Bot.

Handles interactive button actions from Slack approval cards:
  - bioworld_approve: Approve a draft → updates Notion status to Approved
  - bioworld_revise: Request revision → updates Notion status to On Hold, opens modal for comment
  - bioworld_reject: Reject a draft → updates Notion status to Rejected

The approval cards are sent by the Bioworld LinkedIn dashboard
(notify_approval.py or /api/send-for-approval).
"""

import logging
import os

import requests

logger = logging.getLogger("ally-bot.bioworld")

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _notion_headers():
    key = os.environ.get("NOTION_KEY", "")
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _update_notion_status(page_id: str, status: str, extra_props: dict = None):
    """Update a Notion page's status and optional extra properties."""
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    properties = {"Status": {"status": {"name": status}}}
    if extra_props:
        properties.update(extra_props)
    resp = requests.patch(url, headers=_notion_headers(),
                          json={"properties": properties}, timeout=30)
    return resp.ok


def register(app, config, project_root):
    """Register Bioworld approval action handlers with the Slack Bolt app."""

    @app.action("bioworld_approve")
    def handle_approve(ack, body, client):
        ack()
        page_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        ok = _update_notion_status(page_id, "Approved", {
            "Approved By": {
                "rich_text": [{"type": "text", "text": {"content": user}}]
            }
        })

        channel = body["channel"]["id"]
        ts = body["message"]["ts"]

        if ok:
            client.chat_update(
                channel=channel, ts=ts,
                text=f"Approved by @{user}",
                blocks=_approved_blocks(body["message"]["blocks"], user),
            )
            logger.info(f"Bioworld: {user} approved {page_id}")
        else:
            client.chat_postEphemeral(
                channel=channel, user=body["user"]["id"],
                text="Failed to update Notion. Try again or update manually.",
            )

    @app.action("bioworld_revise")
    def handle_revise(ack, body, client):
        ack()
        page_id = body["actions"][0]["value"]

        # Open a modal for the reviewer to add a comment
        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": f"bioworld_revise_modal_{page_id}",
                "title": {"type": "plain_text", "text": "Revision Notes"},
                "submit": {"type": "plain_text", "text": "Submit"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "notes_block",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "notes_input",
                            "multiline": True,
                            "placeholder": {"type": "plain_text", "text": "What should be changed?"},
                        },
                        "label": {"type": "plain_text", "text": "Revision notes"},
                    }
                ],
                "private_metadata": f"{page_id}|{body['channel']['id']}|{body['message']['ts']}",
            },
        )

    @app.view_regex(r"bioworld_revise_modal_.*")
    def handle_revise_submit(ack, body, client):
        ack()
        metadata = body["view"]["private_metadata"]
        page_id, channel_id, message_ts = metadata.split("|")
        notes = body["view"]["state"]["values"]["notes_block"]["notes_input"]["value"]
        user = body["user"]["username"]

        ok = _update_notion_status(page_id, "Draft Ready", {
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": f"Revision by {user}: {notes}"[:2000]}}]
            }
        })

        if ok:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"Revision requested by @{user}: {notes}",
            )
            logger.info(f"Bioworld: {user} requested revision for {page_id}")

    @app.action("bioworld_reject")
    def handle_reject(ack, body, client):
        ack()
        page_id = body["actions"][0]["value"]
        user = body["user"]["username"]

        ok = _update_notion_status(page_id, "Rejected", {
            "Notes": {
                "rich_text": [{"type": "text", "text": {"content": f"Rejected by {user}"}}]
            }
        })

        channel = body["channel"]["id"]
        ts = body["message"]["ts"]

        if ok:
            client.chat_update(
                channel=channel, ts=ts,
                text=f"Rejected by @{user}",
                blocks=_rejected_blocks(body["message"]["blocks"], user),
            )
            logger.info(f"Bioworld: {user} rejected {page_id}")

    logger.info("Registered Bioworld approval handlers")


def _approved_blocks(original_blocks, user):
    """Replace action buttons with an 'Approved' confirmation."""
    new_blocks = []
    for block in original_blocks:
        if block.get("type") == "actions":
            new_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":white_check_mark: *Approved* by @{user}"},
            })
        else:
            new_blocks.append(block)
    return new_blocks


def _rejected_blocks(original_blocks, user):
    """Replace action buttons with a 'Rejected' confirmation."""
    new_blocks = []
    for block in original_blocks:
        if block.get("type") == "actions":
            new_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":x: *Rejected* by @{user}"},
            })
        else:
            new_blocks.append(block)
    return new_blocks
