"""Football orchestration — fetch ESPN fixtures/results, forecast, open + resolve.

Ties the model (football_forecast), the ledger (football_ledger) and the
scoreboard (football_scoreboard) to live data:

  - Elo is computed from the keyless 49k-match history and CACHED to
    web/football_elo.json (refreshed daily, not every 30-min cron run).
  - For each international competition we read the ESPN scoreboard: upcoming
    ('pre') matches get a forecast locked in the ledger; finished ('post')
    matches feed the resolver with their final score.
  - Market implied probabilities are best-effort from ESPN odds (often absent);
    the model is scored regardless, the market comparison accrues when present.

Fully fail-open: any fetch/parse error simply yields fewer forecasts, never an
exception that could break the snapshot. HTTP is injectable for tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from football_forecast import compute_elo, forecast_match, load_results

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/{}/scoreboard"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{}/summary?event={}"
# International "world games": World Cup, continental, their qualifiers, Nations
# League. NATIONAL TEAMS ONLY — the Elo is built from international results, so
# club competitions (e.g. the Champions League) can't be forecast and are out of
# scope; including them would just fetch matches we always drop.
COMPETITIONS = [
    "fifa.world", "uefa.euro", "conmebol.america",
    "fifa.worldq.uefa", "fifa.worldq.conmebol", "uefa.nations",
]
ELO_CACHE = Path(__file__).resolve().parent.parent / "web" / "football_elo.json"
ELO_CACHE_MAX_AGE_H = 24

# Only lock a forecast once a match is within this window of kickoff. ESPN lists
# fixtures (esp. qualifiers) months ahead, before any market odds exist; locking
# that early gives a stale-Elo "forecast" with no market to score against. A few
# days out the 3-way odds are posted and the Elo reflects the current squad, so
# the lock is a genuine pre-match call AND captures the market for comparison.
LOCK_WINDOW_HOURS = 120

# ESPN display name -> martj42 history name (only where they differ).
ALIASES = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Korea DPR": "North Korea",
    "USA": "United States",
    "China PR": "China",
    "Côte d'Ivoire": "Ivory Coast",
    "Cape Verde Islands": "Cape Verde",
    "DR Congo": "DR Congo",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_since(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 1e9
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _hours_until(iso: str) -> float | None:
    """Hours from now until `iso` (negative if past). None if unparseable —
    callers treat that as 'don't gate on time' (fail-open, never drop a match)."""
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (t - datetime.now(timezone.utc)).total_seconds() / 3600.0


def _get_text(url: str) -> str | None:
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 pmi/0.1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _get_json(url: str):
    txt = _get_text(url)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def elo_key(name: str, elo: dict) -> str | None:
    """Resolve an ESPN team name to its Elo-table key, or None (fail-open)."""
    if name in elo:
        return name
    a = ALIASES.get(name)
    return a if (a and a in elo) else None


def load_or_compute_elo(get_text=_get_text) -> dict:
    """Return {generatedAt, elo:{team:rating}}. Use the cache if <24h old,
    else recompute from the keyless history and persist it."""
    if ELO_CACHE.exists():
        try:
            cached = json.loads(ELO_CACHE.read_text(encoding="utf-8"))
            if _hours_since(cached.get("generatedAt", "")) < ELO_CACHE_MAX_AGE_H and cached.get("elo"):
                return cached
        except (ValueError, OSError):
            pass
    elo = compute_elo(load_results())
    out = {"generatedAt": _now(), "elo": elo}
    if elo:
        try:
            ELO_CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = ELO_CACHE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(out), encoding="utf-8")
            tmp.replace(ELO_CACHE)
        except OSError:
            pass
    return out


def _odd_to_decimal(v) -> float | None:
    """Normalise a single price to decimal odds. Handles American moneylines
    (|v| >= 100, e.g. -235 or +600) and decimal odds (1 < v < 100). Anything
    else (0, <=1, non-numeric) is invalid -> None. The |v|>=100 split is exact:
    American lines are always >= +100 or <= -100, decimal quotes never are."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v == 0:
        return None
    if abs(v) >= 100:                       # American moneyline
        return 1.0 + (v / 100.0 if v > 0 else 100.0 / -v)
    if v > 1.0:                             # decimal odds
        return float(v)
    return None


def _normalise(dh: float | None, dd: float | None,
               da: float | None) -> tuple[float, float, float] | None:
    """Three decimal odds -> de-vigged (home, draw, away) probabilities."""
    if not (dh and dd and da):
        return None
    raw = [1.0 / dh, 1.0 / dd, 1.0 / da]
    s = sum(raw)
    return (raw[0] / s, raw[1] / s, raw[2] / s) if s > 0 else None


def _pickcenter_implied(summary: dict | None) -> tuple[float, float, float] | None:
    """3-way implied probabilities from an ESPN summary's pickcenter block —
    the only place the moneyline (home/draw/away) actually lives for soccer.
    None if absent or unparseable (fail-open)."""
    if not isinstance(summary, dict):
        return None
    pc = summary.get("pickcenter")
    if not isinstance(pc, list) or not pc or not isinstance(pc[0], dict):
        return None
    o = pc[0]

    def _ml(block):
        if not isinstance(block, dict):
            return None
        return _odd_to_decimal(block.get("moneyLine"))

    return _normalise(_ml(o.get("homeTeamOdds")), _ml(o.get("drawOdds")),
                      _ml(o.get("awayTeamOdds")))


def _implied_probs(comp: dict) -> tuple[float, float, float] | None:
    """Best-effort 3-way implied probabilities from a scoreboard event's odds
    block (rarely carries a moneyline for soccer; pickcenter is preferred).
    Normalised to remove the overround. None if unparseable."""
    odds = comp.get("odds")
    if not isinstance(odds, list) or not odds or not isinstance(odds[0], dict):
        return None
    o = odds[0]

    def _pick(block, *keys):
        if not isinstance(block, dict):
            return None
        for k in keys:
            d = _odd_to_decimal(block.get(k))
            if d is not None:
                return d
        return None

    dh = _pick(o.get("homeTeamOdds"), "decimal", "moneyLine")
    da = _pick(o.get("awayTeamOdds"), "decimal", "moneyLine")
    draw = o.get("drawOdds")
    dd = _odd_to_decimal(draw) if isinstance(draw, (int, float)) \
        else _pick(draw, "decimal", "moneyLine")
    return _normalise(dh, dd, da)


def fetch_fixtures_and_results(elo: dict, get_json=_get_json) -> tuple[list[dict], dict]:
    """Read every competition scoreboard. Returns (fixtures_to_open, results)."""
    fixtures, results = [], {}
    for comp in COMPETITIONS:
        data = get_json(ESPN_SCOREBOARD.format(comp))
        for ev in (data or {}).get("events", []) or []:
            try:
                c = ev["competitions"][0]
                cs = {x["homeAway"]: x for x in c["competitors"]}
                home_nm = cs["home"]["team"]["displayName"]
                away_nm = cs["away"]["team"]["displayName"]
                state = ev["status"]["type"]["state"]
                mid = str(ev["id"])
            except (KeyError, IndexError, TypeError):
                continue
            if state == "post":
                try:
                    results[mid] = {"homeScore": int(cs["home"]["score"]),
                                    "awayScore": int(cs["away"]["score"])}
                except (KeyError, TypeError, ValueError):
                    pass
                continue
            if state != "pre":
                continue  # 'in' (live) — skip; lock only before kickoff
            hrs = _hours_until(ev.get("date", ""))
            if hrs is not None and hrs > LOCK_WINDOW_HOURS:
                continue  # too far out — odds not posted yet; lock nearer kickoff
            hk, ak = elo_key(home_nm, elo), elo_key(away_nm, elo)
            if hk is None or ak is None:
                continue  # unknown team -> no forecast (honest, never invented)
            neutral = comp in ("fifa.world", "uefa.euro", "conmebol.america")
            f = forecast_match(hk, ak, elo, neutral=neutral)
            if not f.available:
                continue
            # Real 3-way moneyline lives in the summary's pickcenter; the
            # scoreboard odds block is a best-effort fallback. One extra HTTP
            # call per *forecastable* upcoming match only — bounded + fail-open.
            mp = _pickcenter_implied(get_json(ESPN_SUMMARY.format(comp, mid))) \
                or _implied_probs(c)
            fixtures.append({
                "matchId": mid, "competition": comp, "kickoff": ev.get("date", _now()),
                "home": home_nm, "away": away_nm,
                "probHome": f.prob_home, "probDraw": f.prob_draw, "probAway": f.prob_away,
                "expGoalsHome": f.exp_goals_home, "expGoalsAway": f.exp_goals_away,
                "topScorelines": f.top_scorelines,
                "markets": {
                    "over15": f.prob_over_1_5, "over25": f.prob_over_2_5,
                    "over35": f.prob_over_3_5, "btts": f.prob_btts,
                    "totalGoals": f.total_goals,
                },
                "marketProbHome": mp[0] if mp else None,
                "marketProbDraw": mp[1] if mp else None,
                "marketProbAway": mp[2] if mp else None,
                "eloHome": f.elo_home, "eloAway": f.elo_away, "why": f.why,
            })
    return fixtures, results


def run() -> dict:
    """Full cycle: forecast upcoming, resolve finished, persist ledger +
    scoreboard. Returns a small summary. Fail-open at the call site."""
    from football_ledger import (load_football_ledger, open_matches,
                                  resolve_matches, save_football_ledger)
    from football_scoreboard import write as write_scoreboard

    elo = load_or_compute_elo().get("elo", {})
    fixtures, results = fetch_fixtures_and_results(elo)
    fl = load_football_ledger()
    opened = open_matches(fl, fixtures)
    resolved, voided = resolve_matches(fl, results)
    save_football_ledger(fl)
    sb = write_scoreboard(fl)
    return {"teamsRated": len(elo), "opened": opened, "resolved": resolved,
            "voided": voided, "confidence": sb["confidence"]}
