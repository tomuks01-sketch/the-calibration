"""Append-only international-football forecast ledger + auto-scoring (fl-v1).

A football match is the cleanest scorable event: lock our W/D/L probabilities
(and the market's, from ESPN odds) BEFORE kickoff, then settle on the final
score. Scored with RPS (Ranked Probability Score) — the football standard for
3 ordered outcomes [home, draw, away] — against the result AND against the
market, so any edge over the crowd is proven, never claimed.

Integrity, mirroring the crypto ledger:
- Append-only; one entry per matchId, ever; OPEN -> RESOLVED|VOID only.
- Locked pre-kickoff (forecast + market probs frozen); resolved on the final
  score; no result long after kickoff -> VOID (never rots, never invented).
- Atomic write + monthly archive + fail-open-not-job-kill on corrupt.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

FOOTBALL_LEDGER = Path(__file__).resolve().parent.parent / "web" / "football_ledger.json"
ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "web" / "football-ledger-archive"
SCHEMA_VERSION = "fl-v1"
STALE_VOID_DAYS = 7        # no final score this long after kickoff -> VOID

DISCLAIMER = (
    "International-football forecasts (W/D/L + scoreline), scored with RPS vs the "
    "result AND vs the market's implied probabilities. Analytics only — not "
    "betting advice. Append-only: forecasts are locked before kickoff, never edited."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def load_football_ledger() -> dict:
    if not FOOTBALL_LEDGER.exists():
        return {"schemaVersion": SCHEMA_VERSION, "disclaimer": DISCLAIMER, "entries": []}
    try:
        data = json.loads(FOOTBALL_LEDGER.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "entries" not in data:
            raise ValueError("bad football-ledger shape")
        return data
    except (ValueError, OSError) as exc:
        raise RuntimeError(
            "web/football_ledger.json is unreadable/corrupt; skipping football "
            "this run (file left intact for inspection)."
        ) from exc


def save_football_ledger(cl: dict) -> None:
    cl["schemaVersion"] = SCHEMA_VERSION
    cl["disclaimer"] = DISCLAIMER
    text = json.dumps(cl, indent=2)
    json.loads(text)  # validate before any write
    FOOTBALL_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = FOOTBALL_LEDGER.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(FOOTBALL_LEDGER)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ARCHIVE_DIR / f"{_now()[:7]}.json").write_text(text, encoding="utf-8")


def rps(probs: list[float], outcome: list[float]) -> float:
    """Ranked Probability Score over ordered outcomes [home, draw, away].
    RPS = 1/(r-1) * sum_i (cumP_i - cumO_i)^2. Lower is better; order-aware
    (a 'home' call that ends a draw is penalised less than one that ends away)."""
    cum_p = cum_o = total = 0.0
    for i in range(len(probs) - 1):
        cum_p += probs[i]
        cum_o += outcome[i]
        total += (cum_p - cum_o) ** 2
    return round(total / (len(probs) - 1), 6)


def _has_probs(f: dict) -> bool:
    return all(isinstance(f.get(k), (int, float))
               for k in ("probHome", "probDraw", "probAway"))


def _market_probs(f: dict) -> list[float] | None:
    ks = ("marketProbHome", "marketProbDraw", "marketProbAway")
    if all(isinstance(f.get(k), (int, float)) for k in ks):
        return [f[k] for k in ks]
    return None


def open_matches(cl: dict, fixtures: list[dict], now: str | None = None) -> int:
    """Lock a forecast for each upcoming match not already in the ledger. A
    fixture needs a matchId and our three W/D/L probs; market probs are optional.
    Returns count opened."""
    now = now or _now()
    seen = {e.get("matchId") for e in cl["entries"] if e.get("matchId")}
    opened = 0
    for f in fixtures:
        mid = f.get("matchId")
        if not mid or mid in seen or not _has_probs(f):
            continue
        cl["entries"].append({
            "matchId": mid,
            "competition": f.get("competition", ""),
            "kickoff": f.get("kickoff", now),
            "home": f.get("home", ""),
            "away": f.get("away", ""),
            "openedAt": now,
            "probHome": f["probHome"], "probDraw": f["probDraw"], "probAway": f["probAway"],
            "expGoalsHome": f.get("expGoalsHome"), "expGoalsAway": f.get("expGoalsAway"),
            "topScorelines": f.get("topScorelines", []),
            "markets": f.get("markets", {}),
            "marketProbHome": f.get("marketProbHome"),
            "marketProbDraw": f.get("marketProbDraw"),
            "marketProbAway": f.get("marketProbAway"),
            "eloHome": f.get("eloHome"), "eloAway": f.get("eloAway"),
            "why": f.get("why", []),
            "status": "OPEN",
            "resolvedAt": None, "finalScore": None, "outcome": None,
            "rpsModel": None, "rpsMarket": None, "beatMarket": None, "voidReason": None,
        })
        seen.add(mid)
        opened += 1
    return opened


def resolve_matches(cl: dict, results: dict[str, dict], now: str | None = None) -> tuple[int, int]:
    """Settle OPEN matches. `results` maps matchId -> {"homeScore": int,
    "awayScore": int}. Missing result + kickoff older than STALE_VOID_DAYS ->
    VOID. Returns (resolved, voided)."""
    now = now or _now()
    now_dt = _parse(now)
    resolved = voided = 0
    for e in cl["entries"]:
        if e.get("status") != "OPEN":
            continue
        res = results.get(e["matchId"])
        if not res or not isinstance(res.get("homeScore"), int) or not isinstance(res.get("awayScore"), int):
            if (now_dt - _parse(e.get("kickoff") or e["openedAt"])).total_seconds() >= STALE_VOID_DAYS * 86400:
                e.update(status="VOID", voidReason="no final score (stale)", resolvedAt=now)
                voided += 1
            continue
        h, a = res["homeScore"], res["awayScore"]
        outcome = [1.0, 0.0, 0.0] if h > a else [0.0, 1.0, 0.0] if h == a else [0.0, 0.0, 1.0]
        label = "home" if h > a else "draw" if h == a else "away"
        model_probs = [e["probHome"], e["probDraw"], e["probAway"]]
        rps_model = rps(model_probs, outcome)
        mk = _market_probs(e)
        rps_market = rps(mk, outcome) if mk else None
        e.update(
            status="RESOLVED", resolvedAt=now,
            finalScore=f"{h}-{a}", outcome=label,
            rpsModel=rps_model, rpsMarket=rps_market,
            beatMarket=(rps_model <= rps_market) if rps_market is not None else None,
        )
        resolved += 1
    return (resolved, voided)
