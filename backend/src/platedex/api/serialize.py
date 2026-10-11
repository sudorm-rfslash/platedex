import hashlib
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Detection, Photo, Plate, Sighting, User
from ..services.platetext import normalize, skeleton


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def user_json(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "username": u.username, "name": u.display_name or u.username, "color": u.color, "role": u.role}


def plate_brief(p: Plate) -> dict:
    return {
        "id": p.id,
        "text": p.text,
        "state": p.state,
        "state_is_guess": p.state_is_guess,
        "partial": p.is_partial,
        "meaning": p.meaning,
        "tags": p.tags or [],
    }


def sighting_json(s: Sighting) -> dict:
    return {
        "id": s.id,
        "plate_id": s.plate_id,
        "plate": plate_brief(s.plate) if s.plate else None,
        "read_text": s.read_text,
        "seen_at": iso(s.seen_at),
        "tz": s.tz_name,
        "lat": s.lat,
        "lon": s.lon,
        "place": s.place_name,
        "user": user_json(s.user),
        "photo_id": s.photo_id,
        "detection_id": s.detection_id,
        "crop_url": f"/api/detections/{s.detection_id}/crop" if s.detection_id else None,
        "thumb_url": f"/api/photos/{s.photo_id}/thumb" if s.photo_id else None,
        "notes": s.notes,
    }


def photo_summary(p: Photo) -> str:
    """The sub-line under each file on the Upload screen."""
    if p.status == "queued":
        return "Queued"
    if p.status == "processing":
        return "Reading plate…"
    if p.status == "failed":
        return p.error or "Couldn't read this file"
    place = f" · near {p.place_name}" if p.place_name else ""
    dets = p.detections
    if not dets:
        return "Done" + place
    if p.status == "needs_review":
        pending = [d for d in dets if d.status in ("needs_verify", "needs_identify", "reading")]
        d = pending[0]
        if d.status == "needs_identify":
            return (d.reason or "No plate found").rstrip(".")
        return f"Low confidence · {d.text or '???'}"
    texts = [d.text for d in dets if d.status in ("auto", "confirmed") and d.text]
    if texts:
        return "Read " + ", ".join(texts) + place
    return "No plate kept" + place


def photo_json(p: Photo) -> dict:
    return {
        "id": p.id,
        "name": p.original_name,
        "status": p.status,
        "summary": photo_summary(p),
        "uploader": user_json(p.uploader),
        "taken_at": iso(p.taken_at),
        "tz": p.tz_name,
        "taken_at_source": p.taken_at_source,
        "lat": p.lat,
        "lon": p.lon,
        "location_source": p.location_source,
        "place": p.place_name,
        "blur": p.blur,
        "created_at": iso(p.created_at),
        "thumb_url": f"/api/photos/{p.id}/thumb",
        "display_url": f"/api/photos/{p.id}/display",
        "width": p.width,
        "height": p.height,
    }


def _prior(db: Session, d: Detection) -> str | None:
    if not d.text:
        return None
    norm = normalize(d.text)
    plate = db.scalars(select(Plate).where(Plate.norm == norm, Plate.merged_into_id.is_(None))).first()
    if plate is None:
        plate = db.scalars(
            select(Plate).where(Plate.skeleton == skeleton(norm), Plate.merged_into_id.is_(None))
        ).first()
        if plate is None:
            return "No earlier sightings of this plate."
        prefix = f"Possible match: {plate.text}"
    else:
        prefix = f"Matches {plate.text}"
    q = select(Sighting).where(Sighting.plate_id == plate.id)
    if d.sighting_id:
        q = q.where(Sighting.id != d.sighting_id)
    rows = list(db.scalars(q))
    n = len(rows)
    places = len({s.place_name for s in rows if s.place_name})
    if n == 0:
        return f"{prefix} · no other sightings yet."
    tail = f" in {places} place{'s' if places != 1 else ''}" if places > 1 else ""
    return f"{prefix} · {n} earlier sighting{'s' if n != 1 else ''}{tail}."


def crop_url(d: Detection | None) -> str | None:
    if d is None or not d.crop_path:
        return None
    # The crop file name encodes its box, so a re-read gets a new URL and skips stale caches.
    return f"/api/detections/{d.id}/crop?v={hashlib.sha1(d.crop_path.encode(), usedforsecurity=False).hexdigest()[:10]}"


def review_item_json(db: Session, d: Detection, me: User) -> dict:
    photo = d.photo
    ocr = d.ocr or {}
    vlm = d.vlm or {}
    ocr_text, vlm_text = ocr.get("text"), vlm.get("text")
    others = [
        {"id": o.id, "bbox": o.bbox, "text": o.text, "status": o.status}
        for o in photo.detections
        if o.id != d.id and o.bbox
    ]
    pending_in_photo = sum(1 for o in photo.detections if o.status in ("needs_verify", "needs_identify", "reading"))
    return {
        "id": d.id,
        "photo_id": photo.id,
        "status": d.status,
        "source": d.source,
        "reason": d.reason,
        # A box the user drew has been read and waits for confirmation inside Identify.
        "has_reading": bool(
            d.source in ("manual_box", "added_box") and d.bbox and d.status == "needs_identify" and d.ocr
        ),
        "by": user_json(photo.uploader),
        "uploaded_at": iso(photo.created_at),
        "taken_at": iso(photo.taken_at),
        "tz": photo.tz_name,
        "place": photo.place_name,
        "has_location": photo.lat is not None,
        "text": d.text or "",
        "char_conf": d.char_conf or [],
        "candidates": d.candidates or [],
        "confidence": d.confidence,
        "ocr": {"text": ocr_text, "conf": round((ocr.get("conf") or 0) * 100)} if ocr_text else None,
        "vlm": (
            {"text": vlm_text, "conf": round((vlm.get("conf") or 0) * 100), "state": vlm.get("state")}
            if vlm_text
            else ({"error": vlm["error"]} if vlm.get("error") else None)
        ),
        "disagree": bool(ocr_text and vlm_text and normalize(ocr_text) != normalize(vlm_text)),
        "state": d.state,
        "state_is_guess": d.state_is_guess,
        "blur": d.crop_blur if d.crop_blur is not None else photo.blur,
        "photo_blur": photo.blur,
        "bbox": d.bbox,
        "other_boxes": others,
        "pending_in_photo": pending_in_photo,
        "crop_url": crop_url(d),
        "photo_url": f"/api/photos/{photo.id}/display",
        "thumb_url": f"/api/photos/{photo.id}/thumb",
        "photo_size": [photo.width, photo.height],
        "claimed_by_me": d.claimed_by_id == me.id,
        "prior": _prior(db, d),
    }


def count_sightings(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Sighting).where(Sighting.user_id == user_id)) or 0
