"""cfx-v1 crypto 24h forecast tests (zero-dep, run: python tests/test_crypto_forecast.py).

SIGNAL_SPEC.md §9: the forecast is HONEST + falsifiable. prob_up stays clamped
near 0.5 (humble ~coin-flip); band_pct is an 80% volatility band; a flat/short
history is undefined (never faked); unsupported coin or fetch failure ->
available:false. HTTP is injected so tests never touch the network.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from crypto_forecast import (  # noqa: E402
    PROB_CLAMP, Z80, CryptoForecast, forecast, klines_closes, prob_up,
    realized_vol_pct,
)


def _klines(closes):
    """Shape rows like Binance: [openTime, open, high, low, close, volume, ...]."""
    return [[0, "0", "0", "0", str(c), "0", 0, "0", 0, "0", "0", "0"] for c in closes]


def _rising_get(closes):
    return lambda url: _klines(closes) if "klines" in url else None


def _series(start, drift, osc, n):
    """Deterministic price path with a net daily `drift` plus +/- `osc`
    oscillation, so daily RETURNS genuinely vary (non-zero realised vol) —
    a perfectly geometric series has zero return variance and is degenerate."""
    out = [float(start)]
    for i in range(1, n):
        out.append(out[-1] * (1 + drift + (osc if i % 2 else -osc)))
    return out


def test_klines_closes_parses_and_skips_junk():
    rows = _klines([100.0, 101.0]) + [["bad"], {"not": "a row"}, [0, 0, 0, 0, "-5"]]
    closes = klines_closes("BTCUSDT", lambda url: rows)
    assert closes == [100.0, 101.0]            # negative/short/garbage rows dropped


def test_realized_vol_pct_known_series():
    # alternating +/- moves -> non-zero vol; flat -> None
    assert realized_vol_pct([100, 100, 100, 100]) is None        # flat = undefined
    v = realized_vol_pct([100, 102, 100, 102, 100])
    assert isinstance(v, float) and v > 0


def test_prob_up_is_humble_and_clamped():
    rising = _series(100, 0.004, 0.02, 20)      # net up-drift + real oscillation
    falling = _series(100, -0.004, 0.02, 20)    # net down-drift + real oscillation
    pu, pd = prob_up(rising), prob_up(falling)
    assert pu is not None and pd is not None
    assert pu > 0.5 > pd                                  # direction follows momentum
    # never claims more skill than a coin-flip-ish edge
    assert 0.5 - PROB_CLAMP <= pd and pu <= 0.5 + PROB_CLAMP


def test_prob_up_none_when_flat_or_short():
    assert prob_up([100, 100, 100, 100, 100, 100, 100, 100, 100]) is None  # flat
    assert prob_up([100, 101]) is None                                      # too short


def test_forecast_available_shapes():
    closes = _series(100, 0.003, 0.02, 31)
    f = forecast("btc", _rising_get(closes))
    assert isinstance(f, CryptoForecast)
    assert f.available is True
    assert f.baseline == "random_walk"
    assert f.sigma_pct is not None and f.sigma_pct > 0
    assert abs(f.band_pct - round(Z80 * f.sigma_pct, 4)) < 1e-9   # band = z80 * sigma
    assert 0.5 - PROB_CLAMP <= f.prob_up <= 0.5 + PROB_CLAMP
    assert f.n_closes == 31


def test_forecast_unsupported_coin_unavailable():
    f = forecast("usdt", _rising_get([100] * 31))        # stable -> no perp -> no forecast
    assert f.available is False and f.prob_up is None and f.band_pct is None


def test_forecast_fails_open_on_bad_fetch():
    f = forecast("btc", lambda url: None)                # network down
    assert f.available is False and f.sigma_pct is None


def test_forecast_thin_history_unavailable():
    f = forecast("btc", _rising_get([100, 101, 102]))    # < MIN_CLOSES
    assert f.available is False


if __name__ == "__main__":
    test_klines_closes_parses_and_skips_junk()
    test_realized_vol_pct_known_series()
    test_prob_up_is_humble_and_clamped()
    test_prob_up_none_when_flat_or_short()
    test_forecast_available_shapes()
    test_forecast_unsupported_coin_unavailable()
    test_forecast_fails_open_on_bad_fetch()
    test_forecast_thin_history_unavailable()
    print("ALL cfx-v1 CRYPTO-FORECAST TESTS PASSED")
