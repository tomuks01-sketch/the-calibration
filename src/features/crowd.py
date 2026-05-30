"""Crowd layer (SIGNAL_SPEC.md L1) — probabilistic.

The crowd's own implied outcome probability plus market-microstructure
context. In P1 only the probability is sourced (from the snapshot we already
build); spread / order-book imbalance / trade velocity / volume change require
a CLOB book + trade feed and are NOT fetched yet, so they are honest nulls
with ``available`` reflecting only what we actually have. They will be
admitted later under the §3 rule (coverage + source + timestamp + tests).
"""

from __future__ import annotations

from assets import Asset


def crowd_features(asset: Asset) -> dict:
    prob = asset.crowd_prob
    return {
        "prob": prob,                 # 0..1 implied outcome probability (None for crypto)
        "spread": None,               # not fetched in P1 (needs CLOB /book)
        "obImbalance": None,          # not fetched in P1
        "tradeVelocity": None,        # not fetched in P1 (needs /trades)
        "volumeChange": None,         # not fetched in P1 (needs prior snapshot)
        "source": "gamma-midpoint-proxy",
        "available": prob is not None,
    }
