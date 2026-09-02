"""The whole senior structure of the British state, as one web.

Every department publishes its own organogram and nobody joins them, so the
senior civil service has never been seen in one picture. This is it: 6,214
posts from 44 bodies' latest editions, every reporting line as published,
laid out in three dimensions.

The layout is deliberately not one undifferentiated hairball. Each post is
pulled toward its own department as well as toward the post it reports to,
so departments settle into recognisable bodies with their internal
hierarchy visible inside them — the Ministry of Defence's twenty-eight
separate command trees look different from HMRC's single tower, and you can
see that they do.

There is no geography here on purpose. The published schema records a post,
a grade and who it reports to; it records no location. Placing these on a
map would mean geocoding department headquarters and implying that every
post sits there, which is not true and not something the data says.

Usage:  python scripts/orgweb.py
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "analysis" / "organograms" / "organograms.sqlite"
OUT = ROOT / "orgweb.html"
ITERATIONS = 420
CHUNK = 512          # rows of the repulsion matrix computed at a time


def load() -> tuple[list[dict], list[tuple[int, int]], list[str]]:
    import sqlite3
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    latest = dict(conn.execute(
        "SELECT publisher, MAX(edition) FROM senior WHERE edition >= '2024' "
        "GROUP BY publisher").fetchall())

    nodes, edges, bodies = [], [], []
    for pub, ed in sorted(latest.items()):
        rows = conn.execute(
            "SELECT post_ref, job_title, grade, reports_to, pay_floor, "
            "       reports_salary_cost FROM senior "
            "WHERE publisher = ? AND edition = ?", (pub, ed)).fetchall()
        if len(rows) < 3:
            continue
        body = len(bodies)
        bodies.append(pub)
        local = {}
        for r in rows:
            if not r["post_ref"]:
                continue
            local[r["post_ref"]] = len(nodes)
            nodes.append({
                "t": (r["job_title"] or r["grade"] or "post")[:72],
                "g": (r["grade"] or "")[:28],
                "b": body,
                "c": r["reports_salary_cost"] or 0,
            })
        for r in rows:
            src = local.get(r["post_ref"])
            dst = local.get((r["reports_to"] or "").strip())
            if src is not None and dst is not None and src != dst:
                edges.append((src, dst))
    conn.close()
    return nodes, edges, bodies


def layout(nodes: list[dict], edges: list[tuple[int, int]],
           bodies: list[str]) -> np.ndarray:
    """Force layout in 3D, with each department also pulled to its own centre.

    Repulsion is the whole n-by-n interaction, computed a slice of rows at a
    time — 6,214 squared in one array is 900 MB and the machine has better
    uses for it. Slicing costs a little speed and no accuracy.
    """
    rng = np.random.default_rng(20260902)
    n = len(nodes)
    body = np.array([x["b"] for x in nodes])
    n_bodies = len(bodies)

    # Start each department in its own region of the sphere rather than in
    # one shared cloud: the simulation then has only to arrange them, not to
    # first tear them apart.
    seeds = rng.normal(0, 1, (n_bodies, 3))
    seeds /= np.linalg.norm(seeds, axis=1, keepdims=True)
    pos = seeds[body] * 2.4 + rng.normal(0, 0.28, (n, 3))

    src = np.array([e[0] for e in edges])
    dst = np.array([e[1] for e in edges])

    for step in range(ITERATIONS):
        cool = 1.0 - step / ITERATIONS
        force = np.zeros_like(pos)
        for start in range(0, n, CHUNK):
            end = min(start + CHUNK, n)
            delta = pos[start:end, None, :] - pos[None, :, :]
            d2 = (delta ** 2).sum(-1) + 0.08
            force[start:end] += (delta / d2[..., None]).sum(1) * 0.06

        seg = pos[dst] - pos[src]
        pull = seg * 0.055
        np.add.at(force, src, pull)
        np.add.at(force, dst, -pull)

        # Each department toward its own centre of mass, so the bodies stay
        # bodies instead of dissolving into one another.
        centres = np.zeros((n_bodies, 3))
        np.add.at(centres, body, pos)
        counts = np.bincount(body, minlength=n_bodies).clip(1)[:, None]
        centres /= counts
        force += (centres[body] - pos) * 0.035

        force -= pos * 0.004
        pos += np.clip(force, -0.9, 0.9) * (0.30 * cool + 0.02)

    pos -= pos.mean(0)
    pos /= np.abs(pos).max()
    return pos


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>The web of the state — Joined Up workshop</title>
<link rel="stylesheet" href="/site.css">
<style>
  .stage { position: relative; background: #0d1013; border: 1px solid var(--line);
           border-radius: var(--radius); overflow: hidden; touch-action: none; }
  .stage canvas { display: block; width: 100%; height: auto; cursor: grab; }
  .stage canvas:active { cursor: grabbing; }
  .tip { position: absolute; pointer-events: none; background: var(--card);
         border: 1px solid var(--line-strong); border-radius: var(--radius-sm);
         padding: .4rem .6rem; font-size: .8rem; opacity: 0; transition: opacity .12s;
         max-width: 18rem; box-shadow: 0 2px 12px rgba(0,0,0,.35); }
  .ctl { display: flex; gap: 1rem; align-items: center; margin: .8rem 0 0;
         font-size: .85rem; flex-wrap: wrap; }
  .ctl select { font: inherit; padding: .2rem; max-width: 15rem; }
</style>
</head><body><div class="wrap wide">
<h1>The web of the state</h1>
<p class="lede">__LEDE__</p>

<div class="stage" id="stage">
  <canvas id="c" width="1600" height="1000"></canvas>
  <div class="tip" id="tip"></div>
</div>
<div class="ctl">
  <label><input type="checkbox" id="spin" checked> rotate</label>
  <label>highlight
    <select id="pick"><option value="-1">every body</option>__OPTS__</select>
  </label>
  <span class="note" id="stat"></span>
</div>

<p class="note" style="margin-top:1.4rem">
How it was measured: the latest organogram each body published from 2024 on,
as released under the transparency agenda. One point per senior post, one
line per "reports to" reference that resolves to a post in the same file.
Position is a force layout — posts pull toward what they report to and
toward their own department — not a geography: the published schema records
grade and reporting line, and no location, so putting these on a map would
mean inventing where people sit. Joined Up · open-data.org.uk</p>
</div>
<script>
const DATA = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
let rx = -0.3, ry = 0.5, drag = null, hover = -1, only = -1;

// One hue per department, spun round the wheel so neighbours differ.
const HUE = DATA.bodies.map((_, i) => (i * 137.508) % 360);
const MAXC = Math.max(1, ...DATA.nodes.map(n => n.c));

function project() {
  const cx = Math.cos(rx), sx = Math.sin(rx), cy = Math.cos(ry), sy = Math.sin(ry);
  const s = Math.min(cv.width, cv.height) * 0.46;
  return DATA.pos.map(([x, y, z]) => {
    let x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
    let y1 = y * cx - z1 * sx; z1 = y * sx + z1 * cx;
    const k = 1 / (2.5 - z1 * 0.85);
    // 1.35, not 2.1: at the wider scale 424 of the 6,209 posts projected
    // off the edge of the canvas, which on a picture whose claim is "all of
    // it" is the one thing it must not do.
    return [cv.width / 2 + x1 * s * k * 1.35, cv.height / 2 + y1 * s * k * 1.35, k];
  });
}

function draw() {
  const p = project();
  ctx.fillStyle = "#0d1013";
  ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.lineWidth = 0.8;
  for (const [a, b] of DATA.edges) {
    const nb = DATA.nodes[a].b;
    if (only >= 0 && nb !== only) continue;
    const near = (p[a][2] + p[b][2]) / 2;
    ctx.strokeStyle = `hsla(${HUE[nb]},55%,62%,${(0.05 + near * 0.30).toFixed(3)})`;
    ctx.beginPath(); ctx.moveTo(p[a][0], p[a][1]); ctx.lineTo(p[b][0], p[b][1]); ctx.stroke();
  }
  const order = p.map((_, i) => i).sort((i, j) => p[i][2] - p[j][2]);
  for (const i of order) {
    const n = DATA.nodes[i], [x, y, k] = p[i];
    if (only >= 0 && n.b !== only) continue;
    const r = (1.0 + 4.2 * Math.sqrt(n.c / MAXC)) * k * 1.6;
    ctx.globalAlpha = hover === -1 ? 0.30 + k * 0.7 : (hover === i ? 1 : 0.22);
    ctx.fillStyle = `hsl(${HUE[n.b]},62%,${hover === i ? 78 : 58}%)`;
    ctx.beginPath(); ctx.arc(x, y, Math.max(r, 0.8), 0, 6.284); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function pick(mx, my) {
  const p = project();
  let best = -1, bestD = 16;
  for (let i = 0; i < p.length; i++) {
    if (only >= 0 && DATA.nodes[i].b !== only) continue;
    const d = Math.hypot(p[i][0] - mx, p[i][1] - my);
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

cv.addEventListener('pointerdown', e => { drag = [e.clientX, e.clientY]; });
addEventListener('pointerup', () => { drag = null; });
cv.addEventListener('pointermove', e => {
  const r = cv.getBoundingClientRect();
  const mx = (e.clientX - r.left) * cv.width / r.width;
  const my = (e.clientY - r.top) * cv.height / r.height;
  if (drag) {
    ry += (e.clientX - drag[0]) * 0.007; rx += (e.clientY - drag[1]) * 0.007;
    drag = [e.clientX, e.clientY]; draw(); return;
  }
  const i = pick(mx, my);
  if (i !== hover) { hover = i; draw(); }
  if (i >= 0) {
    const n = DATA.nodes[i];
    tip.innerHTML = '<b>' + n.t + '</b><br>' + (n.g ? n.g + ' · ' : '') +
      DATA.bodies[n.b] + (n.c ? '<br>£' + n.c.toLocaleString() +
      ' of salary reports to this post' : '');
    tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX - r.left + 12, r.width - 230) + 'px';
    tip.style.top = (e.clientY - r.top + 12) + 'px';
  } else { tip.style.opacity = 0; }
});
document.getElementById('pick').addEventListener('change', e => {
  only = +e.target.value; hover = -1; stat(); draw();
});
function stat() {
  const n = only < 0 ? DATA.nodes.length
    : DATA.nodes.filter(x => x.b === only).length;
  document.getElementById('stat').textContent =
    n.toLocaleString() + ' posts shown of ' + DATA.nodes.length.toLocaleString();
}
let spinning = true;
document.getElementById('spin').addEventListener('change', e => spinning = e.target.checked);
(function tick() {
  if (spinning && !drag) { ry += 0.0013; draw(); }
  requestAnimationFrame(tick);
})();
stat(); draw();
</script>
</body></html>
"""


def main() -> int:
    nodes, edges, bodies = load()
    print(f"{len(nodes):,} posts, {len(edges):,} reporting lines, "
          f"{len(bodies)} bodies")
    pos = layout(nodes, edges, bodies)

    data = {"nodes": nodes, "bodies": bodies,
            "edges": [[a, b] for a, b in edges],
            "pos": [[round(v, 3) for v in p] for p in pos]}
    counts = collections.Counter(n["b"] for n in nodes)
    biggest = bodies[counts.most_common(1)[0][0]]
    opts = "".join(
        f'<option value="{i}">{bodies[i]} ({counts[i]:,})</option>'
        for i, _ in sorted(counts.items(), key=lambda kv: -kv[1]))

    lede = (
        f"{len(nodes):,} senior posts across {len(bodies)} public bodies, "
        f"and {len(edges):,} reporting lines between them, from the latest "
        "organogram each one published. Every department releases its own "
        "and nobody joins them up, so the senior civil service has not been "
        "seen in one picture before. Each body is a colour and is pulled "
        "together by its own gravity, so you are looking at real structures "
        f"rather than a cloud — {biggest} is the largest. Drag to turn it, "
        "hover for a post, pick one body to see it alone.")

    OUT.write_text(
        PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__LEDE__", lede).replace("__OPTS__", opts),
        encoding="utf-8")
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
