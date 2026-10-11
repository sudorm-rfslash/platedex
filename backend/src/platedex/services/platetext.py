"""Plate text normalization, look-alike folding and the search query language.

Query syntax (same as the Plates screen help popover):
  7AB*     starts with 7AB
  7A?12    ? is one unknown character
  ~LUVU2   fuzzy: look-alike aware (O/0, I/1/L, B/8, S/5, Z/2, U/V, G/6) plus one or two edits
  ski      plain words search meaning, notes and tags (and plate text)
"""

import re
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

# Characters that phone photos and OCR confuse. Every member of a group folds to the first one.
LOOKALIKE_GROUPS = ["O0QD", "I1L", "B8", "S5", "Z2", "UV", "G6"]
_FOLD = {ch: group[0] for group in LOOKALIKE_GROUPS for ch in group}

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
}
_STATE_BY_NAME = {v.upper(): k for k, v in US_STATES.items()}


def clean_display(text: str) -> str:
    """Uppercase, keep letters, digits, ? and the separators people type on plates (space, dash, dot)."""
    text = (text or "").upper().replace("·", "-").replace("•", "-")
    text = re.sub(r"[^A-Z0-9?\- .]", "", text)
    return re.sub(r"[\s.]+", " ", text).strip(" -")[:16]


def normalize(text: str) -> str:
    """Canonical comparison form: letters, digits and ? only."""
    return re.sub(r"[^A-Z0-9?]", "", (text or "").upper())


def skeleton(text: str) -> str:
    """Look-alike folded form, so B0SS and 8OSS compare equal."""
    return "".join(_FOLD.get(ch, ch) for ch in normalize(text))


def is_partial(text: str) -> bool:
    return "?" in normalize(text)


def normalize_state(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().upper()
    if v in US_STATES:
        return v
    return _STATE_BY_NAME.get(v)


def lookalike_pairs(a: str, b: str) -> list[tuple[str, str]]:
    """Positions where two equal-length plates differ only by look-alike characters."""
    a, b = normalize(a), normalize(b)
    if len(a) != len(b):
        return []
    diffs = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    if diffs and all(_FOLD.get(x, x) == _FOLD.get(y, y) for x, y in diffs):
        return diffs
    return []


def fuzzy_distance(a: str, b: str) -> int:
    return Levenshtein.distance(skeleton(a), skeleton(b))


def partial_matches(pattern: str, text: str) -> bool:
    """True if a stored partial plate (with ?) could be the given full plate."""
    p, t = normalize(pattern), normalize(text)
    if len(p) != len(t):
        return False
    return all(pc == "?" or pc == tc or tc == "?" for pc, tc in zip(p, t, strict=True))


@dataclass(frozen=True)
class Query:
    kind: str  # empty | fuzzy | wildcard | plain
    raw: str
    norm: str = ""
    regex: re.Pattern[str] | None = None


def parse_query(q: str | None) -> Query:
    raw = (q or "").strip()
    if not raw:
        return Query("empty", raw)
    if raw.startswith("~"):
        return Query("fuzzy", raw, normalize(raw[1:]))
    if re.search(r"[*?]", raw) and not re.search(r"\s", raw):
        n = re.sub(r"[^A-Z0-9?*]", "", raw.upper())
        pattern = "^" + n.replace("*", ".*").replace("?", ".")
        return Query("wildcard", raw, n, re.compile(pattern))
    return Query("plain", raw, normalize(raw))


def match_score(query: Query, text: str, haystack: str = "") -> float:
    """0 means no match. Higher is better. `haystack` holds meaning, notes and tags."""
    if query.kind == "empty":
        return 1.0
    n = normalize(text)
    if query.kind == "wildcard":
        assert query.regex is not None
        if query.regex.match(n):
            return 3.0
        # A stored partial plate can satisfy a wildcard query too (7A?123 vs 7AB*).
        if "?" in n and re.match(query.regex.pattern.replace(".", "[A-Z0-9?]"), n):
            return 2.0
        return 0.0
    if query.kind == "fuzzy":
        t = query.norm
        if not t:
            return 0.0
        if n == t:
            return 5.0
        sk, tk = skeleton(n), skeleton(t)
        if sk == tk:
            return 4.0
        if tk in sk:
            return 3.0
        limit = 1 if len(tk) < 7 else 2
        d = Levenshtein.distance(sk, tk)
        if d <= limit:
            return 3.0 - d
        if "?" in n and partial_matches(n, t):
            return 1.5
        return 0.0
    # plain
    t = query.norm
    score = 0.0
    if t:
        if n == t:
            score = 6.0
        elif n.startswith(t):
            score = 5.0
        elif t in n:
            score = 4.0
        elif skeleton(t) in skeleton(n):
            score = 3.0
        elif "?" in n and partial_matches(n, t):
            score = 2.5
    if not score and haystack:
        words = [w for w in re.split(r"\s+", query.raw.lower()) if w]
        hay = haystack.lower()
        if words and all(w.lstrip("#") in hay for w in words):
            score = 2.0
    return score
