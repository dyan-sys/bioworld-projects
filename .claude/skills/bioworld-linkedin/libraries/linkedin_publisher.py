"""
LinkedIn Publisher Library for Bioworld LinkedIn Automation.

Handles posting to the Bioworld Ventures LinkedIn company page via API,
and token refresh management.

LinkedIn API docs: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
"""

import os

import requests

LINKEDIN_API_BASE = "https://api.linkedin.com/rest"
LINKEDIN_OAUTH_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REQUEST_TIMEOUT = 30


def _linkedin_headers(access_token: str) -> dict:
    """Return LinkedIn API request headers."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202401",
    }


def publish_post(access_token: str, org_id: str, text: str) -> dict:
    """
    Publish a text post to the Bioworld Ventures LinkedIn company page.

    Args:
        access_token: LinkedIn OAuth2 access token
        org_id: LinkedIn organization ID (numeric)
        text: Post text content

    Returns:
        API response dict with post ID on success
    """
    url = f"{LINKEDIN_API_BASE}/posts"

    payload = {
        "author": f"urn:li:organization:{org_id}",
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
    }

    headers = _linkedin_headers(access_token)
    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)

    if response.status_code == 201:
        post_id = response.headers.get("x-restli-id", "")
        return {"success": True, "post_id": post_id, "status": 201}
    else:
        return {
            "success": False,
            "status": response.status_code,
            "error": response.text,
        }


def refresh_access_token(client_id: str, client_secret: str,
                         refresh_token: str) -> dict:
    """
    Refresh the LinkedIn OAuth2 access token.

    Returns dict with new access_token and refresh_token.
    """
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    response = requests.post(
        LINKEDIN_OAUTH_URL, data=payload, timeout=REQUEST_TIMEOUT
    )

    if response.ok:
        data = response.json()
        return {
            "success": True,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in", 5184000),
        }
    else:
        return {
            "success": False,
            "status": response.status_code,
            "error": response.text,
        }


def get_linkedin_config() -> dict:
    """Load LinkedIn config from environment variables."""
    return {
        "access_token": os.environ.get("LINKEDIN_ACCESS_TOKEN", ""),
        "refresh_token": os.environ.get("LINKEDIN_REFRESH_TOKEN", ""),
        "client_id": os.environ.get("LINKEDIN_CLIENT_ID", ""),
        "client_secret": os.environ.get("LINKEDIN_CLIENT_SECRET", ""),
        "org_id": os.environ.get("BIOWORLD_LINKEDIN_ORG_ID", ""),
    }
