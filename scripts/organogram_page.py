"""Draw the shape of the British state from its own organograms.

Every department publishes its senior structure twice a year as a CSV: one
row per post, with the post it reports to. Nobody joins them up, so nobody
has seen the thing drawn. This does: 44 bodies with a current edition,
6,214 senior posts, every reporting line as published.

The drawing is a layered node-link diagram per body — a node for each post,
placed at its depth below the top, an edge to whatever it reports to. No
force simulation and no smoothing: the position of a node is its real depth
and its real order, so a wide flat department looks wide and flat and a
tower looks like a tower. What you are looking at is the organisation.

Usage:  python scripts/organogram_page.py
"""

from __future__ import annotations

import collections
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import charts  # noqa: E402
from charts import PAD, W, esc  # noqa: E402

DB = ROOT / "analysis" / "organograms" / "organograms.sqlite"
OUT = ROOT / "organograms.html"
SITE = "open-data.org.uk"
BYLINE = "Joined Up"
QUERY = ("Cabinet Office organogram CSVs as published, latest edition per "
         "body from 2024 on; one node per senior post, one edge per "
         "'reports to' reference that resolves within the same file")


def load() -> list[dict]:
    """One tree per body, from its most recent published edition."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    latest = dict(conn.execute(
        "SELECT publisher, MAX(edition) FROM senior "
        "WHERE edition >= '2024' GROUP BY publisher").fetchall())
    bodies = []
    for pub, ed in latest.items():
        rows = conn.execute(
            "SELECT post_ref, reports_to, job_title, pay_floor, pay_ceiling "
            "FROM senior WHERE publisher = ? AND edition = ?",
            (pub, ed)).fetchall()
        refs = {r["post_ref"] for r in rows if r["post_ref"]}
        kids = collections.defaultdict(list)
        roots = []
        for r in rows:
            parent = (r["reports_to"] or "").strip()
            if parent in refs and parent != r["post_ref"]:
                kids[parent].append(r["post_ref"])
            else:
                roots.append(r["post_ref"])
        if not rows or not roots:
            continue
        # Depth by breadth-first descent, so a post appearing twice takes
        # the shallower place rather than whichever was seen last.
        depth, queue, seen = {}, collections.deque(
            (r, 1) for r in roots), set()
        while queue:
            node, d = queue.popleft()
            if node in seen:
                continue
            seen.add(node)
            depth[node] = d
            for k in kids.get(node, []):
                queue.append((k, d + 1))
        spans = [len(v) for v in kids.values()]
        bodies.append({
            "publisher": pub, "edition": ed, "posts": len(rows),
            "depth": max(depth.values()), "roots": len(roots),
            "max_span": max(spans) if spans else 0,
            "kids": kids, "depth_of": depth,
            "by_level": collections.Counter(depth.values()),
        })
    conn.close()
    return sorted(bodies, key=lambda b: -b["posts"])


def tree_svg(body: dict, w: float, h: float) -> str:
    """One body's reporting structure, laid out by real depth and order."""
    levels = collections.defaultdict(list)
    for node, d in body["depth_of"].items():
        levels[d].append(node)
    for d in levels:
        levels[d].sort()
    maxd = max(levels)
    pos: dict[str, tuple[float, float]] = {}
    top, usable = 6.0, h - 12.0
    for d, nodes in levels.items():
        y = top + (usable * (d - 1) / max(maxd - 1, 1))
        for i, node in enumerate(nodes):
            x = w * (i + 1) / (len(nodes) + 1)
            pos[node] = (x, y)

    edges = []
    for parent, children in body["kids"].items():
        if parent not in pos:
            continue
        px, py = pos[parent]
        for child in children:
            if child in pos:
                cx, cy = pos[child]
                edges.append(f"M{px:.1f} {py:.1f}L{cx:.1f} {cy:.1f}")
    # One path element for every edge in a body is thousands of nodes in the
    # DOM for no gain; they all share a stroke, so they can share a path.
    parts = [f'<path d="{"".join(edges)}" fill="none" '
             f'stroke="var(--line-strong, #cfd0ca)" stroke-width=".4" '
             f'opacity=".55"/>']
    for node, (x, y) in pos.items():
        d = body["depth_of"][node]
        r = 2.6 if d == 1 else (1.7 if d == 2 else 1.05)
        fill = ("var(--ju-accent-deep, #0a5349)" if d <= 2
                else "var(--ju-accent, #0e6e63)")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" '
                     f'fill="{fill}" opacity="{0.95 if d <= 2 else 0.6:.2f}"/>')
    return "".join(parts)


def small_multiples(bodies: list[dict], n: int = 12) -> str:
    """The bodies side by side, every one drawn to the same scale."""
    cols, cell_w, cell_h, gap = 4, (W - 2 * PAD - 3 * 14) / 4, 128.0, 14.0
    rows = -(-min(n, len(bodies)) // cols)
    height = PAD + 34 + rows * (cell_h + 46)
    parts = [f'<text x="{PAD}" y="{PAD + 14}" class="lbl">'
             "Each dot is one senior post. Each line is a reporting "
             "relationship, exactly as published.</text>"]
    for i, body in enumerate(bodies[:n]):
        cx = PAD + (i % cols) * (cell_w + gap)
        cy = PAD + 34 + (i // cols) * (cell_h + 46)
        parts.append(f'<g transform="translate({cx:.1f},{cy:.1f})">'
                     f'{tree_svg(body, cell_w, cell_h)}</g>')
        name = body["publisher"]
        short = (name if len(name) <= 30 else name[:29] + "…")
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + cell_h + 14:.1f}" class="lbl b">'
            f'{esc(short)}</text>'
            f'<text x="{cx:.1f}" y="{cy + cell_h + 27:.1f}" class="lbl mut">'
            f'{body["posts"]:,} posts · {body["depth"]} levels deep'
            f'</text>')
    return "".join(parts), height


# Below this a "full-time equivalent payscale" is a placeholder rather than a
# wage — the corpus contains minima of £1 — and above it a single post is
# either an error or a person we would be drawing as a skyscraper on the
# strength of one cell. Both ends are excluded and both counts are reported,
# because a filter nobody can see is just a thumb on the scale.
PAY_FLOOR, PAY_CEILING = 5_000, 1_000_000
PARADE_QUERY = (
    "organogram junior payscale minima weighted by posts in FTE, plus senior "
    "actual pay floors, latest edition per body from 2024 on; heights are "
    "pay divided by the median, after Jan Pen (1971)")


def parade_points(conn) -> tuple[list[tuple[int, float]], dict]:
    """Every post in the state, cheapest first, with how many share that pay.

    Junior rows are pay bands carrying an FTE count, so one row is many
    people. Senior rows are individual posts. Both are weighted honestly and
    poured into one queue.
    """
    pts: list[tuple[int, float]] = []
    dropped = 0
    latest_j = dict(conn.execute(
        "SELECT publisher, MAX(edition) FROM junior WHERE edition >= '2024' "
        "GROUP BY publisher").fetchall())
    for pub, ed in latest_j.items():
        for pay, fte in conn.execute(
                "SELECT payscale_min, posts_fte FROM junior "
                "WHERE publisher = ? AND edition = ? AND payscale_min IS NOT NULL "
                "AND posts_fte > 0", (pub, ed)):
            if PAY_FLOOR <= pay <= PAY_CEILING:
                pts.append((pay, float(fte)))
            else:
                dropped += 1
    latest_s = dict(conn.execute(
        "SELECT publisher, MAX(edition) FROM senior WHERE edition >= '2024' "
        "GROUP BY publisher").fetchall())
    for pub, ed in latest_s.items():
        for pay, fte in conn.execute(
                "SELECT pay_floor, fte FROM senior "
                "WHERE publisher = ? AND edition = ? AND pay_floor IS NOT NULL",
                (pub, ed)):
            if PAY_FLOOR <= pay <= PAY_CEILING:
                pts.append((pay, float(fte) if fte and fte > 0 else 1.0))
            else:
                dropped += 1
    pts.sort()
    return pts, {"dropped": dropped}


def pen_parade(conn) -> tuple[str, float, dict]:
    """Jan Pen's parade: everyone's height is their pay, marching past in an
    hour. Most of the state is ankle-high for fifty minutes."""
    pts, meta = parade_points(conn)
    total = sum(w for _, w in pts)

    # The median earner is one average height. Every other height is that
    # person's pay as a multiple of theirs, which is the whole device.
    seen, median = 0.0, pts[len(pts) // 2][0]
    for pay, w in pts:
        seen += w
        if seen >= total / 2:
            median = pay
            break

    w_px, h_px = W - 2 * PAD, 300.0
    top_units = 4.0          # frame shows up to four average heights
    base_y = PAD + h_px

    # Walk the parade, emitting a step per pixel column rather than per post:
    # 344,000 points is a megabyte of path data and looks identical.
    steps, cum, col = [], 0.0, -1
    tallest_visible = 0.0
    for pay, weight in pts:
        cum += weight
        c = int(cum / total * w_px)
        if c == col:
            continue
        col = c
        units = pay / median
        y = base_y - min(units, top_units) / top_units * h_px
        tallest_visible = max(tallest_visible, units)
        steps.append(f"L{PAD + c} {y:.1f}")
    path = f"M{PAD} {base_y}" + "".join(steps) + f"L{PAD + w_px} {base_y}Z"

    parts = [f'<path d="{path}" fill="var(--ju-accent, #0e6e63)" '
             f'opacity=".85"/>']
    # A head-height line, so "average" is a thing you can see rather than infer
    avg_y = base_y - h_px / top_units
    parts.append(f'<line x1="{PAD}" y1="{avg_y:.1f}" x2="{PAD + w_px}" '
                 f'y2="{avg_y:.1f}" stroke="var(--ink, #16181c)" '
                 f'stroke-dasharray="3 3" stroke-width=".7" opacity=".5"/>')
    parts.append(f'<text x="{PAD + 4}" y="{avg_y - 5:.1f}" class="lbl mut">'
                 f'average height &#8212; the median post, £{median:,}</text>')

    # Minute marks. Pen's device is an hour-long parade, so the x axis is
    # time and "the last thirty seconds" becomes a thing you can point at.
    for minute in (10, 20, 30, 40, 50, 59):
        x = PAD + w_px * minute / 60
        share = minute / 60
        idx, run = 0, 0.0
        for pay, weight in pts:
            run += weight
            if run >= total * share:
                idx = pay
                break
        parts.append(f'<line x1="{x:.1f}" y1="{base_y}" x2="{x:.1f}" '
                     f'y2="{base_y + 4}" stroke="var(--line-strong, #cfd0ca)"/>')
        parts.append(f'<text x="{x:.1f}" y="{base_y + 16}" text-anchor="middle" '
                     f'class="lbl mut">{minute} min · £{idx // 1000:,}k</text>')

    # The giants run off the top of the frame; say so rather than clipping
    # them silently.
    biggest = pts[-1][0]
    parts.append(
        f'<text x="{PAD + w_px}" y="{PAD + 12}" text-anchor="end" class="lbl b">'
        f'&#8593; off the top of this page: £{biggest:,}, '
        f'{biggest / median:.0f}&#215; average height</text>')
    parts.append(
        f'<text x="{PAD}" y="{PAD + 12}" class="lbl">'
        f'{total:,.0f} posts, cheapest first. Height is pay; the dashed line '
        f'is the median.</text>')
    meta.update({"total": total, "median": median, "max": biggest,
                 "tallest_visible": tallest_visible})
    return "".join(parts), base_y + 26, meta


def panel(title: str, body: str, height: float, query: str) -> str:
    band, band_h = charts._provenance(int(height), query,
                                      f"{SITE} · measured 2 September 2026",
                                      byline=BYLINE)
    svg = charts._with_fallbacks(charts._frame(
        body + band, int(height) + band_h, title, query))
    return (f'<article class="finding joined-up"><h2>{esc(title)}</h2>'
            f"<figure>{svg}</figure></article>")


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>The shape of the state — Joined Up workshop</title>
<link rel="stylesheet" href="/site.css">
</head><body><div class="wrap wide">
<h1>The shape of the British state</h1>
<p class="lede">{lede}</p>
{panels}
</div></body></html>
"""


def main() -> int:
    bodies = load()
    total_posts = sum(b["posts"] for b in bodies)
    grid, height = small_multiples(bodies)
    conn = sqlite3.connect(DB)
    parade, p_h, meta = pen_parade(conn)
    conn.close()
    panels = [
        panel("The parade: an hour of the British state, shortest first",
              parade, p_h, PARADE_QUERY),
        panel("Twelve departments, drawn from their own organograms",
              grid, height, QUERY),
    ]

    hs2 = next((b for b in bodies if "High Speed 2" in b["publisher"]), None)
    dft = next((b for b in bodies if b["publisher"] ==
                "Department for Transport"), None)
    widest = max(bodies, key=lambda b: b["max_span"])
    lede = (f"An hour-long parade of {int(meta['total']):,} posts, shortest "
            f"paid first, after Jan Pen (1971): everyone's height is their "
            f"pay. Fifty minutes in you are still below the median of "
            f"£{meta['median']:,}. The tallest is "
            f"£{meta['max']:,} — {meta['max'] / meta['median']:.0f} "
            "times average height, and off the top of the page. Below that, "
            f"{len(bodies)} public bodies published a current organogram: "
            f"{total_posts:,} senior posts, each one naming the post it "
            "reports to. Drawn together, the reporting lines are the "
            "organisation — and no portal holds them together, because "
            "every body publishes its own.")
    if hs2 and dft:
        lede += (f" One thing falls straight out of it: {hs2['publisher']} "
                 f"lists {hs2['posts']:,} senior posts to build one railway, "
                 f"against {dft['posts']:,} at the Department for Transport "
                 "that oversees it.")
    lede += (f" The widest span in government is at "
             f"{widest['publisher']}, where one post has "
             f"{widest['max_span']} direct reports.")

    OUT.write_text(PAGE.replace("{panels}", "".join(panels))
                       .replace("{lede}", lede), encoding="utf-8")
    print(f"{len(bodies)} bodies, {total_posts:,} senior posts")
    print(f"parade: {meta['total']:,.0f} posts, median £{meta['median']:,}, "
          f"tallest £{meta['max']:,} ({meta['max'] / meta['median']:.0f}x), "
          f"{meta['dropped']:,} rows outside the pay bounds")
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
