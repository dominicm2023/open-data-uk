"""Draw the index itself — a gallery, mostly curiosity rather than argument.

The findings engine looks for things that are wrong. This looks for things
that are interesting, which is a different search and mostly a happier one:
where the UK's data actually describes, what it counts, what it has counted
for longest. Roughly a quarter of these carry a political edge and the rest
are here because 106,000 datasets is a strange and rather beautiful object
once you can see the shape of it.

Everything is drawn from the same index and carries the same provenance band,
so an interesting picture is as checkable as an accusatory one. Output is a
standalone HTML page for the workshop.

Usage:
    python scripts/gallery.py            # write gallery.html
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import charts  # noqa: E402
from paths import connect  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "gallery.html"
SITE = "open-data.org.uk"
FINDABLE = ("FROM datasets d WHERE "
            "NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) AND "
            "NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)")

# Years outside this are not dates, they are the epoch-milliseconds bug and
# the unrendered {{modified:toISO}} placeholders — about 14,700 rows.
YEAR_MIN, YEAR_MAX = 1990, 2027


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def gazetteer() -> dict:
    return json.loads((ROOT / "gazetteer.json").read_text(encoding="utf-8"))


def where_the_data_is(conn) -> tuple[str, str, str]:
    """Every council placed at its real centroid, sized by what it publishes."""
    gaz = gazetteer()
    councils = json.loads((ROOT / "council_coverage.json").read_text(encoding="utf-8"))
    fill = {"own": "var(--cat-1)", "hub": "var(--cat-5)",
            "aggregator": "var(--cat-3)", "none": "var(--cat-4)"}
    points, missing = [], 0
    for c in councils:
        pos = gaz.get(norm_name(c["name"])) or \
            gaz.get(norm_name(c["name"].split(",")[0]))
        if not pos:
            missing += 1
            continue
        points.append({"lon": pos[0], "lat": pos[1],
                       "value": (c.get("direct") or 0) + (c.get("aggregated") or 0),
                       "fill": fill.get(c["state"], "var(--cat-2)")})
    body, h = charts.uk_map(
        points,
        f"Every UK council at its true centre, circle area proportional to how "
        f"many datasets we hold. Colour is how we reach them. {missing} could "
        f"not be placed from the ONS gazetteer and are not drawn.",
        [("own portal", "var(--cat-1)"), ("regional hub", "var(--cat-5)"),
         ("data.gov.uk only", "var(--cat-3)"), ("nothing found", "var(--cat-4)")])
    return body, h, "council_coverage.json joined to ONS local authority centroids"


def what_the_data_covers(conn) -> tuple[str, str, str]:
    """The declared extent of 29,000 datasets, drawn as accumulated ink."""
    boxes = conn.execute(
        "SELECT bbox_west, bbox_south, bbox_east, bbox_north FROM dataset_geo "
        "WHERE bbox_west IS NOT NULL AND bbox_west BETWEEN -12 AND 4 "
        "AND bbox_north BETWEEN 49 AND 62 AND bbox_east > bbox_west "
        "AND bbox_north > bbox_south").fetchall()
    body, h = charts.bbox_density(
        boxes, "Where the UK's open data says it is about. Each dataset paints "
               "its own declared extent faintly, so the bright places are the "
               "ones described over and over.")
    return body, h, ("dataset_geo bounding boxes, clipped to the UK and "
                     "excluding nationwide extents")


def what_the_state_counts(conn) -> tuple[str, str, str]:
    """The dozen subjects the UK publishes most about."""
    rows = conn.execute(
        "SELECT t.tag, COUNT(*) n FROM dataset_tags t "
        "JOIN datasets d ON d.key = t.dataset_key "
        "WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) "
        "GROUP BY t.tag ORDER BY n DESC LIMIT 60").fetchall()
    # Publishers tag with machine words as well as subjects. A treemap of
    # "wms", "zip file" and "bdy_adm" would describe our plumbing rather than
    # the country.
    noise = {"wms", "wfs", "zip file", "open data", "uk", "united kingdom",
             "england", "scotland", "wales", "northern ireland", "ni",
             "great britain", "england and wales", "bdy_adm", "nerc_ddc",
             "lad", "fishdac", "other", "data", "gis"}
    items = [(t, n) for t, n in rows if t not in noise][:12]
    body, h = charts.treemap(
        items, "The subjects the UK publishes most about, by the publishers' "
               "own tags. Machine words like 'wms' and 'zip file' are removed: "
               "they describe our plumbing, not the country.")
    return body, h, "dataset_tags grouped by tag, platform vocabulary excluded"


def a_century_of_data(conn) -> tuple[str, str, str]:
    """When the data we hold says it was last updated."""
    rows = conn.execute(
        f"SELECT CAST(substr(d.modified, 1, 4) AS INTEGER) y, COUNT(*) "
        f"{FINDABLE} AND d.modified IS NOT NULL "
        f"AND CAST(substr(d.modified, 1, 4) AS INTEGER) BETWEEN ? AND ? "
        f"GROUP BY y ORDER BY y", (YEAR_MIN, YEAR_MAX)).fetchall()
    bad = conn.execute(
        f"SELECT COUNT(*) {FINDABLE} AND d.modified IS NOT NULL AND ("
        f"CAST(substr(d.modified, 1, 4) AS INTEGER) < ? OR "
        f"CAST(substr(d.modified, 1, 4) AS INTEGER) > ? OR "
        f"d.modified LIKE '%{{%')", (YEAR_MIN, YEAR_MAX)).fetchone()[0]
    if not rows:
        return "", "", ""
    span = {str(y): n for y, n in rows}
    series = [(str(y), span.get(str(y), 0))
              for y in range(min(span, key=int) and int(min(span, key=int)),
                             int(max(span, key=int)) + 1)]
    peak = max(series, key=lambda s: s[1])[0]
    body, h = charts.timeline(
        series,
        f"Last-updated year for every dataset that states one. {bad:,} rows are "
        f"excluded because their date is not a date — raw millisecond "
        f"timestamps reading as the 1700s, and unrendered template "
        f"placeholders. The peak is {peak}.",
        highlight={peak: "var(--cat-5)"})
    return body, h, ("datasets.modified, years 1990-2027 only, corrupt values "
                     "excluded and counted")


def the_long_tail_of_formats(conn) -> tuple[str, str, str]:
    """How many ways the UK has found to publish a file."""
    counts: Counter = Counter()
    for (raw,) in conn.execute(f"SELECT d.formats_norm {FINDABLE} "
                               f"AND d.formats_norm NOT IN ('[]', '')"):
        try:
            counts.update(json.loads(raw))
        except (ValueError, TypeError):
            continue
    top = counts.most_common(10)
    rest = sum(n for _, n in counts.most_common()[10:])
    body, h = charts.hbar(
        top + [(f"{len(counts) - 10} other formats", rest)],
        f"{len(counts)} distinct file formats appear in the index. The top ten "
        f"cover most of it; the tail includes formats last fashionable in the "
        f"1990s.")
    return body, h, "formats_norm exploded and counted across findable datasets"


def the_oldest_things(conn) -> tuple[str, str, str]:
    """What the UK has been counting longest."""
    rows = conn.execute(
        f"SELECT d.title, CAST(substr(d.modified, 1, 4) AS INTEGER) y {FINDABLE} "
        f"AND d.modified IS NOT NULL "
        f"AND CAST(substr(d.modified, 1, 4) AS INTEGER) BETWEEN ? AND 2006 "
        f"AND d.availability IN ('data', 'api') "
        f"ORDER BY y LIMIT 9", (YEAR_MIN,)).fetchall()
    if not rows:
        return "", "", ""
    body, h = charts.hbar(
        [(t, y) for t, y in rows],
        "The oldest datasets whose files we could still download today. The "
        "number is the year, not a quantity — these are the survivors.")
    return body, h, ("oldest verified-downloadable datasets by stated year, "
                     "corrupt dates excluded")


PANELS = [
    ("Where the data is", where_the_data_is, False),
    ("What the data is about", what_the_data_covers, False),
    ("What the state counts", what_the_state_counts, False),
    ("When it was last touched", a_century_of_data, False),
    ("Every way to publish a file", the_long_tail_of_formats, False),
    ("What we have counted longest", the_oldest_things, False),
]

PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Gallery — UK Open Data Index</title>
<link rel="stylesheet" href="/site.css">
</head><body><div class="wrap">
<h1>Gallery</h1>
<p>The index drawn rather than queried. Not published — these are drafts for
the workshop, and every one carries the query behind it so an interesting
picture stays as checkable as an accusatory one.</p>
{panels}
</div></body></html>
"""


def main() -> int:
    conn = connect()
    blocks = []
    for title, fn, political in PANELS:
        try:
            body, height, query = fn(conn)
        except Exception as exc:  # noqa: BLE001 — one bad panel shouldn't stop the rest
            print(f"   {title}: {type(exc).__name__}: {exc}")
            continue
        if not body:
            print(f"   {title}: no data")
            continue
        band, band_h = charts._provenance(height, query, f"{SITE} · gallery")
        svg = charts._with_fallbacks(charts._frame(
            body + band, height + band_h, title, query))
        cls = "finding joined-up" if political else "finding"
        blocks.append(f'<article class="{cls}"><h2>{charts.esc(title)}</h2>'
                      f"<figure>{svg}</figure></article>")
        print(f"   drew {title}")
    OUT.write_text(PAGE.format(panels="".join(blocks)), encoding="utf-8")
    conn.close()
    print(f"\n{len(blocks)} panels — wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
