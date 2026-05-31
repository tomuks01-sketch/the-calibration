"""P5 ledger/scoreboard expansion tests (zero-dep).

Per-category Brier + Wilson confidence bands, N-gated (none<10, low<30), and
the ledger recording a compositeProbAtCallTime alongside the scored modelProb
(SIGNAL_SPEC.md §5/§6). Honesty: nothing meaningful is shown below the gate;
the scored field stays modelProb; old entries without composite keys are fine.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from ledger import open_calls  # noqa: E402
from scoreboard import _by_category, _wilson, build  # noqa: E402


def _resolved(category, model_brier, market_brier, prob=0.6, outcome=1):
    return {"status": "RESOLVED", "category": category, "modelBrier": model_brier,
            "marketBrier": market_brier, "modelProb": prob, "resolvedOutcome": outcome}


def test_wilson_interval():
    lo, hi = _wilson(5, 10)
    assert lo < 0.5 < hi and 0.0 <= lo and hi <= 1.0   # symmetric-ish around 0.5
    lo2, hi2 = _wilson(10, 10)
    assert hi2 <= 1.0 and lo2 < 1.0                     # all-wins: upper near 1, lower < 1
    assert _wilson(0, 0) is None
    # small N -> WIDE band (that is the honest point)
    w_small = _wilson(8, 10); w_big = _wilson(80, 100)
    assert (w_small[1] - w_small[0]) > (w_big[1] - w_big[0])


def test_by_category_gating():
    resolved = (
        [_resolved("Politics", 0.10, 0.20) for _ in range(12)]   # N=12 -> "low", gated open
        + [_resolved("Crypto", 0.10, 0.20) for _ in range(3)]    # N=3  -> "none", nulls
    )
    out = _by_category(resolved)
    pol = out["Politics"]
    assert pol["n"] == 12 and pol["confidence"] == "low"
    assert pol["modelBrier"] == 0.1 and pol["crowdBrier"] == 0.2
    assert pol["skillVsCrowd"] == 0.1                  # crowd 0.2 - model 0.1
    assert pol["beatsCrowdRate"] == 1.0                # model beat crowd every time
    assert pol["beatsCrowdWilson95"] is not None
    cry = out["Crypto"]
    assert cry["n"] == 3 and cry["confidence"] == "none"
    assert cry["modelBrier"] is None and cry["beatsCrowdRate"] is None   # gated -> nothing shown


def test_build_includes_bycategory_empty_when_no_resolved():
    led = {"version": 1, "entries": [
        {"status": "PENDING", "category": "x", "modelProb": 0.5, "modelBrier": None,
         "marketBrier": None}
    ]}
    sb = build(led)
    assert sb["byCategory"] == {}                       # nothing resolved -> empty, honest
    assert sb["confidence"] == "none"


def test_ledger_records_composite_but_scores_qest():
    led = {"version": 1, "entries": []}
    cand = [{"conditionId": "0xZ", "marketId": "m", "question": "q?",
             "eventSlug": "s", "eventTitle": "t", "category": "c",
             "modelProb": 0.6, "marketProb": 0.5, "divergence": 0.1}]
    assert open_calls(led, cand) == 1
    e = led["entries"][0]
    # composite recorded for FUTURE scoring (web/weights.json is committed)
    assert "compositeProbAtCallTime" in e
    assert isinstance(e["compositeProbAtCallTime"], float)
    assert e["compositeWeightsVersion"] == "w-v1"
    # the SCORED field is unchanged — still modelProb (QEST), never the composite
    assert e["modelProb"] == 0.6
    assert e["modelBrier"] is None                      # not resolved yet


if __name__ == "__main__":
    test_wilson_interval()
    test_by_category_gating()
    test_build_includes_bycategory_empty_when_no_resolved()
    test_ledger_records_composite_but_scores_qest()
    print("ALL P5 SCOREBOARD/LEDGER TESTS PASSED")
