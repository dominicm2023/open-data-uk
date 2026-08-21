"""Regression tests for unrendered portal templates.

ArcGIS Hub intermittently serves the Handlebars source instead of the value:
a feed comes back with "{{name}}" where the title should be and
"{{description}}" where the description should be. It is not rare — 17
datasets across eight councils were indexed under the literal title
"{{name}}", and 807 descriptions said nothing but "{{description}}" — and it
is not recoverable, so both fields have to refuse it at ingest.

The two fields are refused differently, and that distinction is what these
cases pin: a title that never rendered means there is no record to store,
while a description that never rendered is blanked and the rest of the
record kept. Getting that backwards would either publish empty pages or
throw away sound datasets over a missing paragraph.

Every harvester is covered, not just the DCAT one where it was found: the
same feed shapes turn up behind CKAN and JSON portals too.

No database or network needed, so CI runs it on every push. When an index is
present (DATA_DIR, or index.db beside the code) it is checked as well, which
is what catches a backfill that was never run.

Usage:  python scripts/placeholder_test.py
"""

from __future__ import annotations

import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import harvester  # noqa: E402
from normalise import norm_title, strip_html, unrendered  # noqa: E402
from paths import DB_PATH  # noqa: E402

failures: list[str] = []


def check(got, want, label: str) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}"
          f"{'' if ok else f'  (got {got!r}, wanted {want!r})'}")
    if not ok:
        failures.append(label)


# --- the rule itself ----------------------------------------------------
for template in ("{{name}}", "{{description}}", "{{default.description}}",
                 "  {{name}}  ", "{{ name }}"):
    check(unrendered(template), True, f"{template!r} is an unrendered template")
    check(norm_title(template), None, f"{template!r} is not a title")

check(unrendered(None), False, "an absent value is not a template")
check(unrendered(42), False, "a non-string value is not a template")

# A title is a title even if it mentions a brace; only the doubled brace of a
# template engine counts. Council datasets really are named things like
# "Section 106 {planning}", and losing one to an over-eager rule would be a
# worse outcome than the fault being fixed.
for title in ("Air Quality {2024}", "Spend over £500 (Q1)", "name"):
    check(norm_title(title), title, f"{title!r} is a perfectly good title")
check(norm_title("  Air Quality  "), "Air Quality", "a title is trimmed")
check(norm_title(None), None, "an absent title stays absent")
check(norm_title(""), None, "an empty title is no title")
check(norm_title("   "), None, "a whitespace title is no title")
# Reversed 2026-08-21: a bare number is unfindable — nobody searches "1234",
# and NBN's thirteen records titled "1" merged into one dataset. Titles need
# at least one word.
check(norm_title(1234), None, "a bare number is not a title")
check(norm_title("1"), None, "nor is '1' — thirteen NBN records were")
check(norm_title("xh"), None, "two characters of keyboard mash is not a title")
check(norm_title("TPO"), "TPO", "a three-letter acronym is (just) a title")
check(norm_title("GREEN_BELT_RELEASE_DEVELOPMENT_SITES"),
      "Green Belt Release Development Sites",
      "a machine slug is read out loud")
check(norm_title("TDC_POLLING_STATIONS_2015"), "TDC Polling Stations 2015",
      "short all-caps words survive as acronyms")
check(norm_title("INSPIRE_WFS"), "Inspire WFS",
      "long shouting is capitalised, short acronyms kept")
check(norm_title("Air Quality (2024)"), "Air Quality (2024)",
      "a real title with punctuation is untouched")
check(norm_title("snake_case_but Has Spaces_too"),
      "snake_case_but Has Spaces_too",
      "underscores inside a real sentence are left alone")

check(strip_html("{{description}}"), None, "a template description is blanked")
check(strip_html("<p>{{description}}</p>"), None,
      "a template wrapped in markup is still a template")
check(strip_html("Counts of {planning} applications"),
      "Counts of {planning} applications",
      "a single brace is ordinary text and survives")
check(strip_html("<p>A real description</p>"), "A real description",
      "a real description is untouched")


# --- every ingest point refuses a template title ------------------------
NOW = "2026-01-01T00:00:00Z"
SRC = {"id": "testsource", "name": "Test Council",
       "web": "https://example.gov.uk",
       "dataset_url": "https://example.gov.uk/dataset/{name}"}


def csw_record(title: str, abstract: str) -> ET.Element:
    return ET.fromstring(
        '<csw:Record xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:dct="http://purl.org/dc/terms/">'
        "<dc:identifier>rec-1</dc:identifier>"
        f"<dc:title>{title}</dc:title>"
        f"<dct:abstract>{abstract}</dct:abstract>"
        "</csw:Record>")


def csw_row(title: str, abstract: str):
    # A CSW catalogue's dataset_url is keyed on {id}, not the {name} the CKAN
    # sources use, so this one gets its own source config.
    src = {**SRC, "dataset_url": "https://example.gov.uk/record/{id}"}
    got = harvester.normalise_csw_record(csw_record(title, abstract), src, NOW)
    return got[0] if got else None


JSON_CFG = {"title": "title", "description": "abstract"}

# (harvester name, build a row from a title and a description)
INGEST = [
    ("ckan", lambda t, d: harvester.normalise_package(
        {"id": "pkg-1", "name": "pkg-1", "title": t, "notes": d}, SRC, NOW)),
    ("dcat", lambda t, d: harvester.normalise_dcat_dataset(
        {"identifier": "ds-1", "title": t, "description": d}, SRC, NOW)),
    ("ods", lambda t, d: harvester.normalise_ods_dataset(
        {"dataset_id": "ds-1",
         "metas": {"default": {"title": t, "description": d}}}, SRC, NOW)),
    ("csw", csw_row),
    ("json", lambda t, d: harvester._normalise_json_record(
        {"title": t, "abstract": d}, "rec-1", JSON_CFG, SRC, NOW)),
    ("geonode", lambda t, d: harvester.normalise_geonode_layer(
        {"uuid": "lyr-1", "title": t, "abstract": d}, SRC,
        "https://example.gov.uk", NOW)),
]

TITLE_COL = 4                                  # position in the UPSERT tuple
DESCRIPTION_COL = harvester.DESCRIPTION_COL

for name, build in INGEST:
    check(build("{{name}}", "A real description"), None,
          f"{name}: a record titled '{{{{name}}}}' is not stored at all")

    # ...but a template description costs the record only its description.
    row = build("Air Quality Monitoring", "{{description}}")
    check(row is not None, True, f"{name}: a sound record with a template "
                                 f"description is still stored")
    if row:
        check(row[TITLE_COL], "Air Quality Monitoring",
              f"{name}: its title is kept")
        check(row[DESCRIPTION_COL], None, f"{name}: its description is blanked")

    row = build("Air Quality Monitoring", "Hourly NO2 readings")
    if row:
        check(row[DESCRIPTION_COL], "Hourly NO2 readings",
              f"{name}: a real description is left alone")

# A Hub feed with no identifier keys the record on publisher and title, so an
# unrendered title would have collapsed every such record onto one key.
check(harvester.normalise_dcat_dataset({"title": "{{name}}"}, SRC, NOW), None,
      "dcat: an identifier-less record with a template title is refused too")

# The publisher guard predates this and must keep working — it is the reason
# an unrendered feed doesn't file its datasets under a publisher called
# "{{source}}".
check(harvester._dcat_publisher({"publisher": {"name": "{{source}}"}}, SRC),
      "Test Council", "dcat: a template publisher falls back to the source")


# --- and nothing template-shaped is left in the built index -------------
if not Path(DB_PATH).exists():
    print(f"\nno index at {DB_PATH} — skipping the stored-data check")
else:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    for column in ("title", "description"):
        rows = conn.execute(
            f"SELECT source_id, COUNT(*) FROM datasets "
            f"WHERE {column} LIKE '%{{{{%' GROUP BY source_id").fetchall()
        check(sum(n for _s, n in rows), 0,
              f"no stored {column} contains an unrendered template"
              + (f" (still in: {', '.join(s for s, _n in rows)})" if rows else ""))
    conn.close()

print()
print("no unrendered templates get in" if not failures
      else f"{len(failures)} failure(s): " + "; ".join(failures))
sys.exit(1 if failures else 0)
