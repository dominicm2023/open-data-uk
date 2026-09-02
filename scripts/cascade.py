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


def load() -> tuple[list[dict], list[str]]:
    """Every post, its parent, and which body it belongs to."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    latest = dict(conn.execute(
        "SELECT publisher, MAX(edition) FROM senior WHERE edition >= '2024' "
        "GROUP BY publisher").fetchall())

    nodes: list[dict] = [{"t": "The top of government", "g": "", "b": -1,
                          "c": 0, "p": -1}]          # the synthetic centre
    bodies: list[str] = []
    for pub, ed in sorted(latest.items()):
        rows = conn.execute(
            "SELECT post_ref, job_title, grade, reports_to, reports_salary_cost "
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
        out.append([round(math.cos(angle[i]) * r, 1),
                    round(math.sin(angle[i]) * r, 1), depth[i]])
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
  <span class="note">hover a post to trace it back to the centre</span>
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

// Fit the whole tree, whatever its deepest branch turns out to be.
const REACH = Math.max(...DATA.pos.map(p => Math.hypot(p[0], p[1])));
const S = (Math.min(cv.width, cv.height) / 2 - 30) / REACH;
const at = i => [CX + DATA.pos[i][0] * S, CY + DATA.pos[i][1] * S];

function pathToRoot(i) {
  const chain = [];
  let guard = 0;
  while (i > 0 && guard++ < 40) { chain.push(i); i = DATA.nodes[i].p; }
  chain.push(0);
  return chain;
}

function draw() {
  ctx.fillStyle = "#0b0e11";
  ctx.fillRect(0, 0, cv.width, cv.height);
  const lit = hover >= 0 ? new Set(pathToRoot(hover)) : null;

  ctx.lineWidth = 0.7;
  for (let i = 1; i < DATA.nodes.length; i++) {
    const n = DATA.nodes[i];
    if (only >= 0 && n.b !== only) continue;
    const [x, y] = at(i), [px, py] = at(n.p);
    const onPath = lit && lit.has(i);
    ctx.strokeStyle = onPath ? "#ffffff"
      : `hsla(${HUE[n.b]},60%,60%,${lit ? 0.06 : 0.20})`;
    ctx.lineWidth = onPath ? 1.8 : 0.7;
    // Bend each link toward the centre: straight spokes read as a starburst,
    // curves read as a tree, and the tree is the true shape.
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.quadraticCurveTo((px + x) / 2 * 0.72 + CX * 0.28,
                         (py + y) / 2 * 0.72 + CY * 0.28, x, y);
    ctx.stroke();
  }

  for (let i = DATA.nodes.length - 1; i >= 0; i--) {
    const n = DATA.nodes[i];
    if (i && only >= 0 && n.b !== only) continue;
    const [x, y] = at(i);
    const onPath = lit && lit.has(i);
    const r = i === 0 ? 7 : 1.4 + 5.0 * Math.sqrt(n.c / MAXC);
    ctx.globalAlpha = lit ? (onPath ? 1 : 0.16) : 0.85;
    ctx.fillStyle = i === 0 ? "#ffffff"
      : `hsl(${HUE[n.b]},65%,${onPath ? 82 : 60}%)`;
    ctx.beginPath(); ctx.arc(x, y, onPath ? r + 1.6 : r, 0, 6.284); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

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
  const i = pick(mx, my);
  if (i !== hover) { hover = i; draw(); }
  if (i >= 0) {
    const n = DATA.nodes[i], chain = pathToRoot(i);
    tip.innerHTML = '<b>' + n.t + '</b><br>' + (n.g ? n.g + ' · ' : '') +
      DATA.bodies[n.b] + '<br>' + (chain.length - 2) +
      ' post(s) between this and the top of its department' +
      (n.c ? '<br>£' + n.c.toLocaleString() + ' of salary reports to it' : '');
    tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX - r.left + 14, r.width - 250) + 'px';
    tip.style.top = (e.clientY - r.top + 14) + 'px';
  } else { tip.style.opacity = 0; }
});
cv.addEventListener('pointerleave', () => { hover = -1; tip.style.opacity = 0; draw(); });
document.getElementById('pick').addEventListener('change', e => {
  only = +e.target.value; hover = -1; stat(); draw();
});
function stat() {
  const n = only < 0 ? DATA.nodes.length - 1
    : DATA.nodes.filter(x => x.b === only).length;
  document.getElementById('stat').textContent = n.toLocaleString() + ' posts';
}
stat(); draw();
</script>
</body></html>
"""


def main() -> int:
    nodes, bodies = load()
    pos = radial(nodes, bodies)
    depth_max = max(p[2] for p in pos)
    counts = collections.Counter(n["b"] for n in nodes if n["b"] >= 0)
    deepest = max(range(len(nodes)), key=lambda i: pos[i][2])

    data = {"nodes": [{k: n[k] for k in ("t", "g", "b", "c", "p")} for n in nodes],
            "bodies": bodies,
            "pos": [[p[0], p[1]] for p in pos]}
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
