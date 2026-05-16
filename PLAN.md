# The Calibration — Build Plan

## Honest framing

This is a **read-only analytics product to sell**, not a betting engine and not
a profit guarantee. It surfaces observable market state (price, volume,
liquidity, time-to-resolution, news context) so traders decide faster. We never
touch wallets, private keys, or order placement. We never claim it predicts
winners.

Why this and not a "what to bet" bot: that niche on GitHub is scam/malware. A
clean analytics SaaS is a legitimate, sellable asset with non-random income.

## Product

A web dashboard + alerts for the prediction-market trader community.
Sellable as a low-priced subscription or one-time tool.

## Phases

### Phase 0 — Data layer (DONE)
- `src/fetch_markets.py`: pulls active markets from official Gamma API
  (read-only), computes honest flags: extreme-price, thin-liquidity,
  resolves-soon, high-attention. Verified working.

### Phase 1 — Signal engine (next)
- Add price-history fetch (CLOB/timeseries) → detect price moves over 1h/24h.
- Add news layer: pull headlines for a market's topic, attach recency/volume.
- Output a ranked "watchlist" with reasons (still descriptive, not advice).

### Phase 2 — Web dashboard
- Next.js front end: searchable market table, filters, signal badges, a market
  detail view with price chart + linked news.
- Static-first, cheap hosting (Vercel free tier). £30 covers a domain.

### Phase 3 — Productize & sell
- Free tier (delayed data) + paid tier (live signals, alerts, watchlists).
- Distribution: prediction-market subreddits/X/Discord communities, a public
  read-only demo, content posts dissecting markets.

## Guardrails
- No wallet/key integration. No auto-trading. No "guaranteed profit" copy.
- All claims must match what the data actually shows.
- Follow the ECC /pipeline workflow (tests, review, security) for each phase.

## Status (2026-05-15)
Phase 0 + Phase 1 complete:
- Read-only Gamma API data layer + honest signal flags (working).
- Keyless Google News RSS layer per market topic (working).
- `generate_snapshot.py` builds `web/data.json` (20 markets, ~32 headlines).
- Static English dashboard (`web/`) — intentional dark terminal design,
  signal filters, inline news, mobile + reduced-motion support.

Phase 2 (partial) complete:
- `src/price_history.py`: read-only CLOB price history → 1h/24h deltas +
  flags (big-move-24h, big-drop-24h, moving-now). Verified working.
- Snapshot + dashboard show Δ1h / Δ24h with semantic up/down colors and a
  move badge; new filter chips. News href sanitized (XSS hardening).
- `.github/workflows/refresh.yml`: scheduled (every 30 min) + manual
  regeneration, commits web/data.json when changed — runs once pushed to
  GitHub.

Phase 2 (diversification) complete — multi-agent designed (architect +
product + skeptic converged):
- Switched markets → events endpoint; near-duplicate markets collapse to one
  event card. Round-robin across category tags (max 4/category, 24 events,
  min $50k vol) → 24 categories instead of football-only.
- Per event: outcome bars (label + % + 1w trend), mover promotion via
  oneWeekPriceChange (no extra API calls), CLOB 24h delta on representative.
- Multi-outcome guard: odds only shown for true binary events (honesty).
- Dashboard rebuilt: KPI strip, dynamic category chips + signal chips,
  event cards with outcome bars, movers highlight, lead-with-delta.

Next: alerts, free vs paid tier, deploy (GitHub Pages) + public demo,
distribution. Open: user's willingness to do audience outreach; repo not yet
pushed to a GitHub remote.
