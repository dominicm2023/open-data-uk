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

# --- URL construction ---------------------------------------------------
check(pagerender.dataset_path("a:b c") == "/dataset?key=a%3Ab%20c",
      "dataset paths percent-encode the whole key")
check("noindex" in pagerender.render_missing("nope:nope"),
      "a 404 page is never offered for indexing")

print()
print("all rendering rules hold" if not failures
      else f"{len(failures)} failure(s): " + "; ".join(failures))
sys.exit(1 if failures else 0)
