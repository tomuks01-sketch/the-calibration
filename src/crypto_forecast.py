"""Crypto 24h forecast layer (SIGNAL_SPEC.md §9, cfx-v1) — falsifiable + scored.

An HONEST, transparent ~24h read for liquid coins, in the only two forms the
spec permits. A raw point "% change" headline is FORBIDDEN: it is provably
worse than a random-walk baseline (MAE) and reads as advice.

  - ``prob_up``: probability the coin closes higher in ~24h. Deliberately
    HUMBLE — a small, damped momentum tilt clamped tight around 0.5. We expect
    ~coin-flip skill and the public scoreboard will say so. Scored by Brier
    vs 0.5.
  - ``band_pct``: an 80% magnitude band (±%) from realised daily volatility.
    A VOLATILITY forecast (genuinely forecastable), scored by empirical
    coverage (does the 80% band cover ~80%?) — NOT a direction claim.

Baseline to beat: random walk (prob_up=0.5, expected change=0). Data: Binance
USDⓈ-M daily klines (keyless, public). HTTP is injectable so tests never touch
the network. NEVER a point % headline; NEVER an edge/advice claim.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass

from features.crypto_regime import BINANCE_FAPI, perp_symbol

FORECAST_VERSION = "cfx-v1"
HORIZON_HOURS = 24
VOL_WINDOW = 30          # daily returns used for realised vol + drift
MOMENTUM_WINDOW = 7      # recent daily returns for the humble drift tilt
Z80 = 1.2816            # +/- z for an 80% central interval of a normal
PROB_TILT_K = 0.3       # small: keeps prob_up near 0.5 (honest ~coin-flip)
PROB_CLAMP = 0.10       # prob_up stays within [0.40, 0.60] worst case
MIN_CLOSES = 10         # need enough history or available:false
REQUEST_TIMEOUT_S = 6


@dataclass(frozen=True)
class CryptoForecast:
    symbol: str
    available: bool
    prob_up: float | None        # 0..1 — P(close higher in ~24h)
    sigma_pct: float | None      # realised daily vol, % (the uncertainty)
    band_pct: float | None       # +/- % 80% central band (= Z80 * sigma)
    n_closes: int                # daily closes used
    source: str
    baseline: str                # what the scoreboard scores us against


def _default_get(url: str):
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "pmi/0.1"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def klines_closes(symbol: str, get=_default_get, limit: int = VOL_WINDOW + 1) -> list[float]:
    """Daily close prices (oldest -> newest) from Binance USDⓈ-M klines, or []."""
    data = get(f"{BINANCE_FAPI}/fapi/v1/klines?symbol={symbol}&interval=1d&limit={limit}")
    if not isinstance(data, list):
        return []
    closes: list[float] = []
    for row in data:
        # Binance kline row: [openTime, open, high, low, close, volume, ...]
        if isinstance(row, (list, tuple)) and len(row) > 4:
            c = _f(row[4])
            if c is not None and c > 0:
                closes.append(c)
    return closes


def _daily_returns(closes: list[float]) -> list[float]:
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1]
    ]


def _stdev(xs: list[float]) -> float | None:
    """Sample standard deviation (N-1). Sample (not population) is the right
    convention for realised volatility from a finite sample of returns, so the
    80% band is not systematically too narrow."""
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def realized_vol_pct(closes: list[float]) -> float | None:
    """Realised daily volatility as a percent. None if flat / too short
    (a flat history is honestly undefined, never reported as 0% certainty)."""
    sd = _stdev(_daily_returns(closes))
    return round(sd * 100.0, 4) if sd is not None and sd > 0 else None


def prob_up(closes: list[float]) -> float | None:
    """HUMBLE probability of an up day: a small, damped momentum tilt around
    0.5, clamped tight so we never claim more skill than ~a coin flip."""
    rets = _daily_returns(closes)
    sd = _stdev(rets)
    if sd is None or sd <= 0 or len(rets) < MOMENTUM_WINDOW:
        return None
    drift = sum(rets[-MOMENTUM_WINDOW:]) / MOMENTUM_WINDOW
    tilt = math.tanh(PROB_TILT_K * (drift / sd))            # ~[-1, 1], small
    p = 0.5 + PROB_CLAMP * tilt
    return round(_clamp(p, 0.5 - PROB_CLAMP, 0.5 + PROB_CLAMP), 4)


def forecast(coin_symbol: str | None, get=_default_get) -> CryptoForecast:
    """Build the 24h forecast for one coin. Fail-open: unsupported coin, thin
    history, or any fetch failure -> available:false with nulls (never faked)."""
    sym = perp_symbol(coin_symbol)
    base = CryptoForecast(
        symbol=(coin_symbol or "").lower(), available=False, prob_up=None,
        sigma_pct=None, band_pct=None, n_closes=0,
        source="binance-fapi-klines", baseline="random_walk",
    )
    if not sym:
        return base
    closes = klines_closes(sym, get)
    if len(closes) < MIN_CLOSES:
        return base
    sigma = realized_vol_pct(closes)
    if sigma is None:
        return base
    return CryptoForecast(
        symbol=(coin_symbol or "").lower(), available=True,
        prob_up=prob_up(closes), sigma_pct=sigma,
        band_pct=round(Z80 * sigma, 4), n_closes=len(closes),
        source="binance-fapi-klines", baseline="random_walk",
    )
