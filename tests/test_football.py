"""Football orchestration tests (zero-dep, run: python tests/test_football.py).

Team-name resolution (aliases + fail-open), best-effort odds parsing, and the
ESPN scoreboard -> (fixtures, results) extraction. HTTP injected so tests never
touch the network.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from football import (  # noqa: E402
    _implied_probs, elo_key, fetch_fixtures_and_results,
)

ELO = {"Brazil": 1800.0, "Bolivia": 1500.0, "Italy": 1700.0}


def _ev(eid, home, away, state, hs=None, as_=None, odds=None):
    comp = {"competitors": [
        {"homeAway": "home", "team": {"displayName": home}, "score": hs},
        {"homeAway": "away", "team": {"displayName": away}, "score": as_}],
        "odds": odds}
    return {"id": eid, "date": "2026-06-01T18:00Z",
            "status": {"type": {"state": state}}, "competitions": [comp]}


def _one_board(events):
    """get_json that returns the board on the first call, None afterwards."""
    calls = [0]
    def g(url):
        calls[0] += 1
        return {"events": events} if calls[0] == 1 else None
    return g


def test_elo_key_exact_alias_and_unknown():
    elo = {"South Korea": 1600.0}
    assert elo_key("Brazil", ELO) == "Brazil"           # exact
    assert elo_key("Korea Republic", elo) == "South Korea"   # alias
    assert elo_key("Atlantis", ELO) is None             # unknown -> fail-open


def test_implied_probs_normalises_and_handles_missing():
    comp = {"odds": [{"homeTeamOdds": {"decimal": 2.0},
                      "awayTeamOdds": {"decimal": 4.0}, "drawOdds": 4.0}]}
    p = _implied_probs(comp)
    assert p is not None and abs(sum(p) - 1.0) < 1e-9
    assert abs(p[0] - 0.5) < 1e-9                        # 1/2 normalised
    assert _implied_probs({"odds": None}) is None
    assert _implied_probs({"odds": [None]}) is None


def test_fetch_builds_fixtures_and_results_failopen_on_unknown():
    events = [
        _ev("m1", "Brazil", "Bolivia", "pre"),            # known -> forecast
        _ev("m2", "Italy", "Atlantis", "pre"),            # unknown away -> skipped
        _ev("m3", "Brazil", "Italy", "post", hs="2", as_="1"),  # finished -> result
        _ev("m4", "Brazil", "Bolivia", "in"),             # live -> skipped (lock pre only)
    ]
    fx, res = fetch_fixtures_and_results(ELO, get_json=_one_board(events))
    ids = {f["matchId"] for f in fx}
    assert ids == {"m1"}                                  # only the known pre match
    f = fx[0]
    assert f["probHome"] > f["probAway"]                  # Brazil (home, stronger) favoured
    assert f["topScorelines"] and f["why"]
    assert res == {"m3": {"homeScore": 2, "awayScore": 1}}


if __name__ == "__main__":
    test_elo_key_exact_alias_and_unknown()
    test_implied_probs_normalises_and_handles_missing()
    test_fetch_builds_fixtures_and_results_failopen_on_unknown()
    print("ALL FOOTBALL-ORCHESTRATION TESTS PASSED")
