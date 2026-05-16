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
  renderMacro();
  renderTicker();
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
  el.innerHTML =
    `<span class="mlabel">Market context · not a signal</span>` +
    `<span>BTC ${usd(m.btcUsd)} ${sign(m.btcChange24h, "%")}</span>` +
    `<span>ETH ${usd(m.ethUsd)} ${sign(m.ethChange24h, "%")}</span>` +
    `<span>Crypto mcap ${sign(m.totalMcapChange24h, "%")} 24h</span>` +
    `<span>BTC dom ${m.btcDominance != null ? m.btcDominance.toFixed(1) + "%" : "—"}</span>` +
    `<span class="regime ${m.regime}">${m.regime}</span>`;
}

function renderTicker() {
  const items = [];
  DATA.events.forEach((e) =>
    (e.movers || []).forEach((m) =>
      items.push(`<span><b>${escapeHtml(m.label)}</b> ${m.weekChange > 0 ? '<i class="u">▲</i>' : '<i class="d">▼</i>'} ${(Math.abs(m.weekChange) * 100).toFixed(1)}pp · ${escapeHtml(e.category)}</span>`)
    )
  );
  const track = document.getElementById("tickerTrack");
  if (!items.length) { document.getElementById("ticker").style.display = "none"; return; }
  document.getElementById("ticker").style.display = "";
  const seq = items.join("");
  track.innerHTML = REDUCED ? seq : seq + seq; // duplicate for seamless loop
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
