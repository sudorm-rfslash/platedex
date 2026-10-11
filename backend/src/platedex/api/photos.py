import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Detection, Photo, Sighting, User
from ..security import current_user, member
from ..services import appsettings, geo, jobs, storage
from ..services.exif import parse_client_time, read_meta
from .serialize import photo_json

router = APIRouter(prefix="/api", tags=["photos"])

IMMUTABLE = {"Cache-Control": "private, max-age=31536000, immutable"}


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def ingest(
    db: Session,
    user: User,
    data: bytes,
    name: str,
    *,
    lat: float | None = None,
    lon: float | None = None,
    accuracy: float | None = None,
    location_source: str | None = None,
    taken_at: str | None = None,
    time_source: str | None = None,
    capture_mode: str = "upload",
) -> tuple[Photo, bool]:
    """Store a photo and queue it for reading. Returns (photo, is_new)."""
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Photo).where(Photo.sha256 == sha))
    if existing is not None:
        return existing, False
    meta = read_meta(data)
    if meta.width is None:
        raise HTTPException(
            415, "That file isn't a photo we can read. Use JPG, HEIC, PNG, WebP or AVIF (RAW/DNG isn't supported)"
        )

    p = Photo(uploader_id=user.id, sha256=sha, original_name=(name or "photo")[:255], mime=meta.mime,
              width=meta.width, height=meta.height, capture_mode=capture_mode)
    if meta.has_location:
        p.lat, p.lon, p.accuracy_m, p.location_source = meta.lat, meta.lon, meta.accuracy_m, "exif"
    elif lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        p.lat, p.lon, p.accuracy_m = lat, lon, accuracy
        p.location_source = location_source if location_source in ("device", "manual") else "device"
    if p.lat is not None:
        p.tz_name = geo.timezone_at(p.lat, p.lon)
        p.place_name, p.place_state = geo.reverse_geocode(p.lat, p.lon)
    if meta.has_time:
        p.taken_at, p.taken_at_source = meta.taken_at_utc(p.tz_name), "exif"
    elif (client_time := parse_client_time(taken_at)) is not None:
        p.taken_at = client_time
        p.taken_at_source = time_source if time_source in ("device", "manual") else "device"

    p.path = storage.original_rel(sha, meta.mime, name)
    storage.save_original(p.path, data)
    db.add(p)
    db.flush()
    jobs.enqueue(db, "process_photo", {"photo_id": p.id})
    db.commit()
    return p, True


@router.post("/photos")
async def upload_photo(
    file: UploadFile = File(...),
    lat: str | None = Form(None),
    lon: str | None = Form(None),
    accuracy: str | None = Form(None),
    location_source: str | None = Form(None),
    taken_at: str | None = Form(None),
    time_source: str | None = Form(None),
    capture_mode: str = Form("upload"),
    user: User = Depends(member),
    db: Session = Depends(get_db),
):
    mb = int(appsettings.get(db, "max_upload_mb"))
    data = await file.read(mb * 1024 * 1024 + 1)
    if len(data) > mb * 1024 * 1024:
        raise HTTPException(413, f"Photos must be under {mb} MB")
    if capture_mode not in ("upload", "camera", "token"):
        capture_mode = "upload"
    photo, is_new = ingest(
        db, user, data, file.filename or "photo",
        lat=_float(lat), lon=_float(lon), accuracy=_float(accuracy), location_source=location_source,
        taken_at=taken_at, time_source=time_source, capture_mode=capture_mode,
    )
    return {**photo_json(photo), "duplicate": not is_new}


@router.get("/photos")
def list_photos(ids: str | None = Query(None), mine: bool = True, limit: int = 30,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Photo).order_by(Photo.id.desc())
    if ids:
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()][:200]
        stmt = stmt.where(Photo.id.in_(wanted))
    elif mine:
        stmt = stmt.where(Photo.uploader_id == user.id).limit(min(limit, 100))
    return [photo_json(p) for p in db.scalars(stmt)]


def _photo(db: Session, photo_id: int) -> Photo:
    p = db.get(Photo, photo_id)
    if p is None:
        raise HTTPException(404, "Photo not found")
    return p


@router.post("/photos/{photo_id}/retry")
def retry(photo_id: int, user: User = Depends(member), db: Session = Depends(get_db)):
    p = _photo(db, photo_id)
    if p.status in ("queued", "processing"):
        return photo_json(p)  # already waiting for the worker; don't queue it twice
    p.status, p.error = "queued", None
    jobs.enqueue(db, "process_photo", {"photo_id": p.id})
    db.commit()
    return photo_json(p)


class PhotoPatch(BaseModel):
    lat: float | None = None
    lon: float | None = None
    taken_at: str | None = None


@router.patch("/photos/{photo_id}")
def patch_photo(photo_id: int, body: PhotoPatch, user: User = Depends(member), db: Session = Depends(get_db)):
    """Fix a missing location or time after the fact. Updates the photo's sightings too."""
    p = _photo(db, photo_id)
    if (body.lat is None) != (body.lon is None):
        raise HTTPException(400, "Send both latitude and longitude")
    if body.lat is not None and not (-90 <= body.lat <= 90 and -180 <= body.lon <= 180):
        raise HTTPException(400, "That location is off the map")
    if body.lat is not None and body.lon is not None:
        p.lat, p.lon, p.accuracy_m, p.location_source = body.lat, body.lon, None, "manual"
        p.tz_name = geo.timezone_at(p.lat, p.lon)
        p.place_name, p.place_state = geo.reverse_geocode(p.lat, p.lon)
    if body.taken_at:
        t = parse_client_time(body.taken_at)
        if t is None:
            raise HTTPException(400, "Couldn't understand that time")
        p.taken_at, p.taken_at_source = t, "manual"
    for s in db.scalars(select(Sighting).where(Sighting.photo_id == p.id)):
        s.lat, s.lon, s.place_name, s.place_state, s.tz_name = p.lat, p.lon, p.place_name, p.place_state, p.tz_name
        if p.taken_at:
            s.seen_at = p.taken_at
    db.commit()
    return photo_json(p)


@router.get("/geo/reverse")
def reverse(lat: float, lon: float, user: User = Depends(current_user)):
    place, state = geo.reverse_geocode(lat, lon)
    return {"place": place, "state": state, "tz": geo.timezone_at(lat, lon)}


def _file(path, media: str = "image/jpeg") -> FileResponse:
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=media, headers=IMMUTABLE)


@router.get("/photos/{photo_id}/display")
def photo_display(photo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _photo(db, photo_id)
    path = storage.display_path(p.sha256)
    if not path.exists():
        storage.write_derivatives(storage.root() / p.path, p.sha256)
    return _file(path)


@router.get("/photos/{photo_id}/thumb")
def photo_thumb(photo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _photo(db, photo_id)
    path = storage.thumb_path(p.sha256)
    if not path.exists():
        storage.write_derivatives(storage.root() / p.path, p.sha256)
    return _file(path)


@router.get("/photos/{photo_id}/original")
def photo_original(photo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _photo(db, photo_id)
    path = storage.root() / p.path
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=p.mime or "application/octet-stream",
                        filename=p.original_name)


@router.get("/detections/{det_id}/crop")
def detection_crop(det_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.get(Detection, det_id)
    if d is None or not d.crop_path:
        raise HTTPException(404, "No crop")
    return _file(storage.crop_path(d.crop_path))
