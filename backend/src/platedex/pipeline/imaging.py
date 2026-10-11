"""Image helpers for blurry phone photos: blur scoring, padded crops and enhancement variants."""

import math

import cv2
import numpy as np
from PIL import Image


def to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def blur_score(bgr: np.ndarray, max_side: int = 1024) -> float:
    """0 = sharp, 1 = very blurry. Based on the variance of the Laplacian."""
    h, w = bgr.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return round(min(1.0, max(0.0, 1 - math.log10(var + 1) / 2.7)), 2)


def crop_blur_score(crop: np.ndarray) -> float:
    """Blur for a plate crop: 0 = sharp, 1 = very blurry.

    Crops vary in size and lighting, so large crops are scaled down to a fixed height and the Laplacian
    variance is divided by the crop's own contrast before scoring.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape[:2]
    if h < 4 or w < 4:
        return 1.0
    target = 96  # only scale down: upscaling would invent softness that isn't in the photo
    if h > target:
        gray = cv2.resize(gray, (max(4, int(w * target / h)), target), interpolation=cv2.INTER_AREA)
    ratio = float(cv2.Laplacian(gray, cv2.CV_64F).var()) / max(1.0, float(gray.std()) ** 2)
    return round(min(1.0, max(0.0, 1 - math.log2(1 + ratio) / 2)), 2)


def padded_box(x1: int, y1: int, x2: int, y2: int, w: int, h: int, pad: float = 0.12) -> tuple[int, int, int, int]:
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad), int(bh * pad * 1.6)
    return max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py)


def _deskew(crop: np.ndarray) -> np.ndarray | None:
    """Rotate so the plate's long edges are horizontal. Returns None when unsure."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=40, minLineLength=crop.shape[1] // 3, maxLineGap=8)
    if lines is None:
        return None
    angles = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if abs(a) < 20:
            angles.append(a)
    if not angles:
        return None
    angle = float(np.median(angles))
    if abs(angle) < 1.0:
        return None
    h, w = crop.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(crop, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _upscale(crop: np.ndarray, target_w: int = 384) -> np.ndarray:
    h, w = crop.shape[:2]
    if w >= target_w:
        return crop
    f = min(4.0, target_w / max(1, w))
    return cv2.resize(crop, (int(w * f), int(h * f)), interpolation=cv2.INTER_LANCZOS4)


def _clahe(crop: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    l_, a, b = cv2.split(lab)
    l_ = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4)).apply(l_)
    return cv2.cvtColor(cv2.merge((l_, a, b)), cv2.COLOR_LAB2BGR)


def _unsharp(crop: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(crop, (0, 0), 2.0)
    return cv2.addWeighted(crop, 1.7, blurred, -0.7, 0)


def variants(crop: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Several cleaned-up versions of one crop; OCR runs on each and the votes are combined."""
    base = _upscale(crop)
    out = [("raw", crop), ("upscaled", base), ("contrast", _clahe(base)), ("sharpened", _unsharp(_clahe(base)))]
    straight = _deskew(base)
    if straight is not None:
        out.append(("deskewed", _unsharp(_clahe(straight))))
    return out


def enlarge_for_viewing(crop: np.ndarray, min_w: int = 640) -> np.ndarray:
    return _unsharp(_upscale(crop, min_w)) if crop.shape[1] < min_w else crop
