"""Read-only CLOB price history → honest 1h / 24h move metrics.

Uses the public CLOB prices-history endpoint. No auth, no wallet. Returns
observable price change only — it explains what already moved, it does not
forecast what will move next.
"""

from __future__ import annotations

import ast
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"
REQUEST_TIMEOUT_S = 20

# A move is "notable" when the YES price shifts at least this much (probability).
MOVE_THRESHOLD_24H = 0.07
MOVE_THRESHOLD_1H = 0.04


@dataclass(frozen=True)
class PriceMove:
    current: float | None
    change_1h: float | None
    change_24h: float | None
    points: int


def parse_token_ids(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                val = parser(raw)
                if isinstance(val, list):
                    return [str(x) for x in val]
            except (ValueError, SyntaxError):
                continue
    return []


def _get(url: str) -> dict | list:
    req = urllib.request.Request(
        url, headers={"User-Agent": "polymarket-insight/0.1", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_price_move(token_id: str) -> PriceMove:
    """Hourly points over the last day → derive 1h and 24h deltas."""
    url = f"{CLOB_HISTORY_URL}?market={token_id}&interval=1d&fidelity=60"
    try:
        data = _get(url)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return PriceMove(None, None, None, 0)

    pts = data.get("history") if isinstance(data, dict) else data
    if not isinstance(pts, list) or not pts:
        return PriceMove(None, None, None, 0)

    prices = [float(p["p"]) for p in pts if "p" in p]
    if not prices:
        return PriceMove(None, None, None, 0)

    current = round(prices[-1], 4)
    change_24h = round(prices[-1] - prices[0], 4)
    change_1h = round(prices[-1] - prices[-2], 4) if len(prices) >= 2 else None
    return PriceMove(current, change_1h, change_24h, len(prices))


def move_flags(move: PriceMove) -> list[str]:
    flags: list[str] = []
    if move.change_24h is not None and abs(move.change_24h) >= MOVE_THRESHOLD_24H:
        flags.append("big-move-24h" if move.change_24h > 0 else "big-drop-24h")
    if move.change_1h is not None and abs(move.change_1h) >= MOVE_THRESHOLD_1H:
        flags.append("moving-now")
    return flags
