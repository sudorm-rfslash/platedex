import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, utcnow
from .models import ApiToken, User

_ph = PasswordHasher()
TOKEN_PREFIX = "pdx_"
CSRF_HEADER = "x-platedex"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_api_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(30)


def new_invite_token() -> str:
    return secrets.token_urlsafe(24)


def login_session(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    request.session["sv"] = user.session_version


def _touch(db: Session, user: User) -> None:
    now = utcnow()
    if not user.last_active_at or now - user.last_active_at > timedelta(minutes=5):
        user.last_active_at = now
        db.commit()


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        raw = auth[7:].strip()
        tok = db.scalar(select(ApiToken).where(ApiToken.token_hash == sha256(raw)))
        if tok is None:
            raise HTTPException(401, "Invalid API token")
        user = db.get(User, tok.user_id)
        if user is None or user.disabled:
            raise HTTPException(401, "Invalid API token")
        now = utcnow()
        if not tok.last_used_at or now - tok.last_used_at > timedelta(minutes=1):
            tok.last_used_at = now
            db.commit()
        request.state.via_token = True
        return user

    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or user.disabled or request.session.get("sv") != user.session_version:
        request.session.clear()
        return None
    # Cookie-authenticated writes must carry a custom header. Browsers never add it cross-site.
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "Missing CSRF header")
    _touch(db, user)
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Not signed in")
    return user


def member(user: User = Depends(current_user)) -> User:
    if user.role not in ("admin", "member"):
        raise HTTPException(403, "Viewers can't change anything")
    return user


def admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    return user
