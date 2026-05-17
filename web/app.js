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

/* ---------- data ---------- */
async function fetchData() {
  const res = await fetch("./data.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function load(initial) {
  try {
    const next = await fetchData();
    DATA = next;
    backoff = REFRESH_MS;
    paint(initial);
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
  }
  setTimeout(() => load(false), backoff);
}

function announce(msg) {
  const el = document.getElementById("refresh-status");
  el.textContent = msg;
  setTimeout(() => { el.textContent = ""; }, 4000);
}

/* ---------- paint ---------- */
function paint(initial) {
  const gen = new Date(DATA.generatedAt);
  const ageMin = Math.max(0, Math.round((Date.now() - gen.getTime()) / 60000));
  const gEl = document.getElementById("generated");
  gEl.textContent =
    `Snapshot ${ageMin} min old · ${gen.toLocaleString("en-US", { timeStyle: "short" })}`;
  gEl.classList.toggle("stale", ageMin > 40);
  renderKpis(initial);
  renderEditorial();
  renderMacro();
  renderKalshi();
  renderCategoryChips();
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

// Editorial hybrid front: Scoreboard pulse + latest brief hero.
// Each block fails open — on any error it stays hidden, board still works.
async function renderEditorial() {
  try {
    const sb = await (await fetch("scoreboard.json", { cache: "no-store" })).json();
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
  if (m.tracked) {
    const st = m.status === "RESOLVED" ? "resolved & scored" : "logged & being scored";
    return `<p class="modelline"><b>QEST ${pct}%</b> · diverges ${m.divergencePp > 0 ? "+" : ""}${m.divergencePp}pp from the crowd
      · documented mean-reversion baseline ${ver}, not AI/advice · this call is
      <a href="scoreboard/">${st} →</a></p>`;
  }
  return `<p class="modelline modelline-flat"><b>QEST ${pct}%</b> · in line with the crowd
    (${m.divergencePp > 0 ? "+" : ""}${m.divergencePp}pp) · documented baseline ${ver},
    not AI/advice · not a tracked call, no edge claimed</p>`;
}

function eventCard(e) {
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

  return `<article class="event ${flash}" data-id="${escAttr(e.id)}">
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
    ${modelLine(e)}
    ${contextLine(e)}
    <div class="news"><h4>Related headlines · Google News (keyword-matched, not curated)</h4>${news}</div>
  </article>`;
}

function render() {
  let list = DATA.events;
  if (activeCategory !== "all") list = list.filter((e) => e.category === activeCategory);
  if (activeSignal !== "all") list = list.filter((e) => (e.flags || []).includes(activeSignal));
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

load(true);
