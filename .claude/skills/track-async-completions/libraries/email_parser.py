"""
Email Parser — Extract candidate info from Hireflix completion emails.

Config-driven via platform-config.json. No code changes needed to tune patterns.
"""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


def load_platform_config(platform: str = "hireflix") -> dict:
    """Load parsing config for a platform."""
    config_path = TEMPLATES_DIR / "platform-config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    if platform not in config:
        raise ValueError(f"Unknown platform: {platform}. Available: {list(config.keys())}")
    return config[platform]


def parse_subject(subject: str, config: dict) -> dict | None:
    """
    Extract candidate name and job title from email subject.

    Returns dict with 'candidate_name' and 'job_title', or None if no match.
    """
    pattern = config["subject_pattern"]
    groups = config["subject_groups"]
    match = re.match(pattern, subject)
    if not match:
        return None
    return {
        "candidate_name": match.group(groups["candidate_name"]).strip(),
        "job_title": match.group(groups["job_title"]).strip(),
    }


def _unwrap_tracking_url(url: str) -> str:
    """Unwrap a Hireflix tracking URL to get the real destination."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "u" in params:
        return unquote(params["u"][0])
    return url


def extract_assessment_link(html_body: str, config: dict) -> str | None:
    """
    Extract the Hireflix admin interview link from email HTML body.

    First tries to find direct admin links. If none found, looks for tracking
    links and unwraps them.
    """
    # Try direct admin link
    direct_pattern = config["body_link_pattern"]
    match = re.search(direct_pattern, html_body)
    if match:
        return match.group(0)

    # Try tracking links that wrap an admin URL
    tracking_prefix = config.get("tracking_link_prefix", "")
    if tracking_prefix:
        # Find all tracking URLs with u= parameter
        tracking_pattern = re.escape(tracking_prefix) + r'[^\s"<>]+\?u=[^\s"<>]+'
        for tracking_match in re.finditer(tracking_pattern, html_body):
            tracking_url = tracking_match.group(0)
            # HTML entities in URLs
            tracking_url = tracking_url.replace("&amp;", "&")
            unwrapped = _unwrap_tracking_url(tracking_url)
            if re.match(direct_pattern, unwrapped):
                return unwrapped

    return None


def extract_candidate_name_from_body(html_body: str, config: dict) -> str | None:
    """Extract candidate name from email body as a fallback."""
    pattern = config.get("body_candidate_pattern")
    if not pattern:
        return None
    match = re.search(pattern, html_body)
    if match:
        return match.group(1).strip()
    return None


def parse_completion_email(subject: str, html_body: str, config: dict | None = None) -> dict | None:
    """
    Parse a Hireflix completion email.

    Returns dict with:
        - candidate_name: str
        - job_title: str
        - assessment_link: str | None
    Or None if the email doesn't match expected format.
    """
    if config is None:
        config = load_platform_config("hireflix")

    # Parse subject for candidate name and job title
    subject_data = parse_subject(subject, config)
    if not subject_data:
        return None

    # Extract assessment link from body
    assessment_link = extract_assessment_link(html_body, config)

    # Fallback: try body for candidate name if subject parse was partial
    if not subject_data.get("candidate_name"):
        body_name = extract_candidate_name_from_body(html_body, config)
        if body_name:
            subject_data["candidate_name"] = body_name

    return {
        "candidate_name": subject_data["candidate_name"],
        "job_title": subject_data["job_title"],
        "assessment_link": assessment_link,
    }
