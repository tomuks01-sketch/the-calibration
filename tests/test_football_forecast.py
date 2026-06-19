"""fbx-v1 football model tests (zero-dep, run: python tests/test_football_forecast.py).

World Football Elo + Poisson goals model. Documented + reproducible; fail-open
on unknown teams (never invent a rating). HTTP injected so tests never hit the net.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from football_forecast import (  # noqa: E402
    ELO_BASE, _expected, _g_multiplier, compute_elo, forecast_match, load_results,
)

_CSV = (
    "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
    "2020-01-01,Brazil,Chile,3,0,Friendly,Rio,Brazil,FALSE\n"
    "2020-02-01,Brazil,Chile,2,1,FIFA World Cup,Doha,Qatar,TRUE\n"
    "2026-07-01,Chile,Brazil,NA,NA,Friendly,Santiago,Chile,FALSE\n"   # unplayed -> skipped
)


def test_load_results_skips_unplayed():
    rows = load_results(lambda url: _CSV)
    assert len(rows) == 2                       # the NA fixture dropped
    assert rows[0]["home"] == "Brazil" and rows[0]["hs"] == 3
    assert rows[1]["neutral"] is True


def test_expected_and_g_multiplier():
    assert abs(_expected(1500, 1500) - 0.5) < 1e-9
    assert _expected(1700, 1500) > 0.5 > _expected(1300, 1500)
    assert _g_multiplier(1) == 1.0 and _g_multiplier(2) == 1.5
    assert abs(_g_multiplier(3) - (11 + 3) / 8) < 1e-9     # bigger win moves more


def test_compute_elo_rewards_winner_symmetrically():
    elo = compute_elo(load_results(lambda url: _CSV))
    assert elo["Brazil"] > ELO_BASE > elo["Chile"]          # two wins -> Brazil up
    # Elo is zero-sum per match: what Brazil gained, Chile lost
    assert abs((elo["Brazil"] - ELO_BASE) + (elo["Chile"] - ELO_BASE)) < 1e-6


def test_forecast_stronger_team_favoured_and_normalised():
    elo = {"Strong": 1750.0, "Weak": 1400.0}
    f = forecast_match("Strong", "Weak", elo)
    assert f.available is True
    assert f.prob_home > f.prob_away                        # stronger + home -> favoured
    s = f.prob_home + f.prob_draw + f.prob_away
    assert abs(s - 1.0) < 0.02                              # probs ~sum to 1 (truncation)
    assert len(f.top_scorelines) == 5 and f.top_scorelines[0]["prob"] > 0
    assert 0.0 <= f.prob_over_2_5 <= 1.0 and 0.0 <= f.prob_btts <= 1.0
    assert f.exp_goals_home > f.exp_goals_away              # supremacy -> more goals
    assert any("Elo" in w for w in f.why)                   # reasoning surfaced


def test_forecast_unknown_team_unavailable():
    f = forecast_match("Nowhere", "Elsewhere", {"Strong": 1750.0})
    assert f.available is False and f.prob_home is None


def test_neutral_venue_removes_home_edge():
    elo = {"A": 1600.0, "B": 1600.0}
    home = forecast_match("A", "B", elo, neutral=False)
    neut = forecast_match("A", "B", elo, neutral=True)
    assert home.prob_home > neut.prob_home                  # home advantage matters
    assert abs(neut.prob_home - neut.prob_away) < 1e-6      # equal teams, neutral -> symmetric


if __name__ == "__main__":
    test_load_results_skips_unplayed()
    test_expected_and_g_multiplier()
    test_compute_elo_rewards_winner_symmetrically()
    test_forecast_stronger_team_favoured_and_normalised()
    test_forecast_unknown_team_unavailable()
    test_neutral_venue_removes_home_edge()
    print("ALL fbx-v1 FOOTBALL-FORECAST TESTS PASSED")
