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
# Direction reliability bins. probUp is clamped to [0.40, 0.60] by design, so
# the bins are deliberately narrow — the plot clusters near 0.5, which IS the
# honest picture (our calls are near-coin-flip), not a defect.
CAL_BINS = ((0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60))


def _pinball(actual: float, q: float, tau: float) -> float:
    """Quantile (pinball) loss: asymmetrically penalises an over- or
    under-shooting quantile by tau. Lower is better."""
    return (actual - q) * tau if actual >= q else (q - actual) * (1.0 - tau)


def band_pinball(resolved: list[dict], field: str = "bandPct") -> float | None:
    """Mean pinball loss treating an 80% band (+/-`field`% around a 0% expected
    move) as a P10/P90 quantile pair on the realised % change. Unlike coverage,
    this rewards a band that is well-sized AND covering: an over-wide band that
    always covers still scores worse than a tight one that does. `field` lets us
    score our band ('bandPct') and the EWMA baseline ('bandPctEwma') the same way."""
    losses = []
    for e in resolved:
        b, r = e.get(field), e.get("realizedChangePct")
        if b is None or r is None:
            continue
        losses.append((_pinball(r, -b, 0.10) + _pinball(r, b, 0.90)) / 2.0)
    return round(sum(losses) / len(losses), 4) if losses else None


def direction_calibration(resolved: list[dict]) -> tuple[list[dict], float | None]:
    """Reliability bins (predicted probUp vs realised up-rate) + a single
    calibration-error number = count-weighted mean |predicted - actual|."""
    rows, werr, wn = [], 0.0, 0
    for i, (lo, hi) in enumerate(CAL_BINS):
        last = i == len(CAL_BINS) - 1
        grp = [
            e for e in resolved
            if isinstance(e.get("probUp"), (int, float)) and e.get("upHit") is not None
            and (lo <= e["probUp"] <= hi if last else lo <= e["probUp"] < hi)
        ]
        if not grp:
            continue
        pred = sum(e["probUp"] for e in grp) / len(grp)
        actual = sum(e["upHit"] for e in grp) / len(grp)
        rows.append({"range": f"{int(lo * 100)}-{int(hi * 100)}%", "n": len(grp),
                     "predicted": round(pred, 3), "actual": round(actual, 3)})
        werr += abs(pred - actual) * len(grp)
        wn += len(grp)
    return rows, (round(werr / wn, 4) if wn else None)


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

    cal_bins, cal_err = direction_calibration(resolved)
    pinball = band_pinball(resolved)
    # EWMA baseline: only score it once enough forecasts carry an ewma band
    # (added going forward), so the comparison is honest, never on N=1.
    ewma_n = sum(1 for e in resolved
                 if e.get("bandPctEwma") is not None and e.get("realizedChangePct") is not None)
    base_gated = ewma_n >= 10
    pinball_base = band_pinball(resolved, field="bandPctEwma") if base_gated else None
    beats_base = (pinball is not None and pinball_base is not None and pinball <= pinball_base) \
        if base_gated else None

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
            "calibrationError": cal_err if gated else None,
            "calibrationBins": cal_bins if gated else [],
        },
        "band": {
            "target": BAND_TARGET,
            "coverageRate": (round(cov_k / cov_n, 3) if (gated and cov_n) else None),
            "coverageWilson95": (_wilson(cov_k, cov_n) if (gated and cov_n) else None),
            "pinball": pinball if gated else None,
            "pinballBaseline": pinball_base,            # EWMA baseline (None until baselineN>=10)
            "beatsBaseline": beats_base,                # True if our band <= EWMA on pinball
            "baselineN": ewma_n,
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
