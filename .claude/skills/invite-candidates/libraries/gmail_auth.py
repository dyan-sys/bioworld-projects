"""
Gmail OAuth2 Authentication Helper

Handles OAuth2 flow for Gmail API access:
- First run: opens browser for consent, saves token
- Subsequent runs: reuses token, auto-refreshes if expired

Scope: gmail.compose (narrowest scope for draft creation)
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def get_gmail_service(
    credentials_path: str | Path | None = None,
    token_path: str | Path | None = None,
) -> object:
    """
    Return an authenticated Gmail API service.

    Args:
        credentials_path: Path to OAuth2 credentials JSON.
            Defaults to GMAIL_CREDENTIALS_PATH env var or PROJECT_ROOT/credentials.json.
        token_path: Path to store/read the refresh token.
            Defaults to PROJECT_ROOT/local-data/gmail_token.json.

    Returns:
        googleapiclient.discovery.Resource for Gmail API.
    """
    project_root = Path(__file__).resolve().parents[4]

    if credentials_path is None:
        credentials_path = os.environ.get(
            "GMAIL_CREDENTIALS_PATH",
            str(project_root / "credentials.json"),
        )
    credentials_path = Path(credentials_path)

    if token_path is None:
        token_path = project_root / "local-data" / "gmail_token.json"
    token_path = Path(token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    creds = None

    # Load existing token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # Refresh or run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {credentials_path}. "
                    "Download OAuth2 credentials from Google Cloud Console "
                    "and save as credentials.json in the project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)
