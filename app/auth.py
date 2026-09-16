from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)

# Naive in-memory login throttle: {email: (failures, blocked_until)}.
_attempts: dict[str, tuple[int, datetime]] = {}
MAX_FAILURES = 8
BLOCK_SECONDS = 300


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": "founder",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRY_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def check_login_allowed(email: str) -> None:
    failures, blocked_until = _attempts.get(email, (0, datetime.min.replace(tzinfo=timezone.utc)))
    if datetime.now(timezone.utc) < blocked_until:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Slow down and try again.")


def record_login_failure(email: str) -> None:
    failures, _ = _attempts.get(email, (0, datetime.min.replace(tzinfo=timezone.utc)))
    failures += 1
    blocked = (
        datetime.now(timezone.utc) + timedelta(seconds=BLOCK_SECONDS)
        if failures >= MAX_FAILURES
        else datetime.min.replace(tzinfo=timezone.utc)
    )
    _attempts[email] = (failures, blocked)


def record_login_success(email: str) -> None:
    _attempts.pop(email, None)


def get_current_founder(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Studio sign-in required.")
    try:
        payload = jwt.decode(creds.credentials, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.")
    if payload.get("role") != "founder":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Studio only.")
    user = db.scalar(select(User).where(User.id == int(payload["sub"])))
    if user is None or user.role != "founder":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Studio sign-in required.")
    return user
