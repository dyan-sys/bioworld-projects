"""Per-command user access control."""


def check_access(user_id: str, command: str, config: dict) -> bool:
    """Check if user is authorized for this specific command."""
    cmd_config = config["commands"].get(command)
    if not cmd_config:
        return False
    return user_id in cmd_config.get("authorized_users", [])


def get_user_display_name(user_id: str, config: dict) -> str:
    """Get human-readable name for a user ID, or the raw ID if unknown."""
    return config.get("authorized_users", {}).get(user_id, user_id)
