"""Plate detector + OCR (fast-alpr's models, ONNX on CPU), loaded once per worker."""

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from ..config import get_settings

log = logging.getLogger(__name__)


@dataclass
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float


class Engine(Protocol):
    alphabet: str
    pad_char: str

    def detect(self, bgr: np.ndarray) -> list[Box]: ...

    def char_probs(self, crops: list[np.ndarray]) -> list[np.ndarray]: ...


class AlprEngine:
    """Wraps open-image-models (detector) and fast-plate-ocr (recognizer).

    char_probs returns the full (slots, vocab) probability matrix per crop, not only the
    top string, so several enhancement passes can vote character by character.
    """

    def __init__(self, detector_model: str, ocr_model: str, det_conf: float):
        from fast_plate_ocr import LicensePlateRecognizer
        from open_image_models.detection.factory import create_detector

        providers = ["CPUExecutionProvider"]
        self.detector = create_detector(detector_model, conf_thresh=det_conf, providers=providers)
        self.ocr = LicensePlateRecognizer(ocr_model, device="cpu")
        cfg = self.ocr.config
        self.alphabet: str = cfg.alphabet
        self.pad_char: str = cfg.pad_char or "_"
        self._slots: int = cfg.max_plate_slots
        self._rgb = cfg.image_color_mode == "rgb"

    def detect(self, bgr: np.ndarray) -> list[Box]:
        out = []
        for d in self.detector.predict(bgr):
            b = d.bounding_box
            out.append(Box(int(b.x1), int(b.y1), int(b.x2), int(b.y2), float(d.confidence)))
        return sorted(out, key=lambda b: -b.conf)

    def char_probs(self, crops: list[np.ndarray]) -> list[np.ndarray]:
        from fast_plate_ocr.core.process import preprocess_image
        from fast_plate_ocr.inference.plate_recognizer import _load_image_from_source

        imgs = [cv2.cvtColor(c, cv2.COLOR_BGR2RGB if self._rgb else cv2.COLOR_BGR2GRAY) for c in crops]
        x = preprocess_image(_load_image_from_source(imgs, self.ocr.config))
        (raw,) = self.ocr.model.run([self.ocr.plate_output_name], {"input": x})
        mats = raw.reshape((-1, self._slots, len(self.alphabet)))
        return [m for m in mats]


_engine: Engine | None = None
_lock = threading.Lock()


def get_engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            s = get_settings()
            log.info("Loading plate models %s + %s", s.ocr_detector_model, s.ocr_model)
            _engine = AlprEngine(s.ocr_detector_model, s.ocr_model, s.ocr_detector_conf)
        return _engine


def set_engine(engine: Engine | None) -> None:
    """Tests swap in a fake engine."""
    global _engine
    _engine = engine
