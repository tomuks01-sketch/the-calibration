"use strict";
/* The Calibration — Football (international match forecasts, scored in public).
 *
 * Reads our own server-computed forecasts from ../football_ledger.json (OPEN =
 * upcoming) and the track record from ../football_scoreboard.json. Thin renderer
 * only: the Elo + Poisson model runs server-side (ESPN has no CORS). Never
 * "team X will win" — probabilities + scenarios, scored with RPS vs result AND
 * market.
 */

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => (v == null ? "—" : Math.round(v * 100) + "%");

const COMP = {
  "fifa.world": "World Cup", "uefa.champions": "Champions Lg", "uefa.euro": "Euro",
  "conmebol.america": "Copa América", "fifa.worldq.uefa": "WC Qual",
  "fifa.worldq.conmebol": "WC Qual", "uefa.nations": "Nations Lg",
};

function probBar(ph, pd, pa) {
  const h = Math.round((ph || 0) * 100), d = Math.round((pd || 0) * 100), a = Math.round((pa || 0) * 100);
  return `<span class="pbar" role="img" aria-label="home ${h}%, draw ${d}%, away ${a}%">
    <span class="pbar-h" style="width:${h}%"></span>
    <span class="pbar-d" style="width:${d}%"></span>
    <span class="pbar-a" style="width:${a}%"></span>
  </span>`;
}

function metric(label, value, note) {
  return `<div class="m"><span class="m-l">${label}</span><span class="m-v">${value}</span>${note ? `<span class="m-n">${note}</span>` : ""}</div>`;
}

const odds = (p) => (p == null || p <= 0) ? "—" : (1 / p).toFixed(2);

function marketsHtml(e) {
  const m = e.markets || {};
  const sum = (a, b) => (a != null && b != null) ? a + b : null;
  const under = (p) => (p == null) ? null : 1 - p;
  const row = (label, p) =>
    `<div class="mk-row"><span class="mk-l">${label}</span><span class="mk-p">${pct(p)}</span><span class="mk-o">${odds(p)}</span></div>`;
  const cmp = (e.marketProbHome != null)
    ? `<p class="mk-cmp">Bookmaker implied: ${pct(e.marketProbHome)} · ${pct(e.marketProbDraw)} · ${pct(e.marketProbAway)} — scored against ours.</p>`
    : "";
  return `<div class="markets-grid">
    <div class="mk-head"><span>Market</span><span>Prob</span><span>Fair odds</span></div>
    ${row(esc(e.home) + " win", e.probHome)}
    ${row("Draw", e.probDraw)}
    ${row(esc(e.away) + " win", e.probAway)}
    ${row("Double chance — " + esc(e.home) + " or draw", sum(e.probHome, e.probDraw))}
    ${row("Double chance — draw or " + esc(e.away), sum(e.probDraw, e.probAway))}
    ${row("Over 1.5 goals", m.over15)}
    ${row("Over 2.5 goals", m.over25)}
    ${row("Under 2.5 goals", under(m.over25))}
    ${row("Over 3.5 goals", m.over35)}
    ${row("Both teams to score", m.btts)}
  </div>
  <p class="mk-note">Fair odds = 1 ÷ our probability (no bookmaker margin). Where a bookmaker's odds are <b>higher</b> than ours, they rate it less likely than we do — that's where to look. Total expected goals: <b>${m.totalGoals ?? "—"}</b>. Analytics, not advice — we don't tell you to bet.</p>
  ${cmp}`;
}

function detail(e) {
  const scen = (e.topScorelines || []).slice(0, 5)
    .map((s) => `<span class="scen"><b>${esc(s.score)}</b> ${Math.round((s.prob || 0) * 100)}%</span>`).join("");
  const why = (e.why || []).map((w) => `<li>${esc(w)}</li>`).join("");
  return `<div class="detail">
    <div class="d-left">
      <p class="d-h">Scoreline scenarios <span class="d-h-note">(the most likely score is usually only ~1 in 8 — a spread, not a pick)</span></p>
      <div class="scen-row">${scen || "—"}</div>
      <p class="d-state">expected goals <span class="state state-flat">${e.expGoalsHome ?? "—"} – ${e.expGoalsAway ?? "—"}</span></p>
      <p class="d-h">Why</p>
      <ul class="why-list">${why || "<li>—</li>"}</ul>
    </div>
    <div class="d-right">
      <p class="d-h">Markets · our fair odds</p>
      ${marketsHtml(e)}
    </div>
  </div>`;
}

function fixtureRow(e) {
  const t0 = e.topScorelines && e.topScorelines[0];
  const likely = t0 ? `${esc(t0.score)} <i class="lk-p">${Math.round((t0.prob || 0) * 100)}%</i>` : "—";
  return `<tr class="coin-row fx-row" data-id="${esc(e.matchId)}" tabindex="0" aria-expanded="false">
    <td class="comp hide-sm">${esc(COMP[e.competition] || e.competition || "")}</td>
    <td class="fx-match"><b>${esc(e.home)}</b> <i>v</i> <b>${esc(e.away)}</b></td>
    <td class="fx-prob">${probBar(e.probHome, e.probDraw, e.probAway)}<span class="fx-nums">${pct(e.probHome)} · ${pct(e.probDraw)} · ${pct(e.probAway)}</span></td>
    <td class="fx-likely">${likely}</td>
  </tr>
  <tr class="detail-row" data-detail="${esc(e.matchId)}" hidden><td colspan="4">${detail(e)}</td></tr>`;
}

function renderFixtures(ledger) {
  const tbody = document.getElementById("fixtures-body");
  const st = document.getElementById("data-status");
  const open = ((ledger && ledger.entries) || [])
    .filter((e) => e.status === "OPEN" && e.probHome != null)
    .sort((a, b) => (a.kickoff || "").localeCompare(b.kickoff || ""));
  if (st) st.textContent = ledger ? "model · scored in public" : "data unavailable";
  if (!tbody) return;
  tbody.innerHTML = open.length
    ? open.map(fixtureRow).join("")
    : `<tr><td colspan="4" class="empty">No upcoming international games locked right now — they appear as fixtures are scheduled.</td></tr>`;
}

function renderTrack(sb) {
  const el = document.getElementById("football-track");
  if (!el) return;
  const tile = (v, l) => `<div class="cs-tile"><span class="cs-v">${v}</span><span class="cs-l">${l}</span></div>`;
  if (!sb || !sb.counts) { el.innerHTML = `<p class="empty">Track record loads with the next snapshot.</p>`; return; }
  const c = sb.counts, gated = (sb.confidence || "none") !== "none";
  const m = sb.model || {}, mk = sb.market || {};
  const rps = (gated && m.meanRps != null) ? m.meanRps : "—";
  const acc = (gated && m.accuracy != null) ? Math.round(m.accuracy * 100) + "%" : "—";
  const calErr = (gated && m.calibrationError != null) ? m.calibrationError : "—";
  const skill = (mk.skillVsMarket != null) ? (mk.skillVsMarket > 0 ? "+" : "") + mk.skillVsMarket : (mk.n ? "accruing " + mk.n + "/10" : "—");
  el.innerHTML =
    tile(c.resolved, "resolved · scored") +
    tile(c.open, "locked · awaiting result") +
    tile(rps, "RPS · lower better") +
    tile(acc, "top-pick accuracy") +
    tile(calErr, "calibration error · lower better") +
    tile(skill, "RPS skill vs market") +
    `<p class="track-note">${gated
      ? "Scored with RPS (lower = better). Accuracy = how often our most-likely outcome was right. 'Skill vs market' = market RPS − ours (positive = we beat the odds; accrues as resolved matches carry odds). Shown win or lose."
      : "Track record not yet meaningful — " + c.resolved + " resolved. Forecasts are locked before kickoff and graded the moment matches finish; this fills over the coming weeks. If we never beat the market, it will say so."}</p>`;
}

function toggleRow(tr) {
  const id = tr.dataset.id;
  const det = document.querySelector(`tr[data-detail="${CSS.escape(id)}"]`);
  if (!det) return;
  if (det.hasAttribute("hidden")) { det.removeAttribute("hidden"); tr.setAttribute("aria-expanded", "true"); }
  else { det.setAttribute("hidden", ""); tr.setAttribute("aria-expanded", "false"); }
}
document.addEventListener("click", (ev) => {
  const tr = ev.target.closest && ev.target.closest(".fx-row");
  if (tr) toggleRow(tr);
});
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  const tr = ev.target.closest && ev.target.closest(".fx-row");
  if (tr) { ev.preventDefault(); toggleRow(tr); }
});

async function load() {
  try {
    const r = await fetch("../football_ledger.json", { cache: "no-store" });
    renderFixtures(r.ok ? await r.json() : null);
  } catch (_) { renderFixtures(null); }
  try {
    const r2 = await fetch("../football_scoreboard.json", { cache: "no-store" });
    renderTrack(r2.ok ? await r2.json() : null);
  } catch (_) { renderTrack(null); }
}

load();
setInterval(load, 300000);
