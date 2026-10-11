"""Read the plates in one photo and route each one: auto-accept, Verify or Identify."""

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import (
    AUTO,
    NEEDS_IDENTIFY,
    NEEDS_VERIFY,
    PENDING_STATUSES,
    Detection,
    Photo,
)
from ..services import appsettings, storage
from ..services.plates import attach_detection, find_or_create_plate
from ..services.platetext import LOOKALIKE_GROUPS, normalize
from . import vlm as vlm_mod
from .engines import Box, get_engine
from .fuse import Reading, fuse
from .imaging import blur_score, crop_blur_score, enlarge_for_viewing, padded_box, to_bgr, variants

log = logging.getLogger(__name__)

MAX_PLATES_PER_PHOTO = 4
UNREADABLE_FLOOR = 0.35  # below this the OCR reading is treated as no reading
MIN_CHAR_FOR_AUTO = 0.5
_LOOKALIKE = {ch: g for g in LOOKALIKE_GROUPS for ch in g}

R_NO_PLATE = "OCR found no plate."
R_BLURRY_NO_PLATE = "Too blurry — no plate found."
R_UNREADABLE = "OCR found a plate-shaped area but could not read it."
R_DISAGREE = "OCR and the AI reader disagree."
R_LOW = "OCR isn't sure about some characters."
R_LENGTH = "Unusual length for a US plate."
R_PARTIAL = "Some characters couldn't be read."
R_MANUAL = "Read from the box you drew. Check it, then confirm."
R_MANUAL_EMPTY = "Couldn't read anything in that box. Redraw it or type the plate."
R_BOX_REMOVED = "Box removed. Draw it again around the plate."
MANUAL_SOURCES = ("manual_box", "added_box")


@dataclass
class RegionResult:
    bbox: list[float]
    det_conf: float | None
    crop_rel: str
    crop_blur: float
    reading: Reading
    vlm: dict[str, Any] | None
    text: str
    confidence: float
    char_conf: list[float]
    candidates: list[list[Any]]
    state: str | None
    state_is_guess: bool
    status: str
    reason: str | None
    ocr: dict[str, Any] = field(default_factory=dict)


def _iou(a: list[float], b: list[float]) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _ambiguous(mats: list[np.ndarray], alphabet: str) -> bool:
    """True when some slot's runner-up character is a look-alike of the winner with real weight."""
    p = np.mean(np.stack(mats), axis=0)
    for slot in p:
        i1, i2 = np.argsort(slot)[::-1][:2]
        c1, c2 = alphabet[i1], alphabet[i2]
        if slot[i2] >= 0.15 and _LOOKALIKE.get(c1) is not None and _LOOKALIKE.get(c1) == _LOOKALIKE.get(c2):
            return True
    return False


def _blend_char_conf(text: str, reading: Reading, vlm_conf: float) -> list[float]:
    """Per-character confidence for a VLM reading: OCR's value where both agree, lower where not."""
    out = []
    for i, ch in enumerate(text):
        if i < len(reading.char_conf) and reading.text[i : i + 1] == ch:
            out.append(round(min(reading.char_conf[i], vlm_conf), 3))
        else:
            out.append(round(vlm_conf * 0.7, 3))
    return out


def _want_vlm(mode: str, reading: Reading, ambiguous: bool, blur: float, thr: float, forced: bool) -> bool:
    if mode == "off":
        return False
    if mode == "always" or forced:
        return True
    return reading.confidence < thr or reading.min_char < 0.6 or ambiguous or blur >= 0.6


def read_region(
    bgr: np.ndarray,
    full: Image.Image,
    box: Box,
    photo: Photo,
    settings: dict[str, Any],
    forced_vlm: bool = False,
    manual: bool = False,
) -> RegionResult:
    h, w = bgr.shape[:2]
    x1, y1, x2, y2 = padded_box(box.x1, box.y1, box.x2, box.y2, w, h, pad=0.04 if manual else 0.12)
    crop = bgr[y1:y2, x1:x2]
    engine = get_engine()
    passes = variants(crop)
    mats = engine.char_probs([c for _, c in passes])
    reading = fuse(mats, engine.alphabet, engine.pad_char)
    per_pass = {name: "".join(engine.alphabet[i] for i in m.argmax(1)).rstrip(engine.pad_char)
                for (name, _), m in zip(passes, mats, strict=True)}
    crop_blur = crop_blur_score(crop)

    crop_view = Image.fromarray(enlarge_for_viewing(crop)[:, :, ::-1])
    crop_rel = f"crops/{photo.sha256[:2]}/{photo.sha256}_{x1}_{y1}_{x2}_{y2}.jpg"
    storage.save_crop(crop_rel, crop_view)

    thr = float(settings["ocr_threshold"]) / 100
    mode = settings["vlm_mode"]
    vlm: dict[str, Any] | None = None
    vr: vlm_mod.VlmReading | None = None
    if _want_vlm(mode, reading, _ambiguous(mats, engine.alphabet), max(crop_blur, photo.blur or 0), thr, forced_vlm):
        try:
            vr = vlm_mod.read_plate(storage.jpeg_bytes(crop_view, 768), storage.jpeg_bytes(full, 1280))
            vlm = vr.as_json()
        except vlm_mod.VlmUnavailable as e:
            vlm = {"error": str(e)[:200]}
            log.warning("VLM unavailable: %s", e)
        except Exception as e:  # noqa: BLE001
            vlm = {"error": f"bad reply: {e}"[:200]}
            log.warning("VLM reply unusable: %s", e)

    ocr_text = reading.text if reading.confidence >= UNREADABLE_FLOOR else ""
    candidates: list[list[Any]] = [[t, round(c * 100)] for t, c in reading.candidates]
    text, confidence, char_conf = reading.text, reading.confidence, reading.char_conf
    status, reason = AUTO, None

    vlm_ok = vr is not None and vr.legible and bool(vr.text)
    if vlm_ok:
        assert vr is not None
        if vr.text not in [c[0] for c in candidates]:
            candidates.insert(0 if vr.confidence > reading.confidence else 1, [vr.text, round(vr.confidence * 100)])
        for alt in vr.alternatives:
            if alt not in [c[0] for c in candidates]:
                candidates.append([alt, round(vr.confidence * 40)])
        candidates = sorted(candidates, key=lambda c: -c[1])[:3]

    if not ocr_text and not vlm_ok:
        status = NEEDS_IDENTIFY
        reason = R_UNREADABLE
    elif vr is not None and vlm_ok and normalize(vr.text) != normalize(ocr_text):
        status, reason = NEEDS_VERIFY, R_DISAGREE
        if vr.confidence > reading.confidence or not ocr_text:
            text, confidence = vr.text, vr.confidence
            char_conf = _blend_char_conf(vr.text, reading, vr.confidence)
    else:
        if vr is not None and vlm_ok:  # both readers agree: that's strong evidence
            confidence = min(0.99, max(confidence, (confidence + vr.confidence) / 2 + 0.1))
            char_conf = [min(0.99, max(c, 0.9)) for c in char_conf]
        if "?" in text:
            status, reason = NEEDS_VERIFY, R_PARTIAL
        elif not 2 <= len(text) <= 8:
            status, reason = NEEDS_VERIFY, R_LENGTH
        elif confidence < thr or min(char_conf or [0]) < MIN_CHAR_FOR_AUTO:
            status, reason = NEEDS_VERIFY, R_LOW
    if manual:
        # A box the user drew stays in Identify with its reading, so they can confirm it in place.
        status = NEEDS_IDENTIFY
        reason = R_MANUAL if text else R_MANUAL_EMPTY

    if vr is not None and vr.state:
        state, guess = vr.state, False
    else:
        state, guess = photo.place_state, True

    return RegionResult(
        bbox=[round(x1 / w, 4), round(y1 / h, 4), round((x2 - x1) / w, 4), round((y2 - y1) / h, 4)],
        det_conf=round(box.conf, 3) if box.conf is not None else None,
        crop_rel=crop_rel,
        crop_blur=crop_blur,
        reading=reading,
        vlm=vlm,
        text=text,
        confidence=round(confidence, 3),
        char_conf=char_conf,
        candidates=candidates,
        state=state,
        state_is_guess=guess,
        status=status,
        reason=reason,
        ocr={
            "text": reading.text,
            "conf": reading.confidence,
            "char_conf": reading.char_conf,
            "candidates": [[t, c] for t, c in reading.candidates],
            "passes": per_pass,
        },
    )


def _apply(det: Detection, r: RegionResult) -> None:
    det.bbox = r.bbox
    det.det_conf = r.det_conf
    det.crop_path = r.crop_rel
    det.crop_blur = r.crop_blur
    det.ocr = r.ocr
    det.vlm = r.vlm
    det.text = r.text
    det.confidence = r.confidence
    det.char_conf = r.char_conf
    det.candidates = r.candidates
    det.state = r.state
    det.state_is_guess = r.state_is_guess
    det.status = r.status
    det.reason = r.reason


def update_photo_status(photo: Photo) -> None:
    if photo.status in ("queued", "processing", "failed"):
        return
    pending = any(d.status in PENDING_STATUSES for d in photo.detections)
    photo.status = "needs_review" if pending else "done"


def _accept_auto(db: Session, det: Detection) -> None:
    plate = find_or_create_plate(db, det.text or "", det.state, det.state_is_guess, det.photo.uploader)
    attach_detection(db, det, plate, None)


def process_photo(db: Session, photo_id: int, reprocess: bool = False) -> dict[str, Any]:
    photo = db.get(Photo, photo_id)
    if photo is None:
        return {"skipped": "missing"}
    photo.status = "processing"
    db.commit()
    settings = appsettings.get_all(db)
    full = storage.write_derivatives(storage.root() / photo.path, photo.sha256)
    photo.width, photo.height = full.size
    bgr = to_bgr(full)
    photo.blur = blur_score(bgr)

    engine = get_engine()
    boxes = [b for b in engine.detect(bgr)][:MAX_PLATES_PER_PHOTO]

    existing = list(photo.detections)
    kept = [d for d in existing if d.status not in (AUTO, NEEDS_VERIFY, NEEDS_IDENTIFY) or d.source != "auto"]
    redo = [d for d in existing if d not in kept]
    changed = False
    seen_ids: set[int] = set()

    for box in boxes:
        h, w = bgr.shape[:2]
        frac = [box.x1 / w, box.y1 / h, (box.x2 - box.x1) / w, (box.y2 - box.y1) / h]
        if any(d.bbox and _iou(d.bbox, frac) > 0.3 for d in kept):
            continue  # a human already handled this plate
        r = read_region(bgr, full, box, photo, settings)
        match = next((d for d in redo if d.bbox and d.id not in seen_ids and _iou(d.bbox, frac) > 0.3), None)
        if match is None:
            det = Detection(photo=photo, source="auto", status=r.status)
            db.add(det)
        else:
            det = match
            seen_ids.add(det.id)
            if normalize(det.text or "") == normalize(r.text) and det.status == AUTO and r.status == AUTO:
                continue  # same reading as before; keep its sighting untouched
            if det.status == AUTO and det.sighting_id and normalize(det.text or "") != normalize(r.text):
                changed = True
                r.status, r.reason = NEEDS_VERIFY, "Reprocessing changed this reading."
        _apply(det, r)
        db.flush()
        if det.status == AUTO:
            _accept_auto(db, det)

    # Placeholders from an earlier run that found nothing are replaced when plates are found now.
    for d in redo:
        if d.id not in seen_ids and d.bbox is None and boxes:
            db.delete(d)

    db.flush()
    db.refresh(photo)
    if not photo.detections:
        reason = R_BLURRY_NO_PLATE if (photo.blur or 0) >= 0.7 else R_NO_PLATE
        db.add(Detection(photo=photo, source="auto", status=NEEDS_IDENTIFY, reason=reason,
                         state=photo.place_state, state_is_guess=True))
    photo.status = "done"
    photo.processed_at = utcnow()
    photo.error = None
    db.flush()
    db.refresh(photo)
    update_photo_status(photo)
    db.commit()
    return {"changed": changed, "detections": len(photo.detections), "status": photo.status}


def clear_box(db: Session, det: Detection) -> bool:
    """Undo a wrong box. Returns True if the item was deleted (an extra plate the user added)."""
    from ..services.plates import detach_detection

    detach_detection(db, det)
    photo = det.photo
    if det.source == "added_box":
        db.delete(det)
        db.flush()
        db.refresh(photo)
        update_photo_status(photo)
        db.commit()
        return True
    det.bbox = det.crop_path = det.ocr = det.vlm = det.text = det.char_conf = det.candidates = None
    det.confidence = det.det_conf = det.crop_blur = None
    det.state, det.state_is_guess = photo.place_state, True
    det.source, det.status, det.reason = "manual_box", NEEDS_IDENTIFY, R_BOX_REMOVED
    db.flush()
    update_photo_status(photo)
    db.commit()
    return False


def read_box(db: Session, detection_id: int, bbox: list[float]) -> Detection:
    """A user drew a box (fractions of the photo). Read just that region; the item stays in Identify."""
    det = db.get(Detection, detection_id)
    if det is None:
        raise ValueError("Unknown detection")
    photo = det.photo
    settings = appsettings.get_all(db)
    full = storage.open_upright(storage.root() / photo.path)
    bgr = to_bgr(full)
    h, w = bgr.shape[:2]
    x, y, bw, bh = bbox
    x1, y1 = int(max(0, x) * w), int(max(0, y) * h)
    x2, y2 = int(min(1, x + bw) * w), int(min(1, y + bh) * h)
    box = Box(x1, y1, x2, y2, conf=None)  # type: ignore[arg-type]

    # Tighten a loose box with the detector, using the plate the box covers best (not the most
    # confident one), and only if that plate sits mostly inside what the user drew.
    mx, my = int((x2 - x1) * 0.25), int((y2 - y1) * 0.25)
    rx1, ry1, rx2, ry2 = max(0, x1 - mx), max(0, y1 - my), min(w, x2 + mx), min(h, y2 + my)
    best, best_score = None, 0.0
    for b in get_engine().detect(bgr[ry1:ry2, rx1:rx2]):
        bx1, by1, bx2, by2 = rx1 + b.x1, ry1 + b.y1, rx1 + b.x2, ry1 + b.y2
        iw = max(0, min(x2, bx2) - max(x1, bx1))
        ih = max(0, min(y2, by2) - max(y1, by1))
        area = max(1, (bx2 - bx1) * (by2 - by1))
        inside = iw * ih / area
        if inside >= 0.6 and inside * b.conf > best_score:
            best, best_score = Box(bx1, by1, bx2, by2, b.conf), inside * b.conf
    manual_pad = best is None
    if best is not None:
        box = best

    r = read_region(bgr, full, box, photo, settings, forced_vlm=True, manual=True)
    if manual_pad:
        r.bbox = [round(x1 / w, 4), round(y1 / h, 4), round((x2 - x1) / w, 4), round((y2 - y1) / h, 4)]
    _apply(det, r)
    if det.source not in MANUAL_SOURCES:
        det.source = "manual_box"
    db.flush()
    update_photo_status(photo)
    db.commit()
    return det

