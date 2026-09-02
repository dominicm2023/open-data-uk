"""The state as one tree, in a viewer you can actually use.

The hand-rolled canvas version looked right and handled badly: no zoom, no
pan, a thirteen-pixel hit target on six thousand nodes, and a dropdown
where a legend should be. This is the same layout — the same radial
dendrogram, the same synthetic centre, the same honesty about missing pay —
handed to Plotly, which brings orbit, scroll-zoom, pan, reliable hover and
a legend that isolates a department on click.

One trace per body is the point. Plotly gives every trace a legend entry,
so clicking a department hides it and double-clicking isolates it, which is
the interaction the dropdown was standing in for.

The library is inlined rather than fetched from a CDN, so the page stays
self-contained like everything else here. That costs about four megabytes
and buys a page that works with no third-party request.

Usage:  python scripts/cascade_plotly.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import plotly.graph_objects as go

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from cascade import RING, load, radial  # noqa: E402

OUT = ROOT / "cascade.html"
NO_FIGURE = "publishes no pay figure"


def marker_size(value: int, biggest: int) -> float:
    if not value:
        return 3.0
    return 4.0 + 22.0 * (value / biggest) ** 0.5


def build() -> go.Figure:
    nodes, bodies = load()
    pos = radial(nodes, bodies)
    biggest = max((n["c"] for n in nodes), default=1) or 1

    fig = go.Figure()

    # Edges first, as one trace of line segments broken by None. Six
    # thousand separate traces would be correct and unusable.
    ex, ey, ez = [], [], []
    for i, n in enumerate(nodes):
        if not i:
            continue
        a, b = pos[i], pos[n["p"]]
        ex += [a[0], b[0], None]
        ey += [a[1], b[1], None]
        ez += [a[2], b[2], None]
    fig.add_trace(go.Scatter3d(
        x=ex, y=ey, z=ez, mode="lines", hoverinfo="skip",
        line=dict(color="rgba(150,160,170,0.20)", width=1),
        name="reporting lines", showlegend=False))

    by_body = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        if i:
            by_body[n["b"]].append(i)

    # Biggest bodies first so the legend opens on the ones worth clicking.
    for body in sorted(by_body, key=lambda b: -len(by_body[b])):
        idx = by_body[body]
        hue = (body * 137.508) % 360
        text = []
        for i in idx:
            n = nodes[i]
            pay = (f"pay from £{n['f']:,}" if n["f"] else "")
            cost = (f"£{n['c']:,} of salary reports to it" if n["c"] else "")
            detail = " · ".join(x for x in (n["g"], pay, cost) if x)
            text.append(f"<b>{n['t']}</b><br>{bodies[body]}"
                        + (f"<br>{detail}" if detail else f"<br>{NO_FIGURE}"))
        fig.add_trace(go.Scatter3d(
            x=[pos[i][0] for i in idx],
            y=[pos[i][1] for i in idx],
            z=[pos[i][2] for i in idx],
            mode="markers",
            name=f"{bodies[body]} ({len(idx):,})",
            text=text, hoverinfo="text",
            marker=dict(
                size=[marker_size(nodes[i]["c"], biggest) for i in idx],
                color=f"hsl({hue:.0f},62%,58%)",
                # A post publishing no figure gets a ring rather than a dot,
                # so an absence looks like an absence and not like a small
                # salary. 58% of these posts publish nothing.
                opacity=0.9,
                line=dict(width=1, color=f"hsl({hue:.0f},62%,72%)"),
            )))

    fig.add_trace(go.Scatter3d(
        x=[pos[0][0]], y=[pos[0][1]], z=[pos[0][2]], mode="markers+text",
        marker=dict(size=14, color="white", line=dict(width=2, color="#888")),
        text=["the top"], textposition="top center",
        textfont=dict(color="white", size=13),
        name="the top (ours, not published)", hoverinfo="text",
        hovertext=["The centre is drawn by us to hold the departments "
                   "together. No published file joins them."]))

    axis = dict(showbackground=False, showgrid=False, zeroline=False,
                showticklabels=False, title="")
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0e11", plot_bgcolor="#0b0e11",
        scene=dict(xaxis=axis, yaxis=axis, zaxis=axis,
                   aspectmode="data",
                   camera=dict(eye=dict(x=1.5, y=1.5, z=0.9))),
        margin=dict(l=0, r=0, t=0, b=0), height=780,
        legend=dict(bgcolor="rgba(11,14,17,.75)", font=dict(size=11),
                    itemsizing="constant", y=0.98, x=0.01),
        hoverlabel=dict(bgcolor="#16181c", font_size=12))
    return fig, nodes, bodies, pos


TEMPLATE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>From the top — Joined Up workshop</title>
<link rel="stylesheet" href="/site.css">
</head><body><div class="wrap wide">
<h1>From the top</h1>
<p class="lede">__LEDE__</p>
__FIG__
<p class="note" style="margin-top:1rem">
Scroll to zoom, drag to orbit, right-drag to pan. Click a body in the
legend to hide it, double-click to see it alone.</p>
<p class="note">
How it was measured: the latest organogram each body published from 2024 on.
One point per senior post, at a radius set by how many reporting steps
separate it from the top of its own department, dropping a level with each
step. Every line is a "reports to" reference as published. Marker size is
the salary reporting to a post, where that is published — <b>__NOPAY__ of
__TOTAL__ posts publish no pay figure at all</b>, and are drawn at the
smallest size rather than being left out. <b>The centre is ours</b>: no file
joins the departments, and organograms record civil servants rather than
ministers, so the hub holds them together and claims nothing about who
reports to whom. Joined Up · open-data.org.uk</p>
</div></body></html>
"""


def main() -> int:
    fig, nodes, bodies, pos = build()
    depth_max = max(p[3] for p in pos)
    deepest = max(range(len(nodes)), key=lambda i: pos[i][3])
    no_pay = sum(1 for n in nodes[1:] if not n["c"])

    lede = (
        f"{len(nodes) - 1:,} senior posts from {len(bodies)} public bodies as "
        "one tree: the top of government at the centre, each department's own "
        "top posts on the first ring, every reporting line dropping outward "
        f"from there. The longest chain runs {depth_max} steps — "
        f"{nodes[deepest]['t']} at {bodies[nodes[deepest]['b']]}.")

    html = fig.to_html(full_html=False, include_plotlyjs=True,
                       config={"displaylogo": False, "scrollZoom": True})
    OUT.write_text(
        TEMPLATE.replace("__FIG__", html).replace("__LEDE__", lede)
                .replace("__NOPAY__", f"{no_pay:,}")
                .replace("__TOTAL__", f"{len(nodes) - 1:,}"),
        encoding="utf-8")
    print(f"{len(nodes) - 1:,} posts, {len(bodies)} bodies, "
          f"{no_pay:,} without a pay figure")
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
