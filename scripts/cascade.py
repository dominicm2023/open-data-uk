"""The whole senior structure as one tree, radiating from the top.

Each department publishes its own organogram, so there is no file anywhere
that joins them. This makes one: a synthetic root at the centre, the top
post of each of 41 bodies on the first ring, and then every reporting line
as published, ring by ring, out to the edge.

The one invented link is the centre. Everything from ring one outward is
what a department released, and the page says which is which — the top of
government is a real thing but it is not in these files, because
organograms record civil servants and ministers are not civil servants.

Layout is a radial dendrogram computed here: each body gets an angular
wedge in proportion to how many posts it has, each post sits at a radius
set by its depth and an angle set by its children. That is deterministic
and instant, which matters — the force layout this replaces took twenty
minutes a go and made every adjustment expensive.

Hovering a post lights the whole path back to the centre, which is the
question the picture exists to answer: what stands between this job and
the top?

Usage:  python scripts/cascade.py
"""

from __future__ import annotations

import collections
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "analysis" / "organograms" / "organograms.sqlite"
OUT = ROOT / "cascade.html"
RING = 108.0          # pixels between depth rings
GAP = 0.012           # radians of breathing space between departments
DROP = 132.0          # how far each ring falls, making a cone not a disc


def load() -> tuple[list[dict], list[str]]:
    """Every post, its parent, and which body it belongs to."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    latest = dict(conn.execute(
        "SELECT publisher, MAX(edition) FROM senior WHERE edition >= '2024' "
        "GROUP BY publisher").fetchall())

    nodes: list[dict] = [{"t": "The top of government", "g": "", "b": -1,
                          "c": 0, "f": 0, "p": -1}]          # the synthetic centre
    bodies: list[str] = []
    for pub, ed in sorted(latest.items()):
        rows = conn.execute(
            "SELECT post_ref, job_title, grade, reports_to, pay_floor, "
            "       reports_salary_cost "
            "FROM senior WHERE publisher = ? AND edition = ?",
            (pub, ed)).fetchall()
        rows = [r for r in rows if r["post_ref"]]
        if len(rows) < 3:
            continue
        body = len(bodies)
        bodies.append(pub)
        refs = {r["post_ref"] for r in rows}
        start = len(nodes)
        local = {r["post_ref"]: start + i for i, r in enumerate(rows)}
        for r in rows:
            parent = (r["reports_to"] or "").strip()
            # A post reporting to nothing inside its own file is a top of
            # that body, and hangs from the centre.
            pid = local[parent] if (parent in refs and parent != r["post_ref"]) else 0
            nodes.append({
                "t": (r["job_title"] or r["grade"] or "post")[:74],
                "g": (r["grade"] or "")[:26],
                "b": body,
                "c": r["reports_salary_cost"] or 0,
                "f": r["pay_floor"] or 0,
                "p": pid,
            })
    conn.close()
    return nodes, bodies


def radial(nodes: list[dict], bodies: list[str]) -> list[list[float]]:
    """Angle from the tree, radius from the depth. Leaves share the circle
    evenly, and every parent sits at the mean angle of its children — which
    is what makes a dendrogram read as a structure rather than a spiral."""
    kids = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        if i:
            kids[n["p"]].append(i)

    depth = [0] * len(nodes)
    order = collections.deque([0])
    while order:
        i = order.popleft()
        for k in kids[i]:
            depth[k] = depth[i] + 1
            order.append(k)

    # Each body owns a wedge sized by its share of all posts, so a big
    # department is visibly big rather than merely crowded.
    share = collections.Counter(n["b"] for n in nodes if n["b"] >= 0)
    total = sum(share.values())
    wedge, cursor = {}, 0.0
    for body, count in sorted(share.items()):
        span = 2 * math.pi * count / total
        wedge[body] = (cursor + GAP / 2, cursor + span - GAP / 2)
        cursor += span

    angle = [0.0] * len(nodes)
    # Leaves first, spread evenly inside their body's wedge; then every
    # parent takes the average of its children, from the outside in.
    by_body_leaves = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        if i and not kids[i]:
            by_body_leaves[n["b"]].append(i)
    for body, leaves in by_body_leaves.items():
        lo, hi = wedge[body]
        leaves.sort()
        for j, leaf in enumerate(leaves):
            angle[leaf] = lo + (hi - lo) * (j + 0.5) / len(leaves)

    for i in sorted(range(len(nodes)), key=lambda i: -depth[i]):
        if kids[i]:
            angle[i] = sum(angle[k] for k in kids[i]) / len(kids[i])
    angle[0] = 0.0

    out = []
    for i, n in enumerate(nodes):
        r = depth[i] * RING
        # z descends with depth, so the tree hangs as a cone rather than
        # lying flat: the top of government is genuinely at the top.
        out.append([round(math.cos(angle[i]) * r, 1),
                    round(math.sin(angle[i]) * r, 1),
                    round(-depth[i] * DROP, 1), depth[i]])
    return out


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>From the top — Joined Up workshop</title>
<link rel="stylesheet" href="/site.css">
<style>
  .stage { position: relative; background: #0b0e11; border: 1px solid var(--line);
           border-radius: var(--radius); overflow: hidden; touch-action: none; }
  .stage canvas { display: block; width: 100%; height: auto; cursor: crosshair; }
  .tip { position: absolute; pointer-events: none; background: var(--card);
         border: 1px solid var(--line-strong); border-radius: var(--radius-sm);
         padding: .45rem .6rem; font-size: .8rem; opacity: 0;
         transition: opacity .1s; max-width: 20rem;
         box-shadow: 0 2px 14px rgba(0,0,0,.4); }
  .ctl { display: flex; gap: 1rem; align-items: center; margin: .8rem 0 0;
         font-size: .85rem; flex-wrap: wrap; }
  .ctl select { font: inherit; padding: .2rem; max-width: 16rem; }
</style>
</head><body><div class="wrap wide">
<h1>From the top</h1>
<p class="lede">__LEDE__</p>

<div class="stage" id="stage">
  <canvas id="c" width="1500" height="1500"></canvas>
  <div class="tip" id="tip"></div>
</div>
<div class="ctl">
  <label>show <select id="pick">
    <option value="-1">every body</option>__OPTS__</select></label>
  <label>size by <select id="scale">
    <option value="c">salary reporting to the post</option>
    <option value="f">the post's own pay</option>
    <option value="n">nothing</option></select></label>
  <label><input type="checkbox" id="spin" checked> turn</label>
  <span class="note" id="stat"></span>
</div>

<p class="note" style="margin-top:1.4rem">
How it was measured: the latest organogram each body published from 2024 on.
One point per senior post, placed at a radius set by how many reporting
steps separate it from the top of its own department, and an angle inside
that department's share of the circle. Every line outward from the first
ring is a "reports to" reference as published. <b>The centre is ours</b>: no
file joins the departments, and organograms record civil servants rather
than ministers, so the hub is drawn to hold them together and is not a
claim about who anyone reports to. Joined Up · open-data.org.uk</p>
</div>
<script>
const DATA = __DATA__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tip = document.getElementById('tip');
let hover = -1, only = -1;
const HUE = DATA.bodies.map((_, i) => (i * 137.508) % 360);
const MAXC = Math.max(1, ...DATA.nodes.map(n => n.c));
const CX = cv.width / 2, CY = cv.height / 2;
let rx = 1.02, ry = 0.0, drag = null, scaleBy = 'c', spinning = true;

// The biggest figure under each scaling, so a size means the same thing
// whichever measure is chosen.
const MAX = {c: Math.max(1, ...DATA.nodes.map(n => n.c)),
             f: Math.max(1, ...DATA.nodes.map(n => n.f)), n: 1};
const REACH = Math.max(...DATA.pos.map(p => Math.hypot(p[0], p[1])));

let P = [];
function project() {
  const cx = Math.cos(rx), sx = Math.sin(rx), cy = Math.cos(ry), sy = Math.sin(ry);
  const s = (Math.min(cv.width, cv.height) / 2 - 40) / REACH;
  P = DATA.pos.map(([x, y, z]) => {
    let x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
    let y1 = y * cx - z1 * sx; z1 = y * sx + z1 * cx;
    // Perspective, so the near side of the cone is larger and the far side
    // recedes — without it a tilted disc just looks like a squashed one.
    const k = 1 / (1.55 - (z1 / (REACH * 1.35)) * 0.85);
    return [CX + x1 * s * k, CY + y1 * s * k, k];
  });
  return P;
}
const at = i => P[i];

function nodeSize(n) {
  if (scaleBy === 'n' || !n[scaleBy]) return 2.0;
  return 2.0 + 9.0 * Math.sqrt(n[scaleBy] / MAX[scaleBy]);
}

function pathToRoot(i) {
  const chain = []; let guard = 0;
  while (i > 0 && guard++ < 40) { chain.push(i); i = DATA.nodes[i].p; }
  chain.push(0);
  return chain;
}

function draw() {
  project();
  ctx.fillStyle = "#0b0e11";
  ctx.fillRect(0, 0, cv.width, cv.height);
  const lit = hover >= 0 ? new Set(pathToRoot(hover)) : null;

  for (let i = 1; i < DATA.nodes.length; i++) {
    const n = DATA.nodes[i];
    if (only >= 0 && n.b !== only) continue;
    const a = at(i), b = at(n.p);
    const onPath = lit && lit.has(i);
    ctx.strokeStyle = onPath ? "#ffffff"
      : `hsla(${HUE[n.b]},60%,62%,${(lit ? 0.05 : 0.10 + a[2] * 0.16).toFixed(3)})`;
    ctx.lineWidth = onPath ? 1.9 : 0.6;
    ctx.beginPath();
    ctx.moveTo(b[0], b[1]);
    ctx.quadraticCurveTo((b[0] + a[0]) / 2 * 0.78 + CX * 0.22,
                         (b[1] + a[1]) / 2 * 0.78 + CY * 0.22, a[0], a[1]);
    ctx.stroke();
  }

  // Painter's algorithm: far side first, or the cone turns inside out.
  const order = DATA.nodes.map((_, i) => i).sort((i, j) => P[i][2] - P[j][2]);
  for (const i of order) {
    const n = DATA.nodes[i];
    if (i && only >= 0 && n.b !== only) continue;
    const [x, y, k] = at(i);
    const onPath = lit && lit.has(i);
    const r = (i === 0 ? 9 : nodeSize(n)) * k;
    ctx.globalAlpha = lit ? (onPath ? 1 : 0.14) : (0.35 + k * 0.6);
    const known = scaleBy === 'n' || n[scaleBy] > 0;
    if (i === 0) {
      ctx.fillStyle = "#ffffff";
      ctx.beginPath(); ctx.arc(x, y, r, 0, 6.284); ctx.fill();
    } else if (known) {
      ctx.fillStyle = `hsl(${HUE[n.b]},66%,${onPath ? 84 : 58}%)`;
      ctx.beginPath(); ctx.arc(x, y, Math.max(r, 0.7), 0, 6.284); ctx.fill();
    } else {
      // No figure published. Drawn hollow rather than small, so an absence
      // reads as an absence instead of as a modest salary.
      ctx.strokeStyle = `hsla(${HUE[n.b]},45%,62%,.75)`;
      ctx.lineWidth = 0.9;
      ctx.beginPath(); ctx.arc(x, y, 2.1 * k, 0, 6.284); ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

cv.addEventListener('pointerdown', e => { drag = [e.clientX, e.clientY]; });
addEventListener('pointerup', () => { drag = null; });

function pick(mx, my) {
  let best = -1, bestD = 13;
  for (let i = 1; i < DATA.nodes.length; i++) {
    if (only >= 0 && DATA.nodes[i].b !== only) continue;
    const [x, y] = at(i);
    const d = Math.hypot(x - mx, y - my);
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

cv.addEventListener('pointermove', e => {
  const r = cv.getBoundingClientRect();
  const mx = (e.clientX - r.left) * cv.width / r.width;
  const my = (e.clientY - r.top) * cv.height / r.height;
  if (drag) {
    ry += (e.clientX - drag[0]) * 0.007;
    rx = Math.max(0.15, Math.min(1.5, rx + (e.clientY - drag[1]) * 0.005));
    drag = [e.clientX, e.clientY]; draw(); return;
  }
  const i = pick(mx, my);
  if (i !== hover) { hover = i; draw(); }
  if (i >= 0) {
    const n = DATA.nodes[i], chain = pathToRoot(i);
    tip.innerHTML = '<b>' + n.t + '</b><br>' + (n.g ? n.g + ' · ' : '') +
      DATA.bodies[n.b] + '<br>' + (chain.length - 2) +
      ' post(s) between this and the top of its department' +
      (n.f ? '<br>pay from £' + n.f.toLocaleString() : '') +
      (n.c ? '<br>£' + n.c.toLocaleString() + ' of salary reports to it' : '') +
      (!n.f && !n.c ? '<br><i>publishes no pay figure</i>' : '');
    tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX - r.left + 14, r.width - 250) + 'px';
    tip.style.top = (e.clientY - r.top + 14) + 'px';
  } else { tip.style.opacity = 0; }
});
cv.addEventListener('pointerleave', () => { hover = -1; tip.style.opacity = 0; draw(); });
document.getElementById('pick').addEventListener('change', e => {
  only = +e.target.value; hover = -1; stat(); draw();
});
document.getElementById('scale').addEventListener('change', e => {
  scaleBy = e.target.value; stat(); draw();
});
document.getElementById('spin').addEventListener('change',
  e => spinning = e.target.checked);
function stat() {
  const sel = only < 0 ? DATA.nodes.slice(1)
    : DATA.nodes.filter(x => x.b === only);
  const known = scaleBy === 'n' ? sel.length
    : sel.filter(x => x[scaleBy] > 0).length;
  document.getElementById('stat').textContent =
    sel.length.toLocaleString() + ' posts' + (scaleBy === 'n' ? '' :
    ' · ' + known.toLocaleString() + ' publish a figure, the hollow ones do not');
}
(function tick() {
  if (spinning && !drag) { ry += 0.0018; draw(); }
  requestAnimationFrame(tick);
})();
stat(); draw();
</script>
</body></html>
"""


def main() -> int:
    nodes, bodies = load()
    pos = radial(nodes, bodies)
    depth_max = max(p[3] for p in pos)   # p[2] is z now, p[3] the ring
    counts = collections.Counter(n["b"] for n in nodes if n["b"] >= 0)
    deepest = max(range(len(nodes)), key=lambda i: pos[i][3])

    data = {"nodes": [{k: n[k] for k in ("t", "g", "b", "c", "f", "p")}
                      for n in nodes],
            "bodies": bodies,
            "pos": [[p[0], p[1], p[2]] for p in pos]}
    opts = "".join(f'<option value="{i}">{bodies[i]} ({counts[i]:,})</option>'
                   for i, _ in sorted(counts.items(), key=lambda kv: -kv[1]))
    lede = (
        f"{len(nodes) - 1:,} senior posts from {len(bodies)} public bodies, "
        "arranged as one tree: the top of government at the centre, each "
        "department's own top posts on the first ring, and every reporting "
        f"line outward from there. The longest chain runs {depth_max} steps "
        f"from the centre — {nodes[deepest]['t']} at "
        f"{bodies[nodes[deepest]['b']]}. Hover any post to light the whole "
        "path back to the middle.")

    OUT.write_text(
        PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__LEDE__", lede).replace("__OPTS__", opts),
        encoding="utf-8")
    print(f"{len(nodes) - 1:,} posts, {len(bodies)} bodies, "
          f"deepest chain {depth_max} rings")
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
