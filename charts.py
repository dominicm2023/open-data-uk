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
}
JU_LITERALS = {"--accent": "#0e6e63", "--accent-soft": "#e4f1ee",
               "--cat-1": "#0e6e63"}

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


def _provenance(y: int, query: str, verify: str,
                byline: str = "") -> tuple[str, int]:
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
    lines = _wrap(query, 11, W - 2 * PAD - reserve, "p-mono")
    rows = "".join(
        f'<text x="{PAD}" y="{y + 40 + i * 14}" class="p-mono">{esc(line)}</text>'
        for i, line in enumerate(lines))
    height = max(BAND, 40 + len(lines) * 14 + 22)
    sign = ""
    if byline:
        sign = (f'<text x="{W - PAD}" y="{y + 24}" class="p-key" '
                f'text-anchor="end">ARGUMENT BY</text>'
                f'<text x="{W - PAD}" y="{y + 41}" class="p-val" '
                f'text-anchor="end">{esc(byline)}</text>')
    return (
        f'<rect x="0" y="{y}" width="{W}" height="{height}" '
        f'fill="var(--accent-soft)"/>'
        f'<rect x="0" y="{y}" width="{W}" height="2" fill="var(--accent)"/>'
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
        return share_bar(n["without_data"], n["councils"],
                         f"of councils in {n['nation']}",
                         "publish no open data we can find anywhere")
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
    """One finding, one SVG. Empty string if the shape doesn't suit a chart."""
    body, height = _chart_for(f)
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
