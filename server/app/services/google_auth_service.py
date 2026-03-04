import logging
from typing import Optional, Tuple, Dict, Any

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

from ..config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _build_client_config() -> Dict[str, Any]:
    return {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        }
    }


def get_authorization_url() -> Tuple[str, str]:
    """Return (auth_url, state) for initiating the OAuth flow."""
    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    return auth_url, state


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange an authorization code for access and refresh tokens."""
    flow = Flow.from_client_config(
        _build_client_config(),
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
    }


def refresh_access_token(refresh_token: str) -> Optional[Credentials]:
    """Use a stored refresh token to obtain a fresh access token."""
    try:
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
        credentials.refresh(Request())
        return credentials
    except Exception as exc:
        logger.error(f"Token refresh failed: {exc}")
        return None


def get_user_email(access_token: str) -> Optional[str]:
    """Fetch the authenticated user's email address from Google."""
    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("email")
    except Exception as exc:
        logger.error(f"Failed to fetch user email: {exc}")
        return None
