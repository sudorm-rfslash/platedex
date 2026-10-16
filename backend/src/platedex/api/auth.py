import logging
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, utcnow
from ..models import Invite, User
from ..security import current_user, hash_password, login_session, optional_user, sha256, verify_password
from ..services import appsettings
from .serialize import count_sightings, iso, user_json

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

PALETTE = ["#1D4ED8", "#B4441A", "#0F6B63", "#7C3AED", "#A16207", "#BE185D", "#047857", "#4338CA", "#9F1239"]
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")


def user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def next_color(db: Session) -> str:
    return PALETTE[user_count(db) % len(PALETTE)]


def clean_username(raw: str) -> str:
    return re.sub(r"[^a-z0-9._-]", "", (raw or "").strip().lower())[:32]


def unique_username(db: Session, base: str) -> str:
    base = clean_username(base) or "user"
    if len(base) < 2:
        base = base + "1"
    name, i = base, 2
    while db.scalar(select(User).where(User.username == name)) is not None:
        name = f"{base[:29]}{i}"
        i += 1
    return name


def me_json(db: Session, u: User) -> dict:
    return {
        **user_json(u),
        "email": u.email,
        "has_password": bool(u.password_hash),
        "password_changed_at": iso(u.password_changed_at),
        "oidc_linked": bool(u.oidc_sub),
        "oidc_linked_at": iso(u.oidc_linked_at),
        "sightings": count_sightings(db, u.id),
    }


@router.get("/config")
def auth_config(db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    a = appsettings.get_all(db)
    return {
        "local_login": a["local_login_enabled"],
        "oidc": {"enabled": appsettings.oidc_enabled(db), "label": a["oidc_button_label"] or "Pocket ID"},
        "needs_setup": user_count(db) == 0,
        "map": {"light": a["map_style_light"], "dark": a["map_style_dark"]},
        "max_upload_mb": a["max_upload_mb"],
        # Only for signed-in members: viewers can't upload, and visitors don't need it.
        "shortcut_url": appsettings.get(db, "shortcut_url") if user and user.role != "viewer" else None,
    }


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/setup")
def setup(body: Credentials, request: Request, db: Session = Depends(get_db)):
    """Create the first (admin) account. Only works while there are no users."""
    if user_count(db) > 0:
        raise HTTPException(409, "Already set up")
    username = clean_username(body.username)
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Usernames are 2–32 characters: letters, numbers, . _ -")
    if len(body.password) < 8:
        raise HTTPException(400, "Use at least 8 characters for the password")
    u = User(username=username, password_hash=hash_password(body.password), role="admin",
             color=PALETTE[0], password_changed_at=utcnow())
    db.add(u)
    db.commit()
    login_session(request, u)
    return me_json(db, u)


@router.post("/login")
def login(body: Credentials, request: Request, db: Session = Depends(get_db)):
    if not appsettings.get(db, "local_login_enabled"):
        raise HTTPException(403, "Password sign-in is turned off")
    u = db.scalar(select(User).where(User.username == clean_username(body.username)))
    if u is None or u.disabled or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    login_session(request, u)
    u.last_active_at = utcnow()
    db.commit()
    return me_json(db, u)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_json(db, user)


class PasswordChange(BaseModel):
    current: str | None = None
    new: str = Field(min_length=8, max_length=256)


@router.post("/password")
def change_password(body: PasswordChange, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if user.password_hash and not verify_password(body.current or "", user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    user.password_hash = hash_password(body.new)
    user.password_changed_at = utcnow()
    user.session_version += 1
    db.commit()
    login_session(request, user)
    return me_json(db, user)


def _invite(db: Session, token: str) -> Invite | None:
    inv = db.scalar(select(Invite).where(Invite.token_hash == sha256(token)))
    if inv is None or inv.used_at is not None or inv.expires_at < utcnow():
        return None
    return inv


@router.get("/invite/{token}")
def invite_info(token: str, db: Session = Depends(get_db)):
    inv = _invite(db, token)
    return {"valid": inv is not None, "role": inv.role if inv else None}


class Register(Credentials):
    token: str


@router.post("/register")
def register(body: Register, request: Request, db: Session = Depends(get_db)):
    inv = _invite(db, body.token)
    if inv is None:
        raise HTTPException(400, "This invite link is invalid or has expired")
    username = clean_username(body.username)
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Usernames are 2–32 characters: letters, numbers, . _ -")
    if db.scalar(select(User).where(User.username == username)) is not None:
        raise HTTPException(409, "That username is taken")
    if len(body.password) < 8:
        raise HTTPException(400, "Use at least 8 characters for the password")
    u = User(username=username, password_hash=hash_password(body.password), role=inv.role,
             color=next_color(db), password_changed_at=utcnow())
    db.add(u)
    db.flush()
    inv.used_by_id, inv.used_at = u.id, utcnow()
    db.commit()
    login_session(request, u)
    return me_json(db, u)


# ---------- OIDC (Pocket ID) ----------

_oauth = None
_oauth_key: tuple | None = None


def oauth_client(db: Session):
    """The OIDC client for the current settings. Rebuilt when an admin changes them."""
    global _oauth, _oauth_key
    if not appsettings.oidc_enabled(db):
        raise HTTPException(404, "OIDC is not configured")
    a = appsettings.get_all(db)
    key = (a["oidc_issuer"].rstrip("/"), a["oidc_client_id"], a["oidc_client_secret"])
    if _oauth is None or key != _oauth_key:
        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        oauth.register(
            "oidc",
            server_metadata_url=key[0] + "/.well-known/openid-configuration",
            client_id=key[1],
            client_secret=key[2] or None,
            client_kwargs={"scope": "openid email profile groups", "code_challenge_method": "S256"},
        )
        _oauth, _oauth_key = oauth, key
    return _oauth.oidc


@router.get("/oidc/start")
async def oidc_start(request: Request, link: bool = False, invite: str | None = None,
                     user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    client = oauth_client(db)
    request.session["oidc_link"] = bool(link and user)
    request.session["oidc_invite"] = invite
    redirect_uri = get_settings().public_url.rstrip("/") + "/api/auth/oidc/callback"
    return await client.authorize_redirect(request, redirect_uri)


def _fail(msg: str) -> RedirectResponse:
    from urllib.parse import quote

    return RedirectResponse(f"/login?error={quote(msg)}", status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    a = appsettings.get_all(db)
    client = oauth_client(db)
    try:
        token = await client.authorize_access_token(request)
    except Exception as e:  # noqa: BLE001
        log.warning("OIDC callback failed: %s", e)
        return _fail("Sign-in with Pocket ID failed. Try again.")
    info = token.get("userinfo") or await client.userinfo(token=token)
    issuer = a["oidc_issuer"].rstrip("/")
    sub = str(info.get("sub") or "")
    if not sub:
        return _fail("Pocket ID didn't return a user id")
    groups = info.get("groups") or []
    is_admin_group = bool(a["oidc_admin_group"] and a["oidc_admin_group"] in groups)
    linking = request.session.pop("oidc_link", False)
    invite_token = request.session.pop("oidc_invite", None)
    current_uid = request.session.get("uid")

    u = db.scalar(select(User).where(User.oidc_issuer == issuer, User.oidc_sub == sub))
    if linking and current_uid:
        me_ = db.get(User, current_uid)
        if u is not None and u.id != current_uid:
            return RedirectResponse("/more?error=That+Pocket+ID+account+is+linked+to+another+user", 302)
        if me_ is not None:
            me_.oidc_issuer, me_.oidc_sub, me_.oidc_linked_at = issuer, sub, utcnow()
            db.commit()
            return RedirectResponse("/more?linked=1", 302)

    email = info.get("email")
    if u is None and email and info.get("email_verified", True) and a["oidc_link_by_email"]:
        u = db.scalar(select(User).where(func.lower(User.email) == email.lower(), User.oidc_sub.is_(None)))
        if u is not None:
            u.oidc_issuer, u.oidc_sub, u.oidc_linked_at = issuer, sub, utcnow()
    if u is None:
        inv = _invite(db, invite_token) if invite_token else None
        if not (a["oidc_auto_create"] or inv or user_count(db) == 0):
            return _fail("Your Pocket ID account isn't invited to Platedex yet")
        role = "admin" if (user_count(db) == 0 or is_admin_group) else (inv.role if inv else "member")
        u = User(
            username=unique_username(db, info.get("preferred_username") or (email or "").split("@")[0] or "user"),
            display_name=info.get("name"),
            email=email,
            role=role,
            color=next_color(db),
            oidc_issuer=issuer,
            oidc_sub=sub,
            oidc_linked_at=utcnow(),
        )
        db.add(u)
        db.flush()
        if inv:
            inv.used_by_id, inv.used_at = u.id, utcnow()
    if u.disabled:
        return _fail("This account is disabled")
    if is_admin_group and u.role != "admin":
        u.role = "admin"
    if email and not u.email:
        u.email = email
    u.last_active_at = utcnow()
    db.commit()
    login_session(request, u)
    return RedirectResponse("/", status_code=302)


@router.post("/oidc/unlink")
def oidc_unlink(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.password_hash:
        raise HTTPException(400, "Set a password first, or you won't be able to sign in")
    user.oidc_issuer = user.oidc_sub = None
    user.oidc_linked_at = None
    db.commit()
    return me_json(db, user)


def invite_expiry():
    return utcnow() + timedelta(days=7)
