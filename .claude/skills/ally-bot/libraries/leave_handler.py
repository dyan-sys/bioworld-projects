"""AllyBot Home Tab — EP self-service hub."""

import logging

logger = logging.getLogger(__name__)

LEAVE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfFwxHJr0OBf7ag99RSnJ2HqyEFx25w8--Udmymd5kE8baVaw/viewform"
INVOICE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdpMy0P8ZQCRndt8xUhSoFuftELw2XKz4G9s09lrY_lglDxBQ/viewform"
BILLING_SOP_URL = "https://www.notion.so/withally/Billing-and-Payment-2612b7ec459780ba9e5cc9850effaff7"
INVOICE_TEMPLATE_URL = "https://file.notion.so/f/f/59d2b7ec-4597-8130-8328-000354b75112/353c8179-8958-46c6-a006-0c50256c49db/Template_INV-last_name__first_name_initial-YYYYMM.pdf?table=block&id=26f2b7ec-4597-80f4-9534-eb705d956deb&spaceId=59d2b7ec-4597-8130-8328-000354b75112&expirationTimestamp=1774454400000&signature=3yz86jdxAhw9QWJaBhOW5uRDhCC3XAx_CHSfKy1l3uY&downloadName=%5BTemplate%5D+INV-%5Blast+name+%2B+first+name+initial%5D-%5BYYYYMM%5D.pdf"
FEEDBACK_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfYJ_1fofCDabnDXnIwnRXTAgCl-ewpwSB6jQQQeiLb1Pfr9A/viewform"
REFERRAL_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSe44m3lXrcOHwmW1qiXa_wFSNmh8pP9fKXN7efIQNCyvPIYng/viewform"
REFERRAL_PROGRAM_URL = "https://www.notion.so/withally/Ally-Referral-Program-ARP-2842b7ec45978075808df53af24f5559"
DAILYOS_TEMPLATES_URL = "https://www.notion.so/withally/DailyOS-Templates-2522b7ec45978046b159cdd3e1ffe19a"
PAID_HOLIDAY_GUIDE_URL = "https://www.notion.so/withally/Paid-Holiday-Leave-EP-Guide-3052b7ec4597803a8c2adfd76ae43750"

HOME_BLOCKS = [
    {
        "type": "header",
        "text": {"type": "plain_text", "text": "👋 Welcome to AllyBot"},
    },
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "Your self-service hub for HR requests. Use the buttons below to get started.",
        },
    },
    {"type": "divider"},
    # --- Forms ---
    {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "📋  *FORMS*"}],
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🗓 Leave Request*\nFile a planned, emergency, or paid holiday leave.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "File Leave Request"},
            "style": "primary",
            "url": LEAVE_FORM_URL,
            "action_id": "home_leave_open_form",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🧾 Invoice Submission*\nSubmit your monthly invoice for processing.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Submit Invoice"},
            "style": "primary",
            "url": INVOICE_FORM_URL,
            "action_id": "home_invoice_open_form",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🤝 Referral Submission*\nRefer someone you know for an open role.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Submit Referral"},
            "style": "primary",
            "url": REFERRAL_FORM_URL,
            "action_id": "home_referral_form",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*💬 Questions & Feedback*\nShare questions, ideas, or feedback with the team.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Share Feedback"},
            "style": "primary",
            "url": FEEDBACK_FORM_URL,
            "action_id": "home_feedback_form",
        },
    },
    {"type": "divider"},
    # --- Resources ---
    {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "📚  *RESOURCES*"}],
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*📄 Billing & Payment SOP*\nLearn how the invoice and payment process works.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "View SOP"},
            "url": BILLING_SOP_URL,
            "action_id": "home_billing_sop",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🧾 Invoice Template*\nDownload the invoice template to fill out and submit.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "Download Template"},
            "url": INVOICE_TEMPLATE_URL,
            "action_id": "home_invoice_template",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🤝 Ally Referral Program*\nLearn how to refer someone and earn rewards.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "View Program"},
            "url": REFERRAL_PROGRAM_URL,
            "action_id": "home_referral_program",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🕐 DailyOS Templates*\nClock-in and clock-out message templates for your daily updates.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "View Templates"},
            "url": DAILYOS_TEMPLATES_URL,
            "action_id": "home_dailyos_templates",
        },
    },
    {"type": "divider"},
    {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*🏖 Paid Holiday Leave Guide*\nLearn about your paid holiday leave entitlements.",
        },
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "View Guide"},
            "url": PAID_HOLIDAY_GUIDE_URL,
            "action_id": "home_paid_holiday_guide",
        },
    },
]


def register(app):
    """Register App Home tab."""

    @app.event("app_home_opened")
    def handle_home_opened(event, client):
        resp = client.views_publish(
            user_id=event["user"],
            view={"type": "home", "blocks": HOME_BLOCKS},
        )
        if not resp.get("ok"):
            logger.error(f"views_publish failed: {resp}")

    @app.action("home_leave_open_form")
    def handle_home_leave_open_form(ack):
        ack()

    @app.action("home_invoice_open_form")
    def handle_home_invoice_open_form(ack):
        ack()

    @app.action("home_billing_sop")
    def handle_home_billing_sop(ack):
        ack()

    @app.action("home_invoice_template")
    def handle_home_invoice_template(ack):
        ack()

    @app.action("home_referral_form")
    def handle_home_referral_form(ack):
        ack()

    @app.action("home_feedback_form")
    def handle_home_feedback_form(ack):
        ack()

    @app.action("home_referral_program")
    def handle_home_referral_program(ack):
        ack()

    @app.action("home_dailyos_templates")
    def handle_home_dailyos_templates(ack):
        ack()

    @app.action("home_paid_holiday_guide")
    def handle_home_paid_holiday_guide(ack):
        ack()
