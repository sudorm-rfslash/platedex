"""Shared filtering for the Plates list, the flat Sightings list, the Map and exports.

Filters apply to sightings first; plate rows are then built from the sightings that
survive, so counts, first/last seen and places always reflect the active filters.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Plate, Sighting, User
from .geo import haversine_mi
from .platetext import US_STATES, match_score, parse_query

SORTS = ("last", "first", "most", "places", "dist", "az")


@dataclass
class Filters:
    q: str = ""
    date_from: date | None = None
    date_to: date | None = None
    states: list[str] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    min_n: int = 1
    near_lat: float | None = None
    near_lon: float | None = None
    radius_mi: float | None = None
    missing: bool = False
    sort: str = "last"
    origin_lat: float | None = None
    origin_lon: float | None = None

    @property
    def has_area(self) -> bool:
        return self.near_lat is not None and self.near_lon is not None and bool(self.radius_mi)


def _load(db: Session, f: Filters) -> list[Sighting]:
    stmt = (
        select(Sighting)
        .join(Plate, Sighting.plate_id == Plate.id)
        .where(Plate.merged_into_id.is_(None))
        .options(joinedload(Sighting.plate), joinedload(Sighting.user))
    )
    if f.date_from:
        stmt = stmt.where(Sighting.seen_at >= datetime.combine(f.date_from, time.min))
    if f.date_to:
        stmt = stmt.where(Sighting.seen_at < datetime.combine(f.date_to + timedelta(days=1), time.min))
    if f.users:
        stmt = stmt.join(User, Sighting.user_id == User.id).where(User.username.in_(f.users))
    if f.missing:
        stmt = stmt.where(Sighting.lat.is_(None))
    rows = list(db.scalars(stmt).unique())
    if f.has_area:
        rows = [
            s for s in rows
            if s.lat is not None and haversine_mi(f.near_lat, f.near_lon, s.lat, s.lon) <= f.radius_mi
        ]
    return rows


def _haystack(p: Plate) -> str:
    return " ".join(
        [p.meaning or "", p.notes or "", " ".join(p.tags or []), US_STATES.get(p.state or "", "")]
    )


def plate_rows(db: Session, f: Filters) -> list[dict]:
    query = parse_query(f.q)
    by_plate: dict[int, list[Sighting]] = {}
    plates: dict[int, Plate] = {}
    for s in _load(db, f):
        by_plate.setdefault(s.plate_id, []).append(s)
        plates[s.plate_id] = s.plate
    out = []
    for pid, ss in by_plate.items():
        p = plates[pid]
        if f.states and p.state not in f.states:
            continue
        if f.tags and not set(f.tags) & set(p.tags or []):
            continue
        if len(ss) < f.min_n:
            continue
        score = match_score(query, p.text, _haystack(p))
        if score <= 0:
            continue
        ss.sort(key=lambda s: s.seen_at or datetime.min)
        located = [s for s in ss if s.lat is not None]
        places = sorted({s.place_name for s in located if s.place_name})
        dist = None
        if f.origin_lat is not None and f.origin_lon is not None and located:
            dist = min(haversine_mi(f.origin_lat, f.origin_lon, s.lat, s.lon) for s in located)
        out.append(
            {
                "plate": p,
                "score": score,
                "n": len(ss),
                "places": places,
                "spotters": len({s.user_id for s in ss}),
                "first": ss[0].seen_at,
                "last": ss[-1].seen_at,
                "dist": dist,
                "points": [[round(s.lat, 4), round(s.lon, 4)] for s in located][-12:],
            }
        )
    key = {
        "last": lambda r: (-(r["last"] or datetime.min).timestamp(),),
        "first": lambda r: (-(r["first"] or datetime.min).timestamp(),),
        "most": lambda r: (-r["n"], -(r["last"] or datetime.min).timestamp()),
        "places": lambda r: (-len(r["places"]), -r["n"]),
        "dist": lambda r: (r["dist"] if r["dist"] is not None else 1e9, -r["n"]),
        "az": lambda r: (r["plate"].norm,),
    }.get(f.sort)
    # The user's sort wins; how well a row matches the search only breaks ties.
    out.sort(key=lambda r: (*key(r), -r["score"]) if key else (-r["score"],))
    return out


def sighting_rows(db: Session, f: Filters) -> list[Sighting]:
    """Flat list: sightings of the plates that pass the plate-level filters, newest first."""
    rows = plate_rows(db, f)
    keep = {r["plate"].id for r in rows}
    out = [s for s in _load(db, f) if s.plate_id in keep]
    out.sort(key=lambda s: s.seen_at or datetime.min, reverse=True)
    return out


def missing_location_count(db: Session) -> int:
    return len(
        list(
            db.scalars(
                select(Sighting.id)
                .join(Plate, Sighting.plate_id == Plate.id)
                .where(Plate.merged_into_id.is_(None), Sighting.lat.is_(None))
            )
        )
    )
