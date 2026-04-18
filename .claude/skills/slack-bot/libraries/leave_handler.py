"""/leave handler: replies with the leave request form link."""

import logging

logger = logging.getLogger(__name__)

LEAVE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfFwxHJr0OBf7ag99RSnJ2HqyEFx25w8--Udmymd5kE8baVaw/viewform"


def register(app, config: dict, project_root: str):
    """Register /leave command — open to all users."""

    @app.command("/leave")
    def handle_leave(ack, respond):
        ack()
        respond(
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":calendar: *Submit a Leave Request*\nFill out the form below to log your leave. Make sure you've already informed your CPL and client before submitting.",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open Leave Form"},
                            "style": "primary",
                            "url": LEAVE_FORM_URL,
                            "action_id": "leave_open_form",
                        }
                    ],
                },
            ],
            text="Submit a Leave Request",
            response_type="ephemeral",
        )

    @app.action("leave_open_form")
    def handle_leave_open_form(ack):
        ack()
