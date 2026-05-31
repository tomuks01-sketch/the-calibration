"""P3 crypto-regime tests (zero-dep, run: python tests/test_crypto_regime.py).

Crypto regime is DESCRIPTIVE-first (SIGNAL_SPEC.md §5): funding / basis / OI
context from Binance USDⓈ-M futures (keyless). The adjustment candidate is
computed but inert (applied:false). HTTP is injected so tests never touch the
network. Missing/failed data -> available:false, never invented.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from features.crypto_regime import (  # noqa: E402
    candidate_tilt, enrich_regime, perp_symbol, regime_for, _zscore,
)


def _fake_get(url):
    if "premiumIndex" in url:
        return {"markPrice": "100.0", "indexPrice": "99.5", "lastFundingRate": "0.0006"}
    if "fundingRate" in url:
        return [{"fundingRate": str(round(0.0001 * i, 6))} for i in range(1, 11)]
    if "openInterestHist" in url:
        return [{"sumOpenInterest": "1000"}, {"sumOpenInterest": "1100"}]
    return None


def test_perp_symbol_known_vs_unknown():
    assert perp_symbol("btc") == "BTCUSDT"
    assert perp_symbol("ETH") == "ETHUSDT"
    assert perp_symbol("usdt") is None        # stable, no directional perp signal
    assert perp_symbol("madeupcoin") is None


def test_regime_for_real_shapes():
    r = regime_for("btc", _fake_get)
    assert r["available"] is True
    assert r["source"] == "binance-fapi"
    assert abs(r["basis"] - (100.0 - 99.5) / 99.5) < 1e-5   # (mark-index)/index, rounded 6dp
    assert abs(r["oiDelta"] - 0.1) < 1e-9                    # (1100-1000)/1000
    assert r["fundingRate"] == 0.0006
    assert isinstance(r["fundingZ"], float)                  # computed from history
    assert r["basisZ"] is None                               # no cheap keyless history -> honest null


def test_regime_for_unsupported_coin_unavailable():
    r = regime_for("usdt", _fake_get)
    assert r["available"] is False


def test_regime_fail_open_on_none():
    r = regime_for("btc", lambda url: None)                  # all calls fail
    assert r["available"] is False                           # nothing invented


def test_candidate_tilt_is_inert():
    c = candidate_tilt({"fundingZ": 3.0})
    assert c["applied"] is False                             # never applied in v1
    assert -1.0 <= c["tilt"] <= 1.0                          # bounded
    assert candidate_tilt({"fundingZ": None})["tilt"] is None


def test_zscore_basics():
    assert _zscore([1, 1, 1, 1, 1], 1) is None               # flat history -> undefined, not "neutral"
    assert _zscore([1, 2], 2) is None                        # too few points
    z = _zscore([0, 1, 2, 3, 4], 4)
    assert isinstance(z, float) and z > 0


def test_enrich_only_touches_crypto_and_fails_open():
    records = [
        {"kind": "PM_BINARY", "regime": {"descriptive": {"available": False},
                                         "adjustmentCandidate": {"tilt": None, "applied": False}}},
        {"kind": "CRYPTO", "assetId": "btc",
         "regime": {"descriptive": {"available": False},
                    "adjustmentCandidate": {"tilt": None, "applied": False}}},
    ]
    enrich_regime(records, _fake_get)
    assert records[0]["regime"]["descriptive"]["available"] is False    # PM untouched
    assert records[1]["regime"]["descriptive"]["available"] is True     # crypto filled
    assert records[1]["regime"]["adjustmentCandidate"]["applied"] is False
    # fail-open: bad getter must not raise
    recs2 = [{"kind": "CRYPTO", "assetId": "btc",
              "regime": {"descriptive": {}, "adjustmentCandidate": {}}}]
    enrich_regime(recs2, lambda url: None)
    assert recs2[0]["regime"]["descriptive"]["available"] is False


if __name__ == "__main__":
    test_perp_symbol_known_vs_unknown()
    test_regime_for_real_shapes()
    test_regime_for_unsupported_coin_unavailable()
    test_regime_fail_open_on_none()
    test_candidate_tilt_is_inert()
    test_zscore_basics()
    test_enrich_only_touches_crypto_and_fails_open()
    print("ALL P3 CRYPTO-REGIME TESTS PASSED")
