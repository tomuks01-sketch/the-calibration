"use strict";
/* The Calibration — cinematic hero field (lit calibration stage).
   Self-hosted Canvas 2D (no Three.js / no CDN — £0, CSP-clean, offline-safe).
   Depth layers, back to front:
     1. receding perspective grid floor + amber horizon line
     2. soft contact shadow grounding the sphere on the floor
     3. a faded floor reflection of the sphere's warm points
     4. the calibration sphere: fibonacci points, RIM-LIT (cool key up-left,
        amber core glow), precomputed divergence links, pointer parallax.
   Honest decoration only — visualises nothing real, carries no data claim.
   Perf: nearest-neighbour links precomputed once (O(n) per frame); 30fps +
   fewer points on mobile; gradients reused. Respects reduced-motion. */

(function () {
  const canvas = document.getElementById("hero-canvas");
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const mobile = coarse || window.innerWidth < 768;

  const AMBER = "255, 180, 92";
  const COOL = "150, 178, 210";
  const KEY = "190, 210, 240";   // cool key-light tint on lit side
  const LINK = "120, 148, 188";
  const GRID = "120, 150, 190";

  let W = 0, H = 0, DPR = 1, cx = 0, cy = 0, R = 0, horizon = 0;
  const POINTS = reduced ? 80 : (mobile ? 120 : 200);
  const TARGET_MS = mobile ? 33 : 0;            // 30fps cap on mobile
  const pts = [];
  let coreGlow = null;                          // reused per resize, not per frame

  // ---- pointer parallax (damped) ----
  let pTargetX = 0, pTargetY = 0, pX = 0, pY = 0;
  if (!reduced && !coarse) {
    window.addEventListener("pointermove", (e) => {
      pTargetX = (e.clientX / window.innerWidth - 0.5) * 2;   // -1..1
      pTargetY = (e.clientY / window.innerHeight - 0.5) * 2;
    }, { passive: true });
  }

  function buildSphere() {
    pts.length = 0;
    const phi = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < POINTS; i++) {
      const y = 1 - (i / (POINTS - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = phi * i;
      pts.push({
        x: Math.cos(th) * r, y: y, z: Math.sin(th) * r,
        s: 0.5 + Math.random() * 1.5,
        tw: Math.random() * Math.PI * 2,
        warm: Math.random() > 0.82,
        near: -1,
      });
    }
    // Precompute nearest neighbour ONCE (topology is rotation-invariant in 3D).
    for (let i = 0; i < pts.length; i++) {
      let best = -1, bd = Infinity;
      for (let j = 0; j < pts.length; j++) {
        if (j === i) continue;
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y, dz = pts[i].z - pts[j].z;
        const d = dx * dx + dy * dy + dz * dz;
        if (d < bd) { bd = d; best = j; }
      }
      pts[i].near = best;
    }
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(1, Math.floor(rect.width));
    H = Math.max(1, Math.floor(rect.height));
    canvas.width = W * DPR;
    canvas.height = H * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    cx = W * 0.62; cy = H * 0.44;
    R = Math.min(W, H) * 0.30;
    horizon = H * 0.62;
    coreGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.6);
    coreGlow.addColorStop(0, `rgba(${AMBER}, 0.28)`);
    coreGlow.addColorStop(0.4, `rgba(${AMBER}, 0.07)`);
    coreGlow.addColorStop(1, "rgba(0,0,0,0)");
  }

  function drawGrid(t) {
    const drift = (t * 0.012) % 60;
    ctx.save();
    for (let i = 0; i < 26; i++) {
      const p = i / 25, ease = p * p;
      const y = horizon + ease * (H - horizon) * 1.05 + drift * (1 - p);
      if (y > H + 2 || y < horizon) continue;
      ctx.strokeStyle = `rgba(${GRID}, ${(1 - p) * 0.22})`;
      ctx.lineWidth = 0.6;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    const vanish = W * 0.5;
    for (let i = -12; i <= 12; i++) {
      const xb = vanish + i * (W / 9);
      ctx.strokeStyle = `rgba(${GRID}, ${Math.max(0, 0.16 - Math.abs(i) * 0.006)})`;
      ctx.lineWidth = 0.6;
      ctx.beginPath(); ctx.moveTo(vanish + i * 8, horizon); ctx.lineTo(xb, H); ctx.stroke();
    }
    // bright amber horizon line + glow
    ctx.strokeStyle = `rgba(${AMBER}, 0.14)`; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, horizon); ctx.lineTo(W, horizon); ctx.stroke();
    const hg = ctx.createLinearGradient(0, horizon - 70, 0, horizon + 50);
    hg.addColorStop(0, "rgba(0,0,0,0)"); hg.addColorStop(1, `rgba(${AMBER}, 0.07)`);
    ctx.fillStyle = hg; ctx.fillRect(0, horizon - 70, W, 120);
    ctx.restore();
  }

  function project(p, ay, ax) {
    let x = p.x, y = p.y, z = p.z;
    const ca = Math.cos(ay), sa = Math.sin(ay);
    let x1 = x * ca - z * sa, z1 = x * sa + z * ca;
    const cb = Math.cos(ax), sb = Math.sin(ax);
    let y1 = y * cb - z1 * sb, z2 = y * sb + z1 * cb;
    const persp = 1 / (1.95 - z2);
    return { sx: cx + x1 * R * persp * 1.7, sy: cy + y1 * R * persp * 1.7, depth: z2, persp, nx: x1, ny: y1 };
  }

  let t = 0, last = 0;
  function frame() {
    ctx.clearRect(0, 0, W, H);
    drawGrid(t);

    // damped parallax
    pX += (pTargetX - pX) * 0.05; pY += (pTargetY - pY) * 0.05;
    const ay = t * 0.00017 + pX * 0.5;
    const ax = 0.40 + Math.sin(t * 0.00008) * 0.12 + pY * 0.18;

    const proj = pts.map((p) => ({ p, ...project(p, ay, ax) }));

    // contact shadow on the floor (grounds the sphere)
    ctx.save();
    ctx.translate(cx, horizon);
    ctx.scale(1, 0.26);
    const cs = ctx.createRadialGradient(0, 0, 0, 0, 0, R * 1.15);
    cs.addColorStop(0, `rgba(${AMBER}, 0.13)`); cs.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = cs; ctx.beginPath(); ctx.arc(0, 0, R * 1.15, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // floor reflection of warm points (cheap "polished floor")
    for (const pp of proj) {
      if (!pp.p.warm || pp.sy > horizon) continue;
      const ry = 2 * horizon - pp.sy;
      if (ry > H) continue;
      const fade = Math.max(0, 1 - (ry - horizon) / (H - horizon)) * 0.18;
      ctx.fillStyle = `rgba(${AMBER}, ${fade})`;
      ctx.beginPath(); ctx.arc(pp.sx, ry, pp.p.s * pp.persp * 1.4, 0, Math.PI * 2); ctx.fill();
    }

    // divergence links (precomputed nearest neighbour — O(n))
    ctx.lineWidth = 0.6;
    for (let i = 0; i < proj.length; i++) {
      const a = proj[i], b = proj[a.p.near];
      if (!b) continue;
      const front = (a.depth + b.depth) / 2;
      ctx.strokeStyle = `rgba(${LINK}, ${Math.max(0, (front + 1) / 2) * 0.16})`;
      ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke();
    }

    // amber core glow (reused gradient)
    ctx.fillStyle = coreGlow;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.6, 0, Math.PI * 2); ctx.fill();

    // points back-to-front, rim-lit: lit side (toward up-left key) brightens
    proj.sort((a, b) => a.depth - b.depth);
    for (const pp of proj) {
      const front = (pp.depth + 1) / 2;
      const tw = 0.7 + Math.sin(t * 0.002 + pp.p.tw) * 0.3;
      const size = pp.p.size = pp.p.s * pp.persp * (0.6 + front) * tw;
      // key light from up-left: nx<0 & ny<0 => lit
      const lit = Math.max(0, (-pp.nx * 0.7 - pp.ny * 0.7));
      const alpha = 0.22 + front * 0.62 + lit * 0.25;
      if (pp.p.warm) {
        ctx.fillStyle = `rgba(${AMBER}, ${Math.min(1, alpha)})`;
      } else {
        // cool points pick up the cool key on their lit side
        const tint = lit > 0.25 ? KEY : COOL;
        ctx.fillStyle = `rgba(${tint}, ${Math.min(1, alpha * 0.85)})`;
      }
      ctx.beginPath(); ctx.arc(pp.sx, pp.sy, Math.max(0.4, size), 0, Math.PI * 2); ctx.fill();
      if (pp.p.warm && front > 0.6) {
        ctx.fillStyle = `rgba(${AMBER}, ${alpha * 0.22})`;
        ctx.beginPath(); ctx.arc(pp.sx, pp.sy, size * 3.4, 0, Math.PI * 2); ctx.fill();
      }
    }
  }

  let raf = null;
  function loop(now) {
    if (TARGET_MS && now - last < TARGET_MS) { raf = requestAnimationFrame(loop); return; }
    last = now; t = now; frame(); raf = requestAnimationFrame(loop);
  }
  function start() {
    resize(); buildSphere();
    if (reduced) { t = 8000; frame(); return; }
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(loop);
  }

  let visible = true;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = null; }
    else if (!reduced && visible && !raf) raf = requestAnimationFrame(loop);
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((e) => {
      visible = e[0].isIntersecting;
      if (!visible) { if (raf) cancelAnimationFrame(raf); raf = null; }
      else if (!reduced && !document.hidden && !raf) raf = requestAnimationFrame(loop);
    }, { threshold: 0 }).observe(canvas);
  }
  let rt = null;
  window.addEventListener("resize", () => {
    clearTimeout(rt);
    rt = setTimeout(() => { resize(); buildSphere(); if (reduced) frame(); }, 160);
  });
  start();
})();
