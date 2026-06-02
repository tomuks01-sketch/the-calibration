"use strict";
/* The Calibration — Stock Pulse (descriptive large-cap analytics).
 *
 * HARD RULE: never a forecast, never advice, never a scored probability. Every
 * signal DESCRIBES observable data (SIGNAL_SPEC §1). Data is computed server-
 * side (Yahoo has no CORS) and read here from ../stocks.json — this file is a
 * thin renderer only. Our scored, falsifiable reads live on the Crypto page.
 */

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtUsd = (v) =>
  v == null ? "—" : "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 });
const fmtBig = (v) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(2) + "M";
  return Math.round(v).toLocaleString("en-US");
};
const pct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(2) + "%");
const cls = (v) => (v == null || Math.abs(v) < 0.01 ? "flat" : v > 0 ? "up" : "down");

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

function metric(label, value, note) {
  return `<div class="m"><span class="m-l">${label}</span><span class="m-v">${value}</span>${note ? `<span class="m-n">${note}</span>` : ""}</div>`;
}

function detail(s) {
  const sig = s.signal || { label: "—", dir: "flat", why: "" };
  const real = [
    metric("Momentum", esc(sig.label), esc(sig.why)),
    metric("24h", pct(s.c24), "vs prior close"),
    metric("7d", pct(s.c7), "~5 trading days"),
    metric("30d", pct(s.c30), "~1 month"),
    metric("Volume", fmtBig(s.volume), "last session"),
  ].join("");
  return `<div class="detail">
    <div class="d-left">
      ${sparkSvg(s.spark, sig.dir)}
      <p class="d-state"><span class="state state-${sig.dir}">${esc(sig.label)}</span></p>
      <p class="d-why">${esc(sig.why)}</p>
    </div>
    <div class="d-right">
      <p class="d-h">Descriptive metrics</p>
      <div class="metrics">${real}</div>
      <p class="d-h">No forecast here <span class="d-h-note">(descriptive only — scored 24h reads are on the Crypto page)</span></p>
    </div>
  </div>`;
}

function row(s) {
  const sig = s.signal || { label: "—", dir: "flat" };
  return `<tr class="coin-row" data-id="${esc(s.symbol)}" tabindex="0" aria-expanded="false">
    <td class="rk">${s.rank ?? "—"}</td>
    <td class="nm"><span><b>${esc(s.name)}</b><i>${esc(s.symbol)}</i></span></td>
    <td class="px">${fmtUsd(s.price)}</td>
    <td class="ch ${cls(s.c24)}">${pct(s.c24)}</td>
    <td class="ch ${cls(s.c7)} hide-sm">${pct(s.c7)}</td>
    <td class="ch ${cls(s.c30)} hide-sm">${pct(s.c30)}</td>
    <td class="vol hide-md">${fmtBig(s.volume)}</td>
    <td class="sig"><span class="state state-${sig.dir}">${esc(sig.label)}</span></td>
  </tr>
  <tr class="detail-row" data-detail="${esc(s.symbol)}" hidden><td colspan="8">${detail(s)}</td></tr>`;
}

function render(block) {
  const st = document.getElementById("data-status");
  const tbody = document.getElementById("stock-body");
  const items = (block && block.items) || [];
  if (st) st.textContent = block && block.available
    ? "delayed · " + (block.source || "public data")
    : "data unavailable";
  if (!tbody) return;
  tbody.innerHTML = items.length
    ? items.map(row).join("")
    : `<tr><td colspan="8" class="empty">Couldn't load stock data right now. Try again shortly.</td></tr>`;
}

function toggleRow(tr) {
  const id = tr.dataset.id;
  const det = document.querySelector(`tr[data-detail="${CSS.escape(id)}"]`);
  if (!det) return;
  if (det.hasAttribute("hidden")) { det.removeAttribute("hidden"); tr.setAttribute("aria-expanded", "true"); }
  else { det.setAttribute("hidden", ""); tr.setAttribute("aria-expanded", "false"); }
}

document.addEventListener("click", (ev) => {
  const tr = ev.target.closest && ev.target.closest(".coin-row");
  if (tr) toggleRow(tr);
});
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  const tr = ev.target.closest && ev.target.closest(".coin-row");
  if (tr) { ev.preventDefault(); toggleRow(tr); }
});

async function load() {
  try {
    const r = await fetch("../stocks.json", { cache: "no-store" });
    render(r.ok ? await r.json() : null);
  } catch (_) {
    render(null);  // fail-open: honest empty state
  }
}

load();
setInterval(load, 300000);  // refresh every 5 min (delayed data; no urgency)
