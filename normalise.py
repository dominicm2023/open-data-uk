"""Normalisation of the messy bits of CKAN metadata: licences, formats, dates.

Portals disagree wildly on how they record the same thing — e.g. a CSV
resource appears as "CSV", "csv", ".csv", "text/csv" or a full IANA
media-type URI depending on the portal. Everything funnels through here so
the index speaks one vocabulary.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone

# --- Unrendered templates -----------------------------------------------


def unrendered(text) -> bool:
    """True when a portal served its own template instead of a value.

    ArcGIS Hub feeds intermittently emit the Handlebars source — "{{name}}",
    "{{description}}", "{{default.description}}" — where the rendered value
    belongs. It is not a value any publisher wrote and nothing can be
    recovered from it, so every field that can carry one is checked here
    rather than in each of the six harvesters.
    """
    return "{{" in text if isinstance(text, str) else False


# --- Titles --------------------------------------------------------------


def norm_title(raw) -> str | None:
    """A usable title, or None when the portal didn't render one.

    A dataset with no title has nothing to show in search results, on a
    publisher's listing or in the FTS index, so callers treat None as "not a
    record" and drop it rather than storing a row headed "{{name}}".
    """
    title = (str(raw).strip() if raw is not None else "")
    return None if not title or unrendered(title) else title


# --- Descriptions -------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def fix_mojibake(text: str | None) -> str | None:
    """Repair double-encoded UTF-8 ("Mayorâ€™s" -> "Mayor's").

    Some publishers serve UTF-8 bytes already decoded as Latin-1, so a
    right single quote arrives as the three characters â€™. Encoding back
    to Latin-1 and decoding as UTF-8 undoes it. Only applied when the
    telltale sequence is present and the round-trip actually succeeds, so
    legitimately accented text is never mangled.
    """
    if not text or "â€" not in text:
        return text
    # cp1252, NOT latin-1: the giveaway characters € (U+20AC) and ™ (U+2122)
    # live in cp1252's 0x80-0x9F range and don't exist in latin-1 at all, so
    # a latin-1 round-trip just raises and silently repairs nothing.
    for codec in ("cp1252", "latin-1"):
        try:
            return text.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return text


def strip_html(text: str | None) -> str | None:
    """Some portals store descriptions as HTML; reduce to plain text.

    Entities have to be unescaped as well as tags removed, or "&nbsp;" and
    "&amp;" survive into the page and read as markup a reader shouldn't be
    seeing — 1,155 descriptions in the index carried a literal "&amp;".
    Unescape *after* stripping tags: doing it first would turn an escaped
    "&lt;script&gt;" into a real tag that the stripper then removes, which
    changes the author's meaning.

    An unrendered template comes back as None. Unlike a title, a description
    is not what makes a record a record: the rest of it may be perfectly
    sound, so the field is blanked and the page falls back to its generated
    summary. Every harvester runs descriptions through here, which is why the
    rule lives here rather than at each ingest point.
    """
    if not text:
        return text
    stripped = _TAG.sub(" ", fix_mojibake(text))
    plain = _WS.sub(" ", html.unescape(stripped)).strip()
    return None if unrendered(plain) else plain


# --- Dates --------------------------------------------------------------

# A date column is only useful if every value in it is a date. Ours weren't:
# one stored `modified` in six was something else, and because the column is
# read as text — sorted, sliced to a year, bucketed by age — none of it
# failed loudly. It just produced wrong answers. Three ways it happened:
#
#   1786367211609        epoch milliseconds, stored verbatim by the ArcGIS
#                        Hub feeds. Reads as the year 1786.
#   18:15                a Cefas timestamp cut at its first colon (see
#                        harvester.flatten_bag, which used to do the cutting).
#   {{modified:toISO}}   an ArcGIS Hub template the portal never rendered.
#
# Only the first is recoverable from the value itself. The rest are dropped:
# a wrong date is worse than a missing one, because "unknown" is a state the
# freshness stats and the dataset page both already handle honestly.

# The window a *metadata* timestamp can credibly fall in. Not a statement
# about the data — Cefas holds surveys from 1902 — but about the catalogue
# record, and no catalogue here predates the web. The upper bound is next
# year rather than today: publishers do post-date records, and clock skew of
# a few hours around New Year shouldn't null a good date.
DATE_FLOOR_YEAR = 1990

_EPOCH = re.compile(r"-?[0-9]{10}(?:[0-9]{3})?$")
_LEADING_YEAR = re.compile(r"([0-9]{4})(?:[^0-9]|$)")


def norm_date(value, now: datetime | None = None) -> str | None:
    """A stored date string, or None when the value isn't a date at all.

    Epoch seconds/milliseconds are converted; anything that cannot be read as
    a plausible calendar date — a template, a time fragment, a year outside
    the window above — becomes None rather than a value that only looks like
    a date until something tries to use it.

    Partial dates ("2018-12", "2023-09-29") are kept as they are: they sort
    and slice correctly, and a truncated date is still true.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or "{{" in text:
        return None

    if _EPOCH.fullmatch(text):
        divisor = 1000 if len(text.lstrip("-")) == 13 else 1
        try:
            text = datetime.fromtimestamp(
                int(text) / divisor, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OSError, OverflowError, ValueError):
            return None

    match = _LEADING_YEAR.match(text)
    if not match:
        return None
    ceiling = (now or datetime.now(timezone.utc)).year + 1
    return text if DATE_FLOOR_YEAR <= int(match.group(1)) <= ceiling else None


# --- Licences -----------------------------------------------------------

# Maps lowercased licence ids/titles (and fragments) to a canonical id.
_LICENSE_MAP = {
    "uk-ogl": "OGL-UK-3.0",
    "ogl": "OGL-UK-3.0",
    "ogl-uk-1.0": "OGL-UK-1.0",
    "ogl-uk-2.0": "OGL-UK-2.0",
    "ogl-uk-3.0": "OGL-UK-3.0",
    "open government licence": "OGL-UK-3.0",
    "cc-by": "CC-BY-4.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-sa": "CC-BY-SA-4.0",
    "cc-zero": "CC0-1.0",
    "cc0": "CC0-1.0",
    "cc-nc": "CC-NC",
    "odc-by": "ODC-BY-1.0",
    "odc-odbl": "ODbL-1.0",
    "odc-pddl": "PDDL-1.0",
    "notspecified": None,
    # Statements of absence are not licences. "No licence" as a chip looks
    # like a licence called "No licence"; the truthful rendering is the
    # same "no licence" state as an empty field.
    "no licence": None,
    "no license": None,
    "none": None,
    "unpublished": None,
    "not specified": None,
    "unspecified": None,
    "licence not specified": None,
    "license not specified": None,
    # ArcGIS Hub sends the literal string "custom" when an org configures
    # its own terms — there is no more information in the feed. Render it
    # as words rather than leaking a config token as a chip.
    "custom": "Custom licence",
    "other": "OTHER",
    "other-open": "OTHER-OPEN",
    "other-closed": "OTHER-CLOSED",
    "other-nc": "OTHER-NC",
    "other-pd": "OTHER-PD",
    "other-at": "OTHER-AT",
}


def extras_dict(extras) -> dict[str, str]:
    """CKAN extras as a plain dict, dropping empties."""
    out: dict[str, str] = {}
    for item in extras or []:
        key, value = item.get("key"), item.get("value")
        if key and value not in (None, "", "[]", "null"):
            out[str(key)] = value
    return out


def bbox_from_extras(extras) -> tuple[float, float, float, float] | None:
    """Geographic bounding box (west, south, east, north) if present.

    INSPIRE/UKLP records on data.gov.uk carry bbox-{west,south,east,north}
    on ~57% of datasets — the only machine-readable geography most of them
    have. Rejects impossible coordinates rather than trusting the publisher.
    """
    ex = extras_dict(extras)
    try:
        w = float(ex["bbox-west-long"]); s = float(ex["bbox-south-lat"])
        e = float(ex["bbox-east-long"]); n = float(ex["bbox-north-lat"])
    except (KeyError, ValueError, TypeError):
        return None
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
        return None
    if s > n:
        return None
    return (w, s, e, n)


def reference_date_from_extras(extras) -> str | None:
    """Earliest publication/creation date of the *data*.

    Distinct from CKAN's metadata_modified, which is when the catalogue
    record was last edited — a dataset can be 'modified' yesterday and
    contain nothing newer than 2011.
    """
    raw = extras_dict(extras).get("dataset-reference-date")
    if not raw:
        return None
    try:
        entries = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    dates = [e.get("value") for e in entries or []
             if isinstance(e, dict) and e.get("type") in ("publication", "creation")
             and e.get("value")]
    return min(dates) if dates else None


def update_frequency_from_extras(extras) -> str | None:
    """How often the publisher intends to update it ('notPlanned', 'annually'…).

    Matters for staleness: a one-off publication that says 'notPlanned' is
    finished, not neglected, and shouldn't be counted as rotting.
    """
    value = extras_dict(extras).get("frequency-of-update")
    return value.strip()[:40] if isinstance(value, str) and value.strip() else None


def license_from_extras(extras) -> str | None:
    """Recover a licence from CKAN 'extras'.

    data.gov.uk frequently leaves the standard license_id/license_title empty
    and records the licence in extras instead — under the *British* spelling
    'licence', or as 'license_url'. Ignoring extras made ~23% of its
    datasets look unlicensed when they are not.

    Values may be plain strings or JSON-encoded lists
    (e.g. '["Open Government Licence"]').
    """
    if not extras:
        return None

    def clean(value) -> str | None:
        if isinstance(value, list):
            value = next((v for v in value if v), None)
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text.startswith("["):
            try:
                return clean(json.loads(text))
            except (ValueError, TypeError):
                return None
        return text or None

    # Prefer a named licence; fall back to a licence URL
    named, url = None, None
    for item in extras:
        key = str(item.get("key", "")).lower()
        if "licen" not in key:
            continue
        got = clean(item.get("value"))
        if not got:
            continue
        if "url" in key:
            url = url or got
        else:
            named = named or got
    return named or url


def _collapse_repeat(text: str) -> str:
    """'NSTA Open User Licence NSTA Open User Licence' -> one copy.

    Some DCAT feeds render the licence as HTML containing the same link twice;
    stripping the tags then concatenates the duplicated text.
    """
    words = text.split()
    n = len(words)
    for size in range(1, n // 2 + 1):
        if n % size == 0 and all(words[i] == words[i % size] for i in range(n)):
            return " ".join(words[:size])
    return text


# Licence URLs that identify a specific regime. Deliberately descriptive
# rather than asserting an OGL id we haven't verified applies.
_LICENSE_URL_LABELS = {
    "https://www.ons.gov.uk/methodology/geography/licences": "ONS Geography Licence",
    "https://www.parliament.scot/about/copyright": "Scottish Parliament Copyright",
}

# The Ordnance Survey licence family arrives in 20+ spellings — with and
# without the URL, with mojibake dashes, as bare PSMA references. Substring
# rules rather than exact entries, because no two publishers paste it alike.
_OS_FAMILY = (
    ("OS INSPIRE EUL", ("public sector end user licence",
                        "end user license - inspire",
                        "inspire-licence", "inspire licence",
                        "inspire license")),
    ("OS PSMA Licence", ("psma",)),
    ("OS OpenData Licence", ("os derived open data",
                             "ordnance survey derived open data",
                             "os opendata")),
)


# Creative Commons, written every way publishers write it. Exact-match
# entries in _LICENSE_MAP caught "cc-by-4.0" but not "CC BY 4.0", so the
# index carried 308 of one and 124 of the other — the same licence, and a
# filter for either silently missed the rest.
_CC_TRIGGER = re.compile(r"creative\s*commons|creativecommons|^cc[\s\-_]?(by|0|zero)",
                         re.I)
_CC_VERSION = re.compile(r"\b([1-4])\.([05])\b")
# Longest first: "by-nc-sa" must not be read as "by-nc".
#
# The "by" has to be attached to a "cc" or a licences/ URL path, never loose.
# Matching a bare "by" anywhere read "Data published by the council; see
# creativecommons.org" as a grant of CC-BY — asserting a licence nobody gave,
# which is the one mistake this field must not make.
_CC_FLAVOURS = (
    ("CC-BY-NC-SA", r"cc[\s\-_]*by[\s\-_]*nc[\s\-_]*sa|licenses[\s\-_]+by[\s\-_]+nc[\s\-_]+sa"
                    r"|attribution[\s\-_]*non[\s\-_]*commercial[\s\-_]*share"),
    ("CC-BY-NC-ND", r"cc[\s\-_]*by[\s\-_]*nc[\s\-_]*nd|licenses[\s\-_]+by[\s\-_]+nc[\s\-_]+nd"
                    r"|attribution[\s\-_]*non[\s\-_]*commercial[\s\-_]*no[\s\-_]*deriv"),
    ("CC-BY-SA", r"cc[\s\-_]*by[\s\-_]*sa|licenses[\s\-_]+by[\s\-_]+sa"
                 r"|attribution[\s\-_]*share"),
    ("CC-BY-NC", r"cc[\s\-_]*by[\s\-_]*nc|licenses[\s\-_]+by[\s\-_]+nc"
                 r"|attribution[\s\-_]*non[\s\-_]*commercial"),
    ("CC-BY-ND", r"cc[\s\-_]*by[\s\-_]*nd|licenses[\s\-_]+by[\s\-_]+nd"
                 r"|attribution[\s\-_]*no[\s\-_]*deriv"),
    ("CC-BY", r"cc[\s\-_]*by\b|licenses[\s\-_]+by\b|\battribution\b"),
)


def _creative_commons(key: str) -> str | None:
    """Canonical CC identifier from any spelling, or None if it isn't CC."""
    if not _CC_TRIGGER.search(key):
        return None
    # Punctuation to spaces, so "CC-BY-SA_4.0" and "CC BY SA 4.0" are one
    # shape. The version is read before flattening, as it contains a dot.
    version = _CC_VERSION.search(key)
    flat = " ".join(re.sub(r"[^a-z0-9.]+", " ", key.lower()).split())

    if re.search(r"\bcc0\b|\bcczero\b|\bzero\b|publicdomain|public domain", flat):
        return "CC0-1.0"
    for canonical, pattern in _CC_FLAVOURS:
        if re.search(pattern, flat):
            v = f"{version.group(1)}.{version.group(2)}" if version else "4.0"
            return f"{canonical}-{v}"
    return None


def norm_license(license_id: str | None, license_title: str | None = None) -> str | None:
    """Return a canonical licence id, or None if absent/unspecified."""
    for raw in (license_id, license_title):
        if not raw or not raw.strip():
            continue
        raw = html.unescape(_collapse_repeat(" ".join(raw.split())))
        key = raw.strip().lower()
        if key.rstrip("/") in _LICENSE_URL_LABELS:
            return _LICENSE_URL_LABELS[key.rstrip("/")]
        if key in _LICENSE_MAP:
            # A mapping to None is a statement of absence ("no licence",
            # "notspecified") — fall through to the next field rather than
            # letting an empty id shadow a real title.
            if _LICENSE_MAP[key] is None:
                continue
            return _LICENSE_MAP[key]
        if "open government licence" in key or "open government license" in key:
            return "OGL-UK-3.0"
        if cc := _creative_commons(key):
            return cc
        for label, needles in _OS_FAMILY:
            if any(n in key for n in needles):
                return label
        if key.startswith("http"):
            if "open-government-licence" in key:
                return "OGL-UK-3.0"
            if "creativecommons.org/licenses/by/" in key:
                return "CC-BY-4.0"
            if "creativecommons.org/publicdomain" in key:
                return "CC0-1.0"
        # Unrecognised: repair the encoding, then decide whether it is a
        # *name* or a *text*. A short string ("NSTA Open User Licence") is a
        # licence's name and worth showing; a paragraph pasted out of Word
        # is the publisher's own terms, and truncating it mid-word into a
        # 60-character chip ("Data is freely available for resear...") told
        # readers nothing — 458 distinct fragments across 4,684 datasets.
        text = (fix_mojibake(raw) or raw).strip()
        return text if len(text) <= 60 else "Custom licence"
    return None


# --- Formats ------------------------------------------------------------

# IANA media type (with or without the full registry URI) -> canonical format.
_MEDIA_TYPE_MAP = {
    "text/csv": "CSV",
    "application/csv": "CSV",
    "application/json": "JSON",
    "application/ld+json": "JSON-LD",
    "application/vnd.geo+json": "GEOJSON",
    "application/geo+json": "GEOJSON",
    "application/parquet": "PARQUET",
    "application/vnd.apache.parquet": "PARQUET",
    "application/rdf+xml": "RDF",
    "text/turtle": "TURTLE",
    "text/n3": "N3",
    "application/n-triples": "N-TRIPLES",
    "application/xml": "XML",
    "text/xml": "XML",
    "application/pdf": "PDF",
    "text/html": "HTML",
    "application/zip": "ZIP",
    "application/vnd.ms-excel": "XLS",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/vnd.oasis.opendocument.spreadsheet": "ODS",
    "application/vnd.ms-excel.sheet.binary.macroenabled.12": "XLSB",
    "application/vnd.ms-excel.sheet.macroenabled.12": "XLSM",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/msword": "DOC",
    "application/geopackage+sqlite3": "GPKG",
    "application/vnd.google-earth.kml+xml": "KML",
    "application/vnd.google-earth.kmz": "KMZ",
    "text/tab-separated-values": "TSV",
    "text/plain": "TXT",
}

# Loose spellings seen in the wild -> canonical format.
# Multi-word format labels. norm_format() only passes through single tokens,
# so anything with a space in it was dropped outright — which is why 4,767
# resources pointing at an ArcGIS REST service carried no format at all, and
# the API's `format` filter could never find them. Esri writes the same thing
# four ways; they collapse to one name here, as licences do.
_FORMAT_ALIASES = {
    "esri rest": "ESRI-REST",
    "esri map service": "ESRI-REST",
    "esri feature service": "ESRI-REST",
    "esri image service": "ESRI-REST",
    "arcgis geoservices rest api": "ESRI-REST",
    "geoservice": "ESRI-REST",
    "arcgis hub dataset": "HTML",       # a portal page, not a service
    "web page": "HTML",
    "esri shapefile": "SHP",
    "esri file geodatabase": "GDB",
    "open geospatial consortium wms": "WMS",
    "open geospatial consortium wfs": "WFS",
    "comma separated values": "CSV",
    "microsoft excel": "XLSX",
    "plain text": "TXT",
    "csv": "CSV",
    ".csv": "CSV",
    "csv file": "CSV",
    "comma separated values": "CSV",
    "xls": "XLS",
    "xlsx": "XLSX",
    "excel": "XLSX",
    "spreadsheet": "XLSX",
    "json": "JSON",
    "geojson": "GEOJSON",
    "kml": "KML",
    "kmz": "KMZ",
    "shp": "SHP",
    "shapefile": "SHP",
    "esri shapefile": "SHP",
    "wms": "WMS",
    "wfs": "WFS",
    "pdf": "PDF",
    "doc": "DOC",
    "docx": "DOCX",
    "html": "HTML",
    "htm": "HTML",
    "web page": "HTML",
    "website": "HTML",
    "url": "HTML",
    "link": "HTML",
    "api": "API",
    "rest api": "API",
    "sparql": "SPARQL",
    "rdf": "RDF",
    "xml": "XML",
    "txt": "TXT",
    "text": "TXT",
    "zip": "ZIP",
    "ods": "ODS",
    "parquet": "PARQUET",
    "geopackage": "GPKG",
    "gpkg": "GPKG",
}

_IANA_PREFIX = re.compile(r"^https?://www\.iana\.org/assignments/media-types/", re.I)


def norm_format(raw: str | None) -> str | None:
    """Return a canonical format label, or None if it can't be recognised."""
    if not raw or not raw.strip():
        return None
    # A leading dot is a file extension being offered as a format (".XLSX",
    # ".PDF") — 2,194 resources carried one and fell through the alias table
    # to become their own filter-invisible tokens.
    fmt = _IANA_PREFIX.sub("", raw.strip()).strip().lstrip(".")
    lower = fmt.lower()
    if lower in _MEDIA_TYPE_MAP:
        return _MEDIA_TYPE_MAP[lower]
    if lower in _FORMAT_ALIASES:
        return _FORMAT_ALIASES[lower]
    # Unknown but plausibly already a format token ("NetCDF", "GML", ...)
    if re.fullmatch(r"[A-Za-z0-9+.\-]{1,20}", fmt):
        return fmt.upper()
    return None


def norm_formats(raws: list[str | None]) -> list[str]:
    """Normalise and de-duplicate a list of raw format strings, keeping order."""
    seen: dict[str, None] = {}
    for raw in raws:
        fmt = norm_format(raw)
        if fmt:
            seen.setdefault(fmt, None)
    return list(seen)
