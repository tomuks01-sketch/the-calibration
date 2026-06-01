# The Calibration — Signal Spec (P0.5 · naming & schema freeze)

> This document is the **contract**. Every layer (crowd, qest, regime,
> repricing, composite) and every UI surface must obey the vocabulary,
> classifications, schemas, and rules below. It exists to stop the one
> failure that would kill this product: a user (or us) treating a
> documented *mixture of signals* as if it were settled truth.
>
> Status: FROZEN at v1 (§1–§8). v2 ADDS §9 (crypto 24h forecast `cfx`) without
> altering the v1 PM contract. Changes require a version bump + a note here.

---

## 1. Three signal classes (the core distinction)

Every signal in the system is exactly one of these. The class determines
whether it is allowed to influence an outcome probability.

| Class | Question it answers | May it enter an outcome probability? | Examples |
|---|---|---|---|
| **Descriptive** | "What is happening *right now*?" | **No. Never.** | trade velocity, volume z-score, spread, order-book imbalance, crypto funding/OI/basis as *regime context*, repricing pressure |
| **Probabilistic** | "How likely is this *outcome*, and we will be scored on it." | **Yes** — and it is falsifiable + logged in the ledger | crowd probability, QEST baseline, composite |
| **Adjustment candidate** | "Could this signal *eventually* justify moving a probability?" | **Not yet.** Shown separately, evaluated over time. | crypto regime → probability tilt (starts as candidate only) |

**Rule of separation:** "what moves now" (descriptive) and "what wins
eventually" (probabilistic) are different questions. They are never merged
into one number. A descriptive signal may *annotate* a market ("volume
spiking, spread widening") but may not *change* its outcome probability.

---

## 2. Frozen vocabulary

- **crowd** — the market's own implied probability of the outcome, from the
  Polymarket CLOB **midpoint** (not last trade). Class: *probabilistic*.
  Always shown with its **spread**; a wide spread means low confidence in
  the crowd number itself.
- **qest** — the transparent baseline model probability (`model.evaluate`,
  documented mean-reversion, `REVERSION=0.35`). NOT "AI", not an edge claim.
  Class: *probabilistic*. This is the number currently written to the
  ledger and Brier-scored.
- **gap** — `qest − crowd` (in pp). Descriptive of disagreement; it is *not*
  itself a probability.
- **composite** — a transparent, documented, **feature-weighted blend** of
  crowd + qest (+ later, calibrated adjustments) in log-odds space. Class:
  *probabilistic candidate*. See §4. Until calibrated it is labelled
  **"uncalibrated composite prior"** everywhere it appears.
- **pressure** (repricing pressure) — a *descriptive* read of present-tense
  conditions (sudden move, volume z, spread widening, pre-resolution vol).
  Class: *descriptive*. Answers "is this market moving / unsettled now",
  NOT "which way will it resolve".
- **regime** (crypto) — *descriptive* market-state context (momentum,
  funding, OI delta, basis). Class: *descriptive* by default. A separate,
  explicitly-flagged **regime adjustment candidate** may be computed but
  does NOT enter any probability in v1 (see §5).
- **confidence** — how much weight to put on a *probabilistic* number. For
  crowd: inverse of spread + liquidity. For qest/composite: derived ONLY
  from realised calibration (per-category Brier vs N). Until enough resolved
  outcomes exist, confidence for model numbers is **"not yet available"**,
  never a fabricated score. See §6.
- **coverage** — the fraction of intended input features that were actually
  `available` (real data) when a composite was computed. `coverage = 0.6`
  means 40% of inputs were missing and the blend renormalised over what
  remained. Coverage is a *data-completeness* metric, not a confidence in
  the outcome.
- **calibration** — backward-looking agreement between stated probabilities
  and realised outcomes (Brier, reliability). Requires resolved outcomes.

### Descriptive vs probabilistic — quick test
> If the number changes the answer to *"how likely is the outcome"*, it is
> **probabilistic** and must be falsifiable + logged. If it only describes
> *current observable conditions*, it is **descriptive** and must never
> touch a probability. When unsure, it is descriptive.

---

## 3. The admission rule (applies to the whole plan)

A new signal MAY NOT enter the **final scored number** (qest/composite that
gets logged) until it has ALL of:

1. **coverage** — a defined `available` flag and a measured coverage rate;
2. **source** — a named, reproducible data source (endpoint or derivation);
3. **timestamp** — the data's own freshness time, carried through to the UI;
4. **tests** — unit tests for its extraction + edge cases (missing, stale, malformed);
5. (for *probabilistic* admission) **calibration evidence** — it improved
   Brier on resolved outcomes, not just looked plausible.

Until 1–4 hold, a signal may be shown **descriptively** with a clear
`source` + `timestamp`, but is excluded from any probability. Until 5 holds,
it stays an *adjustment candidate*, shown side-by-side, never folded in.

---

## 4. Composite — labelling rule (non-negotiable)

- The composite is computed in **log-odds space, anchored on crowd**:
  `logit(composite) = logit(crowd) + Σ weight·tilt` (tilts bounded, weights
  documented in `weights.json`).
- While `weightsCalibrated == false` (i.e. weights are a fixed prior, not
  fitted from resolved outcomes), the composite is displayed **only** as:
  **"Composite · uncalibrated prior"** with a one-line note: *"a documented
  mixture of signals, not a validated forecast — weights not yet fitted to
  outcomes."*
- The composite **never visually outranks or replaces** the crowd and qest
  numbers while uncalibrated. It is shown *alongside*, never *instead*.
- The **scored ledger number stays `qest`** until the composite has its own
  resolved track record passing §6's gate. Only then may the composite be
  promoted to the logged number (with a `weightsVersion` bump; old calls
  keep their original version for audit).

---

## 5. Crypto regime — two explicit parts from day one

`regime` is split so the safe part ships first and the risky part stays
quarantined:

- **`regime.descriptive`** (ships in P3): momentum, funding z, basis z, OI
  delta as *context only*. Shown in the detail panel labelled "regime
  context — descriptive, does not move the probability".
- **`regime.adjustmentCandidate`** (P3 computes, but **inert**): a proposed
  probability tilt derived from regime. In v1 it is **stored and displayed
  for evaluation only**, with `applied: false`. It may not enter any
  composite until it passes §3.5 (calibration evidence on resolved
  outcomes). Funding/OI/basis being elevated does NOT, by itself, justify
  moving an outcome probability.

Liquidations are **out of scope** (no faithful keyless source). If ever
added, only as an explicitly-labelled proxy, never as "liquidations".

---

## 6. Calibration gate (honest until proven)

- All backward-looking stats (per-category Brier, reliability, model
  confidence, "signal quality from history") require resolved outcomes.
- **Gate:** below **N = 30** resolved outcomes overall, show
  **"Calibration: not yet available — N resolved needed"**. Per-category
  stats need ~30 *per category*. No number before the gate. (The ledger is
  currently ~10 pending / 0 resolved — so this reads "pending" for a while,
  and we say so openly.)
- Confidence bands use **Wilson intervals**; reliability uses standard
  calibration bins — but only once past the gate.

---

## 7. Frozen schemas

### `web/features.json` (`schemaVersion: "fs-v1"`)
```json
{
  "schemaVersion": "fs-v1",
  "weightsVersion": "w-v1",
  "generatedAt": "ISO-8601",
  "records": [{
    "assetId": "string",            // PM conditionId or crypto symbol
    "kind": "PM_BINARY|PM_MULTI|CRYPTO",
    "title": "string",
    "category": "string",
    "horizonDays": "number|null",   // days_to_close
    "crowd":     { "prob": "0..1|null", "spread": "number|null", "obImbalance": "-1..1|null",
                   "tradeVelocity": "number|null", "volumeChange": "number|null",
                   "source": "string", "timestamp": "ISO|null", "available": "bool" },
    "baseline":  { "prob": "0..1|null", "gapVsCrowd": "number|null",
                   "signalQuality": "insufficient|low|...", "source": "model.py",
                   "available": "bool" },
    "regime":    { "descriptive": { "spotMom": "n|null", "futMom": "n|null",
                                    "fundingZ": "n|null", "basisZ": "n|null", "oiDelta": "n|null",
                                    "source": "string", "timestamp": "ISO|null", "available": "bool" },
                   "adjustmentCandidate": { "tilt": "-1..1|null", "applied": false } },
    "pressure":  { "suddenMove": "bool", "overheated": "bool", "infoEventNear": "bool",
                   "preResolutionVol": "number|null", "class": "descriptive",
                   "source": "string", "timestamp": "ISO|null", "available": "bool" },
    "composite": { "prob": "0..1|null", "coverage": "0..1", "weightsCalibrated": false,
                   "label": "uncalibrated prior",
                   "contributions": { "baseline": "pp", "regime": "pp", "pressure": "pp" } }
  }]
}
```
> Every block carries `available`, `source`, `timestamp`. Missing data →
> `available:false` + nulls. Never invented.

### `web/weights.json` (`weightsVersion: "w-v1"`)
```json
{
  "weightsVersion": "w-v1",
  "calibrated": false,
  "note": "fixed documented prior; not fitted to outcomes",
  "weights": { "crowd": 0.7, "baseline": 0.2, "regimeAdjustment": 0.0 },
  "scales":  { "gap": 0.15, "fundingZ": 2.0 }
}
```
> `regimeAdjustment` weight is **0.0 in v1** — the candidate is computed but
> contributes nothing until calibrated.

### Ledger extension (append-only, back-compatible)
Existing entries unchanged. New **nullable** fields on new entries:
`compositeProbAtCallTime`, `weightsVersion`, `featuresSnapshotRef`
(`features-archive/YYYY-MM.json#assetId`), `contributions`. The **scored**
field stays `modelProb` (qest) until §4's promotion conditions are met.

---

## 8. What this freeze guarantees
- crowd, qest, composite, pressure, regime, confidence, coverage each mean
  exactly one thing, everywhere.
- descriptive signals can never silently become a forecast.
- the composite is honestly labelled a prior until outcomes prove it.
- no signal reaches the scored number without coverage + source + timestamp
  + tests (+ calibration to become probabilistic).
- the system is built to *become* good, not to pretend it already is.

---

## 9. Crypto 24h forecast — `cfx-v1` (v2 addition)

> v2 addition. v1 (§1–§8) is unchanged and still binding. v1 kept crypto
> **descriptive only** (§1/§5). v2 permits exactly ONE crypto *probabilistic*
> signal — `cfx` — because it is falsifiable and publicly scored exactly like
> a PM call. It does not touch the PM contract.

### What `cfx` outputs (and what it must NOT)
- **`probUp`** — probability the coin closes higher in ~24h. Deliberately
  **HUMBLE**: a small, damped momentum tilt clamped tight around 0.5. Scored
  by **Brier vs the 0.5 baseline** (and vs the unconditional up-rate). We
  expect ~coin-flip skill and the scoreboard says so openly.
- **`bandPct`** — an 80% magnitude band (±%) from realised daily volatility.
  A **volatility** forecast (genuinely forecastable), scored by **empirical
  coverage** (does the 80% band cover ~80%?) + pinball loss.
- **FORBIDDEN (RED LINE):** a point "expected % change" headline. It is
  provably worse than the random-walk baseline on MAE and reads as advice.

### Baseline (what we are scored against)
- direction → **random walk**: `probUp = 0.5` (and the unconditional up-rate).
- magnitude → **random walk**: expected change 0; the band is judged on coverage.
- The crypto scoreboard MUST publish skill-vs-baseline **including when it is
  ≤ 0** ("no better than assuming no change"). Never hidden, never reframed.

### Time-boxed resolution (crypto has no `endDate`)
- A forecast is **locked at open**: `openedAt`, `priceAtOpen` (+ source
  timestamp), `dueAt = openedAt + 24h`, `baseline=random_walk`, written to an
  append-only `crypto_ledger.json` **before** the window. At most **one
  forecast per (coin, UTC day)** — dedup key `sha1(symbol:utcdate)`.
- Auto-resolved when `dueAt <= now`: settled by the price at the first tick
  `>= dueAt` (within a max-staleness tolerance). Resolution code MUST assert
  the resolve price timestamp `>= dueAt` (no look-ahead). Past staleness → VOID.
- Append-only; `OPEN → RESOLVED|VOID` only; never deleted or reworded (same
  integrity as the PM ledger). One frozen reference source/field per coin;
  frozen versioned coin basket; gaps/delistings → **VOID, not silent drop**.

### Gate & honesty
- Same calibration gate (§6): below the N-gate the forecast is shown
  **descriptively** with "track record not yet meaningful (N=…)". Direction
  Brier needs a large **correlation-adjusted** N (majors are highly correlated,
  so effective N « coin-days); volatility coverage is meaningful far sooner.
- Per-coin skill claims require FDR correction; prefer **one aggregate skill
  number** with effective-N over 10 per-coin claims.
- `cfx` is NEVER framed as advice; the analytics-only disclaimer applies to
  every crypto-forecast surface.

### Schema — `web/crypto_ledger.json` (`schemaVersion: "cl-v1"`)
Entries (nullable until resolved): `forecastId`, `symbol`, `openedAt`,
`dueAt`, `priceAtOpen`, `probUp`, `sigmaPct`, `bandPct`, `baseline`,
`status` (OPEN|RESOLVED|VOID), `resolvedAt`, `priceAtResolve`,
`realizedChangePct`, `upHit`, `brierUp`, `bandCovered`, `voidReason`.
