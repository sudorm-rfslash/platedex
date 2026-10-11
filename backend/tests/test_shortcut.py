import plistlib

from conftest import make_admin

from platedex.services import shortcut


def test_template_shape():
    wf = plistlib.loads(plistlib.dumps(shortcut.build(), fmt=plistlib.FMT_BINARY))
    actions = wf["WFWorkflowActions"]
    q = wf["WFWorkflowImportQuestions"][0]
    first = actions[q["ActionIndex"]]
    assert first["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"
    assert q["ParameterKey"] in first["WFWorkflowActionParameters"]
    # Every block that opens (repeat, if) is closed with the same grouping id.
    groups: dict[str, list[int]] = {}
    for a in actions:
        p = a["WFWorkflowActionParameters"]
        if "GroupingIdentifier" in p:
            groups.setdefault(p["GroupingIdentifier"], []).append(p["WFControlFlowMode"])
    assert groups and all(modes[0] == 0 and modes[-1] == 2 for modes in groups.values())
    # Each variable points at an action that exists and comes earlier.
    seen: set[str] = set()
    for a in actions:
        p = a["WFWorkflowActionParameters"]
        for ref in _refs(p):
            assert ref in seen, ref
        seen.add(p["UUID"])
    upload = next(a for a in actions if a["WFWorkflowActionIdentifier"].endswith("downloadurl"))
    assert upload["WFWorkflowActionParameters"]["WFURL"]["Value"]["string"].endswith("/api/photos")


def _refs(v):
    if isinstance(v, dict):
        if "OutputUUID" in v:
            yield v["OutputUUID"]
        for x in v.values():
            yield from _refs(x)
    elif isinstance(v, list):
        for x in v:
            yield from _refs(x)


def test_icloud_link_setting(client):
    make_admin(client)
    assert client.get("/api/auth/config").json()["shortcut_url"] is None
    r = client.put("/api/admin/settings", json={"shortcut_url": "https://example.com/shortcuts/abc"})
    assert r.status_code == 400
    link = "https://icloud.com/shortcuts/0123456789ABCDEF0123456789abcdef/?x=1"
    r = client.put("/api/admin/settings", json={"shortcut_url": link})
    want = "https://www.icloud.com/shortcuts/0123456789abcdef0123456789abcdef"
    assert r.json()["shortcut_url"] == want
    assert client.get("/api/auth/config").json()["shortcut_url"] == want
    client.cookies.clear()
    assert client.get("/api/auth/config").json()["shortcut_url"] is None  # not shown to visitors
    client.post("/api/auth/login", json={"username": "alex", "password": "password123"})
    assert client.put("/api/admin/settings", json={"shortcut_url": ""}).json()["shortcut_url"] is None


def test_setup_code_token_uploads(client, fake_engine):
    """The token part of a setup code works as a Bearer token, as the Shortcut sends it."""
    from test_pipeline import jpeg

    make_admin(client)
    tok = client.post("/api/tokens", json={"name": "Shortcut · iPhone"}).json()["token"]
    code = f"https://plates.example#{tok}\n"
    raw = "".join(code.split()).split("#")[-1]
    client.cookies.clear()
    r = client.post("/api/photos", headers={"Authorization": f"Bearer {raw}"},
                    files={"file": ("IMG.HEIC", jpeg(), "image/jpeg")}, data={"capture_mode": "token"})
    assert r.status_code == 200, r.text
