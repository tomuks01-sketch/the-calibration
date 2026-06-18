"""Append-only crypto 24h-forecast ledger + time-boxed auto-scoring (cl-v1).

Crypto has no Polymarket-style terminal `endDate`, so the resolution boundary
is MANUFACTURED honestly (SIGNAL_SPEC.md §9):

- A forecast is LOCKED at open: priceAtOpen (+ time), dueAt = openedAt + 24h,
  probUp, sigmaPct, bandPct, baseline=random_walk. Written before the window.
- At most ONE forecast per (symbol, UTC day) — dedup key sha1(symbol:utcdate).
- Auto-resolved only when `now >= dueAt` (so we can never peek at a future
  price — no look-ahead). Scored vs the random-walk baseline:
    upHit       = realizedChange > 0
    brierUp     = (probUp - upHit)^2          (baseline brier = 0.25, in scoreboard)
    bandCovered = |realizedChangePct| <= bandPct   (did the 80% band hold?)
- No price available at maturity -> stays OPEN (retried); past STALE -> VOID.
- Append-only; OPEN -> RESOLVED|VOID only; never deleted. Atomic write +
  validation + monthly archive, mirroring the PM ledger's integrity rules.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_forecast import FORECAST_VERSION, CryptoForecast

CRYPTO_LEDGER = Path(__file__).resolve().parent.parent / "web" / "crypto_ledger.json"
ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "web" / "crypto-ledger-archive"
SCHEMA_VERSION = "cl-v1"
BASELINE = "random_walk"
HORIZON_S = 24 * 3600
STALE_VOID_S = 72 * 3600  # OPEN this long past open with no resolve price -> VOID

DISCLAIMER = (
    "Crypto 24h forecasts, scored vs a random-walk baseline (probUp vs 0.5, "
    "magnitude band vs realised vol). Analytics only — not betting advice. "
    "Append-only: forecasts are locked at open and never edited."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _utcdate(iso: str) -> str:
    return iso[:10]


def load_crypto_ledger() -> dict:
    if not CRYPTO_LEDGER.exists():
        return {"schemaVersion": SCHEMA_VERSION, "forecastVersion": FORECAST_VERSION,
                "baseline": BASELINE, "disclaimer": DISCLAIMER, "entries": []}
    try:
        data = json.loads(CRYPTO_LEDGER.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "entries" not in data:
            raise ValueError("bad crypto-ledger shape")
        return data
    except (ValueError, OSError) as exc:
        # Corrupt ledger: raise a normal Exception (NOT SystemExit/BaseException)
        # so the fail-open wrapper in generate_snapshot catches it, WARNs, and
        # skips the crypto block WITHOUT overwriting the corrupt file (history
        # preserved for inspection) and WITHOUT killing the core snapshot run.
        raise RuntimeError(
            "web/crypto_ledger.json is unreadable/corrupt; skipping crypto "
            "forecast this run (file left intact for inspection)."
        ) from exc


def save_crypto_ledger(cl: dict) -> None:
    cl["schemaVersion"] = SCHEMA_VERSION
    cl["forecastVersion"] = FORECAST_VERSION
    cl["baseline"] = BASELINE
    cl["disclaimer"] = DISCLAIMER
    text = json.dumps(cl, indent=2)
    json.loads(text)  # validate before any write
    CRYPTO_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = CRYPTO_LEDGER.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(CRYPTO_LEDGER)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ARCHIVE_DIR / f"{_now()[:7]}.json").write_text(text, encoding="utf-8")


def _existing_ids(cl: dict) -> set[str]:
    return {e["forecastId"] for e in cl["entries"] if e.get("forecastId")}


def open_forecasts(
    cl: dict, forecasts: list[CryptoForecast], spot_prices: dict[str, float],
    now: str | None = None,
) -> int:
    """Open at most one forecast per (symbol, UTC day). Requires an available
    forecast AND a real spot price to lock in. Returns count opened."""
    now = now or _now()
    due = (_parse(now) + timedelta(seconds=HORIZON_S)).isoformat()
    seen = _existing_ids(cl)
    opened = 0
    for f in forecasts:
        if not getattr(f, "available", False):
            continue
        price = spot_prices.get(f.symbol)
        if price is None or price <= 0:
            continue  # cannot lock a forecast without a real open price
        fid = hashlib.sha1(f"{f.symbol}:{_utcdate(now)}".encode()).hexdigest()[:16]
        if fid in seen:
            continue  # one forecast per coin per day
        cl["entries"].append({
            "forecastId": fid,
            "symbol": f.symbol,
            "openedAt": now,
            "dueAt": due,
            "priceAtOpen": float(price),
            "probUp": f.prob_up,
            "sigmaPct": f.sigma_pct,
            "bandPct": f.band_pct,
            "bandPctEwma": getattr(f, "band_pct_ewma", None),
            "baseline": BASELINE,
            "status": "OPEN",
            "resolvedAt": None,
            "priceAtResolve": None,
            "realizedChangePct": None,
            "upHit": None,
            "brierUp": None,
            "bandCovered": None,
            "voidReason": None,
        })
        seen.add(fid)
        opened += 1
    return opened


def resolve_due(
    cl: dict, spot_now: dict[str, float], now: str | None = None,
) -> tuple[int, int]:
    """Resolve every OPEN forecast whose dueAt has passed (now >= dueAt), using
    the price 'now' (>= dueAt, so never a future peek). Missing price -> stays
    OPEN; older than STALE_VOID_S -> VOID. Returns (resolved, voided)."""
    now = now or _now()
    now_dt = _parse(now)
    resolved = voided = 0
    for e in cl["entries"]:
        if e.get("status") != "OPEN":
            continue
        if now_dt < _parse(e["dueAt"]):
            continue  # not mature yet
        price = spot_now.get(e["symbol"])
        open_price = e.get("priceAtOpen")
        if price is None or price <= 0 or open_price is None or open_price <= 0:
            if (now_dt - _parse(e["openedAt"])).total_seconds() >= STALE_VOID_S:
                e.update(status="VOID", voidReason="no resolve price (stale)",
                         resolvedAt=now)
                voided += 1
            continue  # otherwise leave OPEN, retry next run
        realized = (price - open_price) / open_price * 100.0
        up = 1 if realized > 0 else 0
        prob_up = e.get("probUp")
        band = e.get("bandPct")
        e.update(
            status="RESOLVED",
            resolvedAt=now,
            priceAtResolve=float(price),
            realizedChangePct=round(realized, 4),
            upHit=up,
            brierUp=round((prob_up - up) ** 2, 6) if prob_up is not None else None,
            bandCovered=(abs(realized) <= band) if band is not None else None,
        )
        resolved += 1
    return (resolved, voided)
