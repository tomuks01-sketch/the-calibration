"""P6 calibration tests (zero-dep, run: python tests/test_calibrate.py).

calibrate_from_ledger refits the composite weights from RESOLVED outcomes by
minimising Brier — using the SAME composite_signal used in production. Honesty
gate: below N=30 resolved it returns the documented prior UNCHANGED (never
fits on thin data, per SIGNAL_SPEC.md §4/§6).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from weights import calibrate_from_ledger, default_weights  # noqa: E402


def _entry(model_prob, crowd_prob, outcome):
    return {"status": "RESOLVED", "modelProb": model_prob,
            "crowdProbAtCallTime": crowd_prob, "resolvedOutcome": outcome}


def _ledger(entries):
    return {"version": 1, "entries": entries}


def test_below_gate_returns_prior_unchanged():
    led = _ledger([_entry(0.6, 0.5, 1) for _ in range(12)])   # N=12 < 30
    w = calibrate_from_ledger(led)
    assert w["calibrated"] is False
    assert w["weights"] == default_weights()["weights"]       # prior untouched
    assert "12" in w["note"] and "30" in w["note"]            # honest "insufficient N (12/30)"


def test_at_gate_fits_toward_better_layer():
    # Construct 40 resolved calls where the BASELINE is consistently closer to
    # the outcome than the crowd -> the fit should favour baseline (lower crowd
    # weight than the 0.7 prior).
    entries = []
    for i in range(40):
        if i % 2 == 0:
            entries.append(_entry(0.90, 0.60, 1))   # baseline near 1, crowd far
        else:
            entries.append(_entry(0.10, 0.40, 0))   # baseline near 0, crowd far
    w = calibrate_from_ledger(_ledger(entries))
    assert w["calibrated"] is True
    assert w["fittedN"] == 40
    assert w["weights"]["crowd"] < 0.7                        # moved off the prior toward baseline
    assert w["weights"]["regimeAdjustment"] == 0.0           # regime still inert
    assert abs(w["weights"]["crowd"] + w["weights"]["baseline"] - 1.0) < 1e-9
    assert isinstance(w.get("fittedBrier"), float)
    assert w["weightsVersion"] != "w-v1"                      # bumped so old calls keep their version


def test_ignores_unresolved_and_incomplete():
    entries = (
        [_entry(0.9, 0.6, 1) for _ in range(40)]
        + [{"status": "PENDING", "modelProb": 0.5, "crowdProbAtCallTime": 0.5, "resolvedOutcome": None}]
        + [{"status": "RESOLVED", "modelProb": None, "crowdProbAtCallTime": 0.5, "resolvedOutcome": 1}]
    )
    w = calibrate_from_ledger(_ledger(entries))
    assert w["fittedN"] == 40                                 # only complete resolved entries counted


if __name__ == "__main__":
    test_below_gate_returns_prior_unchanged()
    test_at_gate_fits_toward_better_layer()
    test_ignores_unresolved_and_incomplete()
    print("ALL P6 CALIBRATION TESTS PASSED")
