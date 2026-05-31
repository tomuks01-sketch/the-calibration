"""P2 composite tests (zero-dep, run: python tests/test_composite.py).

Composite = transparent weighted average of crowd + baseline in LOG-ODDS
space, anchored on crowd (SIGNAL_SPEC.md §4). v0 weights are a fixed
documented prior (crowd 0.7, baseline 0.2, regimeAdjustment 0.0); the result
must always read "uncalibrated prior" and never replace crowd/qest. Crypto
(no crowd outcome) yields no composite.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from composite import composite_signal  # noqa: E402
from weights import default_weights  # noqa: E402


def _rec(crowd_prob, base_prob):
    return {
        "crowd": {"prob": crowd_prob, "available": crowd_prob is not None},
        "baseline": {"prob": base_prob, "available": base_prob is not None},
    }


def test_blend_between_crowd_and_baseline_closer_to_crowd():
    c = composite_signal(_rec(0.60, 0.50), default_weights())
    assert c is not None
    # weighted (0.7 crowd / 0.2 baseline) -> between 0.50 and 0.60, nearer 0.60
    assert 0.50 < c["prob"] < 0.60, c["prob"]
    assert (0.60 - c["prob"]) < (c["prob"] - 0.50)        # closer to crowd
    assert c["coverage"] == 1.0                            # both layers available
    assert c["contributions"]["baseline"] < 0             # baseline pulled it down
    assert c["weightsCalibrated"] is False
    assert c["label"] == "uncalibrated prior"


def test_baseline_unavailable_equals_crowd_with_partial_coverage():
    c = composite_signal(_rec(0.62, None), default_weights())
    assert abs(c["prob"] - 0.62) < 1e-9                    # only crowd -> composite == crowd
    assert round(c["coverage"], 3) == round(0.7 / 0.9, 3)  # 0.7 of 0.9 weight present
    assert c["contributions"]["baseline"] == 0.0


def test_crypto_no_crowd_outcome_has_no_composite():
    assert composite_signal(_rec(None, None), default_weights()) is None


def test_extremes_do_not_blow_up():
    c = composite_signal(_rec(0.99, 0.5), default_weights())
    assert c is not None and 0.0 < c["prob"] < 1.0        # logit clamp -> finite
    c2 = composite_signal(_rec(0.01, 0.5), default_weights())
    assert c2 is not None and 0.0 < c2["prob"] < 1.0


def test_default_weights_are_documented_prior():
    w = default_weights()
    assert w["calibrated"] is False
    assert w["weights"]["crowd"] == 0.7
    assert w["weights"]["baseline"] == 0.2
    assert w["weights"]["regimeAdjustment"] == 0.0        # candidate inert in v0


if __name__ == "__main__":
    test_blend_between_crowd_and_baseline_closer_to_crowd()
    test_baseline_unavailable_equals_crowd_with_partial_coverage()
    test_crypto_no_crowd_outcome_has_no_composite()
    test_extremes_do_not_blow_up()
    test_default_weights_are_documented_prior()
    print("ALL P2 COMPOSITE TESTS PASSED")
