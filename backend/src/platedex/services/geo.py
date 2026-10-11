"""Offline reverse geocoding ("near Austin, TX"), time zones and distances.

Place names come from a GeoNames cities file prepared at image build time by
`platedex prepare-geo` (columns: lat, lon, name, admin1, country). Without it,
places fall back to rounded coordinates.
"""

import csv
import gzip
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import get_settings

EARTH_MI = 3958.8


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.pi / 180
    dlat, dlon = (lat2 - lat1) * r, (lon2 - lon1) * r
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_MI * math.asin(min(1.0, math.sqrt(h)))


def geo_dir() -> Path:
    s = get_settings()
    return s.geo_dir or (s.data_dir / "geo")


class _Places:
    def __init__(self, path: Path):
        lats, lons, labels, states = [], [], [], []
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as fh:
            for row in csv.reader(fh, delimiter="\t"):
                if len(row) < 5:
                    continue
                lat, lon, name, admin1, cc = row[:5]
                lats.append(float(lat))
                lons.append(float(lon))
                if cc == "US":
                    labels.append(f"{name}, {admin1}")
                    states.append(admin1)
                else:
                    labels.append(f"{name}, {cc}")
                    states.append("")
        self.lat = np.radians(np.array(lats, dtype=np.float64))
        self.lon = np.radians(np.array(lons, dtype=np.float64))
        self.labels = labels
        self.states = states

    def nearest(self, lat: float, lon: float) -> tuple[str, str | None, float]:
        la, lo = math.radians(lat), math.radians(lon)
        dlat = self.lat - la
        dlon = self.lon - lo
        h = np.sin(dlat / 2) ** 2 + np.cos(la) * np.cos(self.lat) * np.sin(dlon / 2) ** 2
        i = int(np.argmin(h))
        dist = 2 * EARTH_MI * math.asin(min(1.0, math.sqrt(float(h[i]))))
        return self.labels[i], (self.states[i] or None), dist


@lru_cache(maxsize=1)
def _places() -> _Places | None:
    for name in ("cities.tsv.gz", "cities.tsv"):
        p = geo_dir() / name
        if p.exists():
            return _Places(p)
    return None


def reverse_geocode(lat: float, lon: float) -> tuple[str, str | None]:
    """Return (place label, US state code or None)."""
    places = _places()
    if places is not None:
        label, state, dist = places.nearest(lat, lon)
        if dist <= 60:
            return label, state
    return f"{lat:.3f}, {lon:.3f}", None


@lru_cache(maxsize=1)
def _tzfinder():
    try:
        from timezonefinder import TimezoneFinder

        return TimezoneFinder(in_memory=True)
    except Exception:  # noqa: BLE001
        return None


def timezone_at(lat: float, lon: float) -> str | None:
    tf = _tzfinder()
    if tf is None:
        return None
    try:
        return tf.timezone_at(lng=lon, lat=lat)
    except Exception:  # noqa: BLE001
        return None


def prepare_geo(src: Path, out: Path, min_population: int = 5000) -> int:
    """Convert a GeoNames citiesNNNN.txt (or .zip) into the compact TSV used above."""
    import io
    import zipfile

    if src.suffix == ".zip":
        with zipfile.ZipFile(src) as z:
            name = next(n for n in z.namelist() if n.endswith(".txt"))
            text = io.TextIOWrapper(z.open(name), encoding="utf-8")
            rows = list(csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE))
    else:
        with open(src, encoding="utf-8") as fh:
            rows = list(csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t")
        for r in rows:
            try:
                pop = int(r[14] or 0)
            except (IndexError, ValueError):
                continue
            if pop < min_population:
                continue
            w.writerow([r[4], r[5], r[1], r[10], r[8]])
            n += 1
    return n
