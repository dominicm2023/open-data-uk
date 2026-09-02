"""The constellation: every UK body that publishes what another one does.

Two councils publishing a dataset of the same name are doing the same job
twice, separately, with no idea the other did it. The index is the only
place that can see this, because each portal knows only its own records.
Drawn as a graph it stops being a statistic and becomes a shape: councils
pull into a dense mass, health bodies into their own, and the national
agencies drift at the edges publishing things nobody else does.

Nodes are publishers, sized by how many datasets they hold. An edge joins
two bodies that publish two or more datasets of the same name. Titles shared
by more than sixty bodies are left out of the edge building — "spend over
£500" is published by everyone and links everything to everything, which is
true and tells you nothing.

The layout is a 3D force simulation, but it runs *here*, once, and the
browser only receives the finished coordinates. So the page opens instantly
and spends its frames rotating and drawing rather than simulating, and the
same input always produces the same constellation.

Usage:  python scripts/constellation.py
"""

from __future__ import annotations

import collections
import itertools
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from paths import connect  # noqa: E402

OUT = ROOT / "constellation.html"

MIN_SHARED = 2       # two bodies must share this many titles to be joined
MAX_SPREAD = 60      # a title more bodies than this share joins everyone
ITERATIONS = 600

SECTORS = (
    ("council", r"council|borough|district|city of|county|unitary|comhairle|cyngor"),
    ("health", r"\bnhs\b|health board|hospital|ambulance|integrated care|ccg|icb"),
    ("government", r"^department|^ministry|^office|^hm |cabinet office|^foreign,"),
    ("agency", r"agency|authority|executive|commission|inspectorate|ofsted|ofcom|ofgem"),
    ("research", r"university|college|institute|research|survey|museum|trust"),
)


def sector(name: str) -> str:
    low = (name or "").lower()
    for label, pattern in SECTORS:
        if re.search(pattern, low):
            return label
    return "other"


def build_graph() -> tuple[list[dict], list[tuple[int, int, int]]]:
    conn = connect()
    rows = conn.execute(
        """SELECT d.publisher, LOWER(TRIM(d.title)) FROM datasets d
           WHERE d.publisher IS NOT NULL AND d.title IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
             AND NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)"""
    ).fetchall()
    conn.close()

    # "(none)" is the harvester's own placeholder for a record that named
    # nobody. It is not an organisation and must not be a star.
    rows = [(p, t) for p, t in rows
            if p.strip().lower() not in ("(none)", "none", "unknown", "n/a")]
    counts = collections.Counter(p for p, _ in rows)
    by_title = collections.defaultdict(set)
    for pub, title in rows:
        by_title[re.sub(r"[^a-z0-9]+", " ", title).strip()].add(pub)

    pairs: collections.Counter = collections.Counter()
    for title, pubs in by_title.items():
        if not 2 <= len(pubs) <= MAX_SPREAD:
            continue
        for a, b in itertools.combinations(sorted(pubs), 2):
            pairs[(a, b)] += 1

    edges_raw = {k: v for k, v in pairs.items() if v >= MIN_SHARED}
    names = sorted({x for pair in edges_raw for x in pair})
    index = {n: i for i, n in enumerate(names)}
    nodes = [{"name": n, "datasets": counts[n], "sector": sector(n)}
             for n in names]
    edges = [(index[a], index[b], w) for (a, b), w in edges_raw.items()]
    return nodes, edges


def layout(nodes: list[dict], edges: list[tuple[int, int, int]]) -> np.ndarray:
    """A 3D force layout: edges pull, everything pushes, the centre holds.

    Plain O(n^2) repulsion. At a few hundred nodes that is a 336x336x3
    array per step, which numpy does in microseconds — the approximations a
    bigger graph would need would only make this one less faithful.
    """
    rng = np.random.default_rng(20260902)   # a fixed constellation, not a new one nightly
    n = len(nodes)
    pos = rng.normal(0, 1, (n, 3))
    src = np.array([e[0] for e in edges])
    dst = np.array([e[1] for e in edges])
    weight = np.array([e[2] for e in edges], dtype=float)
    weight = np.clip(weight, 0, 12) / 12.0
    mass = np.array([max(x["datasets"], 1) for x in nodes], dtype=float)
    mass = 0.5 + np.log1p(mass) / np.log1p(mass).max()

    for step in range(ITERATIONS):
        cool = 1.0 - step / ITERATIONS
        delta = pos[:, None, :] - pos[None, :, :]
        dist2 = (delta ** 2).sum(-1) + 0.05
        push = (delta / dist2[..., None]).sum(1) * 0.9
        force = push * mass[:, None]

        seg = pos[dst] - pos[src]
        pull = seg * weight[:, None] * 0.012
        np.add.at(force, src, pull)
        np.add.at(force, dst, -pull)

        force -= pos * 0.006                 # gravity, or the graph drifts apart
        pos += np.clip(force, -1.5, 1.5) * (0.35 * cool + 0.02)

    pos -= pos.mean(0)
    pos /= np.abs(pos).max()
    return pos


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>The constellation — Joined Up workshop</title>
<link rel="stylesheet" href="/site.css">
<style>
  .stage { position: relative; background: var(--card); border: 1px solid var(--line);
           border-radius: var(--radius); overflow: hidden; touch-action: none; }
  .stage canvas { display: block; width: 100%; height: auto; cursor: grab; }
  .stage canvas:active { cursor: grabbing; }
  .tip { position: absolute; pointer-events: none; background: var(--card);
         border: 1px solid var(--line-strong); border-radius: var(--radius-sm);
         padding: .35rem .55rem; font-size: .8rem; opacity: 0; transition: opacity .12s;
         max-width: 16rem; box-shadow: 0 2px 10px rgba(0,0,0,.12); }
  .key { display: flex; flex-wrap: wrap; gap: .1rem 1rem; margin: .7rem 0 0;
         font-size: .8rem; color: var(--muted); }
  .key b { display: inline-block; width: .6rem; height: .6rem; border-radius: 50%;
           margin-right: .3rem; }
  .ctl { display: flex; gap: .8rem; align-items: center; margin: .8rem 0 0;
         font-size: .85rem; flex-wrap: wrap; }
</style>
</head><body><div class="wrap wide">
<h1>The constellation</h1>
<p class="lede">__LEDE__</p>

<div class="stage" id="stage">
  <canvas id="c" width="1600" height="1000"></canvas>
  <div class="tip" id="tip"></div>
</div>
<div class="ctl">
  <label><input type="checkbox" id="spin" checked> rotate</label>
  <label>links <input type="range" id="thresh" min="2" max="12" value="2"></label>
  <span class="note" id="stat"></span>
</div>
<div class="key" id="key"></div>

<p class="note" style="margin-top:1.4rem">
How it was measured: every dataset in the index that is not a collapsed
duplicate or a retired record, grouped by normalised title. Two bodies are
joined when they each publish __MIN__ or more datasets of the same name.
Titles shared by more than __SPREAD__ bodies are excluded from the joining —
"spend over £500" is published by nearly everyone, and a link that says
everything is connected to everything is true and useless. Layout is a 3D
force simulation computed once from a fixed seed, so this is the same
constellation every time. Joined Up · open-data.org.uk</p>
</div>
<script>
const DATA = __DATA__;
const COLOURS = {council:"#0e6e63", health:"#a4192b", government:"#14549c",
                 agency:"#7a5c00", research:"#6b3fa0", other:"#61656d"};
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const tip = document.getElementById('tip'), stage = document.getElementById('stage');
let rx = -0.35, ry = 0.6, drag = null, hover = -1, thresh = 2;

const R = Math.max(...DATA.nodes.map(n => n.datasets));
const rad = n => 2.2 + 7 * Math.sqrt(n.datasets / R);

function project() {
  const cosX = Math.cos(rx), sinX = Math.sin(rx);
  const cosY = Math.cos(ry), sinY = Math.sin(ry);
  const s = Math.min(cv.width, cv.height) * 0.40;
  return DATA.pos.map(([x, y, z]) => {
    let x1 = x * cosY + z * sinY, z1 = -x * sinY + z * cosY;
    let y1 = y * cosX - z1 * sinX; z1 = y * sinX + z1 * cosX;
    // Perspective: nearer nodes are bigger and brighter, which is the whole
    // reason this reads as depth rather than as a flat scatter.
    const k = 1 / (2.6 - z1 * 0.9);
    return [cv.width / 2 + x1 * s * k * 2.2, cv.height / 2 + y1 * s * k * 2.2, k];
  });
}

function draw() {
  const p = project();
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.lineWidth = 1;
  for (const [a, b, w] of DATA.edges) {
    if (w < thresh) continue;
    const near = (p[a][2] + p[b][2]) / 2;
    const lit = hover === a || hover === b;
    ctx.strokeStyle = lit ? "rgba(14,110,99,.85)"
                          : `rgba(120,128,136,${(0.05 + near * 0.16).toFixed(3)})`;
    ctx.beginPath(); ctx.moveTo(p[a][0], p[a][1]); ctx.lineTo(p[b][0], p[b][1]); ctx.stroke();
  }
  const order = p.map((q, i) => i).sort((i, j) => p[i][2] - p[j][2]);
  for (const i of order) {
    const n = DATA.nodes[i], [x, y, k] = p[i];
    ctx.globalAlpha = hover === -1 ? 0.35 + k * 0.65 : (hover === i ? 1 : 0.25);
    ctx.fillStyle = COLOURS[n.sector] || COLOURS.other;
    ctx.beginPath(); ctx.arc(x, y, rad(n) * k * 1.5, 0, 6.284); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function pick(mx, my) {
  const p = project();
  let best = -1, bestD = 26;
  for (let i = 0; i < p.length; i++) {
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
    ry += (e.clientX - drag[0]) * 0.008; rx += (e.clientY - drag[1]) * 0.008;
    drag = [e.clientX, e.clientY]; draw(); return;
  }
  const i = pick(mx, my);
  if (i !== hover) { hover = i; draw(); }
  if (i >= 0) {
    const n = DATA.nodes[i];
    const links = DATA.edges.filter(e2 => (e2[0] === i || e2[1] === i) && e2[2] >= thresh).length;
    tip.innerHTML = '<b>' + n.name + '</b><br>' + n.datasets.toLocaleString() +
      ' datasets · ' + links + ' bodies publish the same things';
    tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX - r.left + 12, r.width - 200) + 'px';
    tip.style.top = (e.clientY - r.top + 12) + 'px';
  } else { tip.style.opacity = 0; }
});
cv.addEventListener('click', () => {
  if (hover >= 0) window.open('/publisher?name=' +
    encodeURIComponent(DATA.nodes[hover].name), '_blank');
});
document.getElementById('thresh').addEventListener('input', e => {
  thresh = +e.target.value; stat(); draw();
});
function stat() {
  const e = DATA.edges.filter(x => x[2] >= thresh).length;
  document.getElementById('stat').textContent =
    e.toLocaleString() + ' connections at ' + thresh + '+ shared datasets';
}
document.getElementById('key').innerHTML = Object.entries(COLOURS)
  .map(([k, v]) => '<span><b style="background:' + v + '"></b>' + k + '</span>').join('');
let spinning = true;
document.getElementById('spin').addEventListener('change', e => spinning = e.target.checked);
(function tick() {
  if (spinning && !drag) { ry += 0.0016; draw(); }
  requestAnimationFrame(tick);
})();
stat(); draw();
</script>
</body></html>
"""


def main() -> int:
    nodes, edges = build_graph()
    pos = layout(nodes, edges)
    data = {"nodes": nodes,
            "edges": [[a, b, w] for a, b, w in edges],
            "pos": [[round(v, 4) for v in p] for p in pos]}

    counts = collections.Counter(n["sector"] for n in nodes)
    top = max(nodes, key=lambda n: sum(
        1 for e in edges if nodes[e[0]] is n or nodes[e[1]] is n))
    lede = (
        f"{len(nodes):,} UK public bodies, joined wherever two of them publish "
        f"{MIN_SHARED} or more datasets of the same name. {len(edges):,} such "
        "connections. Nobody can see this from inside a portal, because each "
        "portal only knows its own records — the duplication between them is "
        "invisible by construction. Drag to turn it, hover for a name, click "
        "to open that body's datasets. "
        + ", ".join(f"{v} {k}" for k, v in counts.most_common()) + ".")

    page = (PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
                .replace("__LEDE__", lede)
                .replace("__MIN__", str(MIN_SHARED))
                .replace("__SPREAD__", str(MAX_SPREAD)))
    OUT.write_text(page, encoding="utf-8")
    print(f"{len(nodes):,} publishers, {len(edges):,} connections")
    print("sectors:", dict(counts))
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
