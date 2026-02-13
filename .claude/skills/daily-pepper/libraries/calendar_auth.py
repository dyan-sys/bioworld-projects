"""
Google Calendar OAuth2 Authentication Helper

Handles OAuth2 flow for Google Calendar API (read-only):
- First run: opens browser for consent, saves token
- Subsequent runs: reuses token, auto-refreshes if expired

Scope: calendar.readonly (minimal read-only access)
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_calendar_service(
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
    scopes: list[str] | None = None,
) -> object:
    """
    Return an authenticated Google Calendar API service.

    Args:
        credentials_path: Path to OAuth2 credentials JSON.
            Defaults to PROJECT_ROOT/Google-credentials.json.
        token_path: Path to store/read the refresh token.
            Defaults to PROJECT_ROOT/local-data/calendar_token.json.
        scopes: OAuth2 scopes to request. Defaults to DEFAULT_SCOPES.

    Returns:
        Google Calendar API service object.
    """
    scopes = scopes or DEFAULT_SCOPES

    project_root = Path(__file__).resolve().parents[4]

    if credentials_path is None:
        credentials_path = os.environ.get(
            "GOOGLE_CREDENTIALS_PATH",
            str(project_root / "Google-credentials.json"),
        )
    credentials_path = Path(credentials_path)

    if token_path is None:
        token_path = project_root / "local-data" / "calendar_token.json"
    token_path = Path(token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    creds = None

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

        # Check if existing token covers all requested scopes
        if creds and creds.scopes and not set(scopes).issubset(set(creds.scopes)):
            creds = None

    # Refresh or run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {credentials_path}. "
                    "Download OAuth2 credentials from Google Cloud Console "
                    "and save as Google-credentials.json in the project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), scopes
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)
