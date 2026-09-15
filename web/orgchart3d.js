/* The shape of the state — every senior post in UK central government as
   one three-dimensional figure, drawn in WebGL from
   /api/family/organograms/graph.json.

   Navigation follows the rule the good hierarchy explorers share (zoomable
   circle packing, sunbursts with breadcrumbs, 3D graph tools): overview
   first, click to drill, the thing you clicked re-laid to fill the view,
   the trail always visible, one step back always one click or Esc away,
   and a list beside the picture so nothing has to be hunted for in 3D.

   Levels:  government -> department -> body -> post (any post with reports)
   Layout:  at each level the focused set is laid out afresh to fill the
            disc — departments as sectors, bodies as slices, a body's posts
            as a radial tree with the head at the centre — and the figure
            morphs from the old layout to the new. Height is the pay band's
            floor; a post's size is the staff beneath it; junior groups glow
            round the post they report to; colour is department.
   Labels:  the level's own names (departments, then bodies, then posts),
            largest first, never on top of each other.

   No library, no request to any other host (the CSP forbids both). Raw
   WebGL 1; the morph is computed on the CPU (12,856 posts is nothing) and
   uploaded while it runs. Record captures the canvas to a WebM.
*/
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const canvas = $("c"), stage = $("stage"), tip = $("tip"), labelsEl = $("labels"), nogl = $("nogl");
  const crumbsEl = $("crumbs"), navList = $("navlist"), navHead = $("navhead"), search = $("search"), hits = $("hits");
  const gl = canvas.getContext("webgl", { antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: "high-performance" });
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
  const VS_PT = `
    attribute vec3 p; attribute vec3 col; attribute float sz; attribute float a;
    uniform mat4 mvp; uniform float pxr; uniform float scale;
    varying vec3 vc; varying float va;
    void main() {
      vec4 cp = mvp * vec4(p, 1.0); gl_Position = cp;
      float d = max(cp.w, 0.001);
      gl_PointSize = clamp(sz * scale * pxr * 70.0 / d, 1.2 * pxr, 48.0 * pxr);
      vc = col; va = a;
    }`;
  const FS_PT = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = dot(d, d) * 4.0;
      if (r > 1.0) discard;
      float core = exp(-r * 7.0) * 0.85; float halo = (1.0 - r) * 0.12;
      gl_FragColor = vec4(vc * (core + halo) * va, 1.0);
    }`;
  const FS_RING = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = sqrt(dot(d, d)) * 2.0;
      float ring = smoothstep(0.62, 0.7, r) * (1.0 - smoothstep(0.86, 0.96, r));
      gl_FragColor = vec4(vc * ring * va, 1.0);
    }`;
  const VS_LN = `
    attribute vec3 p; attribute vec3 col; attribute float a;
    uniform mat4 mvp; varying vec3 vc; varying float va;
    void main() { gl_Position = mvp * vec4(p, 1.0); vc = col; va = a; }`;
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
  const GRADE_L = { scs4: 0.84, scs3: 0.74, scs2: 0.64, scs1a: 0.56, scs1: 0.5 };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = v => Math.round(v || 0).toLocaleString();

  // --- state ---------------------------------------------------------------------
  const S = {
    G: null, n: 0, N: null, B: null, D: null, kids: null, depth: null, order: null, deptFte: null, hue: null,
    pos: null, from: null, to: null, morph: 1, morphT0: 0, screen: null, vis: null,
    theta: 0.9, phi: 0.72, dist: 3.9, target: [0, 0, 0.18], camTo: null, drag: null, moved: 0,
    orbit: !REDUCED, showPillars: true, idleSince: performance.now(),
    focus: { kind: "gov", d: -1, b: -1, p: -1 }, hover: -1, sizeScale: 1,
    grow: REDUCED ? 1 : 0, t0: performance.now(),
  };

  // --- build the static parts --------------------------------------------------------
  function build(G) {
    S.G = G; const N = G.nodes, n = N.title.length; S.n = n; S.N = N; S.B = G.bodies; S.D = G.departments;
    S.deptFte = G.departments.map(d => d.bodies.reduce((s, bi) => s + (G.bodies[bi].fte || 0), 0));
    S.order = G.departments.map((_, i) => i).sort((a, b) => S.deptFte[b] - S.deptFte[a]);
    S.hue = new Array(G.departments.length); S.order.forEach((di, k) => { S.hue[di] = (k * 137.508) % 360; });
    S.kids = Array.from({ length: n }, () => []); S.depth = new Int16Array(n); S.roots = Array.from({ length: G.bodies.length }, () => []);
    for (let i = 0; i < n; i++) { const p = N.parent[i]; if (p >= 0) { S.kids[p].push(i); S.depth[i] = S.depth[p] + 1; } else S.roots[N.body[i]].push(i); }
    let maxPay = 0; for (let i = 0; i < n; i++) if (N.pay[i] > maxPay) maxPay = N.pay[i]; S.maxPay = Math.max(maxPay, 200000);
    S.z = new Float32Array(n); for (let i = 0; i < n; i++) S.z[i] = N.pay[i] ? Math.max(0.02, (N.pay[i] - 20000) / (S.maxPay - 20000)) * 0.9 : 0.02;
    // colours and sizes never change
    const col = new Float32Array(n * 3), sz = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const di = G.bodies[N.body[i]].dept, g = (N.grade[i] || "").replace(/\s/g, "").toLowerCase();
      const c = hsl(S.hue[di], 0.75, GRADE_L[g] || 0.5); col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
      sz[i] = 0.16 + Math.sqrt(N.below_fte[i] || 0) * 0.032 + (N.parent[i] < 0 ? 0.2 : 0);
    }
    S.col = col; S.sz = sz;
    S.pos = new Float32Array(n * 3); S.from = new Float32Array(n * 3); S.to = new Float32Array(n * 3);
    S.al = new Float32Array(n); S.screen = new Float32Array(n * 2); S.vis = new Uint8Array(n);
    S.pts = { pos: buffer(S.pos, true), col: buffer(col), sz: buffer(sz), al: buffer(S.al, true) };
    // halos: one per post with junior staff
    S.jn = []; for (let i = 0; i < n; i++) if (N.junior_fte[i] > 0) S.jn.push(i);
    const jc = new Float32Array(S.jn.length * 3), js = new Float32Array(S.jn.length);
    S.jn.forEach((i, k) => { const c = hsl(S.hue[G.bodies[N.body[i]].dept], 0.75, 0.6); jc[k * 3] = c[0]; jc[k * 3 + 1] = c[1]; jc[k * 3 + 2] = c[2]; js[k] = 0.3 + Math.sqrt(N.junior_fte[i]) * 0.05; });
    S.hpos = new Float32Array(S.jn.length * 3); S.hal = new Float32Array(S.jn.length);
    S.halo = { pos: buffer(S.hpos, true), col: buffer(jc), sz: buffer(js), al: buffer(S.hal, true) };
    // lines (parent->child) and pillars (disc->post)
    S.ln = []; for (let i = 0; i < n; i++) if (N.parent[i] >= 0) S.ln.push(i);
    const lc = new Float32Array(S.ln.length * 6), pc = new Float32Array(n * 6);
    S.ln.forEach((i, k) => { for (let e = 0; e < 2; e++) { lc[k * 6 + e * 3] = col[i * 3]; lc[k * 6 + e * 3 + 1] = col[i * 3 + 1]; lc[k * 6 + e * 3 + 2] = col[i * 3 + 2]; } });
    for (let i = 0; i < n; i++) for (let e = 0; e < 2; e++) { pc[i * 6 + e * 3] = col[i * 3]; pc[i * 6 + e * 3 + 1] = col[i * 3 + 1]; pc[i * 6 + e * 3 + 2] = col[i * 3 + 2]; }
    S.lpos = new Float32Array(S.ln.length * 6); S.lal = new Float32Array(S.ln.length * 2);
    S.ppos = new Float32Array(n * 6); S.pal = new Float32Array(n * 2);
    S.lines = { pos: buffer(S.lpos, true), col: buffer(lc), al: buffer(S.lal, true) };
    S.pillars = { pos: buffer(S.ppos, true), col: buffer(pc), al: buffer(S.pal, true) };
    S.ring = { pos: buffer(new Float32Array(3), true), col: buffer(new Float32Array([1, 1, 1])), sz: buffer(new Float32Array([1]), true), al: buffer(new Float32Array([1])) };
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

  // --- layouts: every node gets a target position for the current focus -----------
  // Radial tree: siblings share their parent's angle in proportion to the posts beneath.
  function placeTree(root, lo, hi, r0, dr, centre) {
    const N = S.N;
    const weight = i => (N.below_senior[i] || 1) + 0.6;
    (function place(i, a0, a1, d) {
      const a = (a0 + a1) / 2, r = (centre && d === 0) ? 0 : r0 + d * dr;
      S.to[i * 3] = Math.cos(a) * r; S.to[i * 3 + 1] = Math.sin(a) * r; S.to[i * 3 + 2] = S.z[i];
      const ks = S.kids[i]; if (!ks.length) return;
      const ws = ks.map(weight), wsum = ws.reduce((x, y) => x + y, 0);
      let c = a0; ks.forEach((k, j) => { const span = (a1 - a0) * ws[j] / wsum; place(k, c, c + span, d + 1); c += span; });
    })(root, lo, hi, 0);
  }
  function placeBody(bi, lo, hi, r0, dr, centre) {
    const rs = S.roots[bi]; if (!rs.length) return;
    const ws = rs.map(i => (S.N.below_senior[i] || 1) + 0.6), wsum = ws.reduce((x, y) => x + y, 0);
    let c = lo; rs.forEach((r, j) => { const span = (hi - lo) * ws[j] / wsum; placeTree(r, c, c + span, r0, dr, centre && rs.length === 1); c += span; });
  }
  function sectors(items, weightOf, gap) {
    const w = items.map(weightOf), wsum = w.reduce((a, b) => a + b, 0); const out = []; let a0 = -Math.PI / 2;
    items.forEach((it, k) => { const span = 2 * Math.PI * w[k] / wsum; out.push([a0 + span * gap, a0 + span * (1 - gap)]); a0 += span; });
    return out;
  }
  function layout(f) {
    const G = S.G, B = G.bodies, D = G.departments;
    S.vis.fill(0);
    if (f.kind === "gov") {
      const sec = sectors(S.order, di => Math.sqrt(Math.max(S.deptFte[di], 30)) + 6, 0.04);
      S.sector = {}; S.order.forEach((di, k) => { S.sector[di] = sec[k]; });
      S.order.forEach(di => {
        const [s0, s1] = S.sector[di]; const bs = D[di].bodies;
        const w = bs.map(bi => Math.sqrt(Math.max(B[bi].senior, 1)) + 1.5), ws = w.reduce((a, b) => a + b, 0); let c = s0;
        bs.forEach((bi, k) => { const span = (s1 - s0) * w[k] / ws; placeBody(bi, c + span * 0.08, c + span * 0.92, 0.62, 0.15, false); c += span; });
      });
      S.vis.fill(1); S.sizeScale = 1;
    } else if (f.kind === "dept") {
      const bs = D[f.d].bodies.slice().sort((a, b) => B[b].fte - B[a].fte);
      const sec = sectors(bs, bi => Math.sqrt(Math.max(B[bi].senior, 1)) + 2, 0.06);
      bs.forEach((bi, k) => placeBody(bi, sec[k][0], sec[k][1], 0.45, 0.17, false));
      for (let i = 0; i < S.n; i++) if (B[S.N.body[i]].dept === f.d) S.vis[i] = 1;
      S.sizeScale = 1.25;
    } else if (f.kind === "body") {
      placeBody(f.b, -Math.PI / 2, Math.PI * 1.5, 0.28, 0.24, true);
      for (let i = 0; i < S.n; i++) if (S.N.body[i] === f.b) S.vis[i] = 1;
      S.sizeScale = 1.6;
    } else {
      placeTree(f.p, -Math.PI / 2, Math.PI * 1.5, 0.3, 0.26, true);
      (function mark(i) { S.vis[i] = 1; S.kids[i].forEach(mark); })(f.p);
      S.sizeScale = 1.8;
    }
    // nodes out of view keep their last place, so a morph never flings them across the disc
    for (let i = 0; i < S.n; i++) if (!S.vis[i]) { S.to[i * 3] = S.pos[i * 3]; S.to[i * 3 + 1] = S.pos[i * 3 + 1]; S.to[i * 3 + 2] = S.pos[i * 3 + 2]; }
  }
  function applyAlpha() {
    for (let i = 0; i < S.n; i++) S.al[i] = S.vis[i] ? 1 : 0;      // out of focus: gone, not ghosted — the view is the level
    S.jn.forEach((i, k) => { S.hal[k] = S.vis[i] ? 0.07 : 0; });
    S.ln.forEach((i, k) => { const v = S.vis[i] && S.vis[S.N.parent[i]]; S.lal[k * 2] = v ? 0.1 : 0; S.lal[k * 2 + 1] = v ? 0.22 : 0; });
    for (let i = 0; i < S.n; i++) { S.pal[i * 2] = S.vis[i] ? 0.012 : 0; S.pal[i * 2 + 1] = S.vis[i] ? 0.08 : 0; }
    upload(S.pts.al, S.al); upload(S.halo.al, S.hal); upload(S.lines.al, S.lal); upload(S.pillars.al, S.pal);
  }
  function uploadAll() {
    const p = S.pos, N = S.N;
    upload(S.pts.pos, p);
    S.jn.forEach((i, k) => { S.hpos[k * 3] = p[i * 3]; S.hpos[k * 3 + 1] = p[i * 3 + 1]; S.hpos[k * 3 + 2] = p[i * 3 + 2] * 0.5; }); upload(S.halo.pos, S.hpos);
    S.ln.forEach((i, k) => { const q = N.parent[i]; S.lpos[k * 6] = p[q * 3]; S.lpos[k * 6 + 1] = p[q * 3 + 1]; S.lpos[k * 6 + 2] = p[q * 3 + 2]; S.lpos[k * 6 + 3] = p[i * 3]; S.lpos[k * 6 + 4] = p[i * 3 + 1]; S.lpos[k * 6 + 5] = p[i * 3 + 2]; }); upload(S.lines.pos, S.lpos);
    for (let i = 0; i < S.n; i++) { S.ppos[i * 6] = p[i * 3]; S.ppos[i * 6 + 1] = p[i * 3 + 1]; S.ppos[i * 6 + 2] = 0; S.ppos[i * 6 + 3] = p[i * 3]; S.ppos[i * 6 + 4] = p[i * 3 + 1]; S.ppos[i * 6 + 5] = p[i * 3 + 2]; } upload(S.pillars.pos, S.ppos);
  }

  // --- focus: the one operation everything else calls --------------------------------
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
  function drillTo(i) {           // a click on post i: the next level down that makes sense
    const f = S.focus, B = S.B, N = S.N, bi = N.body[i], di = B[bi].dept;
    if (f.kind === "gov") return setFocus({ kind: "dept", d: di, b: -1, p: -1 }, true);
    if (f.kind === "dept") return setFocus({ kind: "body", d: di, b: bi, p: -1 }, true);
    if (S.kids[i].length && !(f.kind === "post" && f.p === i)) return setFocus({ kind: "post", d: di, b: bi, p: i }, true);
    showDetail(i);
  }
  // camera framing: fit the visible nodes
  function frameFocus(instant) {
    let cx = 0, cy = 0, cz = 0, k = 0;
    for (let i = 0; i < S.n; i++) if (S.vis[i]) { cx += S.to[i * 3]; cy += S.to[i * 3 + 1]; cz += S.to[i * 3 + 2]; k++; }
    if (!k) return; cx /= k; cy /= k; cz /= k;
    let r = 0; for (let i = 0; i < S.n; i++) if (S.vis[i]) r = Math.max(r, Math.hypot(S.to[i * 3] - cx, S.to[i * 3 + 1] - cy));
    const dist = Math.max(0.9, r * 2.35 + 0.6), phi = S.focus.kind === "gov" ? 0.72 : 0.62;
    S.camTo = { target: [cx, cy, Math.min(cz, 0.25)], dist, phi };
    if (instant) { S.target = S.camTo.target.slice(); S.dist = dist; S.phi = phi; S.camTo = null; }
  }

  // --- the side panel: trail, list, search ---------------------------------------------
  function trail() {
    const f = S.focus, G = S.G, t = [["UK government", { kind: "gov", d: -1, b: -1, p: -1 }]];
    if (f.d >= 0) t.push([G.departments[f.d].name, { kind: "dept", d: f.d, b: -1, p: -1 }]);
    if (f.b >= 0) t.push([G.bodies[f.b].name, { kind: "body", d: f.d, b: f.b, p: -1 }]);
    if (f.p >= 0) { const chain = []; let p = f.p; while (p >= 0) { chain.unshift(p); p = S.N.parent[p]; } chain.forEach(pi => { if (S.kids[pi].length) t.push([S.N.title[pi] || "(untitled post)", { kind: "post", d: f.d, b: f.b, p: pi }]); }); }
    return t;
  }
  function renderPanel() {
    const f = S.focus, G = S.G, N = S.N, B = G.bodies, D = G.departments;
    const t = trail();
    crumbsEl.innerHTML = t.map(([name, ff], k) => k === t.length - 1 ? `<span aria-current="page">${esc(name)}</span>` : `<a href="#" data-k="${k}">${esc(name)}</a>`).join('<i class="sep">›</i>');
    crumbsEl.querySelectorAll("a").forEach(a => a.addEventListener("click", e => { e.preventDefault(); setFocus(t[+a.dataset.k][1], true); }));
    $("upbtn").hidden = f.kind === "gov";
    let head = "", items = [];
    if (f.kind === "gov") {
      head = `<b>UK central government</b><span>${D.length} departments · ${B.length} bodies · ${fmt(S.deptFte.reduce((a, b) => a + b, 0))} FTE · click a department</span>`;
      items = S.order.map(di => ({ name: D[di].name, meta: `${fmt(S.deptFte[di])} FTE · ${D[di].bodies.length} bod${D[di].bodies.length === 1 ? "y" : "ies"}`, f: { kind: "dept", d: di, b: -1, p: -1 }, hue: S.hue[di] }));
    } else if (f.kind === "dept") {
      const d = D[f.d];
      head = `<b>${esc(d.name)}</b><span>${fmt(S.deptFte[f.d])} FTE · ${d.bodies.length} bod${d.bodies.length === 1 ? "y" : "ies"} · click a body</span>`;
      items = d.bodies.slice().sort((a, b) => B[b].fte - B[a].fte).map(bi => ({ name: B[bi].name, meta: `${fmt(B[bi].fte)} FTE · ${B[bi].senior} senior posts` + (B[bi].head ? ` · top: ${esc(B[bi].head)}` : ""), f: { kind: "body", d: f.d, b: bi, p: -1 }, hue: S.hue[f.d], i: S.roots[bi][0] }));
    } else {
      const b = B[f.b];
      head = f.kind === "body"
        ? `<b>${esc(b.name)}</b><span>${fmt(b.fte)} FTE · ${b.senior} senior posts · snapshot ${esc(b.as_of)} · click a post that has reports</span>`
        : `<b>${esc(N.title[f.p])}</b><span>${esc(N.grade[f.p])}${N.pay[f.p] ? " · from £" + N.pay[f.p].toLocaleString() : ""} · ${fmt(N.below_fte[f.p])} FTE beneath</span>`;
      const list = f.kind === "body" ? S.roots[f.b] : S.kids[f.p];
      items = list.slice().sort((a, c) => N.below_fte[c] - N.below_fte[a]).map(i => ({
        name: N.title[i] || "(untitled post)", meta: `${esc(N.grade[i])}${N.pay[i] ? " · from £" + N.pay[i].toLocaleString() : ""} · ${fmt(N.below_fte[i])} FTE beneath` + (S.kids[i].length ? ` · ${S.kids[i].length} direct senior reports` : ""),
        f: S.kids[i].length ? { kind: "post", d: f.d, b: f.b, p: i } : null, i, hue: S.hue[f.d] }));
    }
    navHead.innerHTML = head;
    navList.innerHTML = items.slice(0, 400).map((it, k) => `<li><a href="#" data-k="${k}" class="${it.f ? "" : "leaf"}"><i style="background:hsl(${it.hue},75%,60%)"></i><span class="nm">${esc(it.name)}</span><span class="mt">${it.meta}</span></a></li>`).join("")
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
  // search: bodies and posts, by substring, best dozen
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

  // --- camera and drawing ----------------------------------------------------------------
  let W = 1, Hh = 1, pxr = 1;
  function resize() {
    pxr = Math.min(window.devicePixelRatio || 1, 2);
    const r = stage.getBoundingClientRect(); W = Math.max(1, Math.floor(r.width)); Hh = Math.max(1, Math.floor(r.height));
    canvas.width = Math.floor(W * pxr); canvas.height = Math.floor(Hh * pxr); canvas.style.width = W + "px"; canvas.style.height = Hh + "px";
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  window.addEventListener("resize", resize); resize();
  function camera() {
    const eye = [S.target[0] + S.dist * Math.cos(S.phi) * Math.cos(S.theta), S.target[1] + S.dist * Math.cos(S.phi) * Math.sin(S.theta), S.target[2] + S.dist * Math.sin(S.phi)];
    return mul(perspective(0.9, W / Hh, 0.02, 40), lookAt(eye, S.target, [0, 0, 1]));
  }
  const ease = t => 1 - Math.pow(1 - t, 3);
  function draw(now) {
    requestAnimationFrame(draw); if (!S.G) return;
    const dt = Math.min(0.05, (now - (S.last || now)) / 1000); S.last = now;
    if (S.grow < 1) S.grow = Math.min(1, (now - S.t0) / 2600);
    const g = ease(S.grow);
    if (S.morph < 1) {
      S.morph = Math.min(1, (now - S.morphT0) / 1000); const e = ease(S.morph);
      for (let i = 0; i < S.n * 3; i++) S.pos[i] = S.from[i] + (S.to[i] - S.from[i]) * e;
      uploadAll();
    }
    if (S.camTo) { const c = S.camTo, k = 1 - Math.pow(0.02, dt);   // exponential ease, frame-rate independent
      for (let j = 0; j < 3; j++) S.target[j] += (c.target[j] - S.target[j]) * k;
      S.dist += (c.dist - S.dist) * k; S.phi += (c.phi - S.phi) * k;
      if (Math.abs(S.dist - c.dist) < 0.003 && Math.hypot(S.target[0] - c.target[0], S.target[1] - c.target[1]) < 0.003) S.camTo = null; }
    const idle = (now - S.idleSince) > 6000;
    if (S.orbit && !S.drag && S.focus.kind === "gov" && idle) S.theta += dt * 0.1;
    const mvp = camera();
    gl.clearColor(0.035, 0.04, 0.07, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    // the intro: the whole figure scales up from the centre, through the matrix
    const m = mvp.slice(); for (let j = 0; j < 12; j++) m[j] *= g;
    gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, m);
    if (S.showPillars) { attrib(LN, "p", S.pillars.pos, 3); attrib(LN, "col", S.pillars.col, 3); attrib(LN, "a", S.pillars.al, 1); gl.drawArrays(gl.LINES, 0, S.n * 2); }
    attrib(LN, "p", S.lines.pos, 3); attrib(LN, "col", S.lines.col, 3); attrib(LN, "a", S.lines.al, 1); gl.drawArrays(gl.LINES, 0, S.ln.length * 2);
    gl.useProgram(PT); gl.uniformMatrix4fv(uni(PT, "mvp"), false, m); gl.uniform1f(uni(PT, "pxr"), pxr); gl.uniform1f(uni(PT, "scale"), S.sizeScale);
    attrib(PT, "p", S.halo.pos, 3); attrib(PT, "col", S.halo.col, 3); attrib(PT, "sz", S.halo.sz, 1); attrib(PT, "a", S.halo.al, 1); gl.drawArrays(gl.POINTS, 0, S.jn.length);
    attrib(PT, "p", S.pts.pos, 3); attrib(PT, "col", S.pts.col, 3); attrib(PT, "sz", S.pts.sz, 1); attrib(PT, "a", S.pts.al, 1); gl.drawArrays(gl.POINTS, 0, S.n);
    if (S.hover >= 0 && S.vis[S.hover]) {
      upload(S.ring.pos, new Float32Array([S.pos[S.hover * 3], S.pos[S.hover * 3 + 1], S.pos[S.hover * 3 + 2]]));
      upload(S.ring.sz, new Float32Array([Math.max(S.sz[S.hover] * S.sizeScale, 0.45) + 0.25]));
      gl.useProgram(RING); gl.uniformMatrix4fv(uni(RING, "mvp"), false, m); gl.uniform1f(uni(RING, "pxr"), pxr); gl.uniform1f(uni(RING, "scale"), 1);
      attrib(RING, "p", S.ring.pos, 3); attrib(RING, "col", S.ring.col, 3); attrib(RING, "sz", S.ring.sz, 1); attrib(RING, "a", S.ring.al, 1); gl.drawArrays(gl.POINTS, 0, 1);
    }
    project(m); labels(m);
  }
  function project(m) {
    const p = S.pos, s = S.screen;
    for (let i = 0; i < S.n; i++) {
      if (!S.vis[i]) { s[i * 2] = -1e4; s[i * 2 + 1] = -1e4; continue; }
      const x = p[i * 3], y = p[i * 3 + 1], z = p[i * 3 + 2];
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
      if (cw <= 0.001) { s[i * 2] = -1e4; s[i * 2 + 1] = -1e4; continue; }
      s[i * 2] = ((m[0] * x + m[4] * y + m[8] * z + m[12]) / cw * 0.5 + 0.5) * W;
      s[i * 2 + 1] = (0.5 - (m[1] * x + m[5] * y + m[9] * z + m[13]) / cw * 0.5) * Hh;
    }
  }
  // labels: the level's names, largest first, none on top of another
  let labelWant = [], labelKey = "";
  function labelsFor() {
    const f = S.focus, G = S.G, B = G.bodies, N = S.N, out = [];
    if (f.kind === "gov") {
      S.order.slice(0, 18).forEach(di => { const [s0, s1] = S.sector[di], a = (s0 + s1) / 2; out.push({ text: G.departments[di].name, x: Math.cos(a) * 1.3, y: Math.sin(a) * 1.3, z: 0.02, hue: S.hue[di], f: { kind: "dept", d: di, b: -1, p: -1 }, big: true }); });
    } else if (f.kind === "dept") {
      G.departments[f.d].bodies.slice().sort((a, b) => B[b].fte - B[a].fte).slice(0, 40).forEach(bi => { const r = S.roots[bi][0]; if (r == null) return;
        out.push({ text: B[bi].name, i: r, hue: S.hue[f.d], f: { kind: "body", d: f.d, b: bi, p: -1 }, big: B[bi].fte > S.deptFte[f.d] * 0.1 }); });
    } else {
      const list = []; for (let i = 0; i < S.n; i++) if (S.vis[i]) list.push(i);
      list.sort((a, b) => N.below_fte[b] - N.below_fte[a]).slice(0, 34).forEach(i => out.push({ text: N.title[i] || "(untitled post)", i, hue: S.hue[f.d], f: S.kids[i].length ? { kind: "post", d: f.d, b: f.b, p: i } : null, big: N.below_fte[i] > 200 }));
    }
    return out;
  }
  function labels(m) {
    const key = JSON.stringify(S.focus);
    if (key !== labelKey) { labelKey = key; labelWant = labelsFor(); labelsEl.innerHTML = "";
      labelWant.forEach(l => { const el = document.createElement("div"); el.className = "org3d-label" + (l.big ? " big" : ""); el.textContent = l.text; el.style.color = `hsl(${l.hue},80%,78%)`;
        el.addEventListener("click", () => { if (l.f) setFocus(l.f, true); else showDetail(l.i); }); el.addEventListener("pointerenter", () => { if (l.i != null) S.hover = l.i; }); labelsEl.appendChild(el); l.el = el; }); }
    const placed = [];
    for (const l of labelWant) {
      let px, py;
      if (l.i != null) { px = S.screen[l.i * 2]; py = S.screen[l.i * 2 + 1] - 12; }
      else { const cw = m[3] * l.x + m[7] * l.y + m[11] * l.z + m[15]; if (cw <= 0.001) { l.el.style.opacity = 0; continue; }
        px = ((m[0] * l.x + m[4] * l.y + m[8] * l.z + m[12]) / cw * 0.5 + 0.5) * W; py = (0.5 - (m[1] * l.x + m[5] * l.y + m[9] * l.z + m[13]) / cw * 0.5) * Hh; }
      if (px < -50 || py < -20 || px > W + 50 || py > Hh + 20 || placed.some(([qx, qy]) => Math.abs(qx - px) < 140 && Math.abs(qy - py) < 15)) { l.el.style.opacity = 0; continue; }
      placed.push([px, py]); l.el.style.opacity = Math.max(0, (S.grow - 0.4) * 1.7) * (S.morph < 0.6 ? S.morph : 1);
      l.el.style.transform = `translate(${px}px, ${py}px)`;
    }
  }

  // --- pointer: drag to turn, click to drill, background to go up ------------------------
  function pick(mx, my) {
    let best = -1, bd = 14 * 14; const s = S.screen;
    for (let i = 0; i < S.n; i++) { if (!S.vis[i]) continue; const dx = s[i * 2] - mx, dy = s[i * 2 + 1] - my, d = dx * dx + dy * dy - S.sz[i] * 6; if (d < bd) { bd = d; best = i; } }
    return best;
  }
  canvas.addEventListener("pointerdown", e => { S.drag = { x: e.clientX, y: e.clientY, th: S.theta, ph: S.phi }; S.moved = 0; canvas.setPointerCapture(e.pointerId); S.idleSince = performance.now(); });
  canvas.addEventListener("pointerup", e => {
    const wasClick = S.drag && S.moved < 5; S.drag = null;
    if (!wasClick) return;
    const r = canvas.getBoundingClientRect(), i = pick(e.clientX - r.left, e.clientY - r.top);
    if (i >= 0) drillTo(i); else up();
  });
  canvas.addEventListener("pointermove", e => {
    S.idleSince = performance.now();
    if (S.drag) { S.moved = Math.max(S.moved, Math.abs(e.clientX - S.drag.x) + Math.abs(e.clientY - S.drag.y));
      if (S.moved >= 5) { S.theta = S.drag.th - (e.clientX - S.drag.x) * 0.006; S.phi = Math.max(0.08, Math.min(1.45, S.drag.ph + (e.clientY - S.drag.y) * 0.005)); S.camTo = null; tip.hidden = true; } return; }
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
    else if (e.key === "ArrowUp") S.phi = Math.min(1.45, S.phi + 0.08); else if (e.key === "ArrowDown") S.phi = Math.max(0.08, S.phi - 0.08);
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
  $("reset").addEventListener("click", () => { S.theta = 0.9; setFocus({ kind: "gov", d: -1, b: -1, p: -1 }, true); S.t0 = performance.now(); S.grow = REDUCED ? 1 : 0; S.idleSince = 0; });

  // --- record the canvas to a WebM ------------------------------------------------------------
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
