"""Kalshi — a SECOND venue, shown SEPARATELY (never auto-paired/compared).

Read-only, keyless public API. Honesty rules (enforced in code):
- Kalshi contracts are NOT the same as Polymarket contracts (different
  wording, thresholds, resolution sources/dates). We therefore display Kalshi
  on its own, clearly labelled "separate venue, separate contracts" — we do
  NOT compute a cross-venue divergence here. True cross-venue comparison is
  gated to a hand-vetted allowlist (web/crossvenue_allowlist.json) and is
  intentionally empty until a pair is human-verified as materially identical.
- Implied probability = last traded price only; null/zero/out-of-range
  rejected (a data gap must never render as "0%"). Fail-open + stderr warn.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets"
REQUEST_TIMEOUT_S = 20

# Curated macro series only (liquid, single-threshold binaries). We pick the
# single highest-volume open market per series as a representative read.
SERIES = ("KXFED", "KXFEDDECISION", "KXU3", "KXCPIYOY")


@dataclass(frozen=True)
class KalshiRead:
    series: str
    ticker: str
    title: str
    implied: float          # last trade price in [0.01, 0.99]
    close_date: str


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "the-calibration/1.0"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _implied(market: dict) -> float | None:
    raw = market.get("last_price_dollars")
    try:
        p = float(raw)
    except (TypeError, ValueError):
        return None
    # Reject gaps/extremes: never let a 0.0 "no trades" render as 0%.
    return p if 0.01 <= p <= 0.99 else None


def fetch_kalshi_macro() -> list[dict]:
    """One representative read per curated series. Fail-open to []."""
    out: list[dict] = []
    for s in SERIES:
        try:
            d = _get(f"{KALSHI}?series_ticker={s}&status=open&limit=100")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            print(f"WARN kalshi: {s} fetch failed ({getattr(exc,'code','net')})",
                  file=sys.stderr)
            continue
        markets = d.get("markets") or []
        priced = []
        for m in markets:
            ip = _implied(m)
            if ip is None:
                continue
            try:
                vol = float(m.get("volume_fp") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            priced.append((vol, ip, m))
        if not priced:
            continue
        priced.sort(key=lambda x: x[0], reverse=True)
        _, ip, m = priced[0]
        out.append(
            {
                "series": s,
                "ticker": str(m.get("ticker") or ""),
                "title": str(m.get("title") or "")[:120],
                "impliedPct": round(ip * 100, 1),
                "closeDate": str(m.get("close_time") or "")[:10],
                "attribution": "Kalshi public API",
            }
        )
    return out
