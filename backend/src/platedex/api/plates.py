import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import Plate, PlateMerge, Sighting, User
from ..security import current_user, member
from ..services import plates as plate_svc
from ..services.listing import Filters, missing_location_count, plate_rows, sighting_rows
from ..services.platetext import US_STATES, clean_display, is_partial, normalize, normalize_state, skeleton
from .serialize import iso, plate_brief, sighting_json, user_json

router = APIRouter(prefix="/api", tags=["plates"])


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _pair(v: str | None) -> tuple[float | None, float | None]:
    try:
        a, b = (float(x) for x in (v or "").split(","))
        return a, b
    except ValueError:
        return None, None


def filters(
    q: str = "",
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    states: str | None = None,
    users: str | None = None,
    tags: str | None = None,
    min_n: int = 1,
    near: str | None = None,
    radius: float | None = None,
    missing: bool = False,
    sort: str = "last",
    origin: str | None = None,
) -> Filters:
    nlat, nlon = _pair(near)
    olat, olon = _pair(origin)
    return Filters(
        q=q, date_from=date_from, date_to=date_to, states=[s.upper() for s in _csv(states)], users=_csv(users),
        tags=[t.lstrip("#").lower() for t in _csv(tags)], min_n=max(1, min_n), near_lat=nlat, near_lon=nlon,
        radius_mi=radius, missing=missing, sort=sort, origin_lat=olat if olat is not None else nlat,
        origin_lon=olon if olon is not None else nlon,
    )


def _row_json(r: dict) -> dict:
    return {
        **plate_brief(r["plate"]),
        "n": r["n"],
        "places": r["places"],
        "spotters": r["spotters"],
        "first": iso(r["first"]),
        "last": iso(r["last"]),
        "dist_mi": round(r["dist"], 1) if r["dist"] is not None else None,
        "points": r["points"],
    }


@router.get("/plates")
def list_plates(f: Filters = Depends(filters), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = plate_rows(db, f)
    return {
        "plates": [_row_json(r) for r in rows],
        "sightings": sum(r["n"] for r in rows),
        "missing_location": missing_location_count(db),
    }


@router.get("/sightings")
def list_sightings(f: Filters = Depends(filters), limit: int = 500, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    rows = sighting_rows(db, f)
    return {"sightings": [sighting_json(s) for s in rows[:limit]], "total": len(rows),
            "missing_location": missing_location_count(db)}


@router.get("/map/points")
def map_points(f: Filters = Depends(filters), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = [s for s in sighting_rows(db, f) if s.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s.lon, s.lat]},
                "properties": {
                    "sid": s.id, "pid": s.plate_id, "text": s.plate.text, "state": s.plate.state or "",
                    "partial": s.plate.is_partial, "seen": iso(s.seen_at), "user": s.user.username,
                },
            }
            for s in rows
        ],
    }


def _plate(db: Session, plate_id: int) -> Plate:
    p = db.get(Plate, plate_id)
    if p is None:
        raise HTTPException(404, "Plate not found")
    return p


@router.get("/plates/{plate_id}")
def get_plate(plate_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _plate(db, plate_id)
    if p.merged_into_id:
        return {"redirect": p.merged_into_id}
    ss = list(
        db.scalars(
            select(Sighting).where(Sighting.plate_id == p.id).options(joinedload(Sighting.user))
            .order_by(Sighting.seen_at)
        ).unique()
    )
    located = [s for s in ss if s.lat is not None]
    dups = plate_svc.duplicates(db, p)
    first_by = ss[0].user if ss else None
    notes_by = db.get(User, p.notes_by_id) if p.notes_by_id else None
    return {
        **plate_brief(p),
        "state_name": US_STATES.get(p.state or ""),
        "notes": p.notes,
        "notes_by": user_json(notes_by),
        "first_by": user_json(first_by),
        "n": len(ss),
        "places": len({s.place_name for s in located if s.place_name}),
        "spotters": len({s.user_id for s in ss}),
        "first": iso(ss[0].seen_at) if ss else None,
        "last": iso(ss[-1].seen_at) if ss else None,
        "sightings": [sighting_json(s) for s in ss],
        "duplicates": [
            {
                **plate_brief(d["plate"]),
                "reason": d["reason"],
                "n": d["sightings"],
                "diffs": d["diffs"],
                "last": sighting_json(d["last"]) if d["last"] else None,
            }
            for d in dups
        ],
    }


class PlatePatch(BaseModel):
    text: str | None = Field(None, max_length=20)
    state: str | None = None
    meaning: str | None = Field(None, max_length=255)
    notes: str | None = Field(None, max_length=4000)
    tags: list[str] | None = None


@router.patch("/plates/{plate_id}")
def patch_plate(plate_id: int, body: PlatePatch, user: User = Depends(member), db: Session = Depends(get_db)):
    p = _plate(db, plate_id)
    if body.text is not None:
        t = clean_display(body.text)
        if not normalize(t):
            raise HTTPException(400, "Plate text can't be empty")
        p.text, p.norm, p.skeleton, p.is_partial = t, normalize(t), skeleton(t), is_partial(t)
    if body.state is not None:
        p.state = normalize_state(body.state) if body.state not in ("", "??") else None
        p.state_is_guess = False
    if body.meaning is not None:
        p.meaning = body.meaning.strip() or None
    if body.notes is not None:
        p.notes = body.notes.strip() or None
        p.notes_by_id = user.id
    if body.tags is not None:
        tags = {t.strip().lstrip("#").lower().replace(" ", "-") for t in body.tags if t.strip()}
        if p.is_partial:
            tags.add("partial")
        p.tags = sorted(tags)[:20]
    db.commit()
    return get_plate(plate_id, user, db)


class MergeBody(BaseModel):
    source_id: int


@router.post("/plates/{plate_id}/merge")
def merge(plate_id: int, body: MergeBody, user: User = Depends(member), db: Session = Depends(get_db)):
    target, source = _plate(db, plate_id), _plate(db, body.source_id)
    try:
        m = plate_svc.merge(db, source, target, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    return {"merge_id": m.id, "toast": f"Merged {source.text} into {target.text}"}


@router.post("/merges/{merge_id}/undo")
def undo_merge(merge_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    m = db.get(PlateMerge, merge_id)
    if m is None:
        raise HTTPException(404, "Merge not found")
    try:
        source = plate_svc.undo_merge(db, m)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    return {"ok": True, "plate_id": source.id, "toast": f"Split {source.text} back out"}


class DupBody(BaseModel):
    other_id: int


@router.post("/plates/{plate_id}/dismiss")
def dismiss(plate_id: int, body: DupBody, user: User = Depends(member), db: Session = Depends(get_db)):
    plate_svc.dismiss_duplicate(db, _plate(db, plate_id).id, _plate(db, body.other_id).id)
    db.commit()
    return {"ok": True, "toast": "Kept as separate plates"}


@router.post("/plates/{plate_id}/undismiss")
def undismiss(plate_id: int, body: DupBody, user: User = Depends(member), db: Session = Depends(get_db)):
    plate_svc.undismiss_duplicate(db, plate_id, body.other_id)
    db.commit()
    return {"ok": True}


class SplitBody(BaseModel):
    sighting_ids: list[int] = Field(min_length=1)
    text: str = Field(min_length=1, max_length=20)
    state: str | None = None


@router.post("/plates/{plate_id}/split")
def split(plate_id: int, body: SplitBody, user: User = Depends(member), db: Session = Depends(get_db)):
    p = _plate(db, plate_id)
    state = normalize_state(body.state) if body.state and body.state != "??" else None
    try:
        new = plate_svc.split(db, p, body.sighting_ids, body.text, state, user)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.commit()
    n = len(body.sighting_ids)
    return {"plate_id": new.id, "toast": f"Split {n} sighting{'s' if n != 1 else ''} into {new.text}"}


@router.get("/meta")
def meta(user: User = Depends(current_user), db: Session = Depends(get_db)):
    users = list(db.scalars(select(User).where(User.disabled.is_(False)).order_by(User.id)))
    tags: set[str] = set()
    states: set[str] = set()
    for p in db.scalars(select(Plate).where(Plate.merged_into_id.is_(None))):
        tags.update(p.tags or [])
        if p.state:
            states.add(p.state)
    return {
        "users": [user_json(u) for u in users],
        "tags": sorted(tags),
        "states": sorted(states),
        "all_states": US_STATES,
        "missing_location": missing_location_count(db),
    }


@router.get("/export.csv")
def export_csv(f: Filters = Depends(filters), user: User = Depends(current_user), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["plate", "state", "seen_at_utc", "lat", "lon", "place", "spotter", "read_as", "meaning", "tags"])
    for s in sighting_rows(db, f):
        w.writerow([s.plate.text, s.plate.state or "", iso(s.seen_at) or "",
                    "" if s.lat is None else s.lat, "" if s.lon is None else s.lon,
                    s.place_name or "", s.user.username, s.read_text or "", s.plate.meaning or "",
                    " ".join(s.plate.tags or [])])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="platedex-sightings.csv"'})


@router.get("/export.geojson")
def export_geojson(f: Filters = Depends(filters), user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    data = map_points(f, user, db)
    return Response(json.dumps(data), media_type="application/geo+json",
                    headers={"Content-Disposition": 'attachment; filename="platedex-sightings.geojson"'})
