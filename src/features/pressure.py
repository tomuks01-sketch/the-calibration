"""Repricing-pressure layer (SIGNAL_SPEC.md §1/§2, L4) — DESCRIPTIVE only.

Answers "is this market moving / unsettled RIGHT NOW", never "which way will it
resolve". It is class ``descriptive`` and must never enter an outcome
probability (the composite does not read it). Pure function of the snapshot we
already build — no new network.

Unit note: a PM ``change24h`` is a probability fraction (0.06 = 6pp); a crypto
coin's ``change24h`` is a percent (7.0 = 7%). Both are normalised to a fraction
before any threshold so one cut-off works for both.
"""

from __future__ import annotations

from assets import Asset, AssetKind

_SUDDEN = 0.05        # |normalised 24h move| at/above this = "sudden"
_EXTREME = 0.05       # crowd within this of 0 or 1 = "priced near-certain"
_NEAR_DAYS = 3        # resolves within this many days = "info event near"
_PRE_RES_DAYS = 7     # within this AND sudden = "unsettled pre-resolution"

_PM_KINDS = (AssetKind.PM_BINARY, AssetKind.PM_MULTI)


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _move_frac(asset: Asset) -> float | None:
    raw = asset.raw if isinstance(asset.raw, dict) else {}
    c24 = _num(raw.get("change24h"))
    if c24 is None:
        return None
    # crypto change is a percent; PM change is already a fraction.
    return c24 / 100.0 if asset.kind is AssetKind.CRYPTO else c24


def pressure_features(asset: Asset) -> dict:
    move = _move_frac(asset)
    if move is None:
        return {"available": False, "class": "descriptive", "source": "snapshot-derived"}
    is_pm = asset.kind in _PM_KINDS
    lead = asset.crowd_prob
    horizon = asset.horizon_days
    sudden = abs(move) >= _SUDDEN
    overheated = bool(
        is_pm and lead is not None and (lead >= 1 - _EXTREME or lead <= _EXTREME)
    )
    near = bool(is_pm and horizon is not None and horizon <= _NEAR_DAYS)
    pre_res_vol = bool(
        is_pm and horizon is not None and horizon <= _PRE_RES_DAYS and sudden
    )
    return {
        "available": True,
        "class": "descriptive",
        "source": "snapshot-derived",
        "suddenMove": sudden,
        "move24hPp": round(move * 100, 1),
        "overheated": overheated,
        "infoEventNear": near,
        "preResolutionVol": pre_res_vol,
    }
