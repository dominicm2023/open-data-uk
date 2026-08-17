"""Draw findings as SVG, in whichever brand's livery is publishing.

Charts are generated from findings.json, never drawn by hand — there will be
hundreds of them and they change every night as the index grows.

Two decisions worth knowing about:

**The provenance band is inside the SVG, not in HTML beside it.** These
graphics exist to be screenshotted and reposted with the context stripped
off. A footer that lives in the surrounding page is gone the moment anyone
saves the image, which is exactly when it matters most. Baked in, the claim
travels with the query that produced it.

**Colours are CSS custom properties, not literals.** The site is theme-aware
and an inline SVG inherits the page's tokens, so one chart is correct in both
modes. It also means a chart inside `.joined-up` re-liveries itself with no
code path of its own — the brand is a class on an ancestor.

The cost of that choice: an SVG saved to a file loses the variables, since
nothing defines them any more. `standalone()` resolves them to literals for
that case, and is what any future PNG export should go through.
"""

from __future__ import annotations

from html import escape

W = 720                  # viewBox width; height varies by chart
PAD = 28
BAND = 74                # provenance band
ROW = 30                 # one horizontal bar
LABEL_W = 232

# Resolved values for standalone files, where CSS variables mean nothing.
# Light-mode tokens: a saved graphic has no page to ask about the theme, and
# guessing dark would be the wrong default for an emailed attachment.
LITERALS = {
    "--card": "#ffffff", "--ink": "#16181c", "--muted": "#61656d",
    "--line": "#e3e3de", "--line-strong": "#cfd0ca",
    "--accent": "#14549c", "--accent-soft": "#e8f0f9", "--on-accent": "#ffffff",
    "--ok": "#0a6b45", "--warn": "#a4192b", "--amber": "#7a5c00",
    "--chart-grid": "#e3e3de", "--chart-baseline": "#cfd0ca",
    "--chart-label": "#61656d", "--chart-value": "#16181c",
    "--cat-1": "#14549c", "--cat-2": "#61656d", "--cat-3": "#7a5c00",
    "--cat-4": "#a4192b", "--cat-5": "#0a6b45",
    "--seq-1": "#dce8f6", "--seq-2": "#abc6e6", "--seq-3": "#7099cb",
    "--seq-4": "#3d72ad", "--seq-5": "#14549c",
    "--on-seq-1": "#16181c", "--on-seq-2": "#16181c", "--on-seq-3": "#16181c",
    "--on-seq-4": "#ffffff", "--on-seq-5": "#ffffff",
    "--land": "#eceae4", "--land-edge": "#cfd0ca",
}
JU_LITERALS = {"--accent": "#0e6e63", "--accent-soft": "#e4f1ee",
               "--cat-1": "#0e6e63",
               "--seq-1": "#d9efe9", "--seq-2": "#a3d6c9", "--seq-3": "#66b3a2",
               "--seq-4": "#2b7867", "--seq-5": "#0e6e63"}

STYLE = """
text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.t-label { font-size: 14px; fill: var(--chart-label); }
.t-value { font-size: 14px; fill: var(--chart-value); font-weight: 600;
           font-variant-numeric: tabular-nums; }
.t-big   { font-size: 62px; fill: var(--cat-1); font-weight: 700;
           font-variant-numeric: tabular-nums; }
.t-unit  { font-size: 15px; fill: var(--chart-label); }
.p-key   { font-size: 9.5px; fill: var(--chart-label); font-weight: 600;
           letter-spacing: .09em; }
.p-val   { font-size: 12px; fill: var(--ink); }
.p-mono  { font-size: 11px; fill: var(--ink);
           font-family: ui-monospace, Menlo, Consolas, monospace; }
"""


def esc(v: object) -> str:
    return escape(str(v), quote=True)


# Average advance width as a fraction of font size, per text class. SVG has
# no reflow: text that doesn't fit doesn't wrap, it is drawn over whatever is
# beside it. So the width has to be predicted before drawing, and predicting
# it too narrow is the failure that puts labels through bars.
#
# These were measured in a browser with getBBox rather than assumed, then
# given headroom. A single figure for everything was wrong in both
# directions: 62px bold tabular digits actually run to 0.72em, and the
# letter-spaced uppercase keys to 0.70em, because `letter-spacing: .09em`
# adds to every character. Both were being under-estimated by a third.
EM_BY_CLASS = {
    "t-big": 0.78,      # measured 0.72 — bold, tabular, 62px
    "p-key": 0.75,      # measured 0.70 — uppercase plus .09em tracking
    "t-value": 0.60,    # measured 0.56 — bold tabular numerals
    "p-mono": 0.60,     # measured 0.55
    "t-label": 0.56,    # measured 0.50
    "p-val": 0.53,      # measured 0.48
    "t-unit": 0.50,     # measured 0.44
}
EM_DEFAULT = 0.60

SIZE_BY_CLASS = {"t-big": 62, "t-unit": 15, "t-label": 14, "t-value": 14,
                 "p-key": 9.5, "p-val": 12, "p-mono": 11}


def _em(cls: str) -> float:
    return EM_BY_CLASS.get(cls, EM_DEFAULT)


def _w(text: str, size: float, cls: str = "") -> float:
    return len(str(text)) * size * _em(cls)


def _fit(text: str, size: float, max_px: float, cls: str = "") -> str:
    """Shorten text to fit a box, with an ellipsis so the cut is visible."""
    text = str(text)
    if _w(text, size, cls) <= max_px:
        return text
    per = size * _em(cls)
    keep = max(1, int(max_px / per) - 1)
    return text[:keep].rstrip(" ,;:-") + "…"


def _wrap(text: str, size: float, max_px: float, cls: str = "") -> list[str]:
    """Break text into lines that each fit `max_px`, on spaces where possible."""
    per = size * _em(cls)
    budget = max(8, int(max_px / per))
    words, lines, cur = str(text).split(), [], ""
    for word in words:
        # A single token longer than the line (a long SQL clause, a hostname)
        # has to be broken mid-word or it overflows the box on its own.
        while len(word) > budget:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:budget])
            word = word[budget:]
        if cur and len(cur) + 1 + len(word) > budget:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def _para(text: str, x: int, y: int, cls: str, size: float, max_px: float,
          leading: int) -> tuple[str, int]:
    """A wrapped run of text. Returns the SVG and the height it consumed."""
    lines = _wrap(text, size, max_px, cls)
    svg = "".join(
        f'<text x="{x}" y="{y + i * leading}" class="{cls}">{esc(line)}</text>'
        for i, line in enumerate(lines))
    return svg, len(lines) * leading


def _provenance(y: int, query: str, verify: str, byline: str = "",
                width: int = W) -> tuple[str, int]:
    """The band every graphic carries. Two or three slots, brand rule on top.

    `byline` is the structural signal that separates the two properties: an
    index graphic is unsigned and ends in a query, a Joined Up graphic is
    signed. Someone can then tell a measurement from an argument without
    knowing anything about either brand.
    """
    # The band grows to fit the whole query. Truncating it would defeat the
    # point of printing it: a claim is only checkable if the reader can see
    # the entire thing that produced it.
    reserve = _w(byline, 12, "p-val") + 90 if byline else 0
    lines = _wrap(query, 11, width - 2 * PAD - reserve, "p-mono")
    rows = "".join(
        f'<text x="{PAD}" y="{y + 40 + i * 14}" class="p-mono">{esc(line)}</text>'
        for i, line in enumerate(lines))
    height = max(BAND, 40 + len(lines) * 14 + 22)
    sign = ""
    if byline:
        sign = (f'<text x="{width - PAD}" y="{y + 24}" class="p-key" '
                f'text-anchor="end">ARGUMENT BY</text>'
                f'<text x="{width - PAD}" y="{y + 41}" class="p-val" '
                f'text-anchor="end">{esc(byline)}</text>')
    return (
        f'<rect x="0" y="{y}" width="{width}" height="{height}" '
        f'fill="var(--accent-soft)"/>'
        f'<rect x="0" y="{y}" width="{width}" height="2" fill="var(--accent)"/>'
        f'<text x="{PAD}" y="{y + 24}" class="p-key">'
        f'{"HOW IT WAS MEASURED" if not byline else "MEASURED FROM"}</text>'
        f'{rows}'
        f'<text x="{PAD}" y="{y + height - 10}" class="p-val">{esc(verify)}</text>'
        f'{sign}'), height


def _frame(body: str, height: int, title: str, desc: str) -> str:
    return (
        f'<svg viewBox="0 0 {W} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{esc(title)}">'
        f'<title>{esc(title)}</title><desc>{esc(desc)}</desc>'
        f'<style>{STYLE}</style>'
        f'<rect width="{W}" height="{height}" fill="var(--card)"/>'
        f'<defs><pattern id="hatch" width="8" height="8" '
        f'patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
        f'<rect width="8" height="8" fill="var(--cat-4)"/>'
        f'<line x1="0" y="0" x2="0" y2="8" stroke="var(--card)" '
        f'stroke-width="3" opacity=".55"/></pattern></defs>'
        f'{body}</svg>')


# --- chart types ---------------------------------------------------------

def share_bar(part: int, whole: int, label: str, sub: str) -> tuple[str, int]:
    """One proportion, stated as a number and shown as a bar.

    The number is the point; the bar is there so the reader feels the size
    without doing arithmetic. Both are drawn, because a percentage alone
    hides its denominator and a bar alone hides its precision.
    """
    pct = round(100 * part / whole) if whole else 0
    y = PAD + 62
    filled = int((W - 2 * PAD) * part / whole) if whole else 0
    # The unit sits on its own line under the number rather than beside it.
    # Placing it alongside meant predicting the width of 62px bold digits from
    # how many there were, which put "state no licence" through the "34%".
    # 24px below the baseline left the 62px number's em box overlapping the
    # label's by 7.6px — invisible only because digits have no descenders,
    # which is not a property to rely on.
    lead, lead_h = _para(label, PAD, y + 38, "t-unit", 15, W - 2 * PAD, 20)
    bar_y = y + 24 + lead_h + 8
    caption, cap_h = _para(sub, PAD, bar_y + 48, "t-label", 14, W - 2 * PAD, 19)
    body = (
        f'<text x="{PAD}" y="{y}" class="t-big">{pct}%</text>'
        f'{lead}'
        f'<rect x="{PAD}" y="{bar_y}" width="{W - 2 * PAD}" height="26" rx="4" '
        f'fill="var(--line)"/>'
        f'<rect x="{PAD}" y="{bar_y}" width="{filled}" height="26" rx="4" '
        f'fill="var(--cat-1)"/>'
        f'{caption}')
    return body, bar_y + 48 + cap_h + 6


def hbar(rows: list[tuple[str, int]], unit: str, dead: bool = False) -> tuple[str, int]:
    """Ranked horizontal bars, labels right-aligned into the gutter.

    Right-aligning against the bars is what keeps this safe: a label can only
    ever grow away from the bar it belongs to, so the worst case is a label
    truncated at the left edge rather than one printed over the data. The
    previous version cut names at 34 characters, which at 14px is about 248px
    of text in a 204px gutter — every long council name crossed its own bar.
    """
    if not rows:
        return "", PAD
    top = max(v for _, v in rows) or 1
    gutter = LABEL_W - PAD - 12          # room for the label itself
    span = W - LABEL_W - PAD - 78        # bar track, leaving room for the value
    out = []
    for i, (name, value) in enumerate(rows):
        y = PAD + i * ROW
        w = max(2, int(span * value / top))
        fill = "url(#hatch)" if dead else f"var(--cat-{min(i + 1, 5)})"
        out.append(
            f'<text x="{LABEL_W - 12}" y="{y + 19}" class="t-label" '
            f'text-anchor="end">{esc(_fit(name, 14, gutter, "t-label"))}</text>'
            f'<rect x="{LABEL_W}" y="{y + 6}" width="{w}" height="17" rx="3" '
            f'fill="{fill}"/>'
            f'<text x="{LABEL_W + w + 8}" y="{y + 19}" class="t-value">'
            f'{value:,}</text>')
    height = PAD + len(rows) * ROW
    cap, cap_h = _para(unit, PAD, height + 16, "t-label", 14, W - 2 * PAD, 19)
    out.append(cap)
    return "".join(out), height + 16 + cap_h + 6


def unit_grid(total: int, marked: int, caption: str) -> tuple[str, int]:
    """One square per thing, so a count reads as a quantity.

    100 councils is an abstraction; 100 squares with every one of them
    crossed out is not. Marked squares carry a hatch as well as a colour,
    so the distinction survives being printed or read by someone
    colour-blind.
    """
    cols = 20
    size, gap = 26, 6
    rows_n = (total + cols - 1) // cols
    cells = []
    for i in range(total):
        x = PAD + (i % cols) * (size + gap)
        y = PAD + (i // cols) * (size + gap)
        fill = "url(#hatch)" if i < marked else "var(--line)"
        cells.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" '
                     f'rx="3" fill="{fill}"/>')
    height = PAD + rows_n * (size + gap)
    cap, cap_h = _para(caption, PAD, height + 18, "t-label", 14,
                       W - 2 * PAD, 19)
    cells.append(cap)
    return "".join(cells), height + 18 + cap_h + 6


# --- dispatch ------------------------------------------------------------

def _chart_for(f: dict) -> tuple[str, int]:
    """Pick a chart that suits the shape of the claim."""
    n = f.get("numbers", {})
    kind = f.get("kind")

    if kind == "licensing" and "no_licence" in n:
        return share_bar(n["no_licence"], n["datasets"],
                         "state no licence",
                         f"{n['no_licence']:,} of {n['datasets']:,} findable "
                         f"datasets. Not restricted — unstated.")
    if kind == "dead-hosts" and "councils" in n:
        c = n["councils"]
        return unit_grid(len(c), len(c),
                         f"every one of {len(c)} councils published through "
                         f"{n['host']}, which no longer answers")
    if kind == "dead-hosts" and "detail" in n:
        return hbar([(d["host"], d["resources"]) for d in n["detail"][:8]],
                    "dataset links pointing at servers that no longer answer",
                    dead=True)
    if kind == "abolished":
        return share_bar(n["dead"], n["checked"], "of their links are dead",
                         f"{n['datasets']:,} datasets from {n['councils']} "
                         f"councils abolished since 2019")
    if kind == "coverage":
        central = n.get("published_centrally", 0)
        return share_bar(
            n["no_trace"], n["councils"], f"of councils in {n['nation']}",
            "leave no trace in the UK's open data"
            + (f" — a further {central} publish centrally, through a national "
               f"portal, so their data exists but is not attributed to them"
               if central else ""))
    if kind == "link-rot":
        return hbar([(o["publisher"], o["dead"]) for o in n.get("others", [])[:8]],
                    "dead links per publisher (of those we followed)", dead=True)
    if kind == "formats":
        return hbar([(o["publisher"], o["datasets"])
                     for o in n.get("others", [])[:8]],
                    "datasets, none of them machine-readable")
    if kind == "licensing" and "licences" in n:
        return hbar([(o["title"].title(), o["licences"])
                     for o in n.get("others", [])[:8]],
                    "distinct licences used for one kind of dataset")
    return "", PAD


def _with_fallbacks(svg: str) -> str:
    """Give every var() a literal fallback.

    An SVG whose colours are all custom properties renders as solid black
    boxes if the stylesheet fails to load — every fill resolves to nothing
    and nothing paints black. That is a plausible failure (a cache miss, a
    blocked request, an email client, someone opening the saved file), and
    the fallback costs a few bytes. Light-mode values are the right default:
    without the stylesheet there is no dark mode to match.
    """
    for name, literal in LITERALS.items():
        svg = svg.replace(f"var({name})", f"var({name}, {literal})")
    return svg


def render(f: dict, byline: str = "", measured: str = "") -> str:
    """One finding, one SVG. Empty string if the shape doesn't suit a chart.

    A finding whose numbers don't match what the chart expects yields no
    chart, never an exception. findings.py is rewritten whenever an analysis
    is sharpened, and renaming one key there once took the whole findings
    page down with a KeyError. A page that loses a picture is a much smaller
    failure than a page that loses itself.
    """
    try:
        body, height = _chart_for(f)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return ""
    if not body:
        return ""
    # Where to check it, and when it was true. The scheme is dropped because
    # the band is read, not clicked.
    verify = f.get("link", "open-data.org.uk").split("://")[-1]
    if measured:
        verify = f"{verify} · measured {measured}"
    query = f.get("sql") or "measured from the index"
    band, band_h = _provenance(height, query, verify, byline)
    return _with_fallbacks(_frame(
        body + band, height + band_h,
        f.get("headline", ""), f.get("detail", "")[:300]))


def standalone(svg: str, joined_up: bool = False) -> str:
    """Resolve CSS variables to literals, for an SVG saved outside the page."""
    values = dict(LITERALS, **(JU_LITERALS if joined_up else {}))
    for name, literal in values.items():
        # Fallback form first — render() has already rewritten them.
        svg = svg.replace(f"var({name}, {LITERALS[name]})", literal)
        svg = svg.replace(f"var({name})", literal)
    return svg


# --- geography -----------------------------------------------------------
#
# A real projection, not a decorative grid. The gazetteer holds ONS centroids
# for 352 of the 361 councils, and 29,103 datasets carry a genuine bounding
# box, so these are drawn where things actually are. An equirectangular
# projection is wrong almost everywhere on Earth and fine across ten degrees
# of latitude, provided the x axis is squeezed by cos(lat) — without that the
# UK comes out visibly fat, which readers notice even when they can't say why.

UK = {"west": -8.6, "east": 2.0, "south": 49.8, "north": 61.0}
LAT0 = 55.0                       # the parallel the projection is true at


def project(lon: float, lat: float, w: int, h: int,
            pad: int = 0) -> tuple[float, float]:
    """Equirectangular, at one scale on both axes, fitted and centred.

    The first version multiplied longitude by cos(lat) and then normalised the
    result across the same range — so the factor cancelled algebraically and
    no correction was applied at all. Ten degrees of longitude and eleven of
    latitude were stretched to fill a 664x504 box, which is 2.43 times too
    wide. Britain runs south-west to north-east, and stretching it sideways
    rotates that axis toward the horizontal: the map read as tilted.

    The fix is to scale both axes by the same number and letterbox whatever is
    left over. Britain's true aspect at this latitude is about 0.54, so a
    correctly-shaped map is tall and narrow and leaves free space either side
    — which is where the legend now goes, rather than being stretched away.
    """
    import math

    k = math.cos(math.radians(LAT0))
    x_span = (UK["east"] - UK["west"]) * k
    y_span = UK["north"] - UK["south"]
    avail_w, avail_h = w - 2 * pad, h - 2 * pad
    scale = min(avail_w / x_span, avail_h / y_span)
    ox = pad + (avail_w - x_span * scale) / 2
    oy = pad + (avail_h - y_span * scale) / 2
    return (ox + (lon - UK["west"]) * k * scale,
            oy + (UK["north"] - lat) * scale)


def map_frame(w: int, h: int, pad: int) -> tuple[float, float, float, float]:
    """The box the land actually occupies, so callers can use the gutters."""
    x0, y0 = project(UK["west"], UK["north"], w, h, pad)
    x1, y1 = project(UK["east"], UK["south"], w, h, pad)
    return x0, y0, x1, y1


def _coastline(w: int, h: int, pad: int) -> str:
    """The UK drawn as filled land, under whatever the chart is plotting.

    Without this the maps were a hundred circles floating in blank space with
    nothing to locate them against. The geometry is vendored in
    coastline.json — ONS country boundaries under the Open Government Licence,
    simplified to about a kilometre — rather than fetched from a tile server,
    because these graphics have to render with no network at all.

    Returns an empty string if the file is missing, so a chart degrades to the
    old floating-circles version rather than failing.
    """
    import json as _json
    from pathlib import Path as _Path

    path = _Path(__file__).parent / "coastline.json"
    if not path.exists():
        return ""
    try:
        rings = _json.loads(path.read_text(encoding="utf-8"))["rings"]
    except (ValueError, KeyError, OSError):
        return ""
    out = []
    for ring in rings:
        pts = []
        for lon, lat in ring:
            x, y = project(lon, lat, w, h, pad)
            pts.append(f"{x:.1f},{y:.1f}")
        if len(pts) >= 3:
            out.append("M" + "L".join(pts) + "Z")
    if not out:
        return ""
    return (f'<path d="{" ".join(out)}" fill="var(--land)" '
            f'stroke="var(--land-edge)" stroke-width="0.7" '
            f'stroke-linejoin="round"/>')


def uk_map(points: list[dict], caption: str, legend: list[tuple[str, str]]
           ) -> tuple[str, int]:
    """One circle per place, at its real position, area proportional to value.

    Area, not radius — a circle whose *radius* doubles looks four times
    bigger, which overstates by exactly the factor people are worst at
    correcting for.
    """
    import math
    # Taller than the other charts on purpose. Britain's true aspect is 0.54,
    # so the width is set by the height; at 560 the country came out 274px
    # across in a 720px frame, which is correct and too small to read.
    h = 700
    top = max((p.get("value") or 0) for p in points) or 1
    out = [f'<rect x="0" y="0" width="{W}" height="{h}" fill="var(--card)"/>',
           _coastline(W, h, PAD)]
    for p in points:
        x, y = project(p["lon"], p["lat"], W, h, PAD)
        r = 3 + 16 * math.sqrt((p.get("value") or 0) / top)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
                   f'fill="{p.get("fill", "var(--cat-1)")}" opacity=".72"/>')
    # Stacked in the left gutter. A correctly-shaped UK leaves about 190px
    # free either side, so the legend no longer has to sit under the map
    # competing with the caption.
    lx0 = int(map_frame(W, h, PAD)[0])
    gutter = max(120, lx0 - PAD - 10)
    for i, (label, fill) in enumerate(legend):
        ly = PAD + 18 + i * 24
        out.append(f'<circle cx="{PAD + 6}" cy="{ly - 4}" r="6" fill="{fill}"/>'
                   f'<text x="{PAD + 18}" y="{ly}" class="t-label">'
                   f'{esc(_fit(label, 14, gutter, "t-label"))}</text>')
    cap, cap_h = _para(caption, PAD, h + 4, "t-label", 14, W - 2 * PAD, 19)
    return "".join(out) + cap, h + 4 + cap_h + 6


def bbox_density(boxes: list[tuple[float, float, float, float]],
                 caption: str, cells: int = 96) -> tuple[str, int]:
    """Where the UK's open data is *about*, from 29,000 declared extents.

    Binned onto a grid rather than drawn box by box. Overlapping 24,000
    translucent rectangles produced the same picture in 2 MB of markup, which
    is a lot of bytes to say something a counted grid says exactly — and the
    grid can state its own cell size, so a reader knows the resolution of what
    they are looking at instead of guessing from ink.

    Nationwide extents are excluded and counted in the caption: a dataset
    covering the whole country tells you nothing about any place in it, and
    left in they flood every cell equally.
    """
    h = 700
    span_x = UK["east"] - UK["west"]
    span_y = UK["north"] - UK["south"]
    grid: dict[tuple[int, int], int] = {}
    drawn = national = 0
    for west, south, east, north in boxes:
        if (east - west) > span_x * 0.6 and (north - south) > span_y * 0.6:
            national += 1
            continue
        drawn += 1
        cx0 = int((west - UK["west"]) / span_x * cells)
        cx1 = int((east - UK["west"]) / span_x * cells)
        cy0 = int((UK["north"] - north) / span_y * cells)
        cy1 = int((UK["north"] - south) / span_y * cells)
        for gx in range(max(0, cx0), min(cells, cx1 + 1)):
            for gy in range(max(0, cy0), min(cells, cy1 + 1)):
                grid[(gx, gy)] = grid.get((gx, gy), 0) + 1
    if not grid:
        return "", PAD
    top = max(grid.values())
    # Cell corners go through the same projection as the coastline, or the
    # grid drifts off the land it is supposed to describe.
    fx0, fy0, fx1, fy1 = map_frame(W, h, PAD)
    cw = (fx1 - fx0) / cells
    ch = (fy1 - fy0) / cells
    out = [f'<rect x="0" y="0" width="{W}" height="{h}" fill="var(--card)"/>',
           _coastline(W, h, PAD)]
    import math
    for (gx, gy), n in grid.items():
        # Log scale: a handful of places are described hundreds of times, and
        # on a linear ramp everywhere else would read as empty.
        f = math.log1p(n) / math.log1p(top)
        step = min(5, 1 + int(f * 5))
        out.append(f'<rect x="{fx0 + gx * cw:.1f}" y="{fy0 + gy * ch:.1f}" '
                   f'width="{cw + 0.6:.1f}" height="{ch + 0.6:.1f}" '
                   f'fill="var(--seq-{step})"/>')
    km = span_y * 111 / cells
    full = (f"{caption} {drawn:,} local extents binned onto a {cells}x{cells} "
            f"grid, about {km:.0f} km a cell, shaded by log count. "
            f"{national:,} nationwide extents are excluded — they describe no "
            f"particular place.")
    cap, cap_h = _para(full, PAD, h + 4, "t-label", 14, W - 2 * PAD, 19)
    return "".join(out) + cap, h + 4 + cap_h + 6


# --- time ----------------------------------------------------------------

def timeline(series: list[tuple[str, int]], caption: str,
             highlight: dict[str, str] | None = None) -> tuple[str, int]:
    """Counts by period, as columns. Every period between first and last is
    drawn even when empty — a gap is data, and closing it up hides it."""
    if not series:
        return "", PAD
    top = max(v for _, v in series) or 1
    h = 250
    left = PAD + 34
    step = (W - left - PAD) / max(1, len(series))
    out = []
    for i, (label, value) in enumerate(series):
        x = left + i * step
        bar_h = (h - 46) * value / top
        fill = (highlight or {}).get(label, "var(--cat-1)")
        out.append(f'<rect x="{x:.1f}" y="{h - 40 - bar_h:.1f}" '
                   f'width="{max(1.5, step - 3):.1f}" height="{bar_h:.1f}" '
                   f'fill="{fill}"/>')
        if len(series) <= 30 or i % max(1, len(series) // 12) == 0:
            out.append(f'<text x="{x + step / 2:.1f}" y="{h - 24}" '
                       f'class="t-label" text-anchor="middle">'
                       f'{esc(str(label)[-4:])}</text>')
    out.append(f'<line x1="{left}" y1="{h - 40}" x2="{W - PAD}" y2="{h - 40}" '
               f'stroke="var(--chart-baseline)" stroke-width="1"/>')
    out.append(f'<text x="{PAD}" y="{PAD + 10}" class="t-value">{top:,}</text>')
    cap, cap_h = _para(caption, PAD, h + 2, "t-label", 14, W - 2 * PAD, 19)
    return "".join(out) + cap, h + 2 + cap_h + 6


# --- composition ---------------------------------------------------------

def treemap(items: list[tuple[str, int]], caption: str) -> tuple[str, int]:
    """Area by share, laid out in slices then rows.

    A simple slice-and-dice rather than squarified: the aspect ratios are
    worse but the order is preserved left to right, so a reader can follow
    the ranking as well as the areas. For a dozen items that trade is right.
    """
    if not items:
        return "", PAD
    h = 330
    total = sum(v for _, v in items) or 1
    x, out = PAD, []
    width = W - 2 * PAD
    for i, (label, value) in enumerate(items):
        w = width * value / total
        fill = f"var(--seq-{min(5, 1 + i % 5)})"
        out.append(f'<rect x="{x:.1f}" y="{PAD}" width="{max(1, w - 2):.1f}" '
                   f'height="{h - PAD - 30}" rx="3" fill="{fill}"/>')
        if w > 58:
            # The label sits on the tile, so its colour comes from that
            # tile's own on- token: the ramp runs pale to saturated and one
            # ink colour cannot serve both ends.
            #
            # As an inline style, not a fill attribute. A presentation
            # attribute loses to any stylesheet rule, and `.t-label` already
            # sets a fill — so every override written as fill="..." was
            # silently discarded and the labels rendered in --muted, at
            # 3.02:1 on the tile. The arithmetic was right and the cascade
            # ignored it.
            on = f"var(--on-seq-{min(5, 1 + i % 5)})"
            out.append(
                f'<text x="{x + 8:.1f}" y="{PAD + 22}" class="t-label" '
                f'style="fill:{on}">{esc(_fit(label, 14, w - 16, "t-label"))}'
                f'</text>'
                f'<text x="{x + 8:.1f}" y="{PAD + 41}" class="t-value" '
                f'style="fill:{on}">{value:,}</text>')
        x += w
    cap, cap_h = _para(caption, PAD, h + 2, "t-label", 14, W - 2 * PAD, 19)
    return "".join(out) + cap, h + 2 + cap_h + 6
