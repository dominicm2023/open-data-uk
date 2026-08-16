"""Crawl the live site the way a search engine would, and check what it finds.

The unit tests cover rendering with made-up records. This covers the thing
they can't: real data through the real stack. It walks from the home page
outwards without JavaScript, samples every page type, and asserts the
invariants that make the site indexable at all — a unique title, a canonical
URL, a robots directive, no unfilled template placeholder, and no broken
internal link.

It is deliberately polite: a small sample per type, one request at a time,
with a pause between. Running it against production should be indistinguishable
from one curious visitor.

Usage:
    python scripts/site_check.py                       # against the live site
    python scripts/site_check.py http://127.0.0.1:8055 # against a local one
    python scripts/site_check.py --sample 12
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS  # noqa: E402

UA = HEADERS
PAUSE = 0.3          # seconds between requests — we are a guest on our own box

failures: list[str] = []
seen_titles: Counter = Counter()


def fetch(base: str, path: str, tries: int = 3) -> tuple[int, str]:
    url = base + path
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception:
            if attempt == tries - 1:
                return 0, ""
            time.sleep(2)
    return 0, ""


def links(body: str, prefix: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(r'href="([^"]+)"', body)
            if h.startswith(prefix)]


def one(pattern: str, body: str) -> str | None:
    m = re.search(pattern, body, re.S)
    return m.group(1) if m else None


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")
    failures.append(msg)


def check_page(base: str, path: str, kind: str, expect_index: bool | None = None) -> str:
    """Fetch one page and assert what every indexable page must have."""
    status, body = fetch(base, path)
    if status != 200:
        fail(f"[{kind}] {path} returned {status}")
        return ""

    if "<!--HEAD-->" in body or "<!--BODY-->" in body:
        fail(f"[{kind}] {path} shipped an unfilled template placeholder")

    title = one(r"<title>(.*?)</title>", body)
    if not title:
        fail(f"[{kind}] {path} has no <title>")
    else:
        seen_titles[title] += 1

    desc = one(r'<meta name="description" content="(.*?)"', body)
    if not desc or len(desc) < 30:
        fail(f"[{kind}] {path} has no usable meta description")

    canonical = one(r'<link rel="canonical" href="(.*?)"', body)
    if not canonical:
        fail(f"[{kind}] {path} has no canonical URL")
    elif not canonical.startswith(("http://", "https://")):
        fail(f"[{kind}] {path} canonical is not absolute: {canonical}")

    robots = one(r'<meta name="robots" content="(.*?)"', body)
    if not robots:
        fail(f"[{kind}] {path} states no robots directive")
    elif expect_index is True and robots.startswith("noindex"):
        fail(f"[{kind}] {path} is noindex but should be indexable")
    elif expect_index is False and not robots.startswith("noindex"):
        fail(f"[{kind}] {path} should be noindex, says {robots!r}")

    return body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", nargs="?", default="https://open-data.org.uk")
    ap.add_argument("--sample", type=int, default=6,
                    help="pages to check per type (default 6)")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    n = args.sample
    print(f"checking {base}, {n} pages per type\n")

    # --- the front door -------------------------------------------------
    status, home = fetch(base, "/")
    if status != 200:
        print(f"FAIL home page returned {status} — stopping")
        return 1
    print("home page: 200")
    for hub in ("/publishers", "/topics", "/who-publishes"):
        if not links(home, hub):
            fail(f"[home] nothing links to {hub}")
    print()

    # --- robots and sitemaps --------------------------------------------
    status, robots_txt = fetch(base, "/robots.txt")
    if status != 200 or "Sitemap:" not in robots_txt:
        fail("[robots] robots.txt missing or names no sitemap")
    if "Disallow: /api/" not in robots_txt:
        fail("[robots] /api/ is not disallowed — crawlers will run the search")
    status, index_xml = fetch(base, "/sitemap.xml")
    children = re.findall(r"<loc>(.*?)</loc>", index_xml)
    if status != 200 or not children:
        fail("[sitemap] index missing or empty")
    print(f"robots.txt and sitemap index: {len(children)} child sitemaps")
    print()

    # --- each hub, then a sample of its children ------------------------
    for hub, prefix, kind in (("/publishers", "/publisher?", "publisher"),
                              ("/topics", "/topic?", "subject"),
                              ("/who-publishes", "/who-publishes?", "who-publishes")):
        body = check_page(base, hub, f"{kind} index", expect_index=True)
        if not body:
            continue
        children = links(body, prefix)
        print(f"{hub}: 200, {len(children):,} children")
        # Spread the sample across the list rather than taking the first few,
        # which are alphabetical and all look alike.
        step = max(1, len(children) // n)
        for path in children[::step][:n]:
            time.sleep(PAUSE)
            page = check_page(base, path, kind)
            if page and not links(page, "/dataset?"):
                fail(f"[{kind}] {path} lists no datasets")
        print(f"  sampled {min(n, len(children))} {kind} pages")
    print()

    # --- dataset pages, reached the way a crawler reaches them ----------
    _, pubs = fetch(base, "/publishers")
    _, one_pub = fetch(base, links(pubs, "/publisher?")[0])
    datasets = links(one_pub, "/dataset?")
    for path in datasets[:n]:
        time.sleep(PAUSE)
        body = check_page(base, path, "dataset")
        if body and not links(body, "/publisher?"):
            fail(f"[dataset] {path} does not link back to its publisher")
    print(f"dataset pages: sampled {min(n, len(datasets))}")

    # --- pages that must NOT be offered for indexing --------------------
    time.sleep(PAUSE)
    status, _ = fetch(base, "/dataset?key=definitely-not-a-real-key")
    if status != 404:
        fail(f"[404] an unknown dataset key returned {status}, not 404")
    time.sleep(PAUSE)
    status, _ = fetch(base, "/publisher?name=No%20Such%20Organisation")
    if status != 404:
        fail(f"[404] an unknown publisher returned {status}, not 404")
    print("unknown keys 404 correctly")

    # --- duplicate titles are a ranking problem -------------------------
    dupes = [(t, c) for t, c in seen_titles.items() if c > 1]
    if dupes:
        for t, c in dupes[:5]:
            fail(f"[titles] {c} sampled pages share the title {t[:60]!r}")

    print()
    if failures:
        print(f"{len(failures)} problem(s) found")
        return 1
    print(f"all checks passed across {sum(seen_titles.values())} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
