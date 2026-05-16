"""Append-only public prediction ledger + auto Brier scoring.

Integrity rules (from team review — these are honored in code, not comments):
- Append-only: entries are never deleted; only PENDING -> RESOLVED/VOID.
- Dedup: at most ONE entry per conditionId, ever (markets resolve once).
- Resolution ONLY on terminal API outcome {0,1}; 0.5/disputed/non-terminal
  -> VOID and excluded from all aggregates. endDate passing is NOT a trigger.
- Score model AND crowd on the SAME call-time probabilities (no flattering).
- Selection caveat is stamped into the file (top-snapshot scope is not random).
- Atomic write + JSON validation; monthly archive shard for reconstructability.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from model import MODEL_VERSION

LEDGER = Path(__file__).resolve().parent.parent / "web" / "ledger.json"
ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "web" / "ledger-archive"
GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"
REQUEST_TIMEOUT_S = 20

STALE_VOID_DAYS = 90  # unresolved this long after open -> VOID (cannot rot)
SAMPLE_NOTE = (
    "Snapshot-scoped: calls are logged only for markets present in the "
    "top-volume snapshot at call time. This is NOT a random sample of all "
    "Polymarket markets; the Brier figures are 'snapshot-scoped' and must be "
    "read with that selection caveat."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcdate(iso: str) -> str:
    return iso[:10]


def _days_since(iso: str) -> float:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return (datetime.now(timezone.utc) - t).total_seconds() / 86400.0


def load_ledger() -> dict:
    if not LEDGER.exists():
        return {"version": 1, "modelVersion": MODEL_VERSION,
                "sampleNote": SAMPLE_NOTE, "entries": []}
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "entries" not in data:
            raise ValueError("bad ledger shape")
        return data
    except (ValueError, OSError):
        # Never silently start a fresh ledger over a corrupt one — fail loud.
        raise SystemExit(
            "FATAL: web/ledger.json is unreadable/corrupt. Refusing to "
            "overwrite history. Restore from web/ledger-archive/."
        )


def save_ledger(ledger: dict) -> None:
    ledger["sampleNote"] = SAMPLE_NOTE
    ledger["modelVersion"] = MODEL_VERSION
    text = json.dumps(ledger, indent=2)
    json.loads(text)  # validate before any write
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(LEDGER)
    # Monthly archive shard (reconstructability)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    shard = ARCHIVE_DIR / f"{_now()[:7]}.json"
    shard.write_text(text, encoding="utf-8")


def _existing_condition_ids(ledger: dict) -> set[str]:
    return {e["conditionId"] for e in ledger["entries"] if e.get("conditionId")}


def open_calls(ledger: dict, candidates: list[dict]) -> int:
    """candidates: dicts with conditionId, marketId, question, eventSlug,
    eventTitle, category, modelProb, marketProb, divergence. Dedup by
    conditionId (one entry per market, ever)."""
    seen = _existing_condition_ids(ledger)
    opened = 0
    for c in candidates:
        cid = c.get("conditionId")
        if not cid or cid in seen:
            continue
        opened_at = _now()
        call_id = hashlib.sha1(
            f"{cid}:{_utcdate(opened_at)}".encode()
        ).hexdigest()[:16]
        ledger["entries"].append(
            {
                "callId": call_id,
                "conditionId": cid,
                "marketId": c.get("marketId", ""),
                "eventSlug": c.get("eventSlug", ""),
                "eventTitle": c.get("eventTitle", ""),
                "category": c.get("category", ""),
                "question": c.get("question", ""),
                "modelVersion": MODEL_VERSION,
                "modelProb": c["modelProb"],
                "crowdProbAtCallTime": c["marketProb"],
                "divergencePp": round(c["divergence"] * 100, 1),
                "openedAt": opened_at,
                "status": "PENDING",
                "resolvedAt": None,
                "resolvedOutcome": None,
                "modelBrier": None,
                "marketBrier": None,
                "voidReason": None,
            }
        )
        seen.add(cid)
        opened += 1
    return opened


def _get(url: str) -> list:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "pmi/0.1"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d if isinstance(d, list) else [d]


def _terminal_outcome(market: dict) -> int | None:
    """Return 1/0 only for a genuinely resolved binary market, else None."""
    if not market.get("closed"):
        return None
    raw = market.get("outcomePrices")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list) or not raw:
        return None
    try:
        yes = float(raw[0])
    except (TypeError, ValueError):
        return None
    if yes >= 0.99:
        return 1
    if yes <= 0.01:
        return 0
    return None  # 0.5 / disputed / non-terminal -> caller VOIDs


def resolve_pending(ledger: dict) -> tuple[int, int]:
    pend = [e for e in ledger["entries"] if e["status"] == "PENDING"]
    if not pend:
        return (0, 0)
    by_cid = {e["conditionId"]: e for e in pend}
    resolved = voided = 0
    ids = list(by_cid)
    for i in range(0, len(ids), 15):
        batch = ids[i : i + 15]
        try:
            mkts = _get(f"{GAMMA_MARKETS}?condition_ids={','.join(batch)}")
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue  # transient: stays PENDING, retried next run
        seen_cids = set()
        for m in mkts:
            cid = str(m.get("conditionId") or "")
            e = by_cid.get(cid)
            if not e:
                continue
            seen_cids.add(cid)
            outcome = _terminal_outcome(m)
            if m.get("closed") and outcome is None:
                e.update(status="VOID", voidReason="non-terminal/disputed",
                         resolvedAt=_now())
                voided += 1
            elif outcome is not None:
                mp, cp = e["modelProb"], e["crowdProbAtCallTime"]
                e.update(
                    status="RESOLVED",
                    resolvedOutcome=outcome,
                    resolvedAt=_now(),
                    modelBrier=round((mp - outcome) ** 2, 6),
                    marketBrier=round((cp - outcome) ** 2, 6),
                )
                resolved += 1
        # Entries whose id vanished from the API and are very old -> VOID
        for cid in batch:
            if cid in seen_cids:
                continue
            e = by_cid[cid]
            if _days_since(e["openedAt"]) >= STALE_VOID_DAYS:
                e.update(status="VOID", voidReason="unresolvable/stale",
                         resolvedAt=_now())
                voided += 1
    return (resolved, voided)
