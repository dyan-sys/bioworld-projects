#!/usr/bin/env python3.11
"""Ally Bot — Slack Socket Mode daemon.

General-purpose skill gateway: routes slash commands to skill handlers
based on bot-config.json. Runs as a launchd KeepAlive daemon.
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Project root = 4 levels up from this file
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

# Load .env from project root
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Add libraries to path
sys.path.insert(0, os.path.join(PROJECT_ROOT, ".claude", "skills", "slack-bot"))

from libraries import invite_handler  # noqa: E402

# --- Logging ---
LOG_DIR = os.path.join(PROJECT_ROOT, "local-data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "slack-bot.log")),
    ],
)
logger = logging.getLogger("ally-bot")

# --- Config ---
CONFIG_PATH = os.path.join(
    PROJECT_ROOT, ".claude", "skills", "slack-bot", "templates", "bot-config.json"
)

with open(CONFIG_PATH) as f:
    config = json.load(f)

# --- Slack App ---
bot_token = os.environ.get("SLACK_BOT_TOKEN")
app_token = os.environ.get("SLACK_APP_TOKEN")

if not bot_token:
    logger.error("SLACK_BOT_TOKEN not set")
    sys.exit(1)
if not app_token:
    logger.error("SLACK_APP_TOKEN not set")
    sys.exit(1)

app = App(token=bot_token)

# --- Register handlers ---
invite_handler.register(app, config, PROJECT_ROOT)
logger.info("Registered handler: /ally-invite")

# --- Start ---
if __name__ == "__main__":
    logger.info("Ally Bot starting (Socket Mode)...")
    handler = SocketModeHandler(app, app_token)
    handler.start()
