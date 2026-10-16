"""Plate identity: attaching sightings, duplicate suggestions, merge/undo, split and delete."""

from datetime import timedelta

from rapidfuzz.distance import Levenshtein
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import REJECTED, Detection, DismissedDuplicate, Photo, Plate, PlateMerge, Sighting, User
from .geo import haversine_mi
from .platetext import clean_display, is_partial, lookalike_pairs, normalize, partial_matches, skeleton

BURST_WINDOW = timedelta(minutes=5)
BURST_MILES = 0.1  # ~160 m


def _sighting_count(db: Session, plate_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Sighting).where(Sighting.plate_id == plate_id)) or 0


def find_or_create_plate(
    db: Session, text: str, state: str | None, state_is_guess: bool, user: User | None
) -> Plate:
    display = clean_display(text)
    norm = normalize(display)
    existing = list(
        db.scalars(select(Plate).where(Plate.norm == norm, Plate.merged_into_id.is_(None)).order_by(Plate.id))
    )
    if existing:
        same = [p for p in existing if state and p.state == state]
        if same:
            plate = same[0]
            if not state_is_guess and plate.state_is_guess:
                plate.state_is_guess = False
            return plate
        if state_is_guess or not state:
            # A guessed state never splits a plate: join the best-known existing one.
            return max(existing, key=lambda p: _sighting_count(db, p.id))
        loose = [p for p in existing if not p.state or p.state_is_guess]
        if loose:
            plate = loose[0]
            plate.state, plate.state_is_guess = state, False
            return plate
    plate = Plate(
        text=display,
        norm=norm,
        skeleton=skeleton(norm),
        state=state,
        state_is_guess=state_is_guess,
        tags=["partial"] if is_partial(norm) else [],
        is_partial=is_partial(norm),
        created_by_id=user.id if user else None,
    )
    db.add(plate)
    db.flush()
    return plate


def delete_if_empty(db: Session, plate_id: int | None) -> None:
    if plate_id is None:
        return
    plate = db.get(Plate, plate_id)
    if plate is None or plate.merged_into_id is not None:
        return
    if _sighting_count(db, plate_id) == 0:
        merged_in = db.scalar(select(func.count()).select_from(Plate).where(Plate.merged_into_id == plate_id))
        if not merged_in:
            db.delete(plate)


def _burst_match(db: Session, plate: Plate, photo: Photo) -> Sighting | None:
    """Another sighting of the same plate a few minutes earlier/later at the same spot is the same sighting."""
    if photo.taken_at is None:
        return None
    rows = db.scalars(
        select(Sighting).where(
            Sighting.plate_id == plate.id,
            Sighting.seen_at.between(photo.taken_at - BURST_WINDOW, photo.taken_at + BURST_WINDOW),
        )
    )
    for s in rows:
        if s.photo_id == photo.id:
            continue
        if s.lat is None or photo.lat is None:
            return s
        if haversine_mi(s.lat, s.lon, photo.lat, photo.lon) <= BURST_MILES:
            return s
    return None


def attach_detection(db: Session, det: Detection, plate: Plate | None, reviewer: User | None) -> Sighting:
    """Create (or move) the sighting for a detection. plate=None makes an unidentified sighting."""
    photo = det.photo
    if det.sighting_id:
        sighting = db.get(Sighting, det.sighting_id)
        if sighting is not None:
            old_plate = sighting.plate_id
            sighting.plate_id = plate.id if plate else None
            sighting.read_text = det.text
            db.flush()
            if old_plate != sighting.plate_id:
                delete_if_empty(db, old_plate)
            return sighting
    if plate is not None:
        dup = _burst_match(db, plate, photo)
        if dup is not None:
            det.sighting_id = dup.id
            return dup
    sighting = Sighting(
        plate_id=plate.id if plate else None,
        photo_id=photo.id,
        detection_id=det.id,
        user_id=photo.uploader_id,
        read_text=det.text,
        seen_at=photo.taken_at or photo.created_at,
        tz_name=photo.tz_name,
        lat=photo.lat,
        lon=photo.lon,
        place_name=photo.place_name,
        place_state=photo.place_state,
    )
    db.add(sighting)
    db.flush()
    det.sighting_id = sighting.id
    return sighting


def detach_detection(db: Session, det: Detection) -> None:
    """Remove the sighting a detection created (e.g. when it's rejected after a reprocess)."""
    if not det.sighting_id:
        return
    sighting = db.get(Sighting, det.sighting_id)
    det.sighting_id = None
    if sighting is None:
        return
    others = db.scalar(
        select(func.count()).select_from(Detection).where(
            Detection.sighting_id == sighting.id, Detection.id != det.id
        )
    )
    if others:
        return
    plate_id = sighting.plate_id
    db.delete(sighting)
    db.flush()
    delete_if_empty(db, plate_id)


def _dismissed(db: Session, a: int, b: int) -> bool:
    lo, hi = min(a, b), max(a, b)
    return db.get(DismissedDuplicate, (lo, hi)) is not None


def duplicates(db: Session, plate: Plate) -> list[dict]:
    """Plates that are probably the same car read differently."""
    out = []
    others = db.scalars(select(Plate).where(Plate.id != plate.id, Plate.merged_into_id.is_(None)))
    for o in others:
        if _dismissed(db, plate.id, o.id):
            continue
        if plate.state and o.state and plate.state != o.state and not (plate.state_is_guess or o.state_is_guess):
            continue
        diffs = lookalike_pairs(plate.norm, o.norm)
        reason = None
        if diffs:
            pairs = ", ".join(f"{x} ↔ {y}" for x, y in diffs)
            reason = f"differs only by {pairs}, a common misread"
        elif plate.is_partial or o.is_partial:
            if partial_matches(plate.norm, o.norm):
                reason = "matches the partial plate"
        elif len(plate.norm) >= 5 and Levenshtein.distance(plate.skeleton, o.skeleton) == 1:
            reason = "one character apart"
        if reason is None:
            continue
        n = _sighting_count(db, o.id)
        last = db.scalars(
            select(Sighting).where(Sighting.plate_id == o.id).order_by(Sighting.seen_at.desc()).limit(1)
        ).first()
        out.append({"plate": o, "reason": reason, "sightings": n, "last": last, "diffs": diffs})
    out.sort(key=lambda d: -d["sightings"])
    return out


def dismiss_duplicate(db: Session, a: int, b: int) -> None:
    lo, hi = min(a, b), max(a, b)
    if db.get(DismissedDuplicate, (lo, hi)) is None:
        db.add(DismissedDuplicate(plate_a_id=lo, plate_b_id=hi))


def undismiss_duplicate(db: Session, a: int, b: int) -> None:
    row = db.get(DismissedDuplicate, (min(a, b), max(a, b)))
    if row is not None:
        db.delete(row)


def merge(db: Session, source: Plate, target: Plate, user: User) -> PlateMerge:
    if source.id == target.id:
        raise ValueError("Can't merge a plate into itself")
    ids = list(db.scalars(select(Sighting.id).where(Sighting.plate_id == source.id)))
    for s in db.scalars(select(Sighting).where(Sighting.id.in_(ids))):
        s.plate_id = target.id
    target.tags = sorted(set(target.tags or []) | (set(source.tags or []) - {"partial"}))
    if not target.meaning and source.meaning:
        target.meaning = source.meaning
    if source.notes and source.notes not in (target.notes or ""):
        target.notes = ((target.notes or "") + "\n" + source.notes).strip()
    if (not target.state or target.state_is_guess) and source.state and not source.state_is_guess:
        target.state, target.state_is_guess = source.state, False
    source.merged_into_id = target.id
    m = PlateMerge(source_plate_id=source.id, target_plate_id=target.id, sighting_ids=ids, by_id=user.id)
    db.add(m)
    db.flush()
    return m


def undo_merge(db: Session, m: PlateMerge) -> Plate:
    if m.undone_at is not None:
        raise ValueError("Already undone")
    source = db.get(Plate, m.source_plate_id)
    if source is None:
        raise ValueError("The merged plate no longer exists")
    for s in db.scalars(select(Sighting).where(Sighting.id.in_(m.sighting_ids))):
        if s.plate_id == m.target_plate_id:
            s.plate_id = source.id
    source.merged_into_id = None
    m.undone_at = utcnow()
    db.flush()
    return source


def split(
    db: Session, plate: Plate, sighting_ids: list[int], text: str, state: str | None, user: User
) -> Plate:
    rows = list(db.scalars(select(Sighting).where(Sighting.id.in_(sighting_ids), Sighting.plate_id == plate.id)))
    if not rows:
        raise ValueError("No sightings selected")
    total = _sighting_count(db, plate.id)
    if len(rows) >= total:
        raise ValueError("Leave at least one sighting on this plate")
    norm = normalize(text)
    if not norm:
        raise ValueError("Enter the plate text for the new plate")
    if norm == plate.norm and (state or plate.state) == plate.state:
        target = Plate(
            text=clean_display(text), norm=norm, skeleton=skeleton(norm), state=state or plate.state,
            state_is_guess=state is None and plate.state_is_guess, tags=[], is_partial=is_partial(norm),
            created_by_id=user.id,
        )
        db.add(target)
        db.flush()
        dismiss_duplicate(db, plate.id, target.id)
    else:
        target = find_or_create_plate(db, text, state or plate.state, state is None, user)
        if target.id == plate.id:
            raise ValueError("That's this plate")
    for s in rows:
        s.plate_id = target.id
    db.flush()
    return target


def delete_plate(db: Session, plate: Plate, user: User) -> int:
    """Delete a plate and its sightings. Photos stay; their detections are marked rejected so they
    don't come back into Review. Plates merged into this one go too. Returns the sighting count."""
    from ..pipeline.process import update_photo_status  # process imports this module

    plate_ids = [plate.id, *db.scalars(select(Plate.id).where(Plate.merged_into_id == plate.id))]
    sighting_ids = list(db.scalars(select(Sighting.id).where(Sighting.plate_id.in_(plate_ids))))
    photos: set[Photo] = set()
    for det in db.scalars(select(Detection).where(Detection.sighting_id.in_(sighting_ids))):
        det.sighting_id = None
        det.status, det.reason = REJECTED, "Plate deleted"
        det.reviewed_by_id, det.reviewed_at = user.id, utcnow()
        det.claimed_by_id = det.claimed_at = None
        photos.add(det.photo)
    for s in db.scalars(select(Sighting).where(Sighting.id.in_(sighting_ids))):
        db.delete(s)
    for p in db.scalars(select(Plate).where(Plate.id.in_(plate_ids))):
        db.delete(p)
    db.flush()
    for photo in photos:
        db.refresh(photo)
        update_photo_status(photo)
    return len(sighting_ids)
