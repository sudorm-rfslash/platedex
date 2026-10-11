"""Demo data from the design prototype: 15 plates, 59 sightings, users alex / maya / jordan."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .api.auth import PALETTE
from .db import utcnow
from .models import Plate, Sighting, User
from .security import hash_password
from .services import geo
from .services.platetext import clean_display, is_partial, normalize, skeleton

CITY = {
    "A": (30.2672, -97.7431),  # Austin, TX
    "D": (32.7767, -96.7970),  # Dallas, TX
    "V": (39.7392, -104.9903),  # Denver, CO
    "S": (35.6870, -105.9378),  # Santa Fe, NM
    "P": (33.4484, -112.0740),  # Phoenix, AZ
}
CITY_NAME = {"A": "Austin, TX", "D": "Dallas, TX", "V": "Denver, CO", "S": "Santa Fe, NM", "P": "Phoenix, AZ"}
U = {"a": "alex", "m": "maya", "j": "jordan"}
RAW = [
    ("GR8FUL", "TX", "grateful", "vanity deadhead", "Tie-dye VW bus with Dead stickers. Usually parked on S Congress on weekends.",
     "03-02 A a,04-19 A m,06-07 D j,07-22 S a,09-14 A m,10-08 A j"),
    ("7ABC123", "CA", "", "", "White Tacoma with a roof tent",
     "01-18 P a,02-27 P j,04-03 S m,05-11 V a,06-29 V j,08-02 A m,09-05 A a,10-01 - j"),
    ("DHK-4821", "TX", "", "local", "Red Civic, probably a neighbor",
     "02-09 A a,03-15 A a,05-03 D m,06-21 A j,08-30 D a,09-28 - m,10-06 A a"),
    ("TX2CALI", "CA", "Texas to California", "vanity movers", "Towing a U-Haul trailer",
     "03-28 A m,05-16 D a,07-04 P j,08-19 P m,10-04 - a"),
    ("LUVU2", "CA", "love you too", "vanity", "", "04-02 P j,06-12 S a,08-08 V m,09-30 V j,10-05 - a"),
    ("NOTMYCAR", "CO", "not my car", "vanity ski", "Silver Subaru, ski rack", "01-07 V a,02-21 V m,07-30 S j,10-03 - m"),
    ("KGT-5527", "NY", "", "road-trip", "", "05-22 D a,06-02 A m,09-19 - j"),
    ("BXR7044", "WA", "", "road-trip", "", "07-11 V j,08-24 - a"),
    ("7A?123", "CA", "", "partial", "Bike rack hides the 3rd character", "09-02 P m"),
    ("CBS8105", "AZ", "", "", "", "02-14 P a,03-30 P j,06-18 S m,09-24 - a"),
    ("CXN-S58", "CO", "", "ski", "", "04-26 V m,08-15 S a"),
    ("LFR-308", "NM", "", "", "Green chile food truck", "03-09 S j,05-27 S a,08-11 P m,10-02 - j"),
    ("LNV-9302", "TX", "", "local", "", "06-05 D m,07-17 A a,09-09 - m"),
    ("H8MNDAZ", "CO", "hate Mondays", "vanity", "", "05-05 V a,09-21 - j"),
    ("SL0WPKE", "CA", "slowpoke", "vanity", "Zero, not O", "04-14 P m,07-26 A j,10-07 - a"),
    # A misread of GR8FUL, so the Plate page can demo "Possible duplicates — merge?"
    ("GR8FU1", "TX", "", "", "", "09-30 A m"),
]


def _ensure_user(db: Session, username: str, password: str, role: str, color: str) -> User:
    u = db.scalar(select(User).where(User.username == username))
    if u is None:
        u = User(username=username, role=role, color=color, password_hash=hash_password(password),
                 password_changed_at=utcnow())
        db.add(u)
        db.flush()
    return u


def seed_demo(db: Session, password: str = "platedex-demo", year: int = 2026) -> dict:
    users = {
        name: _ensure_user(db, name, password, "admin" if name == "alex" else "member", PALETTE[i])
        for i, name in enumerate(["alex", "maya", "jordan"])
    }
    made = 0
    for text, state, meaning, tags, note, sightings in RAW:
        norm = normalize(text)
        if db.scalar(select(Plate).where(Plate.norm == norm)) is not None:
            continue
        p = Plate(text=clean_display(text), norm=norm, skeleton=skeleton(norm), state=state, state_is_guess=False,
                  meaning=meaning or None, notes=note or None, tags=tags.split() if tags else [],
                  is_partial=is_partial(norm), created_by_id=users["alex"].id,
                  notes_by_id=users["maya"].id if note else None)
        db.add(p)
        db.flush()
        for k, item in enumerate(sightings.split(",")):
            d, c, u = item.split(" ")
            month, day = int(d[:2]), int(d[3:])
            hour, minute = (day * 7 + k * 5) % 11 + 8, (day * 13) % 60
            lat = lon = place = pstate = tz = None
            if c != "-":
                base_lat, base_lon = CITY[c]
                jitter = ((day * 37 + k * 11) % 21 - 10) / 1000, ((day * 53 + k * 7) % 21 - 10) / 1000
                lat, lon = round(base_lat + jitter[0], 5), round(base_lon + jitter[1], 5)
                place, pstate = CITY_NAME[c], CITY_NAME[c][-2:]
                tz = geo.timezone_at(lat, lon)
            local = datetime(year, month, day, hour, minute)
            zone = ZoneInfo(tz or "America/Chicago")
            seen = local.replace(tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            db.add(Sighting(plate_id=p.id, user_id=users[U[u]].id, read_text=p.text, seen_at=seen, tz_name=tz,
                            lat=lat, lon=lon, place_name=place, place_state=pstate))
            made += 1
    db.commit()
    return {"sightings": made, "users": list(users)}
