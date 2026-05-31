"""Crypto regime layer (SIGNAL_SPEC.md §5, L3) — DESCRIPTIVE-first.

Derivatives context for crypto assets from Binance USDⓈ-M futures (keyless,
public REST): funding rate + funding z-score, basis (mark vs index), open
interest delta. Split into two explicit parts:

  - ``descriptive``: shown as context only — it does NOT move any probability.
  - ``adjustmentCandidate``: a proposed tilt computed for evaluation, but
    ``applied: false`` and weighted 0.0 in v1. Elevated funding/OI/basis does
    not, by itself, justify moving an outcome probability.

Liquidations are out of scope (no faithful keyless source) and never invented.
HTTP is injectable so the cron uses the real fetcher and tests use a fake.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request

BINANCE_FAPI = "https://fapi.binance.com"
REQUEST_TIMEOUT_S = 6        # short: worst case ~3 calls/coin must stay well inside the cron slot
REGIME_BUDGET_S = 90        # hard wall-clock cap for the whole regime sweep
FUNDING_WINDOW = 30
_SCALE_FUNDING_Z = 2.0

# Coins with liquid USDⓈ-M perps. Conservative allowlist — anything else gets
# no regime (available:false) rather than a guessed symbol that 404s.
PERP_COINS = {
    "btc", "eth", "bnb", "sol", "xrp", "doge", "ada", "avax", "link", "dot",
    "trx", "ltc", "bch", "matic", "near", "atom", "uni", "apt", "arb", "op",
}


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


def _zscore(values, current) -> float | None:
    xs = [x for x in values if isinstance(x, (int, float))]
    if len(xs) < 5 or current is None:
        return None
    mean = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    if sd <= 0:
        return None  # flat history -> z-score undefined (NOT "neutral"; honest null)
    return round((current - mean) / sd, 2)


def perp_symbol(coin_symbol: str | None) -> str | None:
    s = (coin_symbol or "").lower()
    return f"{s.upper()}USDT" if s in PERP_COINS else None


def regime_for(coin_symbol: str | None, get=_default_get) -> dict:
    sym = perp_symbol(coin_symbol)
    if not sym:
        return {"available": False, "source": "binance-fapi", "timestamp": None}

    funding = basis = None
    pi = get(f"{BINANCE_FAPI}/fapi/v1/premiumIndex?symbol={sym}")
    if isinstance(pi, dict):
        funding = _f(pi.get("lastFundingRate"))
        mark, idx = _f(pi.get("markPrice")), _f(pi.get("indexPrice"))
        if mark is not None and idx:
            basis = round((mark - idx) / idx, 6)

    funding_z = None
    fh = get(f"{BINANCE_FAPI}/fapi/v1/fundingRate?symbol={sym}&limit={FUNDING_WINDOW}")
    if isinstance(fh, list) and fh:
        rates = [_f(x.get("fundingRate")) for x in fh if isinstance(x, dict)]
        cur = funding if funding is not None else (rates[-1] if rates else None)
        funding_z = _zscore(rates, cur)

    oi = oi_delta = None
    oih = get(f"{BINANCE_FAPI}/futures/data/openInterestHist?symbol={sym}&period=1d&limit=8")
    if isinstance(oih, list) and len(oih) >= 2:
        ois = [_f(x.get("sumOpenInterest")) for x in oih if isinstance(x, dict)]
        ois = [o for o in ois if o is not None]
        if len(ois) >= 2 and ois[-2]:
            oi, oi_delta = ois[-1], round((ois[-1] - ois[-2]) / ois[-2], 4)

    available = any(v is not None for v in (funding, oi, basis))
    return {
        "available": available,
        "source": "binance-fapi",
        "fundingRate": funding,
        "fundingZ": funding_z,
        "basis": basis,
        "basisZ": None,        # no cheap keyless basis history -> honest null
        "oi": oi,
        "oiDelta": oi_delta,
    }


def candidate_tilt(descriptive: dict) -> dict:
    """An INERT probability-adjustment candidate (applied:false). Documented
    hypothesis only: crowded longs (high +funding z) lean mildly mean-reverting.
    Contributes nothing to any probability in v1."""
    fz = descriptive.get("fundingZ") if isinstance(descriptive, dict) else None
    if fz is None:
        return {"tilt": None, "applied": False}
    return {"tilt": round(-math.tanh(fz / _SCALE_FUNDING_Z), 4), "applied": False}


def enrich_regime(
    records: list[dict], get=_default_get, max_coins: int = 12,
    budget_s: float = REGIME_BUDGET_S,
) -> list[dict]:
    """Fill regime.descriptive + adjustmentCandidate for CRYPTO records only.
    Fail-open: a fetch error leaves available:false; PM records are untouched.
    Wall-clock budgeted so a slow Binance can never overrun the cron slot."""
    deadline = time.monotonic() + budget_s
    done = 0
    for rec in records:
        if rec.get("kind") != "CRYPTO":
            continue
        if done >= max_coins or time.monotonic() > deadline:
            break
        try:
            desc = regime_for(rec.get("assetId"), get)
        except Exception:  # noqa: BLE001 — fail-open by design
            desc = {"available": False, "source": "binance-fapi", "timestamp": None}
        rec.setdefault("regime", {})
        rec["regime"]["descriptive"] = desc
        rec["regime"]["adjustmentCandidate"] = candidate_tilt(desc)
        done += 1
    return records
