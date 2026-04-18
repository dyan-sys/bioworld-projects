#!/usr/bin/env python3
"""AllyBot — EP-facing Slack bot (Socket Mode daemon).

Provides self-service commands for EPs: leave requests, HR info, and more.
Runs as a launchd KeepAlive daemon.
"""

import logging
import os
import sys

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

sys.path.insert(0, os.path.join(PROJECT_ROOT, ".claude", "skills", "ally-bot"))

from libraries import leave_handler, faq_handler  # noqa: E402

# --- Logging ---
LOG_DIR = os.path.join(PROJECT_ROOT, "local-data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "ally-bot.log")),
    ],
)
logger = logging.getLogger(__name__)

bot_token = os.getenv("ALLY_BOT_TOKEN", "")
app_token = os.getenv("ALLY_APP_TOKEN", "")

if not bot_token:
    logger.error("ALLY_BOT_TOKEN not set")
    sys.exit(1)
if not app_token:
    logger.error("ALLY_APP_TOKEN not set")
    sys.exit(1)

app = App(token=bot_token)

# --- Register handlers ---
leave_handler.register(app)
logger.info("Registered handler: /leave")

faq_handler.register(app)
logger.info("Registered handler: FAQ / @mention")

# --- Start ---
if __name__ == "__main__":
    logger.info("AllyBot starting (Socket Mode)...")
    handler = SocketModeHandler(app, app_token)
    handler.start()
