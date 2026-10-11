"""Photo files on disk: originals (untouched), display JPEGs, thumbnails and plate crops."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from ..config import get_settings
from . import exif as _exif  # noqa: F401  (registers the HEIF opener)

EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heic",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


def root() -> Path:
    return get_settings().photos_dir


def original_rel(sha: str, mime: str | None, name: str) -> str:
    ext = EXT_BY_MIME.get(mime or "") or (Path(name).suffix.lower() or ".bin")
    return f"originals/{sha[:2]}/{sha}{ext}"


def save_original(rel: str, data: bytes) -> Path:
    p = root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_bytes(data)
    return p


def display_path(sha: str) -> Path:
    return root() / "display" / sha[:2] / f"{sha}.jpg"


def thumb_path(sha: str) -> Path:
    return root() / "thumbs" / sha[:2] / f"{sha}.jpg"


def crop_path(rel: str) -> Path:
    return root() / rel


def open_upright(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def write_derivatives(original: Path, sha: str) -> Image.Image:
    """Write the display JPEG and thumbnail; return the upright full-size RGB image."""
    img = open_upright(original)
    for path, size in ((display_path(sha), 2048), (thumb_path(sha), 480)):
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        copy = img.copy()
        copy.thumbnail((size, size), Image.Resampling.LANCZOS)
        copy.save(path, "JPEG", quality=86, optimize=True)
    return img


def save_crop(rel: str, img: Image.Image) -> None:
    p = root() / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p, "JPEG", quality=92)


def jpeg_bytes(img: Image.Image, max_side: int | None = None, quality: int = 88) -> bytes:
    if max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()
