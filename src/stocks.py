"""Top large-cap stocks — DESCRIPTIVE analytics (keyless, server-side).

The equities companion to Crypto Pulse: price + 24h/7d/30d change + volume + a
DESCRIPTIVE momentum signal. NOT a forecast, NOT advice, NO scored probability
(SIGNAL_SPEC §1 descriptive class). A *scored* stock forecast is deliberately
not built — equities are efficient and the keyless data is fragile.

Data: Yahoo Finance chart endpoint (keyless, UNOFFICIAL, no CORS → must run
server-side in the cron). Fully fail-open: any symbol that can't be fetched is
omitted; the data is delayed and labelled as such. HTTP injectable for tests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
REQUEST_TIMEOUT_S = 6

# Curated major US large-caps (recognisable, stable set). Labelled "major
# large-caps" in the UI — NOT a precise live top-10-by-market-cap ranking, since
# we deliberately don't fetch market cap (no reliable keyless field).
STOCKS = [
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "Nvidia"),
    ("GOOGL", "Alphabet"), ("AMZN", "Amazon"), ("META", "Meta"),
    ("AVGO", "Broadcom"), ("TSLA", "Tesla"), ("JPM", "JPMorgan"),
    ("LLY", "Eli Lilly"),
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


def _pct(a: float, b: float) -> float | None:
    return round((a - b) / b * 100, 2) if b else None


def signal(c24, c7, c30) -> dict:
    """Descriptive momentum label = agreement of the 24h / 7d / 30d directions.
    Never a forecast — it only describes whether the timeframes point the same way."""
    signs = [1 if x > 0 else -1 if x < 0 else 0 for x in (c24, c7, c30) if x is not None]
    if not signs:
        return {"label": "no data", "dir": "flat", "why": "insufficient history"}
    if all(s > 0 for s in signs):
        return {"label": "rising", "dir": "up", "why": "24h / 7d / 30d all higher"}
    if all(s < 0 for s in signs):
        return {"label": "falling", "dir": "down", "why": "24h / 7d / 30d all lower"}
    return {"label": "mixed", "dir": "flat", "why": "timeframes disagree"}


def stock_quote(symbol: str, name: str, get=_default_get) -> dict | None:
    data = get(f"{YF_CHART}{symbol}?range=3mo&interval=1d")
    try:
        res = data["chart"]["result"][0]
        meta = res["meta"]
        quote = res["indicators"]["quote"][0]
    except (TypeError, KeyError, IndexError):
        return None
    closes = [c for c in (quote.get("close") or []) if isinstance(c, (int, float))]
    vols = [v for v in (quote.get("volume") or []) if isinstance(v, (int, float))]
    if len(closes) < 2:
        return None  # need at least a previous close for a 24h change
    last = closes[-1]
    price = _f(meta.get("regularMarketPrice")) or last
    c24 = _pct(last, closes[-2])
    c7 = _pct(last, closes[-6]) if len(closes) >= 6 else None
    c30 = _pct(last, closes[-23]) if len(closes) >= 23 else None
    return {
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "c24": c24,
        "c7": c7,
        "c30": c30,
        "volume": int(vols[-1]) if vols else None,
        "spark": [round(c, 2) for c in closes[-30:]],
        "signal": signal(c24, c7, c30),
    }


def fetch_stocks(get=_default_get) -> dict:
    """Descriptive large-cap block. Fail-open: failed symbols are omitted;
    all-failed → available:false (the page shows an honest empty state)."""
    items = []
    for i, (sym, name) in enumerate(STOCKS):
        q = stock_quote(sym, name, get)
        if q:
            q["rank"] = i + 1
            items.append(q)
    return {
        "available": bool(items),
        "source": "yahoo-finance (delayed)",
        "class": "descriptive",
        "asOf": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def write_stocks(block: dict, out_path: Path) -> None:
    text = json.dumps(block, indent=2)
    json.loads(text)  # validate before swap
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(out_path)
