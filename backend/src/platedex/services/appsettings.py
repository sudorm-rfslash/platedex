"""Admin-adjustable settings stored in the database.

Each value comes from, in order:
1. An environment variable (LOCKABLE below). It locks the setting: More → Admin shows it read-only,
   and `sync_env` writes it to the database at every start, so it sticks after the variable is
   removed. That's also the lockout fix: LOCAL_LOGIN_ENABLED=true, recreate the container, sign in.
2. The value saved from More → Admin.
3. The built-in default (or the *_DEFAULT variables for the OCR threshold and AI reader mode).
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import Setting

log = logging.getLogger(__name__)

# setting key -> environment variable. The key is also the field name in config.Settings.
LOCKABLE: dict[str, str] = {
    "ocr_threshold": "OCR_THRESHOLD",
    "vlm_mode": "VLM_MODE",
    "local_login_enabled": "LOCAL_LOGIN_ENABLED",
    "oidc_issuer": "OIDC_ISSUER",
    "oidc_client_id": "OIDC_CLIENT_ID",
    "oidc_client_secret": "OIDC_CLIENT_SECRET",
    "oidc_admin_group": "OIDC_ADMIN_GROUP",
    "oidc_auto_create": "OIDC_AUTO_CREATE",
    "oidc_link_by_email": "OIDC_LINK_BY_EMAIL",
    "oidc_button_label": "OIDC_BUTTON_LABEL",
    "map_style_light": "MAP_STYLE_LIGHT",
    "map_style_dark": "MAP_STYLE_DARK",
    "max_upload_mb": "MAX_UPLOAD_MB",
    "shortcut_url": "SHORTCUT_URL",
}
SECRETS = {"oidc_client_secret"}  # never sent back to the browser


class Locked(Exception):
    def __init__(self, key: str):
        super().__init__(f"Set by {LOCKABLE[key]} in the server environment. Remove it there to change it here.")
        self.key = key


def defaults() -> dict[str, Any]:
    s = get_settings()
    out: dict[str, Any] = {k: Settings.model_fields[k].default for k in LOCKABLE}
    out.update({
        "ocr_threshold": s.ocr_threshold_default,  # percent; below this a read goes to Verify
        "vlm_mode": s.vlm_mode_default,  # auto | always | off
        "reprocess_paused": False,
        "reprocess_batch": None,
    })
    return out


def _check(key: str, value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip() or None
    if key == "shortcut_url" and value is not None:
        from .shortcut import clean_icloud_url

        clean = clean_icloud_url(str(value))
        if clean is None:
            raise ValueError("SHORTCUT_URL isn't an iCloud Shortcut link (https://www.icloud.com/shortcuts/…)")
        return clean
    return value


def env_overrides() -> dict[str, Any]:
    """Settings fixed by environment variables (set and non-empty), already validated."""
    s = get_settings()
    out = {}
    for key in LOCKABLE:
        if key in s.model_fields_set:
            try:
                out[key] = _check(key, getattr(s, key))
            except ValueError as e:
                log.error("Ignoring %s: %s", LOCKABLE[key], e)
    return out


def locked() -> dict[str, str]:
    """key -> environment variable name, for the settings the admin panel can't change."""
    return {k: LOCKABLE[k] for k in env_overrides()}


def get_all(db: Session) -> dict[str, Any]:
    out = defaults()
    for row in db.query(Setting).all():
        out[row.key] = row.value
    out.update(env_overrides())
    return out


def get(db: Session, key: str) -> Any:
    env = env_overrides()
    if key in env:
        return env[key]
    row = db.get(Setting, key)
    return row.value if row is not None else defaults().get(key)


def _store(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    elif row.value != value:
        row.value = value


def put(db: Session, key: str, value: Any) -> None:
    if key in env_overrides():
        raise Locked(key)
    _store(db, key, _check(key, value) if key in LOCKABLE else value)
    db.commit()


def sync_env(db: Session) -> list[str]:
    """Write environment-locked values to the database. Runs at every start (`platedex migrate`)."""
    env = env_overrides()
    for key, value in env.items():
        _store(db, key, value)
    db.commit()
    return [LOCKABLE[k] for k in env]


def oidc_enabled(db: Session) -> bool:
    return bool(get(db, "oidc_issuer") and get(db, "oidc_client_id"))
