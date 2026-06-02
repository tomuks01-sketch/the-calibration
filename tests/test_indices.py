"""Index-context tests (zero-dep, run: python tests/test_indices.py).

DESCRIPTIVE only (SIGNAL_SPEC §1): change % vs previous close, fail-open, never
invented. HTTP is injected so tests never touch the network.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from indices import fetch_indices, index_quote  # noqa: E402


def _yf(price, prev):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price,
                                           "chartPreviousClose": prev}}]}}


def _get_ok(url):
    return _yf(110.0, 100.0)        # +10% vs previous close


def test_index_quote_computes_change_vs_prev_close():
    q = index_quote("^GSPC", "S&P 500", _get_ok)
    assert q["symbol"] == "^GSPC" and q["name"] == "S&P 500"
    assert q["price"] == 110.0
    assert abs(q["changePct"] - 10.0) < 1e-9


def test_index_quote_none_on_missing_or_zero_prev():
    assert index_quote("^X", "x", lambda u: None) is None              # fetch failed
    assert index_quote("^X", "x", lambda u: _yf(100.0, 0)) is None     # prev=0 -> no honest change
    assert index_quote("^X", "x", lambda u: {"chart": {}}) is None      # malformed


def test_fetch_indices_fail_open_all_down():
    blk = fetch_indices(lambda u: None)                                # every call fails
    assert blk["available"] is False and blk["items"] == []
    assert blk["class"] == "descriptive"


def test_fetch_indices_available_when_some_ok():
    blk = fetch_indices(_get_ok)
    assert blk["available"] is True
    assert len(blk["items"]) == 4                                      # all 4 indices
    assert all("delayed" in blk["source"] for _ in [0])


if __name__ == "__main__":
    test_index_quote_computes_change_vs_prev_close()
    test_index_quote_none_on_missing_or_zero_prev()
    test_fetch_indices_fail_open_all_down()
    test_fetch_indices_available_when_some_ok()
    print("ALL INDEX-CONTEXT TESTS PASSED")
