"""Second-opinion plate reader: a vision-language model served by Ollama on the GPU."""

import base64
import json
import logging
import re
from dataclasses import dataclass

import httpx

from ..config import get_settings
from ..services.platetext import normalize, normalize_state

log = logging.getLogger(__name__)

PROMPT = """You are reading a United States license plate from a phone photo.
Image 1 is a close-up crop of the plate (it may be blurry, angled or partly hidden).
Image 2 is the whole photo, for context such as the plate design or state name.

Return JSON only:
- plate_text: the characters on the plate, uppercase letters and digits only, no spaces or dashes.
  Use ? for any single character you cannot read. Use "" if there is no readable plate.
- state: the two-letter USPS code of the issuing state if you can tell from the plate, else "".
- legible: true if you can read most characters.
- confidence: 0 to 1, how sure you are of plate_text.
- alternatives: up to 2 other plausible readings (look-alikes such as O/0, I/1, B/8, S/5).
Do not guess a state from the scenery. Do not invent characters."""

SCHEMA = {
    "type": "object",
    "properties": {
        "plate_text": {"type": "string"},
        "state": {"type": "string"},
        "legible": {"type": "boolean"},
        "confidence": {"type": "number"},
        "alternatives": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plate_text", "state", "legible", "confidence"],
}


@dataclass
class VlmReading:
    text: str
    state: str | None
    legible: bool
    confidence: float
    alternatives: list[str]
    model: str

    def as_json(self) -> dict:
        return {
            "text": self.text,
            "state": self.state,
            "legible": self.legible,
            "conf": round(self.confidence, 3),
            "alternatives": self.alternatives,
            "model": self.model,
        }


class VlmUnavailable(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def parse_response(content: str, model: str) -> VlmReading:
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError(f"No JSON in VLM reply: {content[:200]!r}")
    data = json.loads(m.group(0))
    text = normalize(str(data.get("plate_text", "")))[:10]
    try:
        conf = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf if conf <= 1 else conf / 100))
    alts = [normalize(str(a))[:10] for a in (data.get("alternatives") or []) if normalize(str(a))]
    return VlmReading(
        text=text,
        state=normalize_state(str(data.get("state") or "")),
        legible=bool(data.get("legible")) and bool(text),
        confidence=conf,
        alternatives=[a for a in alts if a != text][:2],
        model=model,
    )


def read_plate(crop_jpeg: bytes, photo_jpeg: bytes) -> VlmReading:
    s = get_settings()
    body = {
        "model": s.vlm_model,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": 0, "num_ctx": 4096},
        "messages": [{"role": "user", "content": PROMPT, "images": [_b64(crop_jpeg), _b64(photo_jpeg)]}],
    }
    try:
        r = httpx.post(f"{s.ollama_url.rstrip('/')}/api/chat", json=body, timeout=s.vlm_timeout)
    except httpx.HTTPError as e:
        raise VlmUnavailable(str(e)) from e
    if r.status_code == 404:
        raise VlmUnavailable(f"Model {s.vlm_model} is not pulled yet")
    if r.status_code >= 400:
        raise VlmUnavailable(f"Ollama error {r.status_code}: {r.text[:200]}")
    return parse_response(r.json().get("message", {}).get("content", ""), s.vlm_model)


def status() -> dict:
    """For /api/health and the admin screen."""
    s = get_settings()
    try:
        r = httpx.get(f"{s.ollama_url.rstrip('/')}/api/tags", timeout=3)
        names = [m.get("name") for m in r.json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        return {"reachable": False, "model": s.vlm_model, "ready": False, "error": str(e)[:200]}
    want = s.vlm_model if ":" in s.vlm_model else f"{s.vlm_model}:latest"
    return {"reachable": True, "model": s.vlm_model, "ready": want in names}


def ensure_model() -> None:
    """Pull the configured model if Ollama doesn't have it. Blocks until done (can take minutes)."""
    s = get_settings()
    st = status()
    if not st["reachable"] or st["ready"]:
        return
    log.info("Pulling VLM model %s (first start only)…", s.vlm_model)
    with httpx.stream(
        "POST", f"{s.ollama_url.rstrip('/')}/api/pull", json={"model": s.vlm_model}, timeout=None
    ) as r:
        for line in r.iter_lines():
            if '"error"' in line:
                log.error("Model pull failed: %s", line)
                return
    log.info("VLM model %s ready", s.vlm_model)
