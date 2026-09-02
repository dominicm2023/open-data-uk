"""The state from the top down, as an icicle you can drill into.

This started in three dimensions and should not have. The z axis carried
hierarchy depth, which the layout already showed, so the third dimension
added occlusion and an unstable viewpoint in exchange for no information.
Every rotation gave a different picture and none of them could be compared.

Flat, top to bottom, is the honest shape for a hierarchy: the top of
government on the first row, departments beneath it, and every reporting
layer below that, each block as wide as what sits under it. Nothing hides
behind anything. Clicking a block descends into it and the trail along the
top walks back out, so six thousand posts stay navigable without ever
showing six thousand things at once.

Two measures, because they answer different questions. Sized by posts, a
block is as wide as the number of people beneath it. Sized by salary, it is
as wide as the pay bill beneath it — and those two pictures are not the
same shape, which is the interesting part.

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
from cascade import load  # noqa: E402

OUT = ROOT / "cascade.html"
MAXDEPTH = 4          # rows shown before a click is needed to go deeper


def figure(nodes: list[dict], bodies: list[str]) -> tuple[go.Figure, dict]:
    kids = collections.defaultdict(list)
    for i, n in enumerate(nodes):
        if i:
            kids[n["p"]].append(i)

    # What sits beneath each post, counted once. An icicle divides a parent
    # among its children, so a parent's own value must be the sum of the
    # branch or the arithmetic stops meaning anything.
    below_posts = [0] * len(nodes)
    below_pay = [0] * len(nodes)
    order = []
    stack = [0]
    while stack:
        i = stack.pop()
        order.append(i)
        stack.extend(kids[i])
    for i in reversed(order):
        below_posts[i] = 1 + sum(below_posts[k] for k in kids[i])
        below_pay[i] = (nodes[i]["f"] or 0) + sum(below_pay[k] for k in kids[i])

    ids, parents, labels, hover, count_v, pay_v = [], [], [], [], [], []
    for i, n in enumerate(nodes):
        ids.append(str(i))
        parents.append("" if i == 0 else str(n["p"]))
        body = bodies[n["b"]] if n["b"] >= 0 else "all bodies"
        label = n["t"] if i else "The top of government"
        labels.append(label)
        pay = f"<br>pay from £{n['f']:,}" if n["f"] else ""
        cost = (f"<br>£{n['c']:,} of salary reports to it" if n["c"] else "")
        hover.append(
            f"<b>{label}</b><br>{body}"
            + (f"<br>{n['g']}" if n["g"] else "") + pay + cost
            + f"<br>{below_posts[i] - 1:,} posts below this one"
            + (f"<br>£{below_pay[i]:,} of published pay below it"
               if below_pay[i] else ""))
        count_v.append(below_posts[i])
        pay_v.append(below_pay[i])

    common = dict(ids=ids, parents=parents, labels=labels,
                  customdata=hover, hovertemplate="%{customdata}<extra></extra>",
                  maxdepth=MAXDEPTH, branchvalues="total",
                  tiling=dict(orientation="v"),
                  marker=dict(colorscale="Teal", line=dict(width=1,
                                                           color="#0b0e11")))

    fig = go.Figure()
    fig.add_trace(go.Icicle(values=count_v, visible=True,
                            marker_colors=None, **common))
    fig.add_trace(go.Icicle(values=pay_v, visible=False,
                            marker_colors=None, **common))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0b0e11",
        margin=dict(l=0, r=0, t=4, b=0), height=760,
        hoverlabel=dict(bgcolor="#16181c", font_size=12),
        updatemenus=[dict(
            type="buttons", direction="right", x=0, y=1.06,
            xanchor="left", yanchor="bottom", showactive=True,
            bgcolor="#16181c", bordercolor="#3c4048", font=dict(size=12),
            buttons=[
                dict(label="width = posts beneath", method="update",
                     args=[{"visible": [True, False]}]),
                dict(label="width = published pay beneath", method="update",
                     args=[{"visible": [False, True]}]),
            ])])
    stats = {"posts": len(nodes) - 1,
             "no_pay": sum(1 for n in nodes[1:] if not n["f"]),
             "widest": max(range(1, len(nodes)), key=lambda i: below_posts[i]),
             "below": below_posts, "pay": below_pay}
    return fig, stats


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
Click any block to descend into it; the trail along the top walks back out.
Four layers show at a time, which is what keeps six thousand posts
navigable.</p>
<p class="note">
How it was measured: the latest organogram each body published from 2024 on.
One block per senior post, nested under the post it reports to, as
published. A block is as wide as what sits beneath it — either the number
of posts, or the published pay, whichever the buttons select. <b>__NOPAY__
of __TOTAL__ posts publish no pay at all</b>, so the pay view is a map of
what is disclosed rather than of what is spent, and the two views are
deliberately different shapes. <b>The top row is ours</b>: no published file
joins the departments, and organograms record civil servants rather than
ministers, so it holds them together and claims nothing about who reports
to whom. Joined Up · open-data.org.uk</p>
</div></body></html>
"""


def main() -> int:
    nodes, bodies = load()
    fig, stats = figure(nodes, bodies)
    widest = nodes[stats["widest"]]
    lede = (
        f"{stats['posts']:,} senior posts from {len(bodies)} public bodies, "
        "nested as published: the top of government on the first row, each "
        "department beneath it, every reporting layer below that. The widest "
        f"branch is {widest['t']} at {bodies[widest['b']]}, with "
        f"{stats['below'][stats['widest']] - 1:,} posts under it. Click to "
        "go down; the buttons switch between counting posts and counting pay.")
    html = fig.to_html(full_html=False, include_plotlyjs=True,
                       config={"displaylogo": False})
    OUT.write_text(
        TEMPLATE.replace("__FIG__", html).replace("__LEDE__", lede)
                .replace("__NOPAY__", f"{stats['no_pay']:,}")
                .replace("__TOTAL__", f"{stats['posts']:,}"),
        encoding="utf-8")
    print(f"{stats['posts']:,} posts, {len(bodies)} bodies, "
          f"{stats['no_pay']:,} publish no pay")
    print(f"widest branch: {widest['t']} "
          f"({stats['below'][stats['widest']] - 1:,} beneath)")
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
