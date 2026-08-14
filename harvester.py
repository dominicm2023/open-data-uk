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
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests
import yaml

from normalise import (bbox_from_extras, license_from_extras, norm_formats,
                       norm_license, reference_date_from_extras, strip_html,
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
from paths import DB_PATH, connect as db_connect  # noqa: E402
PAGE_SIZE = 500  # CKAN caps rows at 1000; 500 keeps responses a sane size
# NB: OpenDataNI's WAF 403s any UA containing the word "harvester"
USER_AGENT = "uk-open-data-index/0.1 (metadata indexer prototype)"

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


def normalise_package(pkg: dict, src: dict, now: str) -> tuple:
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
        pkg.get("title"),
        strip_html(pkg.get("notes")),
        org,
        # data.gov.uk often leaves the standard fields empty and puts the
        # licence in extras instead — see license_from_extras()
        (pkg.get("license_id") or pkg.get("license_title")
         or license_from_extras(pkg.get("extras"))),
        norm_license(pkg.get("license_id") or license_from_extras(pkg.get("extras")),
                     pkg.get("license_title")),
        pkg.get("metadata_created"),
        pkg.get("metadata_modified"),
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
        rows = [normalise_package(p, src, now) for p in packages]
        res_rows, keys, geo_rows = [], [], []
        for p in packages:
            key = f"{src['id']}:{p['id']}"
            keys.append((key,))
            res_rows += resource_rows(key, [
                (r.get("url"), r.get("name"), r.get("format"))
                for r in (p.get("resources") or [])
            ])
            if (g := geo_row(key, p)):
                geo_rows.append(g)
        conn.executemany(UPSERT, rows)
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
    """Publisher name, guarding against the two ways feeds get this wrong:
    unresolved template junk ('{{source}}') from some ArcGIS Hub feeds, and
    Socrata's habit of putting the bare hostname in publisher.name."""
    name = ((ds.get("publisher") or {}).get("name") or "").strip()
    looks_like_host = ("." in name and " " not in name and name.islower())
    if not name or "{{" in name or looks_like_host:
        return src["name"]
    return name


def normalise_dcat_dataset(ds: dict, src: dict, now: str) -> tuple | None:
    """Map a DCAT-US dataset entry (ArcGIS Hub feeds etc.) onto our schema."""
    ident = ds.get("identifier") or ds.get("landingPage")
    if not ident:
        return None
    distributions = ds.get("distribution") or []
    formats_raw = [d.get("format") or d.get("mediaType") for d in distributions]
    landing = ds.get("landingPage") or ident
    name = landing.rstrip("/").rsplit("/", 1)[-1] or ident
    license_raw = strip_html(ds.get("license"))
    if license_raw:
        license_raw = license_raw[:150]
    keywords = ds.get("keyword") or []
    return (
        f"{src['id']}:{ident}",
        src["id"],
        ident,
        name,
        ds.get("title"),
        strip_html(ds.get("description")),
        _dcat_publisher(ds, src),
        license_raw,
        norm_license(license_raw),
        ds.get("issued"),
        ds.get("modified"),
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
    rows = [r for ds in datasets if (r := normalise_dcat_dataset(ds, src, now))]
    res_rows, keys = [], []
    for ds in datasets:
        ident = ds.get("identifier") or ds.get("landingPage")
        if not ident:
            continue
        key = f"{src['id']}:{ident}"
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
    if not did:
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
        md.get("title"),
        strip_html(md.get("description")),
        md.get("publisher") or src["name"],
        license_raw,
        norm_license(license_raw, md.get("license_url")),
        None,  # ODS exposes no creation date, only modification
        md.get("modified"),
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
        else:
            print(f"[{src['id']}] skipped: no harvester for type {src.get('type')!r}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
