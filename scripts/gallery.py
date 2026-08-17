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



def the_one_thing_we_agree_on(conn) -> tuple[str, str, str]:
    """The org chart is the most standardised document in British government."""
    n = conn.execute(f"SELECT COUNT(*) {FINDABLE} AND d.title = ?",
                     ("Organogram of Staff Roles & Salaries",)).fetchone()[0]
    pubs = conn.execute(
        f"SELECT COUNT(DISTINCT d.publisher) {FINDABLE} "
        f"AND LOWER(d.title) LIKE '%organogram%'").fetchone()[0]
    total = conn.execute(
        f"SELECT COUNT(*) {FINDABLE} AND LOWER(d.title) LIKE '%organogram%'"
    ).fetchone()[0]
    body, h = share_of(n, total, "share the identical title",
                       f"{total} organogram datasets from {pubs} different public "
                       f"bodies, {n} of them titled \"Organogram of Staff Roles & "
                       f"Salaries\" character for character. The 2010 Transparency "
                       f"Code specified the format, and it is the one thing the "
                       f"whole state agrees on how to record: its own hierarchy.")
    return body, h, ("title = 'Organogram of Staff Roles & Salaries', against all "
                     "datasets whose title contains 'organogram'")


def share_of(part, whole, label, sub):
    return charts.share_bar(part, whole, label, sub)


def a_catalogue_of_questions(conn) -> tuple[str, str, str]:
    """One body's catalogue is almost entirely answers to public questions."""
    foi = conn.execute(
        f"SELECT COUNT(*) {FINDABLE} AND d.source_id = 'nhsbsa' "
        f"AND d.title GLOB 'FOI-*'").fetchone()[0]
    total = conn.execute(
        f"SELECT COUNT(*) {FINDABLE} AND d.source_id = 'nhsbsa'").fetchone()[0]
    body, h = charts.share_bar(
        foi, total, "are titled only with a reference number",
        f"Of the NHS Business Services Authority's {total:,} published datasets, "
        f"{foi:,} are titled nothing but a case number — FOI-03941, FOI-03938 — "
        f"because each one is the answer to a question a member of the public "
        f"asked. The other 51 are its real data, and they are excellent.")
    return body, h, "source_id = 'nhsbsa', titles matching the pattern FOI-*"


def published_once(conn) -> tuple[str, str, str]:
    """What publishers say when asked how often they will update."""
    rows = conn.execute("""
        SELECT LOWER(REPLACE(TRIM(g.update_frequency), ' ', '')) f, COUNT(*) n
        FROM dataset_geo g JOIN datasets d ON d.key = g.dataset_key
        WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
          AND NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)
          AND g.update_frequency IS NOT NULL AND TRIM(g.update_frequency) <> ''
        GROUP BY f ORDER BY n DESC LIMIT 8""").fetchall()
    total = sum(n for _, n in rows)
    body, h = charts.treemap(
        [(f, n) for f, n in rows],
        f"What publishers answer when the metadata asks how often a dataset will "
        f"be updated, across {total:,} spatial records on data.gov.uk that answer "
        f"at all. This is their own vocabulary from a fixed list, not our "
        f"judgement — and only these records are asked the question, so it is a "
        f"fact about INSPIRE spatial metadata rather than about UK open data "
        f"generally.")
    return body, h, ("dataset_geo.update_frequency grouped, findable datasets "
                     "only — the field exists on data.gov.uk records alone")



def the_oldest_thing_is_a_fish(conn) -> tuple[str, str, str]:
    """How far back the observations reach, by declared reference date."""
    rows = conn.execute("""
        SELECT CAST(substr(g.reference_date, 1, 4) AS INTEGER) y, COUNT(*) n
        FROM dataset_geo g JOIN datasets d ON d.key = g.dataset_key
        WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
          AND NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)
          AND g.reference_date IS NOT NULL AND g.reference_date <> ''
          AND CAST(substr(g.reference_date, 1, 4) AS INTEGER) BETWEEN 1700 AND 2027
        GROUP BY y ORDER BY y""").fetchall()
    if not rows:
        return "", "", ""
    # By decade: a year-by-year axis across three centuries is unreadable, and
    # the early end is a handful of records a century.
    decades: dict[int, int] = {}
    for year, n in rows:
        decades[year // 10 * 10] = decades.get(year // 10 * 10, 0) + n
    first, last = min(decades), max(decades)
    series = [(str(d), decades.get(d, 0)) for d in range(first, last + 10, 10)]
    early = sum(n for y, n in rows if y < 1900)
    body, h = charts.timeline(
        series,
        f"What period the data describes, not when the record was written, by "
        f"decade. {early} datasets reach back past 1900 — the earliest are "
        f"British Geological Survey mine plans at 1800, and a marine fish "
        f"recording scheme whose observations start in 1743, thirty years "
        f"before the Boston Tea Party. Those round early years mean \"as far "
        f"back as the collection goes\", not a precise date.",
        highlight={str(first): "var(--cat-5)"})
    return body, h, ("dataset_geo.reference_date by decade, 1700-2027; one "
                     "impossible value of 0201-07-14 excluded as a typo")


def the_biggest_files(conn) -> tuple[str, str, str]:
    """The largest things anyone has published, as far as we measured."""
    rows = conn.execute(f"""
        SELECT d.title, rc.size_bytes
        FROM resource_checks rc JOIN resources r ON r.url = rc.url
        JOIN datasets d ON d.key = r.dataset_key
        WHERE rc.size_bytes IS NOT NULL AND NOT EXISTS
              (SELECT 1 FROM duplicates x WHERE x.key = d.key)
        GROUP BY rc.url ORDER BY rc.size_bytes DESC LIMIT 8""").fetchall()
    if not rows:
        return "", "", ""
    measured = conn.execute(
        "SELECT COUNT(*) FROM resource_checks WHERE size_bytes IS NOT NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(DISTINCT url) FROM resources").fetchone()[0]
    body, h = charts.hbar(
        [(title, size // 1_000_000_000) for title, size in rows],
        f"Gigabytes, for the largest files we have measured. The biggest is "
        f"98 GB of X-ray scans of 600-million-year-old embryo-like fossils, "
        f"and most of the rest is deep-sea video — one 45 GB entry turned out "
        f"to be a DVD disc image, VIDEO_TS folder and all. Only "
        f"{measured:,} of {total:,} resource URLs report a size, so this is "
        f"the largest we could measure, not the largest that exists.")
    return body, h, ("resource_checks.size_bytes, the 11.6% of resource URLs "
                     "that report a Content-Length")


def a_title_is_whatever_you_type(conn) -> tuple[str, str, str]:
    """What a national registry accepts when nobody checks."""
    rows = conn.execute(f"""
        SELECT d.source_id, COUNT(*) n {FINDABLE}
        AND LENGTH(TRIM(d.title)) <= 4
        GROUP BY d.source_id ORDER BY n DESC LIMIT 6""").fetchall()
    titles = [r[0] for r in conn.execute(f"""
        SELECT DISTINCT TRIM(d.title) {FINDABLE}
        AND LENGTH(TRIM(d.title)) <= 4 AND d.source_id = 'nbn_atlas'
        ORDER BY LENGTH(TRIM(d.title)), TRIM(d.title) LIMIT 40""")]
    total = sum(n for _, n in rows)
    body, h = charts.unit_grid(
        len(titles), len(titles),
        f"One square per distinct title of four characters or fewer in the "
        f"National Biodiversity Network's registry. They include "
        f"{', '.join(repr(x) for x in titles[:8])} — live registry entries, "
        f"each with its own public page. {total} such records exist across "
        f"the index; the biodiversity registry is the outlier.")
    return body, h, ("titles of four characters or fewer, grouped by source; "
                     "NBN Atlas is fully harvested")


def one_tag_per_council(conn) -> tuple[str, str, str]:
    """The most exhaustively tagged dataset in the index."""
    row = conn.execute("""
        SELECT d.title, COUNT(*) n FROM dataset_tags t
        JOIN datasets d ON d.key = t.dataset_key
        WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
        GROUP BY d.key ORDER BY n DESC LIMIT 1""").fetchone()
    if not row:
        return "", "", ""
    title, n = row
    top = conn.execute("""
        SELECT d.title, COUNT(*) n FROM dataset_tags t
        JOIN datasets d ON d.key = t.dataset_key
        WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
        GROUP BY d.key ORDER BY n DESC LIMIT 8""").fetchall()
    body, h = charts.hbar(
        list(top),
        f"Tags per dataset, for the eight most exhaustively tagged records in "
        f"the index. The winner is \"{title}\" with {n} — one for every UK "
        f"local authority from Aberdeen City to York, plus a handful of "
        f"themes. Somebody typed all of them.")
    return body, h, "dataset_tags counted per dataset, findable records only"



def one_spreadsheet_holds_it_all(conn) -> tuple[str, str, str]:
    """England's abolished performance regime, all pointing at one file."""
    rows = conn.execute(f"""
        SELECT d.publisher, COUNT(*) n {FINDABLE}
        AND (d.title LIKE 'NI 0%' OR d.title LIKE 'NI 1%')
        GROUP BY d.publisher ORDER BY n DESC LIMIT 8""").fetchall()
    total = conn.execute(f"SELECT COUNT(*) {FINDABLE} "
                         f"AND (d.title LIKE 'NI 0%' OR d.title LIKE 'NI 1%')"
                         ).fetchone()[0]
    if not rows:
        return "", "", ""
    body, h = charts.hbar(
        list(rows),
        f"England once measured its councils on 198 national indicators. The "
        f"regime was abolished in 2010; {total} catalogue entries for it "
        f"survive, spread across {len(rows)}+ departments, and 382 of them "
        f"point at the same archived October 2010 spreadsheet. That URL now "
        f"returns a web page rather than the file.")
    return body, h, ("titles matching 'NI 0%' or 'NI 1%', grouped by publisher; "
                     "the shared resource URL counted across datasets")


def the_statutory_cliff(conn) -> tuple[str, str, str]:
    """What councils publish when the law says so, and when it doesn't."""
    subjects = [("Brownfield land register", "%brownfield%"),
                ("Conservation areas", "%conservation area%"),
                ("Tree preservation orders", "%tree preservation%"),
                ("Allotments", "%allotment%"),
                ("Public toilets", "%public toilet%"),
                ("Polling stations", "%polling%"),
                ("Defibrillators", "%defibrillator%"),
                ("Dog fouling", "%dog foul%"),
                ("Stiles (Devon only)", "%stile%")]
    out = []
    for label, like in subjects:
        n = conn.execute(
            f"SELECT COUNT(DISTINCT d.publisher) {FINDABLE} "
            f"AND (d.publisher LIKE '%Council%' OR d.publisher LIKE '%Borough%') "
            f"AND LOWER(d.title) LIKE ?", (like,)).fetchone()[0]
        out.append((label, n))
    body, h = charts.hbar(
        out,
        "Councils publishing each subject, out of 447 council publishers. The "
        "top of this list is statutory and the bottom is somebody's initiative "
        "— 208 councils publish a brownfield land register because the law "
        "requires it, and exactly one publishes the stiles on its footpaths. "
        "Partial harvesting can only push these counts down, so the large "
        "numbers are floors and the small ones are 'only one that we hold'.")
    return body, h, ("distinct council publishers per title keyword, findable "
                     "datasets only")


def the_questions_they_ask(conn) -> tuple[str, str, str]:
    """Column headings that stop being a ledger and become an interview."""
    import json as _json
    seen: dict[str, int] = {}
    for (raw,) in conn.execute(
            "SELECT columns FROM resource_checks "
            "WHERE columns IS NOT NULL AND columns <> ''"):
        try:
            for head in _json.loads(raw):
                head = str(head).strip()
                if head.endswith("?") and len(head) > 8:
                    seen[head] = seen.get(head, 0) + 1
        except (ValueError, TypeError):
            continue
    questions = sorted(seen)[:60]
    body, h = charts.unit_grid(
        len(questions), 0,
        "One square per distinct column heading that ends in a question mark, "
        "found by opening 4,757 government spreadsheets. They include Leeds "
        "asking \"How urgent is your need?\" on its Covid service requests, "
        "and Calderdale asking \"Cremation or Burial?\" on its public health "
        "funerals. Headings are truncated at 60 characters by our own "
        "harvester, so the longer questions are shown short.")
    return body, h, ("resource_checks.columns, headings ending in '?', across "
                     "the 4,757 files whose headers we have read")


def one_file_in_twenty_six(conn) -> tuple[str, str, str]:
    """The distribution of files per dataset, which is not a distribution."""
    rows = conn.execute(f"""
        SELECT d.title, d.resource_count {FINDABLE}
        ORDER BY d.resource_count DESC LIMIT 8""").fetchall()
    total = conn.execute(f"SELECT SUM(d.resource_count) {FINDABLE}").fetchone()[0]
    if not rows or not total:
        return "", "", ""
    top = rows[0][1]
    body, h = charts.hbar(
        list(rows),
        f"Files per dataset, for the eight largest. Half of Britain's open "
        f"datasets are a single file and 12,526 have none at all — but the "
        f"post-Brexit tariff schedule alone holds {top:,}, which is "
        f"{100 * top / total:.1f}% of every file in the index. Partial "
        f"harvesting works against this figure rather than for it, so treat "
        f"it as a property of our index.")
    return body, h, "resource_count ordered descending, against the index total"



def every_monitored_overflow(conn) -> tuple[str, str, str]:
    """England's storm overflows at their true positions, from fetched data.

    The first panel drawn from data we fetched rather than metadata we hold.
    The deprivation-gradient claim this join was built to test is NOT
    supported — the analysis that killed it is in analysis/sewage/REPORT.md —
    so this shows the geography and declines the inference.
    """
    import csv as _csv
    path = ROOT / "analysis" / "sewage" / "joined.csv"
    if not path.exists():
        return "", "", ""
    rows = list(_csv.DictReader(open(path, encoding="utf-8")))
    # 14,180 circles is a megabyte of markup; bin the quiet ones into the
    # density grid and draw only the loud ones as sized points.
    boxes, points = [], []
    for r in rows:
        try:
            lon, lat = float(r["lon"]), float(r["lat"])
            n = float(r["spill_count"] or 0)
        except (ValueError, KeyError):
            continue
        boxes.append((lon - 0.01, lat - 0.008, lon + 0.01, lat + 0.008))
        if n >= 100:
            points.append({"lon": lon, "lat": lat, "value": n,
                           "fill": "var(--cat-4)"})
    body, h = charts.uk_map(
        points,
        f"Every one of England's {len(rows):,} monitored storm overflows "
        f"shades the map; the {len(points)} that spilled 100 or more times "
        f"in 2025 are drawn as circles, area proportional to spill count. "
        f"Wales and Scotland are different regimes and are not shown. We "
        f"tested whether spills track deprivation: they do not — the full "
        f"working is in the repo, and the middle of the distribution is "
        f"where the spilling is.",
        [("100+ spills in 2025", "var(--cat-4)")])
    # underlay the full population as density behind the points
    grid, gh = charts.bbox_density(
        boxes, "")
    return grid + body, max(h, gh), (
        "analysis/sewage/joined.csv — EA Event Duration Monitoring 2025 "
        "annual return, all English water companies, joined by coordinates")


def rivers_are_the_boundaries(conn) -> tuple[str, str, str]:
    """The methodological finding: the join everyone does is a coin flip."""
    import csv as _csv
    path = ROOT / "analysis" / "sewage" / "joined.csv"
    if not path.exists():
        return "", "", ""
    rows = list(_csv.DictReader(open(path, encoding="utf-8")))
    near = multi = 0
    for r in rows:
        try:
            if float(r.get("dist_to_lsoa_boundary_m") or 9e9) <= 50:
                near += 1
            if int(r.get("candidate_imd_deciles_100m") or 1) > 1:
                multi += 1
        except ValueError:
            continue
    body, h = charts.share_bar(
        multi, len(rows), "of storm overflows sit on a statistical boundary",
        f"{multi:,} of {len(rows):,} monitored overflows have more than one "
        f"candidate deprivation decile within 100 metres, and {near:,} sit "
        f"within 50 metres of a neighbourhood boundary — because sewers "
        f"discharge to rivers, and rivers are where the boundaries were "
        f"drawn. Any analysis that assigns an overflow to exactly one "
        f"neighbourhood is flipping a coin for half its points. Ours "
        f"reported a band instead, and the band says: no deprivation "
        f"gradient.")
    return body, h, ("analysis/sewage/joined.csv — distance to nearest LSOA "
                     "boundary and candidate deciles within 100m, per overflow")


PANELS = [
    ("Where the data is", where_the_data_is, False),
    ("What the data is about", what_the_data_covers, False),
    ("What the state counts", what_the_state_counts, False),
    ("When it was last touched", a_century_of_data, False),
    ("Every way to publish a file", the_long_tail_of_formats, False),
    ("What we have counted longest", the_oldest_things, False),
    ("The one thing the state agrees on", the_one_thing_we_agree_on, False),
    ("A catalogue made of questions", a_catalogue_of_questions, False),
    ("Published once, by their own account", published_once, True),
    ("How far back it reaches", the_oldest_thing_is_a_fish, False),
    ("The biggest things published", the_biggest_files, False),
    ("A title is whatever you type", a_title_is_whatever_you_type, False),
    ("One tag per council", one_tag_per_council, False),
    ("One spreadsheet holds it all", one_spreadsheet_holds_it_all, True),
    ("The statutory cliff", the_statutory_cliff, True),
    ("The questions they ask", the_questions_they_ask, False),
    ("One file in every twenty-six", one_file_in_twenty_six, False),
    ("Every monitored overflow", every_monitored_overflow, True),
    ("Rivers are the boundaries", rivers_are_the_boundaries, True),
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
