/* The shape of the state — every senior post in UK central government as
   a city at night, drawn in WebGL from /api/family/organograms/graph.json.

   Every post is a building. Its footprint is the staff beneath it, its
   height the pay band, its lit windows flicker, and a neon rim marks the
   roof. The ground is an archipelago: every department an island, its
   area the staff it employs, every body a block on it with streets between
   and traffic running. Islands of a kind lie together in the sea: the same
   ministry under its earlier names, the departments of one field, with
   ferry lanes between them. You arrive from the sky. Open a department
   and its island grows to fill the sea; open a
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
  const FOG = "clamp(1.35 - max(cp.w, 0.0) * 0.11, 0.18, 1.0)";
  const VS_BOX = `
    attribute vec3 v; attribute vec3 nrm; attribute vec2 uv;
    attribute vec3 ipos; attribute vec2 isz; attribute vec3 icol; attribute float ia; attribute float istyle;
    uniform mat4 mvp; uniform float rise; uniform float tier;
    varying vec3 vc; varying float va; varying vec2 vuv; varying float vshade; varying float vh; varying float vtop; varying float vstyle; varying float vtone;
    void main() {
      float annex = step(3.5, istyle);
      vtone = fract(sin(dot(ipos.xy, vec2(12.9898, 78.233))) * 43758.5453);
      float fw = tier > 1.5 ? 0.32 : mix(1.0, 0.58, tier), fh = tier > 1.5 ? 1.16 : mix(1.0, 1.07, tier);
      float h = ipos.z * rise;
      vec3 w = vec3(ipos.x + v.x * isz.x * fw, ipos.y + v.y * isz.y * fw, v.z * h * fh);
      vec4 cp = mvp * vec4(w, 1.0); gl_Position = cp;
      vtop = step(0.5, nrm.z);
      vshade = mix(0.5 + 0.35 * max(0.0, dot(nrm.xy, normalize(vec2(-0.55, -0.83)))), 1.0, vtop);
      vuv = vec2(uv.x * max(isz.x, isz.y) * 160.0, uv.y * h * 70.0);
      float big = max(isz.x, isz.y);
      float skip = min(1.0, tier * (step(big, 0.012) + annex) + step(1.5, tier) * step(big, 0.03));   // crowns only on buildings of size, never on annexes
      vc = icol; va = ia * ${FOG} * (1.0 - skip); vh = v.z; vstyle = istyle;
    }`;
  const FS_BOX = `
    precision mediump float; uniform float t;
    varying vec3 vc; varying float va; varying vec2 vuv; varying float vshade; varying float vh; varying float vtop; varying float vstyle; varying float vtone;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    void main() {
      if (va <= 0.002) discard;
      if (vstyle > 3.5) {                                             // an annex: the posts with no pay band, grouped
        float stripe = step(0.5, fract(vuv.y * 0.3));
        vec3 g = vec3(0.3, 0.32, 0.4) * (0.3 + 0.25 * vshade) + vc * 0.06 * stripe * (1.0 - vtop);
        gl_FragColor = vec4(g * va, 1.0); return;
      }
      vec2 g = vuv;                                                   // each district builds its own way
      if (vstyle < 0.5) { } else if (vstyle < 1.5) { g.x *= 0.55; } else if (vstyle < 2.5) { g.y *= 0.45; } else { g *= 0.7; }
      vec2 cell = floor(g); vec2 f = fract(g);
      float busy = vstyle < 0.5 ? 0.42 : vstyle < 1.5 ? 0.35 : vstyle < 2.5 ? 0.6 : 0.28;
      float lit = step(1.0 - busy, hash(cell + floor(t * 0.1 + hash(cell * 1.7) * 9.0)));
      float win = (vstyle < 2.5 ? step(0.2, f.x) * step(f.x, 0.8) * step(0.2, f.y) * step(f.y, 0.75) : step(0.12, f.y) * step(f.y, 0.82)) * (1.0 - vtop);
      vec3 c = vc * 0.14 * vshade;
      vec3 warm = mix(vc, vec3(1.0, 0.86, 0.6), vstyle > 2.5 ? 0.6 : 0.15);
      c += warm * win * lit * 0.75 * (0.5 + 0.5 * vshade);
      c += vc * smoothstep(0.9, 1.0, vh) * (1.0 - vtop) * 0.7;
      c += vc * vtop * 0.45;
      c += vc * 0.06 * step(0.93, f.y) * (1.0 - vtop);                  // a faint line at each floor
      c *= 0.55 + 0.45 * smoothstep(0.0, 0.12, vh);
      c *= 0.86 + 0.28 * vtone;                                           // no two buildings quite the same tone
      gl_FragColor = vec4(c * va, 1.0);
    }`;
  const VS_EDGE = `
    attribute vec3 v; attribute vec3 ipos; attribute vec2 isz; attribute vec3 icol; attribute float ia; attribute float istyle;
    uniform mat4 mvp; uniform float rise; varying vec3 vc; varying float va;
    void main() { vec4 cp = mvp * vec4(ipos.x + v.x * isz.x, ipos.y + v.y * isz.y, v.z * ipos.z * rise, 1.0); gl_Position = cp;
      vc = mix(icol, vec3(0.42, 0.44, 0.52), step(3.5, istyle)); va = ia * ${FOG}; }`;
  // signs: the names as objects in the scene, each a camera-facing quad of a text atlas
  const VS_SIGN = `
    attribute vec3 c; attribute vec2 o; attribute vec2 uv; attribute vec2 sz; attribute vec3 tint;
    uniform mat4 mvp; uniform vec3 right; uniform vec3 upv; uniform float rise;
    varying vec2 vuv; varying vec3 vt; varying float va;
    void main() {
      vec3 w = vec3(c.x, c.y, c.z * rise) + right * (o.x * sz.x) + upv * (o.y * sz.y);
      vec4 cp = mvp * vec4(w, 1.0); gl_Position = cp; vuv = uv; vt = tint; va = ${FOG};
    }`;
  const FS_SIGN = `
    precision mediump float; uniform sampler2D tex; varying vec2 vuv; varying vec3 vt; varying float va;
    void main() { vec4 s = texture2D(tex, vuv); gl_FragColor = vec4(vt * s.rgb * s.a * va * 1.5, 1.0); }`;
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
  // the sea and the islands: one heightfield, lit per vertex on land, the water alive
  // per pixel — a swell, a shimmer in the shallows, and a tide line along every shore
  const VS_TER = `
    attribute vec3 p; attribute vec3 col; attribute float d;
    uniform mat4 mvp; varying vec3 vc; varying float vd; varying vec2 vw; varying float va;
    void main() { vec4 cp = mvp * vec4(p, 1.0); gl_Position = cp; vc = col; vd = d; vw = p.xy; va = ${FOG}; }`;
  const FS_TER = `
    precision mediump float; uniform float t; varying vec3 vc; varying float vd; varying vec2 vw; varying float va;
    void main() {
      vec3 c = vc;
      if (vd > 0.0) {
        float swell = sin(vw.x * 9.0 + t * 0.5 + sin(vw.y * 6.0 - t * 0.3) * 1.7) * sin(vw.y * 7.5 - t * 0.4);
        float rip = sin(vw.x * 38.0 + t * 0.9 + swell * 2.0) * sin(vw.y * 31.0 - t * 0.7);
        c += vec3(0.03, 0.06, 0.10) * (0.5 + 0.5 * swell);                          // the open sea moves
        c += vec3(0.05, 0.16, 0.20) * (0.5 + 0.5 * rip) * exp(-vd * 45.0) * 0.6;     // the shallows shimmer
        c += vec3(0.35, 0.9, 1.0) * exp(-vd * 300.0) * (0.5 + 0.5 * sin(t * 1.3 + vw.x * 9.0 + vw.y * 7.0)) * 0.7;   // the tide line
      }
      gl_FragColor = vec4(c * va, 1.0);
    }`;
  // full-screen passes: the sky behind everything, then bloom over it all
  const VS_QUAD = `attribute vec2 q; varying vec2 uv; void main() { uv = q * 0.5 + 0.5; gl_Position = vec4(q, 0.0, 1.0); }`;
  const FS_SKY = `
    precision mediump float; varying vec2 uv; uniform float theta; uniform float phi; uniform float t; uniform float aspect;
    float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
    void main() {
      float h = uv.y;                                                     // 0 at the bottom of the screen
      vec3 top = vec3(0.012, 0.014, 0.04), mid = vec3(0.05, 0.03, 0.10), glow = vec3(0.16, 0.06, 0.14);
      vec3 c = mix(mid, top, smoothstep(0.35, 1.0, h));
      c += glow * exp(-abs(h - 0.42) * 9.0) * 0.6;                        // a city's horizon glow
      c += vec3(0.02, 0.08, 0.10) * exp(-abs(h - 0.4) * 14.0);
      vec2 sp = vec2((uv.x + theta * 0.16) * aspect * 90.0, (uv.y + phi * 0.25) * 90.0);
      vec2 cell = floor(sp); float r = hash(cell);
      float star = step(0.985, r) * smoothstep(0.45, 0.0, length(fract(sp) - 0.5)) * (0.6 + 0.4 * sin(t * (1.5 + r * 3.0) + r * 20.0));
      c += vec3(0.8, 0.85, 1.0) * star * smoothstep(0.38, 0.7, h) * 0.9;
      gl_FragColor = vec4(c, 1.0);
    }`;
  const FS_BRIGHT = `precision mediump float; varying vec2 uv; uniform sampler2D tex;
    void main() { vec3 c = texture2D(tex, uv).rgb; gl_FragColor = vec4(max(c - 0.32, 0.0) * 1.7, 1.0); }`;
  const FS_BLUR = `precision mediump float; varying vec2 uv; uniform sampler2D tex; uniform vec2 dir;
    void main() { vec3 c = texture2D(tex, uv).rgb * 0.227;
      c += (texture2D(tex, uv + dir * 1.385).rgb + texture2D(tex, uv - dir * 1.385).rgb) * 0.316;
      c += (texture2D(tex, uv + dir * 3.231).rgb + texture2D(tex, uv - dir * 3.231).rgb) * 0.07;
      gl_FragColor = vec4(c, 1.0); }`;
  const FS_COMPOSE = `precision mediump float; varying vec2 uv; uniform sampler2D tex; uniform sampler2D bloom; uniform float strength;
    void main() {
      vec3 c = texture2D(tex, uv).rgb + texture2D(bloom, uv).rgb * strength;
      c = vec3(1.0) - exp(-c * 1.25);                                     // soft shoulder on the brightest neon
      vec2 d = uv - 0.5; c *= 1.0 - 0.32 * dot(d, d) * 1.6;               // vignette
      gl_FragColor = vec4(c, 1.0);
    }`;
  function program(vs, fs) {
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
    const pr = gl.createProgram(); gl.attachShader(pr, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
    return pr;
  }
  const PT = program(VS_PT, FS_PT), RING = program(VS_PT, FS_RING), LN = program(VS_LN, FS_LN), TER = program(VS_TER, FS_TER);
  const BOX = EXT ? program(VS_BOX, FS_BOX) : null, EDGE = EXT ? program(VS_EDGE, FS_FLAT) : null, SIGN = program(VS_SIGN, FS_SIGN);
  const SKY = program(VS_QUAD, FS_SKY), BRIGHT = program(VS_QUAD, FS_BRIGHT), BLUR = program(VS_QUAD, FS_BLUR), COMPOSE = program(VS_QUAD, FS_COMPOSE);
  const QUAD = (() => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]), gl.STATIC_DRAW); return b; })();
  // render targets: the scene at full size with depth, and two quarter-size buffers for the bloom
  const RT = { scene: null, a: null, b: null, w: 0, h: 0 };
  function target(w, h, depth) {
    const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const fb = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    if (depth) { const rb = gl.createRenderbuffer(); gl.bindRenderbuffer(gl.RENDERBUFFER, rb); gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16, w, h); gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, rb); }
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return ok ? { fb, tex, w, h } : null;
  }
  function makeTargets(w, h) {
    if (RT.w === w && RT.h === h) return;
    RT.w = w; RT.h = h; RT.scene = target(w, h, true);
    const bw = Math.max(1, w >> 2), bh = Math.max(1, h >> 2); RT.a = target(bw, bh, false); RT.b = target(bw, bh, false);
    RT.ok = !!(RT.scene && RT.a && RT.b);
  }
  function fullscreen(pr) { disableAll(); gl.useProgram(pr); attrib(pr, "q", QUAD, 2); gl.drawArrays(gl.TRIANGLES, 0, 6); }
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
    const rebuilding = !!S.G, prev = rebuilding ? identityMap() : null, focusNames = rebuilding ? namesOf(S.focus) : null;
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
    // each district builds its own way: four architectures, by department rank
    S.deptStyle = new Array(G.departments.length); S.order.forEach((di, k) => { S.deptStyle[di] = k % 4; });
    S.nopay = new Uint8Array(n); for (let i = 0; i < n; i++) S.nopay[i] = N.pay[i] ? 0 : 1;
    S.styleArr = new Float32Array(n); S.hidden = new Uint8Array(n); S.annex = new Int32Array(n);
    // a spire on the head of every body
    S.spireList = []; for (let bi = 0; bi < G.bodies.length; bi++) for (const r of S.roots[bi]) S.spireList.push(r);
    const spc = new Float32Array(S.spireList.length * 6); S.spireList.forEach((i, k) => { for (let e = 0; e < 2; e++) { spc[k * 6 + e * 3] = col[i * 3]; spc[k * 6 + e * 3 + 1] = col[i * 3 + 1]; spc[k * 6 + e * 3 + 2] = col[i * 3 + 2]; } });
    S.spos = new Float32Array(S.spireList.length * 6); S.sal = new Float32Array(S.spireList.length * 2);
    S.spires = { pos: buffer(S.spos, true), col: buffer(spc), al: buffer(S.sal, true) };
    S.signs = { tex: gl.createTexture(), c: buffer(new Float32Array(0), true), o: buffer(new Float32Array(0), true), uv: buffer(new Float32Array(0), true), sz: buffer(new Float32Array(0), true), tint: buffer(new Float32Array(0), true), n: 0 };
    S.pos = new Float32Array(n * 3); S.from = new Float32Array(n * 3); S.to = new Float32Array(n * 3);
    S.fp = new Float32Array(n * 2); S.fpFrom = new Float32Array(n * 2); S.fpTo = new Float32Array(n * 2);   // footprints
    S.al = new Float32Array(n); S.screen = new Float32Array(n * 2); S.vis = new Uint8Array(n);
    S.pts = { pos: buffer(S.pos, true), col: buffer(col), sz: buffer(sz), al: buffer(S.al, true), fp: buffer(S.fp, true), style: buffer(S.styleArr, true) };
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
    // the ground: the open sea to the horizon (opaque), the islands as a heightfield
    // over it, then block floors, street lines and traffic
    const deep = DEEP, pc = []; for (let e = 0; e < 6; e++) pc.push(deep[0], deep[1], deep[2]);
    S.plane = { pos: buffer(new Float32Array([-40, -40, -0.0205, 40, -40, -0.0205, 40, 40, -0.0205, -40, -40, -0.0205, 40, 40, -0.0205, -40, 40, -0.0205])), col: buffer(new Float32Array(pc)), d: buffer(new Float32Array(6).fill(0.03)) };
    if (!S.terrain) S.terrain = makeTerrainBuffers();
    S.floor = { pos: buffer(new Float32Array(0), true), col: buffer(new Float32Array(0), true), al: buffer(new Float32Array(0), true), n: 0 };
    S.streets = { pos: buffer(new Float32Array(0), true), col: buffer(new Float32Array(0), true), al: buffer(new Float32Array(0), true), n: 0 };
    const TN = 700; S.traffic = { n: TN, seg: new Int32Array(TN), ph: new Float32Array(TN), sp: new Float32Array(TN), pos: buffer(new Float32Array(TN * 3), true), col: buffer(new Float32Array(TN * 3), true), sz: buffer(new Float32Array(TN).fill(0.16)), al: buffer(new Float32Array(TN).fill(0.9)), arr: new Float32Array(TN * 3), carr: new Float32Array(TN * 3) };
    for (let k = 0; k < TN; k++) { S.traffic.ph[k] = Math.random(); S.traffic.sp[k] = 0.05 + Math.random() * 0.12; }
    $("sub").textContent = G.at
      ? `${n.toLocaleString()} senior posts in ${G.bodies.length} bodies under ${G.departments.length} departments, as they stood on ${niceDate(G.at)}. Junior staff are held for the newest snapshot only, so sizes here follow senior posts beneath.`
      : `${n.toLocaleString()} senior posts in ${G.bodies.length} bodies under ${G.departments.length} departments, ${fmt(S.deptFte.reduce((a, b) => a + b, 0))} staff (FTE) beneath them.`;
    $("asof").textContent = G.as_of ? `newest snapshot ${G.as_of}` : "";
    if (rebuilding) {
      // the same date's posts keep their place; a post new at this date rises from the ground
      S.focus = resolveFocus(focusNames);
      layout(S.focus);
      for (let i = 0; i < n; i++) {
        const was = prev.get(identity(i));
        if (was) { S.from[i * 3] = was[0]; S.from[i * 3 + 1] = was[1]; S.from[i * 3 + 2] = was[2]; S.fpFrom[i * 2] = was[3]; S.fpFrom[i * 2 + 1] = was[4]; }
        else { S.from[i * 3] = S.to[i * 3]; S.from[i * 3 + 1] = S.to[i * 3 + 1]; S.from[i * 3 + 2] = 0; S.fpFrom[i * 2] = S.fpTo[i * 2]; S.fpFrom[i * 2 + 1] = S.fpTo[i * 2 + 1]; }
        S.pos[i * 3] = S.from[i * 3]; S.pos[i * 3 + 1] = S.from[i * 3 + 1]; S.pos[i * 3 + 2] = S.from[i * 3 + 2]; S.fp[i * 2] = S.fpFrom[i * 2]; S.fp[i * 2 + 1] = S.fpFrom[i * 2 + 1];
      }
      S.morph = REDUCED ? 1 : 0; S.morphT0 = performance.now(); applyAlpha(); uploadAll(); renderPanel(); frameFocus(false, 1400, 0);
      return;
    }
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

  // --- identity across dates ---------------------------------------------------------------
  const identity = i => S.B[S.N.body[i]].name + "|" + (S.N.ref ? S.N.ref[i] : "") + "|" + (S.N.ref && S.N.ref[i] ? "" : S.N.title[i]);
  function identityMap() { const m = new Map(); for (let i = 0; i < S.n; i++) m.set(identity(i), [S.pos[i * 3], S.pos[i * 3 + 1], S.pos[i * 3 + 2], S.fp[i * 2], S.fp[i * 2 + 1]]); return m; }
  function namesOf(f) { return { kind: f.kind, d: f.d >= 0 ? S.D[f.d].name : null, b: f.b >= 0 ? S.B[f.b].name : null, p: f.p >= 0 ? identity(f.p) : null }; }
  function resolveFocus(nm) {
    const gov = { kind: "gov", d: -1, b: -1, p: -1 }; if (!nm || nm.kind === "gov") return gov;
    const d = S.D.findIndex(x => x.name === nm.d); if (d < 0) return gov;
    if (nm.kind === "dept") return { kind: "dept", d, b: -1, p: -1 };
    const b = S.B.findIndex(x => x.name === nm.b); if (b < 0) return { kind: "dept", d, b: -1, p: -1 };
    if (nm.kind === "body") return { kind: "body", d, b, p: -1 };
    for (let i = 0; i < S.n; i++) if (S.N.body[i] === b && identity(i) === nm.p && S.kids[i].length) return { kind: "post", d, b, p: i };
    return { kind: "body", d, b, p: -1 };
  }
  // the scrubber: every government-wide snapshot date the family holds
  const TL = { dates: [], at: null, playing: false, timer: null, loading: false, want: null };
  function showDate(k, andLoad) {
    const d = TL.dates[k]; if (!d) return;
    const last = k === TL.dates.length - 1;
    $("whenlabel").textContent = last ? "Newest snapshot of every body" : `As it stood on ${niceDate(d.date)}`;
    $("when").value = k;
    if (andLoad) loadDate(d.date);
  }
  const niceDate = iso => { const dt = new Date(iso + "T00:00:00Z"); return dt.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }); };
  function loadDate(date) {
    const last = TL.dates[TL.dates.length - 1]; const at = (last && date === last.date) ? null : date;
    if (TL.loading) { TL.want = at; return; }
    TL.loading = true; TL.at = at;
    fetch("/api/family/organograms/graph.json" + (at ? "?at=" + at : "")).then(r => r.json()).then(G => { build(G); })
      .catch(() => {}).finally(() => { TL.loading = false; if (TL.want !== undefined && TL.want !== null && TL.want !== TL.at) { const w = TL.want; TL.want = null; loadDate(w); } else TL.want = null; });
  }
  function setupTimeline(t) {
    // bodies report on their own days, so the ticks are the half-years (31 March, 30 September)
    // from the first snapshot to the last; the city at a tick is every body's newest snapshot on or before it
    const have = (t.dates || []).filter(d => d.bodies >= 3); if (have.length < 2) return;
    const y0 = +have[0].date.slice(0, 4), last = have[have.length - 1].date, y1 = +last.slice(0, 4);
    TL.dates = [];
    for (let y = y0; y <= y1; y++) for (const md of ["-03-31", "-09-30"]) { const d = y + md; if (d >= have[0].date && d <= last) TL.dates.push({ date: d }); }
    if (!TL.dates.length || TL.dates[TL.dates.length - 1].date !== last) TL.dates.push({ date: last });
    if (TL.dates.length < 2) return;
    const wrap = $("when-wrap"), rng = $("when"); wrap.hidden = false; rng.min = 0; rng.max = TL.dates.length - 1; rng.value = TL.dates.length - 1;
    showDate(TL.dates.length - 1, false);
    rng.addEventListener("input", () => showDate(+rng.value, true));
    $("play").addEventListener("click", () => {
      TL.playing = !TL.playing; $("play").textContent = TL.playing ? "❚❚" : "▶";
      if (TL.playing) { if (+rng.value >= TL.dates.length - 1) rng.value = 0; TL.timer = setInterval(() => { const k = +rng.value + 1; if (k >= TL.dates.length) { clearInterval(TL.timer); TL.playing = false; $("play").textContent = "▶"; return; } showDate(k, true); }, 1500); }
      else clearInterval(TL.timer);
    });
    document.addEventListener("keydown", e => { if (e.target === search) return; if (e.key === "[" || e.key === "]") { const k = Math.max(0, Math.min(TL.dates.length - 1, +rng.value + (e.key === "]" ? 1 : -1))); showDate(k, true); } });
  }

  // --- islands ---------------------------------------------------------------------------
  // Islands of a kind lie together: the same ministry under its earlier names, the
  // departments of one field. The grouping is editorial, not a fact from the data,
  // which says only which body sits under which department; the names are matched
  // here, in order, and a department no pattern names sits in "Elsewhere".
  const SECTORS = [
    ["The centre", /cabinet office|treasury$|equalities|actuary|statistics|prime minister/i],
    ["Money and business", /revenue|business|export finance|competition|science, innovation/i],
    ["Energy and environment", /energy|environment|forestry|climate/i],
    ["Places and transport", /housing|communities|local government|transport/i],
    ["Health and welfare", /health|work and pensions|food standards/i],
    ["Learning and culture", /education|culture|skills/i],
    ["The nations", /scottish|scotland|wales|welsh|northern ireland/i],
    ["Law and justice", /justice|attorney|solicitor|legal|supreme court|prosecution|serious fraud/i],
    ["Security and the world", /defence|home office|foreign|international development/i],
  ];
  const sectorOf = name => { const k = SECTORS.findIndex(q => q[1].test(name)); return k < 0 ? SECTORS.length : k; };
  const hash01 = (i, k) => (((i + 1) * 2654435761 + k * 40503) >>> 0) % 10000 / 10000;
  // Each island's area follows the department's staff, with room for its senior posts
  // to stand. Each kind gets a circle of sea: the centre in the middle, the rest round
  // it in order, so neighbouring fields are neighbours. Islands settle nearest their
  // kind's centre, largest first, with a channel of open water between any two.
  function packIslands() {
    const G = S.G, D = G.departments, B = G.bodies;
    const weight = di => Math.pow(Math.max(S.deptFte[di], 500), 0.85) + D[di].bodies.reduce((q, bi) => q + (B[bi].senior || 0), 0) * 8;
    const total = S.order.reduce((q, di) => q + weight(di), 0) || 1, A = 9.4;
    const size = {}; S.sector = {};
    for (const di of S.order) {
      const a = weight(di) / total * A, asp = 1.1 + hash01(di, 1) * 0.6; let w = Math.sqrt(a * asp), h = Math.sqrt(a / asp);
      if (hash01(di, 2) > 0.5) { const t = w; w = h; h = t; } size[di] = { w, h }; S.sector[di] = sectorOf(D[di].name);
    }
    const kinds = []; for (let k = 0; k <= SECTORS.length; k++) { const m = S.order.filter(di => S.sector[di] === k); if (m.length) kinds.push({ k, members: m, area: m.reduce((q, di) => q + size[di].w * size[di].h, 0) }); }
    for (const q of kinds) q.r = Math.sqrt(q.area) * 0.8 + 0.12;
    const ring = kinds.filter(q => q.k !== 0), mid = kinds.find(q => q.k === 0), gap = 0.3;
    const arc = ring.reduce((q, r) => q + 2 * r.r + gap, 0);
    const R = Math.max(arc / (2 * Math.PI), (mid ? mid.r : 0) + Math.max(0, ...ring.map(q => q.r)) + gap);
    const centre = {}; if (mid) centre[0] = [0, 0];
    let ang = -Math.PI / 2;
    for (const q of ring) { const span = (2 * q.r + gap) / R; ang += span / 2; centre[q.k] = [Math.cos(ang) * R, Math.sin(ang) * R]; ang += span / 2; }
    const placed = [], out = new Map();
    const free = (x, y, w, h, k) => placed.every(p => { const m = p.k === k ? 0.14 : 0.34; return x + w + m <= p.x || p.x + p.w + m <= x || y + h + m <= p.y || p.y + p.h + m <= y; });
    for (const di of S.order) {
      const { w, h } = size[di], c = centre[S.sector[di]], a0 = hash01(di, 3) * Math.PI * 2; let done = false;
      for (let r = 0; r < 30 && !done; r += 0.03) {
        const steps = Math.max(1, Math.floor(r * 40));
        for (let k = 0; k < steps && !done; k++) {
          const a = a0 + k / steps * Math.PI * 2 + r * 0.7, x = c[0] + Math.cos(a) * r - w / 2, y = c[1] + Math.sin(a) * r - h / 2;
          if (free(x, y, w, h, S.sector[di])) { const q = { x, y, w, h }; placed.push({ x, y, w, h, k: S.sector[di] }); out.set(di, q); done = true; }
        }
      }
    }
    S.hubs = {};
    for (const q of kinds) {
      let cx = 0, cy = 0; for (const di of q.members) { const r = out.get(di); cx += r.x + r.w / 2; cy += r.y + r.h / 2; }
      S.hubs[q.k] = { di: q.members[0], members: q.members, name: q.k < SECTORS.length ? SECTORS[q.k][0] : "Elsewhere", c: [cx / q.members.length, cy / q.members.length] };
    }
    return out;
  }
  // The heightfield: a plateau under every island's streets, falling as a shore to the
  // sea, with two octaves of noise so no coast is straight. Water is the same mesh held
  // at sea level and marked by its depth, so the shoreline is wherever the land dips
  // under. Colour and light are set per vertex here; the water's motion is the shader's.
  const TG = 200, DEEP = [0.02, 0.042, 0.09];
  function makeTerrainBuffers() {
    const n = TG, idx = [];
    for (let j = 0; j < n - 1; j++) for (let i = 0; i < n - 1; i++) { const a = j * n + i, b = a + 1, c = a + n; idx.push(a, c, b, b, c, c + 1); }
    const ib = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(idx), gl.STATIC_DRAW);
    return { pos: buffer(new Float32Array(n * n * 3), true), col: buffer(new Float32Array(n * n * 3), true), d: buffer(new Float32Array(n * n), true), ib, ni: idx.length, n: 0 };
  }
  const noise = (x, y) => {
    const xi = Math.floor(x), yi = Math.floor(y), fx = x - xi, fy = y - yi, sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
    const h = (a, b) => { const q = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return q - Math.floor(q); };
    return (h(xi, yi) * (1 - sx) + h(xi + 1, yi) * sx) * (1 - sy) + (h(xi, yi + 1) * (1 - sx) + h(xi + 1, yi + 1) * sx) * sy;
  };
  function makeTerrain(islands) {
    const T = S.terrain, n = TG; if (!islands.length) { T.n = 0; return; }
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const { r } of islands) { x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y); x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h); }
    const pad = 1.2; x0 -= pad; y0 -= pad; x1 += pad; y1 += pad;
    const SEA = -0.02, grow = 0.06, pos = new Float32Array(n * n * 3), col = new Float32Array(n * n * 3), dep = new Float32Array(n * n), hgt = new Float32Array(n * n), who = new Int16Array(n * n);
    const tint = islands.map(({ di }) => hsl(S.hue[di], S.sat[di], 0.5));
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
      const x = x0 + (x1 - x0) * i / (n - 1), y = y0 + (y1 - y0) * j / (n - 1); let s = 1e9, w = 0;
      for (let k = 0; k < islands.length; k++) {
        const r = islands[k].r, lx = r.x - grow, rx = r.x + r.w + grow, ly = r.y - grow, ry = r.y + r.h + grow;
        const dx = Math.max(lx - x, 0, x - rx), dy = Math.max(ly - y, 0, y - ry);
        const d = dx > 0 || dy > 0 ? Math.hypot(dx, dy) : Math.max(lx - x, x - rx, ly - y, y - ry);   // negative inside
        if (d < s) { s = d; w = k; }
      }
      s += (noise(x * 6.5, y * 6.5) - 0.5) * 0.09 + (noise(x * 13, y * 13) - 0.5) * 0.03;
      const f = Math.min(1, Math.max(0, (s + 0.02) / 0.16)), z = -0.05 * f * f * (3 - 2 * f);   // plateau, shore, sea bed
      const k = j * n + i; hgt[k] = z; who[k] = w; pos[k * 3] = x; pos[k * 3 + 1] = y; pos[k * 3 + 2] = Math.max(z, SEA); dep[k] = Math.max(0, SEA - z);
    }
    const lx = -0.5, ly = -0.7, lz = 0.55, ll = Math.hypot(lx, ly, lz), cell = (x1 - x0) / (n - 1), sand = [0.23, 0.2, 0.15], deep = DEEP;
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
      const k = j * n + i, z = hgt[k]; let c;
      if (z > SEA) {
        const zx = (hgt[j * n + Math.min(i + 1, n - 1)] - hgt[j * n + Math.max(i - 1, 0)]) / (2 * cell), zy = (hgt[Math.min(j + 1, n - 1) * n + i] - hgt[Math.max(j - 1, 0) * n + i]) / (2 * cell);
        const lit = 0.55 + 0.45 * Math.max(0, (-zx * lx - zy * ly + lz) / (Math.hypot(zx, zy, 1) * ll));
        const t = tint[who[k]], up = Math.min(1, Math.max(0, 1 + z / 0.02));                 // 1 on the plateau, 0 at the tide line
        c = [(0.06 + t[0] * 0.09) * up + sand[0] * (1 - up), (0.062 + t[1] * 0.09) * up + sand[1] * (1 - up), (0.08 + t[2] * 0.09) * up + sand[2] * (1 - up)].map(v => v * lit);
      } else c = deep;
      col[k * 3] = c[0]; col[k * 3 + 1] = c[1]; col[k * 3 + 2] = c[2];
    }
    upload(T.pos, pos); upload(T.col, col); upload(T.d, dep); T.n = T.ni;
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
  const ASPECT = [[1, 1], [1.35, 0.72], [0.78, 1.3], [1.12, 1.12]];
  const jitter = i => 0.82 + ((i * 2654435761) >>> 0) % 1000 / 1000 * 0.36;
  // A body's buildings on their block: depth-first so a subtree keeps together; the
  // footprint is the staff beneath, capped by the plot, in the district's own shape.
  // Posts with no pay band do not stand as buildings (their height would be a
  // guess): they are one low annex per block, sized by how many there are.
  function placeBlock(bi, r, di) {
    const paid = [], unpaid = []; S.roots[bi].forEach(function walk(i) { (S.nopay[i] ? unpaid : paid).push(i); S.kids[i].forEach(walk); });
    const n = paid.length + (unpaid.length ? 1 : 0); if (!n) return;
    const cols = Math.max(1, Math.ceil(Math.sqrt(n * r.w / Math.max(r.h, 1e-6)))), rows = Math.ceil(n / cols);
    const cw = r.w / cols, ch = r.h / rows, asp = ASPECT[S.deptStyle[di]];
    paid.forEach((i, k) => {
      S.to[i * 3] = r.x + cw * ((k % cols) + 0.5); S.to[i * 3 + 1] = r.y + ch * (Math.floor(k / cols) + 0.5); S.to[i * 3 + 2] = S.z[i];
      const want = (0.01 + Math.sqrt(S.N.below_fte[i] || 0) * 0.0025) * jitter(i);
      S.fpTo[i * 2] = Math.min(cw * 0.66, want * asp[0]); S.fpTo[i * 2 + 1] = Math.min(ch * 0.66, want * asp[1]);
      S.styleArr[i] = S.deptStyle[di]; S.hidden[i] = 0; S.annex[i] = 0;
    });
    if (unpaid.length) {
      const k = paid.length, rep = unpaid[0];
      unpaid.forEach(i => { S.to[i * 3] = r.x + cw * ((k % cols) + 0.5); S.to[i * 3 + 1] = r.y + ch * (Math.floor(k / cols) + 0.5); S.to[i * 3 + 2] = 0.045; S.fpTo[i * 2] = 0; S.fpTo[i * 2 + 1] = 0; S.hidden[i] = 1; S.styleArr[i] = 4; S.annex[i] = 0; });
      const w = Math.min(cw * 0.8, 0.008 + Math.sqrt(unpaid.length) * 0.006);
      S.fpTo[rep * 2] = w; S.fpTo[rep * 2 + 1] = Math.min(ch * 0.8, w); S.hidden[rep] = 0; S.annex[rep] = unpaid.length;
    }
  }
  // The organisation chart: leaves evenly across, parents centred over children, rows by
  // depth running away from the viewer, each building on its pay. A post with no pay
  // band stands as a low plinth here, so the line of reports is complete.
  function placeTree(roots, width, depthStep, backY, di) {
    let leaf = 0; const xs = new Map(); const asp = ASPECT[S.deptStyle[di]];
    function place(i, d) {
      const ks = S.kids[i]; let x;
      if (!ks.length) x = leaf++; else { ks.forEach(k => place(k, d + 1)); x = ks.reduce((s, k) => s + xs.get(k), 0) / ks.length; }
      xs.set(i, x); S.to[i * 3 + 1] = backY - d * depthStep; S.to[i * 3 + 2] = S.nopay[i] ? 0.03 : S.z[i];
    }
    roots.forEach(r => place(r, 0));
    const span = Math.max(1, leaf - 1), w = Math.min(width, Math.max(0.6, leaf * 0.09)), pitch = leaf > 1 ? w / span : w;
    xs.forEach((x, i) => { S.to[i * 3] = leaf > 1 ? (x / span - 0.5) * w : 0;
      const want = (0.03 + Math.sqrt(S.N.below_fte[i] || 0) * 0.004) * jitter(i); const cap = Math.min(pitch * 0.78, depthStep * 0.45, 0.14);
      S.fpTo[i * 2] = Math.min(cap, want * asp[0]); S.fpTo[i * 2 + 1] = Math.min(cap, want * asp[1]);
      S.styleArr[i] = S.nopay[i] ? 4 : S.deptStyle[di]; S.hidden[i] = 0; S.annex[i] = 0; });
    return { leaves: leaf, width: w, rows: 1 + Math.max(...Array.from(xs.keys()).map(i => (backY - S.to[i * 3 + 1]) / depthStep)) };
  }
  function layout(f) {
    const G = S.G, B = G.bodies, D = G.departments;
    S.vis.fill(0); const floors = [], streets = [], segs = [], islands = [];
    const addFloor = (r, di, a) => { floors.push({ r, c: hsl(S.hue[di], S.sat[di], 0.5), a }); };
    const addStreets = (r, di) => { const c = hsl(S.hue[di], S.sat[di], 0.6); const q = [[r.x, r.y, r.x + r.w, r.y], [r.x + r.w, r.y, r.x + r.w, r.y + r.h], [r.x + r.w, r.y + r.h, r.x, r.y + r.h], [r.x, r.y + r.h, r.x, r.y]]; for (const s of q) { streets.push({ s, c }); segs.push({ s, c }); } };
    if (f.kind === "gov") {
      const rects = packIslands();
      S.rects = {};
      S.order.forEach(di => {
        const r = rects.get(di); S.rects[di] = r; islands.push({ r, di }); addFloor(r, di, 0.045); addStreets(r, di);
        const inner = { x: r.x + r.w * 0.06, y: r.y + r.h * 0.06, w: r.w * 0.88, h: r.h * 0.88 };
        const bs = treemap(D[di].bodies, bi => Math.max(B[bi].senior, 1), inner);
        D[di].bodies.forEach(bi => { const q = bs.get(bi); placeBlock(bi, { x: q.x + q.w * 0.1, y: q.y + q.h * 0.1, w: q.w * 0.8, h: q.h * 0.8 }, di); });
      });
      // ferry lanes: every island of a kind to the largest of its kind, with traffic between
      for (const hub of Object.values(S.hubs)) for (const di of hub.members) if (di !== hub.di) {
        const a = S.rects[hub.di], b = S.rects[di], c = hsl(S.hue[hub.di], S.sat[hub.di], 0.6);
        const sg = [a.x + a.w / 2, a.y + a.h / 2, b.x + b.w / 2, b.y + b.h / 2]; streets.push({ s: sg, c, a: 0.09 }); segs.push({ s: sg, c, z: [0.006, 0.006] });
      }
      S.vis.fill(1); S.sizeScale = 0.7; S.phiWant = 0.66; S.thetaWant = null;
    } else if (f.kind === "dept") {
      islands.push({ r: { x: -1.7, y: -1.2, w: 3.4, h: 2.4 }, di: f.d });
      const bs = D[f.d].bodies.slice().sort((a, b) => B[b].fte - B[a].fte);
      const rects = treemap(bs, bi => Math.max(B[bi].senior, 1) + Math.sqrt(B[bi].fte || 0) * 0.15, { x: -1.7, y: -1.2, w: 3.4, h: 2.4 });
      S.bodyRects = {}; bs.forEach(bi => { const r = rects.get(bi); S.bodyRects[bi] = r; addFloor(r, f.d, 0.05); addStreets(r, f.d); placeBlock(bi, { x: r.x + r.w * 0.1, y: r.y + r.h * 0.1, w: r.w * 0.8, h: r.h * 0.8 }, f.d); });
      for (let i = 0; i < S.n; i++) if (B[S.N.body[i]].dept === f.d) S.vis[i] = 1;
      S.sizeScale = 1.0; S.phiWant = 0.6; S.thetaWant = null;
    } else {
      const roots = f.kind === "body" ? S.roots[f.b] : [f.p];
      const t = placeTree(roots, 3.4, 0.5, 1.2, f.d);
      if (f.kind === "body") { for (let i = 0; i < S.n; i++) if (S.N.body[i] === f.b) S.vis[i] = 1; }
      else (function mark(i) { S.vis[i] = 1; S.kids[i].forEach(mark); })(f.p);
      const depthY = 1.2 - (t.rows - 1) * 0.5;
      const fr = { x: -t.width / 2 - 0.25, y: depthY - 0.35, w: t.width + 0.5, h: 1.2 - depthY + 0.7 }; addFloor(fr, f.d, 0.03); islands.push({ r: fr, di: f.d });
      // the reporting lines are the streets here: traffic runs down them
      const c = hsl(S.hue[f.d], S.sat[f.d], 0.7);
      for (let i = 0; i < S.n; i++) if (S.vis[i] && S.N.parent[i] >= 0 && S.vis[S.N.parent[i]]) { const p = S.N.parent[i]; segs.push({ s: [S.to[p * 3], S.to[p * 3 + 1], S.to[i * 3], S.to[i * 3 + 1]], z: [S.to[p * 3 + 2], S.to[i * 3 + 2]], c }); }
      S.sizeScale = 1.5; S.phiWant = 0.5; S.thetaWant = -Math.PI / 2;
    }
    for (let i = 0; i < S.n; i++) if (!S.vis[i]) { S.to[i * 3] = S.pos[i * 3]; S.to[i * 3 + 1] = S.pos[i * 3 + 1]; S.to[i * 3 + 2] = S.pos[i * 3 + 2]; S.fpTo[i * 2] = S.fp[i * 2]; S.fpTo[i * 2 + 1] = S.fp[i * 2 + 1]; }
    const fp = [], fc = [], fa = [];
    for (const { r, c, a } of floors) {
      const q = [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]];
      for (const [x, y] of q) { fp.push(x, y, 0.002); fc.push(c[0], c[1], c[2]); fa.push(a); }
    }
    upload(S.floor.pos, new Float32Array(fp)); upload(S.floor.col, new Float32Array(fc)); upload(S.floor.al, new Float32Array(fa)); S.floor.n = fa.length;
    const sp = [], sc = [], sa = [];
    for (const { s, c, a } of streets) { sp.push(s[0], s[1], 0.003, s[2], s[3], 0.003); sc.push(c[0], c[1], c[2], c[0], c[1], c[2]); sa.push(a || 0.35, a || 0.35); }
    upload(S.streets.pos, new Float32Array(sp)); upload(S.streets.col, new Float32Array(sc)); upload(S.streets.al, new Float32Array(sa)); S.streets.n = sa.length;
    makeTerrain(islands);
    S.segs = segs; for (let k = 0; k < S.traffic.n; k++) S.traffic.seg[k] = segs.length ? Math.floor(Math.random() * segs.length) : -1;
    upload(S.pts.style, S.styleArr);
    makeSigns(f);
  }
  // The names, as objects in the scene: one text atlas per level, a camera-facing
  // quad per name, sized by what it names, floating above it. Far ones are small
  // and faint, as far things are, so they no longer pile up as flat text.
  function makeSigns(f) {
    const G = S.G, B = G.bodies, N = S.N, want = [];
    const tintOf = di => { const c = hsl(S.hue[di], S.sat[di], 0.78); return c; };
    if (f.kind === "gov") {
      for (const hub of Object.values(S.hubs)) if (hub.members.length > 1) want.push({ text: hub.name.toUpperCase(), x: hub.c[0], y: hub.c[1], z: 1.25, w: 1.1, tint: [0.42, 0.48, 0.62], hue: 225 });
      S.order.forEach(di => { const r = S.rects[di]; want.push({ text: G.departments[di].name, x: r.x + r.w / 2, y: r.y + r.h / 2, z: 0.92, w: Math.max(0.2, Math.min(0.9, Math.sqrt(r.w * r.h) * 1.15)), tint: tintOf(di), hue: S.hue[di] }); });
    }
    else if (f.kind === "dept") G.departments[f.d].bodies.forEach(bi => { const r = S.bodyRects[bi]; if (!r) return; want.push({ text: B[bi].name, x: r.x + r.w / 2, y: r.y + r.h / 2, z: 0.86, w: Math.max(0.16, Math.min(0.75, Math.sqrt(r.w * r.h) * 1.2)), tint: tintOf(f.d), hue: S.hue[f.d] }); });
    else { const list = []; for (let i = 0; i < S.n; i++) if (S.vis[i]) list.push(i);
      list.sort((a, b) => N.below_fte[b] - N.below_fte[a]).slice(0, 48).forEach(i => want.push({ text: N.title[i] || "(untitled post)", x: S.to[i * 3], y: S.to[i * 3 + 1], z: S.to[i * 3 + 2] + 0.07, w: Math.max(0.14, Math.min(0.42, 0.1 + Math.sqrt(N.below_fte[i] || 0) * 0.008)), tint: tintOf(f.d), hue: S.hue[f.d] })); }
    const ROW = 64, CW = 1024, n = Math.min(want.length, 64);
    const cv = document.createElement("canvas"); cv.width = CW; cv.height = Math.max(ROW, ROW * n);
    const ctx = cv.getContext("2d"); ctx.font = "700 40px system-ui, -apple-system, Segoe UI, Roboto, sans-serif"; ctx.textBaseline = "middle"; ctx.fillStyle = "#fff";
    const c = [], o = [], uv = [], sz = [], tint = [];
    for (let k = 0; k < n; k++) {
      const L = want[k]; let text = L.text; while (ctx.measureText(text).width > CW - 40 && text.length > 4) text = text.slice(0, -2).trimEnd() + "…";
      const tw = ctx.measureText(text).width + 20;
      ctx.shadowColor = `hsl(${L.hue}, 90%, 60%)`; ctx.shadowBlur = 16; ctx.fillText(text, 10, k * ROW + ROW / 2); ctx.shadowBlur = 0; ctx.fillText(text, 10, k * ROW + ROW / 2);
      const h = L.w * ROW / tw, u1 = tw / CW, v0 = k / n, v1 = (k + 1) / n;
      for (const [ox, oy, u, v] of [[-0.5, -0.5, 0, v1], [0.5, -0.5, u1, v1], [0.5, 0.5, u1, v0], [-0.5, -0.5, 0, v1], [0.5, 0.5, u1, v0], [-0.5, 0.5, 0, v0]]) {
        c.push(L.x, L.y, L.z); o.push(ox, oy); uv.push(u, v); sz.push(L.w, h); tint.push(L.tint[0], L.tint[1], L.tint[2]);
      }
    }
    gl.bindTexture(gl.TEXTURE_2D, S.signs.tex); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, cv);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    upload(S.signs.c, new Float32Array(c)); upload(S.signs.o, new Float32Array(o)); upload(S.signs.uv, new Float32Array(uv)); upload(S.signs.sz, new Float32Array(sz)); upload(S.signs.tint, new Float32Array(tint)); S.signs.n = c.length / 3;
  }
  function applyAlpha() {
    const open = S.focus.kind === "body" || S.focus.kind === "post";
    for (let i = 0; i < S.n; i++) S.al[i] = S.vis[i] && !S.hidden[i] ? 1 : 0;
    S.jn.forEach((i, k) => { S.hal[k] = S.vis[i] && open ? 0.1 : 0; });
    S.ln.forEach((i, k) => { const v = S.vis[i] && S.vis[S.N.parent[i]]; S.lal[k * 2] = v && open ? 0.25 : 0; S.lal[k * 2 + 1] = v && open ? 0.5 : 0; });
    upload(S.pts.al, S.al); upload(S.halo.al, S.hal); upload(S.lines.al, S.lal);
  }
  function uploadAll() {
    const p = S.pos, N = S.N;
    upload(S.pts.pos, p); upload(S.pts.fp, S.fp);
    S.jn.forEach((i, k) => { S.hpos[k * 3] = p[i * 3]; S.hpos[k * 3 + 1] = p[i * 3 + 1]; S.hpos[k * 3 + 2] = p[i * 3 + 2] * 0.5; }); upload(S.halo.pos, S.hpos);
    S.ln.forEach((i, k) => { const q = N.parent[i]; S.lpos[k * 6] = p[q * 3]; S.lpos[k * 6 + 1] = p[q * 3 + 1]; S.lpos[k * 6 + 2] = p[q * 3 + 2]; S.lpos[k * 6 + 3] = p[i * 3]; S.lpos[k * 6 + 4] = p[i * 3 + 1]; S.lpos[k * 6 + 5] = p[i * 3 + 2]; }); upload(S.lines.pos, S.lpos);
    S.spireList.forEach((i, k) => { const v = S.vis[i] && !S.hidden[i] && !S.nopay[i]; S.spos[k * 6] = p[i * 3]; S.spos[k * 6 + 1] = p[i * 3 + 1]; S.spos[k * 6 + 2] = p[i * 3 + 2] * 1.07; S.spos[k * 6 + 3] = p[i * 3]; S.spos[k * 6 + 4] = p[i * 3 + 1]; S.spos[k * 6 + 5] = p[i * 3 + 2] * 1.07 + 0.05 + S.fp[i * 2] * 1.5; S.sal[k * 2] = v ? 0.9 : 0; S.sal[k * 2 + 1] = v ? 0.05 : 0; });
    upload(S.spires.pos, S.spos); upload(S.spires.al, S.sal);
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
      head = `<b>UK central government</b><span>${D.length} departments · ${B.length} bodies · ${fmt(S.deptFte.reduce((a, b) => a + b, 0))} FTE · each island is a department; click one</span>`;
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
    gl.viewport(0, 0, canvas.width, canvas.height); makeTargets(canvas.width, canvas.height);
  }
  window.addEventListener("resize", resize); resize();
  function camera() {
    const eye = [S.target[0] + S.dist * Math.cos(S.phi) * Math.cos(S.theta), S.target[1] + S.dist * Math.cos(S.phi) * Math.sin(S.theta), S.target[2] + S.dist * Math.sin(S.phi)];
    let fx = S.target[0] - eye[0], fy = S.target[1] - eye[1], fz = S.target[2] - eye[2]; const fl = Math.hypot(fx, fy, fz) || 1; fx /= fl; fy /= fl; fz /= fl;
    let rx = fy, ry = -fx; const rl = Math.hypot(rx, ry) || 1; rx /= rl; ry /= rl;               // right = forward x up(z)
    S.camRight = [rx, ry, 0]; S.camUp = [ry * fz, -rx * fz, rx * fy - ry * fx];                  // up = right x forward
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
    gl.bindFramebuffer(gl.FRAMEBUFFER, RT.ok ? RT.scene.fb : null); gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.02, 0.022, 0.045, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND); gl.depthMask(false);
    gl.useProgram(SKY); gl.uniform1f(uni(SKY, "theta"), S.theta); gl.uniform1f(uni(SKY, "phi"), S.phi); gl.uniform1f(uni(SKY, "t"), tsec); gl.uniform1f(uni(SKY, "aspect"), W / Hh);
    fullscreen(SKY);
    gl.depthMask(true); gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL); gl.disable(gl.BLEND); disableAll();
    // the sea to the horizon and the islands on it, opaque, so buildings hide what stands behind them
    gl.useProgram(TER); gl.uniformMatrix4fv(uni(TER, "mvp"), false, m); gl.uniform1f(uni(TER, "t"), tsec);
    attrib(TER, "p", S.plane.pos, 3); attrib(TER, "col", S.plane.col, 3); attrib(TER, "d", S.plane.d, 1); gl.drawArrays(gl.TRIANGLES, 0, 6);
    if (S.terrain.n) { disableAll(); attrib(TER, "p", S.terrain.pos, 3); attrib(TER, "col", S.terrain.col, 3); attrib(TER, "d", S.terrain.d, 1);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, S.terrain.ib); gl.drawElements(gl.TRIANGLES, S.terrain.n, gl.UNSIGNED_SHORT, 0); }
    // the buildings
    if (EXT) {
      disableAll(); gl.useProgram(BOX); gl.uniformMatrix4fv(uni(BOX, "mvp"), false, m); gl.uniform1f(uni(BOX, "rise"), rise); gl.uniform1f(uni(BOX, "t"), tsec);
      gl.bindBuffer(gl.ARRAY_BUFFER, S.unit.geo);
      const lv = gl.getAttribLocation(BOX, "v"), ln = gl.getAttribLocation(BOX, "nrm"), lu = gl.getAttribLocation(BOX, "uv");
      for (const [l, size, off] of [[lv, 3, 0], [ln, 3, 12], [lu, 2, 24]]) { gl.enableVertexAttribArray(l); enabled.add(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, 32, off); EXT.vertexAttribDivisorANGLE(l, 0); }
      attrib(BOX, "ipos", S.pts.pos, 3, 1); attrib(BOX, "isz", S.pts.fp, 2, 1); attrib(BOX, "icol", S.pts.col, 3, 1); attrib(BOX, "ia", S.pts.al, 1, 1); attrib(BOX, "istyle", S.pts.style, 1, 1);
      gl.uniform1f(uni(BOX, "tier"), 0); EXT.drawArraysInstancedANGLE(gl.TRIANGLES, 0, S.unit.nv, S.n);
      gl.uniform1f(uni(BOX, "tier"), 1); EXT.drawArraysInstancedANGLE(gl.TRIANGLES, 0, S.unit.nv, S.n);   // the crown: a slimmer top storey
      gl.uniform1f(uni(BOX, "tier"), 2); EXT.drawArraysInstancedANGLE(gl.TRIANGLES, 0, S.unit.nv, S.n);   // and a second on the towers
    }
    // everything luminous: additive, tested against the buildings but not written
    gl.depthMask(false); gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE); disableAll();
    gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, m); gl.uniform1f(uni(LN, "rise"), 1);
    if (S.floor.n) { attrib(LN, "p", S.floor.pos, 3); attrib(LN, "col", S.floor.col, 3); attrib(LN, "a", S.floor.al, 1); gl.drawArrays(gl.TRIANGLES, 0, S.floor.n); }
    if (S.streets.n) { attrib(LN, "p", S.streets.pos, 3); attrib(LN, "col", S.streets.col, 3); attrib(LN, "a", S.streets.al, 1); gl.drawArrays(gl.LINES, 0, S.streets.n); }
    gl.uniform1f(uni(LN, "rise"), rise);
    attrib(LN, "p", S.lines.pos, 3); attrib(LN, "col", S.lines.col, 3); attrib(LN, "a", S.lines.al, 1); gl.drawArrays(gl.LINES, 0, S.ln.length * 2);
    if (EXT) {
      disableAll(); gl.useProgram(EDGE); gl.uniformMatrix4fv(uni(EDGE, "mvp"), false, m); gl.uniform1f(uni(EDGE, "rise"), rise);
      attrib(EDGE, "v", S.unit.edges, 3, 0); attrib(EDGE, "ipos", S.pts.pos, 3, 1); attrib(EDGE, "isz", S.pts.fp, 2, 1); attrib(EDGE, "icol", S.pts.col, 3, 1); attrib(EDGE, "ia", S.pts.al, 1, 1); attrib(EDGE, "istyle", S.pts.style, 1, 1);
      EXT.drawArraysInstancedANGLE(gl.LINES, 0, S.unit.ne, S.n);
    }
    disableAll(); gl.useProgram(LN); gl.uniformMatrix4fv(uni(LN, "mvp"), false, m); gl.uniform1f(uni(LN, "rise"), rise);
    attrib(LN, "p", S.spires.pos, 3); attrib(LN, "col", S.spires.col, 3); attrib(LN, "a", S.spires.al, 1); gl.drawArrays(gl.LINES, 0, S.spireList.length * 2);
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
    if (S.signs.n && !(S.tour && !S.tour.tree)) {
      gl.enable(gl.DEPTH_TEST); disableAll(); gl.useProgram(SIGN); gl.uniformMatrix4fv(uni(SIGN, "mvp"), false, m); gl.uniform1f(uni(SIGN, "rise"), rise);
      gl.uniform3fv(uni(SIGN, "right"), S.camRight); gl.uniform3fv(uni(SIGN, "upv"), S.camUp);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, S.signs.tex); gl.uniform1i(uni(SIGN, "tex"), 0);
      attrib(SIGN, "c", S.signs.c, 3); attrib(SIGN, "o", S.signs.o, 2); attrib(SIGN, "uv", S.signs.uv, 2); attrib(SIGN, "sz", S.signs.sz, 2); attrib(SIGN, "tint", S.signs.tint, 3);
      gl.drawArrays(gl.TRIANGLES, 0, S.signs.n);
    }
    gl.depthMask(true);
    if (RT.ok) {                                                       // bloom: bright pass, two blurs, compose
      gl.disable(gl.DEPTH_TEST); gl.disable(gl.BLEND);
      gl.bindFramebuffer(gl.FRAMEBUFFER, RT.a.fb); gl.viewport(0, 0, RT.a.w, RT.a.h);
      gl.useProgram(BRIGHT); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, RT.scene.tex); gl.uniform1i(uni(BRIGHT, "tex"), 0); fullscreen(BRIGHT);
      gl.bindFramebuffer(gl.FRAMEBUFFER, RT.b.fb); gl.useProgram(BLUR); gl.bindTexture(gl.TEXTURE_2D, RT.a.tex); gl.uniform1i(uni(BLUR, "tex"), 0); gl.uniform2f(uni(BLUR, "dir"), 1 / RT.a.w, 0); fullscreen(BLUR);
      gl.bindFramebuffer(gl.FRAMEBUFFER, RT.a.fb); gl.useProgram(BLUR); gl.bindTexture(gl.TEXTURE_2D, RT.b.tex); gl.uniform1i(uni(BLUR, "tex"), 0); gl.uniform2f(uni(BLUR, "dir"), 0, 1 / RT.a.h); fullscreen(BLUR);
      gl.bindFramebuffer(gl.FRAMEBUFFER, RT.b.fb); gl.useProgram(BLUR); gl.bindTexture(gl.TEXTURE_2D, RT.a.tex); gl.uniform1i(uni(BLUR, "tex"), 0); gl.uniform2f(uni(BLUR, "dir"), 1.6 / RT.a.w, 0); fullscreen(BLUR);
      gl.bindFramebuffer(gl.FRAMEBUFFER, RT.a.fb); gl.useProgram(BLUR); gl.bindTexture(gl.TEXTURE_2D, RT.b.tex); gl.uniform1i(uni(BLUR, "tex"), 0); gl.uniform2f(uni(BLUR, "dir"), 0, 1.6 / RT.a.h); fullscreen(BLUR);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, canvas.width, canvas.height);
      gl.useProgram(COMPOSE); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, RT.scene.tex); gl.uniform1i(uni(COMPOSE, "tex"), 0);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, RT.a.tex); gl.uniform1i(uni(COMPOSE, "bloom"), 1); gl.uniform1f(uni(COMPOSE, "strength"), 1.1);
      fullscreen(COMPOSE); gl.activeTexture(gl.TEXTURE0);
    }
    project(m, rise);
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
    for (let i = 0; i < S.n; i++) { if (!S.vis[i] || S.hidden[i]) continue; const dx = s[i * 2] - mx, dy = s[i * 2 + 1] - my, d = dx * dx + dy * dy - S.sz[i] * 6; if (d < bd) { bd = d; best = i; } }
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
    tip.innerHTML = S.annex[i]
      ? `<b>${S.annex[i]} senior post${S.annex[i] === 1 ? "" : "s"} with no pay band stated</b><br>${esc(b.name)}<br>Grouped as one low annex: a building's height is its pay band, and these give none. Open the body to see each in its place.<br><i>${next}</i>`
      : `<b>${esc(N.title[i] || "(untitled post)")}</b><br>${esc(b.name)}<br>${esc(N.grade[i])} · ${N.pay[i] ? "from £" + N.pay[i].toLocaleString() : "pay band not stated (shown as a plinth)"}<br>${fmt(N.below_fte[i])} FTE beneath` + (N.below_senior[i] > 1 ? `, ${(N.below_senior[i] - 1).toLocaleString()} senior posts` : "") + `<br><i>${next}</i>`;
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
    .then(G => { build(G); requestAnimationFrame(draw); return fetch("/api/family/organograms/timeline.json").then(r => r.ok ? r.json() : null); })
    .then(t => { if (t) setupTimeline(t); })
    .catch(err => { $("sub").textContent = "The graph could not be loaded (" + err.message + "). The chart as a list has every post."; });
})();
