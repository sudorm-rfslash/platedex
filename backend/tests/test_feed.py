"""The Home feed (/api/feed): sightings plus photos still waiting in Review."""

from conftest import jpeg, make_admin
from test_pipeline import drain, upload


def feed(client, **params):
    r = client.get("/api/feed", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def everything(client, **params):
    out, offset = [], 0
    while offset is not None:
        page = feed(client, offset=offset, limit=200, **params)
        out += page["items"]
        offset = page["next_offset"]
    return out


def test_newest_first_with_paging(seeded):
    first = feed(seeded)
    assert first["total"] == 60 and first["plates"] == 16 and first["spotters"] == 3
    assert len(first["items"]) == 48 and first["next_offset"] == 48
    rest = feed(seeded, offset=48)
    assert len(rest["items"]) == 12 and rest["next_offset"] is None
    times = [i["at"] for i in first["items"] + rest["items"]]
    assert times == sorted(times, reverse=True)
    assert len({i["key"] for i in first["items"] + rest["items"]}) == 60


def test_sorts(seeded):
    old = [i["at"] for i in everything(seeded, sort="old")]
    assert old == sorted(old)
    az = [i["plate"]["text"].replace("-", "") for i in everything(seeded, sort="az")]
    assert az == sorted(az)
    most = everything(seeded, sort="most")
    assert most[0]["plate"]["text"] == "7ABC123" and most[0]["n"] == 8
    assert [i["n"] for i in most] == sorted((i["n"] for i in most), reverse=True)


def test_filters(seeded):
    assert {i["user"]["username"] for i in everything(seeded, who="maya")} == {"maya"}
    mine = everything(seeded, who="mine")
    assert mine and {i["user"]["username"] for i in mine} == {"alex"}
    assert {i["plate"]["state"] for i in everything(seeded, states="CO")} == {"CO"}
    vanity = everything(seeded, vanity=True)
    assert vanity and all("vanity" in i["plate"]["tags"] or i["plate"]["meaning"] for i in vanity)
    missing = everything(seeded, missing=True)
    assert len(missing) == 12 and not any(i["located"] for i in missing)
    summer = everything(seeded, **{"from": "2026-06-01", "to": "2026-08-31"})
    assert summer and all("2026-06-01" <= i["at"][:10] <= "2026-08-31" for i in summer)
    assert feed(seeded, review=True)["total"] == 0


def test_unidentified_photo_shows_as_pending(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.boxes = []
    upload(client, jpeg(gps=None))
    drain()
    items = feed(client)["items"]
    assert len(items) == 1
    item = items[0]
    assert item["pending"] == "No plate found" and item["plate"] is None
    assert item["located"] is False and item["thumb_url"].endswith("/thumb")
    assert feed(client, review=True)["total"] == 1
    assert feed(client, states="TX")["total"] == 0
