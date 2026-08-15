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
import html
import json
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
    if desc := plain_text(rec.get("description")):
        data["description"] = desc[:5000]
    if tags := [t for t in (rec.get("tags") or []) if t][:25]:
        data["keywords"] = tags
    if rec.get("publisher"):
        data["creator"] = {"@type": "Organization",
                           "name": plain_text(rec["publisher"])}
    if lic := rec.get("license"):
        data["license"] = LICENSE_URLS.get(lic, lic)
    for field, key in (("dateModified", "modified"), ("dateCreated", "created")):
        if _ISO_DATE.match(str(rec.get(key) or "")):
            data[field] = str(rec[key])[:10]
    if rec.get("landing_url"):
        data["isBasedOn"] = rec["landing_url"]

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
        if res.get("format_norm"):
            dist["encodingFormat"] = res["format_norm"]
        if res.get("name"):
            dist["name"] = plain_text(res["name"])
        dists.append(dist)
    if dists:
        data["distribution"] = dists

    # "</" would close the script element early, whatever it appears inside.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


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
    if rec.get("retired"):
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
    lic = (f'<span class="chip lic">{esc(rec["license"])}</span>' if rec.get("license")
           else '<span class="chip nolic">no licence stated</span>')

    notices = []
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
            f'<tr><td><a href="{safe_url(res.get("url"))}" rel="noopener">'
            f"{esc(label)}</a>{cols}</td>"
            f'<td>{esc(res.get("format_norm") or "?")}</td>'
            f"<td>{verdict}</td><td>{esc(_size(res.get('size_bytes')))}</td></tr>")

    files = (
        '<table><thead><tr><th>Resource</th><th>Format</th><th>Verified</th>'
        f'<th>Size</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
        if rows else
        '<p class="note">No downloadable resources listed by the publisher.</p>')

    related = "".join(
        f'<li><a href="{esc(dataset_path(r["key"]))}">{esc(r["title"])}</a></li>'
        for r in (rec.get("related") or []))

    return f"""
    <h1>{esc(rec.get("title") or "Untitled dataset")}</h1>
    <div class="meta">
      <span class="chip src">{esc(src.get("name") or rec.get("source") or "")}</span>
      {lic} {_chip(rec.get("availability"))}
      <span>{esc(rec.get("publisher") or "unknown publisher")}</span>
      {f'<span>· updated {esc(str(rec["modified"])[:10])}</span>' if rec.get("modified") else ""}
    </div>
    {"".join(notices)}
    <a class="cta" href="{safe_url(rec.get("landing_url"))}" rel="noopener">Open at publisher ↗</a>
    {f'<div class="desc">{esc(rec["description"])}</div>' if rec.get("description") else ""}
    <h2>Files &amp; links ({len(rec.get("resources") or [])})</h2>
    {files}
    {f'<h2>More from {esc(rec.get("publisher"))}</h2><ul class="related">{related}</ul>' if related else ""}
    <p class="note">{esc(rec.get("attribution") or "")}</p>"""


@functools.lru_cache(maxsize=1)
def _template() -> str:
    return (ROOT / "web" / "dataset.html").read_text(encoding="utf-8")


def render_dataset(rec: dict, site_url: str) -> str:
    return (_template()
            .replace("<!--HEAD-->", head_tags(rec, site_url))
            .replace("<!--BODY-->", body_html(rec)))


def render_missing(key: str | None) -> str:
    """A 404 that is still a page, and is explicit about being a 404."""
    detail = (f"We hold no dataset with the key <code>{esc(key)}</code>."
              if key else "No dataset was named in the link you followed.")
    head = (f"<title>Dataset not found — {SITE_NAME}</title>\n"
            '<meta name="robots" content="noindex,follow">')
    body = (f"<h1>Dataset not found</h1><p class=\"note\">{detail} It may have "
            "been withdrawn by its publisher, or the link may be mistyped.</p>"
            '<p><a class="cta" href="/">Search the index</a></p>')
    return _template().replace("<!--HEAD-->", head).replace("<!--BODY-->", body)
