# Slack Bot — General-Purpose Skill Gateway

## Overview

A Slack Socket Mode bot running as a launchd daemon. Exposes Ally OS skills to authorized team members via slash commands. Each skill registers as a slash command with its own access list, input pattern, and optional confirmation flow. The bot executes Python scripts as subprocesses — credentials and runtime stay local.

## Architecture

```
Slack slash command (e.g. /ally-invite)
  → WebSocket (Socket Mode — outbound, no public URL needed)
    → bot.py (long-running launchd daemon)
      → command registry (bot-config.json)
        → per-command access check
        → optional dry-run preview + [Confirm] / [Cancel]
        → subprocess execution (python3.11 skill_script.py ...)
        → result parsing + ephemeral Slack response
        → cooldown tracking
```

## Commands

### `/ally-invite [limit]`

Creates Gmail DRAFT emails for R1 candidate invitations.

- **Access:** Ivan, Dyan
- **Cooldown:** 120 minutes (warning, not a block)
- **Flow:** Slash command → access check → cooldown check → dry-run preview → Confirm/Cancel → execute → result

**Arguments:**
- `limit` (optional, default 10, max 50): Number of candidates to process

**Example:**
```
/ally-invite        → preview top 10 candidates
/ally-invite 5      → preview top 5 candidates
```

## Adding a New Skill

1. Create a handler file in `libraries/` (e.g., `pipeline_handler.py`)
   - Implement a `register(app, config, project_root)` function
   - Use `skill_runner.run_skill()` for subprocess execution
   - Use `access_control.check_access()` for authorization
   - Use `cooldown.check_cooldown()` / `record_run()` if needed
2. Add config entry to `templates/bot-config.json`
3. Import and call `register()` in `workflows/bot.py`
4. Create the slash command in Slack admin (api.slack.com/apps)

## Configuration

### `bot-config.json`

```json
{
  "authorized_users": {
    "U0975UFHDB8": "Ivan",
    "U097X5H3472": "Dyan"
  },
  "commands": {
    "ally-invite": {
      "handler": "invite_handler",
      "authorized_users": ["U0975UFHDB8", "U097X5H3472"],
      "cooldown_minutes": 120,
      "requires_confirmation": true,
      "options": {
        "default_limit": 10,
        "max_limit": 50
      }
    }
  }
}
```

## State Files

- **Cooldown:** `local-data/slack-bot/cooldown.json`
- **Logs:** `local-data/logs/slack-bot.log` (application log)
- **Stdout/Stderr:** `local-data/logs/slack-bot-stdout.log`, `slack-bot-stderr.log` (launchd)

## Daemon Management

```bash
# Install
cp scheduling/com.ally.slack-bot.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ally.slack-bot.plist

# Uninstall
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ally.slack-bot.plist
rm ~/Library/LaunchAgents/com.ally.slack-bot.plist

# Check status
launchctl list | grep slack-bot

# View logs
tail -f local-data/logs/slack-bot.log
tail -f local-data/logs/slack-bot-stderr.log
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | App-level token (`xapp-...`) for Socket Mode |

Plus all env vars required by the underlying skills (NOTION_KEY, etc.) — the bot inherits them via `.env`.

## Design Decisions

- **Subprocess, not import** — skill scripts use `sys.exit()` and module-level side effects. Subprocess isolation keeps the bot stable.
- **Ephemeral messages only** — responses visible only to the triggering user. Skills that already post to Slack channels continue to do so independently.
- **Per-command access** — different skills can be exposed to different users via config.
- **Cooldown is a warning** — "Run Anyway" is always available. `cooldown_minutes: 0` disables cooldown.
- **Socket Mode** — outbound WebSocket, no public URL or tunnel needed.
