"""Harvest dataset metadata from the CKAN portals listed in sources.yaml
into a single normalised SQLite index (index.db).

Usage:
    python harvester.py                  # harvest every source, no cap
    python harvester.py --limit 2500     # cap datasets per source (prototyping)
    python harvester.py --source nhsbsa  # harvest one source only

Only metadata is fetched — never the data files themselves. Each run
upserts, so re-running refreshes the index in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
import yaml

from normalise import (bbox_from_extras, license_from_extras, norm_date,
                       norm_formats, norm_license, norm_title,
                       reference_date_from_extras, strip_html, unrendered,
                       update_frequency_from_extras)

GEO_UPSERT = """
INSERT OR REPLACE INTO dataset_geo
    (dataset_key, bbox_west, bbox_south, bbox_east, bbox_north,
     update_frequency, reference_date)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def geo_row(key: str, pkg: dict) -> tuple | None:
    """Geography/cadence row for a CKAN package, or None if it has neither."""
    extras = pkg.get("extras")
    bbox = bbox_from_extras(extras)
    freq = update_frequency_from_extras(extras)
    ref = reference_date_from_extras(extras)
    if not (bbox or freq or ref):
        return None
    w, s, e, n = bbox if bbox else (None, None, None, None)
    return (key, w, s, e, n, freq, ref)

ROOT = Path(__file__).parent
from agent import USER_AGENT  # noqa: E402  (see agent.py: the wording matters)
from paths import DB_PATH, connect as db_connect  # noqa: E402
PAGE_SIZE = 500  # CKAN caps rows at 1000; 500 keeps responses a sane size

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    key             TEXT PRIMARY KEY,   -- "<source_id>:<ckan id>"
    source_id       TEXT NOT NULL,
    ckan_id         TEXT NOT NULL,
    name            TEXT,               -- CKAN slug
    title           TEXT,
    description     TEXT,
    publisher       TEXT,
    license_raw     TEXT,
    license_norm    TEXT,
    created         TEXT,
    modified        TEXT,
    landing_url     TEXT,
    tags            TEXT,               -- JSON array
    formats_raw     TEXT,               -- JSON array, as the portal reported
    formats_norm    TEXT,               -- JSON array, canonical
    resource_count  INTEGER,
    harvested_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_datasets_source ON datasets (source_id);
-- "More from this publisher" on every dataset page. Without this it is a
-- full scan plus a sort of the whole table: measured at 97 ms per page view
-- against 65k rows, which is the entire cost of the page.
CREATE INDEX IF NOT EXISTS idx_datasets_publisher
    ON datasets (publisher, modified DESC);

-- Geography and update cadence recovered from CKAN "extras". Kept in its own
-- table so the main dataset row shape (and its positional UPSERT) is untouched.
CREATE TABLE IF NOT EXISTS dataset_geo (
    dataset_key      TEXT PRIMARY KEY,
    bbox_west        REAL,
    bbox_south       REAL,
    bbox_east        REAL,
    bbox_north       REAL,
    update_frequency TEXT,
    reference_date   TEXT
);

CREATE TABLE IF NOT EXISTS resources (
    dataset_key TEXT NOT NULL,
    url         TEXT NOT NULL,
    name        TEXT,
    format_norm TEXT,
    PRIMARY KEY (dataset_key, url)
);
CREATE INDEX IF NOT EXISTS idx_resources_dataset ON resources (dataset_key);

CREATE TABLE IF NOT EXISTS harvest_runs (
    source_id    TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    total_at_source INTEGER,            -- what the portal says it holds
    harvested    INTEGER,               -- what we actually stored
    errors       INTEGER
);
"""


def open_db() -> sqlite3.Connection:
    conn = db_connect()
    conn.executescript(SCHEMA)
    return conn


def load_sources() -> list[dict]:
    with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["sources"]


def resource_rows(key: str, resources: list[tuple]) -> list[tuple]:
    """(url, name, format) triples -> resources-table rows, deduped by url."""
    from normalise import norm_format
    seen: dict[str, tuple] = {}
    for url, name, fmt in resources:
        if url and url.startswith("http") and url not in seen:
            seen[url] = (key, url, (name or "")[:200], norm_format(fmt))
    return list(seen.values())


def normalise_package(pkg: dict, src: dict, now: str) -> tuple | None:
    title = norm_title(pkg.get("title"))
    if not title:
        return None
    resources = pkg.get("resources") or []
    formats_raw = [r.get("format") for r in resources]
    formats_norm = norm_formats(formats_raw)
    org = (pkg.get("organization") or {}).get("title")
    tags = [t.get("name") for t in (pkg.get("tags") or []) if t.get("name")]
    name = pkg.get("name") or pkg.get("id")
    return (
        f"{src['id']}:{pkg['id']}",
        src["id"],
        pkg["id"],
        name,
        title,
        strip_html(pkg.get("notes")),
        org,
        # data.gov.uk often leaves the standard fields empty and puts the
        # licence in extras instead — see license_from_extras()
        (pkg.get("license_id") or pkg.get("license_title")
         or license_from_extras(pkg.get("extras"))),
        norm_license(pkg.get("license_id") or license_from_extras(pkg.get("extras")),
                     pkg.get("license_title")),
        norm_date(pkg.get("metadata_created")),
        norm_date(pkg.get("metadata_modified")),
        src["dataset_url"].format(name=name),
        json.dumps(tags),
        json.dumps([f for f in formats_raw if f]),
        json.dumps(formats_norm),
        len(resources),
        now,
    )


UPSERT = """
INSERT INTO datasets (key, source_id, ckan_id, name, title, description,
    publisher, license_raw, license_norm, created, modified, landing_url,
    tags, formats_raw, formats_norm, resource_count, harvested_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(key) DO UPDATE SET
    name=excluded.name, title=excluded.title, description=excluded.description,
    publisher=excluded.publisher, license_raw=excluded.license_raw,
    license_norm=excluded.license_norm, created=excluded.created,
    modified=excluded.modified, landing_url=excluded.landing_url,
    tags=excluded.tags, formats_raw=excluded.formats_raw,
    formats_norm=excluded.formats_norm, resource_count=excluded.resource_count,
    harvested_at=excluded.harvested_at
"""


def harvest_source(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    total_at_source = None
    stored = 0
    errors = 0
    start = 0

    print(f"[{src['id']}] harvesting from {src['api']} ...", flush=True)
    while True:
        params = {"rows": PAGE_SIZE, "start": start}
        try:
            resp = session.get(f"{src['api']}/package_search", params=params, timeout=60)
            resp.raise_for_status()
            result = resp.json()["result"]
        except Exception as exc:  # noqa: BLE001 - log and move on; one bad page shouldn't kill the run
            errors += 1
            print(f"[{src['id']}]   page at start={start} failed: {exc}", flush=True)
            if errors >= 3:
                print(f"[{src['id']}]   too many errors, abandoning source", flush=True)
                break
            start += PAGE_SIZE
            continue

        total_at_source = result.get("count")
        # Standard CKAN uses result.results; Data Mill North nests under result.result
        packages = result.get("results") or result.get("result") or []
        if not packages:
            break

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows = [r for p in packages if (r := normalise_package(p, src, now))]
        # Files and geography only for the packages we actually stored —
        # otherwise a record we refused (no usable title) still gets resource
        # rows, orphaned against a dataset that isn't there.
        stored_keys = {r[0] for r in rows}
        res_rows, keys, geo_rows = [], [], []
        for p in packages:
            key = f"{src['id']}:{p['id']}"
            if key not in stored_keys:
                continue
            keys.append((key,))
            res_rows += resource_rows(key, [
                (r.get("url"), r.get("name"), r.get("format"))
                for r in (p.get("resources") or [])
            ])
            if (g := geo_row(key, p)):
                geo_rows.append(g)
        conn.executemany(UPSERT, rows)
        # Clear first: a publisher who removes a bounding box would otherwise
        # keep the old one forever, and geo search would go on matching a
        # place the dataset no longer claims to cover.
        conn.executemany("DELETE FROM dataset_geo WHERE dataset_key = ?", keys)
        conn.executemany(GEO_UPSERT, geo_rows)
        conn.executemany("DELETE FROM resources WHERE dataset_key = ?", keys)
        conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res_rows)
        conn.commit()
        stored += len(rows)
        start += len(packages)

        if stored % 2500 < PAGE_SIZE:
            print(f"[{src['id']}]   {stored}/{total_at_source}", flush=True)
        if limit and stored >= limit:
            print(f"[{src['id']}]   hit --limit {limit}, stopping", flush=True)
            break
        if start >= (total_at_source or 0):
            break
        time.sleep(0.2)  # politeness between pages

    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
        (src["id"], started, finished, total_at_source, stored, errors),
    )
    conn.commit()
    print(f"[{src['id']}] done: {stored} stored "
          f"(portal reports {total_at_source}), {errors} page errors", flush=True)


def _dcat_publisher(ds: dict, src: dict) -> str:
    """Publisher name, guarding against the ways feeds get this wrong.

    Three failure modes seen in the wild: unresolved template junk
    ('{{source}}') from some ArcGIS Hub feeds, Socrata's habit of putting the
    bare hostname in publisher.name, and aggregators that omit `publisher`
    entirely while naming the real organisation in `contactPoint`.

    That last one matters: opendata.scot carries no publisher at all, but its
    contactPoint names 67 distinct Scottish bodies — councils, the Scottish
    Parliament, Public Health Scotland. Falling straight back to the source
    name would have filed all 2,507 datasets under one invented publisher and
    told the council tracker nothing.
    """
    def usable(name: str | None) -> str | None:
        name = (name or "").strip()
        looks_like_host = ("." in name and " " not in name and name.islower())
        return None if (not name or unrendered(name) or looks_like_host) else name

    return (usable((ds.get("publisher") or {}).get("name"))
            or usable((ds.get("contactPoint") or {}).get("fn"))
            or src["name"])


def _dcat_landing(ds: dict) -> str | None:
    """A human-facing page for this dataset, from wherever the feed put it.

    Feeds that omit landingPage often still list the portal page as a
    distribution — ArcGIS Hub calls it "Web Page" — so prefer that over
    linking a reader straight at a REST endpoint.
    """
    if landing := ds.get("landingPage"):
        return landing
    dists = ds.get("distribution") or []
    named = next((d for d in dists
                  if "web" in str(d.get("title") or "").lower()), None)
    for d in ([named] if named else []) + dists:
        url = d.get("accessURL") or d.get("downloadURL")
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


def normalise_dcat_dataset(ds: dict, src: dict, now: str) -> tuple | None:
    """Map a DCAT-US dataset entry (ArcGIS Hub feeds etc.) onto our schema."""
    # ArcGIS Hub sometimes serves its own template here, so 17 records across
    # eight councils were indexed under the literal title "{{name}}" — a
    # search result and a listing entry with nothing in them to read.
    title = norm_title(ds.get("title"))
    if not title:
        return None
    landing = _dcat_landing(ds)
    ident = ds.get("identifier") or landing
    if not ident:
        # No id and no link, but a title and a named publisher is still a
        # real record. Key it on those, which stay stable between harvests —
        # a random id would create a new dataset every night.
        seed = f"{_dcat_publisher(ds, src)}|{title}".encode("utf-8")
        ident = "sha1:" + hashlib.sha1(seed).hexdigest()[:16]
    distributions = ds.get("distribution") or []
    formats_raw = [d.get("format") or d.get("mediaType") for d in distributions]
    # landing stays None when the feed offers no URL — 536 opendata.scot
    # records used to carry a literal "sha1:…" here, which the dataset page
    # dutifully rendered as a dead link.
    name = (landing or ident).rstrip("/").rsplit("/", 1)[-1] or ident
    license_raw = strip_html(ds.get("license"))
    if license_raw:
        license_raw = license_raw[:150]
    keywords = ds.get("keyword") or []
    return (
        f"{src['id']}:{ident}",
        src["id"],
        ident,
        name,
        title,
        strip_html(ds.get("description")),
        _dcat_publisher(ds, src),
        license_raw,
        norm_license(license_raw),
        norm_date(ds.get("issued")),
        norm_date(ds.get("modified")),
        landing,
        json.dumps(keywords),
        json.dumps([f for f in formats_raw if f]),
        json.dumps(norm_formats(formats_raw)),
        len(distributions),
        now,
    )


def harvest_dcat(src: dict, conn: sqlite3.Connection) -> None:
    """Harvest a DCAT-US feed (single JSON document listing all datasets)."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{src['id']}] harvesting DCAT feed {src['api']} ...", flush=True)
    try:
        resp = session.get(src["api"], timeout=120)
        resp.raise_for_status()
        datasets = resp.json().get("dataset") or []
    except Exception as exc:  # noqa: BLE001
        print(f"[{src['id']}] feed failed: {exc}", flush=True)
        conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                     (src["id"], started, started, None, 0, 1))
        conn.commit()
        return

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Keep each dataset paired with its normalised row: the row's key is the
    # only truth about what got stored. Recomputing the ident here from
    # identifier-or-landingPage disagreed with normalise_dcat_dataset's
    # identifier-or-distribution-URL-or-sha1 whenever `identifier` was absent,
    # and every one of opendata.scot's 2,467 datasets lost its resource rows
    # to that mismatch.
    pairs = [(ds, r) for ds in datasets
             if (r := normalise_dcat_dataset(ds, src, now))]
    rows = [r for _, r in pairs]
    res_rows, keys = [], []
    for ds, row in pairs:
        key = row[0]
        keys.append((key,))
        res_rows += resource_rows(key, [
            (d.get("downloadURL") or d.get("accessURL"), d.get("title"),
             d.get("format") or d.get("mediaType"))
            for d in (ds.get("distribution") or [])
        ])
    conn.executemany(UPSERT, rows)
    conn.executemany("DELETE FROM resources WHERE dataset_key = ?", keys)
    conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res_rows)
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, finished, len(datasets), len(rows), 0))
    conn.commit()
    print(f"[{src['id']}] done: {len(rows)} stored "
          f"(feed lists {len(datasets)})", flush=True)


ODS_PAGE = 100  # OpenDataSoft caps limit at 100


def ods_export_url(base: str, did: str, fmt: str) -> str:
    return f"{base}/api/explore/v2.1/catalog/datasets/{did}/exports/{fmt}"


def normalise_ods_dataset(ds: dict, src: dict, now: str) -> tuple | None:
    """Map an OpenDataSoft Explore v2.1 catalogue entry onto our schema.

    ODS keeps almost everything under metas.default, and exposes data through
    predictable per-format export endpoints rather than listing resources —
    so we synthesise the resource list from the formats it can export.
    """
    md = (ds.get("metas") or {}).get("default") or {}
    did = ds.get("dataset_id")
    title = norm_title(md.get("title"))
    if not did or not title:
        return None
    base = src["web"].rstrip("/")
    license_raw = md.get("license")
    keywords = list(md.get("keyword") or []) + list(md.get("theme") or [])
    formats = ods_formats(ds, md)
    return (
        f"{src['id']}:{did}",
        src["id"],
        did,
        did,
        title,
        strip_html(md.get("description")),
        md.get("publisher") or src["name"],
        license_raw,
        norm_license(license_raw, md.get("license_url")),
        None,  # ODS exposes no creation date, only modification
        norm_date(md.get("modified")),
        f"{base}/explore/dataset/{did}/",
        json.dumps([k for k in keywords if k]),
        json.dumps(formats),
        json.dumps(norm_formats(formats)),
        len(formats),
        now,
    )


def ods_formats(ds: dict, md: dict) -> list[str]:
    if not ds.get("has_records"):
        return []
    formats = ["CSV", "JSON"]
    if md.get("geometry_types"):
        formats.append("GEOJSON")
    return formats


def harvest_ods(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Harvest an OpenDataSoft portal (Explore v2.1 catalogue API)."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base = src["web"].rstrip("/")
    total_at_source, stored, errors, offset = None, 0, 0, 0

    print(f"[{src['id']}] harvesting OpenDataSoft {src['api']} ...", flush=True)
    while True:
        try:
            resp = session.get(src["api"],
                               params={"limit": ODS_PAGE, "offset": offset},
                               timeout=60)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[{src['id']}]   page at offset={offset} failed: {exc}", flush=True)
            if errors >= 3:
                break
            offset += ODS_PAGE
            continue

        total_at_source = body.get("total_count")
        results = body.get("results") or []
        if not results:
            break

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows, res_rows, keys = [], [], []
        for ds in results:
            row = normalise_ods_dataset(ds, src, now)
            if not row:
                continue
            rows.append(row)
            did, key = ds["dataset_id"], row[0]
            keys.append((key,))
            md = (ds.get("metas") or {}).get("default") or {}
            res_rows += resource_rows(key, [
                (ods_export_url(base, did, f.lower()), f"{did}.{f.lower()}", f)
                for f in ods_formats(ds, md)
            ])
        conn.executemany(UPSERT, rows)
        conn.executemany("DELETE FROM resources WHERE dataset_key = ?", keys)
        conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res_rows)
        conn.commit()

        stored += len(rows)
        offset += len(results)
        if limit and stored >= limit:
            break
        if offset >= (total_at_source or 0):
            break
        time.sleep(0.2)

    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, finished, total_at_source, stored, errors))
    conn.commit()
    print(f"[{src['id']}] done: {stored} stored "
          f"(portal reports {total_at_source}), {errors} page errors", flush=True)


CSW_NS = {
    "csw": "http://www.opengis.net/cat/csw/2.0.2",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dct": "http://purl.org/dc/terms/",
}
CSW_PAGE = 50          # servers commonly cap maxRecords well below 100


def _csw_text(rec, tag: str) -> str | None:
    el = rec.find(tag, CSW_NS)
    return el.text.strip() if el is not None and el.text else None


def _csw_all(rec, tag: str) -> list[str]:
    return [e.text.strip() for e in rec.findall(tag, CSW_NS) if e is not None and e.text]


def normalise_csw_record(rec, src: dict, now: str) -> tuple | None:
    """Map one csw:Record (Dublin Core) onto our schema."""
    ident = _csw_text(rec, "dc:identifier")
    title = norm_title(_csw_text(rec, "dc:title"))
    if not ident or not title:
        return None
    # dc:rights on INSPIRE catalogues is usually an access-constraint code
    # ("otherRestrictions"), which is not a licence and must not become one.
    rights = _csw_text(rec, "dc:rights")
    if rights and rights.lower() in ("otherrestrictions", "restricted",
                                     "unclassified", "copyright", "license",
                                     "licence", "intellectualpropertyrights"):
        rights = None
    urls = [u for u in _csw_all(rec, "dc:URI") + _csw_all(rec, "dct:references")
            if u.startswith("http")]
    subjects = _csw_all(rec, "dc:subject")[:25]
    landing = src.get("dataset_url", "").format(id=ident) if src.get("dataset_url") else None
    return (
        f"{src['id']}:{ident}",
        src["id"],
        ident,
        ident,
        title,
        strip_html(_csw_text(rec, "dct:abstract") or _csw_text(rec, "dc:description")),
        src["name"],
        rights,
        norm_license(rights),
        None,
        norm_date(_csw_text(rec, "dct:modified") or _csw_text(rec, "dc:date")),
        landing or (urls[0] if urls else src["web"]),
        json.dumps(subjects),
        json.dumps([]),
        json.dumps([]),
        len(urls),
        now,
    ), urls


def harvest_csw(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Harvest an OGC Catalogue Service for the Web (CSW 2.0.2).

    The standard behind INSPIRE-compliant spatial catalogues — GeoNetwork
    and friends. Unlike everything else here it speaks XML, and paginates by
    telling you where the next record starts rather than by page number.
    """
    import xml.etree.ElementTree as ET

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{src['id']}] harvesting CSW {src['api']} ...", flush=True)

    rows, res_rows, keys = [], [], []
    total, start, errors = None, 1, 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    while True:
        params = {"service": "CSW", "version": "2.0.2", "request": "GetRecords",
                  "typeNames": "csw:Record", "resultType": "results",
                  "elementSetName": "full", "maxRecords": str(CSW_PAGE),
                  "startPosition": str(start),
                  "outputSchema": "http://www.opengis.net/cat/csw/2.0.2"}
        try:
            resp = session.get(src["api"], params=params, timeout=90)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:  # noqa: BLE001
            print(f"[{src['id']}] records from {start} failed: {exc}", flush=True)
            errors += 1
            break

        results = root.find("csw:SearchResults", CSW_NS)
        if results is None:
            break
        if total is None:
            total = int(results.get("numberOfRecordsMatched") or 0)
        batch = results.findall("csw:Record", CSW_NS)
        if not batch:
            break
        for rec in batch:
            got = normalise_csw_record(rec, src, now)
            if not got:
                continue
            row, urls = got
            rows.append(row)
            keys.append((row[0],))
            res_rows += resource_rows(row[0], [(u, "resource", None) for u in urls])
        print(f"[{src['id']}]   {len(rows)}/{total}", flush=True)

        if limit and len(rows) >= limit:
            rows, keys = rows[:limit], keys[:limit]
            break
        # The server says where to continue; 0 means there is no more.
        nxt = int(results.get("nextRecord") or 0)
        if not nxt or nxt <= start:
            break
        start = nxt
        time.sleep(0.2)

    conn.executemany(UPSERT, rows)
    conn.executemany("DELETE FROM resources WHERE dataset_key = ?", keys)
    conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res_rows)
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, finished, total, len(rows), errors))
    conn.commit()
    print(f"[{src['id']}] done: {len(rows)} stored (catalogue reports {total}), "
          f"{len(res_rows)} files", flush=True)


def _dig(obj, path: str):
    """Follow a dotted path into nested JSON, tolerating anything missing.

    "links.Self.href" walks three levels; "" returns the object itself, which
    is how a bare list at the document root is addressed.
    """
    if not path:
        return obj
    for step in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(step)
        elif isinstance(obj, list) and step.isdigit():
            obj = obj[int(step)] if int(step) < len(obj) else None
        else:
            return None
        if obj is None:
            return None
    return obj


def harvest_json(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Harvest a bespoke JSON catalogue described by config in sources.yaml.

    Three of the portals worth having speak no standard at all — NBN Atlas
    returns a bare list, Cefas paginates under `items`, the Department for
    Business and Trade nests under `datasets`. Writing three adapters for
    three sources is poor leverage; the differences between them are entirely
    *where the fields are*, which is data, not code.

    So the shape lives in sources.yaml under `json:`:

        json:
          list: items            # where the records are ("" = bare list)
          page_param: page       # omit for a single-shot endpoint
          total: totalItems
          id: id
          title: title
          description: abstract
          landing: "https://example.org/dataset/{id}"
          detail: "https://example.org/api/item/{id}"   # optional second fetch

    A `detail` URL is fetched per record when the listing is too thin to be
    worth indexing — NBN's list has no description, licence or download, and
    all three are one request away. That costs one request per dataset, so it
    is only used where the listing genuinely can't stand alone.
    """
    cfg = src.get("json") or {}
    # 126 of our sources are ArcGIS Hub organisations, all paginating against
    # the same host. Unthrottled that is several thousand requests a night at
    # one endpoint, from one IP, for our convenience. A fifth of a second
    # between pages costs us minutes and costs them nothing.
    pause = float(cfg.get("pause", 0.2))
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{src['id']}] harvesting JSON {src['api']} ...", flush=True)

    records, total, errors = [], None, 0
    page = int(cfg.get("page_start", 1))
    while True:
        params = dict(cfg.get("params") or {})
        if cfg.get("page_param"):
            params[cfg["page_param"]] = page
        try:
            resp = session.get(src["api"], params=params, timeout=90)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[{src['id']}] page {page} failed: {exc}", flush=True)
            errors += 1
            break
        batch = _dig(payload, cfg.get("list", ""))
        if not isinstance(batch, list) or not batch:
            break
        if total is None and cfg.get("total"):
            total = _dig(payload, cfg["total"])
        records += batch
        print(f"[{src['id']}]   {len(records)}/{total or '?'}", flush=True)
        if limit and len(records) >= limit:
            records = records[:limit]
            break
        if not cfg.get("page_param") or len(records) >= (total or 0):
            break
        page += 1
        time.sleep(pause)

    total = total or len(records)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows, res_rows, keys = [], [], []
    detail_url = cfg.get("detail")
    for i, rec in enumerate(records, 1):
        ident = _dig(rec, cfg.get("id", "id"))
        if ident in (None, ""):
            continue
        if detail_url:
            if i % 200 == 0:
                print(f"[{src['id']}]   detail {i}/{len(records)}", flush=True)
            try:
                d = session.get(detail_url.format(id=ident), timeout=60)
                if d.ok:
                    rec = {**rec, **d.json()}
            except Exception:  # noqa: BLE001 - the listing row still stands
                pass
            time.sleep(pause)
        rec = flatten_bag(rec, cfg)
        row = _normalise_json_record(rec, ident, cfg, src, now)
        if not row:
            continue
        rows.append(row)
        key = f"{src['id']}:{ident}"
        keys.append((key,))
        res_rows += resource_rows(key, [
            (_dig(rec, u), cfg.get("resource_name", "download"), _fmt(rec, f))
            for u, f in (cfg.get("resources") or [])])

    rows, blanked = drop_boilerplate(rows)

    # A quality gate, for sources where the API returns everything an
    # organisation ever shared rather than what it chose to publish.
    #
    # An ArcGIS Online org exposes working layers, survey forms and logo
    # graphics alongside real datasets: a 10-council pilot returned 12,874
    # records of which only 12% had any description and 28% had nothing at
    # all — titles like "Family Hub Logo form" and "surveyPoint". Indexing
    # that would bury the deprivation indices and flood maps underneath it.
    #
    # Requiring a description is a crude filter but an honest one: it keeps
    # what the publisher bothered to describe.
    dropped = 0
    if cfg.get("require_description"):
        floor = int(cfg.get("require_description"))
        kept = [r for r in rows
                if r[DESCRIPTION_COL] and len(r[DESCRIPTION_COL]) >= floor]
        dropped = len(rows) - len(kept)
        keep_keys = {r[0] for r in kept}
        keys = [k for k in keys if k[0] in keep_keys]
        res_rows = [r for r in res_rows if r[0] in keep_keys]
        rows = kept

    conn.executemany(UPSERT, rows)
    conn.executemany("DELETE FROM resources WHERE dataset_key = ?", keys)
    conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res_rows)
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, finished, total, len(rows), errors))
    conn.commit()
    print(f"[{src['id']}] done: {len(rows)} stored (catalogue reports {total}), "
          f"{len(res_rows)} files"
          + (f", {blanked} shared descriptions dropped" if blanked else "")
          + (f", {dropped} undescribed records skipped" if dropped else ""),
          flush=True)


DESCRIPTION_COL = 5          # position of `description` in the UPSERT tuple
BOILERPLATE_MIN = 5          # copies before a description stops being one


def drop_boilerplate(rows: list[tuple]) -> tuple[list[tuple], int]:
    """Blank descriptions that repeat across a source.

    ArcGIS Hub organisations paste one HTML blurb about themselves onto every
    layer they publish: 200 National Highways records carried 54 distinct
    descriptions, one of them on 30 datasets. A paragraph that appears on
    thirty datasets is not a description of any of them, and repeating it
    would put the same wall of text on hundreds of pages.

    Blanked rather than kept, so the page falls back to the generated summary
    and the thin-page rule can judge the record on what it actually has.
    """
    counts: dict[str, int] = {}
    for row in rows:
        text = row[DESCRIPTION_COL]
        if text:
            counts[text] = counts.get(text, 0) + 1
    shared = {t for t, n in counts.items() if n >= BOILERPLATE_MIN}
    if not shared:
        return rows, 0
    cleaned = [
        (row[:DESCRIPTION_COL] + (None,) + row[DESCRIPTION_COL + 1:])
        if row[DESCRIPTION_COL] in shared else row
        for row in rows
    ]
    return cleaned, sum(counts[t] for t in shared)


# The "Vocab" half of a "Vocab:Term" bag value: a bare word. Excludes digits
# so no timestamp can match it.
VOCAB_PREFIX = re.compile(r"[A-Za-z][A-Za-z_]*")


def flatten_bag(rec: dict, cfg: dict) -> dict:
    """Fold a name/value property list into something field paths can address.

    Cefas returns its metadata as 74 property objects rather than fields:

        {"propertyName": "Desc", "values": [{"value": "<p>A series of ..."}]}

    So every real field — abstract, keywords, formats, licence terms — is
    invisible to a dotted path. This lifts them to rec["_bag"][name], a list
    of strings, and everything downstream addresses them normally.

    Values come from a controlled vocabulary written "Vocab:Term"
    ("Freq:Not planned", "Format:DOC", "RestrictionCode:Public"). The
    displayValue is preferred where the API gives one; where it doesn't, the
    term after the colon is the human-readable half.

    The vocabulary half is always a bare word, and the test has to say so.
    "Anything before a colon with no space in it" also matches the date half
    of "2025-11-11T12:18:15", which it cut down to "18:15" — every Cefas
    HoldingRevDate and StartDate in the index, 2,919 rows, reduced to minutes
    and seconds with the date thrown away.
    """
    spec = cfg.get("bag")
    if not spec:
        return rec
    entries = _dig(rec, spec.get("list", "properties")) or []
    key_field = spec.get("key", "propertyName")
    bag: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get(key_field)
        out: list[str] = []
        for v in (entry.get(spec.get("values", "values")) or []):
            if not isinstance(v, dict):
                continue
            text = v.get("displayValue") or v.get("value")
            if not isinstance(text, str) or not text.strip():
                continue
            if not v.get("displayValue") and ":" in text:
                head, _, tail = text.partition(":")
                # not tail.startswith("//"): "https://..." is a URL, and its
                # scheme is a bare word that would otherwise pass as a vocab.
                if (tail.strip() and not tail.startswith("//")
                        and VOCAB_PREFIX.fullmatch(head)):
                    text = tail
            out.append(text.strip())
        if name and out:
            bag[name] = out
    return {**rec, "_bag": bag}


def _fmt(rec: dict, spec: str | None):
    """A resource format: a path into the record, or a literal after "=".

    Some APIs never state the format but it is knowable from the endpoint —
    ArcGIS Hub's `url` is always an Esri REST service — so the config can say
    so outright rather than us inventing a field that isn't there.
    """
    if not spec:
        return None
    return spec[1:] if spec.startswith("=") else _dig(rec, spec)


def _normalise_json_record(rec: dict, ident, cfg: dict, src: dict,
                           now: str) -> tuple | None:
    def field(key: str):
        """A configured field, or None when the source doesn't have one.

        Not _dig(rec, cfg.get(key, "")) — an empty path means "the whole
        record" to _dig, which is right for a root-level list and very wrong
        for a missing field: it handed the entire dict to strip_html.
        """
        return _dig(rec, cfg[key]) if cfg.get(key) else None

    title = norm_title(_dig(rec, cfg.get("title", "title")))
    if not title:
        return None
    lic = _dig(rec, cfg["license"]) if cfg.get("license") else None
    # Several of these write "other" or "none" where they mean "unstated",
    # which must not become a licence.
    if isinstance(lic, str) and lic.strip().lower() in ("other", "none", "unknown", ""):
        lic = None
    tag_paths = cfg.get("tags")
    tag_paths = [tag_paths] if isinstance(tag_paths, str) else (tag_paths or [])
    tags: list[str] = []
    for path in tag_paths:
        got = _dig(rec, path)
        if isinstance(got, str):
            tags.append(got)
        elif isinstance(got, list):
            tags += [t for t in got if isinstance(t, str)]
    seen_tags: dict[str, None] = {}
    for tag in tags:
        seen_tags.setdefault(tag, None)
    tags = list(seen_tags)[:25]
    fmt_values = [_fmt(rec, f) for _u, f in (cfg.get("resources") or [])
                  if _dig(rec, _u)]
    if cfg.get("formats"):
        extra = _dig(rec, cfg["formats"])
        if isinstance(extra, list):
            fmt_values += [f for f in extra if isinstance(f, str)]
    landing = (cfg["landing"].format(id=ident) if cfg.get("landing")
               else _dig(rec, cfg.get("landing_field", "")) or src["web"])
    return (
        f"{src['id']}:{ident}",
        src["id"],
        str(ident),
        str(field("name") or ident),
        title,
        strip_html(field("description")),
        field("publisher") or src["name"],
        lic,
        norm_license(lic),
        norm_date(field("created")),
        norm_date(field("modified")),
        landing,
        json.dumps(tags),
        json.dumps([f for f in fmt_values if f]),
        json.dumps(norm_formats(fmt_values)),
        len(fmt_values),
        now,
    )


GEONODE_PAGE = 200

# GeoNode records who *uploaded* a layer, not who published it: the owner is
# a named individual and sometimes a personal email address. We never store
# those. The workspace is the only field that identifies an organisation, and
# only for the minority that use a named one — the rest sit in the default
# "geonode" workspace with no attribution at all (verified: the `attribution`
# field is null on all 1,927 DataMap Wales layers).
GEONODE_WORKSPACES = {
    "inspire-nrw": "Natural Resources Wales",
    "appdata-nrw": "Natural Resources Wales",
    "appdata-ons": "Office for National Statistics",
    "inspire-wg": "Welsh Government",
    "appdata-wg": "Welsh Government",
    "appdata-wg-marine": "Welsh Government",
}


def geonode_publisher(rec: dict, src: dict) -> str:
    """Who published this layer, or the platform when nobody says.

    Naming the uploader would put individuals — and in some cases their work
    email address — into a public index, for no gain. Falling back to the
    platform name is the honest answer to "where did this come from?" when
    the record itself doesn't answer "who made it?".
    """
    ws = (rec.get("workspace") or "").strip().lower()
    if ws in GEONODE_WORKSPACES:
        return GEONODE_WORKSPACES[ws]
    for prefix, name in GEONODE_WORKSPACES.items():
        if ws.startswith(prefix + "-"):
            return name
    return src["name"]


def geonode_resources(base: str, alternate: str | None) -> list[tuple]:
    """The download and service URLs a GeoNode layer actually offers.

    GeoNode 3's API exposes no links, but every layer is a GeoServer feature
    type, so these are constructible from `alternate` and are real: all four
    verified against DataMap Wales before this was written. The checker
    confirms them per layer anyway, so a workspace that refuses one of them
    gets marked rather than assumed.
    """
    if not alternate:
        return []
    wfs = f"{base}/geoserver/wfs?service=WFS&version=2.0.0&request=GetFeature&typeName={alternate}"
    return [
        (f"{wfs}&outputFormat=application/json", "GeoJSON (WFS)", "GeoJSON"),
        (f"{wfs}&outputFormat=SHAPE-ZIP", "Shapefile (WFS)", "SHP"),
        (f"{wfs}&outputFormat=csv", "CSV (WFS)", "CSV"),
        (f"{base}/geoserver/wms?service=WMS&version=1.3.0&request=GetCapabilities",
         "WMS service", "WMS"),
    ]


def normalise_geonode_layer(rec: dict, src: dict, base: str, now: str) -> tuple | None:
    ident = rec.get("uuid") or (str(rec["pk"]) if rec.get("pk") else None)
    title = norm_title(rec.get("title"))
    if not ident or not title:
        return None
    formats = [f for _u, _n, f in geonode_resources(base, rec.get("alternate"))]
    keywords = [k.get("name") for k in (rec.get("keywords") or []) if k.get("name")]
    if category := (rec.get("category") or {}).get("identifier"):
        keywords.append(category)
    # GeoNode writes "not_specified" where a licence is unset; that is the
    # same thing as absent and must not be normalised into a licence.
    lic = ((rec.get("license") or {}).get("identifier") or "").strip()
    if lic in ("", "not_specified"):
        lic = None
    return (
        f"{src['id']}:{ident}",
        src["id"],
        ident,
        rec.get("name") or ident,
        title,
        strip_html(rec.get("raw_abstract") or rec.get("abstract")),
        geonode_publisher(rec, src),
        lic,
        norm_license(lic),
        norm_date(rec.get("created")),
        norm_date(rec.get("last_updated") or rec.get("date")),
        rec.get("detail_url") or f"{base}/layers/{rec.get('alternate') or ident}",
        json.dumps(keywords),
        json.dumps(formats),
        json.dumps(norm_formats(formats)),
        len(formats),
        now,
    )


# Everything this index covers is in or around the British Isles, out to
# Rockall and across the North Sea. A bounding box that misses this entirely
# isn't data about somewhere else — it's a broken box, and a broken box is
# worse than none: geo search would offer a Welsh dataset to someone asking
# about the Indian Ocean.
UK_ENVELOPE = (-25.0, 45.0, 5.0, 65.0)  # west, south, east, north


def _intersects_uk(w: float, s: float, e: float, n: float) -> bool:
    uw, us, ue, un = UK_ENVELOPE
    return w <= ue and e >= uw and s <= un and n >= us


def geonode_bbox(rec: dict) -> tuple[float, float, float, float] | None:
    """West/south/east/north from the WGS84 polygon GeoNode publishes.

    `bbox_polygon` is in the layer's own projection — EPSG:27700 for most of
    Wales — so only `ll_bbox_polygon` is safe to read without reprojecting.

    Two real faults in that field on DataMap Wales, both found by checking
    the result against where Wales actually is rather than trusting it:

    - Some layers emit the coordinates as (lat, lon). The Landmap series
      reported a box at 51.33E, 5.47S — Wales with its axes swapped, in the
      Indian Ocean. Swapping back recovers a correct box, so we do, rather
      than throwing away real geography.
    - Others carry a placeholder box from (-1,-1) to (0,0), off the coast of
      Africa. Nothing recovers that one; it is dropped.
    """
    poly = (rec.get("ll_bbox_polygon") or {}).get("coordinates")
    if not poly or not poly[0]:
        return None
    try:
        pairs = [(float(p[0]), float(p[1])) for p in poly[0]]
    except (TypeError, ValueError, IndexError):
        return None
    if not pairs:
        return None

    for lon_first in (True, False):
        xs = [p[0] if lon_first else p[1] for p in pairs]
        ys = [p[1] if lon_first else p[0] for p in pairs]
        w, s, e, n = min(xs), min(ys), max(xs), max(ys)
        if (-180 <= w <= e <= 180 and -90 <= s <= n <= 90
                and not (w == e and s == n) and _intersects_uk(w, s, e, n)):
            return (w, s, e, n)
    return None


def harvest_geonode(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Harvest a GeoNode catalogue (paged /api/v2/layers/)."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base = src["web"].rstrip("/")
    print(f"[{src['id']}] harvesting GeoNode {src['api']} ...", flush=True)

    layers, total, page, errors = [], None, 1, 0
    while True:
        try:
            resp = session.get(src["api"], params={"page_size": GEONODE_PAGE,
                                                   "page": page}, timeout=120)
            # GeoNode answers 404 for the page after the last one rather than
            # an empty list, so that is the end of the catalogue, not a fault.
            if resp.status_code == 404 and layers:
                break
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[{src['id']}] page {page} failed: {exc}", flush=True)
            errors += 1
            break
        total = total or payload.get("total")
        batch = payload.get("layers") or payload.get("resources") or []
        if not batch:
            break
        layers += batch
        print(f"[{src['id']}]   {len(layers)}/{total or '?'}", flush=True)
        if limit and len(layers) >= limit:
            layers = layers[:limit]
            break
        page += 1

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = [r for rec in layers if (r := normalise_geonode_layer(rec, src, base, now))]
    stored_keys = {r[0] for r in rows}
    res_rows, keys, geo_rows = [], [], []
    for rec in layers:
        ident = rec.get("uuid") or (str(rec["pk"]) if rec.get("pk") else None)
        key = f"{src['id']}:{ident}"
        if not ident or key not in stored_keys:
            continue
        keys.append((key,))
        res_rows += resource_rows(key, geonode_resources(base, rec.get("alternate")))
        if box := geonode_bbox(rec):
            geo_rows.append((key, *box, None, rec.get("date")))

    conn.executemany(UPSERT, rows)
    conn.executemany("DELETE FROM resources WHERE dataset_key = ?", keys)
    conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res_rows)
    # Clear before writing, so a box that stops being valid stops being used.
    conn.executemany("DELETE FROM dataset_geo WHERE dataset_key = ?", keys)
    conn.executemany(GEO_UPSERT, geo_rows)
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, finished, total, len(rows), errors))
    conn.commit()
    print(f"[{src['id']}] done: {len(rows)} stored (catalogue reports {total}), "
          f"{len(geo_rows)} with a bounding box", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="max datasets to harvest per source")
    ap.add_argument("--source", action="append",
                    help="harvest only this source id (repeatable)")
    args = ap.parse_args()

    sources = load_sources()
    if args.source:
        unknown = set(args.source) - {s["id"] for s in sources}
        if unknown:
            print(f"unknown source id(s): {', '.join(sorted(unknown))}")
            return 1
        sources = [s for s in sources if s["id"] in args.source]

    conn = open_db()
    for src in sources:
        if src.get("type") == "ckan":
            harvest_source(src, conn, args.limit)
        elif src.get("type") == "dcat":
            harvest_dcat(src, conn)
        elif src.get("type") == "ods":
            harvest_ods(src, conn, args.limit)
        elif src.get("type") == "geonode":
            harvest_geonode(src, conn, args.limit)
        elif src.get("type") == "json":
            harvest_json(src, conn, args.limit)
        elif src.get("type") == "csw":
            harvest_csw(src, conn, args.limit)
        else:
            print(f"[{src['id']}] skipped: no harvester for type {src.get('type')!r}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
