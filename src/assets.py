"""Shared asset spine for the calibrated signal system (SIGNAL_SPEC.md §2).

Both prediction-market events and crypto coins are normalised into one
``Asset`` so every downstream layer (crowd / baseline / regime / repricing /
composite) consumes a single shape and never raw API dicts.

Note (per spec): Polymarket has NO "open interest" — it is a binary CLOB of
fully-collateralised shares. We carry ``volume`` and ``liquidity`` only;
nothing is relabelled as OI anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AssetKind(str, Enum):
    PM_BINARY = "PM_BINARY"   # binary prediction market (has a falsifiable YES/NO)
    PM_MULTI = "PM_MULTI"     # multi-outcome event (no single binary outcome)
    CRYPTO = "CRYPTO"         # crypto coin (no terminal binary outcome -> not ledgered)


@dataclass(frozen=True)
class Asset:
    asset_id: str             # PM: lead conditionId (binary) or event id (multi); crypto: symbol
    kind: AssetKind
    title: str
    category: str
    crowd_prob: float | None  # 0..1 implied outcome prob; None for crypto (no outcome)
    horizon_days: float | None
    volume: float | None
    liquidity: float | None
    raw: dict = field(default_factory=dict, compare=False, repr=False)


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def from_event(e: dict) -> Asset:
    """Normalise a generate_snapshot event dict into an Asset."""
    binary = bool(e.get("binary"))
    kind = AssetKind.PM_BINARY if binary else AssetKind.PM_MULTI
    outcomes = e.get("outcomes") or []
    first = outcomes[0] if outcomes and isinstance(outcomes[0], dict) else {}
    lead_cond = first.get("conditionId")
    # Binary markets are tracked in the ledger by conditionId, so anchor the
    # asset_id there for matching; multi events have no single market. A binary
    # event missing its conditionId gets a visible UNKNOWN_COND sentinel (never
    # silently borrows an event id, which would cause a hidden ledger mismatch).
    if binary:
        asset_id = lead_cond if lead_cond else f"UNKNOWN_COND:{e.get('id')}"
    else:
        asset_id = str(e.get("id") or "")
    return Asset(
        asset_id=asset_id,
        kind=kind,
        title=str(e.get("title") or ""),
        category=str(e.get("category") or ""),
        crowd_prob=_num(e.get("leadPrice")),
        horizon_days=_num(e.get("daysToResolution")),
        volume=_num(e.get("volume")),
        liquidity=_num(e.get("liquidity")),
        raw=e,
    )


def from_coin(c: dict) -> Asset:
    """Normalise a CoinGecko top-coin dict into an Asset.

    Crypto carries NO outcome probability (there is nothing binary to resolve);
    any directional read is descriptive-only and handled in the regime layer.
    """
    sym = str(c.get("symbol") or "").lower()
    return Asset(
        asset_id=sym,
        kind=AssetKind.CRYPTO,
        title=str(c.get("name") or c.get("symbol") or ""),
        category="crypto",
        crowd_prob=None,
        horizon_days=None,
        volume=_num(c.get("volume")),
        liquidity=None,
        raw=c,
    )
