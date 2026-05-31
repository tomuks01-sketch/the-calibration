"""Composite layer (SIGNAL_SPEC.md §4) — probabilistic *candidate*.

A transparent weighted average of the available probabilistic layers
(crowd, baseline) in LOG-ODDS space, anchored on the crowd. While the weights
are an uncalibrated prior, the result is labelled "uncalibrated prior" and
must never replace or outrank the crowd/QEST numbers in the UI; the scored
ledger number stays QEST until the composite earns a resolved track record.

Honesty: crypto assets have no crowd outcome probability, so they get NO
composite (None). Missing layers simply drop out and lower ``coverage`` —
nothing is invented. ``contributions`` shows, in pp, how far each non-anchor
layer moved the result away from a crowd-only reading.
"""

from __future__ import annotations

import math


def _logit(p: float, lo: float = 0.01, hi: float = 0.99) -> float:
    p = min(hi, max(lo, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _avail_prob(block: object) -> float | None:
    if not isinstance(block, dict) or not block.get("available"):
        return None
    p = block.get("prob")
    return float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) else None


def composite_signal(record: dict, weights: dict) -> dict | None:
    """Compute the composite for one feature-store record, or None if there is
    no crowd outcome to anchor on (e.g. crypto)."""
    w = weights.get("weights", {}) if isinstance(weights, dict) else {}
    w_crowd = float(w.get("crowd", 0.0))
    w_base = float(w.get("baseline", 0.0))
    w_reg = float(w.get("regimeAdjustment", 0.0))

    crowd_p = _avail_prob(record.get("crowd"))
    if crowd_p is None or w_crowd <= 0:
        return None  # no anchor -> no probabilistic composite (honest)

    num = w_crowd * _logit(crowd_p)
    den = w_crowd
    base_p = _avail_prob(record.get("baseline"))
    if base_p is not None and w_base > 0:
        num += w_base * _logit(base_p)
        den += w_base
    # regime adjustment is an inert candidate in v0 (weight 0) — never folded in.

    comp = _sigmoid(num / den) if den > 0 else crowd_p
    total = w_crowd + w_base + w_reg
    coverage = round(den / total, 4) if total > 0 else 0.0
    calibrated = bool(weights.get("calibrated", False))
    return {
        "prob": round(comp, 4),
        "coverage": coverage,
        "weightsVersion": weights.get("weightsVersion"),
        "weightsCalibrated": calibrated,
        "label": "calibrated" if calibrated else "uncalibrated prior",
        "contributions": {
            # how far the composite sits from a crowd-only reading, in pp
            "baseline": round((comp - crowd_p) * 100.0, 1),
            "regime": 0.0,
        },
    }
