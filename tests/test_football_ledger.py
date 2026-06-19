"""fl-v1 football-ledger tests (zero-dep, run: python tests/test_football_ledger.py).

Lock W/D/L forecasts pre-kickoff, settle on the final score, score with RPS vs
result AND vs market. Append-only; no result long after kickoff -> VOID. Time is
injected so tests are deterministic.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from football_ledger import open_matches, resolve_matches, rps  # noqa: E402

KO = "2026-06-01T18:00:00+00:00"        # kickoff
SOON = "2026-06-01T21:00:00+00:00"      # ~match end
LATE = "2026-06-20T00:00:00+00:00"      # well past stale window


def _fx(mid, ph=0.6, pd=0.25, pa=0.15, mph=None, mpd=None, mpa=None, kickoff=KO):
    return {"matchId": mid, "competition": "FIFA World Cup", "kickoff": kickoff,
            "home": "Brazil", "away": "Bolivia",
            "probHome": ph, "probDraw": pd, "probAway": pa,
            "marketProbHome": mph, "marketProbDraw": mpd, "marketProbAway": mpa}


def _cl():
    return {"entries": []}


def test_rps_perfect_worst_and_known():
    assert rps([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 0.0          # perfect
    assert rps([0.0, 0.0, 1.0], [1.0, 0.0, 0.0]) == 1.0          # said away, was home
    assert abs(rps([0.6, 0.25, 0.15], [1.0, 0.0, 0.0]) - 0.09125) < 1e-6


def test_open_locks_with_probs_and_dedups():
    cl = _cl()
    assert open_matches(cl, [_fx("m1"), {"matchId": "m2"}], now=KO) == 1  # m2 has no probs
    assert open_matches(cl, [_fx("m1")], now=KO) == 0                     # m1 already open
    e = cl["entries"][0]
    assert e["status"] == "OPEN" and e["matchId"] == "m1" and e["outcome"] is None


def test_resolve_scores_vs_result_and_beats_market():
    cl = _cl()
    # our model favours home (0.6); market is softer (0.4). Home wins -> we beat market.
    open_matches(cl, [_fx("m1", ph=0.6, pd=0.25, pa=0.15, mph=0.4, mpd=0.3, mpa=0.3)], now=KO)
    r, v = resolve_matches(cl, {"m1": {"homeScore": 2, "awayScore": 1}}, now=SOON)
    assert (r, v) == (1, 0)
    e = cl["entries"][0]
    assert e["status"] == "RESOLVED" and e["outcome"] == "home" and e["finalScore"] == "2-1"
    assert abs(e["rpsModel"] - 0.09125) < 1e-6
    assert abs(e["rpsMarket"] - 0.225) < 1e-6
    assert e["beatMarket"] is True                       # lower RPS = better


def test_resolve_market_none_when_no_market_probs():
    cl = _cl()
    open_matches(cl, [_fx("m1")], now=KO)                # no market probs given
    resolve_matches(cl, {"m1": {"homeScore": 0, "awayScore": 0}}, now=SOON)
    e = cl["entries"][0]
    assert e["outcome"] == "draw" and e["rpsModel"] is not None
    assert e["rpsMarket"] is None and e["beatMarket"] is None


def test_resolve_voids_when_stale_else_stays_open():
    cl = _cl()
    open_matches(cl, [_fx("m1")], now=KO)
    # recent, no result -> stays OPEN
    assert resolve_matches(cl, {}, now=SOON) == (0, 0)
    assert cl["entries"][0]["status"] == "OPEN"
    # well past kickoff, still no result -> VOID (never rots)
    assert resolve_matches(cl, {}, now=LATE) == (0, 1)
    assert cl["entries"][0]["status"] == "VOID"


if __name__ == "__main__":
    test_rps_perfect_worst_and_known()
    test_open_locks_with_probs_and_dedups()
    test_resolve_scores_vs_result_and_beats_market()
    test_resolve_market_none_when_no_market_probs()
    test_resolve_voids_when_stale_else_stays_open()
    print("ALL fl-v1 FOOTBALL-LEDGER TESTS PASSED")
