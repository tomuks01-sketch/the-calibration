"""Minimal moat-math guards. No pytest dependency (zero-dep project):
run with `python tests/test_core.py`. Covers the integrity-critical core:
model bounds, ledger dedup, terminal-outcome mapping.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from ledger import _terminal_outcome, open_calls  # noqa: E402
from model import evaluate  # noqa: E402


def test_model_bounds() -> None:
    # Extreme inputs must still clamp into [0.02, 0.98] or be ineligible.
    for mp, wk, liq, days in [
        (0.50, 0.9, 100000, 30),   # huge upward week move
        (0.50, -0.9, 100000, 30),  # huge downward
        (0.06, 0.5, 6000, 10),     # near the low edge
        (0.94, -0.5, 6000, 10),    # near the high edge
    ]:
        r = evaluate(mp, wk, liq, days, "0xcond")
        assert r.model_prob is None or 0.02 <= r.model_prob <= 0.98, r
    # Guards: near-certain / illiquid / bad-horizon must be ineligible.
    assert evaluate(0.99, 0.0, 100000, 30, "x").eligible is False
    assert evaluate(0.5, 0.0, 100, 30, "x").eligible is False
    assert evaluate(0.5, 0.0, 100000, 0, "x").eligible is False
    assert evaluate(0.5, 0.0, 100000, 30, "").eligible is False


def test_ledger_dedup() -> None:
    led = {"version": 1, "entries": []}
    cand = [{"conditionId": "0xAAA", "marketId": "m", "eventSlug": "s",
             "eventTitle": "t", "category": "c", "question": "q?",
             "modelProb": 0.6, "marketProb": 0.5, "divergence": 0.1}]
    assert open_calls(led, cand) == 1
    assert open_calls(led, cand) == 0          # same conditionId -> no dup
    assert len(led["entries"]) == 1


def test_terminal_outcome() -> None:
    assert _terminal_outcome({"closed": True, "outcomePrices": ["0.999", "0.001"]}) == 1
    assert _terminal_outcome({"closed": True, "outcomePrices": ["0.001", "0.999"]}) == 0
    assert _terminal_outcome({"closed": True, "outcomePrices": ["0.5", "0.5"]}) is None
    assert _terminal_outcome({"closed": False, "outcomePrices": ["1", "0"]}) is None


if __name__ == "__main__":
    test_model_bounds()
    test_ledger_dedup()
    test_terminal_outcome()
    print("ALL CORE TESTS PASSED")
