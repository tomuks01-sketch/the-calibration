"""Traditional-market index context (DESCRIPTIVE only) — keyless, server-side.

A small "what the broad market did today" strip shown next to the crypto macro
block. NOT a signal, NOT a forecast, NOT advice. Per SIGNAL_SPEC §1 this is the
*descriptive* class: it describes observable data and never enters any
probability — so there is deliberately no ledger and no scoring here.

Source: Yahoo Finance chart endpoint (keyless, but UNOFFICIAL). Fully fail-open:
if it breaks or is unreachable the strip simply hides — nothing is invented. The
data is delayed and is labelled as such in the UI. HTTP is injectable so tests
never touch the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
REQUEST_TIMEOUT_S = 6

# Broad, widely-recognised indices only. (symbol, display name).
INDICES = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq"),
    ("^DJI", "Dow"),
    ("^FTSE", "FTSE 100"),
]


def _default_get(url: str):
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0 pmi/0.1"}
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


def index_quote(symbol: str, name: str, get=_default_get) -> dict | None:
    """Latest price + % change vs previous close for one index, or None."""
    data = get(f"{YF_CHART}{symbol.replace('^', '%5E')}?range=1d&interval=1d")
    try:
        meta = data["chart"]["result"][0]["meta"]
    except (TypeError, KeyError, IndexError):
        return None
    price = _f(meta.get("regularMarketPrice"))
    prev = _f(meta.get("chartPreviousClose")) or _f(meta.get("previousClose"))
    if price is None or not prev:
        return None  # cannot compute an honest change -> omit, never invent
    return {
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "changePct": round((price - prev) / prev * 100, 2),
    }


def fetch_indices(get=_default_get) -> dict:
    """Descriptive index context block. Fail-open: any index that can't be
    fetched is simply omitted; all-failed -> available:false (strip hides)."""
    items = [q for q in (index_quote(s, n, get) for s, n in INDICES) if q]
    return {
        "available": bool(items),
        "source": "yahoo-finance (delayed)",
        "class": "descriptive",
        "asOf": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
