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
  const row = (label, p) =>
    `<div class="mk-row"><span class="mk-l">${label}</span><span class="mk-p">${pct(p)}</span><span class="mk-o">${odds(p)}</span></div>`;
  // The 3-way win/draw/away % is already in the fixture row — show only the
  // bookmaker comparison here (ours vs theirs, side by side) to avoid repeating it.
  const cmp = (e.marketProbHome != null)
    ? `<p class="mk-cmp">Win / draw / win — <b>ours</b> ${pct(e.probHome)} · ${pct(e.probDraw)} · ${pct(e.probAway)} vs <b>bookmaker</b> ${pct(e.marketProbHome)} · ${pct(e.marketProbDraw)} · ${pct(e.marketProbAway)}. Both scored — see the track record below.</p>`
    : `<p class="mk-cmp">Win / draw / win is in the row above. No bookmaker odds posted for this match yet.</p>`;
  // Goal & double-chance markets only — the bets the row does NOT already show.
  return `${cmp}
  <div class="markets-grid">
    <div class="mk-head"><span>Market</span><span>Prob</span><span>Fair odds</span></div>
    ${row("Double chance — " + esc(e.home) + " or draw", sum(e.probHome, e.probDraw))}
    ${row("Double chance — draw or " + esc(e.away), sum(e.probDraw, e.probAway))}
    ${row("Over 1.5 goals", m.over15)}
    ${row("Over 2.5 goals", m.over25)}
    ${row("Over 3.5 goals", m.over35)}
    ${row("Both teams to score", m.btts)}
  </div>
  <p class="mk-note">Fair odds = 1 ÷ our probability (no bookmaker margin). Total expected goals: <b>${m.totalGoals ?? "—"}</b>. Analytics, not advice — we don't tell you to bet.</p>`;
}

// Shared between upcoming and resolved rows (so the two views don't drift).
function scenarioChips(e) {
  return (e.topScorelines || []).slice(0, 5)
    .map((s) => {
      const hit = e.finalScore && s.score === e.finalScore ? " scen-hit" : "";
      return `<span class="scen${hit}"><b>${esc(s.score)}</b> ${Math.round((s.prob || 0) * 100)}%</span>`;
    }).join("") || "—";
}
function whyList(e) {
  return (e.why || []).map((w) => `<li>${esc(w)}</li>`).join("") || "<li>—</li>";
}
function topPickOutcome(e) {
  const m = Math.max(e.probHome || 0, e.probDraw || 0, e.probAway || 0);
  return m === e.probHome ? "home" : m === e.probAway ? "away" : "draw";
}

function detail(e) {
  return `<div class="detail">
    <div class="d-left">
      <p class="d-h">Scoreline scenarios <span class="d-h-note">(the most likely score is usually only ~1 in 8 — a spread, not a pick)</span></p>
      <div class="scen-row">${scenarioChips(e)}</div>
      <p class="d-state">expected goals <span class="state state-flat">${e.expGoalsHome ?? "—"} – ${e.expGoalsAway ?? "—"}</span></p>
      <p class="d-h">Why</p>
      <ul class="why-list">${whyList(e)}</ul>
    </div>
    <div class="d-right">
      <p class="d-h">Markets · our fair odds</p>
      ${marketsHtml(e)}
    </div>
  </div>`;
}

function resolvedDetail(e) {
  const our = topPickOutcome(e);
  const ourLabel = our === "home" ? esc(e.home) + " win" : our === "away" ? esc(e.away) + " win" : "Draw";
  const ourPct = pct(our === "home" ? e.probHome : our === "away" ? e.probAway : e.probDraw);
  const right = our === e.outcome;
  const mkt = e.rpsMarket != null ? ` · market RPS <b>${e.rpsMarket}</b>` : "";
  const beat = e.beatMarket == null ? ""
    : e.beatMarket ? `<span class="res-badge beat">beat the market</span>`
    : `<span class="res-badge lost">market was closer</span>`;
  return `<div class="detail detail-1col">
    <div class="d-left">
      <p class="d-h">Result</p>
      <p class="res-summary">Final <b>${esc(e.finalScore || "—")}</b>. Our most-likely call was
        <b>${ourLabel}</b> (${ourPct}) — <span class="${right ? "res-ok" : "res-no"}">${right ? "right" : "wrong"}</span>.
        RPS <b>${e.rpsModel ?? "—"}</b> (lower is better)${mkt}. ${beat}</p>
      <p class="d-h">Scoreline scenarios <span class="d-h-note">(what we gave beforehand — the actual score is highlighted if we had it)</span></p>
      <div class="scen-row">${scenarioChips(e)}</div>
      <p class="d-h">Why we had it this way</p>
      <ul class="why-list">${whyList(e)}</ul>
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

// Data freshness without adding a churning field to the ledger: derive it from
// the newest openedAt/resolvedAt already in the data (so the file only changes
// when a forecast is actually locked or graded, not every cron run).
function relTime(iso) {
  const t = Date.parse(iso);
  if (isNaN(t)) return null;
  const s = (Date.now() - t) / 1000;
  if (s < 0) return "just now";
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
  if (s < 86400) return Math.round(s / 3600) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
function lastActivity(ledger) {
  let latest = "";
  for (const e of (ledger && ledger.entries) || []) {
    for (const ts of [e.resolvedAt, e.openedAt]) {
      if (ts && ts > latest) latest = ts;
    }
  }
  return latest || null;
}

function renderFixtures(ledger) {
  const tbody = document.getElementById("fixtures-body");
  const st = document.getElementById("data-status");
  const open = ((ledger && ledger.entries) || [])
    .filter((e) => e.status === "OPEN" && e.probHome != null)
    .sort((a, b) => (a.kickoff || "").localeCompare(b.kickoff || ""));
  if (st) {
    if (!ledger) {
      st.textContent = "data unavailable";
    } else {
      const rel = relTime(lastActivity(ledger));
      st.textContent = "scored in public" + (rel ? " · updated " + rel : "");
    }
  }
  if (!tbody) return;
  tbody.innerHTML = open.length
    ? open.map(fixtureRow).join("")
    : `<tr><td colspan="4" class="empty">No upcoming games locked right now — forecasts lock a few days before kickoff. Recently scored ones are below.</td></tr>`;
}

function resolvedRow(e) {
  const right = topPickOutcome(e) === e.outcome;
  const mark = right ? `<i class="res-ok" title="our most-likely outcome was right">✓</i>`
    : `<i class="res-no" title="our most-likely outcome was wrong">✗</i>`;
  return `<tr class="coin-row fx-row" data-id="${esc(e.matchId)}" tabindex="0" aria-expanded="false">
    <td class="comp hide-sm">${esc(COMP[e.competition] || e.competition || "")}</td>
    <td class="fx-match"><b>${esc(e.home)}</b> <i>v</i> <b>${esc(e.away)}</b></td>
    <td class="fx-prob">${probBar(e.probHome, e.probDraw, e.probAway)}<span class="fx-nums">${pct(e.probHome)} · ${pct(e.probDraw)} · ${pct(e.probAway)}</span></td>
    <td class="fx-likely fx-result"><b>${esc(e.finalScore || "—")}</b> ${mark}</td>
  </tr>
  <tr class="detail-row" data-detail="${esc(e.matchId)}" hidden><td colspan="4">${resolvedDetail(e)}</td></tr>`;
}

function renderResolved(ledger) {
  const sec = document.getElementById("resolved-wrap");
  const tbody = document.getElementById("resolved-body");
  if (!sec || !tbody) return;
  const done = ((ledger && ledger.entries) || [])
    .filter((e) => e.status === "RESOLVED" && e.probHome != null && e.finalScore)
    .sort((a, b) => (b.resolvedAt || "").localeCompare(a.resolvedAt || ""))
    .slice(0, 12);
  if (!done.length) { sec.setAttribute("hidden", ""); return; }
  sec.removeAttribute("hidden");
  tbody.innerHTML = done.map(resolvedRow).join("");
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
  // Until there's enough N (gated), show only the real counts — not a wall of
  // "—" metric tiles. The per-match RPS and result are already in the resolved
  // section above; the aggregate unlocks once it's actually meaningful.
  const counts = tile(c.resolved, "resolved · scored") + tile(c.open, "locked · awaiting result");
  const metrics = tile(rps, "RPS · lower better") + tile(acc, "top-pick accuracy") +
    tile(calErr, "calibration error · lower better") + tile(skill, "RPS skill vs market");
  el.innerHTML = counts + (gated ? metrics : "") +
    `<p class="track-note">${gated
      ? "Scored with RPS (lower = better). Accuracy = how often our most-likely outcome was right. 'Skill vs market' = market RPS − ours (positive = we beat the odds; accrues as resolved matches carry odds). Shown win or lose."
      : "Aggregate stats unlock once enough matches resolve — " + c.resolved + " scored so far" + (c.resolved > 0 ? " (see them above)" : "") + ". Forecasts lock before kickoff and grade the moment matches finish. If we never beat the market, it will say so."}</p>`;
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
  let ledger = null;
  try {
    const r = await fetch("../football_ledger.json", { cache: "no-store" });
    ledger = r.ok ? await r.json() : null;
  } catch (_) { ledger = null; }
  renderFixtures(ledger);
  renderResolved(ledger);
  try {
    const r2 = await fetch("../football_scoreboard.json", { cache: "no-store" });
    renderTrack(r2.ok ? await r2.json() : null);
  } catch (_) { renderTrack(null); }
}

load();
setInterval(load, 300000);
