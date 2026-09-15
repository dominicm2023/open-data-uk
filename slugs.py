"""One short, stable path for every dataset: /dataset/<source>/<id>.

Why this exists. A dataset's key is whatever its portal used as identity,
and for ArcGIS Hub, Socrata and a few others that is a URL — so the page
address became

    /dataset?key=north_sea_transition:https://www.arcgis.com/home/item.html?id%3Dbb84...%26sublayer%3D18

113 characters with an encoded query string inside a query string. Google
reads that as a parameterised page and deprioritises it: on 4 September 2026
such pages were 89% of everything "crawled, currently not indexed" against
11% of the index, and sources with URL keys were losing 10-15% of their pages
where data.gov.uk, with UUID keys, lost 0.1%. The key stays as it is — it is
identity across dedupe, checks and embeddings — and the page gets a path
derived from it:

    /dataset/north_sea_transition/bb8456bf30844433808afaddd888bf18_18

Pure function of the key, deliberately: the canonical tag, the sitemap, the
breadcrumbs and every internal link are built without a database, and they
cannot disagree with each other. The reverse — path back to key — is one
table, built nightly (embed_index.build_slugs), which also asserts that no
two keys share a path. Where an extraction could lose distinguishing detail
(a Hub slug followed by /explore?layer=1) a digest of the whole key is
appended, so uniqueness holds by construction rather than by luck.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse

_ARCGIS = re.compile(r"[?&]id=([0-9a-f]{32})(?:&sublayer=(\d+))?")
_SOCRATA = re.compile(r"/api/views/([a-z0-9]{4}-[a-z0-9]{4})")
_LASTSEG = re.compile(r"/(?:datasets|apps|pages|maps|items?|documents)/([^/?#]+)")
# Characters a path segment may carry without percent-encoding, and which
# nothing downstream (routing, robots, sitemaps) trips over.
_PLAIN = re.compile(r"^[A-Za-z0-9._~:@+-]{1,80}$")
_SAFE = "._~:@+-"


def _digest(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def split_key(key: str) -> tuple[str, str]:
    source, _, rest = str(key).partition(":")
    return source, rest


def short_id(key: str) -> str:
    """The part after the source: the key's own id where it already is one,
    the item id extracted where the key is a URL, a digest where neither."""
    _, rest = split_key(key)
    if "://" not in rest and not any(ch in rest for ch in "?&%/"):
        cand = rest                                   # UUID, code, number
    elif rest.startswith("/"):
        # A site path, not a URL: the ONS lists one dataset under two
        # taxonomy paths and GOV.UK a release under /statistics/ and
        # /statistical-data-sets/ with the same last segment, so the
        # last segment alone clashed (8 Sep 2026, and the nightly stopped
        # at the check). The segment for reading, a digest for uniqueness.
        last = urllib.parse.unquote(rest.rstrip("/").rsplit("/", 1)[-1])[:70]
        cand = f"{last}-{_digest(key)[:6]}"
    elif (m := _ARCGIS.search(rest)):
        cand = m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")
    elif (m := _SOCRATA.search(rest)):
        cand = m.group(1)
    elif (m := _LASTSEG.search(rest)):
        cand = urllib.parse.unquote(m.group(1))
        if rest[m.end():].strip("/"):                 # something followed it
            cand = f"{cand}-{_digest(key)[:6]}"
    else:
        cand = None
    if cand is None or not _PLAIN.match(cand):
        cand = _digest(key)
    return cand


def slug_for(key: str) -> str:
    """'<source>/<id>' — unquoted, as stored in the slugs table."""
    return f"{split_key(key)[0]}/{short_id(key)}"


def _short_id_until_9_sep_2026(key: str) -> str:
    """The rule as it stood from 5 to 9 September 2026, kept verbatim.

    It had no branch for a site path (an ONS or GOV.UK key), so those fell
    through to the last-segment rule or to a bare digest. Those paths were
    announced to the search engines on 8 and 9 September and crawled for a
    week afterwards — 18,385 distinct GOV.UK paths in the seven days to
    15 September — so every one of them must still land on its page.
    """
    _, rest = split_key(key)
    if "://" not in rest and not any(ch in rest for ch in "?&%/"):
        cand = rest
    elif (m := _ARCGIS.search(rest)):
        cand = m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")
    elif (m := _SOCRATA.search(rest)):
        cand = m.group(1)
    elif (m := _LASTSEG.search(rest)):
        cand = urllib.parse.unquote(m.group(1))
        if rest[m.end():].strip("/"):
            cand = f"{cand}-{_digest(key)[:6]}"
    else:
        cand = None
    if cand is None or not _PLAIN.match(cand):
        cand = _digest(key)
    return cand


def legacy_slugs(key: str) -> list[str]:
    """Every '<source>/<id>' this key was once addressed by, other than the
    current one. A page's old addresses are redirected, never dropped: a
    search engine that was told a path exists keeps asking for it."""
    source = split_key(key)[0]
    current = short_id(key)
    return [f"{source}/{old}" for old in {_short_id_until_9_sep_2026(key)} if old != current]


def dataset_path(key: str) -> str:
    """The one canonical path for a dataset, percent-encoded for a URL."""
    source, ident = slug_for(key).split("/", 1)
    return f"/dataset/{urllib.parse.quote(source, safe=_SAFE)}/{urllib.parse.quote(ident, safe=_SAFE)}"
