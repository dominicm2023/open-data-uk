/* The shape of the state — every senior post in UK central government as
   one three-dimensional figure, drawn in WebGL from
   /api/family/organograms/graph.json.

   The figure is a city at night. The ground is a map: every department a
   district, sized by its staff; every body a block within its district. On
   each block stand the body's senior posts as slender pillars of light,
   their height the pay band, so the skyline is the pay. Open a department
   and its district grows to fill the map; open a body and its posts
   re-form as a proper organisation chart — the head at the back, each
   level of reports a row nearer you, lines between them — still standing
   on their pay. Open a post and its reports do the same.

   Navigation follows what the good hierarchy explorers share: overview
   first, click to drill, the thing you opened laid out afresh to fill the
   view, a trail always visible, one step back always one click or Esc
   away, and a list beside the picture so nothing has to be hunted for.

   Raw WebGL 1, no library, no request to any other host (the CSP forbids
   both). Everything is lines and small points, so it runs on integrated
   graphics: the big soft sprites only appear when a body is open.
*/
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const canvas = $("c"), stage = $("stage"), tip = $("tip"), labelsEl = $("labels"), nogl = $("nogl");
  const crumbsEl = $("crumbs"), navList = $("navlist"), navHead = $("navhead"), search = $("search"), hits = $("hits");
  const gl = canvas.getContext("webgl", { antialias: true, alpha: false, preserveDrawingBuffer: false, powerPreference: "high-performance" });
  if (!gl) { nogl.hidden = false; $("panel").hidden = true; return; }
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- matrices --------------------------------------------------------------
  function perspective(fov, aspect, near, far) {
    const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
    return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
  }
  function lookAt(eye, at, up) {
    let zx = eye[0] - at[0], zy = eye[1] - at[1], zz = eye[2] - at[2];
    let l = Math.hypot(zx, zy, zz) || 1; zx /= l; zy /= l; zz /= l;
    let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
    l = Math.hypot(xx, xy, xz) || 1; xx /= l; xy /= l; xz /= l;
    const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
    return [xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0,
      -(xx * eye[0] + xy * eye[1] + xz * eye[2]), -(yx * eye[0] + yy * eye[1] + yz * eye[2]), -(zx * eye[0] + zy * eye[1] + zz * eye[2]), 1];
  }
  function mul(a, b) {
    const o = new Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++)
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    return o;
  }

  // --- shaders --------------------------------------------------------------------
  // fog: things far from the eye fade, which is most of what makes a flat
  // picture read as depth.
  const VS_PT = `
    attribute vec3 p; attribute vec3 col; attribute float sz; attribute float a;
    uniform mat4 mvp; uniform float pxr; uniform float scale; uniform float rise;
    varying vec3 vc; varying float va;
    void main() {
      vec4 cp = mvp * vec4(p.x, p.y, p.z * rise, 1.0); gl_Position = cp;
      float d = max(cp.w, 0.001);
      gl_PointSize = clamp(sz * scale * pxr * 60.0 / d, 1.0 * pxr, 30.0 * pxr);
      vc = col; va = a * clamp(1.25 - d * 0.16, 0.25, 1.0);
    }`;
  const FS_PT = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = dot(d, d) * 4.0;
      if (r > 1.0) discard;
      float core = exp(-r * 6.0) * 0.9; float halo = (1.0 - r) * 0.1;
      gl_FragColor = vec4(vc * (core + halo) * va, 1.0);
    }`;
  const FS_RING = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = sqrt(dot(d, d)) * 2.0;
      float ring = smoothstep(0.6, 0.68, r) * (1.0 - smoothstep(0.86, 0.96, r));
      gl_FragColor = vec4(vc * ring * va, 1.0);
    }`;
  const VS_LN = `
    attribute vec3 p; attribute vec3 col; attribute float a;
    uniform mat4 mvp; uniform float rise; varying vec3 vc; varying float va;
    void main() { vec4 cp = mvp * vec4(p.x, p.y, p.z * rise, 1.0); gl_Position = cp; vc = col; va = a * clamp(1.25 - max(cp.w, 0.0) * 0.16, 0.25, 1.0); }`;
  const FS_LN = `precision mediump float; varying vec3 vc; varying float va; void main() { gl_FragColor = vec4(vc * va, 1.0); }`;
  function program(vs, fs) {
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
    const pr = gl.createProgram(); gl.attachShader(pr, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    return pr;
  }
  const PT = program(VS_PT, FS_PT), RING = program(VS_PT, FS_RING), LN = program(VS_LN, FS_LN);
  const uni = (pr, n) => gl.getUniformLocation(pr, n);
  function buffer(arr, dyn) { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, arr, dyn ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW); return b; }
  function upload(b, arr) { gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, arr, gl.DYNAMIC_DRAW); }
  function attrib(pr, name, buf, size) { const l = gl.getAttribLocation(pr, name); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, 0, 0); }

  function hsl(h, s, l) {
    const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return [f(0), f(8), f(4)];
  }
  // A restrained palette: twelve hues, restated at a second lightness for the
  // next twelve, so forty departments do not become a rainbow.
  const HUES = [204, 28, 160, 262, 44, 340, 186, 76, 300, 12, 226, 120];
  const GRADE_L = { scs4: 0.92, scs3: 0.8, scs2: 0.68, scs1a: 0.6, scs1: 0.55 };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = v => Math.round(v || 0).toLocaleString();

  // --- state ---------------------------------------------------------------------
  const S = {
    G: null, n: 0, N: null, B: null, D: null, kids: null, order: null, deptFte: null, hue: null,
    pos: null, from: null, to: null, morph: 1, morphT0: 0, screen: null, vis: null,
    theta: -1.1, phi: 0.62, dist: 3.6, target: [0, 0, 0.15], camTo: null, drag: null, moved: 0,
    orbit: !REDUCED, showPillars: true, idleSince: performance.now(),
    focus: { kind: "gov", d: -1, b: -1, p: -1 }, hover: -1, sizeScale: 1,
    grow: REDUCED ? 1 : 0, t0: performance.now(), rects: {}, quads: null,
  };

  // --- build the static parts --------------------------------------------------------
  function build(G) {
    S.G = G; const N = G.nodes, n = N.title.length; S.n = n; S.N = N; S.B = G.bodies; S.D = G.departments;
    S.deptFte = G.departments.map(d => d.bodies.reduce((s, bi) => s + (G.bodies[bi].fte || 0), 0));
    S.order = G.departments.map((_, i) => i).sort((a, b) => S.deptFte[b] - S.deptFte[a]);
    S.hue = new Array(G.departments.length); S.sat = new Array(G.departments.length);
    S.order.forEach((di, k) => { S.hue[di] = HUES[k % HUES.length]; S.sat[di] = k < HUES.length ? 0.7 : 0.45; });
    S.kids = Array.from({ length: n }, () => []); S.roots = Array.from({ length: G.bodies.length }, () => []);
    for (let i = 0; i < n; i++) { const p = N.parent[i]; if (p >= 0) S.kids[p].push(i); else S.roots[N.body[i]].push(i); }
    let maxPay = 0; for (let i = 0; i < n; i++) if (N.pay[i] > maxPay) maxPay = N.pay[i]; S.maxPay = Math.max(maxPay, 200000);
    S.z = new Float32Array(n); for (let i = 0; i < n; i++) S.z[i] = N.pay[i] ? Math.max(0.03, (N.pay[i] - 20000) / (S.maxPay - 20000)) * 0.8 : 0.03;
    const col = new Float32Array(n * 3), sz = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const di = G.bodies[N.body[i]].dept, g = (N.grade[i] || "").replace(/\s/g, "").toLowerCase();
      const c = hsl(S.hue[di], S.sat[di], GRADE_L[g] || 0.55); col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
      sz[i] = 0.12 + Math.sqrt(N.below_fte[i] || 0) * 0.02 + (N.parent[i] < 0 ? 0.14 : 0);
    }
    S.col = col; S.sz = sz;
    S.pos = new Float32Array(n * 3); S.from = new Float32Array(n * 3); S.to = new Float32Array(n * 3);
    S.al = new Float32Array(n); S.screen = new Float32Array(n * 2); S.vis = new Uint8Array(n);
    S.pts = { pos: buffer(S.pos, true), col: buffer(col), sz: buffer(sz), al: buffer(S.al, true) };
    S.jn = []; for (let i = 0; i < n; i++) if (N.junior_fte[i] > 0) S.jn.push(i);
    const jc = new Float32Array(S.jn.length * 3), js = new Float32Array(S.jn.length);
    S.jn.forEach((i, k) => { const di = G.bodies[N.body[i]].dept, c = hsl(S.hue[di], S.sat[di], 0.6); jc[k * 3] = c[0]; jc[k * 3 + 1] = c[1]; jc[k * 3 + 2] = c[2]; js[k] = 0.25 + Math.sqrt(N.junior_fte[i]) * 0.04; });
    S.hpos = new Float32Array(S.jn.length * 3); S.hal = new Float32Array(S.jn.length);
    S.halo = { pos: buffer(S.hpos, true), col: buffer(jc), sz: buffer(js), al: buffer(S.hal, true) };
    S.ln = []; for (let i = 0; i < n; i++) if (N.parent[i] >= 0) S.ln.push(i);
    const lc = new Float32Array(S.ln.length * 6), pc = new Float32Array(n * 6);
    S.ln.forEach((i, k) => { for (let e = 0; e < 2; e++) { lc[k * 6 + e * 3] = col[i * 3]; lc[k * 6 + e * 3 + 1] = col[i * 3 + 1]; lc[k * 6 + e * 3 + 2] = col[i * 3 + 2]; } });
    for (let i = 0; i < n; i++) for (let e = 0; e < 2; e++) { pc[i * 6 + e * 3] = col[i * 3]; pc[i * 6 + e * 3 + 1] = col[i * 3 + 1]; pc[i * 6 + e * 3 + 2] = col[i * 3 + 2]; }
    S.lpos = new Float32Array(S.ln.length * 6); S.lal = new Float32Array(S.ln.length * 2);
    S.ppos = new Float32Array(n * 6); S.pal = new Float32Array(n * 2);
    S.lines = { pos: buffer(S.lpos, true), col: buffer(lc), al: buffer(S.lal, true) };
    S.pillars = { pos: buffer(S.ppos, true), col: buffer(pc), al: buffer(S.pal, true) };
    S.ring = { pos: buffer(new Float32Array(3), true), col: buffer(new Float32Array([1, 1, 1])), sz: buffer(new Float32Array([1]), true), al: buffer(new Float32Array([1])) };
    // the ground: a grid, and district floors (filled per level)
    const gp = [], gc = [], ga = [];
    for (let v = -2; v <= 2.001; v += 0.25) { gp.push(v, -2, 0, v, 2, 0, -2, v, 0, 2, v, 0); for (let e = 0; e < 4; e++) { gc.push(0.45, 0.5, 0.75); ga.push(Math.abs(v) < 0.01 ? 0.09 : 0.045); } }
    S.grid = { pos: buffer(new Float32Array(gp)), col: buffer(new Float32Array(gc)), al: buffer(new Float32Array(ga)), n: ga.length };
    S.floor = { pos: buffer(new Float32Array(0), true), col: buffer(new Float32Array(0), true), al: buffer(new Float32Array(0), true), n: 0 };
    $("sub").textContent = `${n.toLocaleString()} senior posts in ${G.bodies.length} bodies under ${G.departments.length} departments, ${fmt(S.deptFte.reduce((a, b) => a + b, 0))} staff (FTE) beneath them.`;
    $("asof").textContent = G.as_of ? `newest snapshot ${G.as_of}` : "";
    layout(S.focus);
    for (let i = 0; i < n * 3; i++) S.pos[i] = S.to[i];
    S.morph = 1; applyAlpha(); uploadAll();
    const q = new URLSearchParams(location.search);
    if (q.has("p") || q.has("b") || q.has("d")) {
      const f = { kind: "gov", d: -1, b: -1, p: -1 };
      if (q.has("d")) { f.kind = "dept"; f.d = +q.get("d"); }
      if (q.has("b")) { f.kind = "body"; f.b = +q.get("b"); f.d = G.bodies[f.b] ? G.bodies[f.b].dept : -1; }
      if (q.has("p")) { f.kind = "post"; f.p = +q.get("p"); f.b = N.body[f.p]; f.d = G.bodies[f.b].dept; }
      if ((f.kind === "dept" && G.departments[f.d]) || (f.kind === "body" && G.bodies[f.b]) || (f.kind === "post" && N.title[f.p] != null)) { setFocus(f, false); return; }
    }
    renderPanel(); frameFocus(true);
  }

  // --- layouts ---------------------------------------------------------------------------
  // Squarified treemap: items with weights into a rectangle, blocks as square as can be.
  function treemap(items, weightOf, rect) {
    const out = new Map(); const total = items.reduce((s, it) => s + weightOf(it), 0) || 1;
    let { x, y, w, h } = rect; let rest = items.slice().sort((a, b) => weightOf(b) - weightOf(a));
    let area = w * h;
    while (rest.length) {
      const horiz = w >= h; const side = horiz ? h : w;
      let row = [], rowW = 0, best = Infinity;
      for (const it of rest) {
        const wt = weightOf(it) / total * area; const tryW = rowW + wt;
        const len = tryW / side; let worst = 0;
        for (const r of row.concat(it)) { const a = weightOf(r) / total * area; const s = a / len; worst = Math.max(worst, Math.max(len / s, s / len)); }
        if (row.length && worst > best) break;
        row.push(it); rowW = tryW; best = worst;
      }
      const len = rowW / side; let off = 0;
      for (const r of row) { const a = weightOf(r) / total * area, s = a / len;
        out.set(r, horiz ? { x, y: y + off, w: len, h: s } : { x: x + off, y, w: s, h: len }); off += s; }
      if (horiz) { x += len; w -= len; } else { y += len; h -= len; }
      area = w * h; rest = rest.slice(row.length);
      if (area <= 0) { for (const r of rest) out.set(r, { x, y, w: 0.001, h: 0.001 }); break; }
    }
    return out;
  }
  // A body's posts on their block: depth-first order so a subtree keeps together, on a grid.
  function placeBlock(bi, r) {
    const order = []; S.roots[bi].forEach(function walk(i) { order.push(i); S.kids[i].forEach(walk); });
    const n = order.length; if (!n) return;
    const cols = Math.max(1, Math.ceil(Math.sqrt(n * r.w / Math.max(r.h, 1e-6)))), rows = Math.ceil(n / cols);
    const inset = 0.12;
    order.forEach((i, k) => {
      const cx = r.x + r.w * (inset + (1 - 2 * inset) * ((k % cols) + 0.5) / cols), cy = r.y + r.h * (inset + (1 - 2 * inset) * (Math.floor(k / cols) + 0.5) / rows);
      S.to[i * 3] = cx; S.to[i * 3 + 1] = cy; S.to[i * 3 + 2] = S.z[i];
    });
  }
  // A tidy tree: leaves evenly across, parents centred over children, rows by depth
  // running away from the viewer. The classic organisation chart, stood on its pay.
  function placeTree(roots, width, depthStep, backY) {
    let leaf = 0; const xs = new Map();
    function place(i, d) {
      const ks = S.kids[i]; let x;
      if (!ks.length) x = leaf++; else { ks.forEach(k => place(k, d + 1)); x = ks.reduce((s, k) => s + xs.get(k), 0) / ks.length; }
      xs.set(i, x); S.to[i * 3 + 1] = backY - d * depthStep; S.to[i * 3 + 2] = S.z[i];
    }
    roots.forEach(r => place(r, 0));
    const span = Math.max(1, leaf - 1), w = Math.min(width, Math.max(0.6, leaf * 0.08));
    xs.forEach((x, i) => { S.to[i * 3] = leaf > 1 ? (x / span - 0.5) * w : 0; });
    return { leaves: leaf, width: w };
  }
  function layout(f) {
    const G = S.G, B = G.bodies, D = G.departments;
    S.vis.fill(0); const floors = [];
    const addFloor = (r, di, a) => { const c = hsl(S.hue[di], S.sat[di], 0.5); floors.push({ r, c, a }); };
    if (f.kind === "gov") {
      const rects = treemap(S.order, di => Math.max(S.deptFte[di], 400), { x: -1.7, y: -1.25, w: 3.4, h: 2.5 });
      S.rects = {};
      S.order.forEach(di => {
        const r = rects.get(di); S.rects[di] = r; addFloor(r, di, 0.05);
        const inner = { x: r.x + r.w * 0.05, y: r.y + r.h * 0.05, w: r.w * 0.9, h: r.h * 0.9 };
        const bs = treemap(D[di].bodies, bi => Math.max(B[bi].senior, 1), inner);
        D[di].bodies.forEach(bi => placeBlock(bi, bs.get(bi)));
      });
      S.vis.fill(1); S.sizeScale = 0.75; S.phiWant = 0.7; S.thetaWant = null;
    } else if (f.kind === "dept") {
      const bs = D[f.d].bodies.slice().sort((a, b) => B[b].fte - B[a].fte);
      const rects = treemap(bs, bi => Math.max(B[bi].senior, 1) + Math.sqrt(B[bi].fte || 0) * 0.15, { x: -1.6, y: -1.15, w: 3.2, h: 2.3 });
      S.bodyRects = {}; bs.forEach(bi => { const r = rects.get(bi); S.bodyRects[bi] = r; addFloor(r, f.d, 0.06); placeBlock(bi, { x: r.x + r.w * 0.06, y: r.y + r.h * 0.06, w: r.w * 0.88, h: r.h * 0.88 }); });
      for (let i = 0; i < S.n; i++) if (B[S.N.body[i]].dept === f.d) S.vis[i] = 1;
      S.sizeScale = 1.1; S.phiWant = 0.62; S.thetaWant = null;
    } else {
      const roots = f.kind === "body" ? S.roots[f.b] : [f.p];
      const t = placeTree(roots, 3.2, 0.42, 1.1);
      if (f.kind === "body") { for (let i = 0; i < S.n; i++) if (S.N.body[i] === f.b) S.vis[i] = 1; }
      else (function mark(i) { S.vis[i] = 1; S.kids[i].forEach(mark); })(f.p);
      addFloor({ x: -t.width / 2 - 0.15, y: -2.2, w: t.width + 0.3, h: 3.5 }, f.d, 0.035);
      S.sizeScale = t.leaves > 120 ? 1.2 : t.leaves > 40 ? 1.7 : 2.4; S.phiWant = 0.58; S.thetaWant = -Math.PI / 2;
    }
    for (let i = 0; i < S.n; i++) if (!S.vis[i]) { S.to[i * 3] = S.pos[i * 3]; S.to[i * 3 + 1] = S.pos[i * 3 + 1]; S.to[i * 3 + 2] = S.pos[i * 3 + 2]; }
    // district floors as two triangles each
    const fp = [], fc = [], fa = [];
    for (const { r, c, a } of floors) {
      const q = [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]];
      for (const [x, y] of q) { fp.push(x, y, 0); fc.push(c[0], c[1], c[2]); fa.push(a); }
    }
    upload(S.floor.pos, new Float32Array(fp)); upload(S.floor.col, new Float32Array(fc)); upload(S.floor.al, new Float32Array(fa)); S.floor.n = fa.length;
  }
  function applyAlpha() {
    const open = S.focus.kind === "body" || S.focus.kind === "post";
    for (let i = 0; i < S.n; i++) S.al[i] = S.vis[i] ? 1 : 0;
    S.jn.forEach((i, k) => { S.hal[k] = S.vis[i] && open ? 0.08 : 0; });
    S.ln.forEach((i, k) => { const v = S.vis[i] && S.vis[S.N.parent[i]]; const a = open ? 0.35 : 0; S.lal[k * 2] = v ? a * 0.6 : 0; S.lal[k * 2 + 1] = v ? a : 0; });
    for (let i = 0; i < S.n; i++) { S.pal[i * 2] = S.vis[i] ? 0.015 : 0; S.pal[i * 2 + 1] = S.vis[i] ? (open ? 0.24 : 0.18) : 0; }
    upload(S.pts.al, S.al); upload(S.halo.al, S.hal); upload(S.lines.al, S.lal); upload(S.pillars.al, S.pal);
  }
  function uploadAll() {
    const p = S.pos, N = S.N;
    upload(S.pts.pos, p);
    S.jn.forEach((i, k) => { S.hpos[k * 3] = p[i * 3]; S.hpos[k * 3 + 1] = p[i * 3 + 1]; S.hpos[k * 3 + 2] = p[i * 3 + 2] * 0.5; }); upload(S.halo.pos, S.hpos);
    S.ln.forEach((i, k) => { const q = N.parent[i]; S.lpos[k * 6] = p[q * 3]; S.lpos[k * 6 + 1] = p[q * 3 + 1]; S.lpos[k * 6 + 2] = p[q * 3 + 2]; S.lpos[k * 6 + 3] = p[i * 3]; S.lpos[k * 6 + 4] = p[i * 3 + 1]; S.lpos[k * 6 + 5] = p[i * 3 + 2]; }); upload(S.lines.pos, S.lpos);
    for (let i = 0; i < S.n; i++) { S.ppos[i * 6] = p[i * 3]; S.ppos[i * 6 + 1] = p[i * 3 + 1]; S.ppos[i * 6 + 2] = 0; S.ppos[i * 6 + 3] = p[i * 3]; S.ppos[i * 6 + 4] = p[i * 3 + 1]; S.ppos[i * 6 + 5] = p[i * 3 + 2]; } upload(S.pillars.pos, S.ppos);
  }

  // --- focus ----------------------------------------------------------------------------------
  function setFocus(f, push) {
    S.focus = f;
    for (let i = 0; i < S.n * 3; i++) S.from[i] = S.pos[i];
    layout(f);
    S.morph = REDUCED ? 1 : 0; S.morphT0 = performance.now();
    if (S.morph === 1) { for (let i = 0; i < S.n * 3; i++) S.pos[i] = S.to[i]; uploadAll(); }
    applyAlpha(); renderPanel(); frameFocus(false); S.hover = -1; tip.hidden = true; $("detail").hidden = true;
    const q = new URLSearchParams();
    if (f.kind === "dept") q.set("d", f.d); if (f.kind === "body") q.set("b", f.b); if (f.kind === "post") q.set("p", f.p);
    const url = location.pathname + (q.toString() ? "?" + q : "");
    if (push) history.pushState(f, "", url); else history.replaceState(f, "", url);
  }
  window.addEventListener("popstate", e => { if (!S.G) return; setFocus(e.state || { kind: "gov", d: -1, b: -1, p: -1 }, false); });
  function up() {
    const f = S.focus;
    if (f.kind === "post") { const p = S.N.parent[f.p]; setFocus(p >= 0 && S.kids[p].length ? { kind: "post", d: f.d, b: f.b, p } : { kind: "body", d: f.d, b: f.b, p: -1 }, true); }
    else if (f.kind === "body") setFocus({ kind: "dept", d: f.d, b: -1, p: -1 }, true);
    else if (f.kind === "dept") setFocus({ kind: "gov", d: -1, b: -1, p: -1 }, true);
  }
  function drillTo(i) {
    const f = S.focus, bi = S.N.body[i], di = S.B[bi].dept;
    if (f.kind === "gov") return setFocus({ kind: "dept", d: di, b: -1, p: -1 }, true);
    if (f.kind === "dept") return setFocus({ kind: "body", d: di, b: bi, p: -1 }, true);
    if (S.kids[i].length && !(f.kind === "post" && f.p === i)) return setFocus({ kind: "post", d: di, b: bi, p: i }, true);
    showDetail(i);
  }
  function frameFocus(instant) {
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, zmax = 0;
    for (let i = 0; i < S.n; i++) if (S.vis[i]) { const x = S.to[i * 3], y = S.to[i * 3 + 1]; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); zmax = Math.max(zmax, S.to[i * 3 + 2]); }
    if (x0 > x1) return;
    const tree = S.focus.kind === "body" || S.focus.kind === "post";
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, r = tree ? Math.max((x1 - x0) * 0.55, (y1 - y0) * 0.9, 0.35) : Math.max(x1 - x0, (y1 - y0) * 1.2, 0.5) / 2;
    const dist = Math.max(0.9, r * (tree ? 2.1 : 2.5) + 0.45);
    S.camTo = { target: [cx, cy, Math.min(zmax * 0.4, tree ? 0.3 : 0.2)], dist, phi: S.phiWant, theta: S.thetaWant == null ? S.theta : S.thetaWant,
      from: { target: S.target.slice(), dist: S.dist, phi: S.phi, theta: S.theta }, t0: performance.now() };
    if (instant || REDUCED) { S.target = S.camTo.target.slice(); S.dist = dist; S.phi = S.camTo.phi; S.theta = S.camTo.theta; S.camTo = null; }
  }

  // --- panel: trail, list, search ----------------------------------------------------------------
  function trail() {
    const f = S.focus, G = S.G, t = [["UK government", { kind: "gov", d: -1, b: -1, p: -1 }]];
    if (f.d >= 0) t.push([G.departments[f.d].name, { kind: "dept", d: f.d, b: -1, p: -1 }]);
    if (f.b >= 0) t.push([G.bodies[f.b].name, { kind: "body", d: f.d, b: f.b, p: -1 }]);
    if (f.p >= 0) { const chain = []; let p = f.p; while (p >= 0) { chain.unshift(p); p = S.N.parent[p]; } chain.forEach(pi => { if (S.kids[pi].length) t.push([S.N.title[pi] || "(untitled post)", { kind: "post", d: f.d, b: f.b, p: pi }]); }); }
    return t;
  }
  function renderPanel() {
    const f = S.focus, G = S.G, N = S.N, B = G.bodies, D = G.departments, t = trail();
    crumbsEl.innerHTML = t.map(([name], k) => k === t.length - 1 ? `<span aria-current="page">${esc(name)}</span>` : `<a href="#" data-k="${k}">${esc(name)}</a>`).join('<i class="sep">›</i>');
    crumbsEl.querySelectorAll("a").forEach(a => a.addEventListener("click", e => { e.preventDefault(); setFocus(t[+a.dataset.k][1], true); }));
    $("upbtn").hidden = f.kind === "gov";
    let head = "", items = [];
    if (f.kind === "gov") {
      head = `<b>UK central government</b><span>${D.length} departments · ${B.length} bodies · ${fmt(S.deptFte.reduce((a, b) => a + b, 0))} FTE · each district is a department; click one</span>`;
      items = S.order.map(di => ({ name: D[di].name, meta: `${fmt(S.deptFte[di])} FTE · ${D[di].bodies.length} bod${D[di].bodies.length === 1 ? "y" : "ies"}`, f: { kind: "dept", d: di, b: -1, p: -1 }, hue: S.hue[di], sat: S.sat[di] }));
    } else if (f.kind === "dept") {
      const d = D[f.d];
      head = `<b>${esc(d.name)}</b><span>${fmt(S.deptFte[f.d])} FTE · ${d.bodies.length} bod${d.bodies.length === 1 ? "y" : "ies"} · each block is a body; click one</span>`;
      items = d.bodies.slice().sort((a, b) => B[b].fte - B[a].fte).map(bi => ({ name: B[bi].name, meta: `${fmt(B[bi].fte)} FTE · ${B[bi].senior} senior posts` + (B[bi].head ? ` · top: ${esc(B[bi].head)}` : ""), f: { kind: "body", d: f.d, b: bi, p: -1 }, hue: S.hue[f.d], sat: S.sat[f.d], i: S.roots[bi][0] }));
    } else {
      const b = B[f.b];
      head = f.kind === "body"
        ? `<b>${esc(b.name)}</b><span>${fmt(b.fte)} FTE · ${b.senior} senior posts · snapshot ${esc(b.as_of)} · the head at the back, each level of reports a row nearer; click a post that has reports</span>`
        : `<b>${esc(N.title[f.p])}</b><span>${esc(N.grade[f.p])}${N.pay[f.p] ? " · from £" + N.pay[f.p].toLocaleString() : ""} · ${fmt(N.below_fte[f.p])} FTE beneath</span>`;
      const list = f.kind === "body" ? S.roots[f.b] : S.kids[f.p];
      items = list.slice().sort((a, c) => N.below_fte[c] - N.below_fte[a]).map(i => ({
        name: N.title[i] || "(untitled post)", meta: `${esc(N.grade[i])}${N.pay[i] ? " · from £" + N.pay[i].toLocaleString() : ""} · ${fmt(N.below_fte[i])} FTE beneath` + (S.kids[i].length ? ` · ${S.kids[i].length} direct senior reports` : ""),
        f: S.kids[i].length ? { kind: "post", d: f.d, b: f.b, p: i } : null, i, hue: S.hue[f.d], sat: S.sat[f.d] }));
    }
    navHead.innerHTML = head;
    navList.innerHTML = items.slice(0, 400).map((it, k) => `<li><a href="#" data-k="${k}" class="${it.f ? "" : "leaf"}"><i style="background:hsl(${it.hue},${Math.round(it.sat * 100)}%,60%)"></i><span class="nm">${esc(it.name)}</span><span class="mt">${it.meta}</span></a></li>`).join("")
      + (items.length > 400 ? `<li class="more">and ${items.length - 400} more — use search</li>` : "");
    navList.querySelectorAll("a").forEach((a, k) => {
      const it = items[k];
      a.addEventListener("click", e => { e.preventDefault(); if (it.f) setFocus(it.f, true); else showDetail(it.i); });
      if (it.i != null) { a.addEventListener("pointerenter", () => { S.hover = it.i; }); a.addEventListener("pointerleave", () => { S.hover = -1; }); }
    });
  }
  function showDetail(i) {
    const N = S.N, b = S.B[N.body[i]];
    $("detailbody").innerHTML = `<b>${esc(N.title[i] || "(untitled post)")}</b><br>${esc(b.name)}<br>${esc(N.grade[i])}${N.pay[i] ? " · from £" + N.pay[i].toLocaleString() : " · pay not stated"} · FTE ${N.fte[i]}`
      + (N.junior_fte[i] ? `<br>${fmt(N.junior_fte[i])} FTE in junior groups report here` : "") + `<br><a href="/family/organograms/chart?body=${encodeURIComponent(b.name)}">This body's chart as a list</a>`;
    $("detail").hidden = false; S.hover = i;
  }
  let idx = null;
  function searchIndex() {
    if (idx) return idx; idx = [];
    S.B.forEach((b, bi) => idx.push({ s: b.name.toLowerCase(), name: b.name, meta: `body · ${fmt(b.fte)} FTE`, f: { kind: "body", d: b.dept, b: bi, p: -1 }, w: b.fte }));
    for (let i = 0; i < S.n; i++) idx.push({ s: (S.N.title[i] || "").toLowerCase() + " " + S.B[S.N.body[i]].name.toLowerCase(), name: S.N.title[i] || "(untitled post)", meta: `${S.B[S.N.body[i]].name} · ${esc(S.N.grade[i])}`, f: S.kids[i].length ? { kind: "post", d: S.B[S.N.body[i]].dept, b: S.N.body[i], p: i } : { kind: "body", d: S.B[S.N.body[i]].dept, b: S.N.body[i], p: -1 }, i, w: S.N.below_fte[i] });
    return idx;
  }
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase(); if (q.length < 2) { hits.hidden = true; return; }
    const words = q.split(/\s+/); const m = searchIndex().filter(e => words.every(w => e.s.includes(w))).sort((a, b) => b.w - a.w).slice(0, 12);
    hits.innerHTML = m.map((e, k) => `<li><a href="#" data-k="${k}"><span class="nm">${esc(e.name)}</span><span class="mt">${e.meta}</span></a></li>`).join("") || "<li class='more'>nothing matches</li>";
    hits.querySelectorAll("a").forEach((a, k) => a.addEventListener("click", ev => { ev.preventDefault(); hits.hidden = true; search.value = ""; setFocus(m[k].f, true); if (m[k].i != null && !S.kids[m[k].i].length) showDetail(m[k].i); }));
    hits.hidden = false;
  });
  search.addEventListener("keydown", e => { if (e.key === "Escape") { hits.hidden = true; search.blur(); } if (e.key === "Enter") { const a = hits.querySelector("a"); if (a) a.click(); } });

  // --- camera and drawing --------------------------------------------------------------------------
  let W = 1, Hh = 1, pxr = 1;
  function resize() {
    pxr = Math.min(window.devicePixelRatio || 1, 1.5);
    const r = stage.getBoundingClientRect(); W = Math.max(1, Math.floor(r.width)); Hh = Math.max(1, Math.floor(r.height));
    canvas.width = Math.floor(W * pxr); canvas.height = Math.floor(Hh * pxr); canvas.style.width = W + "px"; canvas.style.height = Hh + "px";
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  window.addEventListener("resize", resize); resize();
  function camera() {
    const eye = [S.target[0] + S.dist * Math.cos(S.phi) * Math.cos(S.theta), S.target[1] + S.dist * Math.cos(S.phi) * Math.sin(S.theta), S.target[2] + S.dist * Math.sin(S.phi)];
    return mul(perspective(0.8, W / Hh, 0.02, 40), lookAt(eye, S.target, [0, 0, 1]));
  }
  const ease = t => 1 - Math.pow(1 - t, 3);
  function draw(now) {
    requestAnimationFrame(draw); if (!S.G) return;
    const dt = Math.min(0.05, (now - (S.last || now)) / 1000); S.last = now;
    if (S.grow < 1) S.grow = Math.min(1, (now - S.t0) / 2200);
    const rise = ease(S.grow);
    if (S.morph < 1) { S.morph = Math.min(1, (now - S.morphT0) / 1000); const e = ease(S.morph);
      for (let i = 0; i < S.n * 3; i++) S.pos[i] = S.from[i] + (S.to[i] - S.from[i]) * e; uploadAll(); }
    if (S.camTo) { const c = S.camTo, e = ease(Math.min(1, (now - c.t0) / 1200));
      for (let j = 0; j < 3; j++) S.target[j] = c.from.target[j] + (c.target[j] - c.from.target[j]) * e;
      S.dist = c.from.dist + (c.dist - c.from.dist) * e; S.phi = c.from.phi + (c.phi - c.from.phi) * e;
      let dth = c.theta - c.from.theta; dth = Math.atan2(Math.sin(dth), Math.cos(dth)); S.theta = c.from.theta + dth * e;
      if (e >= 1) S.camTo = null; }
    if (S.orbit && !S.drag && S.focus.kind === "gov" && (now - S.idleSince) > 6000) S.theta += dt * 0.07;
    const m = camera();
    gl.clearColor(0.028, 0.032, 0.06, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, m); gl.uniform1f(uni(LN, "rise"), 1);
    attrib(LN, "p", S.floor.pos, 3); attrib(LN, "col", S.floor.col, 3); attrib(LN, "a", S.floor.al, 1); if (S.floor.n) gl.drawArrays(gl.TRIANGLES, 0, S.floor.n);
    attrib(LN, "p", S.grid.pos, 3); attrib(LN, "col", S.grid.col, 3); attrib(LN, "a", S.grid.al, 1); gl.drawArrays(gl.LINES, 0, S.grid.n);
    gl.uniform1f(uni(LN, "rise"), rise);
    if (S.showPillars) { attrib(LN, "p", S.pillars.pos, 3); attrib(LN, "col", S.pillars.col, 3); attrib(LN, "a", S.pillars.al, 1); gl.drawArrays(gl.LINES, 0, S.n * 2); }
    attrib(LN, "p", S.lines.pos, 3); attrib(LN, "col", S.lines.col, 3); attrib(LN, "a", S.lines.al, 1); gl.drawArrays(gl.LINES, 0, S.ln.length * 2);
    gl.useProgram(PT); gl.uniformMatrix4fv(uni(PT, "mvp"), false, m); gl.uniform1f(uni(PT, "pxr"), pxr); gl.uniform1f(uni(PT, "scale"), S.sizeScale); gl.uniform1f(uni(PT, "rise"), rise);
    if (S.focus.kind === "body" || S.focus.kind === "post") { attrib(PT, "p", S.halo.pos, 3); attrib(PT, "col", S.halo.col, 3); attrib(PT, "sz", S.halo.sz, 1); attrib(PT, "a", S.halo.al, 1); gl.drawArrays(gl.POINTS, 0, S.jn.length); }
    attrib(PT, "p", S.pts.pos, 3); attrib(PT, "col", S.pts.col, 3); attrib(PT, "sz", S.pts.sz, 1); attrib(PT, "a", S.pts.al, 1); gl.drawArrays(gl.POINTS, 0, S.n);
    if (S.hover >= 0 && S.vis[S.hover]) {
      upload(S.ring.pos, new Float32Array([S.pos[S.hover * 3], S.pos[S.hover * 3 + 1], S.pos[S.hover * 3 + 2]]));
      upload(S.ring.sz, new Float32Array([Math.max(S.sz[S.hover] * S.sizeScale, 0.4) + 0.3]));
      gl.useProgram(RING); gl.uniformMatrix4fv(uni(RING, "mvp"), false, m); gl.uniform1f(uni(RING, "pxr"), pxr); gl.uniform1f(uni(RING, "scale"), 1); gl.uniform1f(uni(RING, "rise"), rise);
      attrib(RING, "p", S.ring.pos, 3); attrib(RING, "col", S.ring.col, 3); attrib(RING, "sz", S.ring.sz, 1); attrib(RING, "a", S.ring.al, 1); gl.drawArrays(gl.POINTS, 0, 1);
    }
    project(m, rise); labels(m, rise);
  }
  function project(m, rise) {
    const p = S.pos, s = S.screen;
    for (let i = 0; i < S.n; i++) {
      if (!S.vis[i]) { s[i * 2] = -1e4; s[i * 2 + 1] = -1e4; continue; }
      const x = p[i * 3], y = p[i * 3 + 1], z = p[i * 3 + 2] * rise;
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
      if (cw <= 0.001) { s[i * 2] = -1e4; s[i * 2 + 1] = -1e4; continue; }
      s[i * 2] = ((m[0] * x + m[4] * y + m[8] * z + m[12]) / cw * 0.5 + 0.5) * W;
      s[i * 2 + 1] = (0.5 - (m[1] * x + m[5] * y + m[9] * z + m[13]) / cw * 0.5) * Hh;
    }
  }
  let labelWant = [], labelKey = "";
  function labelsFor() {
    const f = S.focus, G = S.G, B = G.bodies, N = S.N, out = [];
    if (f.kind === "gov") S.order.slice(0, 22).forEach(di => { const r = S.rects[di]; out.push({ text: G.departments[di].name, x: r.x + r.w / 2, y: r.y + r.h / 2, z: 0.0, hue: S.hue[di], f: { kind: "dept", d: di, b: -1, p: -1 }, big: S.deptFte[di] > 20000 }); });
    else if (f.kind === "dept") G.departments[f.d].bodies.slice().sort((a, b) => B[b].fte - B[a].fte).slice(0, 40).forEach(bi => { const r = S.bodyRects[bi]; if (!r) return;
      out.push({ text: B[bi].name, x: r.x + r.w / 2, y: r.y + r.h / 2, z: 0.0, hue: S.hue[f.d], f: { kind: "body", d: f.d, b: bi, p: -1 }, big: B[bi].fte > S.deptFte[f.d] * 0.12 }); });
    else { const list = []; for (let i = 0; i < S.n; i++) if (S.vis[i]) list.push(i);
      list.sort((a, b) => N.below_fte[b] - N.below_fte[a]).slice(0, 28).forEach(i => out.push({ text: N.title[i] || "(untitled post)", i, hue: S.hue[f.d], f: S.kids[i].length ? { kind: "post", d: f.d, b: f.b, p: i } : null, big: N.below_fte[i] > 200 })); }
    return out;
  }
  function labels(m, rise) {
    const key = JSON.stringify(S.focus);
    if (key !== labelKey) { labelKey = key; labelWant = labelsFor(); labelsEl.innerHTML = "";
      labelWant.forEach(l => { const el = document.createElement("div"); el.className = "org3d-label" + (l.big ? " big" : "") + (l.i == null ? " ground" : ""); el.textContent = l.text; el.style.color = `hsl(${l.hue},70%,80%)`;
        el.addEventListener("click", () => { if (l.f) setFocus(l.f, true); else showDetail(l.i); }); el.addEventListener("pointerenter", () => { if (l.i != null) S.hover = l.i; }); labelsEl.appendChild(el); l.el = el; }); }
    const placed = [];
    for (const l of labelWant) {
      let px, py;
      if (l.i != null) { px = S.screen[l.i * 2]; py = S.screen[l.i * 2 + 1] - 12; }
      else { const cw = m[3] * l.x + m[7] * l.y + m[11] * l.z + m[15]; if (cw <= 0.001) { l.el.style.opacity = 0; continue; }
        px = ((m[0] * l.x + m[4] * l.y + m[8] * l.z + m[12]) / cw * 0.5 + 0.5) * W; py = (0.5 - (m[1] * l.x + m[5] * l.y + m[9] * l.z + m[13]) / cw * 0.5) * Hh; }
      if (px < -50 || py < -20 || px > W + 50 || py > Hh + 20 || placed.some(([qx, qy]) => Math.abs(qx - px) < 190 && Math.abs(qy - py) < 17)) { l.el.style.opacity = 0; continue; }
      placed.push([px, py]); l.el.style.opacity = Math.max(0, (S.grow - 0.4) * 1.7) * (S.morph < 0.6 ? S.morph : 1);
      l.el.style.transform = `translate(${px}px, ${py}px)`;
    }
  }

  // --- pointer ------------------------------------------------------------------------------------
  function pick(mx, my) {
    let best = -1, bd = 14 * 14; const s = S.screen;
    for (let i = 0; i < S.n; i++) { if (!S.vis[i]) continue; const dx = s[i * 2] - mx, dy = s[i * 2 + 1] - my, d = dx * dx + dy * dy - S.sz[i] * 6; if (d < bd) { bd = d; best = i; } }
    return best;
  }
  canvas.addEventListener("pointerdown", e => { S.drag = { x: e.clientX, y: e.clientY, th: S.theta, ph: S.phi }; S.moved = 0; canvas.setPointerCapture(e.pointerId); S.idleSince = performance.now(); });
  canvas.addEventListener("pointerup", e => {
    const wasClick = S.drag && S.moved < 5; S.drag = null; if (!wasClick) return;
    const r = canvas.getBoundingClientRect(), i = pick(e.clientX - r.left, e.clientY - r.top);
    if (i >= 0) drillTo(i); else up();
  });
  canvas.addEventListener("pointermove", e => {
    S.idleSince = performance.now();
    if (S.drag) { S.moved = Math.max(S.moved, Math.abs(e.clientX - S.drag.x) + Math.abs(e.clientY - S.drag.y));
      if (S.moved >= 5) { S.theta = S.drag.th - (e.clientX - S.drag.x) * 0.006; S.phi = Math.max(0.12, Math.min(1.45, S.drag.ph + (e.clientY - S.drag.y) * 0.005)); S.camTo = null; tip.hidden = true; } return; }
    if (!S.G) return;
    const r = canvas.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, i = pick(mx, my);
    S.hover = i; canvas.style.cursor = i >= 0 ? "pointer" : "grab";
    if (i < 0) { tip.hidden = true; return; }
    const N = S.N, b = S.B[N.body[i]];
    const next = S.focus.kind === "gov" ? "click: open this department" : S.focus.kind === "dept" ? "click: open this body" : S.kids[i].length ? "click: open the posts beneath" : "click: details";
    tip.innerHTML = `<b>${esc(N.title[i] || "(untitled post)")}</b><br>${esc(b.name)}<br>${esc(N.grade[i])} · ${N.pay[i] ? "from £" + N.pay[i].toLocaleString() : "pay not stated"}<br>${fmt(N.below_fte[i])} FTE beneath` + (N.below_senior[i] > 1 ? `, ${(N.below_senior[i] - 1).toLocaleString()} senior posts` : "") + `<br><i>${next}</i>`;
    tip.style.left = Math.min(mx + 14, W - 300) + "px"; tip.style.top = (my + 14) + "px"; tip.hidden = false;
  });
  canvas.addEventListener("pointerleave", () => { tip.hidden = true; S.hover = -1; });
  canvas.addEventListener("wheel", e => { e.preventDefault(); S.idleSince = performance.now(); S.camTo = null; S.dist = Math.max(0.3, Math.min(10, S.dist * (1 + Math.sign(e.deltaY) * 0.08))); }, { passive: false });
  document.addEventListener("keydown", e => {
    if (e.target === search) return;
    if (e.key === "Escape") { if (!$("detail").hidden) { $("detail").hidden = true; return; } up(); }
    else if (e.key === "ArrowLeft") S.theta -= 0.12; else if (e.key === "ArrowRight") S.theta += 0.12;
    else if (e.key === "ArrowUp") S.phi = Math.min(1.45, S.phi + 0.08); else if (e.key === "ArrowDown") S.phi = Math.max(0.12, S.phi - 0.08);
    else if (e.key === "+" || e.key === "=") S.dist *= 0.9; else if (e.key === "-") S.dist *= 1.1;
    else if (e.key === "/") { e.preventDefault(); search.focus(); return; } else if (e.key === "?") { $("help").hidden = !$("help").hidden; return; } else return;
    S.idleSince = performance.now(); S.camTo = null;
  });
  $("upbtn").addEventListener("click", up);
  $("closedetail").addEventListener("click", () => { $("detail").hidden = true; });
  $("helpbtn").addEventListener("click", () => { $("help").hidden = !$("help").hidden; });
  $("closehelp").addEventListener("click", () => { $("help").hidden = true; });
  const orbitBtn = $("orbit"); orbitBtn.textContent = `Orbit: ${S.orbit ? "on" : "off"}`;
  orbitBtn.addEventListener("click", () => { S.orbit = !S.orbit; orbitBtn.textContent = `Orbit: ${S.orbit ? "on" : "off"}`; orbitBtn.setAttribute("aria-pressed", S.orbit); S.idleSince = 0; });
  const pillBtn = $("pillars");
  pillBtn.addEventListener("click", () => { S.showPillars = !S.showPillars; pillBtn.textContent = `Pillars: ${S.showPillars ? "on" : "off"}`; pillBtn.setAttribute("aria-pressed", S.showPillars); });
  $("full").addEventListener("click", () => { if (document.fullscreenElement) document.exitFullscreen(); else if (stage.requestFullscreen) stage.requestFullscreen(); });
  document.addEventListener("fullscreenchange", () => setTimeout(resize, 50));
  $("reset").addEventListener("click", () => { setFocus({ kind: "gov", d: -1, b: -1, p: -1 }, true); S.theta = -1.1; S.t0 = performance.now(); S.grow = REDUCED ? 1 : 0; S.idleSince = 0; });

  // --- record the canvas to a WebM ---------------------------------------------------------------------
  const recBtn = $("rec"), dl = $("dl");
  recBtn.addEventListener("click", () => {
    if (!canvas.captureStream || !window.MediaRecorder) { recBtn.textContent = "Recording not supported here"; recBtn.disabled = true; return; }
    const stream = canvas.captureStream(30);
    const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find(m => MediaRecorder.isTypeSupported(m)) || "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 12e6 } : undefined);
    const chunks = []; rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => { const blob = new Blob(chunks, { type: "video/webm" }); dl.href = URL.createObjectURL(blob); dl.hidden = false; dl.textContent = `Save video (${(blob.size / 1e6).toFixed(1)} MB)`; recBtn.textContent = "Record 12 s"; recBtn.disabled = false; };
    const was = S.orbit; S.orbit = true; S.idleSince = 0; tip.hidden = true;
    if (S.focus.kind === "gov") { S.t0 = performance.now(); S.grow = 0; }
    recBtn.textContent = "Recording…"; recBtn.disabled = true; dl.hidden = true;
    rec.start(250); setTimeout(() => { rec.stop(); S.orbit = was; }, 12000);
  });

  fetch("/api/family/organograms/graph.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(G => { build(G); requestAnimationFrame(draw); })
    .catch(err => { $("sub").textContent = "The graph could not be loaded (" + err.message + "). The chart as a list has every post."; });
})();
