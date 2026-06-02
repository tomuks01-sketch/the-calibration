"""Top large-cap stocks tests (zero-dep, run: python tests/test_stocks.py).

DESCRIPTIVE only (SIGNAL_SPEC §1): change vs prior closes + a momentum-agreement
label, fail-open, never invented. HTTP injected so tests never hit the network.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from stocks import fetch_stocks, signal, stock_quote  # noqa: E402


def _chart(closes, vols=None):
    return {"chart": {"result": [{
        "meta": {"symbol": "X", "regularMarketPrice": closes[-1]},
        "indicators": {"quote": [{"close": closes, "volume": vols or [1] * len(closes)}]},
    }]}}


def _get(closes):
    return lambda url: _chart(closes)


def test_signal_agreement_directions():
    assert signal(2, 3, 5)["label"] == "rising"      # all up
    assert signal(-1, -2, -3)["label"] == "falling"  # all down
    assert signal(2, -1, 3)["label"] == "mixed"      # disagree
    assert signal(None, None, None)["label"] == "no data"


def test_stock_quote_computes_changes():
    closes = [float(100 + i) for i in range(40)]      # steady +1/day
    q = stock_quote("AAPL", "Apple", _get(closes))
    assert q["symbol"] == "AAPL" and q["name"] == "Apple"
    assert q["price"] == closes[-1]
    assert q["c24"] is not None and q["c24"] > 0       # last vs prev close
    assert q["c7"] is not None and q["c30"] is not None
    assert q["signal"]["label"] == "rising"            # all timeframes up
    assert len(q["spark"]) == 30                       # last 30 closes


def test_stock_quote_short_history_or_failure():
    assert stock_quote("X", "x", _get([100.0])) is None       # < 2 closes
    assert stock_quote("X", "x", lambda u: None) is None       # fetch failed
    assert stock_quote("X", "x", lambda u: {"chart": {}}) is None  # malformed


def test_fetch_stocks_fail_open_and_ranks():
    blk = fetch_stocks(lambda u: None)                 # every call fails
    assert blk["available"] is False and blk["items"] == []
    assert blk["class"] == "descriptive"
    blk2 = fetch_stocks(_get([float(100 + i) for i in range(40)]))
    assert blk2["available"] is True
    assert blk2["items"][0]["rank"] == 1               # ranked in list order
    assert len(blk2["items"]) == 10                    # all curated symbols


if __name__ == "__main__":
    test_signal_agreement_directions()
    test_stock_quote_computes_changes()
    test_stock_quote_short_history_or_failure()
    test_fetch_stocks_fail_open_and_ranks()
    print("ALL STOCKS TESTS PASSED")
