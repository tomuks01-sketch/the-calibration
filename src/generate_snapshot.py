"""Generate web/data.json: category-balanced events + outcomes + movers + news.

Read-only. Switches from the markets endpoint to the EVENTS endpoint so
near-duplicate markets (e.g. one per World Cup country) collapse into a single
event card, and a round-robin across category tags guarantees the default
board is not dominated by one topic (football).

Analytics only — observable market state, never predictions or betting advice.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fetch_markets import (
    build_event_group,
    fetch_active_events,
    is_binary,
)
from crypto import build_cross_signals, fetch_macro, fetch_top_coins
from kalshi import fetch_kalshi_macro
from ledger import load_ledger, open_calls, resolve_pending, save_ledger
from context import STATS as CONTEXT_STATS
from context import build_context, llm_enabled
from model import MODEL_VERSION, evaluate
from news import fetch_headlines, topic_from_question
from price_history import fetch_price_move, move_flags, parse_token_ids
from scoreboard import write as write_scoreboard

OUTPUT = Path(__file__).resolve().parent.parent / "web" / "data.json"

TARGET_EVENTS = 24
MAX_EVENTS_PER_CATEGORY = 4          # hard cap so no topic dominates
MIN_EVENT_VOLUME = 50_000
MAX_OUTCOMES = 8                     # bars shown per multi-outcome event
NEWS_FOR_TOP = 10                    # news only for the highest-volume events
MOVE_WEEK_THRESHOLD = 0.05           # |1w price change| to count as a mover


def _coerce_float(v: object) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def outcome_label(market: dict) -> str:
    """Prefer the clean group label ('Spain') over the full question."""
    g = (market.get("groupItemTitle") or "").strip()
    if g:
        return g[:48]
    return str(market.get("question") or "")[:60]


def yes_price(market: dict) -> float | None:
    from fetch_markets import _parse_first_price  # reuse robust parser

    return _parse_first_price(market.get("outcomePrices"))


def summarize_event_outcomes(group) -> list[dict]:
    rows = []
    for m in group.markets:
        p = yes_price(m)
        if p is None:
            continue
        rows.append(
            {
                "label": outcome_label(m),
                "price": round(p, 4),
                "weekChange": round(_coerce_float(m.get("oneWeekPriceChange")), 4),
                "conditionId": str(m.get("conditionId") or ""),
                "marketId": str(m.get("id") or ""),
                "question": str(m.get("question") or "")[:140],
                "liquidity": _coerce_float(m.get("liquidity")),
                "volume": _coerce_float(m.get("volume")),
            }
        )
    rows.sort(key=lambda r: r["price"], reverse=True)
    return rows


def pick_movers(outcomes: list[dict]) -> list[dict]:
    movers = [o for o in outcomes if abs(o["weekChange"]) >= MOVE_WEEK_THRESHOLD]
    movers.sort(key=lambda o: abs(o["weekChange"]), reverse=True)
    return movers[:3]


def representative_market(group) -> dict | None:
    """Highest-volume market in the event (the card's price anchor)."""
    ranked = sorted(
        group.markets, key=lambda m: _coerce_float(m.get("volume")), reverse=True
    )
    return ranked[0] if ranked else None


def select_balanced(groups: list) -> list:
    """Round-robin across categories, capped per category."""
    buckets: dict[str, list] = {}
    for g in groups:
        buckets.setdefault(g.category, []).append(g)
    for cat in buckets:
        buckets[cat].sort(key=lambda g: g.volume_24h or g.volume, reverse=True)

    ordered_cats = sorted(
        buckets, key=lambda c: buckets[c][0].volume, reverse=True
    )
    taken: dict[str, int] = {c: 0 for c in ordered_cats}
    selected: list = []
    progress = True
    while len(selected) < TARGET_EVENTS and progress:
        progress = False
        for cat in ordered_cats:
            if len(selected) >= TARGET_EVENTS:
                break
            if taken[cat] >= MAX_EVENTS_PER_CATEGORY:
                continue
            idx = taken[cat]
            if idx < len(buckets[cat]):
                selected.append(buckets[cat][idx])
                taken[cat] += 1
                progress = True
    return selected


def main() -> None:
    raw_events = fetch_active_events(limit=140)
    groups = [
        g
        for g in (build_event_group(e) for e in raw_events)
        if g and g.volume >= MIN_EVENT_VOLUME
    ]
    selected = select_balanced(groups)
    _LLM = llm_enabled()  # True only if LLM_API_KEY secret is set (card-free Groq/etc.)

    events_out = []
    for i, g in enumerate(selected):
        outcomes = summarize_event_outcomes(g)
        movers = pick_movers(outcomes)
        binary = g.market_count == 1 and outcomes and is_binary(g.markets[0])

        lead_price = outcomes[0]["price"] if outcomes else None
        change_1h = change_24h = None
        price_unavailable = False
        flags: list[str] = []
        rep = representative_market(g)
        if rep is not None:
            token_ids = parse_token_ids(rep.get("clobTokenIds"))
            if token_ids:
                mv = fetch_price_move(token_ids[0])
                change_1h, change_24h = mv.change_1h, mv.change_24h
                price_unavailable = mv.points == 0
                flags.extend(move_flags(mv))
                time.sleep(0.3)

        if g.volume > 1_000_000:
            flags.append("high-attention")
        if g.days_to_resolution is not None and 0 <= g.days_to_resolution <= 3:
            flags.append("resolves-soon")
        if movers and "moving-now" not in flags:
            flags.append("moving-now")
        if price_unavailable:
            flags.append("price-data-unavailable")

        news = []
        context = None
        if i < NEWS_FOR_TOP:
            for h in fetch_headlines(topic_from_question(g.title), limit=4):
                news.append(
                    {"title": h.title, "source": h.source, "link": h.link}
                )
            time.sleep(0.4)
            # Subordinate, fail-open. Tier B (Gemini) only on the top 6 events
            # and only if LLM_API_KEY secret exists; else keyless Tier A.
            context = build_context(g.title, news, use_llm=_LLM and i < 3)

        events_out.append(
            {
                "id": g.event_id,
                "title": g.title,
                "slug": g.slug,
                "category": g.category,
                "tags": list(g.tags),
                "volume": g.volume,
                "volume24h": g.volume_24h,
                "liquidity": g.liquidity,
                "daysToResolution": g.days_to_resolution,
                "marketCount": g.market_count,
                "binary": bool(binary),
                "leadPrice": lead_price,
                "change1h": change_1h,
                "change24h": change_24h,
                "outcomes": outcomes[:MAX_OUTCOMES],
                "movers": movers,
                "flags": flags,
                "news": news,
                "context": context,
            }
        )

    # Subordinate macro-context layer (2 read-only calls, end of run, never
    # blocks the prediction-market board; degrades silently to available=False).
    time.sleep(0.5)
    macro = fetch_macro()
    macro_block = {
        "available": macro.available,
        "regime": macro.regime,
        "btcUsd": macro.btc_usd,
        "ethUsd": macro.eth_usd,
        "btcChange24h": macro.btc_change_24h,
        "ethChange24h": macro.eth_change_24h,
        "totalMcapUsd": macro.total_mcap_usd,
        "totalMcapChange24h": macro.total_mcap_change_24h,
        "btcDominance": macro.btc_dominance,
        "topCoins": fetch_top_coins(),
        "crossSignals": build_cross_signals(macro, events_out),
    }

    # ---- Model + append-only public ledger + scoreboard ----
    # Done BEFORE writing data.json so each event can carry the model number
    # ONLY when it corresponds to a real (open/scored) ledger entry — never an
    # unfalsifiable public claim. Skeptic guardrail: terminal model display is
    # strictly a mirror of the ledger.
    candidates = []
    for e in events_out:
        outs = e.get("outcomes") or []
        if not outs:
            continue
        lead = outs[0]
        mc = evaluate(
            market_prob=lead.get("price"),
            week_change=lead.get("weekChange"),
            liquidity=lead.get("liquidity"),
            days_to_resolution=e.get("daysToResolution"),
            condition_id=lead.get("conditionId"),
        )
        if mc.is_call:
            candidates.append(
                {
                    "conditionId": lead["conditionId"],
                    "marketId": lead.get("marketId", ""),
                    "eventSlug": e.get("slug", ""),
                    "eventTitle": e.get("title", ""),
                    "category": e.get("category", ""),
                    "question": lead.get("question") or e.get("title", ""),
                    "modelProb": mc.model_prob,
                    "marketProb": mc.market_prob,
                    "divergence": mc.divergence,
                }
            )

    ledger = load_ledger()
    opened = open_calls(ledger, candidates)
    resolved, voided = resolve_pending(ledger)
    save_ledger(ledger)
    sb = write_scoreboard(ledger)

    # Attach QEST to every ELIGIBLE market for visibility. Two honest states:
    #  - tracked=True : |div|>=4pp, a real divergence call in the public ledger
    #    (falsifiable + Brier-scored).
    #  - tracked=False: model agrees with the crowd (<4pp); shown transparently
    #    as "in line, not a tracked call, no edge claimed" — NOT a ledger entry
    #    (skeptic guardrail: never pad the scored ledger with agreement calls).
    by_cid = {e["conditionId"]: e for e in ledger["entries"] if e.get("conditionId")}
    annotated = 0
    for ev in events_out:
        outs = ev.get("outcomes") or []
        if not outs:
            continue
        lead = outs[0]
        mc = evaluate(
            market_prob=lead.get("price"),
            week_change=lead.get("weekChange"),
            liquidity=lead.get("liquidity"),
            days_to_resolution=ev.get("daysToResolution"),
            condition_id=lead.get("conditionId"),
        )
        if not mc.eligible:
            continue
        entry = by_cid.get(lead.get("conditionId"))
        ev["model"] = {
            "name": "QEST",
            "version": MODEL_VERSION,
            "prob": mc.model_prob,
            "divergencePp": round((mc.divergence or 0) * 100, 1),
            "tracked": bool(entry),
            "status": entry["status"] if entry else None,
        }
        annotated += 1

    categories = sorted({e["category"] for e in events_out})
    snapshot = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Analytics only. Observable market state + news context. "
            "Not predictions, not betting advice. No wallet access."
        ),
        "categories": categories,
        "eventCount": len(events_out),
        "events": events_out,
        "macro": macro_block,
        "kalshi": fetch_kalshi_macro(),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(
        f"Wrote {OUTPUT} ({len(events_out)} events, "
        f"{len(categories)} categories) | Ledger: +{opened} opened, "
        f"{resolved} resolved, {voided} void | {annotated} events show QEST "
        f"({len(ledger['entries'])} tracked in ledger) | "
        f"scoreboard confidence={sb['confidence']}"
    )
    ctx_diag = {k: v for k, v in CONTEXT_STATS.items() if v}
    print(f"Context Tier-B diagnostics (keyless, no content): {ctx_diag}")


if __name__ == "__main__":
    main()
