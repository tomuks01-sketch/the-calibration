"""cl-v1 crypto-ledger tests (zero-dep, run: python tests/test_crypto_ledger.py).

SIGNAL_SPEC.md §9: forecasts are LOCKED at open (one per coin per UTC day),
auto-resolved only when now >= dueAt (no look-ahead), scored vs random walk
(brierUp, bandCovered). No price at maturity -> stays OPEN; past stale -> VOID.
Append-only; time is injected so tests are deterministic and never wait 24h.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from crypto_forecast import CryptoForecast  # noqa: E402
from crypto_ledger import open_forecasts, resolve_due  # noqa: E402

T0 = "2026-06-01T00:00:00+00:00"        # open time
DUE = "2026-06-02T00:00:00+00:00"       # T0 + 24h
MATURE = "2026-06-02T00:30:00+00:00"    # just past due
EARLY = "2026-06-01T12:00:00+00:00"     # before due


def _fc(symbol, available=True, prob_up=0.55, sigma=2.0, band=2.5632):
    return CryptoForecast(symbol=symbol, available=available, prob_up=prob_up,
                          sigma_pct=sigma, band_pct=band, n_closes=31,
                          source="binance-fapi-klines", baseline="random_walk")


def _ledger():
    return {"entries": []}


def test_open_locks_available_with_price_only():
    cl = _ledger()
    fcs = [_fc("btc"), _fc("eth", available=False), _fc("sol")]
    opened = open_forecasts(cl, fcs, {"btc": 100.0, "sol": 0.0}, now=T0)
    # eth unavailable (skipped); sol price 0 (skipped); only btc locks
    assert opened == 1
    e = cl["entries"][0]
    assert e["symbol"] == "btc" and e["status"] == "OPEN"
    assert e["priceAtOpen"] == 100.0 and e["dueAt"] == DUE
    assert e["baseline"] == "random_walk" and e["resolvedAt"] is None


def test_open_dedup_one_per_coin_per_day():
    cl = _ledger()
    open_forecasts(cl, [_fc("btc")], {"btc": 100.0}, now=T0)
    again = open_forecasts(cl, [_fc("btc")], {"btc": 101.0}, now=T0)  # same UTC day
    assert again == 0 and len(cl["entries"]) == 1


def test_resolve_not_mature_stays_open():
    cl = _ledger()
    open_forecasts(cl, [_fc("btc")], {"btc": 100.0}, now=T0)
    r, v = resolve_due(cl, {"btc": 105.0}, now=EARLY)   # before dueAt
    assert (r, v) == (0, 0)
    assert cl["entries"][0]["status"] == "OPEN"


def test_resolve_scores_vs_random_walk():
    cl = _ledger()
    open_forecasts(cl, [_fc("btc", prob_up=0.55, band=2.5632)], {"btc": 100.0}, now=T0)
    r, v = resolve_due(cl, {"btc": 102.0}, now=MATURE)   # +2% over 24h
    assert (r, v) == (1, 0)
    e = cl["entries"][0]
    assert e["status"] == "RESOLVED" and e["priceAtResolve"] == 102.0
    assert abs(e["realizedChangePct"] - 2.0) < 1e-9
    assert e["upHit"] == 1
    assert abs(e["brierUp"] - (0.55 - 1) ** 2) < 1e-6     # scored vs the outcome
    assert e["bandCovered"] is True                       # |+2%| <= 2.5632 band


def test_band_not_covered_on_big_move():
    cl = _ledger()
    open_forecasts(cl, [_fc("btc", band=2.5632)], {"btc": 100.0}, now=T0)
    resolve_due(cl, {"btc": 110.0}, now=MATURE)           # +10% blows the band
    e = cl["entries"][0]
    assert e["bandCovered"] is False and e["upHit"] == 1


def test_resolve_missing_price_stays_open_then_voids_when_stale():
    cl = _ledger()
    open_forecasts(cl, [_fc("btc")], {"btc": 100.0}, now=T0)
    # mature but no price for btc -> still within stale window -> stays OPEN
    r, v = resolve_due(cl, {}, now=MATURE)
    assert (r, v) == (0, 0) and cl["entries"][0]["status"] == "OPEN"
    # far in the future with still no price -> VOID (cannot rot forever)
    r, v = resolve_due(cl, {}, now="2026-06-10T00:00:00+00:00")
    assert (r, v) == (0, 1) and cl["entries"][0]["status"] == "VOID"


if __name__ == "__main__":
    test_open_locks_available_with_price_only()
    test_open_dedup_one_per_coin_per_day()
    test_resolve_not_mature_stays_open()
    test_resolve_scores_vs_random_walk()
    test_band_not_covered_on_big_move()
    test_resolve_missing_price_stays_open_then_voids_when_stale()
    print("ALL cl-v1 CRYPTO-LEDGER TESTS PASSED")
