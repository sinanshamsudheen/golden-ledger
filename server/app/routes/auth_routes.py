import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..services import google_auth_service
from ..utils.auth import create_access_token, get_current_user
from ..config import settings
from ..schemas.user_schema import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login():
    """Redirect the user to the Google OAuth 2.0 consent screen."""
    auth_url, _state = google_auth_service.get_authorization_url()
    return RedirectResponse(url=auth_url)


@router.get("/callback")
def oauth_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    """
    Handle the Google OAuth callback.

    1. Exchange authorization code for tokens.
    2. Fetch user email from Google.
    3. Upsert user record (create or update refresh token).
    4. Issue a JWT and redirect to the frontend.
    """
    try:
        tokens = google_auth_service.exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error(f"OAuth token exchange failed: {exc}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}?error=oauth_failed")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    email = google_auth_service.get_user_email(access_token)
    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from Google")

    user = db.query(User).filter(User.email == email).first()
    if user:
        # Update refresh token only when Google issues a new one
        if refresh_token:
            user.refresh_token = refresh_token
    else:
        user = User(email=email, refresh_token=refresh_token)
        db.add(user)

    db.commit()
    db.refresh(user)

    jwt_token = create_access_token(user.id)
    redirect_url = f"{settings.FRONTEND_URL}?token={jwt_token}&email={email}"
    return RedirectResponse(url=redirect_url)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return current_user
