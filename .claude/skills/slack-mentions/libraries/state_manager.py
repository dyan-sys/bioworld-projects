"""
State Manager Library

Tracks which mentions have already been notified to avoid duplicate DMs.
Uses atomic file writes for safety.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))


def load_state(path: str | Path) -> dict:
    """Load state from JSON file. Returns empty state if file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return {"notified": {}, "last_run": None}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict, path: str | Path) -> None:
    """Save state to JSON file using atomic write (temp + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory, then rename for atomicity
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def prune_state(state: dict, retention_hours: int = 48) -> dict:
    """Remove notified entries older than retention_hours."""
    cutoff = datetime.now(SGT) - timedelta(hours=retention_hours)
    cutoff_iso = cutoff.isoformat()

    pruned = {}
    for key, entry in state.get("notified", {}).items():
        if entry.get("notified_at", "") >= cutoff_iso:
            pruned[key] = entry

    state["notified"] = pruned
    return state


def make_key(channel_id: str, message_ts: str) -> str:
    """Create a state key from channel ID and message timestamp."""
    return f"{channel_id}:{message_ts}"


def is_already_notified(state: dict, channel_id: str, message_ts: str) -> bool:
    """Check if a mention has already been notified."""
    return make_key(channel_id, message_ts) in state.get("notified", {})


def mark_notified(
    state: dict,
    channel_id: str,
    message_ts: str,
    channel_name: str,
    sender: str,
    text_preview: str,
) -> None:
    """Mark a mention as notified in state."""
    key = make_key(channel_id, message_ts)
    state.setdefault("notified", {})[key] = {
        "channel_name": channel_name,
        "sender": sender,
        "notified_at": datetime.now(SGT).isoformat(),
        "text_preview": text_preview,
    }
