"""Regression tests for server-rendered dataset pages.

Every string on these pages comes from a publisher's catalogue, and we render
tens of thousands of them. That makes escaping a correctness problem rather
than a nicety: a title containing a script tag, or a resource whose URL is a
`javascript:` scheme, has to come out inert in the HTML, in the meta tags and
inside the JSON-LD block — three different escaping contexts on one page.

No database or network needed, so CI can run it on every push.

Usage:  python scripts/render_test.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import pagerender  # noqa: E402

SITE = "https://open-data.org.uk"
XSS = '<script>alert("x")</script>'

failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


def record(**over) -> dict:
    base = {
        "key": "data_gov_uk:abc-123",
        "title": "Air Quality Monitoring",
        "publisher": "Leeds City Council",
        "source": "data_gov_uk",
        "license": "OGL-UK-3.0",
        "created": "2020-01-01",
        "modified": "2026-05-04",
        "landing_url": "https://www.data.gov.uk/dataset/abc",
        "description": "Hourly readings from roadside monitors.",
        "tags": ["air", "quality"],
        "formats": ["CSV"],
        "availability": "data",
        "duplicate_of": None,
        "retired": False,
        "resources": [{"url": "https://example.gov.uk/a.csv", "name": "2026 data",
                       "format_norm": "CSV", "verdict": "data",
                       "size_bytes": 2048, "columns": ["date", "no2"]}],
        "related": [],
        "attribution": "Contains public sector information.",
    }
    return {**base, "resources": list(base["resources"]), **over}


def ld(html: str) -> dict:
    raw = re.search(r'<script type="application/ld\+json">(.*?)</script>',
                    html, re.S).group(1)
    return json.loads(raw.replace("\\u003c", "<"))


# --- a normal page ------------------------------------------------------
page = pagerender.render_dataset(record(), SITE)
check("<!--HEAD-->" not in page and "<!--BODY-->" not in page,
      "both template placeholders are filled")
check("Air Quality Monitoring" in re.search(r"<title>(.*?)</title>", page).group(1),
      "title element names the dataset")
check("Leeds City Council" in page, "publisher appears in the rendered body")
check("Hourly readings" in page, "description is in the HTML, not fetched later")
check(f'<link rel="canonical" href="{SITE}/dataset?key=data_gov_uk%3Aabc-123">' in page,
      "canonical URL is absolute and percent-encoded")
check('content="index,follow"' in page, "an ordinary record is indexable")
check(ld(page)["@type"] == "Dataset", "JSON-LD parses and declares a Dataset")
check(ld(page)["isBasedOn"] == "https://www.data.gov.uk/dataset/abc",
      "JSON-LD credits the publisher's page as the source")
check(ld(page)["license"].startswith("https://www.nationalarchives"),
      "a known licence id becomes its canonical URL")

# --- licences in JSON-LD -------------------------------------------------
# Google reads `license` best as a URL, so every id that pins one down gets
# one; free text is passed through as the name; and where the publisher
# stated nothing, the field is absent — an invented licence would be a claim.
for lic, url in (("CC-BY-3.0", "https://creativecommons.org/licenses/by/3.0/"),
                 ("CC-BY-NC-SA-2.5", "https://creativecommons.org/licenses/by-nc-sa/2.5/"),
                 ("ODbL-1.0", "https://opendatacommons.org/licenses/odbl/1-0/")):
    check(ld(pagerender.render_dataset(record(license=lic), SITE))["license"] == url,
          f"{lic} resolves to its canonical URL")
check(ld(pagerender.render_dataset(record(license="NSTA Open User Licence"),
                                   SITE))["license"] == "NSTA Open User Licence",
      "an unrecognised licence stays as its name — no URL is guessed")
check("license" not in ld(pagerender.render_dataset(record(license=None), SITE)),
      "no stated licence emits no license field: absence is not invented")

# --- hostile publisher content -----------------------------------------
nasty = pagerender.render_dataset(
    record(title=XSS, description=f"harmless {XSS}",
           publisher='" onmouseover="evil()',
           resources=[{"url": "javascript:alert(1)", "name": XSS,
                       "format_norm": "CSV", "verdict": "data",
                       "size_bytes": None, "columns": [XSS]}]), SITE)
check("<script>alert" not in nasty, "a script tag in the title cannot execute")
check(nasty.count("<script") == 1, "only our own JSON-LD script element exists")
check('href="#"' in nasty and "javascript:alert" not in nasty,
      "a javascript: resource URL is refused, not linked")
check(' onmouseover="evil()' not in nasty,
      "a quote in the publisher name cannot break out of an attribute")
check("</script>" not in json.dumps(ld(nasty)["name"]) and ld(nasty),
      "JSON-LD stays parseable when the title contains markup")

# --- records search doesn't return --------------------------------------
dup = pagerender.render_dataset(record(duplicate_of="calderdale:e69o0"), SITE)
check(f'canonical" href="{SITE}/dataset?key=calderdale%3Ae69o0"' in dup,
      "a duplicate points its canonical tag at the copy we rank")
check("Another portal publishes this same dataset" in dup,
      "a duplicate says so on the page, not just in a meta tag")

ret = pagerender.render_dataset(record(retired=True), SITE)
check('content="noindex,follow"' in ret, "a withdrawn record is not offered for indexing")
check("retired or superseded" in ret, "a withdrawn record warns the reader")

# --- description fallback ----------------------------------------------
bare = record(description=None, title="Council Spending")
desc = pagerender.meta_description(bare)
check("no description" in desc and "Council Spending" in desc,
      "a dataset with no description still gets an honest snippet")
check(len(pagerender.meta_description(record(description="word " * 200))) < 200,
      "a long description is trimmed to snippet length")

# --- browse pages -------------------------------------------------------
# These exist so dataset pages aren't orphans. An ampersand is the trap: it
# has to be percent-encoded in the path AND escaped again as an HTML
# attribute, or the link is broken and the sitemap is invalid XML.
AMP = "Marine Environmental Data & Information Network"

pubs = pagerender.render_publishers([("Leeds City Council", 412), (AMP, 4042),
                                     ("3D Data Ltd", 7)], SITE)
check('href="/publisher?name=Leeds%20City%20Council"' in pubs,
      "publisher links percent-encode the name")
check("%26" in pubs and "Data & Information" not in pubs.split("<style>")[0],
      "an ampersand in a publisher name is encoded, not left raw")
check('id="#"' in pubs, "a publisher starting with a digit files under #")
check(f"{SITE}/publishers" in pubs, "the publisher index canonicalises to itself")

def rows(n: int) -> list[dict]:
    return [{"key": f"x:{i}", "title": f"Survey {i}", "modified": "2026-01-02",
             "availability": "data"} for i in range(n)]


page2 = pagerender.render_publisher(AMP, rows(100), page=2, pages=41,
                                    total=4042, site_url=SITE)
raw_amp = re.findall(r'href="[^"]*&(?!amp;)[^"]*"', page2)
check(not raw_amp, f"no href carries a bare ampersand ({raw_amp[:1]})")
check('href="/publisher?name=Marine%20Environmental%20Data%20%26%20Information'
      '%20Network&amp;page=3"' in page2,
      "the next-page link is both percent-encoded and HTML-escaped")
check('rel="prev"' in page2 and 'rel="next"' in page2,
      "a middle page declares both neighbours")
check(f'canonical" href="{SITE}/publisher?name=Marine%20Environmental%20Data'
      f'%20%26%20Information%20Network&amp;page=2"' in page2,
      "page 2 canonicalises to itself, not to page 1")
check("showing 101–200" in page2 and "page 2 of 41" in page2,
      "the reader is told where in the list they are")

# The last page is short. Counting from len(rows) instead of the page size
# puts the reader thousands of entries from where they actually are.
last = pagerender.render_publisher(AMP, rows(42), page=41, pages=41,
                                   total=4042, site_url=SITE)
check("showing 4,001–4,042" in last,
      "the short last page still numbers from the top of the list")

page1 = pagerender.render_publisher(
    "Leeds City Council", [{"key": "x:1", "title": "Spending", "modified": None,
                            "availability": None}], page=1, pages=1, total=1,
    site_url=SITE)
check('rel="prev"' not in page1 and 'rel="next"' not in page1,
      "a single-page publisher declares no neighbours")
check("1 dataset in the index." in page1, "one dataset is not '1 datasets'")

# --- thin pages ---------------------------------------------------------
# 646 records hold a title and nothing else. Offering those for indexing
# invites a search engine to judge the whole site by them.
empty = record(description=None, resources=[], tags=[], formats=[])
check(pagerender.is_thin(empty), "a record with no text, files, tags or formats is thin")
check('content="noindex,follow"' in pagerender.render_dataset(empty, SITE),
      "a page with nothing on it is not offered for indexing")
check(not pagerender.is_thin(record(description=None, tags=[], formats=[])),
      "no prose but real files is NOT thin — 2,139 records are like this")
check(not pagerender.is_thin(record(description=None, resources=[], formats=[],
                                    tags=["air quality", "no2"])),
      "no prose but real tags is not thin either")
check('content="index,follow"' in pagerender.render_dataset(record(), SITE),
      "an ordinary record is still indexable after the thin rule")

# --- subjects -----------------------------------------------------------
# Publishers store tags like " Bins ", which produced /topic?tag=%20bins —
# a URL that could never match the subject index.
check(pagerender.norm_tag("  Bring   Sites ") == "bring sites",
      "tag normalisation strips and collapses whitespace")
check(pagerender.topic_path(" Bins ") == "/topic?tag=bins",
      "a tag link is built from the normalised form, not the raw string")
tagged = pagerender.render_dataset(
    record(tags=[" Bins ", "bins", "Waste Collection"]), SITE)
check(tagged.count('class="chip tag"') == 2,
      "tags differing only in case or spacing collapse to one chip")
check('href="/topic?tag=waste%20collection"' in tagged,
      "a multi-word tag links to its percent-encoded subject page")

topic = pagerender.render_topic("recycling", rows(3), page=1, pages=1, total=57,
                                publishers=25, site_url=SITE)
check("57 datasets" in topic and "25 organisations" in topic,
      "a subject page states its span across publishers")
check('content="index,follow"' in topic, "a shared subject is indexable")
lonely = pagerender.render_topic("nerc_ddc", rows(1), page=1, pages=1, total=1,
                                 publishers=1, site_url=SITE, indexable=False)
check('content="noindex,follow"' in lonely,
      "a subject only one publisher uses is not offered for indexing")

# --- who publishes what -------------------------------------------------
who = pagerender.render_who("Conservation Areas", [
    {"key": "a:1", "title": "Conservation Areas", "publisher": "Leeds City Council",
     "modified": "2026-01-01", "availability": "data"},
    {"key": "b:2", "title": "Conservation areas", "publisher": "Bristol City Council",
     "modified": None, "availability": "webpage"}], SITE)
check("2 UK organisations publish" in who, "the count leads the page")
check("1 of them lead to a file or an API" in who,
      "it says how many of those links are actually usable")
check("Bristol City Council" in who and "Leeds City Council" in who,
      "every publisher is named")
check(f'canonical" href="{SITE}/who-publishes?name=Conservation%20Areas"' in who,
      "the page canonicalises to its own encoded URL")

shared_notice = pagerender.render_dataset(
    record(title="Conservation Areas",
           also_published={"title": "Conservation Areas", "count": 84}), SITE)
check("83 other UK organisations publish" in shared_notice,
      "a dataset page counts the OTHER publishers, not including itself")
check('href="/who-publishes?name=Conservation%20Areas"' in shared_notice,
      "and links to the page listing them")
check("other UK organisation" not in pagerender.render_dataset(record(), SITE),
      "a dataset nobody else publishes says nothing about it")
solo = pagerender.render_dataset(
    record(also_published={"title": "Odd One Out", "count": 1}), SITE)
check("other UK organisation" not in solo,
      "a count of one is this dataset alone, so no notice")

# --- URL construction ---------------------------------------------------
check(pagerender.dataset_path("a:b c") == "/dataset?key=a%3Ab%20c",
      "dataset paths percent-encode the whole key")
check("noindex" in pagerender.render_missing("nope:nope"),
      "a 404 page is never offered for indexing")

# --- the stylesheet ------------------------------------------------------
# One file now, after three inline copies drifted apart. These pin the two
# things that silently broke while they were separate.
CSS = (Path(__file__).parent.parent / "web" / "site.css").read_text(encoding="utf-8")
dark = CSS.split("prefers-color-scheme: dark", 1)[-1]

check("--on-accent" in CSS.split("prefers-color-scheme: dark", 1)[0]
      and "--on-accent" in dark,
      "text on the accent colour is defined for BOTH schemes")
check("color: #fff" not in CSS and "color: white" not in CSS,
      "no hard-coded white text — it fails on the dark accent")
for token in ("--accent", "--ink", "--bg", "--muted", "--ok", "--warn", "--amber"):
    check(token in dark, f"{token} is redefined for dark mode")
check(".table-wrap" in CSS and "overflow-x" in CSS,
      "wide tables scroll inside their own box on a phone")
check("columns: 3" in CSS, "the publisher and subject lists are multi-column")

for page in ("index.html", "about.html", "dataset.html"):
    src = (Path(__file__).parent.parent / "web" / page).read_text(encoding="utf-8")
    check("<style>" not in src, f"{page} carries no inline stylesheet copy")
    check('href="/site.css"' in src, f"{page} links the shared stylesheet")
    check("site-header" in src, f"{page} has the shared header")

check(len(pagerender.asset_version()) >= 6,
      "the stylesheet URL carries a content hash, so a restyle is never "
      "hidden behind a cached copy")
check('href="/site.css?v=' in pagerender.render_dataset(record(), SITE),
      "and rendered pages link the hashed URL")

print()
print("all rendering rules hold" if not failures
      else f"{len(failures)} failure(s): " + "; ".join(failures))
sys.exit(1 if failures else 0)
