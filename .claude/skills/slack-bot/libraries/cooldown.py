"""JSON-based cooldown tracker (per-skill)."""

import json
import os
from datetime import datetime, timezone


COOLDOWN_FILE = "local-data/slack-bot/cooldown.json"


def _load(project_root: str) -> dict:
    path = os.path.join(project_root, COOLDOWN_FILE)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _save(data: dict, project_root: str):
    path = os.path.join(project_root, COOLDOWN_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def check_cooldown(skill_id: str, window_minutes: int, project_root: str) -> dict | None:
    """Return last run info if within cooldown window, else None.

    Returns dict with keys: last_run_at, last_run_by, result, metadata, minutes_ago
    """
    if window_minutes <= 0:
        return None
    data = _load(project_root)
    entry = data.get(skill_id)
    if not entry:
        return None

    last_run = datetime.fromisoformat(entry["last_run_at"])
    now = datetime.now(timezone.utc)
    minutes_ago = (now - last_run).total_seconds() / 60

    if minutes_ago < window_minutes:
        return {**entry, "minutes_ago": int(minutes_ago)}
    return None


def record_run(skill_id: str, user_id: str, result: str,
               metadata: dict, project_root: str):
    """Record a skill execution for cooldown tracking."""
    data = _load(project_root)
    data[skill_id] = {
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "last_run_by": user_id,
        "result": result,
        "metadata": metadata,
    }
    _save(data, project_root)
