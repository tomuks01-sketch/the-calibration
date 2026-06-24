"use strict";

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const exact = new Intl.NumberFormat("en-US");
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const REFRESH_MS = 45000;

let DATA = null;
let activeCategory = "all";
let activeSignal = "all";
let prevLead = {};        // event id -> last leadPrice (for change flash)
let backoff = REFRESH_MS;
let lastGen = null;       // last generatedAt seen — pulse only on a NEW snapshot
let activeQuery = "";     // board free-text search
let activePlace = "all";  // geopolitics lens filter
let PLACES = null;        // place_allowlist.json (transparent country tagging)
let MAP_READY = false;    // world.svg injected

/* ---------- geopolitics "by place" lens (honest, allowlist-driven) ---------- */
async function loadPlaces() {
  try {
    const res = await fetch("./place_allowlist.json", { cache: "no-store" });
    if (res.ok) { PLACES = await res.json(); if (DATA) { renderPlaceChips(); paintMap(); } }
  } catch (_) { /* fail-open: the place row stays hidden, board unaffected */ }
}

// Self-hosted world map (Natural Earth, public domain — no CDN). Inject once.
async function loadWorldMap() {
  const host = document.getElementById("worldmap");
  if (!host) return;
  try {
    const res = await fetch("./world.svg", { cache: "force-cache" });
    if (!res.ok) return;
    host.innerHTML = await res.text();
    MAP_READY = true;
    paintMap();
  } catch (_) { /* fail-open: the map block stays hidden */ }
}

// Real event count per place — single source of truth for chips AND map.
function placeCounts() {
  const counts = {};
  if (!PLACES || !PLACES.places || !DATA) return counts;
  (DATA.events || []).forEach((e) => {
    const c = eventPlace(e);
    if (c && PLACES.places[c]) counts[c] = (counts[c] || 0) + 1;
  });
  return counts;
}

// Centralised place selection — keeps board, chips and map in sync.
function setPlace(code) {
  activePlace = code;
  render();
  renderPlaceChips();
  paintMap();
  bindTilt();
}

function paintMap() {
  if (!MAP_READY) return;
  const wrap = document.getElementById("geomap");
  const host = document.getElementById("worldmap");
  if (!host) return;
  const counts = placeCounts();
  // Density: the map only earns its space when several countries are tagged.
  // With 0–3 the place-chips row already conveys this without a mostly-empty map.
  const MIN_MAP_COUNTRIES = 4;
  if (Object.keys(counts).length < MIN_MAP_COUNTRIES) { if (wrap) wrap.hidden = true; return; }
  if (wrap) wrap.hidden = false;
  host.querySelectorAll("path").forEach((p) => {
    const iso = (p.id || "").replace("c-", "");
    const n = counts[iso] || 0;
    p.classList.toggle("has", n > 0);
    p.classList.toggle("sel", activePlace !== "all" && iso === activePlace);
    if (n > 0) {
      const nm = (PLACES.places[iso] && PLACES.places[iso].name) || iso;
      p.setAttribute("role", "button");
      p.setAttribute("tabindex", "0");
      p.setAttribute("aria-label", `${nm}: ${n} market${n === 1 ? "" : "s"}`);
    } else {
      p.removeAttribute("role"); p.removeAttribute("tabindex"); p.removeAttribute("aria-label");
    }
  });
}

// One country per event, ONLY via the vetted allowlist. No confident match → null.
function eventPlace(e) {
  if (!PLACES || !e) return null;
  const byCat = PLACES.byCategory || {};
  if (e.category && byCat[e.category]) return byCat[e.category];
  const byKw = PLACES.byTitleKeyword || {};
  for (const kw in byKw) {
    if (e.title && e.title.indexOf(kw) !== -1) return byKw[kw];
  }
  return null;
}

function renderPlaceChips() {
  const wrap = document.getElementById("places");
  const row = document.querySelector(".place-row");
  if (!wrap) return;
  if (!PLACES || !DATA || !PLACES.places) { if (row) row.hidden = true; return; }
  const counts = placeCounts();
  const codes = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  if (!codes.length) { if (row) row.hidden = true; return; }
  // If the active place dropped out of this snapshot, fall back to "all".
  if (activePlace !== "all" && !codes.includes(activePlace)) activePlace = "all";
  if (row) row.hidden = false;
  const chip = (place, label, count, flag) =>
    `<button class="chip${place === activePlace ? " is-active" : ""}" data-place="${escAttr(place)}">` +
    (flag ? `<span class="flag">${flag}</span>` : "") + escapeHtml(label) +
    (count != null ? `<span class="pcount">${count}</span>` : "") + `</button>`;
  wrap.innerHTML =
    chip("all", "All places", null, "") +
    codes.map((c) => chip(c, PLACES.places[c].name, counts[c], PLACES.places[c].flag)).join("");
}

/* ---------- data ---------- */
async function fetchData() {
  const res = await fetch("./data.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function load(initial) {
  document.body.classList.add("is-refreshing");
  try {
    const next = await fetchData();
    DATA = next;
    backoff = REFRESH_MS;
    paint(initial);
    document.body.classList.remove("is-refreshing");
    // One-shot amber scan ONLY when a genuinely new snapshot arrived —
    // never on identical re-fetches (honest: don't signal "updated" if it isn't).
    const gen = next && next.generatedAt;
    if (!initial && gen && gen !== lastGen) pulseRefresh();
    lastGen = gen || lastGen;
    announce(initial ? "Dashboard loaded" : "Dashboard updated");
    document.getElementById("generated").classList.remove("stale");
  } catch (err) {
    if (initial) {
      document.getElementById("board").innerHTML =
        `<p class="empty">Could not load data.json (${err.message}). ` +
        `Run <code>python src/generate_snapshot.py</code> first.</p>`;
    } else {
      document.getElementById("generated").classList.add("stale");
      backoff = Math.min(backoff * 2, 300000);
    }
    document.body.classList.remove("is-refreshing");
  }
  setTimeout(() => load(false), backoff);
}

function announce(msg) {
  const el = document.getElementById("refresh-status");
  el.textContent = msg;
  setTimeout(() => { el.textContent = ""; }, 4000);
}

// Restart the one-shot top scan-line animation (remove → reflow → add).
function pulseRefresh() {
  if (REDUCED) return;
  const el = document.getElementById("refresh-scan");
  if (!el) return;
  el.classList.remove("run");
  void el.offsetWidth;            // force reflow so the animation can re-trigger
  el.classList.add("run");
}

/* ---------- paint ---------- */
function paint(initial) {
  const gen = new Date(DATA.generatedAt);
  const ageMin = Math.max(0, Math.round((Date.now() - gen.getTime()) / 60000));
  const gEl = document.getElementById("generated");
  gEl.textContent =
    `Snapshot ${ageMin} min old · ${gen.toLocaleString("en-US", { timeStyle: "short" })}`;
  gEl.classList.toggle("stale", ageMin > 40);

  // Dynamic freshness labels — derived from actual snapshot age, not hardcoded.
  const freshnessLabel = ageMin <= 5 ? "LIVE" : ageMin <= 35 ? "DELAYED" : ageMin <= 60 ? "STALE" : "VERY STALE";
  const delayDetail = ageMin <= 5 ? "live" : ageMin <= 35 ? `~${ageMin}m delayed` : `${ageMin}m old`;
  const freshEl = document.getElementById("data-freshness");
  if (freshEl) freshEl.textContent = freshnessLabel;
  const boardDelayEl = document.getElementById("board-delay-label");
  if (boardDelayEl) boardDelayEl.textContent = freshnessLabel + " · " + delayDetail;
  renderKpis(initial);
  renderEditorial();
  renderProof();
  renderMacro();
  renderKalshi();
  renderCategoryChips();
  renderPlaceChips();
  paintMap();
  const y = window.scrollY;
  const focusInBoard = document.activeElement &&
    document.getElementById("board").contains(document.activeElement);
  render();
  if (!focusInBoard) window.scrollTo({ top: y, behavior: "instant" });
  bindTilt();
}

function num(v) { return v === null || v === undefined ? null : v; }
function pct1(p) { return p === null || p === undefined ? null : (p * 100).toFixed(1); }
function odds(p) { return !p || p <= 0 || p >= 1 ? null : (1 / p).toFixed(2); }
function dTxt(d) {
  if (d === null || d === undefined) return "—";
  const v = d * 100;
  if (Math.abs(v) < 0.005) return "0.00 pp";
  return (v > 0 ? "+" : "") + v.toFixed(2) + " pp";
}
function dCls(d) {
  if (d === null || d === undefined || Math.abs(d) < 0.0005) return "flat";
  return d > 0 ? "up" : "down";
}
function wk(w) {
  if (!w || Math.abs(w) < 0.005) return "";
  const c = w > 0 ? "up" : "down";
  return `<span class="wk ${c}">${w > 0 ? "▲" : "▼"}${Math.abs(w * 100).toFixed(1)}</span>`;
}

function renderKpis(initial) {
  const e = DATA.events;
  const totalVol = e.reduce((a, x) => a + (x.volume || 0), 0);
  const movers = e.filter((x) => (x.movers || []).length).length;
  const tiles = [
    { v: e.length, l: "Events tracked", c: "" },
    { v: "$" + compact.format(totalVol), l: "Total volume", c: "accent" },
    { v: movers, l: "With movers", c: "up" },
    { v: (DATA.categories || []).length, l: "Categories", c: "sap" },
  ];
  document.getElementById("kpis").innerHTML = tiles
    .map((t, i) => `<div class="kpi ${t.c}"><div class="v" data-i="${i}">${t.v}</div><div class="l">${t.l}</div></div>`)
    .join("");
  if (initial && !REDUCED) {
    tiles.forEach((t, i) => {
      if (/^\d+$/.test(String(t.v))) {
        countUp(document.querySelector(`.kpi .v[data-i="${i}"]`), parseInt(t.v, 10));
      }
    });
  }
}

function countUp(el, target) {
  if (!el || target <= 0) return;
  const start = performance.now();
  const dur = 480;
  function step(now) {
    const p = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = p < 1 ? Math.round(target * eased).toString() : String(target);
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Editorial hybrid front: Scoreboard pulse + latest brief hero + hero stats.
// Each block fails open — on any error it stays hidden / unfilled, board still works.
async function renderEditorial() {
  let sb = null;
  try {
    sb = await (await fetch("scoreboard.json", { cache: "no-store" })).json();
    const c = sb && sb.counts;
    if (c) {
      const el = document.getElementById("sb-pulse");
      el.innerHTML =
        `<span class="lbl">The Scoreboard</span> ` +
        `<b>${c.resolved}</b> resolved · <b>${c.pending}</b> open · ` +
        `<b>${c.void}</b> void · model <b>${escapeHtml(sb.modelVersion || "—")}</b>` +
        ` <span class="go">audit →</span>`;
      el.hidden = false;
    }
  } catch (_) { /* fail-open: pulse stays hidden */ }
  try {
    const b = await (await fetch("briefs/latest.json", { cache: "no-store" })).json();
    if (b && b.title && b.url) {
      const el = document.getElementById("latest-brief");
      el.innerHTML =
        `<p class="lb-kicker">The Crowd Signal · latest</p>` +
        `<h2>${escapeHtml(b.title)}</h2>` +
        (b.standfirst ? `<p class="lb-sf">${escapeHtml(b.standfirst)}</p>` : "") +
        `<a class="lb-go" href="${safeUrl(b.url)}">Read the brief →</a>`;
      el.hidden = false;
    }
  } catch (_) { /* fail-open: brief hero stays hidden */ }
  // Hero stats — fill from whatever we have. Per-item fail-open: missing
  // values stay as the placeholder em-dash. No fabrication.
  const hs = document.getElementById("hero-stats");
  if (hs) {
    const set = (k, v) => {
      if (v === undefined || v === null) return;
      const el = hs.querySelector(`[data-stat="${k}"]`);
      if (el) el.textContent = v;
    };
    const c = sb && sb.counts;
    if (c) {
      set("resolved", c.resolved);
      set("pending", c.pending);
    }
    if (sb && sb.modelVersion) set("model", sb.modelVersion);
    if (DATA && Array.isArray(DATA.events)) set("events", DATA.events.length);
  }
}

// Live calibration proof: scoreboard pulse panel + open calls list +
// divergence chart. All driven by the public ledger/scoreboard JSON.
// Per-panel fail-open: a missing file leaves placeholders, never fakes data.
async function renderProof() {
  // ----- Scoreboard status grid (4 cells: resolved / pending / void / confidence)
  try {
    const sb = await (await fetch("scoreboard.json", { cache: "no-store" })).json();
    const c = sb && sb.counts;
    const grid = document.getElementById("pr-status-grid");
    if (grid && c) {
      const set = (k, v) => {
        const el = grid.querySelector(`[data-stat="${k}"]`);
        if (el && v !== undefined && v !== null) el.textContent = v;
      };
      set("resolved", c.resolved);
      set("pending", c.pending);
      set("void", c.void);
      set("confidence", sb.confidence || "none");
    }
  } catch (_) { /* fail-open */ }

  // ----- Open calls list + divergence chart from the public ledger
  let led;
  try {
    led = await (await fetch("ledger.json", { cache: "no-store" })).json();
  } catch (_) {
    return; // panels keep their skeleton state
  }
  const open = (led.entries || []).filter((e) => e.status === "PENDING");

  // Next expected resolution: find the soonest-closing tracked pending call.
  // Declared BEFORE the awaiting-resolution block below, which reads it
  // (const has a temporal dead zone — referencing it earlier throws).
  const nextResolve = (() => {
    const pending = (led.entries || []).filter((e) => e.status === "PENDING" && e.openedAt);
    if (!pending.length) return null;
    // Use daysToResolution from data.json if available for the same event slug.
    const events = (DATA && DATA.events) || [];
    let best = null;
    for (const call of pending) {
      const match = events.find((ev) => ev.slug === call.eventSlug || ev.id === call.marketId);
      const d = match ? match.daysToResolution : null;
      if (d !== null && d !== undefined && d >= 0 && (best === null || d < best.d)) {
        best = { d, title: call.eventTitle || call.question };
      }
    }
    return best;
  })();

  // Honest "awaiting first resolution" status — real ledger data only, no
  // fabricated countdown (the ledger carries no market close date). Shows the
  // age of the oldest still-open call while nothing has resolved yet.
  const ageEl = document.getElementById("pr-age");
  if (ageEl) {
    const resolvedN = (led.entries || []).filter((e) => e.status === "RESOLVED").length;
    const opens = open.map((e) => e.openedAt).filter(Boolean).sort();
    const t0 = opens.length ? new Date(opens[0]).getTime() : NaN;
    if (resolvedN === 0 && !Number.isNaN(t0)) {
      const days = Math.max(0, Math.floor((Date.now() - t0) / 86400000));
      const nextHint = nextResolve
        ? ` · Next tracked call closes in ~${nextResolve.d}d`
        : "";
      ageEl.textContent =
        `First call still open — oldest opened ${days}d ago, awaiting the first resolution.${nextHint}`;
      ageEl.hidden = false;
    } else {
      // malformed/absent date or a call has resolved → hide rather than
      // ever render "NaNd ago" or a stale "awaiting" claim.
      ageEl.hidden = true;
    }
  }

  // Confidence-tier legend — updates based on resolved count so it stays honest.
  const tiersEl = document.getElementById("confidence-tiers-note");
  if (tiersEl) {
    const resolvedCount = (led.entries || []).filter((e) => e.status === "RESOLVED").length;
    const tiers = [
      { min: 0,  max: 9,  label: "none",   note: "Fewer than 10 resolved calls — model history too short to assess." },
      { min: 10, max: 29, label: "low",    note: "10–29 resolved · early signal, treat with caution." },
      { min: 30, max: 99, label: "medium", note: "30–99 resolved · meaningful sample, caveats remain." },
      { min: 100, max: Infinity, label: "high", note: "100+ resolved · enough history to assess calibration." },
    ];
    const current = tiers.find((t) => resolvedCount >= t.min && resolvedCount <= t.max);
    tiersEl.innerHTML =
      `Current: <em>${current ? escapeHtml(current.label) : "—"}</em> · ${current ? escapeHtml(current.note) : ""} ` +
      `<span class="tier-scale">none &lt;10 · low &lt;30 · medium &lt;100 · high 100+</span>`;
  }

  const callsEl = document.getElementById("proof-open-calls");
  if (callsEl) {
    callsEl.innerHTML = open.length
      ? open.slice(0, 5).map((e) => {
          const cp = Math.round((e.crowdProbAtCallTime || 0) * 100);
          const mp = Math.round((e.modelProb || 0) * 100);
          const dv = Number(e.divergencePp) || 0;
          const sgn = dv > 0 ? "+" : "";
          const dir = dv >= 0 ? "up" : "dn";
          const q = escapeHtml((e.question || e.eventTitle || "—").slice(0, 110));
          return `<li>
              <div class="pc-q">${q}</div>
              <div class="pc-meta">
                <span><b>${cp}%</b> crowd</span>
                <span><b>${mp}%</b> qest</span>
                <span class="pc-dv pc-dv-${dir}">${sgn}${dv}pp</span>
              </div>
            </li>`;
        }).join("")
      : `<li class="pr-skel">No open calls right now &mdash; ledger is empty.</li>`;
  }

  const divEl = document.getElementById("proof-divergence");
  if (divEl) {
    if (!open.length) {
      divEl.innerHTML = `<p class="pr-skel">No open calls right now.</p>`;
    } else {
      const max = Math.max(6, ...open.map((e) => Math.abs(Number(e.divergencePp) || 0)));
      divEl.innerHTML = open.map((e) => {
        const dv = Number(e.divergencePp) || 0;
        const w = (Math.abs(dv) / max) * 50; // half-axis percentage
        const dir = dv >= 0 ? "right" : "left";
        const q = escAttr((e.question || "—").slice(0, 60));
        const sgn = dv > 0 ? "+" : "";
        const aria = escAttr(`${(e.question || "—").slice(0, 60)}: QEST ${sgn}${dv}pp ${dv >= 0 ? "above" : "below"} crowd`);
        return `<div class="pd-row" title="${q}" aria-label="${aria}">
            <span class="pd-axis">
              <span class="pd-mid"></span>
              <span class="pd-bar pd-${dir}" style="width:${w}%"></span>
            </span>
            <span class="pd-val">${sgn}${dv}pp</span>
          </div>`;
      }).join("");
    }
  }
}

// Kalshi shown as a SEPARATE venue — explicitly NOT compared/paired with
// Polymarket (different contracts/terms). Hides if no data (fail-open).
function renderKalshi() {
  const el = document.getElementById("kalshi");
  const k = (DATA && DATA.kalshi) || [];
  if (!k.length) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML =
    `<span class="mlabel">Kalshi · separate venue — own contracts, NOT a Polymarket comparison</span>` +
    k.map((r) =>
      `<span class="kx" title="${escAttr(r.title)} (closes ${escAttr(r.closeDate)})">` +
      `${escapeHtml(r.series)} <b>${Number.isFinite(r.impliedPct) ? r.impliedPct : "—"}%</b></span>`
    ).join("") +
    `<span class="kx-src">Kalshi public API · read-only</span>`;
}

function renderMacro() {
  const el = document.getElementById("macro");
  const m = DATA.macro;
  if (!m || !m.available) { el.hidden = true; return; }
  el.hidden = false;
  const sign = (v, suf) =>
    v === null || v === undefined
      ? "—"
      : `<b class="${v > 0 ? "up" : v < 0 ? "down" : "flat"}">${v > 0 ? "+" : ""}${v.toFixed(1)}${suf}</b>`;
  const usd = (v) =>
    v === null || v === undefined ? "—" : "$" + Intl.NumberFormat("en-US").format(Math.round(v));
  let html =
    `<span class="mlabel">Market context · not a signal</span>` +
    `<span>BTC ${usd(m.btcUsd)} ${sign(m.btcChange24h, "%")}</span>` +
    `<span>ETH ${usd(m.ethUsd)} ${sign(m.ethChange24h, "%")}</span>` +
    `<span>Crypto mcap ${sign(m.totalMcapChange24h, "%")} 24h</span>` +
    `<span>BTC dom ${m.btcDominance != null ? m.btcDominance.toFixed(1) + "%" : "—"}</span>` +
    `<span class="regime ${m.regime}">${m.regime}</span>`;

  const top = m.topCoins || [];
  if (top.length) {
    html += `<div class="topcoins"><span class="mlabel">Top 10 by mcap · 24h / 7d · context, not advice</span>` +
      top.map((c) =>
        `<span class="tc">${escapeHtml(c.symbol)} ${sign(c.change24h, "%")}` +
        `<i>${c.change7d == null ? "" : (c.change7d > 0 ? "+" : "") + c.change7d.toFixed(1) + "% 7d"}</i></span>`
      ).join("") + `</div>`;
  }

  // Descriptive traditional-market index context (delayed, not a signal).
  const idx = m.indices;
  if (idx && idx.available && (idx.items || []).length) {
    html += `<div class="topcoins"><span class="mlabel">Stocks · delayed · context, not a signal</span>` +
      idx.items.map((s) =>
        `<span class="tc">${escapeHtml(s.name)} ${sign(s.changePct, "%")}</span>`
      ).join("") + `</div>`;
  }
  el.innerHTML = html;
}

function renderCategoryChips() {
  const cats = ["all", ...(DATA.categories || [])];
  document.getElementById("categories").innerHTML = cats
    .map((c) => `<button class="chip${c === activeCategory ? " is-active" : ""}" data-cat="${escAttr(c)}">${c === "all" ? "All categories" : escapeHtml(c)}</button>`)
    .join("");
}

function leadBlock(e) {
  const lp = pct1(e.leadPrice);
  const dc = dCls(e.change24h);
  const delta = dTxt(e.change24h);
  if (e.binary) {
    const o = odds(e.leadPrice);
    return `<div class="lead">
      <div class="big ${lp !== null && +lp >= 50 ? "y" : ""}">${lp ?? "—"}%</div>
      ${o ? `<div class="odds-pill">${o}× <small>odds</small></div>` : ""}
      <div class="lead-sub">YES probability</div>
      <div class="hero ${dc}">${delta} <small>24h</small></div>
    </div>`;
  }
  const top = e.outcomes && e.outcomes[0];
  const to = top ? odds(top.price) : null;
  return `<div class="lead">
    <div class="big">${top ? pct1(top.price) + "%" : "—"}</div>
    ${to ? `<div class="odds-pill">${to}× <small>odds</small></div>` : ""}
    <div class="lead-sub">${top ? "leader · " + escapeHtml(top.label) : "multi"}</div>
    <div class="hero ${dc}">${delta} <small>24h leader</small></div>
  </div>`;
}

function contextLine(e) {
  const c = e.context;
  if (!c || !c.summary) return "";
  const src = (c.sources || [])
    .map((s) => `<a href="${safeUrl(s.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.name)}</a>`)
    .join(" · ");
  const prov = c.tier === "B"
    ? "AI-summarised from news · may be wrong, check sources"
    : "from news headlines";
  return `<p class="ctxline"><span class="ctxlabel">Context · ${prov}</span>
    ${escapeHtml(c.summary)}${src ? ` <span class="ctxsrc">${src}</span>` : ""}</p>`;
}

function modelLine(e) {
  const m = e.model;
  if (!m || m.prob == null) return "";
  const pct = (m.prob * 100).toFixed(0);
  const ver = escapeHtml(m.version);
  // QEST = Quantitative Estimate: a documented mean-reversion baseline.
  // NOT AI, NOT advice. Honest two-state framing:
  //  - tracked: a real divergence call, in the public scored ledger.
  //  - untracked: model agrees with the crowd — NO edge claim, NOT scored.
  const crowd = e.leadPrice == null ? null : Math.round(e.leadPrice * 100);
  const dv = Number(m.divergencePp) || 0;
  const dpp = `${dv > 0 ? "+" : ""}${dv}pp`;
  const tail = m.tracked
    ? `<a href="scoreboard/">${m.status === "RESOLVED" ? "resolved & scored →" : "logged & being scored →"}</a>`
    : `in line · not a tracked call, no edge claimed`;
  // Two INDEPENDENT readings side by side so the reader judges for themselves.
  // No third "Google %" — news has no probability (shown as context only).
  const cls = "cmpviz" + (m.tracked ? "" : " cmpviz-flat");
  const cw = crowd == null ? 0 : Math.max(0, Math.min(100, crowd));
  const qw = Math.max(0, Math.min(100, Number(pct)));
  // Two INDEPENDENT readings on one 0–100% scale so the gap is visible at a
  // glance. Same honest numbers as before — no third source, no new claim.
  return `<div class="${cls}">
      <div class="cv-row">
        <span class="cv-lab">Crowd · Polymarket</span>
        <span class="cv-track"><i style="width:${cw}%"></i></span>
        <span class="cv-val">${crowd == null ? "—" : cw + "%"}</span>
      </div>
      <div class="cv-row">
        <span class="cv-lab">QEST · baseline ${ver}</span>
        <span class="cv-track q"><i style="width:${qw}%"></i></span>
        <span class="cv-val">${pct}%</span>
      </div>
      <p class="cv-note"><b>${dpp}</b> difference · two independent readings ·
        QEST not AI, not advice · ${tail}</p>
    </div>`;
}

// Descriptive "repricing pressure" — what's moving / unsettled NOW. Never a
// forecast, never an outcome probability (mirrors features.json pressure).
function pressureLine(e) {
  const p = e.pressure;
  if (!p) return "";
  const chips = [];
  if (p.preResolutionVol) chips.push("unsettled before resolution");
  if (p.overheated) chips.push("priced near-certain");
  if (p.suddenMove) {
    const m = p.move24hPp;
    chips.push(`moving now ${m > 0 ? "+" : ""}${m}pp/24h`);
  } else if (p.infoEventNear) {
    chips.push("resolves soon");
  }
  if (!chips.length) return "";
  return `<p class="pressure" title="Descriptive: current market conditions, not a prediction of the outcome.">` +
    `<span class="pr-tag">Repricing pressure</span>` +
    chips.map((c) => `<span class="pr-chip">${escapeHtml(c)}</span>`).join("") + `</p>`;
}

function eventCard(e) {
  const isExpired = e.daysToResolution !== null && e.daysToResolution !== undefined && e.daysToResolution < 0;
  const bars = (e.outcomes || [])
    .map((o) => {
      const p = pct1(o.price) ?? "0";
      return `<div class="ob"><div class="ob-top"><span class="ob-name">${escapeHtml(o.label)}</span><span class="ob-val">${p}% ${wk(o.weekChange)}</span></div><div class="ob-track"><i style="width:${Math.round(o.price * 100)}%"></i></div></div>`;
    })
    .join("");

  const moreCount = (e.marketCount || 0) - (e.outcomes ? e.outcomes.length : 0);
  const movers =
    e.movers && e.movers.length
      ? `<div class="movers"><span class="ml">⚡ Movers · 1w</span>${e.movers
          .map((m) => `<span class="mv ${m.weekChange > 0 ? "up" : "down"}">${escapeHtml(m.label)} ${m.weekChange > 0 ? "+" : ""}${(m.weekChange * 100).toFixed(1)}pp</span>`)
          .join("")}</div>`
      : "";

  const flags = (e.flags || [])
    .map((f) => `<span class="flag ${f}">${f.replace(/-/g, " ")}</span>`)
    .join("");
  const barNote = e.binary
    ? ""
    : `<p class="bar-note">Per-outcome YES prices — independent sub-markets, may not sum to 100%.</p>`;

  const news =
    e.news && e.news.length
      ? `<ul>${e.news.map((n) => `<li><a href="${safeUrl(n.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(n.title)} <span>${escapeHtml(n.source || "")}</span></a></li>`).join("")}</ul>`
      : `<p class="none">No recent headlines matched this event.</p>`;

  const days = e.daysToResolution === null || e.daysToResolution === undefined ? "—" : `${e.daysToResolution}d`;
  let flash = "";
  if (prevLead[e.id] !== undefined && e.leadPrice !== null && !REDUCED) {
    if (e.leadPrice > prevLead[e.id] + 0.0005) flash = "flash-up";
    else if (e.leadPrice < prevLead[e.id] - 0.0005) flash = "flash-down";
  }
  prevLead[e.id] = e.leadPrice;

  return `<article class="event ${flash}${isExpired ? " expired" : ""}" data-id="${escAttr(e.id)}">
    ${isExpired ? `<p class="expired-badge">Market closed — awaiting resolution</p>` : ""}
    <div class="ehead">
      <div><span class="cat">${escapeHtml(e.category)}</span><h3>${escapeHtml(e.title)}</h3></div>
      ${leadBlock(e)}
    </div>
    <div class="bars">${bars}</div>
    ${barNote}
    ${moreCount > 0 ? `<p class="more">+${moreCount} more outcomes in this event</p>` : ""}
    ${movers}
    <div class="stats">
      <span title="$${exact.format(Math.round(e.volume))}">Volume <b>$${compact.format(e.volume)}</b></span>
      <span title="$${exact.format(Math.round(e.liquidity))}">Liquidity <b>$${compact.format(e.liquidity)}</b></span>
      <span>Δ1h <b class="${dCls(e.change1h)}">${dTxt(e.change1h)}</b></span>
      <span>Outcomes <b>${e.marketCount}</b></span>
      <span>Resolves <b>${days}</b></span>
    </div>
    <div class="flags">${flags}</div>
    ${pressureLine(e)}
    ${modelLine(e)}
    ${contextLine(e)}
    <div class="news"><h4>Related headlines · Google News (keyword-matched, not curated)</h4>${news}</div>
  </article>`;
}

// Free-text match over the fields a reader would search: question, category,
// and the visible outcome labels. Pure filter on real data — no new claim.
function matchesQuery(e, q) {
  q = q.toLowerCase();
  if ((e.title || "").toLowerCase().includes(q)) return true;
  if ((e.category || "").toLowerCase().includes(q)) return true;
  return (e.outcomes || []).some((o) => (o.label || "").toLowerCase().includes(q));
}

function render() {
  let list = DATA.events;
  if (activeCategory !== "all") list = list.filter((e) => e.category === activeCategory);
  if (activeSignal !== "all") list = list.filter((e) => (e.flags || []).includes(activeSignal));
  if (activePlace !== "all") list = list.filter((e) => eventPlace(e) === activePlace);
  if (activeQuery) list = list.filter((e) => matchesQuery(e, activeQuery));
  document.getElementById("board").innerHTML = list.length
    ? list.map(eventCard).join("")
    : `<p class="empty">No events match this filter right now.</p>`;
}

/* ---------- pointer tilt (compositor-only, throttled) ---------- */
function bindTilt() {
  if (REDUCED || window.matchMedia("(pointer: coarse)").matches) return;
  document.querySelectorAll(".event").forEach((card) => {
    let pending = false, px = 0, py = 0;
    card.addEventListener("pointermove", (ev) => {
      const r = card.getBoundingClientRect();
      px = (ev.clientX - r.left) / r.width - 0.5;
      py = (ev.clientY - r.top) / r.height - 0.5;
      if (!pending) {
        pending = true;
        requestAnimationFrame(() => {
          card.style.transform = `perspective(1200px) rotateY(${px * 5}deg) rotateX(${-py * 5}deg)`;
          pending = false;
        });
      }
    });
    card.addEventListener("pointerleave", () => { card.style.transform = ""; });
  });
}

/* ---------- helpers ---------- */
function safeUrl(u) {
  try {
    const url = new URL(String(u), location.href);
    if (url.protocol === "http:" || url.protocol === "https:") return escapeHtml(url.href);
  } catch (_) { /* fall through */ }
  return "#";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escAttr(s) { return String(s).replace(/"/g, "&quot;"); }

document.getElementById("categories").addEventListener("click", (ev) => {
  const b = ev.target.closest(".chip");
  if (!b) return;
  document.querySelectorAll("#categories .chip").forEach((c) => c.classList.remove("is-active"));
  b.classList.add("is-active");
  activeCategory = b.dataset.cat;
  render();
  bindTilt();
});
document.getElementById("signals").addEventListener("click", (ev) => {
  const b = ev.target.closest(".chip");
  if (!b) return;
  document.querySelectorAll("#signals .chip").forEach((c) => c.classList.remove("is-active"));
  b.classList.add("is-active");
  activeSignal = b.dataset.flag;
  render();
  bindTilt();
});

const placesEl = document.getElementById("places");
if (placesEl) {
  placesEl.addEventListener("click", (ev) => {
    const b = ev.target.closest(".chip");
    if (!b) return;
    setPlace(b.dataset.place);
  });
}

// World map: click / keyboard-activate a highlighted country to filter.
const mapEl = document.getElementById("worldmap");
if (mapEl) {
  const fromPath = (target) => {
    const p = target.closest && target.closest("path");
    if (!p) return null;
    const iso = (p.id || "").replace("c-", "");
    return placeCounts()[iso] ? iso : null;
  };
  mapEl.addEventListener("click", (ev) => {
    const iso = fromPath(ev.target);
    if (iso) setPlace(iso === activePlace ? "all" : iso);
  });
  mapEl.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const iso = fromPath(ev.target);
    if (iso) { ev.preventDefault(); setPlace(iso === activePlace ? "all" : iso); }
  });
  // Hover tooltip — country name + live market count, follows the cursor.
  const tip = document.getElementById("map-tip");
  mapEl.addEventListener("pointermove", (ev) => {
    if (!tip) return;
    const p = ev.target.closest && ev.target.closest("path");
    const iso = p && p.classList.contains("has") ? (p.id || "").replace("c-", "") : null;
    const n = iso ? placeCounts()[iso] : 0;
    if (!n) { tip.hidden = true; return; }
    const nm = (PLACES.places[iso] && PLACES.places[iso].name) || iso;
    tip.textContent = `${nm} · ${n} market${n === 1 ? "" : "s"}`;
    tip.style.left = ev.clientX + "px";
    tip.style.top = ev.clientY + "px";
    tip.hidden = false;
  });
  mapEl.addEventListener("pointerleave", () => { if (tip) tip.hidden = true; });
}

const searchEl = document.getElementById("board-search");
if (searchEl) {
  // Debounce: a full board re-render + tilt re-bind on every keystroke blocks
  // input on low-end devices. 200ms keeps it responsive without churn.
  let searchTimer;
  searchEl.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      activeQuery = searchEl.value.trim();
      render();
      bindTilt();
    }, 200);
  });
}
// "/" focuses the board search (skip when already typing in a field).
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "/") return;
  const t = ev.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  if (searchEl) { ev.preventDefault(); searchEl.focus(); }
});

loadPlaces();
loadWorldMap();
load(true);
