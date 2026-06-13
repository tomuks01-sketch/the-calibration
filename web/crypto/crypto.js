"use strict";
/* The Calibration — Crypto Pulse (honest descriptive analytics).
 *
 * HARD RULE: this dashboard NEVER shows a FABRICATED or unfalsifiable number.
 * The descriptive signals DESCRIBE observable data (price changes, volume,
 * volatility). The 24h forecast (probUp + volatility band, SIGNAL_SPEC §9) IS
 * shown — but ONLY because every forecast is logged at the time it's made and
 * automatically scored 24h later vs a random-walk baseline (web/crypto_ledger
 * .json + crypto_scoreboard.json). It is always labelled unproven, never a
 * point "% change", never advice or an edge claim.
 *
 * Data: CoinGecko public API (keyless, CORS-ok), with a committed snapshot
 * (markets.json) as an offline / rate-limit fallback. Swapping in another
 * data source later = change ENDPOINT + normalise() only.
 *
 * Normalised coin shape (the contract the UI renders):
 *   { rank, id, symbol, name, image, price, mcap, volume,
 *     c24, c7, c30,           // % changes
 *     spark: number[],        // 7d price series
 *     stable: boolean }
 */

const ENDPOINT =
  "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd" +
  "&order=market_cap_desc&per_page=10&page=1&sparkline=true" +
  "&price_change_percentage=24h,7d,30d";
const FALLBACK = "./markets.json";
const STABLES = new Set(["usdt", "usdc", "dai", "busd", "tusd", "usde", "fdusd", "pyusd"]);

const fmtUsd = (v) =>
  v == null ? "—"
    : v >= 1 ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 })
    : "$" + v.toLocaleString("en-US", { maximumFractionDigits: 6 });
const fmtBig = (v) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return "$" + (v / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return "$" + (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return "$" + (v / 1e6).toFixed(2) + "M";
  return "$" + Math.round(v).toLocaleString("en-US");
};
const pct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(2) + "%");
const cls = (v) => (v == null || Math.abs(v) < 0.01 ? "flat" : v > 0 ? "up" : "down");
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function normalise(raw) {
  return (raw || []).map((c) => ({
    rank: c.market_cap_rank,
    id: c.id,
    symbol: (c.symbol || "").toLowerCase(),
    name: c.name,
    image: c.image,
    price: c.current_price,
    mcap: c.market_cap,
    volume: c.total_volume,
    c24: c.price_change_percentage_24h_in_currency ?? c.price_change_percentage_24h,
    c7: c.price_change_percentage_7d_in_currency,
    c30: c.price_change_percentage_30d_in_currency,
    spark: (c.sparkline_in_7d && c.sparkline_in_7d.price) || [],
    stable: STABLES.has((c.symbol || "").toLowerCase()),
  }));
}

async function fetchMarkets() {
  try {
    const r = await fetch(ENDPOINT, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return { coins: normalise(await r.json()), live: true };
  } catch (_) {
    // honest fallback: the last committed snapshot, clearly labelled stale
    try {
      const r = await fetch(FALLBACK, { cache: "no-store" });
      if (r.ok) return { coins: normalise(await r.json()), live: false };
    } catch (__) { /* ignore */ }
    return { coins: [], live: false };
  }
}

/* ---------- DESCRIPTIVE signals (observed facts, never forecasts) ---------- */

// Momentum: agreement of 24h / 7d / 30d direction. A label, not a probability.
function momentum(c) {
  const s = [c.c24, c.c7, c.c30].map((x) => Math.sign(x || 0));
  const up = s.filter((x) => x > 0).length;
  const dn = s.filter((x) => x < 0).length;
  if (up === 3) return { label: "Sustained uptrend", dir: "up" };
  if (dn === 3) return { label: "Sustained downtrend", dir: "down" };
  if ((c.c24 || 0) > 0 && (c.c7 || 0) > 0) return { label: "Recovering", dir: "up" };
  if ((c.c24 || 0) < 0 && (c.c7 || 0) < 0) return { label: "Cooling", dir: "down" };
  return { label: "Mixed / choppy", dir: "flat" };
}

// Volatility: coefficient of variation of the real 7d price series.
function volatility(spark) {
  if (!spark || spark.length < 3) return { label: "—", level: "na", cv: null };
  const mean = spark.reduce((a, b) => a + b, 0) / spark.length;
  if (!mean) return { label: "—", level: "na", cv: null };
  const sd = Math.sqrt(spark.reduce((a, b) => a + (b - mean) ** 2, 0) / spark.length);
  const cv = sd / mean;
  if (cv > 0.06) return { label: "High", level: "high", cv };
  if (cv > 0.025) return { label: "Medium", level: "med", cv };
  return { label: "Low", level: "low", cv };
}

// Turnover: volume / market cap. Honest proxy for "how much is actually trading".
function turnover(c) {
  const r = c.mcap ? c.volume / c.mcap : 0;
  if (r > 0.15) return { label: "Hot", level: "high", ratio: r };
  if (r > 0.05) return { label: "Active", level: "med", ratio: r };
  if (r > 0) return { label: "Thin", level: "low", ratio: r };
  return { label: "—", level: "na", ratio: r };
}

// A single descriptive STATE chip + a transparent one-line explanation.
// This is a summary of recent observable behaviour — explicitly NOT a forecast.
function describe(c) {
  if (c.stable) {
    return {
      state: "Stablecoin · pegged", dir: "flat",
      why: "Designed to track ~$1; price-direction signals do not apply.",
      mom: { label: "—", dir: "flat" }, vol: volatility(c.spark), turn: turnover(c),
    };
  }
  const mom = momentum(c);
  const vol = volatility(c.spark);
  const turn = turnover(c);
  let state;
  if (mom.dir === "up") state = vol.level === "high" ? "Uptrend · volatile" : "Uptrend";
  else if (mom.dir === "down") state = vol.level === "high" ? "Downtrend · volatile" : "Downtrend";
  else state = "Rangebound";
  const parts = [];
  parts.push(`24h ${pct(c.c24)}, 7d ${pct(c.c7)}, 30d ${pct(c.c30)}`);
  parts.push(`volatility ${vol.label.toLowerCase()}`);
  parts.push(`turnover ${turn.label.toLowerCase()}`);
  const why = `${mom.label} — ${parts.join(" · ")}. Describes recent observable behaviour, not a forecast.`;
  return { state, dir: mom.dir, why, mom, vol, turn };
}

/* ---------- render ---------- */

let COINS = [];

function marketSummary(coins) {
  const tradable = coins.filter((c) => !c.stable);
  if (!tradable.length) return "";
  const up = tradable.filter((c) => (c.c24 || 0) > 0).length;
  const breadth = up / tradable.length;
  const sorted = [...tradable].sort((a, b) => (b.c24 || 0) - (a.c24 || 0));
  const gain = sorted[0], lose = sorted[sorted.length - 1];
  const biggest = [...tradable].sort((a, b) => Math.abs(b.c24 || 0) - Math.abs(a.c24 || 0))[0];
  let mood, moodCls;
  if (breadth >= 0.7) { mood = "Broadly green"; moodCls = "up"; }
  else if (breadth <= 0.3) { mood = "Broadly red"; moodCls = "down"; }
  else { mood = "Mixed"; moodCls = "flat"; }
  const tile = (v, l, c) => `<div class="cs-tile"><span class="cs-v ${c || ""}">${v}</span><span class="cs-l">${l}</span></div>`;
  return (
    tile(`<b class="${moodCls}">${mood}</b>`, "24h breadth · descriptive", "") +
    tile(`${up}/${tradable.length}`, "coins up on 24h", "") +
    tile(`${esc(gain.symbol.toUpperCase())} <span class="up">${pct(gain.c24)}</span>`, "top 24h gainer", "") +
    tile(`${esc(lose.symbol.toUpperCase())} <span class="down">${pct(lose.c24)}</span>`, "top 24h faller", "") +
    tile(`${esc(biggest.symbol.toUpperCase())} ${pct(biggest.c24)}`, "biggest 24h move", "")
  );
}

function sparkSvg(spark, dir) {
  if (!spark || spark.length < 2) return "";
  const n = Math.min(64, spark.length);
  const step = spark.length / n;
  const pts = [];
  for (let i = 0; i < n; i++) pts.push(spark[Math.floor(i * step)]);
  const min = Math.min(...pts), max = Math.max(...pts), rng = max - min || 1;
  const W = 120, H = 34;
  const d = pts.map((p, i) => `${(i / (n - 1) * W).toFixed(1)},${(H - ((p - min) / rng) * H).toFixed(1)}`).join(" ");
  const col = dir === "up" ? "var(--up)" : dir === "down" ? "var(--down)" : "var(--muted)";
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${d}" fill="none" stroke="${col}" stroke-width="1.5"/></svg>`;
}

function row(c) {
  const d = describe(c);
  return `<tr class="coin-row" data-id="${esc(c.id)}" tabindex="0" aria-expanded="false">
    <td class="rk">${c.rank ?? "—"}</td>
    <td class="nm"><img src="${esc(c.image || "")}" alt="" width="20" height="20" loading="lazy"/><span><b>${esc(c.name)}</b><i>${esc(c.symbol.toUpperCase())}</i></span></td>
    <td class="px">${fmtUsd(c.price)}</td>
    <td class="ch ${cls(c.c24)}">${pct(c.c24)}</td>
    <td class="ch ${cls(c.c7)} hide-sm">${pct(c.c7)}</td>
    <td class="ch ${cls(c.c30)} hide-sm">${pct(c.c30)}</td>
    <td class="vol hide-md">${fmtBig(c.volume)}</td>
    <td class="mc hide-md">${fmtBig(c.mcap)}</td>
    <td class="sig"><span class="state state-${d.dir}">${esc(d.state)}</span></td>
  </tr>
  <tr class="detail-row" data-detail="${esc(c.id)}" hidden><td colspan="9">${detail(c, d)}</td></tr>`;
}

function metric(label, value, note) {
  return `<div class="m"><span class="m-l">${label}</span><span class="m-v">${value}</span>${note ? `<span class="m-n">${note}</span>` : ""}</div>`;
}

// Real derivatives context from the cron-built feature store (Binance perps,
// keyless). Only fields that are actually present are shown — never faked.
function regimeMetrics(symbol) {
  const r = REGIME[symbol];
  if (!r) return null;
  const out = [];
  if (r.fundingRate != null)
    out.push(metric("Funding rate", (r.fundingRate * 100).toFixed(4) + "%",
      r.fundingZ != null ? "z-score " + esc(r.fundingZ) : "perp funding"));
  if (r.oiDelta != null)
    out.push(metric("Open interest", (r.oiDelta > 0 ? "+" : "") + (r.oiDelta * 100).toFixed(2) + "%", "1d change"));
  if (r.basis != null)
    out.push(metric("Basis", (r.basis * 100).toFixed(3) + "%", "mark vs index"));
  return out.length ? out.join("") : null;
}

function detail(c, d) {
  const real = [
    metric("Momentum", esc(d.mom.label), "agreement of 24h / 7d / 30d direction"),
    metric("Volatility (7d)", esc(d.vol.label), d.vol.cv != null ? "CV " + (d.vol.cv * 100).toFixed(1) + "%" : ""),
    metric("Turnover", esc(d.turn.label), d.turn.ratio ? "vol/mcap " + (d.turn.ratio * 100).toFixed(1) + "%" : ""),
    metric("24h volume", fmtBig(c.volume), ""),
    metric("Market cap", fmtBig(c.mcap), "rank #" + (c.rank ?? "—")),
  ].join("");
  const reg = regimeMetrics(c.symbol);
  const fx = forecastMetrics(c.symbol);
  const trackNote = forecastTrackNote();
  // Liquidations + on-chain stay honestly unavailable (no keyless source).
  // Funding / OI / basis are REAL now if the feature store loaded for this coin.
  const missingItems = ["Liquidations", "On-chain flows"];
  if (!reg) missingItems.unshift("Funding rate", "Open interest", "Basis");
  const missing = missingItems.map((m) => `<span class="soon">${m}</span>`).join("");
  return `<div class="detail">
    <div class="d-left">
      ${sparkSvg(c.spark, d.dir)}
      <p class="d-state"><span class="state state-${d.dir}">${esc(d.state)}</span></p>
      <p class="d-why">${esc(d.why)}</p>
    </div>
    <div class="d-right">
      ${fx ? `<p class="d-h">Our 24h forecast <span class="d-h-note">(unproven · scored vs random walk)</span></p>
      <div class="metrics">${fx}</div>
      <p class="fx-note">${trackNote}</p>` : ""}
      <p class="d-h">Observed metrics</p>
      <div class="metrics">${real}</div>
      ${reg ? `<p class="d-h">Derivatives · live <span class="d-h-note">(Binance perps, keyless)</span></p><div class="metrics">${reg}</div>` : ""}
      <p class="d-h">${reg ? "Still unavailable" : "Advanced — needs a derivatives / on-chain source"} <span class="d-h-note">(never faked)</span></p>
      <div class="soon-row">${missing}</div>
    </div>
  </div>`;
}

let REGIME = {};   // symbol -> regime.descriptive, from the cron-built feature store

// Join the cron-computed crypto regime (Binance perps) by symbol. Same-origin
// fetch; fail-open so the detail panel falls back to "not available".
async function loadRegime() {
  try {
    const r = await fetch("../features.json", { cache: "no-store" });
    if (!r.ok) return;
    const fs = await r.json();
    const map = {};
    (fs.records || []).forEach((rec) => {
      const reg = rec.regime && rec.regime.descriptive;
      if (rec.kind === "CRYPTO" && reg && reg.available) map[rec.assetId] = reg;
    });
    REGIME = map;
  } catch (_) { /* fail-open: detail shows derivatives as unavailable */ }
}

let FORECAST = {};        // symbol -> latest OPEN forecast (probUp, bandPct, sigmaPct)
let FORECAST_META = null; // crypto_scoreboard.json (the random-walk-scored track record)

// Join the public crypto-forecast ledger (cfx-v1) + its scoreboard. Same-origin
// fetch; fail-open so the panel simply omits the forecast if unavailable.
async function loadForecast() {
  try {
    const r = await fetch("../crypto_ledger.json", { cache: "no-store" });
    if (r.ok) {
      const cl = await r.json();
      const map = {};
      (cl.entries || []).forEach((e) => {
        if (e.status === "OPEN" && e.symbol && e.probUp != null) {
          const prev = map[e.symbol];
          if (!prev || e.openedAt > prev.openedAt) map[e.symbol] = e;
        }
      });
      FORECAST = map;
    }
  } catch (_) { /* fail-open */ }
  try {
    const r2 = await fetch("../crypto_scoreboard.json", { cache: "no-store" });
    if (r2.ok) FORECAST_META = await r2.json();
  } catch (_) { /* fail-open */ }
}

// Our 24h read: probUp + 80% volatility band. Falsifiable + publicly scored
// (SIGNAL_SPEC §9). NEVER a point "% change"; the band is a volatility range.
function forecastMetrics(symbol) {
  const f = FORECAST[symbol];
  if (!f || f.probUp == null || f.bandPct == null) return null;
  const up = Math.round(f.probUp * 1000) / 10;          // e.g. 47.7
  const note = f.sigmaPct != null
    ? "from " + Number(f.sigmaPct).toFixed(2) + "% daily vol"
    : "80% volatility band";
  return metric("24h up-probability", up + "%", "vs a 50% coin-flip baseline")
    + metric("24h range (80%)", "±" + Number(f.bandPct).toFixed(2) + "%", note);
}

// Honest one-liner on the live track record (N-gated, vs random walk).
function forecastTrackNote() {
  const m = FORECAST_META;
  if (!m || !m.counts) return "Logged now &amp; auto-scored after 24h. Track record building.";
  const n = m.counts.resolved || 0;
  if ((m.confidence || "none") === "none")
    return "Track record not yet meaningful — " + n +
           " resolved (auto-scored vs a random-walk baseline; honest by design).";
  const dir = m.direction || {}, band = m.band || {};
  const skill = dir.skillVsRandomWalk;
  const cov = band.coverageRate;
  return "Scored: " + n + " resolved · direction skill vs coin-flip " +
    (skill == null ? "—" : (skill > 0 ? "+" : "") + skill) +
    " · band coverage " +
    (cov == null ? "—" : Math.round(cov * 100) + "% (target 80%)") + ".";
}

// Public crypto-forecast track record (cs-v1) — scored vs random walk, N-gated.
// Honest by design: shows "not yet meaningful" until enough forecasts resolve,
// and shows skill even when we are no better than the baseline.
function renderTrack() {
  const el = document.getElementById("forecast-track");
  if (!el) return;
  const m = FORECAST_META;
  const tile = (v, l) =>
    `<div class="cs-tile"><span class="cs-v">${v}</span><span class="cs-l">${l}</span></div>`;
  if (!m || !m.counts) {
    el.innerHTML = `<p class="empty">Forecast track record loads with the next snapshot.</p>`;
    return;
  }
  const c = m.counts;
  const gated = (m.confidence || "none") !== "none";
  const dir = m.direction || {}, band = m.band || {};
  const skill = (gated && dir.skillVsRandomWalk != null)
    ? (dir.skillVsRandomWalk > 0 ? "+" : "") + dir.skillVsRandomWalk : "—";
  const cov = (gated && band.coverageRate != null)
    ? Math.round(band.coverageRate * 100) + "%" : "—";
  const calErr = (gated && dir.calibrationError != null) ? dir.calibrationError : "—";
  const pinball = (gated && band.pinball != null) ? band.pinball : "—";

  // Reliability mini-plot: predicted probUp vs realised up-rate, per bin.
  const bins = (gated && Array.isArray(dir.calibrationBins)) ? dir.calibrationBins : [];
  const relRow = (b) => {
    const p = Math.round((b.predicted || 0) * 100), a = Math.round((b.actual || 0) * 100);
    return `<div class="rel-row">
      <span class="rel-range">${esc(b.range)}<i>n=${b.n}</i></span>
      <span class="rel-bars">
        <span class="rel-bar rel-pred" style="width:${p}%"></span>
        <span class="rel-bar rel-act" style="width:${a}%"></span>
      </span>
      <span class="rel-nums">${p}% <i>pred</i> · ${a}% <i>real</i></span>
    </div>`;
  };
  const reliability = bins.length
    ? `<div class="reliability"><p class="rel-h">Direction reliability · predicted vs realised up-rate (steel = predicted, amber = actual)</p>${bins.map(relRow).join("")}</div>`
    : "";

  el.innerHTML =
    tile(c.resolved, "resolved · scored") +
    tile(c.open, "open · awaiting 24h") +
    tile(skill, "direction skill vs coin-flip") +
    tile(cov, "band coverage · target 80%") +
    tile(calErr, "calibration error · lower better") +
    tile(pinball, "band pinball · lower better") +
    `<p class="track-note">${gated
      ? "Scored vs a random-walk baseline. Direction skill near 0 = a coin flip; calibration error is how far our stated odds sit from reality; band coverage near 80% with low pinball = honest, well-sized uncertainty. Shown win or lose."
      : "Not yet meaningful — " + c.resolved + " resolved. Direction needs a long, "
        + "correlation-adjusted sample; the volatility band proves out sooner. "
        + "If we never beat the baseline, this will say so."}</p>` +
    reliability;
}

function render(data) {
  const { coins, live } = data;
  COINS = coins;
  const statusEl = document.getElementById("data-status");
  if (statusEl) statusEl.textContent = live ? "live · CoinGecko" : "cached snapshot (live feed unavailable)";
  const sumEl = document.getElementById("summary");
  const tbody = document.getElementById("coin-body");
  if (!coins.length) {
    if (sumEl) sumEl.innerHTML = `<p class="empty">Couldn't load market data right now. Try again shortly.</p>`;
    if (tbody) tbody.innerHTML = "";
    return;
  }
  if (sumEl) sumEl.innerHTML = marketSummary(coins);
  if (tbody) tbody.innerHTML = coins.map(row).join("");
  renderTrack();
}

function toggleRow(tr) {
  const id = tr.dataset.id;
  const det = document.querySelector(`tr[data-detail="${CSS.escape(id)}"]`);
  if (!det) return;
  const open = det.hasAttribute("hidden");
  if (open) { det.removeAttribute("hidden"); tr.setAttribute("aria-expanded", "true"); }
  else { det.setAttribute("hidden", ""); tr.setAttribute("aria-expanded", "false"); }
}

document.addEventListener("click", (ev) => {
  const tr = ev.target.closest(".coin-row");
  if (tr) toggleRow(tr);
});
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  const tr = ev.target.closest && ev.target.closest(".coin-row");
  if (tr) { ev.preventDefault(); toggleRow(tr); }
});

async function start() {
  await loadRegime();
  await loadForecast();
  render(await fetchMarkets());
  // light auto-refresh every 90s (descriptive data only; no alerts/sound)
  setInterval(async () => {
    await loadRegime();
    await loadForecast();
    render(await fetchMarkets());
  }, 90000);
}
start();
