# The Calibration

Read-only analytics terminal for Polymarket: price / volume / liquidity signals
and the news driving each market. **Analytics, not predictions or betting
advice. No wallet, no keys, no order placement.**

## Run locally

```bash
# 1. Generate a fresh data snapshot (markets + signals + news)
python src/generate_snapshot.py

# 2. Serve the dashboard (fetch() needs http, not file://)
cd web && python -m http.server 8000
# open http://localhost:8000
```

## Layout

| Path | Role |
|------|------|
| `src/fetch_markets.py` | Official Gamma API (read-only) + honest signal flags |
| `src/news.py` | Keyless Google News RSS headlines per market topic |
| `src/generate_snapshot.py` | Builds `web/data.json` |
| `web/` | Static dashboard (no build step — free GitHub Pages / Vercel) |

## Signals (descriptive, not advice)

- `extreme-price` — market priced near 0 or 1 (treated as near-certain)
- `thin-liquidity` — low liquidity, wide spread, hard to enter/exit
- `resolves-soon` — resolves within 3 days
- `high-attention` — volume over $100k

## Roadmap

See [PLAN.md](PLAN.md). Phase 0 (data) and Phase 1 (news + dashboard) done.
Next: price-history moves, alerts, paid tier, distribution.
