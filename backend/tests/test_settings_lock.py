"""Environment variables lock admin settings (services/appsettings.py)."""

import pytest
from conftest import make_admin

from platedex.config import get_settings
from platedex.db import db_session
from platedex.services import appsettings


@pytest.fixture()
def env(monkeypatch):
    """Pretend these variables were set in docker-compose.yml."""
    def set_env(**values):
        fake = get_settings().model_copy(update=values)
        object.__setattr__(fake, "__pydantic_fields_set__", set(values))
        monkeypatch.setattr(appsettings, "get_settings", lambda: fake)

    return set_env


def test_locked_setting_wins_and_is_read_only(client, env):
    make_admin(client)
    assert client.put("/api/admin/settings", json={"oidc_button_label": "Login"}).status_code == 200
    env(oidc_button_label="Pocket ID SSO", max_upload_mb=40)
    st = client.get("/api/admin/settings").json()
    assert st["oidc_button_label"] == "Pocket ID SSO" and st["max_upload_mb"] == 40
    assert st["locked"] == {"oidc_button_label": "OIDC_BUTTON_LABEL", "max_upload_mb": "MAX_UPLOAD_MB"}
    r = client.put("/api/admin/settings", json={"oidc_button_label": "Other"})
    assert r.status_code == 409 and "OIDC_BUTTON_LABEL" in r.json()["detail"]
    assert client.get("/api/auth/config").json()["oidc"]["label"] == "Pocket ID SSO"
    # Unlocked settings in the same request are refused too, so nothing half-applies.
    r = client.put("/api/admin/settings", json={"ocr_threshold": 70, "max_upload_mb": 10})
    assert r.status_code == 409
    assert client.get("/api/admin/settings").json()["ocr_threshold"] == 85


def test_env_value_sticks_after_removal(client, env):
    """The lockout fix: LOCAL_LOGIN_ENABLED=true, restart, sign in, remove it, still on."""
    make_admin(client)
    with db_session() as db:
        appsettings.put(db, "local_login_enabled", False)
    r = client.post("/api/auth/login", json={"username": "alex", "password": "password123"})
    assert r.status_code == 403
    env(local_login_enabled=True)
    with db_session() as db:
        assert appsettings.sync_env(db) == ["LOCAL_LOGIN_ENABLED"]  # what `platedex migrate` does at start
    env()  # variable removed again
    assert client.post("/api/auth/login", json={"username": "alex", "password": "password123"}).status_code == 200
    assert client.get("/api/admin/settings").json()["locked"] == {}


def test_secret_is_never_returned(client):
    make_admin(client)
    st = client.put("/api/admin/settings", json={"oidc_issuer": "https://id.example", "oidc_client_id": "abc",
                                                 "oidc_client_secret": "s3cret"}).json()
    assert "oidc_client_secret" not in st and st["oidc_client_secret_set"] is True and st["oidc_enabled"] is True
    assert "s3cret" not in client.get("/api/admin/settings").text
    assert client.get("/api/auth/config").json()["oidc"]["enabled"] is True


def test_cant_lock_yourself_out(client):
    make_admin(client)
    r = client.put("/api/admin/settings", json={"local_login_enabled": False})
    assert r.status_code == 400 and "Pocket ID" in r.json()["detail"]
    r = client.put("/api/admin/settings", json={"oidc_issuer": "https://id.example", "oidc_client_id": "abc",
                                                "local_login_enabled": False})
    assert r.status_code == 400 and "Link your own account" in r.json()["detail"]
    assert client.get("/api/admin/settings").json()["oidc_issuer"] is None  # nothing applied


def test_bad_values_are_refused(client):
    make_admin(client)
    assert client.put("/api/admin/settings", json={"oidc_issuer": "id.example"}).status_code == 400
    assert client.put("/api/admin/settings", json={"vlm_mode": "sometimes"}).status_code == 422
    assert client.put("/api/admin/settings", json={"max_upload_mb": 0}).status_code == 422


def test_upload_limit_setting_applies(client, fake_engine):
    from test_pipeline import jpeg

    make_admin(client)
    client.put("/api/admin/settings", json={"max_upload_mb": 1})
    big = jpeg(size=(3000, 3000)) + b"\0" * (1024 * 1024)
    r = client.post("/api/photos", files={"file": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
