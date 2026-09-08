"""Two national statistics sites that are not catalogues: the ONS website
and the Department for Education's Explore Education Statistics. Neither
speaks CKAN or DCAT; each has an API of its own that lists what it
publishes, and each was the gap behind a real search ("population of
hertfordshire" found a cattle census; "SATs" found nothing) on 7 September
2026.

Both adapters write the same rows harvester.py writes for any source, so
everything downstream — dedupe, editions, the checker, search — treats
them as portals. They are incremental where the site lets them be: a
record whose release date has not moved keeps its resources without a
second request, because the ONS has 3,928 dataset pages and the polite
spacing is 1.5 s per request.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from agent import USER_AGENT  # noqa: E402
from normalise import norm_date, norm_formats, norm_license, norm_tags, norm_title, strip_html  # noqa: E402

SPACING = 1.5           # seconds between requests to one host: the family rule, kept here too
ONS_API = "https://api.beta.ons.gov.uk/v1/search"
ONS_WEB = "https://www.ons.gov.uk"
ONS_PAGE = 500
EES_API = "https://content.explore-education-statistics.service.gov.uk/api"
EES_WEB = "https://explore-education-statistics.service.gov.uk"

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


class _Client:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.last = 0.0
        self.requests = 0

    def get(self, url: str, **kw):
        wait = SPACING - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.requests += 1
        return self.s.get(url, timeout=60, **kw)

    def json(self, url: str, **kw):
        r = self.get(url, **kw)
        r.raise_for_status()
        return r.json()


def _ext(name: str) -> str:
    m = re.search(r"\.([a-z0-9]{2,5})$", (name or "").lower())
    return m.group(1) if m else ""


def _row(src_id: str, ident: str, title: str, description, publisher: str, licence: str,
         created, modified, landing: str, tags: list, formats: list, n_res: int, now: str) -> tuple | None:
    t = norm_title(title)
    if not t:
        return None
    return (f"{src_id}:{ident}", src_id, str(ident), ident, t, strip_html(description), publisher,
            licence, norm_license(licence), norm_date(created), norm_date(modified), landing,
            json.dumps(norm_tags(tags)), json.dumps([f for f in formats if f]), json.dumps(norm_formats(formats)),
            n_res, now)


def _finish(conn: sqlite3.Connection, src: dict, started: str, rows: list, res_by_key: dict,
            total, errors: int, unchanged: int) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.executemany(UPSERT, rows)
    for key, res in res_by_key.items():
        conn.execute("DELETE FROM resources WHERE dataset_key = ?", (key,))
        conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res)
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, now, total, len(rows), errors))
    conn.commit()
    print(f"[{src['id']}] done: {len(rows)} stored (catalogue reports {total}), "
          f"{sum(len(v) for v in res_by_key.values())} files refreshed, {unchanged} unchanged kept, {errors} errors", flush=True)


# --- ONS ---------------------------------------------------------------------

def harvest_ons(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every dataset landing page the ONS search API lists, with the latest
    edition's downloads. ons.gov.uk/help/termsandconditions: 'Most content
    on this website is subject to Crown copyright protection and is
    published under the Open Government Licence (OGL)' (v3)."""
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    print(f"[{src['id']}] harvesting ONS search API ...", flush=True)
    known = {k: m for k, m in conn.execute("SELECT key, modified FROM datasets WHERE source_id = ?", (src["id"],))}
    items, total, offset, errors = [], None, 0, 0
    while True:
        try:
            d = c.json(ONS_API, params={"content_type": "dataset_landing_page", "limit": ONS_PAGE, "offset": offset})
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[{src['id']}]   page at offset={offset} failed: {exc}", flush=True)
            break
        total = d.get("count", total)
        got = d.get("items") or []
        items += got
        offset += len(got)
        if not got or offset >= (total or 0) or (limit and len(items) >= limit):
            break
    if limit:
        items = items[:limit]
    rows, res_by_key, unchanged = [], {}, 0
    for i, it in enumerate(items, 1):
        uri = (it.get("uri") or "").strip()
        if not uri.startswith("/"):
            continue
        key = f"{src['id']}:{uri}"
        release = norm_date(it.get("release_date"))
        formats: list = []
        n_res = 0
        # The listing has everything but the files. Files are two requests
        # away, so only a new or re-released dataset pays for them.
        if key in known and known[key] == release and release:
            unchanged += 1
            n_res = conn.execute("SELECT count(*) FROM resources WHERE dataset_key = ?", (key,)).fetchone()[0]
            formats = [r[0] for r in conn.execute("SELECT format_norm FROM resources WHERE dataset_key = ?", (key,)) if r[0]]
        else:
            res = []
            try:
                page = c.json(f"{ONS_WEB}{uri}/data")
                editions = page.get("datasets") or []
                if editions:
                    ver_uri = editions[0].get("uri") or ""
                    ver = c.json(f"{ONS_WEB}{ver_uri}/data")
                    for dl in (ver.get("downloads") or []) + (ver.get("supplementaryFiles") or []):
                        f = dl.get("file") or ""
                        if f:
                            res.append((key, f"{ONS_WEB}/file?uri={ver_uri}/{f}", dl.get("title") or f, _ext(f)))
            except Exception as exc:  # noqa: BLE001 — the landing page still stands
                errors += 1
                if errors <= 5:
                    print(f"[{src['id']}]   files for {uri[-60:]}: {exc}", flush=True)
            res_by_key[key] = res
            n_res = len(res)
            formats = [r[3] for r in res]
            if i % 100 == 0:
                print(f"[{src['id']}]   {i}/{len(items)} ({c.requests} requests)", flush=True)
        row = _row(src["id"], uri, it.get("title"), it.get("summary") or it.get("meta_description"),
                   "Office for National Statistics", "Open Government Licence v3.0", None, it.get("release_date"),
                   f"{ONS_WEB}{uri}", it.get("keywords") or [], formats, n_res, now)
        if row:
            rows.append(row)
    _finish(conn, src, started, rows, res_by_key, total, errors, unchanged)


# --- DfE Explore Education Statistics ---------------------------------------

def harvest_ees(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every publication on Explore Education Statistics, as one dataset
    record per publication with the latest release's data files. The
    content API lists publications (sitemap-items), a publication's
    summary, and a release's data sets. explore-education-statistics is
    'Crown copyright … Open Government Licence v3.0' (GOV.UK footer)."""
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    print(f"[{src['id']}] harvesting Explore Education Statistics ...", flush=True)
    known = {k: m for k, m in conn.execute("SELECT key, modified FROM datasets WHERE source_id = ?", (src["id"],))}
    try:
        pubs = c.json(f"{EES_API}/publications/sitemap-items")
    except Exception as exc:  # noqa: BLE001
        print(f"[{src['id']}] publication list failed: {exc}", flush=True)
        return
    if limit:
        pubs = pubs[:limit]
    rows, res_by_key, unchanged, errors = [], {}, 0, 0
    for i, p in enumerate(pubs, 1):
        slug = p.get("slug")
        rels = p.get("releases") or []
        if not slug or not rels:
            continue
        latest = max(rels, key=lambda r: r.get("lastModified") or "")
        key = f"{src['id']}:{slug}"
        modified = norm_date(latest.get("lastModified"))
        try:
            pub = c.json(f"{EES_API}/publications/{slug}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 5:
                print(f"[{src['id']}]   {slug}: {exc}", flush=True)
            continue
        title = pub.get("title") or slug
        summary = pub.get("summary") or pub.get("slug")
        formats: list = []
        if key in known and known[key] == modified and modified:
            unchanged += 1
            n_res = conn.execute("SELECT count(*) FROM resources WHERE dataset_key = ?", (key,)).fetchone()[0]
            formats = [r[0] for r in conn.execute("SELECT format_norm FROM resources WHERE dataset_key = ?", (key,)) if r[0]]
        else:
            res = []
            try:
                dc = c.json(f"{EES_API}/publications/{slug}/releases/{latest['slug']}/data-content")
                rv = dc.get("releaseVersionId") or dc.get("releaseId")
                # the site's own download route (downloadService.ts):
                # /releases/{releaseVersionId}/files?fileIds={fileId} -> a zip of the CSV and its metadata
                for ds in dc.get("dataSets") or []:
                    fid = ds.get("fileId")
                    if fid and rv:
                        res.append((key, f"{EES_API}/releases/{rv}/files?fileIds={fid}",
                                    ds.get("title") or "data set", "zip"))
                for sf in dc.get("supportingFiles") or []:
                    fid = sf.get("id") or sf.get("fileId")
                    if fid and rv:
                        res.append((key, f"{EES_API}/releases/{rv}/files?fileIds={fid}",
                                    sf.get("name") or sf.get("filename") or "supporting file", "zip"))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                if errors <= 5:
                    print(f"[{src['id']}]   files for {slug}: {exc}", flush=True)
            res_by_key[key] = res
            n_res = len(res)
            formats = [r[3] for r in res]
        row = _row(src["id"], slug, title, summary, "Department for Education", "Open Government Licence v3.0",
                   None, latest.get("lastModified"), f"{EES_WEB}/find-statistics/{slug}",
                   [t.get("title") for t in (pub.get("topics") or []) if isinstance(t, dict)] if isinstance(pub.get("topics"), list) else [],
                   formats, n_res, now)
        if row:
            rows.append(row)
        if i % 50 == 0:
            print(f"[{src['id']}]   {i}/{len(pubs)} ({c.requests} requests)", flush=True)
    _finish(conn, src, started, rows, res_by_key, len(pubs), errors, unchanged)


# --- GOV.UK research and statistics -----------------------------------------

GOVUK_SEARCH = "https://www.gov.uk/api/search.json"
GOVUK_CONTENT = "https://www.gov.uk/api/content"
GOVUK_WEB = "https://www.gov.uk"
GOVUK_PAGE = 1500
_CT_FORMAT = {"text/csv": "csv", "spreadsheetml": "xlsx", "ms-excel": "xls", "opendocument.spreadsheet": "ods",
              "application/pdf": "pdf", "zip": "zip", "json": "json", "xml": "xml", "text/plain": "txt",
              "wordprocessingml": "docx", "msword": "doc", "opendocument.text": "odt"}


def _ct_format(content_type: str | None, url: str = "") -> str:
    ct = (content_type or "").lower()
    for needle, fmt in _CT_FORMAT.items():
        if needle in ct:
            return fmt
    return _ext(url)


def harvest_govuk(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every statistics release on GOV.UK, in two passes. The search API
    lists them all in a minute (title, description, department, date); the
    content API gives each one's attachments, one request per release, so
    attachments are fetched newest-first within a budget per run and the
    rest wait for the next night. A release whose public timestamp has not
    moved since its attachments were fetched is not fetched again.
    GOV.UK: 'All content is available under the Open Government Licence
    v3.0, except where otherwise stated.'"""
    cfg = src.get("govuk") or {}
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    state_path = Path(conn.execute("PRAGMA database_list").fetchone()[2]).parent / "govuk_attachments.json"
    fetched = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    print(f"[{src['id']}] listing GOV.UK statistics ...", flush=True)
    items, errors = [], 0
    for doc_type in cfg.get("document_types") or ["national_statistics", "official_statistics", "statistical_data_set"]:
        start, total = 0, None
        while True:
            try:
                d = c.json(GOVUK_SEARCH, params={
                    "filter_content_store_document_type": doc_type, "count": GOVUK_PAGE, "start": start,
                    "fields": "title,description,link,public_timestamp,organisations,format,display_type",
                    "order": "-public_timestamp"})
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"[{src['id']}]   {doc_type} at start={start} failed: {exc}", flush=True)
                break
            total = d.get("total", total)
            got = d.get("results") or []
            items += got
            start += len(got)
            if not got or start >= (total or 0) or (limit and len(items) >= limit):
                break
        if limit and len(items) >= limit:
            break
    if limit:
        items = items[:limit]
    seen: set[str] = set()
    rows, keys_by_link = [], {}
    for it in items:
        link = (it.get("link") or "").strip()
        if not link.startswith("/") or link in seen:
            continue
        seen.add(link)
        key = f"{src['id']}:{link}"
        keys_by_link[link] = key
        orgs = [o.get("title") for o in (it.get("organisations") or []) if isinstance(o, dict) and o.get("title")]
        publisher = orgs[0] if orgs else "GOV.UK"
        tags = [it.get("display_type") or it.get("format") or ""] + [o.get("acronym") for o in (it.get("organisations") or []) if isinstance(o, dict) and o.get("acronym")]
        formats = [r[0] for r in conn.execute("SELECT format_norm FROM resources WHERE dataset_key = ?", (key,)) if r[0]]
        n_res = len(formats)
        row = _row(src["id"], link, it.get("title"), it.get("description"), publisher, "Open Government Licence v3.0",
                   None, it.get("public_timestamp"), f"{GOVUK_WEB}{link}", tags, formats, n_res, now)
        if row:
            rows.append(row)
    conn.executemany(UPSERT, rows)
    conn.commit()
    print(f"[{src['id']}] listed {len(rows)} releases; fetching attachments ...", flush=True)
    # attachments: newest first, within the budget, only where the release moved
    budget = int(cfg.get("attachments_per_run", 3000))
    if limit:
        budget = min(budget, limit)
    todo = [it for it in items if it.get("link") in keys_by_link
            and fetched.get(it["link"]) != it.get("public_timestamp")]
    todo.sort(key=lambda it: it.get("public_timestamp") or "", reverse=True)
    done_att, n_files = 0, 0
    for it in todo[:budget]:
        link, key = it["link"], keys_by_link[it["link"]]
        try:
            doc = c.json(f"{GOVUK_CONTENT}{link}")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 5:
                print(f"[{src['id']}]   content {link[-50:]}: {exc}", flush=True)
            continue
        det = doc.get("details") or {}
        res = []
        for a in (det.get("attachments") or []):
            url = a.get("url") or ""
            if url.startswith("http"):
                res.append((key, url, (a.get("title") or "")[:200], _ct_format(a.get("content_type"), url)))
        conn.execute("DELETE FROM resources WHERE dataset_key = ?", (key,))
        conn.executemany("INSERT OR REPLACE INTO resources VALUES (?, ?, ?, ?)", res)
        fmts = [r[3] for r in res]
        conn.execute("UPDATE datasets SET formats_raw = ?, formats_norm = ?, resource_count = ?, created = COALESCE(created, ?) WHERE key = ?",
                     (json.dumps(fmts), json.dumps(norm_formats(fmts)), len(res), norm_date(doc.get("first_published_at")), key))
        fetched[link] = it.get("public_timestamp")
        done_att += 1
        n_files += len(res)
        if done_att % 200 == 0:
            conn.commit()
            state_path.write_text(json.dumps(fetched), encoding="utf-8")
            print(f"[{src['id']}]   attachments {done_att}/{min(len(todo), budget)} ({n_files} files)", flush=True)
    state_path.write_text(json.dumps(fetched), encoding="utf-8")
    finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("INSERT INTO harvest_runs VALUES (?, ?, ?, ?, ?, ?)",
                 (src["id"], started, finished, len(items), len(rows), errors))
    conn.commit()
    print(f"[{src['id']}] done: {len(rows)} releases stored; attachments fetched for {done_att} "
          f"({n_files} files), {len(todo) - done_att} still waiting; {errors} errors", flush=True)


# --- Nomis (ONS labour market and census tables) ----------------------------

NOMIS_DEF = "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json"
NOMIS_WEB = "https://www.nomisweb.co.uk"


def harvest_nomis(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every dataset Nomis serves, from its one SDMX definition file: id,
    name, description, keywords, status and last-updated date. The
    downloadable resource is the dataset's CSV endpoint on the API, which
    takes the reader's own geography and time selection."""
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    print(f"[{src['id']}] harvesting Nomis definitions ...", flush=True)
    try:
        d = c.json(NOMIS_DEF)
        fams = d["structure"]["keyfamilies"]["keyfamily"]
    except Exception as exc:  # noqa: BLE001
        print(f"[{src['id']}] definition file failed: {exc}", flush=True)
        return
    if limit:
        fams = fams[:limit]
    rows, res_by_key = [], {}
    for k in fams:
        ident = k.get("id")
        if not ident:
            continue
        ann = {a.get("annotationtitle"): a.get("annotationtext") for a in ((k.get("annotations") or {}).get("annotation") or [])}
        name = k.get("name")
        name = name.get("value") if isinstance(name, dict) else name
        desc = k.get("description")
        desc = desc.get("value") if isinstance(desc, dict) else desc
        mnemonic = str(ann.get("Mnemonic") or "").strip()
        landing = f"{NOMIS_WEB}/datasets/{mnemonic}" if mnemonic else f"{NOMIS_WEB}/api/v01/dataset/{ident}.def.htm"
        key = f"{src['id']}:{ident}"
        res = [(key, f"{NOMIS_WEB}/api/v01/dataset/{ident}.data.csv", "data (CSV via the Nomis API; select a geography)", "csv"),
               (key, f"{NOMIS_WEB}/api/v01/dataset/{ident}.def.sdmx.json", "definition (SDMX)", "json")]
        res_by_key[key] = res
        tags = [t.strip() for t in str(ann.get("Keywords") or "").split(",") if t.strip()] + [str(ann.get("Status") or "")]
        row = _row(src["id"], ident, name, desc or ann.get("SubDescription"), "Office for National Statistics (Nomis)",
                   "Open Government Licence v3.0", ann.get("FirstReleased"), ann.get("LastUpdated"), landing, tags,
                   ["csv", "json"], 2, now)
        if row:
            rows.append(row)
    _finish(conn, src, started, rows, res_by_key, len(fams), 0, 0)


# --- Fingertips (OHID public health profiles) --------------------------------

FT_API = "https://fingertips.phe.org.uk/api"
FT_WEB = "https://fingertips.phe.org.uk"


def harvest_fingertips(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every indicator in OHID's public health profiles, from the metadata
    endpoint, with the API's CSV of all its data by upper-tier local
    authority as the resource. fingertips.phe.org.uk: 'All content is
    available under the Open Government Licence, except where otherwise
    stated'."""
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    print(f"[{src['id']}] harvesting Fingertips indicator metadata ...", flush=True)
    try:
        meta = c.json(f"{FT_API}/indicator_metadata/all")
    except Exception as exc:  # noqa: BLE001
        print(f"[{src['id']}] metadata failed: {exc}", flush=True)
        return
    items = list(meta.values())
    if limit:
        items = items[:limit]
    rows, res_by_key = [], {}
    for m in items:
        iid = m.get("IID")
        if not iid:
            continue
        d = m.get("Descriptive") or {}
        key = f"{src['id']}:{iid}"
        definition = " ".join(x for x in (d.get("Definition"), d.get("Rationale")) if x) or d.get("Name")
        unit = (m.get("Unit") or {}).get("Label")
        res = [(key, f"{FT_API}/all_data/csv/by_indicator_id?indicator_ids={iid}&child_area_type_id=402&parent_area_type_id=6",
                "all data by upper-tier local authority (CSV)", "csv"),
               (key, f"{FT_API}/all_data/csv/by_indicator_id?indicator_ids={iid}&child_area_type_id=502&parent_area_type_id=6",
                "all data by lower-tier local authority (CSV)", "csv")]
        res_by_key[key] = res
        tags = [t for t in (unit, d.get("DataSource")) if t]
        row = _row(src["id"], str(iid), d.get("Name"), definition, "Office for Health Improvement and Disparities (Fingertips)",
                   "Open Government Licence v3.0", None, m.get("LatestChangeTimestampOverride"), f"{FT_WEB}/search/{iid}",
                   tags, ["csv"], 2, now)
        if row:
            rows.append(row)
    _finish(conn, src, started, rows, res_by_key, len(meta), 0, 0)


# --- statistics.gov.scot (Scottish Government open statistics) ---------------

SCOT_SPARQL = "https://statistics.gov.scot/sparql.json"
SCOT_QUERY = """
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?ds ?title ?comment ?modified ?issued ?publisher WHERE {
  ?ds a <http://publishmydata.com/def/dataset#Dataset> ; rdfs:label ?title .
  OPTIONAL { ?ds rdfs:comment ?comment }
  OPTIONAL { ?ds dcterms:modified ?modified }
  OPTIONAL { ?ds dcterms:issued ?issued }
  OPTIONAL { ?ds dcterms:publisher ?pub . ?pub rdfs:label ?publisher }
}"""


def harvest_scotstats(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every dataset on statistics.gov.scot, from its SPARQL endpoint, with
    the site's whole-cube CSV download as the resource."""
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    print(f"[{src['id']}] querying statistics.gov.scot ...", flush=True)
    try:
        d = c.json(SCOT_SPARQL, params={"query": SCOT_QUERY})
        binds = d["results"]["bindings"]
    except Exception as exc:  # noqa: BLE001
        print(f"[{src['id']}] SPARQL failed: {exc}", flush=True)
        return
    if limit:
        binds = binds[:limit]
    rows, res_by_key = [], {}
    from urllib.parse import quote
    for b in binds:
        uri = (b.get("ds") or {}).get("value") or ""
        if not uri:
            continue
        slug = uri.rsplit("/", 1)[-1]
        key = f"{src['id']}:{slug}"
        landing = uri.replace("http://", "https://", 1)
        res = [(key, f"https://statistics.gov.scot/downloads/cube-table?uri={quote(uri, safe='')}", "whole dataset (CSV)", "csv"),
               (key, landing.rstrip("/") + ".json", "dataset metadata (JSON)", "json")]
        res_by_key[key] = res
        pub = (b.get("publisher") or {}).get("value") or "Scottish Government"
        row = _row(src["id"], slug, (b.get("title") or {}).get("value"), (b.get("comment") or {}).get("value"),
                   pub, "Open Government Licence v3.0", (b.get("issued") or {}).get("value"),
                   (b.get("modified") or {}).get("value"), landing, [], ["csv", "json"], 2, now)
        if row:
            rows.append(row)
    _finish(conn, src, started, rows, res_by_key, len(binds), 0, 0)


# --- NISRA data portal (PxStat) ----------------------------------------------

NISRA_API = ("https://ws-data.nisra.gov.uk/public/api.jsonrpc?data="
             "%7B%22jsonrpc%22:%222.0%22,%22method%22:%22PxStat.Data.Cube_API.ReadCollection%22,"
             "%22params%22:%7B%22language%22:%22en%22%7D%7D")
NISRA_WEB = "https://data.nisra.gov.uk"


def harvest_nisra(src: dict, conn: sqlite3.Connection, limit: int | None) -> None:
    """Every table on NISRA's data portal, from PxStat's ReadCollection: a
    JSON-stat item per table with its label, matrix code, CSV link and
    copyright. nisra.gov.uk/crown-copyright: released under the Open
    Government Licence."""
    c = _Client()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now = started
    print(f"[{src['id']}] harvesting NISRA PxStat collection ...", flush=True)
    try:
        d = c.json(NISRA_API)
        items = (d.get("result") or d).get("link", {}).get("item") or []
    except Exception as exc:  # noqa: BLE001
        print(f"[{src['id']}] collection failed: {exc}", flush=True)
        return
    if limit:
        items = items[:limit]
    rows, res_by_key = [], {}
    for it in items:
        matrix = ((it.get("extension") or {}).get("matrix")) or ""
        if not matrix:
            continue
        key = f"{src['id']}:{matrix}"
        res = []
        for alt in ((it.get("link") or {}).get("alternate") or []):
            href = alt.get("href") or ""
            if href.startswith("http"):
                fmt = "csv" if "csv" in (alt.get("type") or "") else "json" if "json" in (alt.get("type") or "") else _ext(href)
                res.append((key, href, f"table {matrix} ({fmt.upper()})", fmt))
        if it.get("href"):
            res.append((key, it["href"], f"table {matrix} (JSON-stat)", "json"))
        res_by_key[key] = res
        note = (it.get("note") or [""])[0] if isinstance(it.get("note"), list) else it.get("note")
        subject = ((it.get("extension") or {}).get("subject") or {}).get("value") or ""
        product = ((it.get("extension") or {}).get("product") or {}).get("value") or ""
        tags = [t for t in (subject, product) if t]
        row = _row(src["id"], matrix, it.get("label"), note or it.get("label"), "Northern Ireland Statistics and Research Agency",
                   "Open Government Licence v3.0", None, it.get("updated"), f"{NISRA_WEB}/table/{matrix}", tags,
                   [r[3] for r in res], len(res), now)
        if row:
            rows.append(row)
    _finish(conn, src, started, rows, res_by_key, len(items), 0, 0)
