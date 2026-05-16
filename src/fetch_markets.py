"""Read-only Polymarket data + honest signal computation.

No wallet, no private keys, no order placement. This is an ANALYTICS tool:
it surfaces observable facts (price, volume, liquidity, time-to-resolution)
and simple derived flags. It does NOT predict outcomes or tell you to bet.
"""

from __future__ import annotations

import ast
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
REQUEST_TIMEOUT_S = 20
DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class MarketSignal:
    question: str
    slug: str
    yes_price: float | None
    volume: float
    liquidity: float
    days_to_resolution: float | None
    flags: tuple[str, ...]


def _http_get_json(url: str) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "polymarket-insight/0.1 (analytics; +https://example.com)",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_active_markets(limit: int = DEFAULT_LIMIT) -> list[dict]:
    url = f"{GAMMA_MARKETS_URL}?limit={limit}&active=true&closed=false"
    data = _http_get_json(url)
    return data if isinstance(data, list) else [data]


def _coerce_list(raw: object) -> list:
    """Handle the API returning a list, a JSON string, or a py-literal string."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                val = parser(raw)
                if isinstance(val, list):
                    return val
            except (ValueError, SyntaxError):
                continue
    return []


def _parse_first_price(outcome_prices: object) -> float | None:
    prices = _coerce_list(outcome_prices)
    if prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None
    return None


def summarize_outcomes(market: dict, top: int = 4) -> list[dict]:
    """Outcome name + price pairs, sorted by price desc. Multi-outcome safe."""
    names = [str(n) for n in _coerce_list(market.get("outcomes"))]
    prices: list[float] = []
    for p in _coerce_list(market.get("outcomePrices")):
        try:
            prices.append(float(p))
        except (TypeError, ValueError):
            prices.append(0.0)
    pairs = [
        {"name": names[i] if i < len(names) else f"Outcome {i + 1}",
         "price": prices[i]}
        for i in range(min(len(names), len(prices)))
    ]
    pairs.sort(key=lambda x: x["price"], reverse=True)
    return pairs[:top]


def is_binary(market: dict) -> bool:
    return len(_coerce_list(market.get("outcomes"))) == 2


def _days_until(end_date: str | None) -> float | None:
    if not end_date:
        return None
    try:
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = end - datetime.now(timezone.utc)
    return round(delta.total_seconds() / 86400, 1)


def build_signal(market: dict) -> MarketSignal:
    yes_price = _parse_first_price(market.get("outcomePrices"))
    volume = float(market.get("volume") or 0.0)
    liquidity = float(market.get("liquidity") or 0.0)
    days = _days_until(market.get("endDate"))

    flags: list[str] = []
    if yes_price is not None and (yes_price <= 0.08 or yes_price >= 0.92):
        flags.append("extreme-price")  # market thinks outcome is near-certain
    if liquidity < 1000:
        flags.append("thin-liquidity")  # hard to enter/exit, wide spread
    if days is not None and 0 <= days <= 3:
        flags.append("resolves-soon")
    if volume > 100_000:
        flags.append("high-attention")

    return MarketSignal(
        question=str(market.get("question") or "")[:100],
        slug=str(market.get("slug") or ""),
        yes_price=yes_price,
        volume=volume,
        liquidity=liquidity,
        days_to_resolution=days,
        flags=tuple(flags),
    )


@dataclass(frozen=True)
class EventGroup:
    event_id: str
    title: str
    slug: str
    category: str
    tags: tuple[str, ...]
    volume: float
    volume_24h: float
    liquidity: float
    days_to_resolution: float | None
    market_count: int
    markets: tuple[dict, ...]  # raw market dicts inside this event


def _event_tags(event: dict) -> list[str]:
    out: list[str] = []
    for t in event.get("tags") or []:
        if isinstance(t, dict):
            label = t.get("label") or t.get("slug")
            if label:
                out.append(str(label))
    return out


def fetch_active_events(limit: int = 120) -> list[dict]:
    url = (
        f"{GAMMA_EVENTS_URL}?limit={limit}&active=true&closed=false"
        "&order=volume&ascending=false"
    )
    data = _http_get_json(url)
    return data if isinstance(data, list) else [data]


def build_event_group(event: dict) -> EventGroup | None:
    markets = [m for m in (event.get("markets") or []) if isinstance(m, dict)]
    if not markets:  # skeptiko CRITICAL: skip zero-market events
        return None
    tags = _event_tags(event)
    return EventGroup(
        event_id=str(event.get("id") or ""),
        title=str(event.get("title") or "")[:140],
        slug=str(event.get("slug") or ""),
        category=tags[0] if tags else "Uncategorized",
        tags=tuple(tags),
        volume=float(event.get("volume") or 0.0),
        volume_24h=float(event.get("volume24hr") or 0.0),
        liquidity=float(event.get("liquidity") or 0.0),
        days_to_resolution=_days_until(event.get("endDate")),
        market_count=len(markets),
        markets=tuple(markets),
    )


def main() -> None:
    events = [g for g in (build_event_group(e) for e in fetch_active_events(60)) if g]
    print(f"{len(events)} active events (read-only)\n")
    for g in sorted(events, key=lambda x: x.volume, reverse=True)[:15]:
        print(f"[{g.category:>14}] vol={g.volume:>13,.0f}  "
              f"{g.market_count:>3} mkts  {g.title}")
    print("\nNOTE: observable market state, not predictions or betting advice.")


if __name__ == "__main__":
    main()
