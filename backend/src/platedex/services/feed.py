"""The Home feed: every sighting, plus uploaded photos that still wait in Review, newest first.

A sighting is one plate in one photo (or a plate logged without a photo), so a photo with two
plates shows twice. Photos that aren't identified yet have no sighting, so they show as their own
item until someone reviews them.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..models import PENDING_STATUSES, Photo, Plate, Sighting, User
from ..pipeline.process import R_BLURRY_NO_PLATE, R_NO_PLATE

SORTS = ("new", "old", "az", "most")
NEEDS_REVIEW = "Needs review"
NO_PLATE = "No plate found"


@dataclass
class FeedFilters:
    sort: str = "new"
    who: str = "all"  # all | mine | <username>
    date_from: date | None = None
    date_to: date | None = None
    states: list[str] = field(default_factory=list)
    vanity: bool = False
    review: bool = False
    missing: bool = False


@dataclass
class Item:
    key: str
    at: datetime | None
    tz: str | None
    user: User
    lat: float | None
    place: str | None
    photo_id: int | None
    plate: Plate | None = None
    sighting_id: int | None = None
    pending: str | None = None
    n: int = 0


def is_vanity(p: Plate) -> bool:
    return "vanity" in (p.tags or []) or bool(p.meaning)


def _window(stmt, column, f: FeedFilters):
    if f.date_from:
        stmt = stmt.where(column >= datetime.combine(f.date_from, time.min))
    if f.date_to:
        stmt = stmt.where(column < datetime.combine(f.date_to + timedelta(days=1), time.min))
    return stmt


def _user_ids(db: Session, f: FeedFilters, me: User) -> list[int] | None:
    if f.who == "all":
        return None
    if f.who == "mine":
        return [me.id]
    return list(db.scalars(select(User.id).where(User.username == f.who)))


def _sightings(db: Session, f: FeedFilters, users: list[int] | None) -> list[Item]:
    stmt = (
        select(Sighting)
        .join(Plate, Sighting.plate_id == Plate.id)
        .where(Plate.merged_into_id.is_(None))
        .options(joinedload(Sighting.plate), joinedload(Sighting.user))
    )
    stmt = _window(stmt, Sighting.seen_at, f)
    if users is not None:
        stmt = stmt.where(Sighting.user_id.in_(users))
    if f.states:
        stmt = stmt.where(Plate.state.in_(f.states))
    if f.missing:
        stmt = stmt.where(Sighting.lat.is_(None))
    rows = list(db.scalars(stmt).unique())
    if f.vanity:
        rows = [s for s in rows if is_vanity(s.plate)]
    counts = dict(
        db.execute(
            select(Sighting.plate_id, func.count()).where(Sighting.plate_id.in_({s.plate_id for s in rows}))
            .group_by(Sighting.plate_id)
        ).all()
    )
    return [
        Item(key=f"s{s.id}", at=s.seen_at, tz=s.tz_name, user=s.user, lat=s.lat, place=s.place_name,
             photo_id=s.photo_id, plate=s.plate, sighting_id=s.id, n=counts.get(s.plate_id, 0))
        for s in rows
    ]


def _pending(db: Session, f: FeedFilters, users: list[int] | None) -> list[Item]:
    if f.states or f.vanity:  # no plate yet, so no state and no meaning
        return []
    stmt = (
        select(Photo)
        .where(Photo.status == "needs_review")
        .options(joinedload(Photo.uploader), selectinload(Photo.detections))
    )
    stmt = _window(stmt, func.coalesce(Photo.taken_at, Photo.created_at), f)
    if users is not None:
        stmt = stmt.where(Photo.uploader_id.in_(users))
    if f.missing:
        stmt = stmt.where(Photo.lat.is_(None))
    out = []
    for p in db.scalars(stmt).unique():
        waiting = [d for d in p.detections if d.status in PENDING_STATUSES]
        no_plate = bool(waiting) and all(d.reason in (R_NO_PLATE, R_BLURRY_NO_PLATE) for d in waiting)
        out.append(Item(key=f"p{p.id}", at=p.taken_at or p.created_at, tz=p.tz_name, user=p.uploader,
                        lat=p.lat, place=p.place_name, photo_id=p.id, pending=NO_PLATE if no_plate else NEEDS_REVIEW))
    return out


def feed(db: Session, f: FeedFilters, me: User) -> list[Item]:
    users = _user_ids(db, f, me)
    items = _pending(db, f, users)
    if not f.review:
        items += _sightings(db, f, users)

    def ts(i: Item) -> float:
        return i.at.timestamp() if i.at else 0.0

    if f.sort == "old":
        items.sort(key=lambda i: (ts(i), i.key))
    elif f.sort == "az":  # photos without a plate go last
        items.sort(key=lambda i: (i.plate is None, i.plate.norm if i.plate else "", -ts(i)))
    elif f.sort == "most":
        items.sort(key=lambda i: (-i.n, i.plate.norm if i.plate else "~", -ts(i)))
    else:
        items.sort(key=lambda i: (-ts(i), i.key))
    return items
