import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..models.user import User
from ..services import google_auth_service
from ..utils.auth import create_access_token, create_refresh_token, verify_refresh_token, get_current_user
from ..utils.encryption import encrypt
from ..config import settings
from ..schemas.user_schema import UserResponse, UpdateProfileRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

_OAUTH_STATE_COOKIE = "oauth_state"
_COOKIE_MAX_AGE = 300  # 5 minutes — enough for any OAuth round-trip


class RefreshRequest(BaseModel):
    refresh_token: str


@router.get("/login")
@limiter.limit("20/minute")
def login(request: Request):
    """Redirect the user to the Google OAuth 2.0 consent screen."""
    auth_url, state = google_auth_service.get_authorization_url()
    response = RedirectResponse(url=auth_url)
    # Store the state in an HttpOnly, SameSite=Lax cookie so the callback
    # can verify it and prevent CSRF attacks.
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.FRONTEND_URL.startswith("https"),
    )
    return response


@router.get("/callback")
@limiter.limit("20/minute")
def oauth_callback(request: Request, code: str, state: str = "", db: Session = Depends(get_db)):
    """
    Handle the Google OAuth callback.

    1. Validate the state parameter against the cookie to prevent CSRF.
    2. Exchange authorization code for tokens.
    3. Fetch user email from Google.
    4. Upsert user record — Google refresh token is encrypted before storage.
    5. Issue a JWT access token (24 h) + refresh token (7 d) and redirect.
    """
    # ── CSRF check: compare state param with cookie using constant-time compare ──
    expected_state = request.cookies.get(_OAUTH_STATE_COOKIE, "")
    if not expected_state or not hmac.compare_digest(expected_state, state):
        logger.warning("OAuth state mismatch — possible CSRF attempt")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}?error=state_mismatch")

    try:
        tokens = google_auth_service.exchange_code_for_tokens(code)
    except Exception as exc:
        logger.error(f"OAuth token exchange failed: {exc}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}?error=oauth_failed")

    access_token = tokens.get("access_token")
    google_refresh_token = tokens.get("refresh_token")

    email = google_auth_service.get_user_email(access_token)
    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve user email from Google")

    user = db.query(User).filter(User.email == email).first()
    if user:
        # Update only when Google issues a new refresh token (not on every login)
        if google_refresh_token:
            user.refresh_token = encrypt(google_refresh_token)
    else:
        user = User(
            email=email,
            refresh_token=encrypt(google_refresh_token) if google_refresh_token else None,
        )
        db.add(user)

    db.commit()
    db.refresh(user)

    jwt_access = create_access_token(user.id)
    jwt_refresh = create_refresh_token(user.id)
    redirect_url = (
        f"{settings.FRONTEND_URL}"
        f"?token={jwt_access}"
        f"&refresh_token={jwt_refresh}"
        f"&email={email}"
    )
    response = RedirectResponse(url=redirect_url)
    # Clear the state cookie — it's single-use
    response.delete_cookie(key=_OAUTH_STATE_COOKIE)
    return response


@router.post("/refresh")
@limiter.limit("30/minute")
def refresh_token(request: Request, body: RefreshRequest, db: Session = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    The refresh token rotates on every call (rolling 7-day window), so the
    client must always store the latest pair returned by this endpoint.
    """
    user_id = verify_refresh_token(body.refresh_token)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update mutable profile fields (company_name, custom_prompt)."""
    if body.company_name is not None:
        current_user.company_name = body.company_name.strip() or None
    if body.custom_prompt is not None:
        current_user.custom_prompt = body.custom_prompt.strip() or None
    db.commit()
    db.refresh(current_user)
    return current_user
