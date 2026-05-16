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

## Optional: AI context (card-free, free tier)

Per-market context works with zero setup using keyless Google News (Tier A).
To upgrade to AI-summarised sourced context (Tier B), add a free,
**no-credit-card** API key (OpenAI-compatible). Recommended: **Groq**.

1. Sign up free at console.groq.com (no credit card) → create an API key.
   (Or any OpenAI-compatible card-free provider, e.g. openrouter.ai.)
2. GitHub repo → Settings → Secrets and variables → Actions → New repository
   secret. Name it exactly `LLM_API_KEY`, paste the key, save.
3. (Only if NOT using Groq) add repo *Variables* `LLM_API_BASE` and
   `LLM_MODEL` for your provider. Groq needs neither.
4. Done. The 30-min workflow auto-detects it next run (top 3 events,
   spaced, stops on rate-limit). No key = stays on Tier A silently.

AI context is always a sourced, qualitative summary — never a probability,
verdict or forecast (those are rejected and fall back to Tier A).

## Signals (descriptive, not advice)

- `extreme-price` — market priced near 0 or 1 (treated as near-certain)
- `thin-liquidity` — low liquidity, wide spread, hard to enter/exit
- `resolves-soon` — resolves within 3 days
- `high-attention` — volume over $100k

## Roadmap

See [PLAN.md](PLAN.md). Phase 0 (data) and Phase 1 (news + dashboard) done.
Next: price-history moves, alerts, paid tier, distribution.
