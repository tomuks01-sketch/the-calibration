"""Transparent BASELINE model — a simple, documented statistical hypothesis.

This is NOT "AI", NOT an "edge", NOT a forecast you should act on. It is a
falsifiable baseline whose only worth is the public, never-deleted scored
record (see ledger.py / scoreboard). If the scoreboard later shows it is no
better than the crowd, that is the honest answer and it stays public.

THE FORMULA (fully disclosed, fixed at MODEL_VERSION):
  Given a binary market's YES price `p` and its leader's 1-week change `w`:
  1. Mean-reversion nudge: a market that moved sharply recently is assumed to
     partially over/undershoot, so fade part of that move:
        m1 = p - REVERSION * w
  2. Confidence shrink: thin markets are noisier, so pull slightly toward 0.5
     by an amount that shrinks as liquidity rises:
        s  = clamp(SHRINK_MAX * (1 - liquidity / LIQ_FULL), 0, SHRINK_MAX)
        m2 = m1 * (1 - s) + 0.5 * s
  3. Clamp to [0.02, 0.98].
A "call" is logged only when |model - market| >= CALL_THRESHOLD AND the market
is eligible (not near-certain, liquid enough, sane horizon, has a conditionId).
"""

from __future__ import annotations

from dataclasses import dataclass

MODEL_VERSION = "baseline-v1"

REVERSION = 0.35          # fraction of the 1w move faded out (fixed @ v1)
SHRINK_MAX = 0.10         # max pull toward 0.5 for very thin markets
LIQ_FULL = 50_000.0       # liquidity at/above which no shrink is applied
CALL_THRESHOLD = 0.04     # |model - market| >= 4pp to log a tracked call

# Eligibility guards (the demo exposed junk calls on extreme/near-resolved mkts)
MIN_PRICE = 0.05
MAX_PRICE = 0.95
MIN_LIQUIDITY = 5_000.0
MIN_DAYS = 2.0
MAX_DAYS = 365.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class ModelCall:
    eligible: bool
    model_prob: float | None
    market_prob: float | None
    divergence: float | None  # model - market
    is_call: bool             # eligible and |divergence| >= CALL_THRESHOLD
    reason: str               # why ineligible (for transparency/logging)


def evaluate(
    market_prob: float | None,
    week_change: float | None,
    liquidity: float | None,
    days_to_resolution: float | None,
    condition_id: str | None,
) -> ModelCall:
    if market_prob is None:
        return ModelCall(False, None, None, None, False, "no-price")
    if not condition_id:
        return ModelCall(False, None, market_prob, None, False, "no-conditionId")
    if not (MIN_PRICE <= market_prob <= MAX_PRICE):
        return ModelCall(False, None, market_prob, None, False, "near-certain")
    liq = liquidity or 0.0
    if liq < MIN_LIQUIDITY:
        return ModelCall(False, None, market_prob, None, False, "thin-liquidity")
    if days_to_resolution is None or not (
        MIN_DAYS <= days_to_resolution <= MAX_DAYS
    ):
        return ModelCall(False, None, market_prob, None, False, "bad-horizon")

    w = week_change or 0.0
    m1 = market_prob - REVERSION * w
    s = _clamp(SHRINK_MAX * (1.0 - liq / LIQ_FULL), 0.0, SHRINK_MAX)
    m2 = m1 * (1.0 - s) + 0.5 * s
    model_prob = round(_clamp(m2, 0.02, 0.98), 4)
    divergence = round(model_prob - market_prob, 4)
    is_call = abs(divergence) >= CALL_THRESHOLD
    return ModelCall(True, model_prob, market_prob, divergence, is_call, "ok")
