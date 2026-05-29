"use strict";
/* The Calibration — hero calibration sphere.
   Self-contained Canvas 2D (no Three.js / no CDN — £0, CSP-clean, offline-safe).
   A slowly rotating point-sphere ("calibration field") with nearest-neighbour
   divergence links and a soft amber core glow. Honest decoration only — it
   visualises nothing real, so it carries no data claim. Respects
   prefers-reduced-motion (renders a single static frame, no RAF loop). */

(function () {
  const canvas = document.getElementById("hero-canvas");
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- colour tokens (kept in sync with styles.css accents) ----
  const AMBER = "255, 184, 92";
  const COOL = "150, 180, 220";
  const LINK = "120, 150, 190";

  let W = 0, H = 0, DPR = 1, cx = 0, cy = 0, R = 0;
  const POINTS = reduced ? 90 : 210;
  const pts = [];

  // Fibonacci sphere — even point distribution, no clustering at poles.
  function buildSphere() {
    pts.length = 0;
    const phi = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < POINTS; i++) {
      const y = 1 - (i / (POINTS - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = phi * i;
      pts.push({
        x: Math.cos(th) * r,
        y: y,
        z: Math.sin(th) * r,
        s: 0.5 + Math.random() * 1.4,        // base point size
        tw: Math.random() * Math.PI * 2,      // twinkle phase
      });
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
    cx = W / 2;
    cy = H / 2;
    R = Math.min(W, H) * 0.42;
  }

  // Rotate a point around Y then X, return projected screen coords + depth.
  function project(p, ay, ax) {
    let x = p.x, y = p.y, z = p.z;
    // yaw
    let cosA = Math.cos(ay), sinA = Math.sin(ay);
    let x1 = x * cosA - z * sinA;
    let z1 = x * sinA + z * cosA;
    // pitch
    let cosB = Math.cos(ax), sinB = Math.sin(ax);
    let y1 = y * cosB - z1 * sinB;
    let z2 = y * sinB + z1 * cosB;
    const persp = 1 / (1.9 - z2);          // simple perspective
    return {
      sx: cx + x1 * R * persp * 1.6,
      sy: cy + y1 * R * persp * 1.6,
      depth: z2,                            // -1 (back) .. 1 (front)
      persp,
    };
  }

  let t = 0;
  function frame() {
    ctx.clearRect(0, 0, W, H);

    const ay = t * 0.00018;
    const ax = 0.42 + Math.sin(t * 0.00009) * 0.12;

    // Pre-project all points.
    const proj = pts.map((p) => {
      const pr = project(p, ay, ax);
      return { p, ...pr };
    });

    // ---- divergence links: connect near points, fade by depth ----
    ctx.lineWidth = 0.6;
    for (let i = 0; i < proj.length; i += 2) {
      const a = proj[i];
      let best = null, bestD = Infinity;
      for (let j = i + 1; j < proj.length; j++) {
        const b = proj[j];
        const dx = a.sx - b.sx, dy = a.sy - b.sy;
        const d = dx * dx + dy * dy;
        if (d < bestD) { bestD = d; best = b; }
      }
      if (best && bestD < (R * 0.42) * (R * 0.42)) {
        const front = (a.depth + best.depth) / 2;
        const alpha = Math.max(0, (front + 1) / 2) * 0.16;
        ctx.strokeStyle = `rgba(${LINK}, ${alpha})`;
        ctx.beginPath();
        ctx.moveTo(a.sx, a.sy);
        ctx.lineTo(best.sx, best.sy);
        ctx.stroke();
      }
    }

    // ---- core glow ----
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.3);
    g.addColorStop(0, `rgba(${AMBER}, 0.16)`);
    g.addColorStop(0.4, `rgba(${AMBER}, 0.05)`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // ---- points (painter's order: back to front) ----
    proj.sort((a, b) => a.depth - b.depth);
    for (const pp of proj) {
      const front = (pp.depth + 1) / 2;           // 0 back .. 1 front
      const tw = 0.7 + Math.sin(t * 0.002 + pp.p.tw) * 0.3;
      const size = pp.p.s * pp.persp * (0.6 + front) * tw;
      const alpha = 0.25 + front * 0.7;
      // A few "live" points glow amber; the rest are cool graphite.
      const warm = pp.p.tw > 5.1;
      ctx.fillStyle = warm
        ? `rgba(${AMBER}, ${alpha})`
        : `rgba(${COOL}, ${alpha * 0.8})`;
      ctx.beginPath();
      ctx.arc(pp.sx, pp.sy, Math.max(0.4, size), 0, Math.PI * 2);
      ctx.fill();
      if (warm && front > 0.6) {
        ctx.fillStyle = `rgba(${AMBER}, ${alpha * 0.22})`;
        ctx.beginPath();
        ctx.arc(pp.sx, pp.sy, size * 3.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  let raf = null;
  function loop(now) {
    t = now;
    frame();
    raf = requestAnimationFrame(loop);
  }

  function start() {
    resize();
    buildSphere();
    if (reduced) { t = 8000; frame(); return; }   // single static frame
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(loop);
  }

  // Pause when off-screen / tab hidden (battery + CPU honesty).
  let visible = true;
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = null; }
    else if (!reduced && visible && !raf) raf = requestAnimationFrame(loop);
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
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
