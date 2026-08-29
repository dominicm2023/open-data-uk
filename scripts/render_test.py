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

# --- hostile publisher content -----------------------------------------
nasty = pagerender.render_dataset(
    record(title=XSS, description=f"harmless {XSS}",
           publisher='" onmouseover="evil()',
           resources=[{"url": "javascript:alert(1)", "name": XSS,
                       "format_norm": "CSV", "verdict": "data",
                       "size_bytes": None, "columns": [XSS]}]), SITE)
check("<script>alert" not in nasty, "a script tag in the title cannot execute")
# Counting to 1 broke the moment a second legitimate block (BreadcrumbList)
# was added, which is the wrong thing to be counting: the property that
# matters is that no script element exists which isn't ours.
check(nasty.count("<script") == nasty.count('<script type="application/ld+json">'),
      "every script element on the page is our own JSON-LD, none injected")
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

# --- every distribution says what format it is -------------------------
# Google Search Console flagged distributions with no encodingFormat. The
# publisher's declaration is preferred, the checker's observed content type
# is the fallback, and the URL extension is the last resort — but only from
# an allowlist, so a ".aspx" page never becomes a data format.
_df = pagerender.distribution_format
check(_df({"format_norm": "CSV", "content_type": "text/html",
           "url": "http://x/a"}) == "CSV",
      "a declared format outranks the served content type")
check(_df({"format_norm": None, "content_type": "text/csv; charset=utf-8",
           "url": "http://x/a"}) == "CSV",
      "an undeclared format falls back to what the server served")
check(_df({"format_norm": None, "content_type": None,
           "url": "http://x/data.csv?token=1"}) == "CSV",
      "and last to the URL's extension, ignoring the query string")
check(_df({"format_norm": None, "content_type": None,
           "url": "http://x/page.aspx"}) is None,
      "'.aspx' is a page, not a data format, so nothing is claimed")
check(_df({"format_norm": None, "content_type": None,
           "url": "http://x/download"}) is None,
      "with no evidence at all we say nothing rather than guess")

_ld = json.loads(pagerender.json_ld(record(), SITE + "/dataset?key=x"))
check(all("encodingFormat" in d for d in _ld.get("distribution", [])),
      "every emitted distribution carries an encodingFormat")

# --- the evidence we hold but used not to publish ----------------------
# A bounding box is what Dataset Search filters geographically on, and a
# wrong box is worse than none: it is a confident false claim about where
# the data applies.
check(pagerender._geo_shape([-1.6, 52.4, -1.3, 52.6]) == "52.4 -1.6 52.6 -1.3",
      "a bbox becomes a GeoShape box, lower corner first, lat before lon")
check(pagerender._geo_shape([2.0, 52.0, -1.0, 51.0]) is None,
      "an inverted bbox is harvesting rubbish and is not published")
check(pagerender._geo_shape([-1.0, 52.0, 999.0, 53.0]) is None,
      "nor is one that runs off the planet")
check(pagerender._geo_shape(None) is None and pagerender._geo_shape([1, 2]) is None,
      "a missing or malformed bbox says nothing")

check(pagerender._content_size(2_450_000) == "2.5 MB"
      and pagerender._content_size(900) == "900 B",
      "a measured file size carries its unit, since '1200' is ambiguous")
check(pagerender._content_size(0) is None and pagerender._content_size(None) is None,
      "an unmeasured file size is not invented")

_geo_rec = dict(record(), bbox=[-1.6, 52.4, -1.3, 52.6],
                data_published="2011-06-01", license="OGL-UK-3.0")
_gl = json.loads(pagerender.json_ld(_geo_rec, SITE + "/dataset?key=x"))
check(_gl.get("spatialCoverage", {}).get("geo", {}).get("box"),
      "a sound bbox reaches the page as spatialCoverage")
check(_gl.get("datePublished") == "2011-06-01",
      "the data's own publication date is distinct from the record's")
check(_gl.get("isAccessibleForFree") is True,
      "a known open licence says so outright")
check("isAccessibleForFree" not in json.loads(
          pagerender.json_ld(dict(_geo_rec, license="Custom licence"), SITE)),
      "a bespoke licence makes no claim about free access")

# --- breadcrumbs: the markup and the page must say the same thing ------
# Google's structured-data guidelines forbid marking up what a reader can't
# see, and the way that rule gets broken is by generating the two halves
# apart and letting them drift. breadcrumbs() returns both from one call.
_crumb_html = pagerender.render_dataset(record(), SITE)
_crumb_ld = [json.loads(b) for b in
             re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                        _crumb_html, re.S) if "BreadcrumbList" in b]
check(len(_crumb_ld) == 1, "a dataset page carries exactly one BreadcrumbList")
_items = _crumb_ld[0]["itemListElement"]
check([i["position"] for i in _items] == list(range(1, len(_items) + 1)),
      "breadcrumb positions run 1..n with no gaps")
check("item" not in _items[-1],
      "the last crumb is the current page, so carries no item URL")
check(all("item" in i for i in _items[:-1]),
      "every crumb above it links somewhere")
_nav = re.search(r'<nav class="crumbs".*?</nav>', _crumb_html, re.S)
check(_nav is not None, "and the trail is actually visible on the page")
_seen = [v for v in re.findall(r'>([^<>]+)</(?:a|span)>', _nav.group(0)) if v != "/"]
check(_seen == [i["name"] for i in _items],
      "the visible trail and the structured data name the same steps")

_no_pub = dict(record())
_no_pub.pop("publisher", None)
_np_ld = [json.loads(b) for b in
          re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                     pagerender.render_dataset(_no_pub, SITE), re.S)
          if "BreadcrumbList" in b][0]
check(len(_np_ld["itemListElement"]) == 3,
      "a dataset with no publisher skips that crumb rather than inventing one")

# --- a licence recovered from a merged twin ----------------------------
# If we were confident enough to call two records one dataset, a licence one
# copy states is a fact about that dataset. But a licence is a legal claim,
# so the page has to say the statement came from elsewhere.
_inh = dict(record(), license=None,
            license_inherited="OGL-UK-3.0",
            license_inherited_from="datamillnorth:abc")
_inh_html = pagerender.render_dataset(_inh, SITE)
check("OGL-UK-3.0" in _inh_html,
      "an inherited licence is shown rather than withheld")
check("another copy of this dataset" in _inh_html,
      "and the page says the statement came from another copy")
_inh_ld = json.loads(re.search(
    r'<script type="application/ld\+json">(.*?)</script>', _inh_html, re.S).group(1))
check(_inh_ld.get("license", "").endswith("/version/3/"),
      "the structured data carries it too, as its canonical URL")
check(_inh_ld.get("isAccessibleForFree") is True,
      "and a known open licence still says so")
check('class="chip nolic"' not in _inh_html,
      "the record no longer claims no licence exists anywhere")

_none = dict(record(), license=None, license_inherited=None)
check('class="chip nolic"' in pagerender.render_dataset(_none, SITE),
      "a dataset with no licence anywhere still says so plainly")

# --- the search snippet earns the click -------------------------------
# Our result appears beside the publisher's own. Carrying the same words
# gave no reason to prefer us: 443 impressions at positions 5-10 returned
# five clicks. The snippet now leads with what only this index measured.
_snip = pagerender.search_snippet(dict(
    record(), availability="data", formats=["CSV"], license="OGL-UK-3.0",
    also_published={"count": 227}))
check(_snip.startswith("CSV"), "the snippet leads with the formats really there")
check("checked and working" in _snip,
      "and says the links were checked, which the publisher's page cannot")
check("226 other UK bodies" in _snip,
      "and the count no single portal could ever state")
check("Hourly readings" in _snip,
      "the publisher's own words still follow, in the space left")
check(len(_snip) <= 160, f"it fits a search result ({len(_snip)} chars)")

check("currently broken" in pagerender.search_snippet(
          dict(record(), availability="dead", formats=["CSV"])),
      "a dead dataset says so in the snippet rather than hiding it")
check(pagerender.search_snippet(dict(record(), availability=None, formats=[],
                                     resources=[], license=None,
                                     license_inherited=None, also_published=None))
      .startswith("Hourly readings"),
      "with nothing measured to add, the publisher's words lead alone")
_bare = pagerender.search_snippet(dict(record(), description=None,
                                       availability="webpage", formats=["HTML"]))
check(len(_bare) > 60 and "Air Quality" in _bare,
      "a description-less record still gets a full snippet, not six words")

# --- pagination is how deep pages earn a crawl -------------------------
# With previous/next only, the last dataset a big publisher holds sat 54
# clicks from its own first page: 53,915 of 83,370 dataset pages, 65% of
# the site, reachable in practice only from the sitemap.
_big = pagerender.render_publisher(AMP, rows(100), page=1, pages=54,
                                   total=5360, site_url=SITE)
_nav = re.search(r'<nav class="pager".*?</nav>', _big, re.S)
check(_nav is not None, "a multi-page listing carries a numbered pager")
check(len(re.findall(r'href="', _nav.group(0))) >= 53,
      "every page of a 54-page listing is one click from the first")
check('rel="next"' in _nav.group(0) and 'rel="prev"' not in _nav.group(0),
      "page 1 declares next but has no previous")

_mid = re.search(r'<nav class="pager".*?</nav>',
                 pagerender.render_topic("england", rows(100), page=150,
                                         pages=300, total=30000, publishers=40,
                                         site_url=SITE), re.S).group(0)
_seen = {int(n) for n in re.findall(r'page=(\d+)"', _mid)}
check(300 in _seen and 299 in _seen,
      "past the link budget it elides but still reaches the last page")
check(149 in _seen and 151 in _seen, "and keeps a window around the current page")
check('aria-current="page"' in _mid, "the current page is marked, not linked")
check("/topic?tag=england\"" in _mid,
      "page 1 is linked at its canonical URL, without a page parameter")

check('class="pager"' not in pagerender.render_publisher(
          "Tiny", rows(5), page=1, pages=1, total=5, site_url=SITE),
      "a single-page listing shows no pager at all")

print()
print("all rendering rules hold" if not failures
      else f"{len(failures)} failure(s): " + "; ".join(failures))
sys.exit(1 if failures else 0)
