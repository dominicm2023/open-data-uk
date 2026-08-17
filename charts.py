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


def _wrap(text: str, width: int) -> list[str]:
    """Break a string into lines of roughly `width` characters, on spaces."""
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def _provenance(y: int, query: str, verify: str, byline: str = "") -> str:
    """The band every graphic carries. Two or three slots, brand rule on top.

    `byline` is the structural signal that separates the two properties: an
    index graphic is unsigned and ends in a query, a Joined Up graphic is
    signed. Someone can then tell a measurement from an argument without
    knowing anything about either brand.
    """
    q = _wrap(query, 62)[:2]
    rows = "".join(
        f'<text x="{PAD}" y="{y + 40 + i * 14}" class="p-mono">{esc(line)}</text>'
        for i, line in enumerate(q))
    sign = ""
    if byline:
        sign = (f'<text x="{W - PAD}" y="{y + 24}" class="p-key" '
                f'text-anchor="end">ARGUMENT BY</text>'
                f'<text x="{W - PAD}" y="{y + 41}" class="p-val" '
                f'text-anchor="end">{esc(byline)}</text>')
    return (
        f'<rect x="0" y="{y}" width="{W}" height="{BAND}" fill="var(--accent-soft)"/>'
        f'<rect x="0" y="{y}" width="{W}" height="2" fill="var(--accent)"/>'
        f'<text x="{PAD}" y="{y + 24}" class="p-key">'
        f'{"HOW IT WAS MEASURED" if not byline else "MEASURED FROM"}</text>'
        f'{rows}'
        f'<text x="{PAD}" y="{y + BAND - 8}" class="p-val">{esc(verify)}</text>'
        f'{sign}')


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
    y = PAD + 66
    filled = int((W - 2 * PAD) * part / whole) if whole else 0
    body = (
        f'<text x="{PAD}" y="{y}" class="t-big">{pct}%</text>'
        f'<text x="{PAD + 14 + len(str(pct)) * 38}" y="{y}" class="t-unit">'
        f'{esc(label)}</text>'
        f'<rect x="{PAD}" y="{y + 26}" width="{W - 2 * PAD}" height="26" rx="4" '
        f'fill="var(--line)"/>'
        f'<rect x="{PAD}" y="{y + 26}" width="{filled}" height="26" rx="4" '
        f'fill="var(--cat-1)"/>'
        f'<text x="{PAD}" y="{y + 76}" class="t-label">{esc(sub)}</text>')
    return body, y + 96


def hbar(rows: list[tuple[str, int]], unit: str, dead: bool = False) -> tuple[str, int]:
    """Ranked horizontal bars. Labels sit outside, values inside or after."""
    if not rows:
        return "", PAD
    top = max(v for _, v in rows) or 1
    span = W - PAD - LABEL_W - 70
    out = []
    for i, (name, value) in enumerate(rows):
        y = PAD + i * ROW
        w = max(2, int(span * value / top))
        fill = "url(#hatch)" if dead else f"var(--cat-{min(i + 1, 5)})"
        out.append(
            f'<text x="{PAD}" y="{y + 19}" class="t-label">'
            f'{esc(name[:34])}</text>'
            f'<rect x="{LABEL_W}" y="{y + 6}" width="{w}" height="17" rx="3" '
            f'fill="{fill}"/>'
            f'<text x="{LABEL_W + w + 8}" y="{y + 19}" class="t-value">'
            f'{value:,}</text>')
    height = PAD + len(rows) * ROW
    out.append(f'<text x="{PAD}" y="{height + 16}" class="t-label">'
               f'{esc(unit)}</text>')
    return "".join(out), height + 32


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
    cells.append(f'<text x="{PAD}" y="{height + 18}" class="t-label">'
                 f'{esc(caption)}</text>')
    return "".join(cells), height + 34


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


def render(f: dict, byline: str = "") -> str:
    """One finding, one SVG. Empty string if the shape doesn't suit a chart."""
    body, height = _chart_for(f)
    if not body:
        return ""
    verify = f.get("link", "open-data.org.uk")
    query = f.get("sql") or "measured from the index"
    return _with_fallbacks(_frame(
        body + _provenance(height, query, verify, byline),
        height + BAND, f.get("headline", ""), f.get("detail", "")[:300]))


def standalone(svg: str, joined_up: bool = False) -> str:
    """Resolve CSS variables to literals, for an SVG saved outside the page."""
    values = dict(LITERALS, **(JU_LITERALS if joined_up else {}))
    for name, literal in values.items():
        # Fallback form first — render() has already rewritten them.
        svg = svg.replace(f"var({name}, {LITERALS[name]})", literal)
        svg = svg.replace(f"var({name})", literal)
    return svg
