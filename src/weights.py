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
