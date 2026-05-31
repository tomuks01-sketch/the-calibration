"""Aggregate the ledger into web/scoreboard.json — honestly.

N-gating (team rule): below 10 resolved calls show NO Brier; below 30 show it
only with a "too few to be meaningful" flag. Always expose pending/void counts
so nothing is hidden. Brier is labelled snapshot-scoped.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ledger import SAMPLE_NOTE
from model import MODEL_VERSION

OUT = Path(__file__).resolve().parent.parent / "web" / "scoreboard.json"


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 5) if xs else None


def _confidence(n: int) -> str:
    return "none" if n < 10 else ("low" if n < 30 else "ok")


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for a proportion k/n. Honest small-N bands
    (the interval is wide when N is small — that *is* the point)."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return [round(max(0.0, centre - margin), 3), round(min(1.0, centre + margin), 3)]


def _by_category(resolved: list[dict]) -> dict:
    """Per-category model vs crowd Brier + a Wilson band on the rate at which
    the model beat the crowd. Gated per category (none<10, low<30)."""
    cats: dict[str, list[dict]] = {}
    for e in resolved:
        # Self-guard: only count entries with both Briers (don't rely on the
        # caller's pre-filter). Keeps the bare brier access below safe.
        if e.get("modelBrier") is None or e.get("marketBrier") is None:
            continue
        cats.setdefault(e.get("category") or "—", []).append(e)
    out: dict[str, dict] = {}
    for cat, grp in cats.items():
        n = len(grp)
        conf = _confidence(n)
        gated = conf != "none"
        mb = _mean([e["modelBrier"] for e in grp])
        cb = _mean([e["marketBrier"] for e in grp])
        beats = sum(1 for e in grp if e["modelBrier"] < e["marketBrier"])
        out[cat] = {
            "n": n,
            "confidence": conf,
            "modelBrier": mb if gated else None,
            "crowdBrier": cb if gated else None,
            "skillVsCrowd": (round(cb - mb, 5) if (gated and mb is not None and cb is not None) else None),
            "beatsCrowdRate": round(beats / n, 3) if gated else None,
            "beatsCrowdWilson95": _wilson(beats, n) if gated else None,
        }
    return out


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

    confidence = _confidence(n)
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
        # Per-category Brier + Wilson confidence bands (empty until categories
        # accumulate resolved calls; gated per category — honest small-N).
        "byCategory": _by_category(resolved),
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
