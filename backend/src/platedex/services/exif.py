"""Read capture time and GPS from photo metadata (JPEG, HEIC, AVIF, PNG, WebP)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import ExifTags, Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass

GPS_IFD = 0x8825
EXIF_IFD = 0x8769
T_DATETIME_ORIGINAL = 36867
T_DATETIME_DIGITIZED = 36868
T_OFFSET_ORIGINAL = 36881
T_OFFSET = 36880
T_DATETIME = 306


@dataclass
class PhotoMeta:
    width: int | None = None
    height: int | None = None
    mime: str | None = None
    lat: float | None = None
    lon: float | None = None
    accuracy_m: float | None = None
    local_time: datetime | None = None  # naive wall-clock time from the camera
    utc_offset: timedelta | None = None  # from OffsetTimeOriginal when present
    gps_time: datetime | None = None  # UTC, from GPSDateStamp/GPSTimeStamp

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def has_time(self) -> bool:
        return self.local_time is not None or self.gps_time is not None

    def taken_at_utc(self, tz_name: str | None) -> datetime | None:
        """Best UTC capture time: explicit offset, then GPS clock, then the location's time zone."""
        if self.local_time is not None and self.utc_offset is not None:
            return (self.local_time - self.utc_offset).replace(tzinfo=None)
        if self.gps_time is not None:
            return self.gps_time
        if self.local_time is not None and tz_name:
            from zoneinfo import ZoneInfo

            try:
                aware = self.local_time.replace(tzinfo=ZoneInfo(tz_name))
                return aware.astimezone(UTC).replace(tzinfo=None)
            except Exception:  # noqa: BLE001
                pass
        return self.local_time  # unknown zone: treat wall clock as UTC rather than drop it


def _ratio(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        num, den = v
        return float(num) / float(den) if den else 0.0


def _dms(values, ref) -> float | None:
    try:
        d, m, s = (_ratio(x) for x in values)
    except (TypeError, ValueError):
        return None
    out = d + m / 60 + s / 3600
    if isinstance(ref, bytes):
        ref = ref.decode(errors="ignore")
    if str(ref).strip().upper() in ("S", "W"):
        out = -out
    return out


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    value = str(value).strip().strip("\x00")
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def _parse_offset(value) -> timedelta | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    value = str(value).strip().strip("\x00")
    try:
        sign = -1 if value[0] == "-" else 1
        hh, mm = value.lstrip("+-").split(":")[:2]
        return sign * timedelta(hours=int(hh), minutes=int(mm))
    except (ValueError, IndexError):
        return None


# Only formats phones and cameras actually produce. Everything else Pillow can open (GIF, TIFF,
# BMP, PSD, EPS…) is refused, which also keeps rarely used decoders away from uploaded bytes.
# MPO is what Pillow calls JPEGs with extra embedded images (iPhone portrait shots, Android
# Ultra HDR). AVIF is offered by some Android cameras. RAW/DNG is left out on purpose: it needs a
# separate decoder and Pro-mode files are usually over the upload limit anyway.
FORMAT_MIME = {"JPEG": "image/jpeg", "MPO": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp",
               "HEIF": "image/heic", "AVIF": "image/avif"}
Image.init()  # Pillow registers most plugins lazily; load them so the list below is complete
PHOTO_FORMATS = [f for f in FORMAT_MIME if f in Image.OPEN]


def read_meta(data: bytes) -> PhotoMeta:
    meta = PhotoMeta()
    try:
        img = Image.open(BytesIO(data), formats=PHOTO_FORMATS)
    except Exception:  # noqa: BLE001
        return meta
    meta.width, meta.height = img.size
    meta.mime = FORMAT_MIME.get(img.format or "")
    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001
        return meta
    if not exif:
        return meta

    sub = exif.get_ifd(EXIF_IFD) or {}
    meta.local_time = (
        _parse_dt(sub.get(T_DATETIME_ORIGINAL))
        or _parse_dt(sub.get(T_DATETIME_DIGITIZED))
        or _parse_dt(exif.get(T_DATETIME))
    )
    meta.utc_offset = _parse_offset(sub.get(T_OFFSET_ORIGINAL) or sub.get(T_OFFSET))

    gps = exif.get_ifd(GPS_IFD) or {}
    if gps:
        g = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
        if "GPSLatitude" in g and "GPSLongitude" in g:
            lat = _dms(g["GPSLatitude"], g.get("GPSLatitudeRef", "N"))
            lon = _dms(g["GPSLongitude"], g.get("GPSLongitudeRef", "E"))
            if lat is not None and lon is not None and not (lat == 0 and lon == 0):
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    meta.lat, meta.lon = round(lat, 7), round(lon, 7)
        if "GPSHPositioningError" in g:
            try:
                meta.accuracy_m = _ratio(g["GPSHPositioningError"])
            except Exception:  # noqa: BLE001
                pass
        if "GPSDateStamp" in g and "GPSTimeStamp" in g:
            try:
                day = _parse_dt(str(g["GPSDateStamp"]) + " 00:00:00")
                h, m, s = (_ratio(x) for x in g["GPSTimeStamp"])
                if day:
                    meta.gps_time = day + timedelta(hours=h, minutes=m, seconds=int(s))
            except Exception:  # noqa: BLE001
                pass
    return meta


def parse_client_time(value: str | None) -> datetime | None:
    """Parse an ISO-8601 time from the browser into naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None)
