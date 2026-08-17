"""Poster-scale versions of the findings that survived review.

The gallery charts are made to be read on the page. These are made to be
*seen*: 1200x630, which is the size every social platform crops a link
preview to, so one file works as a shareable image and as an Open Graph card
without being redrawn.

One rule is held throughout, and it is the reason these can be dramatic
without becoming untrustworthy: **nothing decorative may carry a value.**
Atmosphere in the background is fine. A gradient along a bar is not, because
the reader cannot tell where the data stopped and the styling began — and
every one of these claims names a real public body that may want to argue
with it.

Within that the forms are chosen to be arresting because of what they show
rather than in spite of it:

  converge   N things joined to one point. The strongest picture available
             for the two findings whose whole substance is that a single
             failure looks like many — one dead host serving a hundred
             councils, one archived spreadsheet standing in for a whole
             abolished performance regime. A bar chart of those would hide
             the mechanism; this *is* the mechanism.
  matrix     one mark per thing, at a size where 361 marks have physical
             presence. A percentage is an abstraction; 296 squares with 28
             lit is a quantity you feel.
  headline   one number at poster scale, for the findings whose force is
             arithmetic.

Usage:
    python posters.py                 # write posters.html
    python posters.py --only 3        # one poster, while art-directing it
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import charts
from charts import PAD, _fit, _para, _provenance, esc

ROOT = Path(__file__).parent
OUT = ROOT / "posters.html"
W = 1200
H = 630                # 1.905:1, what link previews crop to
SITE = "open-data.org.uk"

STYLE = charts.STYLE + """
.h-kicker { font-size: 15px; fill: var(--chart-label); font-weight: 600;
            letter-spacing: .11em; }
.h-title  { font-size: 44px; fill: var(--ink); font-weight: 700; }
.h-title2 { font-size: 31px; fill: var(--ink); font-weight: 700; }
.h-sub    { font-size: 17px; fill: var(--chart-label); }
.h-huge   { font-size: 150px; fill: var(--cat-1); font-weight: 700;
            font-variant-numeric: tabular-nums; }
.h-unit   { font-size: 22px; fill: var(--ink); font-weight: 600; }
.h-note   { font-size: 13px; fill: var(--chart-label); }
"""

# Widths measured the same way as the page charts: over-estimate, because SVG
# does not reflow and a title that runs off the edge is worse than a short one.
EM = {"h-kicker": 0.72, "h-title": 0.56, "h-title2": 0.56, "h-sub": 0.53,
      "h-huge": 0.66, "h-unit": 0.60, "h-note": 0.53}
SIZE = {"h-kicker": 15, "h-title": 44, "h-title2": 31, "h-sub": 17,
        "h-huge": 150, "h-unit": 22, "h-note": 13}


def wrap(text: str, cls: str, max_px: float) -> list[str]:
    per = SIZE[cls] * EM[cls]
    budget = max(6, int(max_px / per))
    words, lines, cur = str(text).split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > budget:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def heading(kicker: str, title: str, x: int = PAD * 2, y: int = 86,
            max_px: int = 470, cls: str = "h-title2") -> tuple[str, int]:
    """Kicker plus wrapped title. Returns the SVG and the baseline it ended on.

    Two sizes, because the column width decides how many lines a headline
    takes and the lines have to fit above the provenance band. A poster with
    art down the right-hand side gets the narrower column and the smaller
    type; a poster whose art is one huge number gets the full width and the
    big type.
    """
    lead = 52 if cls == "h-title" else 38
    out = [f'<text x="{x}" y="{y}" class="h-kicker">{esc(kicker.upper())}</text>']
    line_y = y
    for i, line in enumerate(wrap(title, cls, max_px)):
        line_y = y + lead + i * lead
        out.append(f'<text x="{x}" y="{line_y}" class="{cls}">{esc(line)}</text>')
    return "".join(out), line_y


def frame(body: str, title: str, desc: str, query: str, byline: str = "",
          measured: str = "") -> str:
    """A poster, with the provenance band on the bottom edge as always."""
    verify = SITE + (f" · measured {measured}" if measured else "")
    band, band_h = _provenance(H - 92, query, verify, byline, width=W)
    svg = (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{esc(title)}">'
        f'<title>{esc(title)}</title><desc>{esc(desc)}</desc>'
        f'<style>{STYLE}</style>'
        f'<rect width="{W}" height="{H}" fill="var(--card)"/>'
        f'<rect x="0" y="0" width="6" height="{H}" fill="var(--accent)"/>'
        f'{body}{band}</svg>')
    return charts._with_fallbacks(svg)


# --- forms ---------------------------------------------------------------

def converge(outer: int, centre: str, outer_label: str, note: str,
             lit: int | None = None, top: int = 300) -> str:
    """Many things joined to one point, drawn as spokes into a dead centre.

    For the findings whose entire substance is that one failure looks like
    many independent ones. Every spoke is one real thing, so the density is
    the data rather than decoration — and the centre is deliberately drawn as
    a hole rather than a hub, because what sits there stopped answering.
    """
    cx, cy, r = 940, 300, 205
    lit = outer if lit is None else lit
    spokes, dots = [], []
    for i in range(outer):
        angle = (i / outer) * math.tau - math.pi / 2
        x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
        colour = "var(--cat-4)" if i < lit else "var(--line-strong)"
        spokes.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" '
                      f'stroke="{colour}" stroke-width="0.9" opacity=".5"/>')
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" '
                    f'fill="{colour}"/>')
    hole = (f'<circle cx="{cx}" cy="{cy}" r="34" fill="var(--card)" '
            f'stroke="var(--cat-4)" stroke-width="2.5"/>'
            f'<line x1="{cx - 15}" y1="{cy - 15}" x2="{cx + 15}" y2="{cy + 15}" '
            f'stroke="var(--cat-4)" stroke-width="2.5"/>'
            f'<line x1="{cx + 15}" y1="{cy - 15}" x2="{cx - 15}" y2="{cy + 15}" '
            f'stroke="var(--cat-4)" stroke-width="2.5"/>')
    label = (f'<text x="{cx}" y="{cy + 74}" class="h-note" '
             f'text-anchor="middle">{esc(_fit(centre, 13, 300, "t-label"))}</text>')
    ring = (f'<text x="{cx}" y="{cy - r - 24}" class="h-note" '
            f'text-anchor="middle">{esc(outer_label)}</text>')
    body, _ = _para(note, PAD * 2, top, "h-note", 13, 470, 20)
    return "".join(spokes) + "".join(dots) + hole + label + ring + body


def matrix(total: int, lit: int, lit_label: str, rest_label: str,
           note: str, top: int = 300) -> str:
    """One square per thing, so a proportion becomes a quantity.

    Marks are laid out to fill the right-hand half at whatever size fits,
    because the point of this form is that the count has physical presence —
    296 registers should look like 296 things.
    """
    # Named grid_top, not top: unpacking into `top` silently overwrote
    # the caption position parameter, so every caption drew at y=96.
    left, grid_top, box_w, box_h = 560, 96, 600, 380
    cols = max(1, int(math.ceil(math.sqrt(total * box_w / max(box_h, 1)))))
    rows = max(1, math.ceil(total / cols))
    cell = min(box_w / cols, box_h / rows)
    size = max(2.0, cell - max(1.0, cell * 0.18))
    out = []
    for i in range(total):
        x = left + (i % cols) * cell
        y = grid_top + (i // cols) * cell
        fill = "var(--cat-1)" if i < lit else "var(--line)"
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" '
                   f'height="{size:.1f}" rx="{min(2, size / 4):.1f}" '
                   f'fill="{fill}"/>')
    key_y = grid_top + rows * cell + 26
    out.append(f'<rect x="{left}" y="{key_y - 10}" width="12" height="12" '
               f'rx="2" fill="var(--cat-1)"/>'
               f'<text x="{left + 20}" y="{key_y}" class="h-note">'
               f'{esc(_fit(lit_label, 13, 260, "t-label"))}</text>')
    out.append(f'<rect x="{left + 300}" y="{key_y - 10}" width="12" '
               f'height="12" rx="2" fill="var(--line)"/>'
               f'<text x="{left + 320}" y="{key_y}" class="h-note">'
               f'{esc(_fit(rest_label, 13, 260, "t-label"))}</text>')
    note_svg, _ = _para(note, PAD * 2, top, "h-note", 13, 460, 20)
    return "".join(out) + note_svg


def headline(value: str, unit: str, note: str,
             top: int = 300) -> str:
    """One number at poster scale, for claims whose force is arithmetic."""
    base = top + 112
    out = [f'<text x="{PAD * 2}" y="{base}" class="h-huge">{esc(value)}</text>']
    x = PAD * 2 + len(value) * SIZE["h-huge"] * EM["h-huge"] + 20
    for i, line in enumerate(wrap(unit, "h-unit", W - x - PAD * 2)):
        out.append(f'<text x="{x:.0f}" y="{base - 46 + i * 28}" class="h-unit">'
                   f'{esc(line)}</text>')
    # 62, not 44: a 150px numeral's em box reaches 33px below its
    # baseline, and digits having no descenders is not a property to
    # lean on.
    note_svg, _ = _para(note, PAD * 2, base + 62, "h-sub", 17,
                        W - PAD * 4, 25)
    return "".join(out) + note_svg


# --- the ten -------------------------------------------------------------

def posters() -> list[dict]:
    return [
        {"kicker": "One host, a hundred councils",
         "title": "A hundred councils published their INSPIRE data through one address. It stopped answering.",
         "art": lambda top: converge(
             100, "inspire.misoportal.com", "100 councils",
             "904 datasets from 100 different councils resolve to a single "
             "host that answers from no network we have tried. The supplier "
             "is alive and trading; it is this endpoint that went. No "
             "individual portal could notice — each holds a handful of "
             "records that look perfectly healthy.", top=top),
         "query": "dead_hosts.json — the host serving the most distinct publishers",
         "desc": "100 spokes converging on one unreachable host"},

        {"kicker": "Statutory since 2017",
         "title": "296 councils must publish a brownfield land register. 28 have a link that still works.",
         "art": lambda top: matrix(
             296, 28, "link returns data", "no working link",
             "Every English planning authority has been required to publish a "
             "brownfield land register since December 2017. 116 appear in the "
             "national index at all. The duty is to publish, not to publish "
             "as open data — so this measures findability, not compliance.", top=top),
         "query": "brownfield land register in title; availability IN ('data','api'); "
                  "denominator = 296 English councils",
         "desc": "296 squares, 28 filled"},

        {"kicker": "The supplier is a name",
         "title": "Follow the money between public bodies and it stops at the spelling of a company name.",
         "art": lambda top: matrix(
             80, 1, "publishes an identifier", "name only",
             "80 public bodies publish a supplier column. One — Crown "
             "Commercial Service — publishes a structured organisation "
             "identifier. Everywhere else the supplier is free text, so "
             "following one company between bodies means fuzzy-matching "
             "“BT PLC” against “British Telecommunications plc” across "
             "80 independently typed spreadsheets.", top=top),
         "query": "resource_checks.columns matched for supplier/vendor/payee against "
                  "identifier, VAT and OCDS patterns — columns read for 8.6%",
         "desc": "80 squares, one filled"},

        {"kicker": "A dead regime, still listed",
         "title": "England measured its councils on 198 indicators. All 403 records point at one archived file.",
         "art": lambda top: converge(
             403, "one October 2010 spreadsheet", "403 catalogue records",
             "The National Indicator Set was abolished in 2010. 403 entries "
             "for it survive across eleven government departments, and 382 "
             "of them resolve to the same National Archives snapshot of a "
             "single October 2010 spreadsheet. That URL now returns a web "
             "page rather than the file.", lit=382, top=top),
         "query": "titles matching 'NI 0%' or 'NI 1%'; shared resource URL counted "
                  "across datasets and publishers",
         "desc": "403 spokes converging on one archived spreadsheet"},

        {"kicker": "Nobody updated it", "wide": True,
         "title": "9,027 datasets from 673 publishers share one last-modified date.",
         "art": lambda top: headline(
             "9,027", "datasets, one date, 673 publishers",
             "Including 102 from Allerdale and 97 from Wycombe — councils "
             "abolished years ago and incapable of updating anything. A third "
             "of the index sits on one of six such bulk dates, so “last "
             "updated” on the national catalogue often means the platform "
             "touched the record. Our own staleness figures are a floor: "
             "excluding churn, 34.8% becomes 44.6%.", top=top),
         "query": "SELECT substr(modified,1,10), COUNT(*), COUNT(DISTINCT publisher) "
                  "FROM datasets GROUP BY 1 HAVING COUNT(*) > 1500",
         "desc": "9,027 datasets sharing a single modification date"},

        {"kicker": "Filed under the wrong council", "wide": True,
         "title": "data.gov.uk lists 119 datasets about Leeds under Sunderland City Council.",
         "art": lambda top: headline(
             "238", "records about Leeds, filed elsewhere",
             "119 under Sunderland and 119 under North Tyneside — including "
             "“Who’s who in Leeds” and “Collection of council tax and "
             "non-domestic rates - Leeds area”. Asked directly, the "
             "data.gov.uk package API returns organization = Sunderland City "
             "Council. The mis-attribution is upstream; the national "
             "catalogue is not a reliable list of who published what.", top=top),
         "query": "publisher IN ('Sunderland City Council','North Tyneside "
                  "Metropolitan Borough Council') AND LOWER(title) LIKE '%leeds%'",
         "desc": "238 mis-attributed records"},

        {"kicker": "One in five", "wide": True,
         "title": "17,255 datasets are a single file nobody has touched in three years.",
         "art": lambda top: headline(
             "20%", "of the index, and twice as likely to be broken",
             "Dead links run at 10.3% among these against 5.0% among "
             "recently-updated records, on a 6.5% index baseline. The caveat "
             "matters: the Home Office does still publish monthly asylum "
             "statistics — it is the catalogue record that was abandoned, "
             "not the data. And a finished one-off publication is not "
             "neglected at all.", top=top),
         "query": "resource_count <= 1 AND modified < date('now','-3 years'), "
                  "availability compared across the same cut",
         "desc": "One in five datasets stale and single-file"},

        {"kicker": "Air quality",
         "title": "Fewer than three in ten councils publish their own air quality data.",
         "art": lambda top: matrix(
             335, 97, "publishes its own dataset", "none found",
             "97 of 335 councils, and only 16% publish their statutory Air "
             "Quality Management Areas. The rate is flat across coverage "
             "states — 31% for councils we harvest directly, 28% for those we "
             "see only through data.gov.uk — so this is not our blindness. "
             "Councils discharge the duty by reporting to Defra, so the "
             "measurements exist even where the council publishes nothing.", top=top),
         "query": "title LIKE air quality / no2 / nitrogen dioxide / air pollut / "
                  "pm10 / pm2.5, attributed to councils by exact identity",
         "desc": "335 squares, 97 filled"},

        {"kicker": "Depends which nation",
         "title": "73% of Northern Irish councils run their own catalogue. One of 22 Welsh councils does.",
         "art": lambda top: matrix(
             361, 103, "runs its own catalogue", "reached another way",
             "Northern Ireland 8 of 11, Scotland 17 of 32, England 77 of 296, "
             "Wales 1 of 22. Not running a portal is not a failure — for a "
             "small district, publishing via data.gov.uk is the correct and "
             "cheaper thing. This is about whether a council's data has an "
             "address of its own, not about virtue.", top=top),
         "query": "council_coverage.json state=='own', grouped by nation and by "
                  "ONS code prefix",
         "desc": "361 councils, 103 with their own catalogue"},

        {"kicker": "Better than it looks",
         "title": "2,192 of the NHS Business Services Authority's 2,248 datasets are answers to questions.",
         "art": lambda top: matrix(
             2248, 2192, "an FOI case number", "actual datasets",
             "Each of the 2,192 is titled only with a reference — FOI-03941, "
             "FOI-03938 — because it is the answer to something a member of "
             "the public asked. The remaining 51 are 1,692 CSV files under a "
             "single open licence, monthly series up to 145 files deep, and "
             "among the most consistently published data in the index.", top=top),
         "query": "source_id='nhsbsa', split on title GLOB 'FOI-*'",
         "desc": "2,248 records, 2,192 of them FOI answers"},
    ]


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Posters — UK Open Data Index</title>
<link rel="stylesheet" href="/site.css">
<style>
 .poster { margin: 2rem 0; }
 .poster svg { display: block; width: 100%; min-width: 0; height: auto;
               border: 1px solid var(--line); border-radius: var(--radius); }
 .poster h2 { font-size: 1rem; color: var(--muted); font-weight: 600;
              letter-spacing: .04em; text-transform: uppercase;
              margin: 0 0 .6rem; }
</style>
</head><body><div class="wrap" style="max-width:76rem">
<h1>Posters</h1>
<p>The ten findings that survived review, drawn at 1200&#215;630 — the size every
platform crops a link preview to, so one file works as a shareable image and
as an Open Graph card. Not published: these are drafts.</p>
<p class="note">One rule throughout: nothing decorative carries a value.
Background is atmosphere; anything a reader could measure is data. Every
poster keeps the provenance band, so an arresting picture stays as checkable
as a plain one.</p>
{posters}
</div></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", type=int, help="render just this one (1-based)")
    args = ap.parse_args()

    items = posters()
    if args.only:
        items = items[args.only - 1:args.only]

    blocks = []
    for i, spec in enumerate(items, 1):
        # The art starts where the title finished. Placing captions at a
        # fixed y put every one of them through the last line of its own
        # headline — twelve collisions across ten posters.
        wide = spec.get("wide", False)
        head, last = heading(spec["kicker"], spec["title"],
                             max_px=900 if wide else 470,
                             cls="h-title" if wide else "h-title2")
        svg = frame(head + spec["art"](last + 40), spec["title"], spec["desc"],
                    spec["query"], measured="17 August 2026")
        blocks.append(f'<section class="poster"><h2>{i:02d}</h2>{svg}</section>')
        print(f"   {i:02d}  {spec['title'][:66]}")

    # replace, not format: the page carries inline CSS and every brace
    # in it would be read as a field name.
    OUT.write_text(PAGE.replace("{posters}", "".join(blocks)),
                   encoding="utf-8")
    print(f"\n{len(blocks)} posters — wrote {OUT.name} "
          f"({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
