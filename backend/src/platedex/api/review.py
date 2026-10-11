from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db, utcnow
from ..models import (
    CONFIRMED,
    NEEDS_IDENTIFY,
    NEEDS_VERIFY,
    READING,
    REJECTED,
    UNIDENTIFIED,
    Detection,
    Photo,
    User,
)
from ..pipeline.process import clear_box, update_photo_status
from ..security import current_user, member
from ..services import jobs
from ..services.plates import attach_detection, detach_detection, find_or_create_plate
from ..services.platetext import clean_display, normalize, normalize_state
from .serialize import iso, review_item_json, user_json

router = APIRouter(prefix="/api", tags=["review"])
CLAIM_TTL = timedelta(minutes=5)
TAB_STATUSES = {"verify": (NEEDS_VERIFY,), "identify": (NEEDS_IDENTIFY, READING)}


def _base(user: User, who: str, statuses: tuple[str, ...]):
    stmt = select(Detection).join(Photo, Detection.photo_id == Photo.id).where(Detection.status.in_(statuses))
    if who == "mine":
        stmt = stmt.where(Photo.uploader_id == user.id)
    return stmt


def _not_claimed_by_others(user: User):
    cutoff = utcnow() - CLAIM_TTL
    return or_(Detection.claimed_by_id.is_(None), Detection.claimed_by_id == user.id, Detection.claimed_at < cutoff)


def counts(db: Session, user: User) -> dict:
    out = {}
    for who in ("mine", "all"):
        for tab, st in TAB_STATUSES.items():
            out[f"{who}_{tab}"] = len(list(db.scalars(_base(user, who, st).with_only_columns(Detection.id))))
    return {
        "verify": {"mine": out["mine_verify"], "all": out["all_verify"]},
        "identify": {"mine": out["mine_identify"], "all": out["all_identify"]},
        "badge": out["mine_verify"] + out["mine_identify"],
    }


@router.get("/review/counts")
def review_counts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return counts(db, user)


@router.get("/review/queue")
def review_queue(
    tab: str = Query("verify", pattern="^(verify|identify)$"),
    who: str = Query("mine", pattern="^(mine|all)$"),
    limit: int = 100,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        _base(user, who, TAB_STATUSES[tab])
        .where(_not_claimed_by_others(user))
        .options(joinedload(Detection.photo).joinedload(Photo.uploader))
        .order_by(Detection.created_at.desc(), Detection.id.desc())
    )
    rows = list(db.scalars(stmt).unique())
    items = [
        {
            "id": d.id,
            "title": d.text or ("Reading…" if d.status == READING else "No reading"),
            "state": d.state,
            "status": d.status,
            "by": user_json(d.photo.uploader),
            "uploaded_at": iso(d.photo.created_at),
            "place": d.photo.place_name,
        }
        for d in rows[:limit]
    ]
    locked = len(list(db.scalars(_base(user, who, TAB_STATUSES[tab]).with_only_columns(Detection.id)))) - len(rows)
    return {"items": items, "total": len(rows), "locked_by_others": max(0, locked)}


def _item(db: Session, det_id: int) -> Detection:
    d = db.get(Detection, det_id)
    if d is None:
        raise HTTPException(404, "That review item is gone")
    return d


@router.get("/review/items/{det_id}")
def get_item(det_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return review_item_json(db, _item(db, det_id), user)


@router.post("/review/items/{det_id}/claim")
def claim(det_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    now = utcnow()
    if d.claimed_by_id and d.claimed_by_id != user.id and d.claimed_at and now - d.claimed_at < CLAIM_TTL:
        other = db.get(User, d.claimed_by_id)
        raise HTTPException(409, f"{other.username if other else 'Someone'} is reviewing this")
    d.claimed_by_id, d.claimed_at = user.id, now
    db.commit()
    return review_item_json(db, d, user)


@router.post("/review/items/{det_id}/release")
def release(det_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    if d.claimed_by_id == user.id:
        d.claimed_by_id = d.claimed_at = None
        db.commit()
    return {"ok": True}


def _finish(db: Session, d: Detection, user: User, status: str) -> None:
    d.status = status
    d.reviewed_by_id, d.reviewed_at = user.id, utcnow()
    d.claimed_by_id = d.claimed_at = None
    db.flush()
    db.refresh(d.photo)
    update_photo_status(d.photo)
    db.commit()


class Confirm(BaseModel):
    text: str = Field(min_length=1, max_length=20)
    state: str | None = None
    state_is_guess: bool = False


def _confirm(db: Session, d: Detection, body: Confirm, user: User, source: str | None = None) -> dict:
    text = clean_display(body.text)
    if not normalize(text):
        raise HTTPException(400, "Type the plate's letters and numbers")
    if len(normalize(text)) > 10:
        raise HTTPException(400, "That's longer than any US plate")
    state = normalize_state(body.state) if body.state and body.state != "??" else None
    guess = body.state_is_guess if state else True
    d.text, d.state, d.state_is_guess = text, state, guess
    if source:
        d.source = source
    plate = find_or_create_plate(db, text, state, guess, user)
    attach_detection(db, d, plate, user)
    _finish(db, d, user, CONFIRMED)
    partial = "?" in text
    msg = f"{'Saved partial plate' if partial else 'Confirmed'} {plate.text}" + (f" · {state}" if state else "")
    return {"ok": True, "plate_id": plate.id, "toast": msg}


@router.post("/review/items/{det_id}/confirm")
def confirm(det_id: int, body: Confirm, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    if d.status == READING:
        raise HTTPException(409, "Still reading this plate")
    return _confirm(db, d, body, user)


@router.post("/review/items/{det_id}/type")
def type_plate(det_id: int, body: Confirm, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    return _confirm(db, d, body, user, source="typed")


@router.post("/review/items/{det_id}/reject")
def reject(det_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    detach_detection(db, d)
    d.reason = "Not a plate"
    _finish(db, d, user, REJECTED)
    return {"ok": True, "toast": "Rejected — not a plate"}


@router.post("/review/items/{det_id}/no-plate")
def no_plate(det_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    detach_detection(db, d)
    d.reason = "No plate in photo"
    _finish(db, d, user, REJECTED)
    return {"ok": True, "toast": "Marked: no plate in photo"}


@router.post("/review/items/{det_id}/keep")
def keep_unidentified(det_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    attach_detection(db, d, None, user)
    _finish(db, d, user, UNIDENTIFIED)
    place = d.photo.place_name
    return {"ok": True, "toast": "Kept as unidentified sighting" + (f" · near {place}" if place else "")}


class BoxBody(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)


def _valid_box(b: list[float]) -> list[float]:
    x, y, w, h = b
    x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    w, h = max(0.0, min(1.0 - x, w)), max(0.0, min(1.0 - y, h))
    if w < 0.01 or h < 0.005:
        raise HTTPException(400, "Draw a bigger box around the plate")
    return [x, y, w, h]


@router.post("/review/items/{det_id}/box")
def draw_box(det_id: int, body: BoxBody, user: User = Depends(member), db: Session = Depends(get_db)):
    d = _item(db, det_id)
    d.bbox = _valid_box(body.bbox)
    d.status, d.reason = READING, None
    d.claimed_by_id, d.claimed_at = user.id, utcnow()
    jobs.enqueue(db, "read_box", {"detection_id": d.id, "bbox": d.bbox}, priority=jobs.PRIORITY_INTERACTIVE)
    db.flush()
    db.refresh(d.photo)
    update_photo_status(d.photo)
    db.commit()
    return review_item_json(db, d, user)


@router.post("/photos/{photo_id}/detections")
def add_plate_box(photo_id: int, body: BoxBody, user: User = Depends(member), db: Session = Depends(get_db)):
    """'Add another plate': a new review item for a second plate in the same photo."""
    p = db.get(Photo, photo_id)
    if p is None:
        raise HTTPException(404, "Photo not found")
    d = Detection(photo=p, source="added_box", status=READING, bbox=_valid_box(body.bbox),
                  state=p.place_state, state_is_guess=True, claimed_by_id=user.id, claimed_at=utcnow())
    db.add(d)
    db.flush()
    jobs.enqueue(db, "read_box", {"detection_id": d.id, "bbox": d.bbox}, priority=jobs.PRIORITY_INTERACTIVE)
    update_photo_status(p)
    db.commit()
    return review_item_json(db, d, user)


@router.post("/review/items/{det_id}/clear-box")
def remove_box(det_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    """Undo a wrong box: the item goes back to Identify without a box (an extra plate is removed)."""
    d = _item(db, det_id)
    if d.status == READING:
        raise HTTPException(409, "Still reading that box — try again in a moment")
    if d.status in (CONFIRMED, REJECTED, UNIDENTIFIED):
        raise HTTPException(409, "This item was already reviewed")
    if clear_box(db, d):
        return {"deleted": True, "toast": "Box removed"}
    d.claimed_by_id, d.claimed_at = user.id, utcnow()
    db.commit()
    return {**review_item_json(db, d, user), "deleted": False, "toast": "Box removed — draw it again"}
