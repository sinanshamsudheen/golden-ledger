from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.user import User

_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_HOURS = 24   # short-lived; refresh before expiry
_REFRESH_TOKEN_EXPIRE_DAYS = 7    # rolling window — renewed on each refresh

_security = HTTPBearer(auto_error=False)


def create_access_token(user_id: int) -> str:
    """Create a short-lived (24 h) signed JWT access token."""
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=_ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Create a 7-day signed JWT refresh token (rolling window)."""
    expire = datetime.now(tz=timezone.utc) + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def verify_refresh_token(token: str) -> int:
    """
    Validate a refresh token and return the user_id.
    Raises HTTP 401 if invalid, expired, or wrong type.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that validates the Bearer access token and returns the current user.
    Raises HTTP 401 if the token is missing, wrong type, or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[_ALGORITHM]
        )
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        user_id: int = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
