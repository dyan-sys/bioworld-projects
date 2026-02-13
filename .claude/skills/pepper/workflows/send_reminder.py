#!/usr/bin/env python3.11
"""Send a Slack DM reminder. Used by Pepper (Personal EA) for scheduled pings.

Usage:
    python3.11 send_reminder.py "Your reminder message here"
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from slack_sdk import WebClient

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

SLACK_USER_ID = "U0975UFHDB8"


def main():
    if len(sys.argv) < 2:
        print("ERROR: No message provided. Usage: send_reminder.py <message>")
        sys.exit(1)

    message = sys.argv[1]
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: SLACK_BOT_TOKEN not set")
        sys.exit(1)

    client = WebClient(token=token)
    client.chat_postMessage(channel=SLACK_USER_ID, text=message, mrkdwn=True)
    print(f"SUMMARY: Reminder sent to Slack.")


if __name__ == "__main__":
    main()
