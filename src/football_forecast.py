"""International football forecast (fbx-v1) — our OWN model, documented + scorable.

For big international games (World Cup, Euros, Copa América, qualifiers, Nations League)
we want a rich, falsifiable read: who wins (W/D/L), the likely scoreline and a
'what could happen' scenario table, plus WHY — and every number is scored vs the
result AND vs the market, so any edge is proven, never claimed.

Two documented, reproducible layers (NOT 'AI', NOT fitted — priors until a
resolved track record earns calibration, per the project's honesty rule):

  1. World Football Elo: delta = weight * G * (result - expected), weight =
     tournament importance, G = goal-difference multiplier, home advantage in
     Elo points. Iterated chronologically over real history.
  2. Poisson goals model: the Elo gap maps to an expected goal supremacy; two
     Poisson rates (lambda_home, lambda_away) give the full scoreline matrix ->
     W/D/L, the top scorelines, expected goals, over-2.5 and both-teams-score.

Data: martj42/international_results (keyless GitHub CSV, ~49k matches). HTTP is
injectable so tests never touch the network. NEVER 'team X will win'; always
probabilities + scenarios, scored in public.
"""

from __future__ import annotations

import csv
import io
import math
import urllib.error
import urllib.request
from dataclasses import dataclass

FORECAST_VERSION = "fbx-v1"
INTL_RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)
REQUEST_TIMEOUT_S = 20

# --- Elo priors (documented; World Football Elo conventions) ---
ELO_BASE = 1500.0
HOME_ADV_ELO = 65.0        # ~0.59 expected score for otherwise-equal teams at home
# Tournament importance weight (the Elo K). Bigger games move ratings more.
TOURNAMENT_WEIGHT = {
    "FIFA World Cup": 60.0,
    "UEFA Euro": 50.0,
    "Copa América": 50.0,
    "FIFA World Cup qualification": 40.0,
    "UEFA Euro qualification": 40.0,
    "UEFA Nations League": 40.0,
    "Friendly": 20.0,
}
DEFAULT_WEIGHT = 30.0      # any other competitive match

# --- Goals model priors ---
INTL_AVG_TOTAL_GOALS = 2.6  # long-run avg total goals in international football
ELO_PER_GOAL = 250.0        # Elo gap (incl. home adv) per 1.0 of expected supremacy
MIN_LAMBDA = 0.15           # a team is never literally incapable of scoring
MAX_GOALS = 8               # scoreline matrix truncation (P(>8) is negligible)


def _default_get(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pmi/0.1"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
            return r.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _i(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_results(get=_default_get) -> list[dict]:
    """Played international matches (with both scores), oldest -> newest."""
    text = get(INTL_RESULTS_URL)
    if not text:
        return []
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        hs, as_ = _i(row.get("home_score")), _i(row.get("away_score"))
        if hs is None or as_ is None:
            continue  # unplayed / scheduled fixture — skip for rating
        out.append({
            "date": row.get("date", ""),
            "home": (row.get("home_team") or "").strip(),
            "away": (row.get("away_team") or "").strip(),
            "hs": hs, "as": as_,
            "tournament": (row.get("tournament") or "").strip(),
            "neutral": (row.get("neutral") or "").strip().lower() == "true",
        })
    return out


def _expected(elo_a: float, elo_b: float) -> float:
    """Elo expected score for A vs B (0..1)."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def _g_multiplier(goal_diff: int) -> float:
    """Goal-difference multiplier G (World Football Elo): a bigger win moves
    ratings more, with diminishing returns."""
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11.0 + gd) / 8.0


def compute_elo(matches: list[dict]) -> dict[str, float]:
    """Iterate matches chronologically, returning final Elo per team. New teams
    start at ELO_BASE. Home advantage applied only for non-neutral venues."""
    elo: dict[str, float] = {}
    for m in matches:
        h, a = m["home"], m["away"]
        if not h or not a:
            continue
        rh = elo.get(h, ELO_BASE)
        ra = elo.get(a, ELO_BASE)
        ha = 0.0 if m["neutral"] else HOME_ADV_ELO
        exp_h = _expected(rh + ha, ra)
        res_h = 1.0 if m["hs"] > m["as"] else 0.0 if m["hs"] < m["as"] else 0.5
        weight = TOURNAMENT_WEIGHT.get(m["tournament"], DEFAULT_WEIGHT)
        delta = weight * _g_multiplier(m["hs"] - m["as"]) * (res_h - exp_h)
        elo[h] = rh + delta
        elo[a] = ra - delta
    return elo


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


@dataclass(frozen=True)
class MatchForecast:
    home: str
    away: str
    available: bool
    elo_home: float | None
    elo_away: float | None
    prob_home: float | None      # P(home win)
    prob_draw: float | None
    prob_away: float | None
    exp_goals_home: float | None
    exp_goals_away: float | None
    total_goals: float | None     # expected total goals (lambda_home + lambda_away)
    top_scorelines: list          # [{"score": "2-1", "prob": 0.11}, ...] highest first
    prob_over_1_5: float | None
    prob_over_2_5: float | None
    prob_over_3_5: float | None
    prob_btts: float | None       # both teams to score
    why: list                     # human-readable factor strings


def forecast_match(home: str, away: str, elo: dict[str, float],
                   neutral: bool = False) -> MatchForecast:
    """Full probabilistic read for one fixture from the Elo table. Fail-open:
    unknown teams -> available:false (we never invent a rating)."""
    base = MatchForecast(home=home, away=away, available=False, elo_home=None,
                         elo_away=None, prob_home=None, prob_draw=None, prob_away=None,
                         exp_goals_home=None, exp_goals_away=None, total_goals=None,
                         top_scorelines=[], prob_over_1_5=None, prob_over_2_5=None,
                         prob_over_3_5=None, prob_btts=None, why=[])
    rh, ra = elo.get(home), elo.get(away)
    if rh is None or ra is None:
        return base
    ha = 0.0 if neutral else HOME_ADV_ELO
    elo_diff = (rh + ha) - ra
    supremacy = elo_diff / ELO_PER_GOAL                       # expected goal margin
    lam_h = max(MIN_LAMBDA, INTL_AVG_TOTAL_GOALS / 2.0 + supremacy / 2.0)
    lam_a = max(MIN_LAMBDA, INTL_AVG_TOTAL_GOALS / 2.0 - supremacy / 2.0)

    ph = [_poisson_pmf(k, lam_h) for k in range(MAX_GOALS + 1)]
    pa = [_poisson_pmf(k, lam_a) for k in range(MAX_GOALS + 1)]
    p_home = p_draw = p_away = p_btts = 0.0
    p_o15 = p_o25 = p_o35 = 0.0
    cells = []
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            p = ph[h] * pa[a]
            cells.append((p, h, a))
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            tot = h + a
            if tot > 1.5:
                p_o15 += p
            if tot > 2.5:
                p_o25 += p
            if tot > 3.5:
                p_o35 += p
            if h >= 1 and a >= 1:
                p_btts += p
    cells.sort(reverse=True)
    top = [{"score": f"{h}-{a}", "prob": round(p, 4)} for p, h, a in cells[:5]]

    why = [
        f"Elo {round(rh)} vs {round(ra)} ({'+' if elo_diff >= 0 else ''}{round(elo_diff)} incl. "
        f"{'neutral venue' if neutral else 'home advantage'})",
        f"expected goals {round(lam_h, 2)} – {round(lam_a, 2)}",
        f"most likely score {top[0]['score']} ({round(top[0]['prob'] * 100)}%)" if top else "",
    ]
    return MatchForecast(
        home=home, away=away, available=True, elo_home=round(rh, 1), elo_away=round(ra, 1),
        prob_home=round(p_home, 4), prob_draw=round(p_draw, 4), prob_away=round(p_away, 4),
        exp_goals_home=round(lam_h, 3), exp_goals_away=round(lam_a, 3),
        total_goals=round(lam_h + lam_a, 2), top_scorelines=top,
        prob_over_1_5=round(p_o15, 4), prob_over_2_5=round(p_o25, 4),
        prob_over_3_5=round(p_o35, 4), prob_btts=round(p_btts, 4),
        why=[w for w in why if w],
    )
