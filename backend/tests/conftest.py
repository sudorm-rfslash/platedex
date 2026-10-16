import os
import tempfile
from fractions import Fraction
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

_tmp = Path(tempfile.mkdtemp(prefix="platedex-test-"))
os.environ["DATA_DIR"] = str(_tmp)
os.environ["SECRET_KEY"] = "test-secret"
os.environ["STATIC_DIR"] = str(_tmp / "no-frontend")
os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"  # nothing listens here

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from platedex.config import get_settings  # noqa: E402
from platedex.db import Base, make_engine, set_engine  # noqa: E402
from platedex.pipeline import engines  # noqa: E402
from platedex.pipeline.engines import Box  # noqa: E402

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"


def probs_for(text: str, conf: float | list[float] = 0.98, alt: dict[int, str] | None = None) -> np.ndarray:
    """A (10, 37) probability matrix that reads `text` with the given per-character confidence."""
    m = np.full((10, len(ALPHABET)), 1e-4)
    confs = conf if isinstance(conf, list) else [conf] * len(text)
    for i in range(10):
        if i < len(text):
            ch, c = text[i], confs[i]
            m[i, ALPHABET.index(ch)] = c
            other = (alt or {}).get(i) or ALPHABET[(ALPHABET.index(ch) + 7) % 36]
            m[i, ALPHABET.index(other)] = 1 - c
        else:
            m[i, ALPHABET.index("_")] = 0.999
        m[i] /= m[i].sum()
    return m


class FakeEngine:
    alphabet = ALPHABET
    pad_char = "_"

    def __init__(self):
        self.boxes: list[Box] = [Box(100, 200, 300, 260, 0.9)]
        self.mat = probs_for("GR8FUL")

    def detect(self, bgr):
        h, w = bgr.shape[:2]
        return [b for b in self.boxes if b.x2 <= w and b.y2 <= h]

    def char_probs(self, crops):
        return [self.mat for _ in crops]


@pytest.fixture()
def fake_engine():
    e = FakeEngine()
    engines.set_engine(e)
    yield e
    engines.set_engine(None)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    set_engine(engine)
    write_test_places(tmp_path / "geo" / "cities.tsv")
    from platedex.main import create_app

    yield create_app()
    engine.dispose()


TEST_PLACES = [
    (30.2672, -97.7431, "Austin", "TX", "US"),
    (32.7767, -96.7970, "Dallas", "TX", "US"),
    (39.7392, -104.9903, "Denver", "CO", "US"),
    (35.6870, -105.9378, "Santa Fe", "NM", "US"),
    (33.4484, -112.0740, "Phoenix", "AZ", "US"),
]


def write_test_places(path: Path) -> None:
    from platedex.services import geo

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join("\t".join(str(x) for x in row) + "\n" for row in TEST_PLACES))
    geo._places.cache_clear()


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        c.headers["x-platedex"] = "1"
        yield c


def make_admin(client, username="alex", password="password123"):
    r = client.post("/api/auth/setup", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def jpeg(gps: tuple[float, float] | None = (30.2672, -97.7431), when: str | None = "2026:10:09 17:42:00",
         offset: str | None = "-05:00", size=(800, 600), color=(120, 130, 140), fmt="JPEG") -> bytes:
    rng = np.random.default_rng(sum(color) * 7919 + size[0])
    noise = rng.integers(0, 60, (size[1], size[0], 3), dtype=np.uint8)
    img = Image.fromarray(np.clip(np.array(color, dtype=np.int16) + noise, 0, 255).astype(np.uint8))
    exif = Image.Exif()
    if when:
        sub = exif.get_ifd(0x8769)
        sub[36867] = when
        if offset:
            sub[36881] = offset
    if gps:
        lat, lon = gps

        def dms(v):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            s = round(((v - d) * 60 - m) * 60 * 100)
            return (Fraction(d), Fraction(m), Fraction(s, 100))

        g = exif.get_ifd(0x8825)
        g[1] = "N" if lat >= 0 else "S"
        g[2] = dms(lat)
        g[3] = "E" if lon >= 0 else "W"
        g[4] = dms(lon)
    buf = BytesIO()
    img.save(buf, fmt, exif=exif.tobytes())
    return buf.getvalue()


@pytest.fixture()
def seeded(client):
    """Signed in as alex (admin) with the demo plates loaded."""
    from platedex.db import db_session
    from platedex.seed import seed_demo

    make_admin(client, "alex", "password123")
    with db_session() as db:
        out = seed_demo(db)
    assert out["sightings"] == 60  # 59 from the design + 1 GR8FU1 misread
    return client


@pytest.fixture()
def no_vlm(monkeypatch):
    from platedex.pipeline import vlm as vlm_mod

    def unavailable(*_a, **_k):
        raise vlm_mod.VlmUnavailable("off in tests")

    monkeypatch.setattr(vlm_mod, "read_plate", unavailable)
