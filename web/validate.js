#!/usr/bin/env node
// validate.js — lightweight schema smoke-test for web/ JSON files.
// Usage: node validate.js
// Exits 0 if all checks pass, 1 on first failure.

"use strict";
const fs = require("fs");
const path = require("path");

const dir = __dirname;
let ok = true;

function fail(msg) { console.error("FAIL:", msg); ok = false; }
function pass(msg) { console.log("PASS:", msg); }

function loadJson(file) {
  const p = path.join(dir, file);
  if (!fs.existsSync(p)) { fail(`${file} — file not found`); return null; }
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch (e) {
    fail(`${file} — invalid JSON: ${e.message}`);
    return null;
  }
}

// ---- data.json ----
const data = loadJson("data.json");
if (data) {
  if (!Array.isArray(data.events)) fail("data.json: missing events array");
  else {
    pass(`data.json: ${data.events.length} events`);
    data.events.forEach((e, i) => {
      if (typeof e.id !== "string" && typeof e.id !== "number") fail(`data.json events[${i}]: missing id`);
      if (typeof e.title !== "string") fail(`data.json events[${i}]: missing title`);
      if (typeof e.volume !== "number") fail(`data.json events[${i}] (${e.title}): volume is not a number`);
    });
  }
  if (typeof data.generatedAt !== "string") fail("data.json: missing generatedAt");
  else pass("data.json: generatedAt present");
}

// ---- ledger.json ----
const ledger = loadJson("ledger.json");
if (ledger) {
  if (!Array.isArray(ledger.entries)) fail("ledger.json: missing entries array");
  else {
    pass(`ledger.json: ${ledger.entries.length} entries`);
    ledger.entries.forEach((e, i) => {
      if (typeof e.callId !== "string") fail(`ledger.json entries[${i}]: missing callId`);
      const validStatus = ["PENDING", "RESOLVED", "VOID"];
      if (!validStatus.includes(e.status)) fail(`ledger.json entries[${i}] (${e.callId}): invalid status "${e.status}"`);
      if (typeof e.modelProb !== "number") fail(`ledger.json entries[${i}] (${e.callId}): modelProb is not a number`);
    });
  }
}

// ---- scoreboard.json ----
const sb = loadJson("scoreboard.json");
if (sb) {
  if (!sb.counts || typeof sb.counts.resolved !== "number") fail("scoreboard.json: missing counts.resolved");
  else pass(`scoreboard.json: ${sb.counts.resolved} resolved, ${sb.counts.pending} pending`);
  if (typeof sb.confidence !== "string") fail("scoreboard.json: missing confidence field");
  else pass(`scoreboard.json: confidence = "${sb.confidence}"`);
}

// ---- features.json ----
const features = loadJson("features.json");
if (features) {
  if (!Array.isArray(features.records)) fail("features.json: missing records array");
  else pass(`features.json: ${features.records.length} records`);
}

// ---- weights.json ----
const weights = loadJson("weights.json");
if (weights) {
  if (!weights.weights || typeof weights.weights.crowd !== "number") fail("weights.json: missing weights.crowd");
  else pass(`weights.json: crowd=${weights.weights.crowd}, baseline=${weights.weights.baseline}`);
}

if (ok) {
  console.log("\nAll checks passed.");
  process.exit(0);
} else {
  console.error("\nOne or more checks failed — see above.");
  process.exit(1);
}
