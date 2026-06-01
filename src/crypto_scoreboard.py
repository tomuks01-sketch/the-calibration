"""Aggregate the crypto-forecast ledger into web/crypto_scoreboard.json (cs-v1).

Honest scoring vs the random-walk baseline (SIGNAL_SPEC.md §9):
- Direction: mean Brier of probUp vs the realised up/down outcome. The
  random-walk forecaster always says 0.5, whose Brier is EXACTLY 0.25 for any
  binary outcome — so skillVsRandomWalk = 0.25 - ourMeanBrier (positive only
  if we genuinely beat a coin flip). Published even when <= 0.
- Magnitude band: empirical coverage of the 80% band (target 0.80) with a
  Wilson interval. This is a volatility read, scored separately from direction.

Same N-gate as the PM scoreboard (none<10, low<30). Per-coin breakdown is
count-only / gated; we headline ONE aggregate number to avoid multiple-
comparisons inflation across 10 correlated coins.
"""

from __future__ import annotations

import json
from pathlib import Path

from crypto_ledger import BASELINE
from scoreboard import _confidence, _mean, _wilson  # shared honest helpers (DRY)

OUT = Path(__file__).resolve().parent.parent / "web" / "crypto_scoreboard.json"
BASELINE_BRIER = 0.25   # Brier of the always-0.5 (random-walk) direction forecaster
BAND_TARGET = 0.80      # the band is an 80% interval; coverage should approach this


def _by_coin(resolved: list[dict]) -> dict:
    coins: dict[str, list[dict]] = {}
    for e in resolved:
        coins.setdefault(e.get("symbol") or "—", []).append(e)
    out: dict[str, dict] = {}
    for sym, grp in coins.items():
        n = len(grp)
        gated = _confidence(n) != "none"
        cov = [e["bandCovered"] for e in grp if e.get("bandCovered") is not None]
        k = sum(1 for c in cov if c)
        out[sym] = {
            "n": n,
            "confidence": _confidence(n),
            "coverageRate": (round(k / len(cov), 3) if (gated and cov) else None),
        }
    return out


def build(cl: dict) -> dict:
    entries = cl.get("entries", [])
    resolved = [e for e in entries if e.get("status") == "RESOLVED"]
    n = len(resolved)
    conf = _confidence(n)
    gated = conf != "none"

    dir_briers = [e["brierUp"] for e in resolved if e.get("brierUp") is not None]
    mean_brier = _mean(dir_briers)
    skill = (round(BASELINE_BRIER - mean_brier, 5)
             if (gated and mean_brier is not None) else None)

    # direction accuracy (exclude ties where probUp == 0.5 — no call made)
    dir_grp = [e for e in resolved
               if e.get("probUp") not in (None, 0.5) and e.get("upHit") is not None]
    dir_hits = sum(1 for e in dir_grp if (e["probUp"] > 0.5) == (e["upHit"] == 1))
    up_hits = [e["upHit"] for e in resolved if e.get("upHit") is not None]

    cov = [e["bandCovered"] for e in resolved if e.get("bandCovered") is not None]
    cov_k, cov_n = sum(1 for c in cov if c), len(cov)

    return {
        "schemaVersion": "cs-v1",
        "generatedFrom": "web/crypto_ledger.json",
        "baseline": BASELINE,
        "bandTarget": BAND_TARGET,
        "counts": {
            "resolved": n,
            "open": sum(1 for e in entries if e.get("status") == "OPEN"),
            "void": sum(1 for e in entries if e.get("status") == "VOID"),
            "total": len(entries),
        },
        "confidence": conf,
        "direction": {
            "meanBrierUp": mean_brier if gated else None,
            "baselineBrier": BASELINE_BRIER,
            "skillVsRandomWalk": skill,            # positive = beat the coin flip
            "accuracy": (round(dir_hits / len(dir_grp), 3) if (gated and dir_grp) else None),
            "accuracyWilson95": (_wilson(dir_hits, len(dir_grp)) if (gated and dir_grp) else None),
            "observedUpRate": (round(_mean([float(x) for x in up_hits]), 3)
                               if (gated and up_hits) else None),
        },
        "band": {
            "target": BAND_TARGET,
            "coverageRate": (round(cov_k / cov_n, 3) if (gated and cov_n) else None),
            "coverageWilson95": (_wilson(cov_k, cov_n) if (gated and cov_n) else None),
            "n": cov_n,
        },
        "byCoin": _by_coin(resolved),
        "disclaimer": (
            "Crypto 24h forecasts scored vs a random-walk baseline. Direction: "
            "lower Brier is better; skillVsRandomWalk = 0.25 - our Brier "
            "(positive = better than a coin flip; shown even when negative). "
            "Band: empirical coverage of the 80% interval (target 0.80). "
            "Analytics only, not advice. Per-coin claims need many more samples "
            "(majors are highly correlated) — read the aggregate."
        ),
    }


def write(cl: dict) -> dict:
    sb = build(cl)
    text = json.dumps(sb, indent=2)
    json.loads(text)  # validate before swap
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(OUT)
    return sb
