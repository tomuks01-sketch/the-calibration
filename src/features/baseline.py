"""Baseline / QEST layer (SIGNAL_SPEC.md L2) — probabilistic.

Thin, read-only wrapper over the QEST output already attached to events by
generate_snapshot (``event["model"]`` from model.evaluate). It does NOT
recompute or change the model. ``signalQuality`` stays "insufficient" until
the calibration gate (N>=30 resolved) is met — currently 0 resolved.
"""

from __future__ import annotations

from assets import Asset


def baseline_features(asset: Asset) -> dict:
    m = asset.raw.get("model") if isinstance(asset.raw, dict) else None
    prob = None
    gap = None
    if isinstance(m, dict):
        p = m.get("prob")
        if isinstance(p, (int, float)) and not isinstance(p, bool):
            prob = float(p)
        d = m.get("divergencePp")
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            gap = round(d / 100.0, 6)   # pp -> fraction (qest - crowd)
    return {
        "prob": prob,
        "gapVsCrowd": gap,
        # Per the calibration gate: no history-derived quality until N>=30
        # resolved outcomes exist. Honest fixed value until then.
        "signalQuality": "insufficient",
        "source": "model.py",
        "available": prob is not None,
    }
