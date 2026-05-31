"""Feature store (SIGNAL_SPEC.md §7) — assembles per-asset records into the
frozen fs-v1 schema and writes web/features.json atomically.

P1 fills crowd + baseline only. regime / pressure / composite are present in
the schema but inert (descriptive placeholders / None) until P2–P4. Every
block keeps its ``available`` flag so the UI can show "unavailable" rather
than a fabricated value.
"""

from __future__ import annotations

import json
from pathlib import Path

from assets import Asset, from_coin, from_event
from composite import composite_signal
from features.baseline import baseline_features
from features.crowd import crowd_features
from weights import default_weights

SCHEMA_VERSION = "fs-v1"
WEIGHTS_VERSION = "w-v1"


def build_record(asset: Asset, crowd: dict, baseline: dict) -> dict:
    return {
        "assetId": asset.asset_id,
        "kind": asset.kind.value,
        "title": asset.title,
        "category": asset.category,
        "horizonDays": asset.horizon_days,
        "crowd": crowd,
        "baseline": baseline,
        # regime split from day one: descriptive context vs an inert
        # adjustment candidate (applied:false, contributes nothing in v1).
        "regime": {
            "descriptive": {"available": False, "source": None, "timestamp": None},
            "adjustmentCandidate": {"tilt": None, "applied": False},
        },
        # repricing is descriptive only — never folded into an outcome prob.
        "pressure": {"available": False, "class": "descriptive"},
        # composite is filled in P2; left None so nothing reads as a forecast.
        "composite": None,
    }


def build_records(
    events: list[dict], coins: list[dict], weights: dict | None = None
) -> list[dict]:
    w = weights if isinstance(weights, dict) else default_weights()
    records: list[dict] = []
    for e in events or []:
        a = from_event(e)
        records.append(build_record(a, crowd_features(a), baseline_features(a)))
    for c in coins or []:
        a = from_coin(c)
        records.append(build_record(a, crowd_features(a), baseline_features(a)))
    # P2: fill the composite for each record (None where there's no crowd
    # anchor, e.g. crypto). Weights are the documented prior until calibrated.
    for rec in records:
        rec["composite"] = composite_signal(rec, w)
    return records


def write_features(records: list[dict], path: Path, generated_at: str) -> None:
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "weightsVersion": WEIGHTS_VERSION,
        "generatedAt": generated_at,
        "records": records,
    }
    text = json.dumps(payload, indent=2)
    json.loads(text)  # validate before any swap
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)   # best-effort cleanup; keep original error
        except OSError:
            pass
        raise
