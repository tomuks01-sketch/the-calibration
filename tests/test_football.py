"""Football orchestration tests (zero-dep, run: python tests/test_football.py).

Team-name resolution (aliases + fail-open), best-effort odds parsing, and the
ESPN scoreboard -> (fixtures, results) extraction. HTTP injected so tests never
touch the network.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from football import (  # noqa: E402
    _implied_probs, _odd_to_decimal, _pickcenter_implied, elo_key,
    fetch_fixtures_and_results,
)

ELO = {"Brazil": 1800.0, "Bolivia": 1500.0, "Italy": 1700.0}


def _ev(eid, home, away, state, hs=None, as_=None, odds=None, date="2026-06-01T18:00Z"):
    comp = {"competitors": [
        {"homeAway": "home", "team": {"displayName": home}, "score": hs},
        {"homeAway": "away", "team": {"displayName": away}, "score": as_}],
        "odds": odds}
    return {"id": eid, "date": date,
            "status": {"type": {"state": state}}, "competitions": [comp]}


def _one_board(events, summaries=None):
    """get_json that serves the scoreboard for /scoreboard URLs and per-event
    summary JSON for /summary URLs (so market-odds parsing can be exercised)."""
    summaries = summaries or {}
    def g(url):
        if "/summary?event=" in url:
            eid = url.split("event=")[-1]
            return summaries.get(eid)
        if "/scoreboard" in url:
            return {"events": events}
        return None
    return g


def _pc(home_ml, draw_ml, away_ml):
    """A minimal ESPN summary payload carrying pickcenter moneylines."""
    return {"pickcenter": [{
        "homeTeamOdds": {"moneyLine": home_ml},
        "awayTeamOdds": {"moneyLine": away_ml},
        "drawOdds": {"moneyLine": draw_ml},
    }]}


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


def test_odd_to_decimal_handles_american_and_decimal():
    # American moneylines (|v| >= 100)
    assert abs(_odd_to_decimal(100) - 2.0) < 1e-9          # +100 even money
    assert abs(_odd_to_decimal(-235) - (1 + 100 / 235)) < 1e-9
    assert abs(_odd_to_decimal(600) - 7.0) < 1e-9          # +600 (was mis-read as decimal)
    # Decimal odds (1 < v < 100)
    assert abs(_odd_to_decimal(2.5) - 2.5) < 1e-9
    # Invalid
    assert _odd_to_decimal(0) is None
    assert _odd_to_decimal("x") is None
    assert _odd_to_decimal(1.0) is None                    # <= 1 is not a valid quote


def test_pickcenter_implied_normalises_three_way():
    # Real-shape Germany v Ivory Coast: -235 / +400 / +600
    p = _pickcenter_implied(_pc(-235, 400, 600))
    assert p is not None and abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1] and p[0] > p[2]                     # home (-235) the favourite
    assert p[1] > p[2]                                     # draw (+400) over away (+600)
    assert p[0] > 0.6                                      # strong favourite de-vigged
    # Missing / malformed -> None (fail-open)
    assert _pickcenter_implied(None) is None
    assert _pickcenter_implied({"pickcenter": []}) is None
    assert _pickcenter_implied({"pickcenter": [{"homeTeamOdds": {}}]}) is None


def test_fetch_builds_fixtures_and_results_failopen_on_unknown():
    events = [
        _ev("m1", "Brazil", "Bolivia", "pre"),            # known -> forecast
        _ev("m2", "Italy", "Atlantis", "pre"),            # unknown away -> skipped
        _ev("m3", "Brazil", "Italy", "post", hs="2", as_="1"),  # finished -> result
        _ev("m4", "Brazil", "Bolivia", "in"),             # live -> skipped (lock pre only)
    ]
    # m1 carries pickcenter odds via the summary endpoint.
    summaries = {"m1": _pc(-300, 350, 700)}
    fx, res = fetch_fixtures_and_results(
        ELO, get_json=_one_board(events, summaries))
    ids = {f["matchId"] for f in fx}
    assert ids == {"m1"}                                  # only the known pre match
    f = fx[0]
    assert f["probHome"] > f["probAway"]                  # Brazil (home, stronger) favoured
    assert f["topScorelines"] and f["why"]
    assert f["marketProbHome"] is not None                # market odds parsed from summary
    assert abs(f["marketProbHome"] + f["marketProbDraw"]
               + f["marketProbAway"] - 1.0) < 1e-9
    assert res == {"m3": {"homeScore": 2, "awayScore": 1}}


def test_fetch_failopen_when_summary_missing():
    """No summary payload -> market probs are None, model still forecasts."""
    events = [_ev("m1", "Brazil", "Bolivia", "pre")]
    fx, _ = fetch_fixtures_and_results(ELO, get_json=_one_board(events))
    assert fx and fx[0]["marketProbHome"] is None


def test_fetch_skips_far_future_matches_outside_lock_window():
    """A match many months out (no odds yet) is not locked; one near kickoff is."""
    events = [
        _ev("far", "Brazil", "Bolivia", "pre", date="2099-01-01T00:00Z"),
        _ev("near", "Brazil", "Italy", "pre", date="2026-06-01T18:00Z"),
    ]
    fx, _ = fetch_fixtures_and_results(ELO, get_json=_one_board(events))
    assert {f["matchId"] for f in fx} == {"near"}


if __name__ == "__main__":
    test_elo_key_exact_alias_and_unknown()
    test_implied_probs_normalises_and_handles_missing()
    test_odd_to_decimal_handles_american_and_decimal()
    test_pickcenter_implied_normalises_three_way()
    test_fetch_builds_fixtures_and_results_failopen_on_unknown()
    test_fetch_failopen_when_summary_missing()
    test_fetch_skips_far_future_matches_outside_lock_window()
    print("ALL FOOTBALL-ORCHESTRATION TESTS PASSED")
