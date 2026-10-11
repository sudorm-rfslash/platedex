import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, utcnow
from ..models import ROLES, ApiToken, Detection, Invite, Photo, Sighting, User
from ..pipeline import vlm
from ..security import admin, current_user, new_api_token, new_invite_token, sha256
from ..services import appsettings, jobs, shortcut
from .auth import invite_expiry
from .serialize import iso, user_json

router = APIRouter(prefix="/api", tags=["admin"])


# ---------- API tokens (any signed-in user, for their own account) ----------

def _token_json(t: ApiToken) -> dict:
    return {"id": t.id, "name": t.name, "prefix": t.prefix + "…", "created_at": iso(t.created_at),
            "last_used_at": iso(t.last_used_at)}


@router.get("/tokens")
def list_tokens(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.id.desc()))
    return [_token_json(t) for t in rows]


class TokenBody(BaseModel):
    name: str = Field("", max_length=128)


@router.post("/tokens")
def create_token(body: TokenBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "viewer":
        raise HTTPException(403, "Viewers can't upload, so they don't need tokens")
    raw = new_api_token()
    t = ApiToken(user_id=user.id, name=body.name.strip() or "New token", prefix=raw[:8], token_hash=sha256(raw))
    db.add(t)
    db.commit()
    return {**_token_json(t), "token": raw}


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(ApiToken, token_id)
    if t is None or t.user_id != user.id:
        raise HTTPException(404, "Token not found")
    db.delete(t)
    db.commit()
    return {"ok": True, "toast": "Token revoked"}


# ---------- Admin ----------

@router.get("/admin/users")
def admin_users(user: User = Depends(admin), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Sighting.user_id, func.count()).group_by(Sighting.user_id)).all())
    rows = db.scalars(select(User).order_by(User.id))
    return [
        {**user_json(u), "sightings": counts.get(u.id, 0), "last_active_at": iso(u.last_active_at),
         "disabled": u.disabled, "oidc_linked": bool(u.oidc_sub), "you": u.id == user.id}
        for u in rows
    ]


class UserPatch(BaseModel):
    role: str | None = None
    disabled: bool | None = None


@router.patch("/admin/users/{user_id}")
def admin_patch_user(user_id: int, body: UserPatch, user: User = Depends(admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.disabled.is_(False)))
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, "Unknown role")
        if u.role == "admin" and body.role != "admin" and admins <= 1:
            raise HTTPException(400, "Keep at least one admin")
        u.role = body.role
    if body.disabled is not None:
        if u.id == user.id:
            raise HTTPException(400, "You can't disable yourself")
        u.disabled = body.disabled
        u.session_version += 1
    db.commit()
    return {**user_json(u), "toast": f"{u.username} is now {u.role}"}


class InviteBody(BaseModel):
    role: str = "member"


@router.post("/admin/invites")
def create_invite(body: InviteBody, user: User = Depends(admin), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(400, "Unknown role")
    raw = new_invite_token()
    inv = Invite(token_hash=sha256(raw), role=body.role, created_by_id=user.id, expires_at=invite_expiry())
    db.add(inv)
    db.commit()
    url = get_settings().public_url.rstrip("/") + f"/invite/{raw}"
    return {"url": url, "expires_at": iso(inv.expires_at), "role": inv.role}


def _review_share(db: Session, thr: int) -> int | None:
    """What share of past OCR readings would have gone to Verify at this threshold."""
    rows = [d.ocr for d in db.scalars(select(Detection).where(Detection.ocr.is_not(None)).limit(2000))]
    confs = [r.get("conf", 0) for r in rows if r]
    if len(confs) < 5:
        return None
    return round(100 * sum(1 for c in confs if c * 100 < thr) / len(confs))


@router.get("/admin/settings")
def get_admin_settings(user: User = Depends(admin), db: Session = Depends(get_db)):
    s = appsettings.get_all(db)
    out = {k: s[k] for k in appsettings.LOCKABLE if k not in appsettings.SECRETS}
    return {
        **out,
        "oidc_client_secret_set": bool(s["oidc_client_secret"]),
        "oidc_enabled": appsettings.oidc_enabled(db),
        "locked": appsettings.locked(),
        "review_share": _review_share(db, int(s["ocr_threshold"])),
        "vlm": vlm.status(),
        "photos": db.scalar(select(func.count()).select_from(Photo)) or 0,
    }


class SettingsBody(BaseModel):
    """Only the fields sent are changed. For text fields, "" clears the value."""

    ocr_threshold: int | None = Field(None, ge=50, le=99)
    vlm_mode: Literal["auto", "always", "off"] | None = None
    local_login_enabled: bool | None = None
    oidc_issuer: str | None = Field(None, max_length=300)
    oidc_client_id: str | None = Field(None, max_length=300)
    oidc_client_secret: str | None = Field(None, max_length=500)
    oidc_admin_group: str | None = Field(None, max_length=128)
    oidc_auto_create: bool | None = None
    oidc_link_by_email: bool | None = None
    oidc_button_label: str | None = Field(None, max_length=40)
    map_style_light: str | None = Field(None, max_length=500)
    map_style_dark: str | None = Field(None, max_length=500)
    max_upload_mb: int | None = Field(None, ge=1, le=500)
    shortcut_url: str | None = Field(None, max_length=300)


def _url_ok(v: str | None) -> bool:
    return not v or v.startswith(("https://", "http://"))


@router.put("/admin/settings")
def put_admin_settings(body: SettingsBody, user: User = Depends(admin), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    locked = appsettings.locked()
    if hit := [locked[k] for k in changes if k in locked]:
        raise HTTPException(
            409, f"Set by {', '.join(hit)} in the server environment. Remove it there to change it here."
        )
    for k in ("oidc_issuer", "map_style_light", "map_style_dark"):
        if not _url_ok(changes.get(k)):
            raise HTTPException(400, "Addresses must start with https:// (or http:// on your own network)")
    if changes.get("shortcut_url") and shortcut.clean_icloud_url(changes["shortcut_url"]) is None:
        raise HTTPException(400, "That isn't an iCloud Shortcut link (https://www.icloud.com/shortcuts/…)")

    # Don't let an admin switch off passwords unless they can get back in with Pocket ID.
    after = {**appsettings.get_all(db), **{k: (v.strip() or None) if isinstance(v, str) else v
                                         for k, v in changes.items()}}
    if not after["local_login_enabled"] and ("local_login_enabled" in changes or not after["oidc_issuer"]):
        if not (after["oidc_issuer"] and after["oidc_client_id"]):
            raise HTTPException(400, "Set up Pocket ID before turning off password sign-in")
        if not user.oidc_sub:
            raise HTTPException(400, "Link your own account to Pocket ID first (Linked accounts), "
                                     "or you'd be locked out")

    for k, v in changes.items():
        appsettings.put(db, k, v)
    return get_admin_settings(user, db)


class OidcTest(BaseModel):
    issuer: str = Field(min_length=1, max_length=300)


@router.post("/admin/oidc/test")
def test_oidc(body: OidcTest, user: User = Depends(admin)):
    """Fetch the issuer's discovery document so a typo shows up before anyone tries to sign in."""
    import httpx

    issuer = body.issuer.strip().rstrip("/")
    if not _url_ok(issuer):
        return {"ok": False, "error": "The issuer must start with https://"}
    try:
        r = httpx.get(issuer + "/.well-known/openid-configuration", timeout=6, follow_redirects=True)
        r.raise_for_status()
        doc = r.json()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Couldn't reach {issuer}: {str(e)[:160]}"}
    if not isinstance(doc, dict) or "authorization_endpoint" not in doc:
        return {"ok": False, "error": "That address answered, but it isn't an OIDC provider"}
    if str(doc.get("issuer", "")).rstrip("/") != issuer:
        return {"ok": False, "error": f"The provider calls itself {doc.get('issuer')}. Use exactly that."}
    return {"ok": True, "callback": get_settings().public_url.rstrip("/") + "/api/auth/oidc/callback"}


def _reprocess_state(db: Session) -> dict:
    batch = appsettings.get(db, "reprocess_batch")
    if not batch:
        return {"state": "idle", "total": 0, "done": 0, "changed": 0}
    prog = jobs.batch_progress(db, batch)
    paused = appsettings.get(db, "reprocess_paused")
    if prog["total"] and prog["done"] >= prog["total"]:
        state = "done"
    else:
        state = "paused" if paused else "running"
    return {"state": state, **prog}


@router.get("/admin/reprocess")
def reprocess_status(user: User = Depends(admin), db: Session = Depends(get_db)):
    return _reprocess_state(db)


class ReprocessBody(BaseModel):
    action: str


@router.post("/admin/reprocess")
def reprocess(body: ReprocessBody, user: User = Depends(admin), db: Session = Depends(get_db)):
    cur = _reprocess_state(db)
    if body.action == "start":
        if cur["state"] in ("running", "paused"):
            raise HTTPException(409, "A reprocess is already in progress")
        batch = "rp-" + utcnow().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)
        for (pid,) in db.execute(select(Photo.id).order_by(Photo.id)):
            jobs.enqueue(db, "process_photo", {"photo_id": pid, "reprocess": True},
                         priority=jobs.PRIORITY_BACKGROUND, batch=batch)
        db.commit()
        appsettings.put(db, "reprocess_batch", batch)
        appsettings.put(db, "reprocess_paused", False)
    elif body.action == "pause":
        appsettings.put(db, "reprocess_paused", True)
    elif body.action == "resume":
        appsettings.put(db, "reprocess_paused", False)
    else:
        raise HTTPException(400, "Unknown action")
    return _reprocess_state(db)
