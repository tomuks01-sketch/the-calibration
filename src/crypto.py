"""Read-only crypto MACRO CONTEXT (CoinGecko public API, no key).

This is deliberately a *subordinate context layer*, not a crypto feed. It
exists only to let prediction-market briefs add an honest, gated cross-signal
when (and only when) a crypto- or macro-rate-related market is in play.

Never predictive. Never causal. Degrades silently but flags availability.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

COINGECKO_SIMPLE_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd"
    "&include_24hr_change=true&include_market_cap=true"
)
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
REQUEST_TIMEOUT_S = 20


@dataclass(frozen=True)
class MacroContext:
    available: bool
    regime: str  # "risk-on" | "risk-off" | "neutral" | "unknown"
    btc_usd: float | None = None
    eth_usd: float | None = None
    btc_change_24h: float | None = None
    eth_change_24h: float | None = None
    total_mcap_usd: float | None = None
    total_mcap_change_24h: float | None = None
    btc_dominance: float | None = None


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "polymarket-insight/0.1"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _f(v: object) -> float | None:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def classify_regime(
    btc_change_24h: float | None, total_mcap_change_24h: float | None
) -> str:
    vals = [v for v in (btc_change_24h, total_mcap_change_24h) if v is not None]
    if not vals:
        return "unknown"
    avg = sum(vals) / len(vals)
    if avg >= 2.0:
        return "risk-on"
    if avg <= -2.0:
        return "risk-off"
    return "neutral"


def fetch_macro() -> MacroContext:
    """Two read-only calls. Any failure degrades to available=False."""
    btc = eth = btc_chg = eth_chg = None
    mcap = mcap_chg = dom = None

    try:
        s = _get(COINGECKO_SIMPLE_URL)
        b, e = s.get("bitcoin", {}), s.get("ethereum", {})
        btc, eth = _f(b.get("usd")), _f(e.get("usd"))
        btc_chg, eth_chg = _f(b.get("usd_24h_change")), _f(e.get("usd_24h_change"))
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        pass

    try:
        g = _get(COINGECKO_GLOBAL_URL).get("data", {})
        mcap = _f(g.get("total_market_cap", {}).get("usd"))
        mcap_chg = _f(g.get("market_cap_change_percentage_24h_usd"))
        dom = _f(g.get("market_cap_percentage", {}).get("btc"))
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        pass

    available = btc is not None or mcap is not None
    return MacroContext(
        available=available,
        regime=classify_regime(btc_chg, mcap_chg) if available else "unknown",
        btc_usd=btc,
        eth_usd=eth,
        btc_change_24h=btc_chg,
        eth_change_24h=eth_chg,
        total_mcap_usd=mcap,
        total_mcap_change_24h=mcap_chg,
        btc_dominance=dom,
    )


# Keywords that make a prediction-market event eligible for a crypto/macro
# cross-signal. Anything else (sports, entertainment, geopolitics) is NOT
# eligible — connecting it to crypto would be spurious pattern-matching.
_MACRO_KEYWORDS = (
    "fed", "fomc", "interest rate", "rate cut", "rate hike", "inflation",
    "cpi", "recession", "bitcoin", "btc", "ethereum", "eth", "crypto",
    "etf", "sec ", "stablecoin",
)
_MACRO_CATEGORIES = {"economic policy", "economy", "crypto", "bitcoin"}


def event_is_macro_eligible(event: dict) -> bool:
    cat = str(event.get("category") or "").lower()
    if cat in _MACRO_CATEGORIES:
        return True
    title = str(event.get("title") or "").lower()
    return any(k in title for k in _MACRO_KEYWORDS)


def build_cross_signals(macro: MacroContext, events: list[dict]) -> list[dict]:
    """Descriptive only. Gated to macro-eligible events. Empty if no basis."""
    if not macro.available:
        return []
    eligible = [e for e in events if event_is_macro_eligible(e)]
    if not eligible:
        return []

    top = max(
        eligible,
        key=lambda e: abs(e.get("change24h") or 0.0)
        if e.get("change24h") is not None
        else 0.0,
    )
    chg = top.get("change24h")
    move_txt = (
        f"repriced ~{abs(chg) * 100:.1f}pp (24h)"
        if isinstance(chg, (int, float)) and chg is not None
        else "was little changed (24h)"
    )
    btc_txt = (
        f"BTC was {macro.btc_change_24h:+.1f}% over the same window"
        if macro.btc_change_24h is not None
        else "BTC change unavailable"
    )
    return [
        {
            "label": "Crowd vs tape (context only)",
            "reading": (
                f"The crowd's '{top.get('title', '')[:70]}' market {move_txt}; "
                f"separately, {btc_txt}. Observed crypto regime label: "
                f"{macro.regime}."
            ),
            "note": (
                "Market context only — two observed moves shown side by side. "
                "No causal relationship implied; not predictive or investment "
                "commentary."
            ),
        }
    ]
