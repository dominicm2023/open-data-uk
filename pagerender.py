"""Server-side rendering for dataset pages.

Every dataset page used to be the same HTML file with the same `<title>`,
filled in by JavaScript after a second round trip. That is invisible to
anything that doesn't run scripts — search engines indexing 55,000 pages,
link previews in Slack or WhatsApp, and AI crawlers alike all saw one page
called "Dataset — UK Open Data Index". Rendering here fixes that, and is
*cheaper* than it was: one request and one set of indexed lookups per page
view instead of an HTML fetch followed by an API fetch.

Nothing in this module runs the embedding model or touches the vectors —
a dataset page is three indexed SQLite reads and some string building.
"""

from __future__ import annotations

import functools
import hashlib
import html
import json
import os
import re
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
SITE_NAME = "UK Open Data Index"

# How the availability verdicts read to a person. Same wording as the search
# results, deliberately: a badge that changes meaning between pages is worse
# than no badge.
VERDICT = {
    "data": ("data", "✓ data file verified"),
    "api": ("data", "⚙ service endpoint"),
    "webpage": ("webpage", "↪ webpage — more clicking needed"),
    "dead": ("dead", "✗ link dead"),
    "blocked": ("unknown", "? couldn't verify — publisher blocked our check"),
    "unreachable": ("unknown", "? host not answering — may be temporary"),
    "nofiles": ("unknown", "no files listed by the publisher"),
}

# Licence ids we can state a canonical URL for. Only the ones we are sure of:
# schema.org treats `license` as a claim, so guessing a URL would be asserting
# a legal regime we haven't verified.
LICENSE_URLS = {
    "OGL-UK-3.0": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "OGL-UK-2.0": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/",
    "OGL-UK-1.0": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/1/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
}

_TAGS = re.compile(r"<[^>]+>")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def esc(value: object) -> str:
    """Escape for both element text and quoted attribute values."""
    return html.escape("" if value is None else str(value), quote=True)


def safe_url(url: object) -> str:
    """Publisher-supplied URLs are untrusted: only http(s) may become a link."""
    text = "" if url is None else str(url)
    return esc(text) if text[:8].lower().startswith(("http://", "https:")) else "#"


@functools.lru_cache(maxsize=1)
def source_names() -> dict[str, dict[str, str]]:
    """id -> {name, web}, from the same registry the harvester reads."""
    with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
        return {s["id"]: {"name": s["name"], "web": s.get("web", "")}
                for s in yaml.safe_load(fh)["sources"]}


def dataset_path(key: str) -> str:
    """The one canonical path for a dataset.

    Built in exactly one place so the canonical tag, the sitemap and every
    internal link agree character for character — two spellings of the same
    page is how a site ends up competing with itself in search results.
    """
    return "/dataset?key=" + urllib.parse.quote(str(key), safe="")


def publisher_path(name: str, page: int = 1) -> str:
    """The one canonical path for a publisher's datasets."""
    path = "/publisher?name=" + urllib.parse.quote(str(name), safe="")
    return path if page <= 1 else f"{path}&page={page}"


def norm_tag(tag: object) -> str:
    """Lower-case, whitespace collapsed. Publishers store tags like " Bins "."""
    return " ".join(str(tag or "").lower().split())


def topic_path(tag: str, page: int = 1) -> str:
    path = "/topic?tag=" + urllib.parse.quote(norm_tag(tag), safe="")
    return path if page <= 1 else f"{path}&page={page}"


def who_path(title: str) -> str:
    """'Who publishes X?' — the page for a dataset type many bodies publish."""
    return "/who-publishes?name=" + urllib.parse.quote(str(title), safe="")


def plain_text(value: object) -> str:
    """Publisher prose reduced to one line: no tags, no runaway whitespace."""
    return " ".join(_TAGS.sub(" ", str(value or "")).split())


def summarise(text: str, limit: int = 155) -> str:
    """Trim to a whole word, because search engines cut mid-word themselves."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.6 else cut).rstrip(" ,;:.-") + "…"


def meta_description(rec: dict) -> str:
    """One honest sentence about this dataset for a search result snippet.

    Prefers the publisher's own words. Where there are none — 571 datasets
    have no description at all — we state the facts we do hold rather than
    leave the snippet for a search engine to invent from the page furniture.
    """
    body = plain_text(rec.get("description"))
    if body:
        return summarise(body)

    src = source_names().get(rec.get("source") or "", {})
    bits = [f"{plain_text(rec.get('title')) or 'Dataset'} — open data"]
    if rec.get("publisher"):
        bits.append(f"published by {plain_text(rec['publisher'])}")
    if src.get("name"):
        bits.append(f"via {src['name']}")
    lead = " ".join(bits) + "."
    formats = [f for f in (rec.get("formats") or []) if f][:4]
    if formats:
        lead += f" {len(rec.get('resources') or [])} file(s), {', '.join(formats)}."
    lead += " The publisher gives no description."
    return summarise(lead, 200)


# Extensions we are willing to read a format out of. An allowlist, not a
# regex: a URL ending ".aspx" or ".php" would otherwise mint "ASPX" as a
# data format, which is a guess dressed as a fact.
_URL_EXT_FORMATS = {
    "csv", "tsv", "json", "geojson", "xml", "rdf", "ttl", "xlsx", "xls",
    "xlsm", "ods", "pdf", "zip", "gz", "kml", "kmz", "shp", "gpkg",
    "parquet", "txt", "doc", "docx",
}


# Licences under which the data really is free to get and reuse. Only the
# ones we can name: "isAccessibleForFree" on a bespoke corporate licence
# would be us asserting a legal position we haven't read.
OPEN_LICENSES = frozenset(LICENSE_URLS) | {
    "OGL-UK-1.0", "OGL-UK-2.0", "OGL-UK-3.0", "CC-BY-4.0", "CC-BY-SA-4.0",
    "CC0-1.0", "ODC-BY-1.0", "ODbL-1.0", "PDDL-1.0",
}

# UK-plausible bounds. A box outside these is a harvesting artefact rather
# than a claim about the world, and publishing it would put a dataset on the
# wrong continent in Dataset Search.
_BOX_LIMITS = (-180.0, 180.0, -90.0, 90.0)


def _geo_shape(bbox: object) -> str | None:
    """schema.org GeoShape "box": lower corner then upper, lat before lon.

    Emitted only when the numbers describe a real rectangle. 133 stored
    boxes are inverted or out of range — harvested rubbish — and a wrong
    box is worse than no box, because it is a confident false claim about
    where the data applies.
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        west, south, east, north = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    lon_min, lon_max, lat_min, lat_max = _BOX_LIMITS
    if not (lon_min <= west <= east <= lon_max
            and lat_min <= south <= north <= lat_max):
        return None
    return f"{south} {west} {north} {east}"


def _variables(rec: dict, limit: int = 40) -> list[str]:
    """The column names the checker read from this dataset's own files.

    Deduplicated case-insensitively — the same columns recur across a
    publisher's monthly files — but reported in the spelling the file used.
    """
    out: list[str] = []
    seen: set[str] = set()
    for res in rec.get("resources") or []:
        for col in res.get("columns") or []:
            name = plain_text(col)[:80]
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
                if len(out) >= limit:
                    return out
    return out


def _content_size(size: object) -> str | None:
    """File size with its unit, from the Content-Length we measured.

    A bare number is ambiguous — schema.org's contentSize is text, and
    readers and parsers both guess wrongly at "1200". Units are decimal
    (kB = 1000 bytes), which is what Content-Length reporting implies.
    """
    try:
        n = int(size)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    for unit, cut in (("GB", 10**9), ("MB", 10**6), ("kB", 10**3)):
        if n >= cut:
            return f"{n / cut:.1f} {unit}"
    return f"{n} B"


def distribution_format(res: dict) -> str | None:
    """The best evidence we hold for what a file actually is.

    Google Search Console flags a distribution carrying no encodingFormat,
    and 18% of stored resources have no declared format at all — the
    publisher simply never said. Three sources, in descending order of
    confidence: what the publisher declared, what the server actually
    returned when the checker fetched it, and last the extension on the
    URL. All three go through norm_format, so a distribution reads "CSV"
    however we came to know it.
    """
    from normalise import norm_format

    if declared := res.get("format_norm"):
        return declared
    # The measured answer. Parameters are stripped: "text/csv; charset=utf-8"
    # is a CSV, and the charset is not part of the format.
    if served := norm_format((res.get("content_type") or "").split(";")[0].strip()):
        return served
    tail = urllib.parse.urlsplit(str(res.get("url") or "")).path.rsplit("/", 1)[-1]
    ext = tail.rsplit(".", 1)[-1].lower() if "." in tail else ""
    return norm_format(ext) if ext in _URL_EXT_FORMATS else None


def json_ld(rec: dict, page_url: str) -> str:
    """schema.org/Dataset markup — how machines read this page.

    `isBasedOn` and the second catalogue entry are the honest part: this is
    our page *about* someone else's dataset, not a claim to have published
    it. We hold metadata only, so `distribution` points at the publisher's
    files, never at us.
    """
    src = source_names().get(rec.get("source") or "", {})
    data: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": plain_text(rec.get("title")),
        "url": page_url,
        "identifier": rec.get("key"),
    }
    # description is required for Google Dataset Search eligibility, and
    # 2,915 sitemap-listed pages emitted none because the publisher wrote
    # none. The generated snippet already exists for exactly that case and
    # states facts we hold, so machines get the same honest fallback the
    # search-result snippet does.
    desc = plain_text(rec.get("description")) or meta_description(rec)
    if desc:
        data["description"] = desc[:5000]
    if tags := [t for t in (rec.get("tags") or []) if t][:25]:
        data["keywords"] = tags
    if rec.get("publisher"):
        data["creator"] = {"@type": "Organization",
                           "name": plain_text(rec["publisher"])}
    # The licence, whether this copy stated it or a confirmed copy of the
    # same dataset did. Both are statements by the publisher about this
    # dataset; only one of them reached this particular record.
    if lic := (rec.get("license") or rec.get("license_inherited")):
        data["license"] = LICENSE_URLS.get(lic, lic)
    for field, key in (("dateModified", "modified"), ("dateCreated", "created")):
        if _ISO_DATE.match(str(rec.get(key) or "")):
            data[field] = str(rec[key])[:10]
    if rec.get("landing_url"):
        data["isBasedOn"] = rec["landing_url"]
    # When the *data* was published, as distinct from when the catalogue
    # record was last touched — a dataset can be "modified" yesterday and
    # contain nothing newer than 2011.
    if _ISO_DATE.match(str(rec.get("data_published") or "")):
        data["datePublished"] = str(rec["data_published"])[:10]
    if box := _geo_shape(rec.get("bbox")):
        data["spatialCoverage"] = {
            "@type": "Place",
            "geo": {"@type": "GeoShape", "box": box},
        }
    # The columns the checker actually read out of the file. Nobody else
    # holds these: they come from opening the CSV, not from the catalogue.
    if variables := _variables(rec):
        data["variableMeasured"] = variables
    if (rec.get("license") or rec.get("license_inherited") or "") in OPEN_LICENSES:
        data["isAccessibleForFree"] = True

    catalogues = [{"@type": "DataCatalog", "name": SITE_NAME}]
    if src.get("name"):
        entry = {"@type": "DataCatalog", "name": src["name"]}
        if src.get("web"):
            entry["url"] = src["web"]
        catalogues.append(entry)
    data["includedInDataCatalog"] = catalogues

    dists = []
    for res in (rec.get("resources") or [])[:50]:
        if not str(res.get("url") or "").lower().startswith(("http://", "https://")):
            continue
        dist: dict[str, object] = {"@type": "DataDownload", "contentUrl": res["url"]}
        if fmt := distribution_format(res):
            dist["encodingFormat"] = fmt
        if size := _content_size(res.get("size_bytes")):
            dist["contentSize"] = size
        if res.get("name"):
            dist["name"] = plain_text(res["name"])
        dists.append(dist)
    if dists:
        data["distribution"] = dists

    # "</" would close the script element early, whatever it appears inside.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def is_thin(rec: dict) -> bool:
    """Does this page hold anything a reader could use?

    A catalogue entry with no description, no files, no tags and no formats
    is a title and a link, and offering 646 of those for indexing invites a
    search engine to conclude the whole site is thin. It stays reachable and
    stays crawlable — `follow`, and still linked from the publisher's page —
    it just isn't put forward as something worth ranking.

    Deliberately an AND of everything: 2,139 records have no prose but do
    list files, and a page telling you exactly which four CSVs a council
    published is not thin, whatever its word count.
    """
    return not (
        len(plain_text(rec.get("description"))) >= 40
        or rec.get("resources")
        or [t for t in (rec.get("tags") or []) if t]
        or [f for f in (rec.get("formats") or []) if f]
    )


def breadcrumbs(trail: list[tuple[str, str | None]],
                site_url: str) -> tuple[str, str]:
    """A breadcrumb trail, as visible markup and as structured data.

    Both come out of one call on purpose. Google's structured-data
    guidelines say not to mark up what a reader can't see, and the way that
    rule gets broken is by generating the two halves in separate places and
    letting them drift. A crumb whose path is None is the current page: it
    renders as plain text and, per schema.org, carries no `item`.
    """
    items = []
    for position, (name, path) in enumerate(trail, start=1):
        entry: dict[str, object] = {"@type": "ListItem", "position": position,
                                    "name": plain_text(name)}
        if path is not None:
            entry["item"] = site_url + path
        items.append(entry)
    payload = json.dumps({"@context": "https://schema.org",
                          "@type": "BreadcrumbList",
                          "itemListElement": items},
                         ensure_ascii=False).replace("<", "\\u003c")

    links = [f'<a href="{esc(path)}">{esc(plain_text(name))}</a>' if path is not None
             else f'<span aria-current="page">{esc(plain_text(name))}</span>'
             for name, path in trail]
    sep = '<span aria-hidden="true">/</span>'
    nav = (f'<nav class="crumbs" aria-label="Breadcrumb">{sep.join(links)}</nav>')
    return nav, f'<script type="application/ld+json">{payload}</script>'


def head_tags(rec: dict, site_url: str) -> str:
    """Title, description, canonical, social preview and structured data."""
    title = plain_text(rec.get("title")) or "Dataset"
    page_url = site_url + dataset_path(rec["key"])
    desc = meta_description(rec)
    publisher = plain_text(rec.get("publisher"))

    # A duplicate is a real page — it just isn't the copy we want ranked, so
    # it points at the canonical one instead of being hidden. Retired records
    # are withdrawn by their publisher and shouldn't be in an index at all,
    # but their links still work, hence "follow".
    canonical = page_url
    robots = "index,follow"
    if rec.get("duplicate_of"):
        canonical = site_url + dataset_path(rec["duplicate_of"])
    if rec.get("retired") or is_thin(rec):
        robots = "noindex,follow"

    head = [
        f"<title>{esc(title)}{f' — {esc(publisher)}' if publisher else ''} "
        f"— {SITE_NAME}</title>",
        f'<meta name="description" content="{esc(desc)}">',
        f'<link rel="canonical" href="{esc(canonical)}">',
        f'<meta name="robots" content="{robots}">',
        f'<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{esc(page_url)}">',
        f'<meta name="twitter:card" content="summary">',
        f'<meta property="og:image" content="{site_url}/icon-512.png">',
        f'<script type="application/ld+json">{json_ld(rec, page_url)}</script>',
    ]
    return "\n".join(head)


def _chip(kind: str | None) -> str:
    if not kind or kind not in VERDICT:
        return ""
    css, label = VERDICT[kind]
    return f'<span class="chip {css}">{esc(label)}</span>'


def _size(n: object) -> str:
    if not isinstance(n, int):
        return ""
    if n > 1048576:
        return f"{n / 1048576:.1f} MB"
    return f"{round(n / 1024)} KB" if n > 1024 else f"{n} B"


def body_html(rec: dict) -> str:
    """The page itself. Same markup the client-side renderer produced."""
    src = source_names().get(rec.get("source") or "", {})
    if rec.get("license"):
        lic = f'<span class="chip lic">{esc(rec["license"])}</span>'
    elif rec.get("license_inherited"):
        # Say where it came from. The publisher stated this licence on their
        # own copy of the dataset and the aggregator dropped it, which is a
        # different thing from the publisher having stated it here — and a
        # licence is a legal claim, so the distinction is the reader's to
        # make, not ours to smooth over.
        lic = (f'<span class="chip lic">{esc(rec["license_inherited"])}</span>'
               f'<span class="note">· stated on '
               f'<a href="{esc(dataset_path(rec["license_inherited_from"]))}">'
               f'another copy of this dataset</a>, not on this record</span>')
    else:
        lic = '<span class="chip nolic">no licence stated</span>' 

    notices = []
    # Dozens of councils publish a dataset of the same name, and until now
    # each page was a dead end about one of them. This is the one link on a
    # dataset page that no publisher's own catalogue could ever offer.
    also = rec.get("also_published") or {}
    if also.get("count", 0) > 1:
        others = also["count"] - 1
        notices.append(
            f'<p class="notice">{others:,} other UK organisation'
            f'{"" if others == 1 else "s"} publish a dataset called '
            f'“{esc(also["title"])}”. '
            f'<a href="{esc(who_path(also["title"]))}">See who, and whether '
            "their links lead to real data →</a></p>")
    if rec.get("retired"):
        notices.append('<p class="notice">The publisher has marked this record '
                       'retired or superseded. It is kept here because links to '
                       'it still exist, but look for a current version.</p>')
    if rec.get("duplicate_of"):
        notices.append(
            '<p class="notice">Another portal publishes this same dataset. We '
            f'treat <a href="{esc(dataset_path(rec["duplicate_of"]))}">that copy'
            "</a> as the main one, so it is what search returns.</p>")

    rows = []
    for res in rec.get("resources") or []:
        verdict = (_chip(res.get("verdict")) or '<span class="note">unchecked</span>')
        cols = ""
        if res.get("columns"):
            shown = "".join(f"<code>{esc(c)}</code>" for c in res["columns"][:12])
            cols = (f'<div class="cols">{shown}'
                    f'{"…" if len(res["columns"]) > 12 else ""}</div>')
        label = res.get("name") or str(res.get("url") or "").rsplit("/", 1)[-1] or "resource"
        rows.append(
            f'<tr><td><a href="{safe_url(res.get("url"))}" target="_blank" rel="noopener">'
            f"{esc(label)}</a>{cols}</td>"
            f'<td>{esc(res.get("format_norm") or "?")}</td>'
            f"<td>{verdict}</td><td>{esc(_size(res.get('size_bytes')))}</td></tr>")

    files = (
        '<div class="table-wrap"><table><thead><tr><th>Resource</th>'
        '<th>Format</th><th>Verified</th><th>Size</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        if rows else
        '<p class="note">No downloadable resources listed by the publisher.</p>')

    related = "".join(
        f'<li><a href="{esc(dataset_path(r["key"]))}">{esc(r["title"])}</a></li>'
        for r in (rec.get("related") or []))

    # Tags have always been harvested and used for ranking, but never shown.
    # On the 11,000 records whose publisher wrote little or no description
    # they are most of what there is to say about the subject.
    seen, tags = set(), []
    for raw in (rec.get("tags") or []):
        key = norm_tag(raw)
        if key and key not in seen:
            seen.add(key)
            tags.append(str(raw).strip())
    tag_html = "".join(f'<a class="chip tag" href="{esc(topic_path(t))}">{esc(t)}</a>'
                       for t in tags[:20])
    formats = [f for f in (rec.get("formats") or []) if f][:8]
    fmt_html = "".join(f'<span class="chip">{esc(f)}</span>' for f in formats)

    return f"""
    <h1>{esc(rec.get("title") or "Untitled dataset")}</h1>
    <div class="meta">
      <span class="chip src">{esc(src.get("name") or rec.get("source") or "")}</span>
      {lic} {_chip(rec.get("availability"))}
      <span>{f'<a href="{esc(publisher_path(rec["publisher"]))}">{esc(rec["publisher"])}</a>'
             if rec.get("publisher") else "unknown publisher"}</span>
      {f'<span>· updated {esc(str(rec["modified"])[:10])}</span>' if rec.get("modified") else ""}
    </div>
    {"".join(notices)}
    {f'<a class="cta" href="{safe_url(rec.get("landing_url"))}" target="_blank" rel="noopener">Open at publisher ↗</a>'
     if safe_url(rec.get("landing_url")) != "#" else ""}
    {f'<div class="desc">{esc(rec["description"])}</div>' if rec.get("description") else ""}
    <h2>Files &amp; links ({len(rec.get("resources") or [])})</h2>
    {files}
    {f'<h2>Formats</h2><div class="meta">{fmt_html}</div>' if fmt_html else ""}
    {f'<h2>Subjects</h2><div class="meta">{tag_html}</div>'
      '<p class="note">Tags as the publisher recorded them — each one lists '
      'every dataset on that subject, from every portal we index.</p>' if tag_html else ""}
    {f'<h2>More from {esc(rec.get("publisher"))}</h2><ul class="related">{related}</ul>'
      f'<p class="note"><a href="{esc(publisher_path(rec["publisher"]))}">'
      f'All datasets from {esc(rec["publisher"])} →</a></p>' if related else ""}
    <p class="note">{esc(rec.get("attribution") or "")}</p>"""


@functools.lru_cache(maxsize=1)
def asset_version() -> str:
    """Short content hash of the stylesheet, for cache-busting its URL.

    Without this a restyle reaches nobody who has visited before until their
    cache expires — which is exactly how a genuine contrast fix sat invisible
    behind a day-old copy of the file. The URL changes when the bytes change,
    so the cache can be long and still always correct.
    """
    try:
        return hashlib.sha256(
            (ROOT / "web" / "site.css").read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


def with_assets(html_text: str) -> str:
    return html_text.replace('href="/site.css"',
                             f'href="/site.css?v={asset_version()}"')


@functools.lru_cache(maxsize=1)
def _template() -> str:
    return with_assets(
        (ROOT / "web" / "dataset.html").read_text(encoding="utf-8"))



def _page(head: str, body: str, current: str | None = None) -> str:
    """Assemble the shared template, marking the nav link for this section.

    aria-current tells assistive tech which nav item is the page it is on —
    the two static pages had it, the ~60k template pages did not.
    """
    page = _template().replace("<!--HEAD-->", head).replace("<!--BODY-->", body)
    if current:
        page = page.replace(f'<a href="{current}">',
                            f'<a href="{current}" aria-current="page">', 1)
    return page


def render_dataset(rec: dict, site_url: str) -> str:
    trail: list[tuple[str, str | None]] = [("Home", "/"),
                                           ("Publishers", "/publishers")]
    if rec.get("publisher"):
        trail.append((rec["publisher"], publisher_path(rec["publisher"])))
    trail.append((rec.get("title") or "Untitled dataset", None))
    crumbs, crumb_ld = breadcrumbs(trail, site_url)
    return (_template()
            .replace("<!--HEAD-->", head_tags(rec, site_url) + "\n" + crumb_ld)
            .replace("<!--BODY-->", crumbs + body_html(rec)))


def simple_head(title: str, description: str, path: str, site_url: str,
                extra: str = "") -> str:
    """Head tags for the browse pages — same shape as a dataset page's."""
    url = site_url + path
    return "\n".join([
        f"<title>{esc(title)} — {SITE_NAME}</title>",
        f'<meta name="description" content="{esc(description)}">',
        f'<link rel="canonical" href="{esc(url)}">',
        '<meta name="robots" content="index,follow">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta property="og:image" content="{site_url}/icon-512.png">',
        extra,
    ]).strip()


def _initial(name: str) -> str:
    """The heading a publisher files under. Anything non-alphabetic goes to #."""
    first = (name or "?").strip()[:1].upper()
    return first if first.isalpha() else "#"


def render_publishers(rows: list[tuple[str, int]], site_url: str) -> str:
    """Every publisher, grouped by initial.

    This page exists because the dataset pages had nothing linking to them.
    Search is the only way in, search runs on an API we ask crawlers not to
    touch, so 60,000 pages sat in the sitemap as orphans. This is the front
    door to them — and, incidentally, the browse mode the search box can't
    offer.
    """
    total = sum(n for _, n in rows)
    groups: dict[str, list[tuple[str, int]]] = {}
    for name, count in rows:
        groups.setdefault(_initial(name), []).append((name, count))
    letters = sorted(groups, key=lambda c: (c == "#", c))

    nav = " ".join(f'<a href="#{esc(c)}">{esc(c)}</a>' for c in letters)
    blocks = []
    for letter in letters:
        items = "".join(
            f'<li><a href="{esc(publisher_path(name))}">{esc(name)}</a>'
            f' <span class="note">{count:,}</span></li>'
            for name, count in groups[letter])
        blocks.append(f'<h2 id="{esc(letter)}">{esc(letter)}</h2>'
                      f'<ul class="cols">{items}</ul>')

    body = (f"<h1>Browse by publisher</h1>"
            f'<p class="note">{len(rows):,} organisations publish the '
            f"{total:,} datasets you can find through this index. Counts "
            f"exclude duplicate copies of another portal's entry and records "
            f"the publisher has withdrawn.</p>"
            f'<p class="letters">{nav}</p>' + "".join(blocks))

    head = simple_head(
        "Browse UK open data by publisher",
        f"Every one of the {len(rows):,} government bodies, councils, NHS "
        f"organisations and agencies publishing open data in the index, with "
        f"{total:,} datasets between them.",
        "/publishers", site_url)
    return _page(head, body, "/publishers")


def _dataset_items(rows: list[dict], show_publisher: bool = False) -> str:
    """One <li> per dataset — the same line wherever datasets are listed."""
    items = []
    for r in rows:
        bits = []
        if show_publisher and r.get("publisher"):
            bits.append(esc(r["publisher"]))
        if r.get("modified"):
            bits.append(f"updated {esc(str(r['modified'])[:10])}")
        if chip := _chip(r.get("availability")):
            bits.append(chip)
        meta = f' <span class="note">· {" · ".join(bits)}</span>' if bits else ""
        items.append(f'<li><a href="{esc(dataset_path(r["key"]))}">'
                     f'{esc(r["title"] or "Untitled dataset")}</a>{meta}</li>')
    return "".join(items)


def render_publisher(name: str, rows: list[dict], page: int, pages: int,
                     total: int, site_url: str, per_page: int = 100) -> str:
    """One publisher's datasets, paginated."""
    items = _dataset_items(rows)

    # From the page size, never from len(rows) — the last page is short, and
    # multiplying by its length puts the reader in the wrong part of the list.
    first = (page - 1) * per_page + 1 if rows else 0
    nav = []
    if page > 1:
        nav.append(f'<a href="{esc(publisher_path(name, page - 1))}">← previous</a>')
    if page < pages:
        nav.append(f'<a href="{esc(publisher_path(name, page + 1))}">next →</a>')

    crumbs, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Publishers", "/publishers"), (name, None)], site_url)
    body = (crumbs
            + f"<h1>{esc(name)}</h1>"
            f'<p class="note">{total:,} dataset{"" if total == 1 else "s"} in '
            f"the index"
            + (f", showing {first:,}–{first + len(rows) - 1:,} "
               f"(page {page} of {pages})" if pages > 1 else "")
            + '.</p>'
            f'<ul class="datasets">{items}</ul>'
            + (f'<p class="pager">{" · ".join(nav)}</p>' if nav else "")
            + '<p class="note"><a href="/publishers">All publishers</a></p>')

    # Only the first page carries rel=prev/next; every page self-canonicalises,
    # which is what Google wants now that it ignores prev/next for indexing.
    rel = []
    if page > 1:
        rel.append(f'<link rel="prev" href="{esc(site_url + publisher_path(name, page - 1))}">')
    if page < pages:
        rel.append(f'<link rel="next" href="{esc(site_url + publisher_path(name, page + 1))}">')

    head = simple_head(
        f"{name} — open datasets" + (f" (page {page})" if page > 1 else ""),
        f"All {total:,} datasets published by {name} that we hold, each with "
        "the licence, formats and whether the link actually leads to data.",
        publisher_path(name, page), site_url, "\n".join(rel + [crumb_ld]))
    return _page(head, body, "/publishers")


def render_topic(tag: str, rows: list[dict], page: int, pages: int, total: int,
                 publishers: int, site_url: str, per_page: int = 100,
                 indexable: bool = True) -> str:
    """Everything on one subject, from every portal at once.

    A council's own portal can only show you its own recycling data. This is
    the view no single publisher can offer, which is the whole argument for
    collating in the first place.
    """
    first = (page - 1) * per_page + 1 if rows else 0
    nav, rel = [], []
    for step, label, kind in ((-1, "← previous", "prev"), (1, "next →", "next")):
        target = page + step
        if 1 <= target <= pages:
            nav.append(f'<a href="{esc(topic_path(tag, target))}">{label}</a>')
            rel.append(f'<link rel="{kind}" href="{esc(site_url + topic_path(tag, target))}">')

    crumbs, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Subjects", "/topics"), (tag.title(), None)], site_url)
    body = (crumbs
            + f"<h1>{esc(tag.title())}</h1>"
            f'<p class="note">{total:,} dataset{"" if total == 1 else "s"} tagged '
            f'"{esc(tag)}", from {publishers:,} '
            f'organisation{"" if publishers == 1 else "s"}'
            + (f", showing {first:,}–{first + len(rows) - 1:,} "
               f"(page {page} of {pages})" if pages > 1 else "")
            + ". Tags are the publishers' own; we don't add or infer them.</p>"
            f'<ul class="datasets">{_dataset_items(rows, show_publisher=True)}</ul>'
            + (f'<p class="pager">{" · ".join(nav)}</p>' if nav else "")
            + '<p class="note"><a href="/topics">All subjects</a> · '
              '<a href="/publishers">All publishers</a></p>')

    head = simple_head(
        f"{tag.title()} — UK open data" + (f" (page {page})" if page > 1 else ""),
        f"{total:,} UK government datasets tagged \"{tag}\", from {publishers:,} "
        "publishers across every portal we index — with the licence and "
        "whether each link really leads to data.",
        topic_path(tag, page), site_url, "\n".join(rel + [crumb_ld]))
    if not indexable:
        # A tag only one publisher uses, or one with a handful of records, is
        # that publisher's private vocabulary rather than a subject. The page
        # works and stays linked; it just isn't offered up for ranking.
        head = head.replace('content="index,follow"', 'content="noindex,follow"')
    return _page(head, body, "/topics")


def render_topics(rows: list[tuple[str, int, int]], site_url: str) -> str:
    """Index of subjects worth a page of their own."""
    groups: dict[str, list[tuple[str, int, int]]] = {}
    for tag, n, pubs in rows:
        groups.setdefault(_initial(tag), []).append((tag, n, pubs))
    letters = sorted(groups, key=lambda c: (c == "#", c))

    nav = " ".join(f'<a href="#{esc(c)}">{esc(c)}</a>' for c in letters)
    blocks = []
    for letter in letters:
        items = "".join(
            f'<li><a href="{esc(topic_path(tag))}">{esc(tag)}</a>'
            f' <span class="note">{n:,}</span></li>'
            for tag, n, _ in groups[letter])
        blocks.append(f'<h2 id="{esc(letter)}">{esc(letter)}</h2>'
                      f'<ul class="cols">{items}</ul>')

    body = (f"<h1>Browse by subject</h1>"
            f'<p class="note">{len(rows):,} subjects that more than one '
            "organisation publishes data on. These are the publishers' own "
            "tags, normalised for case only — we don't invent categories, so "
            "the vocabulary is as consistent as UK open data actually is.</p>"
            f'<p class="letters">{nav}</p>' + "".join(blocks))
    head = simple_head(
        "Browse UK open data by subject",
        f"{len(rows):,} subjects — from air quality to waste collection — each "
        "listing every UK government dataset on it, from every portal at once.",
        "/topics", site_url)
    return _page(head, body, "/topics")


def render_who(title: str, rows: list[dict], site_url: str) -> str:
    """Which organisations publish this same kind of dataset.

    Genuinely unanswerable anywhere else: 91 councils publish a dataset
    called "Conservation Areas" and no portal lists them together, because
    each portal only knows its own.
    """
    items = []
    for r in sorted(rows, key=lambda r: (r.get("publisher") or "").lower()):
        bits = []
        if r.get("modified"):
            bits.append(f"updated {esc(str(r['modified'])[:10])}")
        if chip := _chip(r.get("availability")):
            bits.append(chip)
        meta = f' <span class="note">· {" · ".join(bits)}</span>' if bits else ""
        items.append(
            f'<li><a href="{esc(dataset_path(r["key"]))}">'
            f'{esc(r.get("publisher") or "unknown publisher")}</a>{meta}'
            f'<br><span class="note">{esc(r.get("title") or "")}</span></li>')

    with_data = sum(1 for r in rows if r.get("availability") in ("data", "api"))
    crumbs, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Who publishes what", "/who-publishes"), (title, None)],
        site_url)
    body = (crumbs
            + f"<h1>Who publishes “{esc(title)}” data?</h1>"
            f'<p class="note">{len(rows):,} UK organisations publish a dataset '
            f'of this name. {with_data:,} of them lead to a file or an API you '
            "can actually use; the rest lead to a webpage, are broken, or "
            "refused our checker. No single portal can show you this list, "
            "because each one only knows its own records.</p>"
            f'<ul class="datasets">{"".join(items)}</ul>'
            '<p class="note"><a href="/who-publishes">Other datasets many '
            'organisations publish</a></p>')
    head = simple_head(
        f"Who publishes {title} data? {len(rows):,} UK organisations",
        f"{len(rows):,} UK councils and public bodies publish a dataset called "
        f"\"{title}\". Every one listed, with whether the link leads to real data.",
        who_path(title), site_url, crumb_ld)
    return _page(head, body, "/who-publishes")


def render_who_index(rows: list[tuple[str, int]], site_url: str) -> str:
    """Index of dataset types that many organisations publish."""
    items = "".join(
        f'<li><a href="{esc(who_path(title))}">{esc(title)}</a>'
        f' <span class="note">{n:,} organisations</span></li>'
        for title, n in rows)
    body = ("<h1>Datasets that many organisations publish</h1>"
            f'<p class="note">{len(rows):,} kinds of dataset that three or more '
            "UK organisations each publish separately — conservation areas, "
            "spending returns, allotment registers. Each page lists every "
            "organisation publishing it, which is a question no individual "
            "portal can answer.</p>"
            f'<ul class="datasets">{items}</ul>')
    head = simple_head(
        "Datasets many UK organisations publish",
        f"{len(rows):,} kinds of dataset — conservation areas, tree preservation "
        "orders, spending returns — each listing every UK organisation that "
        "publishes one.",
        "/who-publishes", site_url)
    return _page(head, body, "/who-publishes")


def render_missing(key: str | None) -> str:
    """A 404 that is still a page, and is explicit about being a 404."""
    detail = (f"We hold no dataset with the key <code>{esc(key)}</code>."
              if key else "No dataset was named in the link you followed.")
    head = (f"<title>Dataset not found — {SITE_NAME}</title>\n"
            '<meta name="robots" content="noindex,follow">')
    body = (f"<h1>Dataset not found</h1><p class=\"note\">{detail} It may have "
            "been withdrawn by its publisher, or the link may be mistyped.</p>"
            '<p><a class="cta" href="/">Search the index</a></p>')
    return _page(head, body)


def render_findings(findings: list[dict], measured: str, site_url: str) -> str:
    """What the index knows that no single portal can see.

    Published while still being built, deliberately. Every claim here names
    real organisations, and the fastest way to find out we are wrong about
    one is to show it to them with the query attached — a council replying
    "we do publish that, you missed it" is a correction and a new source in
    the same message. That has already been the most productive way we find
    data. So the page carries the date it was measured, the query behind
    every number, and a plain route to challenge it.

    Only tiers 1-2 appear. They describe patterns; tier 3 and up name a body
    or make an argument, and every tier-3 claim the engine has produced so
    far had a cause outside our data that changed what it meant.
    """
    import charts

    auto = [f for f in findings if f.get("tier", 5) <= 2]
    cards = []
    for f in auto:
        svg = charts.render(f, measured=measured)
        # The provenance band lives inside the SVG, so a chart carries its own
        # query wherever it ends up. Repeating it in HTML underneath said "how
        # it was measured" twice on every card. When there is no chart, the
        # HTML band is the only place the query can go.
        if svg:
            body = f"<figure>{svg}</figure>"
        else:
            body = (
                '<div class="provenance">'
                '<div class="slot query"><b>How it was measured</b>'
                f'<code>{esc(f.get("sql") or "measured from the index")}</code>'
                "</div>"
                f'<div class="slot verify"><b>Measured</b>{esc(measured)}</div>'
                "</div>")
        cards.append(
            f'<article class="finding">'
            f'<h2><span class="tier">Tier {f.get("tier")}</span> '
            f'{esc(f.get("headline", ""))}</h2>'
            f'<p class="lede">{esc(f.get("detail", ""))}</p>'
            f"{body}</article>")

    held = [f for f in findings if f.get("tier", 5) > 2]
    queued = ""
    if held:
        items = "".join(f"<li>{esc(f.get('headline', ''))} "
                        f'<span class="note">tier {f.get("tier")}</span></li>'
                        for f in held)
        queued = ("<h2>Held back for a person</h2>"
                  f'<p class="note">{len(held)} further findings are not '
                  "published automatically. A claim naming one organisation "
                  "implies a cause, and the cause usually lives outside our "
                  "data: the first four this engine produced were a council "
                  "abolished in 2023, a stale copy of our own database, a "
                  "portal switched off that the national catalogue never "
                  "pruned, and files removed by a different agency. All four "
                  "were true as measurements and misleading as sentences.</p>"
                  f'<ul class="datasets">{items}</ul>')

    body = (
        "<h1>Findings</h1>"
        '<p>Things this index can see that no single portal can, because each '
        "portal only knows its own records. Every number below carries the "
        "query that produced it, so anyone — including anyone who thinks it "
        "is wrong — can re-run it.</p>"
        f'<p class="note">Measured {esc(measured)}. These figures move as we '
        "add sources, and this page is being built in the open, so expect it "
        "to change. If a finding is wrong about your organisation we want to "
        "know: <a href=\"https://github.com/dominicm2023/open-data-uk/issues\" "
        'rel="noopener">open an issue</a> and we will re-check and correct it. '
        "Telling us we have missed data you publish is the single most useful "
        "thing you can do — it is how a good share of our coverage gets "
        "found.</p>"
        + "".join(cards) + queued)

    head = simple_head(
        "Findings — what the UK's open data shows",
        f"{len(auto)} measured findings about UK open government data: dead "
        "hosting, missing licences, councils publishing nothing, and data that "
        "outlived the councils that published it. Each with the query behind it.",
        "/findings", site_url)
    return _page(head, body, "/findings")


LAB_BYLINE = os.environ.get("LAB_BYLINE", "Joined Up")


def render_lab(findings: list[dict], measured: str, site_url: str) -> str:
    """The workshop: Joined Up's livery, and the findings a person must judge.

    Behind HTTP auth at the edge, which is what makes it useful. Two things
    can happen here that must not happen in public:

    Tier 3 and up get drawn. They are exactly the claims that need a person —
    a named organisation, a join across sources, an argument — and judging one
    is much easier with the chart in front of you than as a line of text in a
    queue. Nothing here is published; this is the queue with pictures.

    And both liveries render side by side. The whole credibility model rests
    on a reader being able to tell a measurement from an argument at a glance,
    which is not a claim anyone should accept from a design document. Put them
    next to each other and it is either obvious or it isn't.
    """
    import charts

    hero = next((f for f in findings if f.get("kind") == "dead-hosts"
                 and "councils" in f.get("numbers", {})), findings[0])
    compare = (
        "<h2>The same finding, both liveries</h2>"
        '<p class="note">Left is the index: unsigned, ending in the query that '
        "produced it. Right is Joined Up: same skeleton, same chart grammar, "
        "signed. If you cannot tell them apart at a glance the separation "
        "isn't working, and the separation is the whole reason the index can "
        "claim to be neutral.</p>"
        '<div class="livery-pair">'
        f'<figure><figcaption>Index</figcaption>'
        f'{charts.render(hero, measured=measured)}</figure>'
        f'<figure class="joined-up"><figcaption>Joined Up</figcaption>'
        f'{charts.render(hero, byline=LAB_BYLINE, measured=measured)}</figure>'
        "</div>")

    by_tier: dict[int, list[dict]] = {}
    for f in findings:
        by_tier.setdefault(f.get("tier", 5), []).append(f)

    note = {
        1: "A fact about our own index. Publishes unattended.",
        2: "A pattern across many bodies. Publishes unattended.",
        3: "Names one organisation. Every one of these so far had a cause "
           "outside our data that changed what it meant — an abolished "
           "council, a decommissioned portal, files removed by a different "
           "agency. Read the chart, then go and check the cause.",
        4: "A join across sources. The join is where this goes wrong: "
           "mismatched geographies, different reporting periods, events "
           "counted as volumes. Nobody should publish one of these without "
           "having checked it themselves.",
        5: "An argument. A person writes this one, in their own name.",
    }

    blocks = []
    for tier in sorted(by_tier):
        blocks.append(f'<h2>Tier {tier}</h2><p class="note">{note[tier]}</p>')
        for f in by_tier[tier]:
            svg = charts.render(f, byline=LAB_BYLINE, measured=measured)
            figure = f"<figure>{svg}</figure>" if svg else (
                '<p class="note">No chart — this one is a prompt, not a '
                "measurement. It needs writing, not drawing.</p>")
            blocks.append(
                f'<article class="finding joined-up">'
                f'<h3>{esc(f.get("headline", ""))}</h3>'
                f'<p class="lede">{esc(f.get("detail", ""))}</p>'
                f"{figure}</article>")

    slate = ""
    slate_path = ROOT / "proposals.json"
    if slate_path.exists():
        data = json.loads(slate_path.read_text(encoding="utf-8"))
        slate = render_proposals(data.get("proposals", []),
                                 data.get("reviewed", "recently"))

    body = ("<h1>Workshop</h1>"
            "<p>Not published. This is where Joined Up's graphics get tried "
            "out, and where the findings that need a person get drawn so they "
            "can be judged rather than skimmed.</p>"
            f'<p class="note">Measured {esc(measured)}. '
            f'{len(findings)} findings. Signed as "{esc(LAB_BYLINE)}" — set '
            "<code>LAB_BYLINE</code> in the service environment to change "
            "it.</p>"
            + slate + compare + "".join(blocks))

    head = "\n".join([
        f"<title>Workshop — {SITE_NAME}</title>",
        '<meta name="robots" content="noindex,nofollow,noarchive">',
        '<meta name="referrer" content="no-referrer">',
    ])
    return _page(head, body)


VERDICT_CLASS = {
    "PROVABLE NOW": "ok",
    "NEEDS DATA FETCH": "amber",
    "MISLEADING AS FRAMED": "warn",
    "NOT SUPPORTED": "warn",
}


def render_proposals(proposals: list[dict], reviewed: str) -> str:
    """The graphics slate, with the verdict on each and why.

    This exists because a list of punchy ideas is the easy half. Fifteen
    claims that sound good will contain several the data cannot carry, and
    publishing one of those costs more credibility than the other fourteen
    earn. So each proposal keeps its verdict, its numbers, the query behind
    them, and — the part that matters — the strongest objection the
    organisation being named would make.

    Rendered as a section of the workshop, never publicly.
    """
    rows = []
    for p in proposals:
        verdict = p.get("verdict", "UNREVIEWED")
        cls = VERDICT_CLASS.get(verdict, "")
        objection = p.get("objection", "")
        claim = p.get("claim", "")
        rows.append(
            f'<article class="proposal">'
            f'<h3><span class="tier {esc(cls)}">{esc(verdict)}</span> '
            f'{esc(p.get("title", ""))}</h3>'
            + (f'<p class="lede">{esc(claim)}</p>' if claim else "")
            + (f'<p class="note"><b>Numbers.</b> {esc(p.get("numbers", ""))}</p>'
               if p.get("numbers") else "")
            + (f'<p class="note"><b>Strongest objection.</b> {esc(objection)}</p>'
               if objection else "")
            + (f'<p class="note"><b>Our own blindness.</b> '
               f'{esc(p.get("blindness", ""))}</p>' if p.get("blindness") else "")
            + (f'<details><summary>How it would be measured</summary>'
               f'<pre><code>{esc(p.get("sql", ""))}</code></pre></details>'
               if p.get("sql") else "")
            + "</article>")

    counts: dict[str, int] = {}
    for p in proposals:
        counts[p.get("verdict", "UNREVIEWED")] = \
            counts.get(p.get("verdict", "UNREVIEWED"), 0) + 1
    tally = " · ".join(f"{n} {v.lower()}" for v, n in sorted(counts.items()))

    return ("<h2>Graphics slate</h2>"
            f'<p class="note">{len(proposals)} proposed graphics, reviewed '
            f'{esc(reviewed)}. {esc(tally)}. Each was checked against the index '
            "by a separate pass whose instruction was to find reasons the "
            "claim is wrong, not to confirm it. The recurring failure is "
            'always the same shape: "they do not publish it" turning out to '
            'mean "we never looked".</p>'
            + "".join(rows))
