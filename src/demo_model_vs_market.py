"""DEMO / PROTOTYPE — not shipped, not deployed.

Shows what an honest "model vs market" layer would look like, computed from
the live snapshot's observable fields only.

HONESTY (read this):
- The market probability IS the crowd's aggregated estimate. We do NOT claim
  to beat it. This baseline is deliberately simple and UNPROVEN.
- Its only future value is the PUBLIC SCORED LEDGER: every model estimate is
  timestamped and Brier-scored on resolution. Until that record exists and is
  good, the model number means nothing. We say so out loud.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "web" / "data.json"

# Transparent baseline: nudge the market probability by recent 1-week momentum
# of the leading outcome, damped hard. This is NOT an edge claim — it is a
# falsifiable, simple hypothesis whose worth is decided only by the ledger.
MOMENTUM_WEIGHT = 0.25  # how much 1w move nudges the baseline (damped)
DIVERGENCE_FLAG = 0.04  # |model - market| >= 4pp -> flag as a tracked call


def clamp01(x: float) -> float:
    return max(0.01, min(0.99, x))


def model_probability(market_p: float, lead_week_change: float | None) -> float:
    """Baseline = market price softly nudged by leader's 1w momentum."""
    if lead_week_change is None:
        return market_p
    return clamp01(market_p + MOMENTUM_WEIGHT * lead_week_change)


def main() -> None:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    gen = d["generatedAt"]
    rows = []
    for e in d["events"]:
        mp = e.get("leadPrice")
        if mp is None:
            continue
        outs = e.get("outcomes") or []
        lead_wk = outs[0].get("weekChange") if outs else None
        model_p = model_probability(mp, lead_wk)
        div = model_p - mp
        rows.append((abs(div), e["category"], e["title"], mp, model_p, div,
                     e.get("daysToResolution")))

    rows.sort(reverse=True)
    print(f"MODEL vs MARKET — demo from snapshot {gen}\n")
    print(f"{'category':14} {'market':>7} {'model':>7} {'diverg':>7} {'call?':>6}  question")
    print("-" * 92)
    for adiv, cat, title, mp, model_p, div, days in rows[:12]:
        call = "TRACK" if adiv >= DIVERGENCE_FLAG else "-"
        print(
            f"{cat[:14]:14} {mp * 100:6.1f}% {model_p * 100:6.1f}% "
            f"{div * 100:+6.1f}pp {call:>6}  {title[:46]}"
        )

    flagged = [r for r in rows if r[0] >= DIVERGENCE_FLAG]
    print(f"\n{len(flagged)} markets would generate a TRACKED model call this run.")
    print("\nHow each TRACK becomes a public ledger row (the actual moat):")
    if flagged:
        adiv, cat, title, mp, model_p, div, days = flagged[0]
        print(json.dumps({
            "ts": gen,
            "market": title[:60],
            "marketProb": round(mp, 4),
            "modelProb": round(model_p, 4),
            "divergencePp": round(div * 100, 2),
            "resolvesInDays": days,
            "status": "PENDING",
            "brierScore": None,  # filled automatically on resolution, kept forever
        }, indent=2))
    print(
        "\nHONEST NOTE: this baseline is unproven. The number alone is worth "
        "nothing. Only the never-deleted scored history makes it a moat."
    )


if __name__ == "__main__":
    main()
