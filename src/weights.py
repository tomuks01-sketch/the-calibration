"""Composite weights (SIGNAL_SPEC.md §4, §7).

Weights live in web/weights.json as named, version-stamped, documented
parameters — never as literals buried in code. v0 is a fixed prior
(``calibrated: false``); ``calibrate_from_ledger`` (later, P6) will refit them
from resolved outcomes once N>=30. Until then the composite is labelled an
uncalibrated prior everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

# The documented v0 prior. Kept in code as the canonical fallback so the
# composite is reproducible even if weights.json is missing.
_DEFAULT = {
    "weightsVersion": "w-v1",
    "calibrated": False,
    "note": "fixed documented prior; not fitted to outcomes",
    "weights": {"crowd": 0.7, "baseline": 0.2, "regimeAdjustment": 0.0},
    "scales": {"gap": 0.15, "fundingZ": 2.0},
}


def default_weights() -> dict:
    """A fresh copy of the documented v0 prior."""
    return json.loads(json.dumps(_DEFAULT))


def _valid(w: object) -> bool:
    return (
        isinstance(w, dict)
        and isinstance(w.get("weights"), dict)
        and all(k in w["weights"] for k in ("crowd", "baseline", "regimeAdjustment"))
        and "calibrated" in w
        and "weightsVersion" in w
    )


def load_weights(path: str | Path | None = None) -> dict:
    """Load + validate weights.json; fall back to the documented prior on any
    problem (fail-open: the composite must never crash the snapshot)."""
    if path is None:
        return default_weights()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if _valid(data) else default_weights()
    except (OSError, ValueError):
        return default_weights()


MIN_CALIBRATION_N = 30


def calibrate_from_ledger(ledger: dict, min_n: int = MIN_CALIBRATION_N) -> dict:
    """Refit the composite weights from RESOLVED outcomes by minimising Brier,
    using the SAME composite_signal used in production. Honesty gate: below
    ``min_n`` resolved calls, return the documented prior UNCHANGED — never fit
    on thin data (SIGNAL_SPEC.md §4/§6). At/above the gate, grid-search the
    crowd/baseline split and bump the weightsVersion so old calls keep theirs.
    """
    from datetime import datetime, timezone

    from composite import composite_signal

    resolved = [
        e for e in ledger.get("entries", [])
        if e.get("status") == "RESOLVED"
        and isinstance(e.get("modelProb"), (int, float))
        and isinstance(e.get("crowdProbAtCallTime"), (int, float))
        and e.get("resolvedOutcome") in (0, 1)
    ]
    n = len(resolved)
    prior = default_weights()
    if n < min_n:
        prior["calibrated"] = False
        prior["note"] = f"insufficient N ({n}/{min_n}) — prior unchanged, not fitted to outcomes"
        prior["resolvedN"] = n
        return prior

    def _brier(w_crowd: float) -> float:
        cand = {
            "weightsVersion": "fit",
            "calibrated": True,
            "weights": {"crowd": w_crowd, "baseline": round(1.0 - w_crowd, 4), "regimeAdjustment": 0.0},
        }
        sq = []
        for e in resolved:
            rec = {
                "crowd": {"prob": e["crowdProbAtCallTime"], "available": True},
                "baseline": {"prob": e["modelProb"], "available": True},
            }
            c = composite_signal(rec, cand)
            if c is not None:
                sq.append((c["prob"] - e["resolvedOutcome"]) ** 2)
        return sum(sq) / len(sq) if sq else float("inf")

    best_w, best_b = 0.5, float("inf")
    for i in range(0, 21):              # crowd weight 0.00 .. 1.00 step 0.05
        wc = round(i * 0.05, 2)
        b = _brier(wc)
        if b < best_b:
            best_b, best_w = b, wc

    out = default_weights()
    out["weights"] = {"crowd": best_w, "baseline": round(1.0 - best_w, 4), "regimeAdjustment": 0.0}
    out["calibrated"] = True
    out["weightsVersion"] = "w-cal-" + datetime.now(timezone.utc).strftime("%Y%m%d")
    out["note"] = f"fitted to {n} resolved outcomes by Brier minimisation"
    out["fittedN"] = n
    out["fittedBrier"] = round(best_b, 6)
    return out
