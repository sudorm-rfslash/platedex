import numpy as np
import pytest
from conftest import jpeg, make_admin, probs_for

from platedex.pipeline import vlm as vlm_mod
from platedex.pipeline.engines import Box
from platedex.pipeline.fuse import fuse
from platedex.worker import run_once

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"


def drain():
    n = 0
    while run_once():
        n += 1
    return n


def upload(client, data=None, name="IMG_1.HEIC", **form):
    r = client.post("/api/photos", files={"file": (name, data or jpeg(), "image/jpeg")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def no_vlm(monkeypatch):
    def unavailable(*_a, **_k):
        raise vlm_mod.VlmUnavailable("off in tests")

    monkeypatch.setattr(vlm_mod, "read_plate", unavailable)


def vlm_says(monkeypatch, text, conf=0.9, state="TX"):
    calls = []

    def fake(crop, photo):
        calls.append(1)
        return vlm_mod.VlmReading(text=text, state=state, legible=bool(text), confidence=conf, alternatives=[],
                                  model="fake")

    monkeypatch.setattr(vlm_mod, "read_plate", fake)
    return calls


def test_fuse_votes_across_passes():
    a = probs_for("BXR7044", [0.9, 0.95, 0.95, 0.95, 0.55, 0.95, 0.95], alt={4: "O"})
    b = probs_for("BXR7044", [0.9, 0.95, 0.95, 0.95, 0.75, 0.95, 0.95], alt={4: "O"})
    r = fuse([a, b], ALPHABET)
    assert r.text == "BXR7044"
    assert r.candidates[0][0] == "BXR7044"
    assert any(t == "BXR7O44" for t, _ in r.candidates)
    assert 0.6 < r.char_conf[4] < 0.7


def test_confident_read_is_accepted(client, fake_engine, no_vlm):
    make_admin(client)
    p = upload(client)
    assert p["status"] == "queued"
    drain()
    photo = client.get(f"/api/photos?ids={p['id']}").json()[0]
    assert photo["status"] == "done"
    assert photo["summary"].startswith("Read GR8FUL")
    plates = client.get("/api/plates").json()["plates"]
    assert [x["text"] for x in plates] == ["GR8FUL"]
    assert plates[0]["state"] == "TX" and plates[0]["state_is_guess"] is True


def test_unsure_read_goes_to_verify_and_confirm_creates_sighting(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.mat = probs_for("8XR7O44", [0.55, 0.96, 0.94, 0.97, 0.42, 0.93, 0.95], alt={0: "B", 4: "0"})
    upload(client)
    drain()
    counts = client.get("/api/review/counts").json()
    assert counts["verify"]["mine"] == 1 and counts["badge"] == 1
    q = client.get("/api/review/queue?tab=verify").json()
    item = client.post(f"/api/review/items/{q['items'][0]['id']}/claim").json()
    assert item["reason"] and len(item["candidates"]) >= 2
    assert item["char_conf"][4] < 0.6
    r = client.post(f"/api/review/items/{item['id']}/confirm", json={"text": "BXR7044", "state": "WA"})
    assert r.status_code == 200 and r.json()["toast"] == "Confirmed BXR7044 · WA"
    assert client.get("/api/review/counts").json()["badge"] == 0
    plates = client.get("/api/plates").json()["plates"]
    assert plates[0]["text"] == "BXR7044" and plates[0]["state"] == "WA" and not plates[0]["state_is_guess"]


def test_disagreement_is_shown_and_never_auto_accepted(client, fake_engine, monkeypatch):
    make_admin(client)
    fake_engine.mat = probs_for("TX2CAL1", [0.97, 0.95, 0.92, 0.9, 0.93, 0.88, 0.61], alt={6: "I"})
    calls = vlm_says(monkeypatch, "TX2CALI", 0.88, "CA")
    upload(client)
    drain()
    assert calls, "low confidence should ask the VLM"
    item_id = client.get("/api/review/queue?tab=verify").json()["items"][0]["id"]
    item = client.get(f"/api/review/items/{item_id}").json()
    assert item["disagree"] is True
    assert item["ocr"]["text"] == "TX2CAL1" and item["vlm"]["text"] == "TX2CALI"
    assert item["text"] == "TX2CALI"  # the more confident reader wins the default
    assert item["state"] == "CA" and item["state_is_guess"] is False


def test_agreement_boosts_confidence(client, fake_engine, monkeypatch):
    make_admin(client)
    fake_engine.mat = probs_for("LUVU2", [0.9, 0.85, 0.7, 0.88, 0.95], alt={2: "U"})
    vlm_says(monkeypatch, "LUVU2", 0.9, "CA")
    upload(client)
    drain()
    assert client.get("/api/review/counts").json()["badge"] == 0
    assert client.get("/api/plates").json()["plates"][0]["text"] == "LUVU2"


def test_drawn_box_is_read_and_stays_in_identify(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.boxes = []
    p = upload(client)
    drain()
    q = client.get("/api/review/queue?tab=identify").json()
    assert q["total"] == 1
    item = client.get(f"/api/review/items/{q['items'][0]['id']}").json()
    assert item["reason"] == "OCR found no plate." and item["has_reading"] is False
    r = client.post(f"/api/review/items/{item['id']}/box", json={"bbox": [0.1, 0.3, 0.3, 0.12]})
    assert r.json()["status"] == "reading"
    # Still counted under Identify while it's being read
    assert client.get("/api/review/counts").json()["identify"]["mine"] == 1
    drain()
    item = client.get(f"/api/review/items/{item['id']}").json()
    assert item["status"] == "needs_identify" and item["has_reading"] is True
    assert item["text"] == "GR8FUL" and item["source"] == "manual_box"
    counts = client.get("/api/review/counts").json()
    assert counts["verify"]["mine"] == 0 and counts["identify"]["mine"] == 1
    # Confirm right from Identify
    r = client.post(f"/api/review/items/{item['id']}/confirm", json={"text": item["text"], "state": "TX"})
    assert r.status_code == 200
    assert client.get("/api/review/counts").json()["badge"] == 0
    assert client.get(f"/api/photos?ids={p['id']}").json()[0]["status"] == "done"


def test_remove_wrong_box(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.boxes = []
    p = upload(client)
    drain()
    item_id = client.get("/api/review/queue?tab=identify").json()["items"][0]["id"]
    client.post(f"/api/review/items/{item_id}/box", json={"bbox": [0.1, 0.3, 0.3, 0.12]})
    drain()
    r = client.post(f"/api/review/items/{item_id}/clear-box").json()
    assert r["deleted"] is False and r["bbox"] is None and r["text"] == "" and r["has_reading"] is False
    assert r["status"] == "needs_identify" and r["reason"].startswith("Box removed")
    # An extra plate added by mistake disappears entirely
    added = client.post(f"/api/photos/{p['id']}/detections", json={"bbox": [0.5, 0.5, 0.3, 0.1]}).json()
    assert client.post(f"/api/review/items/{added['id']}/clear-box").status_code == 409  # still reading
    drain()
    assert client.get(f"/api/review/items/{added['id']}").json()["has_reading"] is True
    assert client.post(f"/api/review/items/{added['id']}/clear-box").json()["deleted"] is True
    assert client.get(f"/api/review/items/{added['id']}").status_code == 404
    assert client.get("/api/review/counts").json()["identify"]["mine"] == 1


def test_verify_item_with_wrong_area_goes_back_to_identify(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.mat = probs_for("8XR7O44", [0.55, 0.96, 0.94, 0.97, 0.42, 0.93, 0.95], alt={0: "B", 4: "0"})
    upload(client)
    drain()
    item_id = client.get("/api/review/queue?tab=verify").json()["items"][0]["id"]
    r = client.post(f"/api/review/items/{item_id}/clear-box").json()
    assert r["status"] == "needs_identify"
    counts = client.get("/api/review/counts").json()
    assert counts["verify"]["mine"] == 0 and counts["identify"]["mine"] == 1


def test_box_tightens_to_the_plate_the_user_framed(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.boxes = []
    upload(client, jpeg(size=(1000, 800)))
    drain()
    item_id = client.get("/api/review/queue?tab=identify").json()["items"][0]["id"]
    # Drawn box: x 150–320, y 288–384 px. The detector searches a 25% margin around it
    # (origin 108, 264), so these boxes are relative to that search area.
    decoy = Box(0, 0, 62, 26, 0.95)  # confident, but mostly outside the drawn box
    framed = Box(72, 36, 182, 86, 0.6)  # absolute 180–290 x 300–350, inside the drawn box
    fake_engine.boxes = [decoy, framed]
    client.post(f"/api/review/items/{item_id}/box", json={"bbox": [0.15, 0.36, 0.17, 0.12]})
    drain()
    bbox = client.get(f"/api/review/items/{item_id}").json()["bbox"]
    x_px, y_px, w_px = bbox[0] * 1000, bbox[1] * 800, bbox[2] * 1000
    assert 170 < x_px < 182 and 290 < y_px < 300 and w_px < 125  # the framed plate, lightly padded


def test_identify_actions(client, fake_engine, no_vlm):
    make_admin(client)
    fake_engine.boxes = []
    for i in range(3):
        upload(client, jpeg(color=(i, 2, 3)), name=f"{i}.jpg")
    drain()
    ids = [x["id"] for x in client.get("/api/review/queue?tab=identify").json()["items"]]
    assert client.post(f"/api/review/items/{ids[0]}/no-plate").json()["toast"] == "Marked: no plate in photo"
    assert "unidentified" in client.post(f"/api/review/items/{ids[1]}/keep").json()["toast"]
    r = client.post(f"/api/review/items/{ids[2]}/type", json={"text": "7a?123", "state": "CA"})
    assert r.json()["toast"] == "Saved partial plate 7A?123 · CA"
    plates = client.get("/api/plates").json()["plates"]
    assert plates[0]["partial"] is True and "partial" in plates[0]["tags"]
    assert client.get("/api/review/counts").json()["badge"] == 0


def test_burst_photos_make_one_sighting(client, fake_engine, no_vlm):
    make_admin(client)
    upload(client, jpeg(when="2026:10:09 17:42:00"), name="a.jpg")
    upload(client, jpeg(when="2026:10:09 17:42:20", color=(1, 1, 1)), name="b.jpg")
    upload(client, jpeg(when="2026:10:10 09:00:00", color=(2, 2, 2)), name="c.jpg")
    drain()
    plates = client.get("/api/plates").json()["plates"]
    assert plates[0]["n"] == 2


def test_duplicate_upload_is_deduped(client, fake_engine, no_vlm):
    make_admin(client)
    data = jpeg()
    first = upload(client, data)
    second = upload(client, data)
    assert second["duplicate"] is True and second["id"] == first["id"]


def test_missing_location_uses_client_values(client, fake_engine, no_vlm):
    make_admin(client)
    p = upload(client, jpeg(gps=None, when=None), lat="39.7392", lon="-104.9903", location_source="manual",
               taken_at="2026-10-09T17:42:00-06:00", time_source="manual")
    assert p["location_source"] == "manual" and p["taken_at_source"] == "manual"
    assert p["taken_at"] == "2026-10-09T23:42:00Z"
    assert p["tz"] == "America/Denver"


def test_failed_photo_is_marked(client, fake_engine, no_vlm, monkeypatch):
    make_admin(client)
    from platedex.pipeline import process

    def boom(*a, **k):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(process, "read_region", boom)
    p = upload(client)
    drain()
    photo = client.get(f"/api/photos?ids={p['id']}").json()[0]
    assert photo["status"] == "failed" and "model exploded" in photo["summary"]
    monkeypatch.undo()
    engines_ok = client.post(f"/api/photos/{p['id']}/retry").json()
    assert engines_ok["status"] == "queued"
    # A second tap while it's still queued doesn't add another job.
    client.post(f"/api/photos/{p['id']}/retry")
    from platedex.db import db_session
    from platedex.models import Job

    with db_session() as db:
        queued = [j for j in db.query(Job).filter(Job.status == "queued") if j.payload.get("photo_id") == p["id"]]
    assert len(queued) == 1


def test_reprocess_keeps_confirmed_and_flags_changes(client, fake_engine, no_vlm):
    make_admin(client)
    upload(client)
    drain()
    assert client.get("/api/plates").json()["plates"][0]["text"] == "GR8FUL"
    fake_engine.mat = probs_for("GR8FU1", 0.97)
    assert client.post("/api/admin/reprocess", json={"action": "start"}).json()["state"] == "running"
    drain()
    st = client.get("/api/admin/reprocess").json()
    assert st == {"state": "done", "total": 1, "done": 1, "changed": 1}
    item = client.get("/api/review/queue?tab=verify").json()["items"][0]
    assert item["title"] == "GR8FU1"
    client.post(f"/api/review/items/{item['id']}/confirm", json={"text": "GR8FUL", "state": "TX"})
    plates = client.get("/api/plates").json()["plates"]
    assert [p["text"] for p in plates] == ["GR8FUL"] and plates[0]["n"] == 1


def test_vlm_reply_parsing():
    r = vlm_mod.parse_response('```json\n{"plate_text":"gr8-ful","state":"Texas","legible":true,'
                               '"confidence":91,"alternatives":["GR8FU1","gr8ful"]}\n```', "m")
    assert r.text == "GR8FUL" and r.state == "TX" and r.confidence == 0.91
    assert r.alternatives == ["GR8FU1"]
    with pytest.raises(ValueError):
        vlm_mod.parse_response("no json here", "m")


def test_blur_score_orders_sharp_before_blurry():
    import cv2

    from platedex.pipeline.imaging import blur_score

    rng = np.random.default_rng(0)
    sharp = (rng.random((400, 400, 3)) * 255).astype(np.uint8)
    blurry = cv2.GaussianBlur(sharp, (0, 0), 6)
    assert blur_score(sharp) < 0.3 < blur_score(blurry)

    from platedex.pipeline.imaging import crop_blur_score

    plate = np.full((60, 200, 3), 235, np.uint8)
    cv2.putText(plate, "GR8FUL", (14, 46), cv2.FONT_HERSHEY_DUPLEX, 1.5, (30, 20, 10), 3)
    soft = cv2.GaussianBlur(plate, (0, 0), 2.5)
    assert crop_blur_score(plate) < crop_blur_score(soft)


def test_avif_is_read_and_other_formats_are_refused(client, fake_engine, no_vlm):
    from io import BytesIO

    from PIL import Image

    make_admin(client)

    def enc(fmt: str) -> bytes:
        b = BytesIO()
        Image.new("RGB", (640, 480), "white").save(b, fmt)
        return b.getvalue()

    p = upload(client, enc("AVIF"), name="PXL_1.avif")
    drain()
    photo = client.get(f"/api/photos?ids={p['id']}").json()[0]
    assert photo["status"] != "failed"
    assert client.get(f"/api/photos/{p['id']}/thumb").status_code == 200
    r = client.post("/api/photos", files={"file": ("x.jpg", enc("GIF"), "image/jpeg")})
    assert r.status_code == 415 and "RAW/DNG" in r.json()["detail"]


def test_no_ollama_url_means_ocr_only(client, fake_engine, monkeypatch):
    from platedex.config import get_settings
    from platedex.pipeline import process

    no_ollama = get_settings().model_copy(update={"ollama_url": None})
    monkeypatch.setattr(process, "get_settings", lambda: no_ollama)
    monkeypatch.setattr(vlm_mod, "get_settings", lambda: no_ollama)
    make_admin(client)
    fake_engine.mat = probs_for("TX2CAL1", [0.97, 0.95, 0.92, 0.9, 0.93, 0.88, 0.61], alt={6: "I"})
    calls = vlm_says(monkeypatch, "TX2CALI", 0.88, "CA")
    upload(client)
    drain()
    assert not calls, "without OLLAMA_URL the AI reader is never asked"
    assert vlm_mod.status()["configured"] is False
