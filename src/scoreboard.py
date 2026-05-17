"""Aggregate the ledger into web/scoreboard.json — honestly.

N-gating (team rule): below 10 resolved calls show NO Brier; below 30 show it
only with a "too few to be meaningful" flag. Always expose pending/void counts
so nothing is hidden. Brier is labelled snapshot-scoped.
"""

from __future__ import annotations

import json
from pathlib import Path

from ledger import SAMPLE_NOTE
from model import MODEL_VERSION

OUT = Path(__file__).resolve().parent.parent / "web" / "scoreboard.json"


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 5) if xs else None


def build(ledger: dict) -> dict:
    entries = ledger["entries"]
    resolved = [
        e for e in entries
        if e["status"] == "RESOLVED" and e["modelBrier"] is not None
    ]
    n = len(resolved)
    model_briers = [e["modelBrier"] for e in resolved]
    market_briers = [e["marketBrier"] for e in resolved]
    mm, cm = _mean(model_briers), _mean(market_briers)

    confidence = "none" if n < 10 else ("low" if n < 30 else "ok")
    skill = (
        round(cm - mm, 5)
        if (mm is not None and cm is not None) else None
    )

    # 5-bin calibration on model probability vs realized outcome rate
    bins = []
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        hi = lo + 0.2
        grp = [e for e in resolved if lo <= e["modelProb"] < hi
               or (hi == 1.0 and e["modelProb"] == 1.0)]
        if grp:
            bins.append({
                "range": f"{int(lo*100)}-{int(hi*100)}%",
                "n": len(grp),
                "predicted": round(_mean([e["modelProb"] for e in grp]), 3),
                "actual": round(_mean([e["resolvedOutcome"] for e in grp]), 3),
            })

    return {
        "generatedFrom": "web/ledger.json",
        "modelVersion": MODEL_VERSION,
        "sampleNote": SAMPLE_NOTE,
        "counts": {
            "resolved": n,
            "pending": sum(1 for e in entries if e["status"] == "PENDING"),
            "void": sum(1 for e in entries if e["status"] == "VOID"),
            "total": len(entries),
        },
        "confidence": confidence,
        "snapshotScopedModelBrier": mm if confidence != "none" else None,
        "snapshotScopedCrowdBrier": cm if confidence != "none" else None,
        "skillVsCrowd": skill if confidence != "none" else None,
        "calibration": bins if confidence != "none" else [],
        "disclaimer": (
            "Baseline statistical model, not advice, not an edge claim. "
            "Brier is snapshot-scoped (selection caveat above). Lower Brier "
            "is better; skill = crowd Brier - model Brier (positive = model "
            "beat the crowd on this scoped sample)."
        ),
    }


def write(ledger: dict) -> dict:
    sb = build(ledger)
    # Atomic write (same pattern as ledger.save_ledger): never leave a
    # half-written scoreboard.json if the process is killed mid-write.
    text = json.dumps(sb, indent=2)
    json.loads(text)  # validate before swap
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(OUT)
    return sb
