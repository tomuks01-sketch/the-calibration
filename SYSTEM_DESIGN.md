# The Calibration — System Design

> Reference for the public forecasting + calibration system. Grounded in the
> code that exists (`SIGNAL_SPEC.md`, `src/ledger.py`, `src/crypto_ledger.py`,
> `src/scoreboard.py`, `src/crypto_scoreboard.py`, `src/composite.py`,
> `src/model.py`, `src/crypto_forecast.py`). Goal: provably calibrated +
> auditable, not "beats the market". Honesty over hype.

## 1 · Architecture — five layers, one direction (raw → published)
- **L0 Ingestion** — raw API pulls (Polymarket Gamma/CLOB, Yahoo, CoinGecko, Binance) + fetch timestamp. No transforms.
- **L1 Normalized facts** — one clean record/asset/snapshot (crowd prob = CLOB midpoint, spread, volume, prevClose). → `web/features.json`.
- **L2 Model signal** — our estimates computed FROM L1 ONLY (QEST, cfx probUp, vol band, composite), tagged `modelVersion`/`weightsVersion`.
- **L3 Forecast ledger** — locked, append-only entries with a resolution rule. → `ledger.py`, `crypto_ledger.py`.
- **L4 Evaluation** — scoring after resolution + calibration + signal attribution. → `scoreboard.py`, `crypto_scoreboard.py`.
- **L5 Published** — briefs + UI, rendered ONLY from L3/L4. **Invariant: L5 may never state a number that isn't in L3/L4.**

**Signal classes (SIGNAL_SPEC §1) — keep enforced in code:** descriptive (never enters a probability) · probabilistic (scored, logged) · adjustment-candidate (inert until proven).

## 2 · Forecasting framework
- **Don't anchor on the crowd before earned.** First independent model = a **1-parameter recalibration** of the crowd, fitted only at N≥~30/category — NOT a multi-signal blend (overfits at low N). Until then QEST = crowd passthrough, said openly.
- **Forecast what's forecastable.** Live proof: 24h direction skill ≈ 0; the **volatility band is calibrated** (81.6% vs 80%). Lead with the band.
- **Baselines, always published:** direction → always-0.5 (Brier 0.25) + base rate; PM → the crowd (scored on same call-time prob); range → naive EWMA-vol band (pinball).
- **Which signals matter** (needs N≥~50): ablation (Brier with/without each), holdout or FDR correction, prefer one aggregate over per-signal cherry-picks. Until then signals stay descriptive.

## 3 · Scoring & evaluation
| Dimension | Metric | Baseline |
|---|---|---|
| Direction | Brier, accuracy, **calibration error** | 0.5 / base rate |
| Calibration | reliability bins | diagonal |
| Range | **coverage + pinball** | EWMA band |
| Timing | in-window hit-rate (`timingHit`) | — |
| Confidence | Wilson interval | — |
- **Score direction / range / timing separately** — never blend.
- **Unresolved:** N-gates (none<10, low<30, ok≥30); VOID (not guess) on non-terminal/stale; show pending honestly.
- **Auditable:** append-only + monthly archive + atomic write + fail-loud on corrupt; lock price+timestamp BEFORE the window; resolution asserts `resolveTime ≥ dueAt` (no look-ahead); selection caveat stamped in file; every published number traceable to a ledger entry (`featuresSnapshotRef`).

## 4 · Content (briefs)
- Generated ONLY from L3/L4 JSON; template-driven (see `BRIEF_007_TEMPLATE.md`).
- Three registers, visibly distinct: **fact** (L4) · **estimate** (L3, model, labeled unproven) · **opinion** (descriptive context, never scored).
- House style: measured, no hype; banned words (guaranteed/edge/beat the market/any unscored %); **lead with the unflattering fact** (#007 = the model).
- Pre-publish honesty pass: every number traces to a field.

## 5 · Implementation
- **Build first:** pinball + calibration-error (done) → reliability plot (done) → PM `timingHit` → ablation harness (report-only).
- **Automate (cron, fail-open):** ingest→normalize→model→open/resolve→score→aggregate→publish. Weights stay frozen until a deliberate N≥30 promotion.
- **Keep manual:** promoting weights, publishing briefs (draft auto / human approves), adding cross-venue or new-signal pairings (human-verified allowlist).

## 6 · 30-day roadmap
- D1–5: pinball + calibration-error (✅) + PM `timingHit` schema.
- D6–12: render reliability + coverage-over-time + "band vs EWMA" comparison.
- D13–20: ablation harness (reports "insufficient N" for weeks — correct).
- D21–26: email capture (the real bottleneck) + brief cadence off real numbers.
- D27–30: spec the 1-parameter crowd recalibration (do NOT fit yet).

## 7 · Storage note
At current scale, **append-only JSON + monthly archives is the right call** — simpler and auditable. A DB earns its place only past ~100k rows or cross-cutting queries; if so, **SQLite first** (tables: snapshots, assets, observations, model_signals, forecasts, resolutions, weights), not Postgres.

## Frozen scoring contract (cs-v1 + cl-v1)
- Direction: `skillVsRandomWalk = 0.25 − meanBrierUp`; `calibrationError` = count-weighted mean |predicted − actual| over reliability bins; `calibrationBins` predicted-vs-actual.
- Band: `coverageRate` vs 0.80 target; `pinball` = mean quantile loss treating ±bandPct as P10/P90 (rewards tight-and-covering, penalises over-wide).
- All N-gated; negatives/weaknesses published, never hidden.
