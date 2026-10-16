


def texts(r):
    return [p["text"] for p in r.json()["plates"]]


def test_list_counts_and_headline(seeded):
    r = seeded.get("/api/plates")
    body = r.json()
    assert len(body["plates"]) == 16
    assert body["sightings"] == 60
    assert body["missing_location"] == 12
    gr = next(p for p in body["plates"] if p["text"] == "GR8FUL")
    assert gr["n"] == 6 and gr["places"] == ["Austin, TX", "Dallas, TX", "Santa Fe, NM"] and gr["spotters"] == 3


def test_search_syntax(seeded):
    assert texts(seeded.get("/api/plates", params={"q": "7AB*"})) == ["7ABC123"]
    assert set(texts(seeded.get("/api/plates", params={"q": "7A?12"}))) == {"7A?123"}
    assert "LUVU2" in texts(seeded.get("/api/plates", params={"q": "~LUVV2"}))
    assert "LUVU2" in texts(seeded.get("/api/plates", params={"q": "~1UVU2"}))
    assert texts(seeded.get("/api/plates", params={"q": "grateful"})) == ["GR8FUL"]
    assert set(texts(seeded.get("/api/plates", params={"q": "ski"}))) == {"NOTMYCAR", "CXN-S58"}
    assert texts(seeded.get("/api/plates", params={"q": "4821"})) == ["DHK-4821"]
    # A full plate query also surfaces the partial plate it could be
    assert "7A?123" in texts(seeded.get("/api/plates", params={"q": "7AB123"}))


def test_sorts(seeded):
    most = texts(seeded.get("/api/plates", params={"sort": "most"}))
    assert most[0] == "7ABC123"
    az = texts(seeded.get("/api/plates", params={"sort": "az"}))
    assert az == sorted(az, key=lambda t: t.replace("-", ""))
    dist = seeded.get("/api/plates", params={"sort": "dist", "origin": "33.45,-112.07"}).json()["plates"]
    assert dist[0]["dist_mi"] < 5
    places = texts(seeded.get("/api/plates", params={"sort": "places"}))
    assert places[0] == "7ABC123"


def test_filters(seeded):
    assert set(texts(seeded.get("/api/plates", params={"states": "CO"}))) == {"NOTMYCAR", "CXN-S58", "H8MNDAZ"}
    r = seeded.get("/api/plates", params={"users": "jordan", "min_n": 2})
    assert all(p["n"] >= 2 for p in r.json()["plates"])
    r = seeded.get("/api/plates", params={"near": "30.27,-97.74", "radius": 25})
    assert "GR8FUL" in texts(r) and "NOTMYCAR" not in texts(r)
    r = seeded.get("/api/plates", params={"from": "2026-06-01", "to": "2026-08-31", "tags": "vanity"})
    assert "GR8FUL" in texts(r)
    flat = seeded.get("/api/sightings", params={"missing": True}).json()
    assert flat["total"] == 12 and all(s["lat"] is None for s in flat["sightings"])


def test_map_points_skip_missing_locations(seeded):
    fc = seeded.get("/api/map/points").json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 48


def test_detail_duplicates_merge_undo(seeded):
    gr = next(p for p in seeded.get("/api/plates").json()["plates"] if p["text"] == "GR8FUL")
    detail = seeded.get(f"/api/plates/{gr['id']}").json()
    assert detail["n"] == 6 and detail["places"] == 3 and detail["spotters"] == 3
    assert detail["meaning"] == "grateful" and detail["state_name"] == "Texas"
    dup = detail["duplicates"][0]
    assert dup["text"] == "GR8FU1" and "L ↔ 1" in dup["reason"]
    m = seeded.post(f"/api/plates/{gr['id']}/merge", json={"source_id": dup["id"]}).json()
    assert m["toast"] == "Merged GR8FU1 into GR8FUL"
    detail = seeded.get(f"/api/plates/{gr['id']}").json()
    assert detail["n"] == 7 and detail["duplicates"] == []
    assert seeded.get(f"/api/plates/{dup['id']}").json() == {"redirect": gr["id"]}
    seeded.post(f"/api/merges/{m['merge_id']}/undo")
    assert seeded.get(f"/api/plates/{gr['id']}").json()["n"] == 6


def test_dismiss_duplicate(seeded):
    gr = next(p for p in seeded.get("/api/plates").json()["plates"] if p["text"] == "GR8FUL")
    dup = seeded.get(f"/api/plates/{gr['id']}").json()["duplicates"][0]
    seeded.post(f"/api/plates/{gr['id']}/dismiss", json={"other_id": dup["id"]})
    assert seeded.get(f"/api/plates/{gr['id']}").json()["duplicates"] == []
    seeded.post(f"/api/plates/{gr['id']}/undismiss", json={"other_id": dup["id"]})
    assert len(seeded.get(f"/api/plates/{gr['id']}").json()["duplicates"]) == 1


def test_split(seeded):
    gr = next(p for p in seeded.get("/api/plates").json()["plates"] if p["text"] == "GR8FUL")
    detail = seeded.get(f"/api/plates/{gr['id']}").json()
    ids = [s["id"] for s in detail["sightings"][:2]]
    r = seeded.post(f"/api/plates/{gr['id']}/split", json={"sighting_ids": ids, "text": "GR8FUN", "state": "TX"})
    assert r.status_code == 200 and r.json()["toast"] == "Split 2 sightings into GR8FUN"
    assert seeded.get(f"/api/plates/{gr['id']}").json()["n"] == 4
    new = seeded.get(f"/api/plates/{r.json()['plate_id']}").json()
    assert new["text"] == "GR8FUN" and new["n"] == 2
    all_ids = [s["id"] for s in seeded.get(f"/api/plates/{gr['id']}").json()["sightings"]]
    bad = seeded.post(f"/api/plates/{gr['id']}/split", json={"sighting_ids": all_ids, "text": "X1"})
    assert bad.status_code == 400


def test_edit_plate(seeded):
    gr = next(p for p in seeded.get("/api/plates").json()["plates"] if p["text"] == "LUVU2")
    r = seeded.patch(f"/api/plates/{gr['id']}", json={"tags": ["#Vanity", "sweet tooth"], "notes": "Pink Fiat"})
    body = r.json()
    assert body["tags"] == ["sweet-tooth", "vanity"] and body["notes"] == "Pink Fiat"
    assert body["notes_by"]["username"] == "alex"


def test_meta_and_exports(seeded):
    meta = seeded.get("/api/meta").json()
    assert [u["username"] for u in meta["users"]] == ["alex", "maya", "jordan"]
    assert "vanity" in meta["tags"] and "TX" in meta["states"]
    csv_text = seeded.get("/api/export.csv", params={"q": "GR8FUL"}).text
    assert csv_text.count("\n") == 8  # header + 6 GR8FUL + the GR8FU1 look-alike
    geo = seeded.get("/api/export.geojson").json()
    assert len(geo["features"]) == 48


def test_delete_plate_also_removes_plates_merged_into_it(seeded):
    plates = seeded.get("/api/plates").json()["plates"]
    target = next(p for p in plates if p["text"] == "GR8FUL")
    source = next(p for p in plates if p["text"] == "GR8FU1")
    assert seeded.post(f"/api/plates/{target['id']}/merge", json={"source_id": source["id"]}).status_code == 200
    r = seeded.delete(f"/api/plates/{target['id']}")
    assert r.json()["toast"] == "Deleted GR8FUL and 7 sightings"
    assert seeded.get(f"/api/plates/{source['id']}").status_code == 404
    body = seeded.get("/api/plates").json()
    assert len(body["plates"]) == 14 and body["sightings"] == 53


def test_members_only_can_delete(seeded):
    plate = seeded.get("/api/plates").json()["plates"][0]
    seeded.post("/api/auth/logout")
    assert seeded.delete(f"/api/plates/{plate['id']}").status_code in (401, 403)
