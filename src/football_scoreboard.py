"""Aggregate the football ledger into web/football_scoreboard.json (fs2-v1).

Honest scoring for W/D/L forecasts:
- meanRpsModel: our Ranked Probability Score (lower is better).
- meanRpsMarket + skillVsMarket = marketRPS - ourRPS (positive = we beat the
  market's implied probabilities). This is the headline edge claim — proven,
  not asserted. Gated until enough matches carry market odds.
- accuracy: did our top pick (argmax of W/D/L) match the result, with a Wilson
  band; market accuracy shown alongside.
- calibrationError + bins: pooled over the three W/D/L outcomes — when we say
  "60% home", does it happen ~60% of the time.

Same N-gates as the other scoreboards (none<10, low<30, ok>=30). Negatives and
weaknesses are published, never hidden.
"""

from __future__ import annotations

import json
from pathlib import Path

from scoreboard import _confidence, _mean, _wilson  # shared honest helpers (DRY)

OUT = Path(__file__).resolve().parent.parent / "web" / "football_scoreboard.json"
# Pooled W/D/L reliability bins (deciles).
CAL_BINS = tuple((i / 10.0, (i + 1) / 10.0) for i in range(10))


def _top_pick(e: dict, hk: str, dk: str, ak: str) -> str | None:
    vals = {"home": e.get(hk), "draw": e.get(dk), "away": e.get(ak)}
    if any(v is None for v in vals.values()):
        return None
    return max(vals, key=lambda k: vals[k])


def calibration(resolved: list[dict]) -> tuple[list[dict], float | None]:
    """Reliability bins + calibration error, pooled over the three W/D/L
    outcomes (each match contributes three predicted-vs-realised points)."""
    points = []  # (predicted_prob, hit 0/1)
    for e in resolved:
        out = e.get("outcome")
        for cls, key in (("home", "probHome"), ("draw", "probDraw"), ("away", "probAway")):
            p = e.get(key)
            if isinstance(p, (int, float)) and out in ("home", "draw", "away"):
                points.append((p, 1.0 if out == cls else 0.0))
    rows, werr, wn = [], 0.0, 0
    for i, (lo, hi) in enumerate(CAL_BINS):
        last = i == len(CAL_BINS) - 1
        grp = [pt for pt in points if (lo <= pt[0] <= hi if last else lo <= pt[0] < hi)]
        if not grp:
            continue
        pred = sum(p for p, _ in grp) / len(grp)
        actual = sum(o for _, o in grp) / len(grp)
        rows.append({"range": f"{int(lo * 100)}-{int(hi * 100)}%", "n": len(grp),
                     "predicted": round(pred, 3), "actual": round(actual, 3)})
        werr += abs(pred - actual) * len(grp)
        wn += len(grp)
    return rows, (round(werr / wn, 4) if wn else None)


def build(cl: dict) -> dict:
    entries = cl.get("entries", [])
    resolved = [e for e in entries if e.get("status") == "RESOLVED" and e.get("rpsModel") is not None]
    n = len(resolved)
    conf = _confidence(n)
    gated = conf != "none"

    mean_rps = _mean([e["rpsModel"] for e in resolved])
    mk = [e for e in resolved if e.get("rpsMarket") is not None]
    market_n = len(mk)
    market_gated = market_n >= 10
    mean_rps_market = _mean([e["rpsMarket"] for e in mk]) if mk else None
    skill = (round(mean_rps_market - mean_rps, 6)
             if (market_gated and mean_rps is not None and mean_rps_market is not None) else None)

    bm = [e for e in resolved if e.get("beatMarket") is not None]
    bm_k = sum(1 for e in bm if e["beatMarket"])
    beat_rate = round(bm_k / len(bm), 3) if (market_gated and bm) else None
    beat_wilson = _wilson(bm_k, len(bm)) if (market_gated and bm) else None

    hits = sum(1 for e in resolved if _top_pick(e, "probHome", "probDraw", "probAway") == e.get("outcome"))
    accuracy = round(hits / n, 3) if gated else None
    mk_hits = sum(1 for e in mk if _top_pick(e, "marketProbHome", "marketProbDraw", "marketProbAway") == e.get("outcome"))
    market_accuracy = round(mk_hits / market_n, 3) if (market_gated and market_n) else None

    cal_bins, cal_err = calibration(resolved)

    return {
        "schemaVersion": "fs2-v1",
        "generatedFrom": "web/football_ledger.json",
        "counts": {
            "resolved": n,
            "open": sum(1 for e in entries if e.get("status") == "OPEN"),
            "void": sum(1 for e in entries if e.get("status") == "VOID"),
            "total": len(entries),
        },
        "confidence": conf,
        "model": {
            "meanRps": mean_rps if gated else None,            # lower is better
            "accuracy": accuracy,                              # top-pick hit rate
            "accuracyWilson95": (_wilson(hits, n) if gated else None),
            "calibrationError": cal_err if gated else None,
            "calibrationBins": cal_bins if gated else [],
        },
        "market": {
            "meanRps": mean_rps_market if market_gated else None,
            "accuracy": market_accuracy,
            "skillVsMarket": skill,                            # positive = we beat the market
            "beatMarketRate": beat_rate,
            "beatMarketWilson95": beat_wilson,
            "n": market_n,
        },
        "disclaimer": (
            "International-football W/D/L forecasts scored with RPS (lower is "
            "better). skillVsMarket = market RPS - our RPS (positive = we beat "
            "the market; shown even when negative). Calibration pooled over the "
            "three outcomes. Analytics only, not advice. Gated until enough "
            "resolved matches; market comparison needs matches with odds."
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
