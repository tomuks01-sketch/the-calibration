"""cs-v1 crypto-scoreboard tests (zero-dep, run: python tests/test_crypto_scoreboard.py).

SIGNAL_SPEC.md §9: aggregate vs random-walk. Below the N-gate (10) NO stats are
shown (honest small-N); at/above it, skillVsRandomWalk = 0.25 - meanBrierUp and
band coverage are exposed. Counts are always visible.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from crypto_scoreboard import (  # noqa: E402
    BASELINE_BRIER, band_pinball, build, direction_calibration,
)


def _resolved(symbol, prob_up, up_hit, brier, covered, band=None, realized=None):
    return {"symbol": symbol, "status": "RESOLVED", "probUp": prob_up,
            "upHit": up_hit, "brierUp": brier, "bandCovered": covered,
            "bandPct": band, "realizedChangePct": realized}


def _cl(entries):
    return {"entries": entries}


def test_below_gate_hides_stats_but_shows_counts():
    entries = [_resolved("btc", 0.55, 1, 0.2, True) for _ in range(5)]
    entries.append({"symbol": "eth", "status": "OPEN"})
    sb = build(_cl(entries))
    assert sb["confidence"] == "none"
    assert sb["direction"]["skillVsRandomWalk"] is None    # gated
    assert sb["band"]["coverageRate"] is None
    assert sb["counts"]["resolved"] == 5 and sb["counts"]["open"] == 1


def test_above_gate_scores_vs_random_walk():
    # 12 resolved, each Brier 0.20 (< 0.25) -> positive skill; all covered
    entries = [_resolved("btc", 0.6, 1, 0.20, True) for _ in range(12)]
    sb = build(_cl(entries))
    assert sb["confidence"] == "low"                       # 10 <= n < 30
    assert abs(sb["direction"]["meanBrierUp"] - 0.20) < 1e-9
    assert abs(sb["direction"]["skillVsRandomWalk"] - (BASELINE_BRIER - 0.20)) < 1e-9
    assert sb["direction"]["accuracy"] == 1.0              # probUp>0.5 and upHit==1 every time
    assert sb["band"]["coverageRate"] == 1.0
    assert sb["band"]["coverageWilson95"] is not None


def test_negative_skill_is_published_not_hidden():
    # Brier 0.30 (> 0.25 baseline) -> we are WORSE than a coin flip; must show it
    entries = [_resolved("btc", 0.6, 0, 0.30, False) for _ in range(12)]
    sb = build(_cl(entries))
    assert sb["direction"]["skillVsRandomWalk"] < 0        # honest: shown, not hidden
    assert sb["band"]["coverageRate"] == 0.0


def test_band_pinball_known_value():
    # realised 0%, band +/-2%: P10=-2 -> (0-(-2))*0.1=0.2 ; P90=+2 -> (2-0)*0.1=0.2 ; mean 0.2
    pb = band_pinball([_resolved("btc", 0.5, 1, 0.25, True, band=2.0, realized=0.0)])
    assert abs(pb - 0.2) < 1e-9
    assert band_pinball([]) is None                     # nothing to score
    assert band_pinball([_resolved("x", 0.5, 1, 0.25, True)]) is None  # missing band/realized -> skipped


def test_direction_calibration_bins_and_error():
    # 10 forecasts at probUp 0.55, all resolved up -> one bin, predicted 0.55, actual 1.0
    rows, err = direction_calibration([_resolved("btc", 0.55, 1, 0.2, True) for _ in range(10)])
    assert len(rows) == 1 and rows[0]["range"] == "55-60%"
    assert rows[0]["predicted"] == 0.55 and rows[0]["actual"] == 1.0
    assert abs(err - 0.45) < 1e-9                        # |0.55 - 1.0|
    assert direction_calibration([]) == ([], None)       # empty -> no rows, no error


def test_build_exposes_calibration_and_pinball_when_gated():
    entries = [_resolved("btc", 0.55, 1, 0.20, True, band=2.0, realized=1.0) for _ in range(12)]
    sb = build(_cl(entries))
    assert sb["direction"]["calibrationError"] is not None
    assert len(sb["direction"]["calibrationBins"]) >= 1
    assert sb["band"]["pinball"] is not None
    # below gate -> hidden
    sb2 = build(_cl([_resolved("btc", 0.55, 1, 0.2, True, band=2.0, realized=1.0) for _ in range(5)]))
    assert sb2["direction"]["calibrationError"] is None and sb2["band"]["pinball"] is None


if __name__ == "__main__":
    test_below_gate_hides_stats_but_shows_counts()
    test_above_gate_scores_vs_random_walk()
    test_negative_skill_is_published_not_hidden()
    test_band_pinball_known_value()
    test_direction_calibration_bins_and_error()
    test_build_exposes_calibration_and_pinball_when_gated()
    print("ALL cs-v1 CRYPTO-SCOREBOARD TESTS PASSED")
