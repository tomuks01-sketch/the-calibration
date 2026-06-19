"""fs2-v1 football-scoreboard tests (zero-dep, run: python tests/test_football_scoreboard.py).

RPS aggregate + W/D/L calibration + skill-vs-market, N-gated. Market comparison
needs >=10 matches with odds; negatives published, never hidden.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from football_scoreboard import build, calibration  # noqa: E402


def _res(outcome="home", ph=0.6, pd=0.25, pa=0.15, rps_m=0.09,
         rps_mkt=None, beat=None, mph=None, mpd=None, mpa=None):
    return {"status": "RESOLVED", "outcome": outcome,
            "probHome": ph, "probDraw": pd, "probAway": pa,
            "rpsModel": rps_m, "rpsMarket": rps_mkt, "beatMarket": beat,
            "marketProbHome": mph, "marketProbDraw": mpd, "marketProbAway": mpa}


def _cl(entries):
    return {"entries": entries}


def test_below_gate_hides_stats_but_shows_counts():
    sb = build(_cl([_res() for _ in range(5)] + [{"status": "OPEN"}]))
    assert sb["confidence"] == "none"
    assert sb["model"]["meanRps"] is None and sb["model"]["accuracy"] is None
    assert sb["counts"]["resolved"] == 5 and sb["counts"]["open"] == 1


def test_above_gate_model_stats():
    sb = build(_cl([_res(outcome="home") for _ in range(12)]))  # top pick = home every time
    assert sb["confidence"] == "low"
    assert abs(sb["model"]["meanRps"] - 0.09) < 1e-9
    assert sb["model"]["accuracy"] == 1.0                       # argmax probHome == home
    assert sb["model"]["calibrationError"] is not None
    assert len(sb["model"]["calibrationBins"]) >= 1


def test_skill_vs_market_gated_and_positive():
    # our RPS 0.09 beats market RPS 0.20 -> positive skill + beats every time
    entries = [_res(rps_m=0.09, rps_mkt=0.20, beat=True, mph=0.4, mpd=0.3, mpa=0.3)
               for _ in range(12)]
    sb = build(_cl(entries))
    assert sb["market"]["n"] == 12
    assert abs(sb["market"]["skillVsMarket"] - (0.20 - 0.09)) < 1e-9   # > 0 = we win
    assert sb["market"]["beatMarketRate"] == 1.0
    assert sb["market"]["meanRps"] is not None


def test_market_gate_off_below_10_with_odds():
    # 12 resolved but only 9 carry market odds -> market comparison hidden
    entries = ([_res(rps_mkt=0.2, beat=True, mph=0.4, mpd=0.3, mpa=0.3) for _ in range(9)]
               + [_res(rps_mkt=None) for _ in range(3)])
    sb = build(_cl(entries))
    assert sb["market"]["n"] == 9
    assert sb["market"]["skillVsMarket"] is None and sb["market"]["meanRps"] is None


def test_calibration_pools_three_outcomes():
    rows, err = calibration([_res(outcome="home", ph=0.6, pd=0.25, pa=0.15) for _ in range(12)])
    # three bins touched (0.6 home, 0.25 draw, 0.15 away), each n=12
    ranges = {r["range"]: r for r in rows}
    assert "60-70%" in ranges and ranges["60-70%"]["actual"] == 1.0   # home always happened
    assert "10-20%" in ranges and ranges["10-20%"]["actual"] == 0.0   # away never
    assert err is not None and err > 0


if __name__ == "__main__":
    test_below_gate_hides_stats_but_shows_counts()
    test_above_gate_model_stats()
    test_skill_vs_market_gated_and_positive()
    test_market_gate_off_below_10_with_odds()
    test_calibration_pools_three_outcomes()
    print("ALL fs2-v1 FOOTBALL-SCOREBOARD TESTS PASSED")
