/* The shape of the state — every senior post in UK central government as
   a city at night, drawn in WebGL from /api/family/organograms/graph.json.

   Every post is a building. Its footprint is the staff beneath it, its
   height the pay band, its lit windows flicker, and a neon rim marks the
   roof. The ground is a map: every department a district, every body a
   block, streets between them with traffic running. You arrive from the
   sky. Open a department and its district grows to fill the map; open a
   body and its buildings re-form as an organisation chart — the head at
   the back, each level of reports a row nearer you, lit lines between
   them, and the traffic now runs along the reporting lines. Fly-through
   glides you down into the streets; Record captures it to a video.

   Navigation follows what the good hierarchy explorers share: overview
   first, click to drill, the thing you opened laid out afresh to fill the
   view, a trail always visible, one step back always one click or Esc
   away, and a list beside the picture so nothing has to be hunted for.

   Raw WebGL 1 with instanced drawing (ANGLE_instanced_arrays; without it
   the buildings become points), no library, no request to any other host.
*/
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const canvas = $("c"), stage = $("stage"), tip = $("tip"), labelsEl = $("labels"), nogl = $("nogl");
  const crumbsEl = $("crumbs"), navList = $("navlist"), navHead = $("navhead"), search = $("search"), hits = $("hits");
  const gl = canvas.getContext("webgl", { antialias: true, alpha: false, preserveDrawingBuffer: false, powerPreference: "high-performance" });
  if (!gl) { nogl.hidden = false; $("panel").hidden = true; return; }
  const EXT = gl.getExtension("ANGLE_instanced_arrays");
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
  const FOG = "clamp(1.35 - max(cp.w, 0.0) * 0.14, 0.18, 1.0)";
  const VS_BOX = `
    attribute vec3 v; attribute vec3 nrm; attribute vec2 uv;
    attribute vec3 ipos; attribute vec2 isz; attribute vec3 icol; attribute float ia;
    uniform mat4 mvp; uniform float rise;
    varying vec3 vc; varying float va; varying vec2 vuv; varying float vshade; varying float vh; varying float vtop;
    void main() {
      float h = ipos.z * rise;
      vec3 w = vec3(ipos.x + v.x * isz.x, ipos.y + v.y * isz.y, v.z * h);
      vec4 cp = mvp * vec4(w, 1.0); gl_Position = cp;
      vtop = step(0.5, nrm.z);
      vshade = mix(0.5 + 0.35 * max(0.0, dot(nrm.xy, normalize(vec2(-0.55, -0.83)))), 1.0, vtop);
      vuv = vec2(uv.x * max(isz.x, isz.y) * 160.0, uv.y * h * 70.0);
      vc = icol; va = ia * ${FOG}; vh = v.z;
    }`;
  const FS_BOX = `
    precision mediump float; uniform float t;
    varying vec3 vc; varying float va; varying vec2 vuv; varying float vshade; varying float vh; varying float vtop;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    void main() {
      if (va <= 0.002) discard;
      vec3 c = vc * 0.16 * vshade;                                   // the dark body of the building
      vec2 cell = floor(vuv); vec2 f = fract(vuv);
      float lit = step(0.58, hash(cell + floor(t * 0.12 + hash(cell * 1.7) * 9.0)));
      float win = step(0.22, f.x) * step(f.x, 0.78) * step(0.18, f.y) * step(f.y, 0.72) * (1.0 - vtop);
      c += vc * win * lit * 0.75 * (0.5 + 0.5 * vshade);              // lit windows, slowly changing
      c += vc * smoothstep(0.9, 1.0, vh) * (1.0 - vtop) * 0.7;        // neon rim under the roof
      c += vc * vtop * 0.45;                                          // the roof glows
      gl_FragColor = vec4(c * va, 1.0);
    }`;
  const VS_EDGE = `
    attribute vec3 v; attribute vec3 ipos; attribute vec2 isz; attribute vec3 icol; attribute float ia;
    uniform mat4 mvp; uniform float rise; varying vec3 vc; varying float va;
    void main() { vec4 cp = mvp * vec4(ipos.x + v.x * isz.x, ipos.y + v.y * isz.y, v.z * ipos.z * rise, 1.0); gl_Position = cp; vc = icol; va = ia * ${FOG}; }`;
  const VS_PT = `
    attribute vec3 p; attribute vec3 col; attribute float sz; attribute float a;
    uniform mat4 mvp; uniform float pxr; uniform float scale; uniform float rise;
    varying vec3 vc; varying float va;
    void main() {
      vec4 cp = mvp * vec4(p.x, p.y, p.z * rise, 1.0); gl_Position = cp;
      float d = max(cp.w, 0.001);
      gl_PointSize = clamp(sz * scale * pxr * 60.0 / d, 1.0 * pxr, 34.0 * pxr);
      vc = col; va = a * ${FOG};
    }`;
  const FS_PT = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = dot(d, d) * 4.0;
      if (r > 1.0) discard;
      gl_FragColor = vec4(vc * (exp(-r * 6.0) * 0.9 + (1.0 - r) * 0.1) * va, 1.0);
    }`;
  const FS_RING = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = sqrt(dot(d, d)) * 2.0;
      gl_FragColor = vec4(vc * smoothstep(0.6, 0.68, r) * (1.0 - smoothstep(0.86, 0.96, r)) * va, 1.0);
    }`;
  const VS_LN = `
    attribute vec3 p; attribute vec3 col; attribute float a;
    uniform mat4 mvp; uniform float rise; varying vec3 vc; varying float va;
    void main() { vec4 cp = mvp * vec4(p.x, p.y, p.z * rise, 1.0); gl_Position = cp; vc = col; va = a * ${FOG}; }`;
  const FS_LN = `precision mediump float; varying vec3 vc; varying float va; void main() { gl_FragColor = vec4(vc * va, 1.0); }`;
  const FS_FLAT = `precision mediump float; varying vec3 vc; varying float va; void main() { gl_FragColor = vec4(vc * va, 1.0); }`;
  function program(vs, fs) {
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
    const pr = gl.createProgram(); gl.attachShader(pr, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    return pr;
  }
  const PT = program(VS_PT, FS_PT), RING = program(VS_PT, FS_RING), LN = program(VS_LN, FS_LN);
  const BOX = EXT ? program(VS_BOX, FS_BOX) : null, EDGE = EXT ? program(VS_EDGE, FS_FLAT) : null;
  const uni = (pr, n) => gl.getUniformLocation(pr, n);
  function buffer(arr, dyn) { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, arr, dyn ? gl.DYNAMIC_DRAW : gl.STATIC_DRAW); return b; }
  function upload(b, arr) { gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, arr, gl.DYNAMIC_DRAW); }
  const enabled = new Set();
  function attrib(pr, name, buf, size, div) {
    const l = gl.getAttribLocation(pr, name); if (l < 0) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(l); enabled.add(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, 0, 0);
    if (EXT) EXT.vertexAttribDivisorANGLE(l, div || 0);
  }
  function disableAll() { for (const l of enabled) { gl.disableVertexAttribArray(l); if (EXT) EXT.vertexAttribDivisorANGLE(l, 0); } enabled.clear(); }

  function hsl(h, s, l) {
    const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return [f(0), f(8), f(4)];
  }
  // Neon: a dozen saturated hues, restated a little cooler for the next dozen.
  const HUES = [190, 320, 45, 150, 270, 20, 205, 340, 80, 300, 170, 235];
  const GRADE_L = { scs4: 0.9, scs3: 0.78, scs2: 0.66, scs1a: 0.6, scs1: 0.56 };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = v => Math.round(v || 0).toLocaleString();

  // --- state ---------------------------------------------------------------------
  const S = {
    G: null, n: 0, N: null, B: null, D: null, kids: null, order: null, deptFte: null, hue: null,
    pos: null, from: null, to: null, morph: 1, morphT0: 0, screen: null, vis: null,
    theta: -1.1, phi: 1.45, dist: 7.5, target: [0, 0, 0], camTo: null, drag: null, moved: 0,
    orbit: !REDUCED, showTraffic: true, idleSince: performance.now(),
    focus: { kind: "gov", d: -1, b: -1, p: -1 }, hover: -1, sizeScale: 1,
    grow: REDUCED ? 1 : 0, t0: performance.now(), rects: {}, tour: null, segs: [],
  };

  // --- build the static parts --------------------------------------------------------
  function build(G) {
    S.G = G; const N = G.nodes, n = N.title.length; S.n = n; S.N = N; S.B = G.bodies; S.D = G.departments;
    S.deptFte = G.departments.map(d => d.bodies.reduce((s, bi) => s + (G.bodies[bi].fte || 0), 0));
    S.order = G.departments.map((_, i) => i).sort((a, b) => S.deptFte[b] - S.deptFte[a]);
    S.hue = new Array(G.departments.length); S.sat = new Array(G.departments.length);
    S.order.forEach((di, k) => { S.hue[di] = HUES[k % HUES.length]; S.sat[di] = k < HUES.length ? 0.85 : 0.6; });
    S.kids = Array.from({ length: n }, () => []); S.roots = Array.from({ length: G.bodies.length }, () => []);
    for (let i = 0; i < n; i++) { const p = N.parent[i]; if (p >= 0) S.kids[p].push(i); else S.roots[N.body[i]].push(i); }
    let maxPay = 0; for (let i = 0; i < n; i++) if (N.pay[i] > maxPay) maxPay = N.pay[i]; S.maxPay = Math.max(maxPay, 200000);
    S.z = new Float32Array(n); for (let i = 0; i < n; i++) S.z[i] = N.pay[i] ? Math.max(0.035, (N.pay[i] - 20000) / (S.maxPay - 20000)) * 0.8 : 0.035;
    const col = new Float32Array(n * 3), sz = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const di = G.bodies[N.body[i]].dept, g = (N.grade[i] || "").replace(/\s/g, "").toLowerCase();
      const c = hsl(S.hue[di], S.sat[di], GRADE_L[g] || 0.56); col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
      sz[i] = 0.12 + Math.sqrt(N.below_fte[i] || 0) * 0.02 + (N.parent[i] < 0 ? 0.14 : 0);
    }
    S.col = col; S.sz = sz;
    S.pos = new Float32Array(n * 3); S.from = new Float32Array(n * 3); S.to = new Float32Array(n * 3);
    S.fp = new Float32Array(n * 2); S.fpFrom = new Float32Array(n * 2); S.fpTo = new Float32Array(n * 2);   // footprints
    S.al = new Float32Array(n); S.screen = new Float32Array(n * 2); S.vis = new Uint8Array(n);
    S.pts = { pos: buffer(S.pos, true), col: buffer(col), sz: buffer(sz), al: buffer(S.al, true), fp: buffer(S.fp, true) };
    // the unit building: five faces, with normals and window coordinates; and its twelve edges
    const F = [], E = [];
    const face = (pts, nrm) => { const [a, b, c, d] = pts; for (const q of [a, b, c, a, c, d]) F.push(q[0], q[1], q[2], nrm[0], nrm[1], nrm[2], q[3], q[4]); };
    face([[-0.5, -0.5, 0, 0, 0], [0.5, -0.5, 0, 1, 0], [0.5, -0.5, 1, 1, 1], [-0.5, -0.5, 1, 0, 1]], [0, -1, 0]);
    face([[0.5, -0.5, 0, 0, 0], [0.5, 0.5, 0, 1, 0], [0.5, 0.5, 1, 1, 1], [0.5, -0.5, 1, 0, 1]], [1, 0, 0]);
    face([[0.5, 0.5, 0, 0, 0], [-0.5, 0.5, 0, 1, 0], [-0.5, 0.5, 1, 1, 1], [0.5, 0.5, 1, 0, 1]], [0, 1, 0]);
    face([[-0.5, 0.5, 0, 0, 0], [-0.5, -0.5, 0, 1, 0], [-0.5, -0.5, 1, 1, 1], [-0.5, 0.5, 1, 0, 1]], [-1, 0, 0]);
    face([[-0.5, -0.5, 1, 0, 0], [0.5, -0.5, 1, 1, 0], [0.5, 0.5, 1, 1, 1], [-0.5, 0.5, 1, 0, 1]], [0, 0, 1]);
    const corners = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]];
    for (let k = 0; k < 4; k++) { const a = corners[k], b = corners[(k + 1) % 4]; E.push(a[0], a[1], 1, b[0], b[1], 1); E.push(a[0], a[1], 0, a[0], a[1], 1); }
    S.unit = { geo: buffer(new Float32Array(F)), nv: F.length / 8, edges: buffer(new Float32Array(E)), ne: E.length / 3 };
    // geometry of the unit box is interleaved: 3 pos, 3 nrm, 2 uv
    S.jn = []; for (let i = 0; i < n; i++) if (N.junior_fte[i] > 0) S.jn.push(i);
    const jc = new Float32Array(S.jn.length * 3), js = new Float32Array(S.jn.length);
    S.jn.forEach((i, k) => { const di = G.bodies[N.body[i]].dept, c = hsl(S.hue[di], S.sat[di], 0.6); jc[k * 3] = c[0]; jc[k * 3 + 1] = c[1]; jc[k * 3 + 2] = c[2]; js[k] = 0.25 + Math.sqrt(N.junior_fte[i]) * 0.04; });
    S.hpos = new Float32Array(S.jn.length * 3); S.hal = new Float32Array(S.jn.length);
    S.halo = { pos: buffer(S.hpos, true), col: buffer(jc), sz: buffer(js), al: buffer(S.hal, true) };
    S.ln = []; for (let i = 0; i < n; i++) if (N.parent[i] >= 0) S.ln.push(i);
    const lc = new Float32Array(S.ln.length * 6);
    S.ln.forEach((i, k) => { for (let e = 0; e < 2; e++) { lc[k * 6 + e * 3] = col[i * 3]; lc[k * 6 + e * 3 + 1] = col[i * 3 + 1]; lc[k * 6 + e * 3 + 2] = col[i * 3 + 2]; } });
    S.lpos = new Float32Array(S.ln.length * 6); S.lal = new Float32Array(S.ln.length * 2);
    S.lines = { pos: buffer(S.lpos, true), col: buffer(lc), al: buffer(S.lal, true) };
    S.ring = { pos: buffer(new Float32Array(3), true), col: buffer(new Float32Array([1, 1, 1])), sz: buffer(new Float32Array([1]), true), al: buffer(new Float32Array([1])) };
    // the ground: a dark plane (opaque), a grid, district floors, street lines and traffic
    S.plane = { pos: buffer(new Float32Array([-6, -6, -0.001, 6, -6, -0.001, 6, 6, -0.001, -6, -6, -0.001, 6, 6, -0.001, -6, 6, -0.001])), col: buffer(new Float32Array(18).fill(0.05)), al: buffer(new Float32Array(6).fill(1)) };
    const gp = [], gc = [], ga = [];
    for (let v = -3; v <= 3.001; v += 0.25) { gp.push(v, -3, 0, v, 3, 0, -3, v, 0, 3, v, 0); for (let e = 0; e < 4; e++) { gc.push(0.4, 0.5, 0.8); ga.push(0.035); } }
    S.grid = { pos: buffer(new Float32Array(gp)), col: buffer(new Float32Array(gc)), al: buffer(new Float32Array(ga)), n: ga.length };
    S.floor = { pos: buffer(new Float32Array(0), true), col: buffer(new Float32Array(0), true), al: buffer(new Float32Array(0), true), n: 0 };
    S.streets = { pos: buffer(new Float32Array(0), true), col: buffer(new Float32Array(0), true), al: buffer(new Float32Array(0), true), n: 0 };
    const TN = 700; S.traffic = { n: TN, seg: new Int32Array(TN), ph: new Float32Array(TN), sp: new Float32Array(TN), pos: buffer(new Float32Array(TN * 3), true), col: buffer(new Float32Array(TN * 3), true), sz: buffer(new Float32Array(TN).fill(0.16)), al: buffer(new Float32Array(TN).fill(0.9)), arr: new Float32Array(TN * 3), carr: new Float32Array(TN * 3) };
    for (let k = 0; k < TN; k++) { S.traffic.ph[k] = Math.random(); S.traffic.sp[k] = 0.05 + Math.random() * 0.12; }
    $("sub").textContent = `${n.toLocaleString()} senior posts in ${G.bodies.length} bodies under ${G.departments.length} departments, ${fmt(S.deptFte.reduce((a, b) => a + b, 0))} staff (FTE) beneath them.`;
    $("asof").textContent = G.as_of ? `newest snapshot ${G.as_of}` : "";
    layout(S.focus);
    for (let i = 0; i < n * 3; i++) S.pos[i] = S.to[i];
    for (let i = 0; i < n * 2; i++) S.fp[i] = S.fpTo[i];
    S.morph = 1; applyAlpha(); uploadAll();
    const q = new URLSearchParams(location.search);
    if (q.has("p") || q.has("b") || q.has("d")) {
      const f = { kind: "gov", d: -1, b: -1, p: -1 };
      if (q.has("d")) { f.kind = "dept"; f.d = +q.get("d"); }
      if (q.has("b")) { f.kind = "body"; f.b = +q.get("b"); f.d = G.bodies[f.b] ? G.bodies[f.b].dept : -1; }
      if (q.has("p")) { f.kind = "post"; f.p = +q.get("p"); f.b = N.body[f.p]; f.d = G.bodies[f.b].dept; }
      if ((f.kind === "dept" && G.departments[f.d]) || (f.kind === "body" && G.bodies[f.b]) || (f.kind === "post" && N.title[f.p] != null)) { setFocus(f, false); return; }
    }
    renderPanel();
    // arrival from the sky: a long slow descent to the three-quarter view
    frameFocus(false, 4200, 900);
  }

  // --- layouts ---------------------------------------------------------------------------
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
  // A body's buildings on their block: depth-first so a subtree keeps together; the
  // footprint is the staff beneath, capped by the plot.
  function placeBlock(bi, r) {
    const order = []; S.roots[bi].forEach(function walk(i) { order.push(i); S.kids[i].forEach(walk); });
    const n = order.length; if (!n) return;
    const cols = Math.max(1, Math.ceil(Math.sqrt(n * r.w / Math.max(r.h, 1e-6)))), rows = Math.ceil(n / cols);
    const cw = r.w / cols, ch = r.h / rows;
    order.forEach((i, k) => {
      S.to[i * 3] = r.x + cw * ((k % cols) + 0.5); S.to[i * 3 + 1] = r.y + ch * (Math.floor(k / cols) + 0.5); S.to[i * 3 + 2] = S.z[i];
      const want = 0.01 + Math.sqrt(S.N.below_fte[i] || 0) * 0.0025;
      S.fpTo[i * 2] = Math.min(cw * 0.62, want); S.fpTo[i * 2 + 1] = Math.min(ch * 0.62, want);
    });
  }
  // The organisation chart: leaves evenly across, parents centred over children, rows by
  // depth running away from the viewer, each building on its pay.
  function placeTree(roots, width, depthStep, backY) {
    let leaf = 0; const xs = new Map();
    function place(i, d) {
      const ks = S.kids[i]; let x;
      if (!ks.length) x = leaf++; else { ks.forEach(k => place(k, d + 1)); x = ks.reduce((s, k) => s + xs.get(k), 0) / ks.length; }
      xs.set(i, x); S.to[i * 3 + 1] = backY - d * depthStep; S.to[i * 3 + 2] = S.z[i];
    }
    roots.forEach(r => place(r, 0));
    const span = Math.max(1, leaf - 1), w = Math.min(width, Math.max(0.6, leaf * 0.09)), pitch = leaf > 1 ? w / span : w;
    xs.forEach((x, i) => { S.to[i * 3] = leaf > 1 ? (x / span - 0.5) * w : 0;
      const want = 0.03 + Math.sqrt(S.N.below_fte[i] || 0) * 0.004; const cap = Math.min(pitch * 0.75, depthStep * 0.45, 0.14);
      S.fpTo[i * 2] = Math.min(cap, want); S.fpTo[i * 2 + 1] = Math.min(cap, want); });
    return { leaves: leaf, width: w, rows: 1 + Math.max(...Array.from(xs.keys()).map(i => (backY - S.to[i * 3 + 1]) / depthStep)) };
  }
  function layout(f) {
    const G = S.G, B = G.bodies, D = G.departments;
    S.vis.fill(0); const floors = [], streets = [], segs = [];
    const addFloor = (r, di, a) => { floors.push({ r, c: hsl(S.hue[di], S.sat[di], 0.5), a }); };
    const addStreets = (r, di) => { const c = hsl(S.hue[di], S.sat[di], 0.6); const q = [[r.x, r.y, r.x + r.w, r.y], [r.x + r.w, r.y, r.x + r.w, r.y + r.h], [r.x + r.w, r.y + r.h, r.x, r.y + r.h], [r.x, r.y + r.h, r.x, r.y]]; for (const s of q) { streets.push({ s, c }); segs.push({ s, c }); } };
    if (f.kind === "gov") {
      const rects = treemap(S.order, di => Math.max(S.deptFte[di], 400), { x: -1.8, y: -1.3, w: 3.6, h: 2.6 });
      S.rects = {};
      S.order.forEach(di => {
        const r = rects.get(di); S.rects[di] = r; addFloor(r, di, 0.045); addStreets(r, di);
        const inner = { x: r.x + r.w * 0.06, y: r.y + r.h * 0.06, w: r.w * 0.88, h: r.h * 0.88 };
        const bs = treemap(D[di].bodies, bi => Math.max(B[bi].senior, 1), inner);
        D[di].bodies.forEach(bi => { const q = bs.get(bi); placeBlock(bi, { x: q.x + q.w * 0.1, y: q.y + q.h * 0.1, w: q.w * 0.8, h: q.h * 0.8 }); });
      });
      S.vis.fill(1); S.sizeScale = 0.7; S.phiWant = 0.66; S.thetaWant = null;
    } else if (f.kind === "dept") {
      const bs = D[f.d].bodies.slice().sort((a, b) => B[b].fte - B[a].fte);
      const rects = treemap(bs, bi => Math.max(B[bi].senior, 1) + Math.sqrt(B[bi].fte || 0) * 0.15, { x: -1.7, y: -1.2, w: 3.4, h: 2.4 });
      S.bodyRects = {}; bs.forEach(bi => { const r = rects.get(bi); S.bodyRects[bi] = r; addFloor(r, f.d, 0.05); addStreets(r, f.d); placeBlock(bi, { x: r.x + r.w * 0.1, y: r.y + r.h * 0.1, w: r.w * 0.8, h: r.h * 0.8 }); });
      for (let i = 0; i < S.n; i++) if (B[S.N.body[i]].dept === f.d) S.vis[i] = 1;
      S.sizeScale = 1.0; S.phiWant = 0.6; S.thetaWant = null;
    } else {
      const roots = f.kind === "body" ? S.roots[f.b] : [f.p];
      const t = placeTree(roots, 3.4, 0.5, 1.2);
      if (f.kind === "body") { for (let i = 0; i < S.n; i++) if (S.N.body[i] === f.b) S.vis[i] = 1; }
      else (function mark(i) { S.vis[i] = 1; S.kids[i].forEach(mark); })(f.p);
      const depthY = 1.2 - (t.rows - 1) * 0.5;
      addFloor({ x: -t.width / 2 - 0.25, y: depthY - 0.35, w: t.width + 0.5, h: 1.2 - depthY + 0.7 }, f.d, 0.03);
      // the reporting lines are the streets here: traffic runs down them
      const c = hsl(S.hue[f.d], S.sat[f.d], 0.7);
      for (let i = 0; i < S.n; i++) if (S.vis[i] && S.N.parent[i] >= 0 && S.vis[S.N.parent[i]]) { const p = S.N.parent[i]; segs.push({ s: [S.to[p * 3], S.to[p * 3 + 1], S.to[i * 3], S.to[i * 3 + 1]], z: [S.to[p * 3 + 2], S.to[i * 3 + 2]], c }); }
      S.sizeScale = 1.5; S.phiWant = 0.5; S.thetaWant = -Math.PI / 2;
    }
    for (let i = 0; i < S.n; i++) if (!S.vis[i]) { S.to[i * 3] = S.pos[i * 3]; S.to[i * 3 + 1] = S.pos[i * 3 + 1]; S.to[i * 3 + 2] = S.pos[i * 3 + 2]; S.fpTo[i * 2] = S.fp[i * 2]; S.fpTo[i * 2 + 1] = S.fp[i * 2 + 1]; }
    const fp = [], fc = [], fa = [];
    for (const { r, c, a } of floors) {
      const q = [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]];
      for (const [x, y] of q) { fp.push(x, y, 0); fc.push(c[0], c[1], c[2]); fa.push(a); }
    }
    upload(S.floor.pos, new Float32Array(fp)); upload(S.floor.col, new Float32Array(fc)); upload(S.floor.al, new Float32Array(fa)); S.floor.n = fa.length;
    const sp = [], sc = [], sa = [];
    for (const { s, c } of streets) { sp.push(s[0], s[1], 0.001, s[2], s[3], 0.001); sc.push(c[0], c[1], c[2], c[0], c[1], c[2]); sa.push(0.35, 0.35); }
    upload(S.streets.pos, new Float32Array(sp)); upload(S.streets.col, new Float32Array(sc)); upload(S.streets.al, new Float32Array(sa)); S.streets.n = sa.length;
    S.segs = segs; for (let k = 0; k < S.traffic.n; k++) S.traffic.seg[k] = segs.length ? Math.floor(Math.random() * segs.length) : -1;
  }
  function applyAlpha() {
    const open = S.focus.kind === "body" || S.focus.kind === "post";
    for (let i = 0; i < S.n; i++) S.al[i] = S.vis[i] ? 1 : 0;
    S.jn.forEach((i, k) => { S.hal[k] = S.vis[i] && open ? 0.1 : 0; });
    S.ln.forEach((i, k) => { const v = S.vis[i] && S.vis[S.N.parent[i]]; S.lal[k * 2] = v && open ? 0.25 : 0; S.lal[k * 2 + 1] = v && open ? 0.5 : 0; });
    upload(S.pts.al, S.al); upload(S.halo.al, S.hal); upload(S.lines.al, S.lal);
  }
  function uploadAll() {
    const p = S.pos, N = S.N;
    upload(S.pts.pos, p); upload(S.pts.fp, S.fp);
    S.jn.forEach((i, k) => { S.hpos[k * 3] = p[i * 3]; S.hpos[k * 3 + 1] = p[i * 3 + 1]; S.hpos[k * 3 + 2] = p[i * 3 + 2] * 0.5; }); upload(S.halo.pos, S.hpos);
    S.ln.forEach((i, k) => { const q = N.parent[i]; S.lpos[k * 6] = p[q * 3]; S.lpos[k * 6 + 1] = p[q * 3 + 1]; S.lpos[k * 6 + 2] = p[q * 3 + 2]; S.lpos[k * 6 + 3] = p[i * 3]; S.lpos[k * 6 + 4] = p[i * 3 + 1]; S.lpos[k * 6 + 5] = p[i * 3 + 2]; }); upload(S.lines.pos, S.lpos);
  }

  // --- focus ----------------------------------------------------------------------------------
  function setFocus(f, push) {
    S.focus = f; S.tour = null;
    for (let i = 0; i < S.n * 3; i++) S.from[i] = S.pos[i];
    for (let i = 0; i < S.n * 2; i++) S.fpFrom[i] = S.fp[i];
    layout(f);
    S.morph = REDUCED ? 1 : 0; S.morphT0 = performance.now();
    if (S.morph === 1) { for (let i = 0; i < S.n * 3; i++) S.pos[i] = S.to[i]; for (let i = 0; i < S.n * 2; i++) S.fp[i] = S.fpTo[i]; uploadAll(); }
    applyAlpha(); renderPanel(); frameFocus(false, 1400, 0); S.hover = -1; tip.hidden = true; $("detail").hidden = true;
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
  function bounds() {
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, zmax = 0;
    for (let i = 0; i < S.n; i++) if (S.vis[i]) { const x = S.to[i * 3], y = S.to[i * 3 + 1]; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); zmax = Math.max(zmax, S.to[i * 3 + 2]); }
    return x0 > x1 ? null : { x0, x1, y0, y1, zmax, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 };
  }
  function frameFocus(instant, dur, delay) {
    const b = bounds(); if (!b) return;
    const tree = S.focus.kind === "body" || S.focus.kind === "post";
    const r = tree ? Math.max((b.x1 - b.x0) * 0.55, (b.y1 - b.y0) * 0.9, 0.35) : Math.max(b.x1 - b.x0, (b.y1 - b.y0) * 1.2, 0.5) / 2;
    const dist = Math.max(0.8, r * (tree ? 2.1 : 2.4) + 0.45);
    S.camTo = { target: [b.cx, b.cy, Math.min(b.zmax * 0.4, tree ? 0.3 : 0.15)], dist, phi: S.phiWant, theta: S.thetaWant == null ? S.theta : S.thetaWant,
      from: { target: S.target.slice(), dist: S.dist, phi: S.phi, theta: S.theta }, t0: performance.now() + (delay || 0), dur: dur || 1400 };
    if (instant || REDUCED) { S.target = S.camTo.target.slice(); S.dist = dist; S.phi = S.camTo.phi; S.theta = S.camTo.theta; S.camTo = null; }
  }
  // Fly-through: a 14-second glide from above down into the streets and round, then back
  // up. At a body it runs from the head of the body forward along the rows.
  function startTour() {
    const b = bounds(); if (!b) return;
    S.tour = { t0: performance.now(), b, theta0: S.theta, tree: S.focus.kind === "body" || S.focus.kind === "post" }; S.camTo = null; tip.hidden = true;
  }
  function tourCamera(now) {
    const T = S.tour, u = Math.min(1, (now - T.t0) / 14000), b = T.b;
    const dip = Math.sin(u * Math.PI);                                   // 0 -> 1 -> 0
    if (T.tree) {
      const y = b.y1 - (b.y1 - b.y0 + 0.4) * u;                          // from the head, forward along the rows
      S.target = [b.cx + Math.sin(u * Math.PI * 2) * (b.x1 - b.x0) * 0.15, y, 0.12 + dip * 0.05];
      S.dist = 1.2 - dip * 0.55; S.phi = 0.42 - dip * 0.24; S.theta = -Math.PI / 2 + Math.sin(u * Math.PI * 2) * 0.35;
    } else {
      const ang = T.theta0 + u * Math.PI * 1.6;
      S.target = [b.cx + Math.cos(ang * 0.5) * (b.x1 - b.x0) * 0.22 * dip, b.cy + Math.sin(ang * 0.5) * (b.y1 - b.y0) * 0.22 * dip, 0.06 + dip * 0.06];
      S.dist = (S.focus.kind === "gov" ? 3.8 : 3.2) - dip * (S.focus.kind === "gov" ? 3.0 : 2.5); S.phi = 0.9 - dip * 0.72; S.theta = ang;
    }
    if (u >= 1) { S.tour = null; frameFocus(false, 1600, 0); }
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
        ? `<b>${esc(b.name)}</b><span>${fmt(b.fte)} FTE · ${b.senior} senior posts · snapshot ${esc(b.as_of)} · the head at the back, each level of reports a row nearer; click a building that has reports</span>`
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
    return mul(perspective(0.8, W / Hh, 0.01, 40), lookAt(eye, S.target, [0, 0, 1]));
  }
  const ease = t => 1 - Math.pow(1 - t, 3), easeIO = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  function traffic(now) {
    const T = S.traffic, segs = S.segs; if (!segs.length || !S.showTraffic) return 0;
    const tsec = now / 1000, open = S.focus.kind === "body" || S.focus.kind === "post";
    for (let k = 0; k < T.n; k++) {
      let si = T.seg[k]; if (si < 0 || si >= segs.length) { si = T.seg[k] = Math.floor(Math.random() * segs.length); }
      const g = segs[si], L = Math.hypot(g.s[2] - g.s[0], g.s[3] - g.s[1]) || 0.01;
      let u = (T.ph[k] + tsec * T.sp[k] / (L * 4)) % 1; if (k % 2) u = 1 - u;
      T.arr[k * 3] = g.s[0] + (g.s[2] - g.s[0]) * u; T.arr[k * 3 + 1] = g.s[1] + (g.s[3] - g.s[1]) * u;
      T.arr[k * 3 + 2] = g.z ? g.z[0] + (g.z[1] - g.z[0]) * u : 0.004;
      const warm = k % 3 === 0; T.carr[k * 3] = warm ? 1.0 : g.c[0] * 0.9 + 0.1; T.carr[k * 3 + 1] = warm ? 0.85 : g.c[1] * 0.9 + 0.1; T.carr[k * 3 + 2] = warm ? 0.6 : g.c[2] * 0.9 + 0.1;
    }
    upload(T.pos, T.arr); upload(T.col, T.carr);
    return open ? T.n : T.n;
  }
  function draw(now) {
    requestAnimationFrame(draw); if (!S.G) return;
    const dt = Math.min(0.05, (now - (S.last || now)) / 1000); S.last = now;
    if (S.grow < 1) S.grow = Math.min(1, (now - S.t0 - 600) / 2600);
    const rise = ease(Math.max(0, S.grow));
    if (S.morph < 1) { S.morph = Math.min(1, (now - S.morphT0) / 1100); const e = easeIO(S.morph);
      for (let i = 0; i < S.n * 3; i++) S.pos[i] = S.from[i] + (S.to[i] - S.from[i]) * e;
      for (let i = 0; i < S.n * 2; i++) S.fp[i] = S.fpFrom[i] + (S.fpTo[i] - S.fpFrom[i]) * e; uploadAll(); }
    if (S.tour) tourCamera(now);
    else if (S.camTo && now >= S.camTo.t0) { const c = S.camTo, e = easeIO(Math.min(1, (now - c.t0) / c.dur));
      for (let j = 0; j < 3; j++) S.target[j] = c.from.target[j] + (c.target[j] - c.from.target[j]) * e;
      S.dist = c.from.dist + (c.dist - c.from.dist) * e; S.phi = c.from.phi + (c.phi - c.from.phi) * e;
      let dth = c.theta - c.from.theta; dth = Math.atan2(Math.sin(dth), Math.cos(dth)); S.theta = c.from.theta + dth * e;
      if (e >= 1) S.camTo = null; }
    else if (S.orbit && !S.drag && (now - S.idleSince) > 7000) S.theta += dt * 0.06;
    const m = camera(), tsec = now / 1000;
    gl.clearColor(0.02, 0.022, 0.045, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.disable(gl.BLEND); disableAll();
    // the ground plane, opaque, so buildings hide what stands behind them
    gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, m); gl.uniform1f(uni(LN, "rise"), 1);
    attrib(LN, "p", S.plane.pos, 3); attrib(LN, "col", S.plane.col, 3); attrib(LN, "a", S.plane.al, 1); gl.drawArrays(gl.TRIANGLES, 0, 6);
    // the buildings
    if (EXT) {
      disableAll(); gl.useProgram(BOX); gl.uniformMatrix4fv(uni(BOX, "mvp"), false, m); gl.uniform1f(uni(BOX, "rise"), rise); gl.uniform1f(uni(BOX, "t"), tsec);
      gl.bindBuffer(gl.ARRAY_BUFFER, S.unit.geo);
      const lv = gl.getAttribLocation(BOX, "v"), ln = gl.getAttribLocation(BOX, "nrm"), lu = gl.getAttribLocation(BOX, "uv");
      for (const [l, size, off] of [[lv, 3, 0], [ln, 3, 12], [lu, 2, 24]]) { gl.enableVertexAttribArray(l); enabled.add(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, 32, off); EXT.vertexAttribDivisorANGLE(l, 0); }
      attrib(BOX, "ipos", S.pts.pos, 3, 1); attrib(BOX, "isz", S.pts.fp, 2, 1); attrib(BOX, "icol", S.pts.col, 3, 1); attrib(BOX, "ia", S.pts.al, 1, 1);
      EXT.drawArraysInstancedANGLE(gl.TRIANGLES, 0, S.unit.nv, S.n);
    }
    // everything luminous: additive, tested against the buildings but not written
    gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE); disableAll();
    gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, m); gl.uniform1f(uni(LN, "rise"), 1);
    if (S.floor.n) { attrib(LN, "p", S.floor.pos, 3); attrib(LN, "col", S.floor.col, 3); attrib(LN, "a", S.floor.al, 1); gl.drawArrays(gl.TRIANGLES, 0, S.floor.n); }
    attrib(LN, "p", S.grid.pos, 3); attrib(LN, "col", S.grid.col, 3); attrib(LN, "a", S.grid.al, 1); gl.drawArrays(gl.LINES, 0, S.grid.n);
    if (S.streets.n) { attrib(LN, "p", S.streets.pos, 3); attrib(LN, "col", S.streets.col, 3); attrib(LN, "a", S.streets.al, 1); gl.drawArrays(gl.LINES, 0, S.streets.n); }
    gl.uniform1f(uni(LN, "rise"), rise);
    attrib(LN, "p", S.lines.pos, 3); attrib(LN, "col", S.lines.col, 3); attrib(LN, "a", S.lines.al, 1); gl.drawArrays(gl.LINES, 0, S.ln.length * 2);
    if (EXT) {
      disableAll(); gl.useProgram(EDGE); gl.uniformMatrix4fv(uni(EDGE, "mvp"), false, m); gl.uniform1f(uni(EDGE, "rise"), rise);
      attrib(EDGE, "v", S.unit.edges, 3, 0); attrib(EDGE, "ipos", S.pts.pos, 3, 1); attrib(EDGE, "isz", S.pts.fp, 2, 1); attrib(EDGE, "icol", S.pts.col, 3, 1); attrib(EDGE, "ia", S.pts.al, 1, 1);
      EXT.drawArraysInstancedANGLE(gl.LINES, 0, S.unit.ne, S.n);
    }
    disableAll(); gl.useProgram(PT); gl.uniformMatrix4fv(uni(PT, "mvp"), false, m); gl.uniform1f(uni(PT, "pxr"), pxr); gl.uniform1f(uni(PT, "rise"), rise);
    if (S.focus.kind === "body" || S.focus.kind === "post") { gl.uniform1f(uni(PT, "scale"), S.sizeScale); attrib(PT, "p", S.halo.pos, 3); attrib(PT, "col", S.halo.col, 3); attrib(PT, "sz", S.halo.sz, 1); attrib(PT, "a", S.halo.al, 1); gl.drawArrays(gl.POINTS, 0, S.jn.length); }
    // roof lights: with buildings, small caps; without the extension, the buildings themselves
    gl.uniform1f(uni(PT, "scale"), EXT ? S.sizeScale * 0.45 : S.sizeScale);
    attrib(PT, "p", S.pts.pos, 3); attrib(PT, "col", S.pts.col, 3); attrib(PT, "sz", S.pts.sz, 1); attrib(PT, "a", S.pts.al, 1); gl.drawArrays(gl.POINTS, 0, S.n);
    const tn = traffic(now);
    if (tn) { gl.uniform1f(uni(PT, "scale"), 1); gl.uniform1f(uni(PT, "rise"), 1); attrib(PT, "p", S.traffic.pos, 3); attrib(PT, "col", S.traffic.col, 3); attrib(PT, "sz", S.traffic.sz, 1); attrib(PT, "a", S.traffic.al, 1); gl.drawArrays(gl.POINTS, 0, tn); }
    if (S.hover >= 0 && S.vis[S.hover]) {
      gl.disable(gl.DEPTH_TEST);
      upload(S.ring.pos, new Float32Array([S.pos[S.hover * 3], S.pos[S.hover * 3 + 1], S.pos[S.hover * 3 + 2]]));
      upload(S.ring.sz, new Float32Array([Math.max(S.sz[S.hover] * S.sizeScale, 0.4) + 0.3]));
      gl.useProgram(RING); gl.uniformMatrix4fv(uni(RING, "mvp"), false, m); gl.uniform1f(uni(RING, "pxr"), pxr); gl.uniform1f(uni(RING, "scale"), 1); gl.uniform1f(uni(RING, "rise"), rise);
      attrib(RING, "p", S.ring.pos, 3); attrib(RING, "col", S.ring.col, 3); attrib(RING, "sz", S.ring.sz, 1); attrib(RING, "a", S.ring.al, 1); gl.drawArrays(gl.POINTS, 0, 1);
    }
    gl.depthMask(true);
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
      labelWant.forEach(l => { const el = document.createElement("div"); el.className = "org3d-label" + (l.big ? " big" : "") + (l.i == null ? " ground" : ""); el.textContent = l.text; el.style.color = `hsl(${l.hue},80%,82%)`;
        el.addEventListener("click", () => { if (l.f) setFocus(l.f, true); else showDetail(l.i); }); el.addEventListener("pointerenter", () => { if (l.i != null) S.hover = l.i; }); labelsEl.appendChild(el); l.el = el; }); }
    const placed = [], hide = S.tour && !S.tour.tree;
    for (const l of labelWant) {
      let px, py;
      if (l.i != null) { px = S.screen[l.i * 2]; py = S.screen[l.i * 2 + 1] - 14; }
      else { const cw = m[3] * l.x + m[7] * l.y + m[11] * l.z + m[15]; if (cw <= 0.001) { l.el.style.opacity = 0; continue; }
        px = ((m[0] * l.x + m[4] * l.y + m[8] * l.z + m[12]) / cw * 0.5 + 0.5) * W; py = (0.5 - (m[1] * l.x + m[5] * l.y + m[9] * l.z + m[13]) / cw * 0.5) * Hh; }
      if (hide || px < -50 || py < -20 || px > W + 50 || py > Hh + 20 || placed.some(([qx, qy]) => Math.abs(qx - px) < 190 && Math.abs(qy - py) < 17)) { l.el.style.opacity = 0; continue; }
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
  const wake = () => { S.idleSince = performance.now(); S.tour = null; };
  canvas.addEventListener("pointerdown", e => { S.drag = { x: e.clientX, y: e.clientY, th: S.theta, ph: S.phi }; S.moved = 0; canvas.setPointerCapture(e.pointerId); wake(); });
  canvas.addEventListener("pointerup", e => {
    const wasClick = S.drag && S.moved < 5; S.drag = null; if (!wasClick) return;
    const r = canvas.getBoundingClientRect(), i = pick(e.clientX - r.left, e.clientY - r.top);
    if (i >= 0) drillTo(i); else up();
  });
  canvas.addEventListener("pointermove", e => {
    if (S.drag) { S.moved = Math.max(S.moved, Math.abs(e.clientX - S.drag.x) + Math.abs(e.clientY - S.drag.y));
      if (S.moved >= 5) { wake(); S.theta = S.drag.th - (e.clientX - S.drag.x) * 0.006; S.phi = Math.max(0.1, Math.min(1.5, S.drag.ph + (e.clientY - S.drag.y) * 0.005)); S.camTo = null; tip.hidden = true; } return; }
    if (!S.G) return;
    S.idleSince = performance.now();
    const r = canvas.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, i = pick(mx, my);
    S.hover = i; canvas.style.cursor = i >= 0 ? "pointer" : "grab";
    if (i < 0) { tip.hidden = true; return; }
    const N = S.N, b = S.B[N.body[i]];
    const next = S.focus.kind === "gov" ? "click: open this department" : S.focus.kind === "dept" ? "click: open this body" : S.kids[i].length ? "click: open the posts beneath" : "click: details";
    tip.innerHTML = `<b>${esc(N.title[i] || "(untitled post)")}</b><br>${esc(b.name)}<br>${esc(N.grade[i])} · ${N.pay[i] ? "from £" + N.pay[i].toLocaleString() : "pay not stated"}<br>${fmt(N.below_fte[i])} FTE beneath` + (N.below_senior[i] > 1 ? `, ${(N.below_senior[i] - 1).toLocaleString()} senior posts` : "") + `<br><i>${next}</i>`;
    tip.style.left = Math.min(mx + 14, W - 300) + "px"; tip.style.top = (my + 14) + "px"; tip.hidden = false;
  });
  canvas.addEventListener("pointerleave", () => { tip.hidden = true; S.hover = -1; });
  canvas.addEventListener("wheel", e => { e.preventDefault(); wake(); S.camTo = null; S.dist = Math.max(0.15, Math.min(12, S.dist * (1 + Math.sign(e.deltaY) * 0.08))); }, { passive: false });
  document.addEventListener("keydown", e => {
    if (e.target === search) return;
    if (e.key === "Escape") { if (S.tour) { S.tour = null; frameFocus(false, 1200, 0); return; } if (!$("detail").hidden) { $("detail").hidden = true; return; } up(); }
    else if (e.key === "ArrowLeft") S.theta -= 0.12; else if (e.key === "ArrowRight") S.theta += 0.12;
    else if (e.key === "ArrowUp") S.phi = Math.min(1.5, S.phi + 0.08); else if (e.key === "ArrowDown") S.phi = Math.max(0.1, S.phi - 0.08);
    else if (e.key === "+" || e.key === "=") S.dist *= 0.9; else if (e.key === "-") S.dist *= 1.1;
    else if (e.key === "/") { e.preventDefault(); search.focus(); return; } else if (e.key === "?") { $("help").hidden = !$("help").hidden; return; }
    else if (e.key === "f" || e.key === "F") { startTour(); return; } else return;
    wake(); S.camTo = null;
  });
  $("upbtn").addEventListener("click", up);
  $("closedetail").addEventListener("click", () => { $("detail").hidden = true; });
  $("helpbtn").addEventListener("click", () => { $("help").hidden = !$("help").hidden; });
  $("closehelp").addEventListener("click", () => { $("help").hidden = true; });
  const orbitBtn = $("orbit"); orbitBtn.textContent = `Orbit: ${S.orbit ? "on" : "off"}`;
  orbitBtn.addEventListener("click", () => { S.orbit = !S.orbit; orbitBtn.textContent = `Orbit: ${S.orbit ? "on" : "off"}`; orbitBtn.setAttribute("aria-pressed", S.orbit); S.idleSince = 0; });
  const trBtn = $("pillars"); trBtn.textContent = "Traffic: on";
  trBtn.addEventListener("click", () => { S.showTraffic = !S.showTraffic; trBtn.textContent = `Traffic: ${S.showTraffic ? "on" : "off"}`; trBtn.setAttribute("aria-pressed", S.showTraffic); });
  $("full").addEventListener("click", () => { if (document.fullscreenElement) document.exitFullscreen(); else if (stage.requestFullscreen) stage.requestFullscreen(); });
  document.addEventListener("fullscreenchange", () => setTimeout(resize, 50));
  $("reset").addEventListener("click", () => { setFocus({ kind: "gov", d: -1, b: -1, p: -1 }, true); S.theta = -1.1; S.phi = 1.45; S.dist = 7.5; S.t0 = performance.now(); S.grow = REDUCED ? 1 : 0; frameFocus(false, 4200, 900); S.idleSince = 0; });
  $("tour").addEventListener("click", startTour);

  // --- record the canvas to a WebM ---------------------------------------------------------------------
  const recBtn = $("rec"), dl = $("dl");
  recBtn.addEventListener("click", () => {
    if (!canvas.captureStream || !window.MediaRecorder) { recBtn.textContent = "Recording not supported here"; recBtn.disabled = true; return; }
    const stream = canvas.captureStream(30);
    const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find(m => MediaRecorder.isTypeSupported(m)) || "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 14e6 } : undefined);
    const chunks = []; rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => { const blob = new Blob(chunks, { type: "video/webm" }); dl.href = URL.createObjectURL(blob); dl.hidden = false; dl.textContent = `Save video (${(blob.size / 1e6).toFixed(1)} MB)`; recBtn.textContent = "Record fly-through"; recBtn.disabled = false; };
    tip.hidden = true; recBtn.textContent = "Recording…"; recBtn.disabled = true; dl.hidden = true;
    startTour(); rec.start(250); setTimeout(() => rec.stop(), 14500);
  });

  fetch("/api/family/organograms/graph.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(G => { build(G); requestAnimationFrame(draw); })
    .catch(err => { $("sub").textContent = "The graph could not be loaded (" + err.message + "). The chart as a list has every post."; });
})();
