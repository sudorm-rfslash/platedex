from datetime import datetime, timedelta
from io import BytesIO

from conftest import jpeg

from platedex.services.exif import parse_client_time, read_meta


def test_reads_gps_and_time_with_offset():
    m = read_meta(jpeg())
    assert m.has_location and m.has_time
    assert abs(m.lat - 30.2672) < 1e-3
    assert abs(m.lon + 97.7431) < 1e-3
    assert m.local_time == datetime(2026, 10, 9, 17, 42)
    assert m.utc_offset == timedelta(hours=-5)
    assert m.taken_at_utc(None) == datetime(2026, 10, 9, 22, 42)


def test_uses_location_time_zone_when_offset_missing():
    m = read_meta(jpeg(offset=None))
    assert m.taken_at_utc("America/Chicago") == datetime(2026, 10, 9, 22, 42)


def test_stripped_file_has_no_location_or_time():
    m = read_meta(jpeg(gps=None, when=None))
    assert not m.has_location
    assert not m.has_time
    assert m.width == 800


def test_png_without_metadata():
    m = read_meta(jpeg(gps=None, when=None, fmt="PNG"))
    assert m.width == 800 and not m.has_location


def test_heic_roundtrip():
    from io import BytesIO

    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    src = Image.open(BytesIO(jpeg()))
    buf = BytesIO()
    src.save(buf, "HEIF", exif=src.getexif().tobytes())
    m = read_meta(buf.getvalue())
    assert m.has_location and m.has_time


def test_not_an_image():
    assert read_meta(b"hello").width is None


def test_only_photo_formats_are_accepted():
    from PIL import Image

    def enc(fmt: str, **kw) -> bytes:
        b = BytesIO()
        Image.new("RGB", (40, 20), "white").save(b, fmt, **kw)
        return b.getvalue()

    assert read_meta(enc("WEBP")).mime == "image/webp"
    assert read_meta(enc("AVIF")).mime == "image/avif"
    for fmt in ("GIF", "BMP", "TIFF"):
        assert read_meta(enc(fmt)).width is None, fmt
    # JPEGs with extra embedded pictures (MPO) are still JPEGs.
    a, b = Image.new("RGB", (40, 20)), Image.new("RGB", (40, 20))
    buf = BytesIO()
    a.save(buf, "MPO", save_all=True, append_images=[b])
    assert read_meta(buf.getvalue()).mime == "image/jpeg"


def test_client_time():
    assert parse_client_time("2026-10-09T17:42:00-05:00") == datetime(2026, 10, 9, 22, 42)
    assert parse_client_time("2026-10-09T22:42:00Z") == datetime(2026, 10, 9, 22, 42)
    assert parse_client_time("nope") is None


def test_formats_work_in_a_fresh_process():
    """Pillow loads most plugins lazily; the first upload after a restart must still be accepted."""
    import subprocess
    import sys

    code = (
        "from io import BytesIO\n"
        "from platedex.services.exif import read_meta\n"
        "from PIL import Image\n"
        "for fmt in ('JPEG', 'PNG', 'WEBP', 'AVIF'):\n"
        "    b = BytesIO(); Image.new('RGB', (40, 20)).save(b, fmt)\n"
        "    assert read_meta(b.getvalue()).width == 40, fmt\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
