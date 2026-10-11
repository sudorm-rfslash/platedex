from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow

ROLES = ("admin", "member", "viewer")

# Detection (review item) statuses
AUTO = "auto"  # accepted automatically, has a sighting
CONFIRMED = "confirmed"  # accepted by a human, has a sighting
NEEDS_VERIFY = "needs_verify"  # OCR has a reading but is unsure
NEEDS_IDENTIFY = "needs_identify"  # OCR found no plate or could not read it
READING = "reading"  # a user drew a box; waiting for the worker
REJECTED = "rejected"  # "not a plate" / "no plate in photo"
UNIDENTIFIED = "unidentified"  # "can't read, keep sighting"
PENDING_STATUSES = (NEEDS_VERIFY, NEEDS_IDENTIFY, READING)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    role: Mapped[str] = mapped_column(String(16), default="member")
    color: Mapped[str] = mapped_column(String(16), default="#1D4ED8")
    oidc_issuer: Mapped[str | None] = mapped_column(String(255))
    oidc_sub: Mapped[str | None] = mapped_column(String(255))
    oidc_linked_at: Mapped[datetime | None] = mapped_column(DateTime)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_sub", name="uq_users_oidc"),)


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(512))  # relative to photos dir
    mime: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)  # UTC
    tz_name: Mapped[str | None] = mapped_column(String(64))
    taken_at_source: Mapped[str | None] = mapped_column(String(16))  # exif | device | manual | upload
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    location_source: Mapped[str | None] = mapped_column(String(16))  # exif | device | manual
    place_name: Mapped[str | None] = mapped_column(String(128))
    place_state: Mapped[str | None] = mapped_column(String(8))
    blur: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    capture_mode: Mapped[str] = mapped_column(String(16), default="upload")  # upload | camera | token | import
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)

    uploader: Mapped[User] = relationship()
    detections: Mapped[list["Detection"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", order_by="Detection.id"
    )


class Detection(Base):
    """One plate (or one place a plate should be) in a photo. Doubles as the review item."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="auto")  # auto | manual_box | typed
    bbox: Mapped[list[float] | None] = mapped_column(JSON)  # [x, y, w, h] as fractions of the photo
    det_conf: Mapped[float | None] = mapped_column(Float)
    crop_path: Mapped[str | None] = mapped_column(String(512))
    crop_blur: Mapped[float | None] = mapped_column(Float)
    ocr: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # {text, conf, char_conf, candidates}
    vlm: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # {text, state, legible, conf, ...}
    text: Mapped[str | None] = mapped_column(String(16))
    char_conf: Mapped[list[float] | None] = mapped_column(JSON)
    candidates: Mapped[list[list[Any]] | None] = mapped_column(JSON)  # [[text, pct], ...]
    confidence: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str | None] = mapped_column(String(8))
    state_is_guess: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    claimed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    sighting_id: Mapped[int | None] = mapped_column(ForeignKey("sightings.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    photo: Mapped[Photo] = relationship(back_populates="detections")


class Plate(Base):
    __tablename__ = "plates"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(16))  # display form, e.g. DHK-4821 or 7A?123
    norm: Mapped[str] = mapped_column(String(16), index=True)
    skeleton: Mapped[str] = mapped_column(String(16), index=True)
    state: Mapped[str | None] = mapped_column(String(8))
    state_is_guess: Mapped[bool] = mapped_column(Boolean, default=True)
    meaning: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    notes_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_partial: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("plates.id", ondelete="SET NULL"))

    sightings: Mapped[list["Sighting"]] = relationship(back_populates="plate")


class Sighting(Base):
    __tablename__ = "sightings"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate_id: Mapped[int | None] = mapped_column(ForeignKey("plates.id", ondelete="SET NULL"), index=True)
    photo_id: Mapped[int | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"))
    detection_id: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    read_text: Mapped[str | None] = mapped_column(String(16))  # how this sighting was read
    seen_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)  # UTC
    tz_name: Mapped[str | None] = mapped_column(String(64))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    place_name: Mapped[str | None] = mapped_column(String(128))
    place_state: Mapped[str | None] = mapped_column(String(8))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    plate: Mapped[Plate | None] = relationship(back_populates="sightings")
    user: Mapped[User] = relationship()
    photo: Mapped[Photo | None] = relationship()

    __table_args__ = (Index("ix_sightings_latlon", "lat", "lon"),)


class PlateMerge(Base):
    """Audit log for merges so they can be undone."""

    __tablename__ = "plate_merges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_plate_id: Mapped[int] = mapped_column(ForeignKey("plates.id", ondelete="CASCADE"))
    target_plate_id: Mapped[int] = mapped_column(ForeignKey("plates.id", ondelete="CASCADE"))
    sighting_ids: Mapped[list[int]] = mapped_column(JSON)
    by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)


class DismissedDuplicate(Base):
    __tablename__ = "dismissed_duplicates"

    plate_a_id: Mapped[int] = mapped_column(ForeignKey("plates.id", ondelete="CASCADE"), primary_key=True)
    plate_b_id: Mapped[int] = mapped_column(ForeignKey("plates.id", ondelete="CASCADE"), primary_key=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    batch: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
