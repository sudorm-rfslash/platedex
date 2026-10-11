from conftest import jpeg, make_admin


def test_first_run_setup_and_login(client):
    assert client.get("/api/auth/config").json()["needs_setup"] is True
    me = make_admin(client)
    assert me["role"] == "admin"
    assert client.get("/api/auth/config").json()["needs_setup"] is False
    # Setup only works once
    assert client.post("/api/auth/setup", json={"username": "eve", "password": "password123"}).status_code == 409
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"username": "alex", "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "ALEX", "password": "password123"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "alex"


def test_writes_need_csrf_header(client):
    make_admin(client)
    del client.headers["x-platedex"]
    r = client.post("/api/tokens", json={"name": "x"})
    assert r.status_code == 403
    client.headers["x-platedex"] = "1"
    assert client.post("/api/tokens", json={"name": "x"}).status_code == 200


def test_invite_register_and_roles(client):
    make_admin(client)
    url = client.post("/api/admin/invites", json={"role": "viewer"}).json()["url"]
    token = url.rsplit("/", 1)[-1]
    assert client.get(f"/api/auth/invite/{token}").json() == {"valid": True, "role": "viewer"}
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"token": token, "username": "Jordan", "password": "password123"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "jordan" and r.json()["role"] == "viewer"
    # Invite can't be reused
    assert client.get(f"/api/auth/invite/{token}").json()["valid"] is False
    # Viewers can't upload or reach admin
    files = {"file": ("a.jpg", jpeg(), "image/jpeg")}
    assert client.post("/api/photos", files=files).status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_api_token_upload(client, fake_engine):
    make_admin(client)
    tok = client.post("/api/tokens", json={"name": "iPhone"}).json()
    assert tok["token"].startswith("pdx_")
    listed = client.get("/api/tokens").json()
    assert listed[0]["name"] == "iPhone" and "token" not in listed[0]
    client.post("/api/auth/logout")
    client.cookies.clear()
    del client.headers["x-platedex"]
    files = {"file": ("IMG_1.HEIC", jpeg(), "image/jpeg")}
    r = client.post("/api/photos", files=files, headers={"Authorization": f"Bearer {tok['token']}"})
    assert r.status_code == 200, r.text
    assert r.json()["place"] is not None or r.json()["lat"] is not None
    bad = client.post("/api/photos", files=files, headers={"Authorization": "Bearer pdx_wrong"})
    assert bad.status_code == 401


def test_last_admin_cannot_be_demoted(client):
    me = make_admin(client)
    r = client.patch(f"/api/admin/users/{me['id']}", json={"role": "member"})
    assert r.status_code == 400


def test_password_change_invalidates_other_sessions(client, app):
    from fastapi.testclient import TestClient

    make_admin(client)
    with TestClient(app) as other:
        other.headers["x-platedex"] = "1"
        other.post("/api/auth/login", json={"username": "alex", "password": "password123"})
        assert other.get("/api/auth/me").status_code == 200
        client.post("/api/auth/password", json={"current": "password123", "new": "newpassword1"})
        assert other.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200
