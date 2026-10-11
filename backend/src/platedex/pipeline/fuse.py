"""Combine per-character probabilities from several OCR passes into one reading plus alternatives."""

import heapq
import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Reading:
    text: str
    char_conf: list[float]
    confidence: float  # geometric mean of the character probabilities, 0..1
    candidates: list[tuple[str, float]]  # top readings with confidence, best first

    @property
    def min_char(self) -> float:
        return min(self.char_conf) if self.char_conf else 0.0


def _geo_mean(ps: list[float]) -> float:
    if not ps:
        return 0.0
    return math.exp(sum(math.log(max(p, 1e-6)) for p in ps) / len(ps))


def fuse(prob_mats: list[np.ndarray], alphabet: str, pad_char: str = "_", top_k: int = 3) -> Reading:
    """prob_mats: one (slots, vocab) matrix per OCR pass over the same plate."""
    if not prob_mats:
        return Reading("", [], 0.0, [])
    p = np.mean(np.stack(prob_mats), axis=0)
    # Each slot keeps its top three characters; a small beam search builds whole-plate candidates.
    options: list[list[tuple[str, float]]] = []
    for slot in p:
        idx = np.argsort(slot)[::-1][:3]
        opts = [(alphabet[i], float(slot[i])) for i in idx if slot[i] >= 0.03]
        options.append(opts or [(alphabet[idx[0]], float(slot[idx[0]]))])

    beam: list[tuple[float, str, list[float]]] = [(0.0, "", [])]
    for opts in options:
        nxt = []
        for neg_logp, text, probs in beam:
            for ch, pr in opts:
                nxt.append((neg_logp - math.log(max(pr, 1e-9)), text + ch, probs + [pr]))
        beam = heapq.nsmallest(12, nxt, key=lambda t: t[0])

    seen: dict[str, list[float]] = {}
    for _, text, probs in sorted(beam, key=lambda t: t[0]):
        stripped = text.rstrip(pad_char)
        if pad_char in stripped or not stripped:
            continue  # padding in the middle isn't a real plate
        if stripped not in seen:
            seen[stripped] = probs[: len(stripped)]
    ranked = sorted(seen.items(), key=lambda kv: -_geo_mean(kv[1]))
    if not ranked:
        return Reading("", [], 0.0, [])
    best_text, best_probs = ranked[0]
    return Reading(
        text=best_text,
        char_conf=[round(x, 3) for x in best_probs],
        confidence=round(_geo_mean(best_probs), 3),
        candidates=[(t, round(_geo_mean(ps), 3)) for t, ps in ranked[:top_k]],
    )
