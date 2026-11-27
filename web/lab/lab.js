// Strategy Lab — renders strategies.json. Built with DOM nodes and
// textContent only, so nothing in the data file is ever parsed as HTML.
(function () {
  "use strict";

  const VERDICT_ORDER = ["passed", "fragile", "failed"];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function fmt(value, unit) {
    if (value === null || value === undefined) return "—";
    const sign = value > 0 && (unit === "pts") ? "+" : "";
    const num = Math.abs(value) >= 100 ? value.toFixed(0) : String(value);
    if (unit === "%" || unit === "%/yr") return `${sign}${num}%${unit === "%/yr" ? " a year" : ""}`;
    if (unit === "pts") return `${sign}${num} pts`;
    return `${sign}${num}`;
  }

  // Two LED meters on a shared scale: the strategy and what it was measured against.
  function compareBlock(cmp) {
    if (!cmp) return null;
    const wrap = el("div", "cmp");
    wrap.appendChild(el("p", "cmp-label", cmp.label));
    const max = Math.max(Math.abs(cmp.strategy), Math.abs(cmp.benchmark), 1);
    const rows = [
      { name: "Strategy", value: cmp.strategy, cls: "s" },
      { name: cmp.benchmarkName || "Benchmark", value: cmp.benchmark, cls: "b" },
    ];
    rows.forEach((r) => {
      const row = el("div", `cmp-row ${r.cls}${r.value < 0 ? " neg" : ""}`);
      row.appendChild(el("span", "cmp-name", r.name));
      const track = el("i", "cmp-track");
      const fill = el("b", "cmp-fill");
      fill.style.width = `${Math.round((Math.abs(r.value) / max) * 100)}%`;
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "cmp-val", fmt(r.value, cmp.unit)));
      wrap.appendChild(row);
    });
    return wrap;
  }

  function card(s) {
    const art = el("article", `lab-card v-${s.verdict}`);
    art.id = s.id;

    const top = el("div", "lab-top");
    const titleWrap = el("div");
    titleWrap.appendChild(el("p", "lab-period", s.period));
    titleWrap.appendChild(el("h2", "lab-name", s.name));
    top.appendChild(titleWrap);
    top.appendChild(el("span", `badge ${s.verdict}`, s.verdictText));
    art.appendChild(top);

    const dl = el("dl", "lab-facts");
    [["The idea", s.idea], ["Pass mark", s.bar]].forEach(([k, v]) => {
      const d = el("div");
      d.appendChild(el("dt", null, k));
      d.appendChild(el("dd", null, v));
      dl.appendChild(d);
    });
    art.appendChild(dl);

    const meters = el("div", "lab-meters");
    const a = compareBlock(s.compare);
    const b = compareBlock(s.extra && { ...s.extra, benchmarkName: s.extra.benchmarkName || s.compare.benchmarkName });
    if (a) meters.appendChild(a);
    if (b) meters.appendChild(b);
    art.appendChild(meters);

    art.appendChild(el("p", "lab-finding", s.finding));
    art.appendChild(el("p", "lab-caveat", `Limits: ${s.caveats}`));
    return art;
  }

  function renderTally(list) {
    const counts = { passed: 0, fragile: 0, failed: 0 };
    list.forEach((s) => { counts[s.verdict] = (counts[s.verdict] || 0) + 1; });
    const row = document.getElementById("tally");
    VERDICT_ORDER.forEach((v) => {
      for (let i = 0; i < counts[v]; i += 1) row.appendChild(el("i", `cell ${v}`));
    });
    VERDICT_ORDER.forEach((v) => {
      const node = document.getElementById(`n-${v}`);
      if (node) node.textContent = String(counts[v]);
    });
    row.setAttribute("aria-label", `${counts.passed} passed, ${counts.fragile} fragile, ${counts.failed} did not pass`);
  }

  function showError() {
    const box = document.getElementById("cards");
    box.textContent = "";
    box.appendChild(el("p", "empty", "The test results could not be loaded. Refresh the page to try again."));
  }

  fetch("strategies.json", { cache: "no-cache" })
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((data) => {
      const list = Array.isArray(data.strategies) ? data.strategies : [];
      if (!list.length) throw new Error("no strategies");
      const sorted = [...list].sort((x, y) => VERDICT_ORDER.indexOf(x.verdict) - VERDICT_ORDER.indexOf(y.verdict));
      renderTally(sorted);
      const box = document.getElementById("cards");
      box.textContent = "";
      sorted.forEach((s) => box.appendChild(card(s)));
      const tested = document.getElementById("tested");
      if (tested && data.testedBetween) tested.textContent = data.testedBetween;
    })
    .catch(showError);
})();
