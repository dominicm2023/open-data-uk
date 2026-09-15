/* The shape of the state — every senior post in UK central government as
   one three-dimensional figure, drawn in WebGL from
   /api/family/organograms/graph.json.

   Layout: the whole of government is a disc. Each department owns a sector
   of it, sized by the square root of its staff so small departments stay
   visible; each body a slice of its department's sector; each body's posts
   a radial tree — the head of the body nearest the centre, each reporting
   level one ring further out, siblings sharing their parent's angle in
   proportion to the posts beneath them. Height above the disc is the pay
   band's floor, so the skyline is the pay. A post's size is the staff
   beneath it, and the junior groups reporting to it glow around it.

   No library, no request to any other host (the CSP forbids both). Raw
   WebGL 1: point sprites with additive blending for posts, GL_LINES for
   reporting lines and pay pillars. Hover reads the nearest projected post.
   Record captures the canvas to a WebM in the browser.
*/
(function () {
  "use strict";
  const canvas = document.getElementById("c");
  const stage = document.getElementById("stage");
  const tip = document.getElementById("tip");
  const labelsEl = document.getElementById("labels");
  const sub = document.getElementById("sub");
  const nogl = document.getElementById("nogl");
  const gl = canvas.getContext("webgl", { antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: "high-performance" });
  if (!gl) { nogl.hidden = false; document.getElementById("panel").hidden = true; return; }

  // --- tiny matrix helpers (column-major, like GLSL) ---------------------------
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
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
    }
    return o;
  }

  // --- shaders -----------------------------------------------------------------
  const VS_PT = `
    attribute vec3 p; attribute vec3 col; attribute float sz; attribute float a;
    uniform mat4 mvp; uniform float grow; uniform float pxr; uniform float fade;
    varying vec3 vc; varying float va;
    void main() {
      vec3 q = vec3(p.x * grow, p.y * grow, p.z * grow);
      vec4 cp = mvp * vec4(q, 1.0);
      gl_Position = cp;
      float d = max(cp.w, 0.001);
      gl_PointSize = clamp(sz * pxr * 260.0 / d, 1.5 * pxr, 90.0 * pxr);
      vc = col; va = a * fade;
    }`;
  const FS_PT = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() {
      vec2 d = gl_PointCoord - 0.5; float r = dot(d, d) * 4.0;
      if (r > 1.0) discard;
      float core = exp(-r * 6.0); float halo = (1.0 - r) * 0.35;
      gl_FragColor = vec4(vc * (core + halo) * va, 1.0);
    }`;
  const VS_LN = `
    attribute vec3 p; attribute vec3 col; attribute float a;
    uniform mat4 mvp; uniform float grow; uniform float fade;
    varying vec3 vc; varying float va;
    void main() { gl_Position = mvp * vec4(p * grow, 1.0); vc = col; va = a * fade; }`;
  const FS_LN = `
    precision mediump float; varying vec3 vc; varying float va;
    void main() { gl_FragColor = vec4(vc * va, 1.0); }`;

  function program(vs, fs) {
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
    const pr = gl.createProgram(); gl.attachShader(pr, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    return pr;
  }
  const PT = program(VS_PT, FS_PT), LN = program(VS_LN, FS_LN);
  const loc = (pr, n) => gl.getAttribLocation(pr, n), uni = (pr, n) => gl.getUniformLocation(pr, n);
  function buffer(arr) { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW); return b; }
  function attrib(pr, name, buf, size) { const l = loc(pr, name); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, 0, 0); }

  // --- colour: a hue per department, brightness by grade ----------------------
  function hsl(h, s, l) {
    const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return [f(0), f(8), f(4)];
  }
  const GRADE_L = { scs4: 0.82, scs3: 0.72, scs2: 0.62, scs1a: 0.55, scs1: 0.5 };

  // --- state -------------------------------------------------------------------
  const S = {
    G: null, n: 0, pos: null, screen: null, pts: {}, lines: {}, pillars: {},
    theta: 0.9, phi: 0.95, dist: 3.1, target: [0, 0, 0.12], drag: null,
    orbit: !window.matchMedia("(prefers-reduced-motion: reduce)").matches, showPillars: true,
    t0: performance.now(), grow: 0, focus: -1, fade: 1, deptHub: [], deptLabel: [], hover: -1,
    fly: null,
  };

  function build(G) {
    S.G = G;
    const N = G.nodes, n = N.title.length; S.n = n;
    const D = G.departments, B = G.bodies;
    // sectors: departments by sqrt(FTE), bodies within by sqrt(senior posts)
    const deptFte = D.map(d => d.bodies.reduce((s, bi) => s + (B[bi].fte || 0), 0));
    const order = D.map((_, i) => i).sort((a, b) => deptFte[b] - deptFte[a]);
    const w = order.map(i => Math.sqrt(Math.max(deptFte[i], 30)) + 6);
    const wsum = w.reduce((a, b) => a + b, 0);
    const sector = new Array(D.length);
    let a0 = -Math.PI / 2;
    order.forEach((di, k) => { const span = 2 * Math.PI * w[k] / wsum; sector[di] = [a0 + span * 0.04, a0 + span * 0.96]; a0 += span; });
    const bodyArc = new Array(B.length);
    D.forEach((d, di) => {
      const [s0, s1] = sector[di];
      const bw = d.bodies.map(bi => Math.sqrt(Math.max(B[bi].senior, 1)) + 1.5);
      const bs = bw.reduce((a, b) => a + b, 0);
      let c = s0;
      d.bodies.forEach((bi, k) => { const span = (s1 - s0) * bw[k] / bs; bodyArc[bi] = [c + span * 0.08, c + span * 0.92]; c += span; });
    });
    // children lists and depth, parents precede children
    const kids = Array.from({ length: n }, () => []), depth = new Int16Array(n), roots = Array.from({ length: B.length }, () => []);
    for (let i = 0; i < n; i++) { const p = N.parent[i]; if (p >= 0) { kids[p].push(i); depth[i] = depth[p] + 1; } else roots[N.body[i]].push(i); }
    const weight = i => (N.below_senior[i] || 1) + 0.6;
    const ang = new Float32Array(n), rad = new Float32Array(n);
    const R0 = 0.34, DR = 0.115;
    function place(i, lo, hi) {
      ang[i] = (lo + hi) / 2; rad[i] = R0 + depth[i] * DR;
      const ks = kids[i]; if (!ks.length) return;
      const ws = ks.map(weight), wsum2 = ws.reduce((a, b) => a + b, 0);
      let c = lo; ks.forEach((k, j) => { const span = (hi - lo) * ws[j] / wsum2; place(k, c, c + span); c += span; });
    }
    B.forEach((b, bi) => {
      const [lo, hi] = bodyArc[bi]; const rs = roots[bi]; if (!rs.length) return;
      const ws = rs.map(weight), wsum2 = ws.reduce((a, b) => a + b, 0);
      let c = lo; rs.forEach((r, j) => { const span = (hi - lo) * ws[j] / wsum2; place(r, c, c + span); c += span; });
    });
    // pay -> height
    let maxPay = 0; for (let i = 0; i < n; i++) if (N.pay[i] && N.pay[i] > maxPay) maxPay = N.pay[i];
    maxPay = Math.max(maxPay, 200000);
    const H = 0.9;
    const pos = new Float32Array(n * 3), col = new Float32Array(n * 3), sz = new Float32Array(n), al = new Float32Array(n);
    const deptCol = D.map((_, di) => { const k = order.indexOf(di); return hsl((k * 137.508) % 360, 0.72, 0.6); });
    S.deptCol = deptCol;
    for (let i = 0; i < n; i++) {
      const bi = N.body[i], di = B[bi].dept;
      const x = Math.cos(ang[i]) * rad[i], y = Math.sin(ang[i]) * rad[i];
      const pay = N.pay[i]; const z = pay ? Math.max(0.02, (pay - 20000) / (maxPay - 20000)) * H : 0.02;
      pos[i * 3] = x; pos[i * 3 + 1] = y; pos[i * 3 + 2] = z;
      const g = (N.grade[i] || "").replace(/\s/g, "").toLowerCase();
      const c = hsl(((order.indexOf(di)) * 137.508) % 360, 0.75, GRADE_L[g] || 0.5);
      col[i * 3] = c[0]; col[i * 3 + 1] = c[1]; col[i * 3 + 2] = c[2];
      sz[i] = 0.22 + Math.sqrt(N.below_fte[i] || 0) * 0.075 + (depth[i] === 0 ? 0.25 : 0);
      al[i] = 1;
    }
    S.pos = pos; S.screen = new Float32Array(n * 2); S.depth = depth; S.kids = kids;
    S.pts = { pos: buffer(pos), col: buffer(col), sz: buffer(sz), al: buffer(al), alArr: al, n };
    // junior halos: one soft point per post with junior staff, bigger and dimmer
    const jn = []; for (let i = 0; i < n; i++) if (N.junior_fte[i] > 0) jn.push(i);
    const jp = new Float32Array(jn.length * 3), jc = new Float32Array(jn.length * 3), js = new Float32Array(jn.length), ja = new Float32Array(jn.length);
    jn.forEach((i, k) => { jp[k * 3] = pos[i * 3]; jp[k * 3 + 1] = pos[i * 3 + 1]; jp[k * 3 + 2] = pos[i * 3 + 2] * 0.5;
      const di = B[N.body[i]].dept, c = deptCol[di]; jc[k * 3] = c[0]; jc[k * 3 + 1] = c[1]; jc[k * 3 + 2] = c[2];
      js[k] = 0.35 + Math.sqrt(N.junior_fte[i]) * 0.09; ja[k] = 0.22; });
    S.halo = { pos: buffer(jp), col: buffer(jc), sz: buffer(js), al: buffer(ja), alArr: ja, idx: jn, n: jn.length };
    // reporting lines: parent -> child; pillars: disc -> post
    const lp = [], lc = [], la = [], pp = [], pc = [], pa = [];
    for (let i = 0; i < n; i++) {
      const di = B[N.body[i]].dept, c = deptCol[di]; const p = N.parent[i];
      if (p >= 0) { lp.push(pos[p * 3], pos[p * 3 + 1], pos[p * 3 + 2], pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]);
        lc.push(c[0], c[1], c[2], c[0], c[1], c[2]); la.push(0.22, 0.34); }
      pp.push(pos[i * 3], pos[i * 3 + 1], 0, pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]);
      pc.push(c[0], c[1], c[2], c[0], c[1], c[2]); pa.push(0.02, 0.16);
    }
    S.lines = { pos: buffer(new Float32Array(lp)), col: buffer(new Float32Array(lc)), al: buffer(new Float32Array(la)), alArr: new Float32Array(la), n: la.length };
    S.pillars = { pos: buffer(new Float32Array(pp)), col: buffer(new Float32Array(pc)), al: buffer(new Float32Array(pa)), alArr: new Float32Array(pa), n: pa.length };
    // department hubs for labels: the mid-angle of the sector at the inner ring
    S.deptHub = D.map((d, di) => { const [s0, s1] = sector[di]; const a = (s0 + s1) / 2; return [Math.cos(a) * 0.22, Math.sin(a) * 0.22, 0.0, deptFte[di]]; });
    S.order = order;
    // panel
    const totalFte = B.reduce((s, b) => s + (b.fte || 0), 0);
    sub.textContent = `${n.toLocaleString()} senior posts in ${B.length} bodies under ${D.length} departments, ${Math.round(totalFte).toLocaleString()} staff (FTE) beneath them.`;
    document.getElementById("asof").textContent = G.as_of ? `newest snapshot ${G.as_of}` : "";
    const sel = document.getElementById("dept");
    order.forEach(di => { const o = document.createElement("option"); o.value = di; o.textContent = `${D[di].name} (${Math.round(deptFte[di]).toLocaleString()} FTE)`; sel.appendChild(o); });
    labelsEl.innerHTML = "";
    S.deptLabel = order.slice(0, 28).map(di => { const el = document.createElement("div"); el.className = "org3d-label"; el.textContent = D[di].name; el.style.color = `rgb(${deptCol[di].map(v => Math.round(v * 255)).join(",")})`; el.dataset.di = di; labelsEl.appendChild(el); return [di, el]; });
  }

  // --- focus: dim every other department --------------------------------------
  function setFocus(di) {
    S.focus = di;
    const N = S.G.nodes, B = S.G.bodies;
    const dim = i => (di < 0 || B[N.body[i]].dept === di) ? 1 : 0.06;
    const al = S.pts.alArr; for (let i = 0; i < S.n; i++) al[i] = dim(i);
    gl.bindBuffer(gl.ARRAY_BUFFER, S.pts.al); gl.bufferData(gl.ARRAY_BUFFER, al, gl.STATIC_DRAW);
    const ha = S.halo.alArr; S.halo.idx.forEach((i, k) => { ha[k] = 0.22 * dim(i); });
    gl.bindBuffer(gl.ARRAY_BUFFER, S.halo.al); gl.bufferData(gl.ARRAY_BUFFER, ha, gl.STATIC_DRAW);
    const la = S.lines.alArr; let k = 0;
    for (let i = 0; i < S.n; i++) if (N.parent[i] >= 0) { const d = dim(i); la[k++] = 0.22 * d; la[k++] = 0.34 * d; }
    gl.bindBuffer(gl.ARRAY_BUFFER, S.lines.al); gl.bufferData(gl.ARRAY_BUFFER, la, gl.STATIC_DRAW);
    const pa = S.pillars.alArr; for (let i = 0; i < S.n; i++) { const d = dim(i); pa[i * 2] = 0.02 * d; pa[i * 2 + 1] = 0.16 * d; }
    gl.bindBuffer(gl.ARRAY_BUFFER, S.pillars.al); gl.bufferData(gl.ARRAY_BUFFER, pa, gl.STATIC_DRAW);
    if (di >= 0) { const h = S.deptHub[di]; S.fly = { to: [h[0] * 1.6, h[1] * 1.6, 0.16], dist: 1.6, t: 0 }; }
    else S.fly = { to: [0, 0, 0.12], dist: 3.1, t: 0 };
  }

  // --- camera and drawing ----------------------------------------------------------
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
    const view = lookAt(eye, S.target, [0, 0, 1]);
    const proj = perspective(0.9, W / Hh, 0.02, 40);
    return mul(proj, view);
  }

  function draw(now) {
    requestAnimationFrame(draw);
    if (!S.G) return;
    const dt = Math.min(0.05, (now - (S.last || now)) / 1000); S.last = now;
    const life = (now - S.t0) / 1000;
    S.grow = Math.min(1, life / 2.6); const g = 1 - Math.pow(1 - S.grow, 3);   // ease-out
    if (S.orbit && !S.drag) S.theta += dt * 0.11;
    if (S.fly) { S.fly.t = Math.min(1, S.fly.t + dt / 1.4); const e = 1 - Math.pow(1 - S.fly.t, 3);
      for (let k = 0; k < 3; k++) S.target[k] += (S.fly.to[k] - S.target[k]) * e * 0.18; S.dist += (S.fly.dist - S.dist) * e * 0.18;
      if (S.fly.t >= 1 && Math.abs(S.dist - S.fly.dist) < 0.002) S.fly = null; }
    const mvp = camera();
    gl.clearColor(0.035, 0.04, 0.07, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    // lines
    gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, mvp); gl.uniform1f(uni(LN, "grow"), g); gl.uniform1f(uni(LN, "fade"), 1);
    if (S.showPillars) { attrib(LN, "p", S.pillars.pos, 3); attrib(LN, "col", S.pillars.col, 3); attrib(LN, "a", S.pillars.al, 1); gl.drawArrays(gl.LINES, 0, S.pillars.n); }
    attrib(LN, "p", S.lines.pos, 3); attrib(LN, "col", S.lines.col, 3); attrib(LN, "a", S.lines.al, 1); gl.drawArrays(gl.LINES, 0, S.lines.n);
    // halos then posts
    gl.useProgram(PT); gl.uniformMatrix4fv(uni(PT, "mvp"), false, mvp); gl.uniform1f(uni(PT, "grow"), g); gl.uniform1f(uni(PT, "pxr"), pxr); gl.uniform1f(uni(PT, "fade"), 1);
    attrib(PT, "p", S.halo.pos, 3); attrib(PT, "col", S.halo.col, 3); attrib(PT, "sz", S.halo.sz, 1); attrib(PT, "a", S.halo.al, 1); gl.drawArrays(gl.POINTS, 0, S.halo.n);
    attrib(PT, "p", S.pts.pos, 3); attrib(PT, "col", S.pts.col, 3); attrib(PT, "sz", S.pts.sz, 1); attrib(PT, "a", S.pts.al, 1); gl.drawArrays(gl.POINTS, 0, S.pts.n);
    // project for labels and picking (every frame is cheap at 14k)
    project(mvp, g);
    labels(mvp, g);
  }

  function project(m, g) {
    const p = S.pos, s = S.screen;
    for (let i = 0; i < S.n; i++) {
      const x = p[i * 3] * g, y = p[i * 3 + 1] * g, z = p[i * 3 + 2] * g;
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
      if (cw <= 0.001) { s[i * 2] = -1e4; s[i * 2 + 1] = -1e4; continue; }
      const cx = (m[0] * x + m[4] * y + m[8] * z + m[12]) / cw, cy = (m[1] * x + m[5] * y + m[9] * z + m[13]) / cw;
      s[i * 2] = (cx * 0.5 + 0.5) * W; s[i * 2 + 1] = (0.5 - cy * 0.5) * Hh;
    }
  }
  function labels(m, g) {
    for (const [di, el] of S.deptLabel) {
      const h = S.deptHub[di]; const x = h[0] * g, y = h[1] * g, z = 0.0;
      const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
      if (cw <= 0.001 || (S.focus >= 0 && S.focus !== di)) { el.style.opacity = 0; continue; }
      const cx = (m[0] * x + m[4] * y + m[8] * z + m[12]) / cw, cy = (m[1] * x + m[5] * y + m[9] * z + m[13]) / cw;
      el.style.opacity = Math.min(1, Math.max(0, (S.grow - 0.5) * 2)) * 0.9;
      el.style.transform = `translate(${(cx * 0.5 + 0.5) * W}px, ${(0.5 - cy * 0.5) * Hh}px)`;
    }
  }

  // --- interaction ---------------------------------------------------------------
  canvas.addEventListener("pointerdown", e => { S.drag = { x: e.clientX, y: e.clientY, th: S.theta, ph: S.phi }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointerup", e => { S.drag = null; });
  canvas.addEventListener("pointermove", e => {
    if (S.drag) { S.theta = S.drag.th - (e.clientX - S.drag.x) * 0.006; S.phi = Math.max(0.08, Math.min(1.45, S.drag.ph + (e.clientY - S.drag.y) * 0.005)); tip.hidden = true; return; }
    if (!S.G) return;
    const r = canvas.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    let best = -1, bd = 12 * 12; const s = S.screen, N = S.G.nodes, B = S.G.bodies;
    for (let i = 0; i < S.n; i++) { if (S.focus >= 0 && B[N.body[i]].dept !== S.focus) continue;
      const dx = s[i * 2] - mx, dy = s[i * 2 + 1] - my, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } }
    if (best < 0) { tip.hidden = true; return; }
    const i = best, b = B[N.body[i]];
    const pay = N.pay[i] ? `from £${N.pay[i].toLocaleString()}` : "pay not stated";
    tip.innerHTML = `<b>${esc(N.title[i] || "(untitled post)")}</b><br>${esc(b.name)}<br>` +
      `${esc(N.grade[i] || "")} · ${pay}<br>` +
      `${Math.round(N.below_fte[i]).toLocaleString()} FTE beneath` + (N.below_senior[i] > 1 ? `, ${(N.below_senior[i] - 1).toLocaleString()} senior posts` : "") +
      (N.junior_fte[i] ? `<br>${Math.round(N.junior_fte[i]).toLocaleString()} FTE in junior groups reporting here` : "");
    tip.style.left = Math.min(mx + 14, W - 300) + "px"; tip.style.top = (my + 14) + "px"; tip.hidden = false;
  });
  canvas.addEventListener("pointerleave", () => { tip.hidden = true; });
  canvas.addEventListener("wheel", e => { e.preventDefault(); S.dist = Math.max(0.4, Math.min(8, S.dist * (1 + Math.sign(e.deltaY) * 0.08))); }, { passive: false });
  labelsEl.addEventListener("click", e => { const el = e.target.closest(".org3d-label"); if (!el) return; document.getElementById("dept").value = el.dataset.di; setFocus(+el.dataset.di); });
  function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  const orbitBtn = document.getElementById("orbit");
  orbitBtn.addEventListener("click", () => { S.orbit = !S.orbit; orbitBtn.textContent = `Orbit: ${S.orbit ? "on" : "off"}`; orbitBtn.setAttribute("aria-pressed", S.orbit); });
  orbitBtn.textContent = `Orbit: ${S.orbit ? "on" : "off"}`;
  const pillBtn = document.getElementById("pillars");
  pillBtn.addEventListener("click", () => { S.showPillars = !S.showPillars; pillBtn.textContent = `Pillars: ${S.showPillars ? "on" : "off"}`; pillBtn.setAttribute("aria-pressed", S.showPillars); });
  document.getElementById("full").addEventListener("click", () => { if (document.fullscreenElement) document.exitFullscreen(); else stage.requestFullscreen && stage.requestFullscreen(); });
  document.addEventListener("fullscreenchange", () => setTimeout(resize, 50));
  document.getElementById("dept").addEventListener("change", e => setFocus(e.target.value === "" ? -1 : +e.target.value));
  document.getElementById("reset").addEventListener("click", () => { document.getElementById("dept").value = ""; setFocus(-1); S.theta = 0.9; S.phi = 0.95; S.t0 = performance.now(); });

  // --- record: the canvas to a WebM, in the browser ------------------------------
  const recBtn = document.getElementById("rec"), dl = document.getElementById("dl");
  recBtn.addEventListener("click", () => {
    if (!canvas.captureStream || !window.MediaRecorder) { recBtn.textContent = "Recording not supported here"; recBtn.disabled = true; return; }
    const stream = canvas.captureStream(30);
    const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find(m => MediaRecorder.isTypeSupported(m)) || "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 12e6 } : undefined);
    const chunks = []; rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => { const blob = new Blob(chunks, { type: "video/webm" }); dl.href = URL.createObjectURL(blob); dl.hidden = false; dl.textContent = `Save video (${(blob.size / 1e6).toFixed(1)} MB)`; recBtn.textContent = "Record 12 s"; recBtn.disabled = false; };
    const wasOrbit = S.orbit; S.orbit = true; S.t0 = performance.now(); tip.hidden = true;
    recBtn.textContent = "Recording…"; recBtn.disabled = true; dl.hidden = true;
    rec.start(250); setTimeout(() => { rec.stop(); S.orbit = wasOrbit; }, 12000);
  });

  // --- go --------------------------------------------------------------------------
  fetch("/api/family/organograms/graph.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(G => { build(G); requestAnimationFrame(draw); })
    .catch(err => { sub.textContent = "The graph could not be loaded (" + err.message + "). The chart as a list has every post."; });
})();
