"""Licence-gated, polite, hash-addressed intake for one dataset family.

Derived from Codex's pilot (September 2026) and changed where the brief
said it must change before anything scales:

  * every host is asked at most once per 1.5 seconds, the same spacing the
    link checker uses — the pilot asked Brent four times a second and was
    told 429;
  * Retry-After is honoured; a 429 or 503 parks the whole host for the rest
    of the run, and is recorded as "refused this time", never as "gone";
  * a retry budget per host per run.

Everything else keeps the pilot's shape. Originals, licence evidence and
extracted tables are stored by SHA-256 under data/families/; a source is a
job that moves through the ladder

    queued → fetched → extracted (needs_review) → mapped → reviewed

and nothing is published from here. What the intake produces is evidence.

Licence: an explicit Open Government Licence v1–3, from the portal's own
metadata where the registry could name it (CKAN, ArcGIS item), otherwise
from what the index harvested — recorded as the weaker kind. Generic
"uk-ogl", custom prose, conflicting versions and silence all refuse.

Usage:  DATA_DIR=... python families/intake.py recycling_centres [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import ipaddress
import json
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import USER_AGENT  # noqa: E402
from paths import DATA_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
STORE = DATA_DIR / "families"
LIMITS = {
    "max_file_bytes": 25_000_000, "max_metadata_bytes": 2_000_000,
    "max_storage_bytes": 2_000_000_000, "min_free_bytes": 20_000_000_000,
    "max_pages": 100, "max_rows": 50_000, "max_output_bytes": 20_000_000,
    "job_timeout_seconds": 120, "host_spacing_seconds": 1.5, "host_retry_budget": 3,
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
    id TEXT PRIMARY KEY, family TEXT, dataset_key TEXT, publisher TEXT, portal TEXT,
    title TEXT, resource_url TEXT, format TEXT, licence_kind TEXT, evidence_url TEXT,
    evidence_sha TEXT, licence_json TEXT, state TEXT, detail TEXT, blob_sha TEXT,
    extraction_sha TEXT, extractor TEXT, checked_at TEXT, etag TEXT, last_modified TEXT,
    candidates TEXT, series INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS files(
    job_id TEXT, url TEXT, format TEXT, name TEXT, blob_sha TEXT, extraction_sha TEXT,
    extractor TEXT, etag TEXT, last_modified TEXT, state TEXT, detail TEXT, fetched_at TEXT,
    PRIMARY KEY (job_id, url));
CREATE TABLE IF NOT EXISTS attempts(
    id INTEGER PRIMARY KEY, job_id TEXT, started_at TEXT, seconds REAL, state TEXT,
    downloaded_bytes INTEGER, blob_sha TEXT, detail TEXT);
"""


class Refused(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


# --- licence --------------------------------------------------------------

_OGL_URL = re.compile(r"nationalarchives\.gov\.uk/doc/open-government-licence(?:/version/([123]))?", re.I)
_OGL_NAME = re.compile(r"open\s+government\s+licen[cs]e(?:\s*\(?\s*(?:ogl)?\s*v?(?:ersion)?\s*([123])(?:\.0)?\s*\)?)?", re.I)
# Words that mean a licence other than the OGL is in force, or that reuse is
# restricted. Ordnance Survey *attribution* ("Contains OS data © Crown
# copyright") is not on this list: it is a condition the OGL itself allows.
_RESTRICTED = re.compile(r"inspire\s+end\s+user|end\s+user\s+licen[cs]e|public\s+sector\s+end\s+user|psma|pseul|"
                         r"derived\s+data\s+exemption|non.?commercial|no.?derivatives|all\s+rights\s+reserved|"
                         r"notspecified|not\s+specified|restricted|cc.?by.?nc|creative\s+commons", re.I)
_NEUTRAL = {"uk-ogl", "uk_ogl", "ogl", "ogl-uk", "uk open government licence (ogl)", "open government license", "",
            "http://reference.data.gov.uk/id/open-government-licence",
            "https://reference.data.gov.uk/id/open-government-licence"}


def licence(fields) -> dict:
    """An Open Government Licence, stated unambiguously, or refuse.

    Every value — a CKAN id, a URL, an ArcGIS licenseInfo paragraph — is read
    the same way. Text that names a restricted licence (INSPIRE end-user
    terms, OS PSMA, "derived data exemption", non-commercial) refuses, even
    if the OGL is mentioned beside it: mixed terms need a person. Otherwise
    the value must name the OGL, by URL or by name; a generic identifier
    such as data.gov.uk's "uk-ogl" counts as naming it, because the National
    Archives holds all OGL versions compatible and v3 terms apply. OS
    attribution wording is not a restriction: 4 of the first refused
    councils were refused for saying "Contains OS data © Crown copyright"
    in front of an OGL link. The exact statement is kept as evidence.
    """
    versions: set[str] = set()
    named = False
    for value in fields:
        if not value:
            continue
        raw = html.unescape(str(value))
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        low = text.lower()
        links = re.findall(r"href=[\"']([^\"']+)", raw)
        if low == "uk_oglv3.0":
            low = "open government licence v3.0"
        m_id = re.fullmatch(r"ogl-uk-([123])\.0", low)
        if m_id:
            versions.add(m_id.group(1)); named = True; continue
        if low in _NEUTRAL:
            named = True; continue
        if _RESTRICTED.search(low) or any(_RESTRICTED.search(l) for l in links):
            raise Refused("Licence text names a restricted or non-OGL licence: " + text[:120])
        hit = False
        for m in list(_OGL_URL.finditer(low)) + [_OGL_URL.search(l) for l in links if _OGL_URL.search(l)]:
            hit = True
            if m and m.group(1):
                versions.add(m.group(1))
        m = _OGL_NAME.search(low)
        if m:
            hit = True
            if m.group(1):
                versions.add(m.group(1))
        if hit:
            named = True
        else:
            raise Refused("Unrecognised licence statement: " + text[:160])
    if not named:
        raise Refused("No licence stated")
    if len(versions) > 1:
        raise Refused("Conflicting OGL versions stated")
    v = versions.pop() if versions else None
    return {"id": f"OGL-UK-{v}.0" if v else "OGL-UK",
            "version": f"{v}.0" if v else "unstated (v3 terms apply)",
            "url": f"https://www.nationalarchives.gov.uk/doc/open-government-licence/version/{v or 3}/",
            "attribution": ("Contains public sector information licensed under the Open Government Licence"
                            + (f" v{v}.0." if v else " (version unstated; v3 terms apply)."))}


def licence_from_metadata(kind: str, doc: dict) -> dict:
    if kind == "ckan":
        if doc.get("success") is not True:
            raise Refused("Unsuccessful CKAN response")
        p = doc["result"]
        return licence([p.get(k) for k in ("license_id", "license_title", "license_url")])
    if kind == "arcgis":
        if doc.get("error"):
            raise Refused("ArcGIS item error")
        return licence([doc.get("licenseInfo")])
    raise Refused("Unknown metadata kind " + kind)


# --- fetching, politely ---------------------------------------------------

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_last_hit: dict[str, float] = defaultdict(float)
_parked: dict[str, str] = {}
_retries: dict[str, int] = defaultdict(int)


def _validate(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise Refused("Unacceptable URL")
    try:
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise Refused("URL resolves to a private address")
    except socket.gaierror:
        raise Refused("DNS failure")


def _ascii_url(url: str) -> str:
    """Publishers put pounds signs and spaces in file names. urllib refuses a
    non-ASCII URL outright, so percent-encode what needs it and nothing else."""
    from urllib.parse import quote
    return quote(url, safe=":/?&=%+,;@#~$!*'()[]-._")


def fetch(url: str, limit: int, headers: dict | None = None) -> tuple[bytes | None, dict, str]:
    """One request, spaced per host, redirects followed by hand, size-capped."""
    url = _ascii_url(url)
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    opener = build_opener(NoRedirect, HTTPSHandler(context=ctx))
    start = time.monotonic()
    for _ in range(6):
        _validate(url)
        host = urlparse(url).hostname or ""
        if host in _parked:
            raise Refused(f"host parked this run: {_parked[host]}")
        wait = LIMITS["host_spacing_seconds"] - (time.monotonic() - _last_hit[host])
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.monotonic()
        try:
            resp = opener.open(Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})}), timeout=45)
        except HTTPError as err:
            if err.code == 304:
                return None, dict(err.headers), url
            if err.code in (301, 302, 303, 307, 308) and err.headers.get("Location"):
                from urllib.parse import urljoin
                url = urljoin(url, err.headers["Location"])
                continue
            if err.code in (429, 503):
                retry = err.headers.get("Retry-After")
                _parked[host] = f"HTTP {err.code}" + (f", Retry-After {retry}" if retry else "")
                raise Refused(f"rate limited (HTTP {err.code}); host parked for this run")
            raise Refused(f"HTTP {err.code}")
        except URLError as err:
            _retries[host] += 1
            if _retries[host] >= LIMITS["host_retry_budget"]:
                _parked[host] = "retry budget spent"
            raise Refused(f"unreachable: {getattr(err, 'reason', err)}")
        with resp:
            declared = resp.headers.get("Content-Length")
            if declared and int(declared) > limit:
                raise Refused("Declared download exceeds byte limit")
            chunks, size = [], 0
            while True:
                if time.monotonic() - start > 120:
                    raise Refused("Download time limit exceeded")
                chunk = resp.read(min(65536, limit - size + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    raise Refused("Download exceeds byte limit")
            return b"".join(chunks), dict(resp.headers), url
    raise Refused("Too many redirects")


# --- storage ----------------------------------------------------------------

def _used() -> int:
    return sum(p.stat().st_size for p in STORE.rglob("*") if p.is_file())


def capacity(reserve: int = 0) -> None:
    if _used() + reserve > LIMITS["max_storage_bytes"]:
        raise Refused("families storage budget reached")
    if shutil.disk_usage(STORE).free - reserve < LIMITS["min_free_bytes"]:
        raise Refused("free-disk reserve reached")


def store(folder: str, body: bytes) -> str:
    digest = sha(body)
    path = STORE / folder / digest
    if not path.exists():
        capacity(len(body))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
    return digest


def connect() -> sqlite3.Connection:
    STORE.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(STORE / "families.db", timeout=15)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    # A database from before candidates existed gets the column added.
    have = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    if "candidates" not in have:
        c.execute("ALTER TABLE jobs ADD COLUMN candidates TEXT")
    if "series" not in have:
        c.execute("ALTER TABLE jobs ADD COLUMN series INTEGER DEFAULT 0")
    c.commit()
    return c


# --- the run ----------------------------------------------------------------

def admit(c: sqlite3.Connection, family: str, src: dict) -> str | None:
    """Establish licence evidence for one source; queue its job or refuse."""
    checked = now()
    job_id = sha((family + "\n" + src["dataset_key"]).encode())   # a job is a dataset
    try:
        if src["licence_kind"] in ("ckan", "arcgis") and src["metadata_url"]:
            body, _, _ = fetch(src["metadata_url"], LIMITS["max_metadata_bytes"])
            evidence_sha = store("evidence", body)
            approval = licence_from_metadata(src["licence_kind"], json.loads(body))
            evidence_url, kind = src["metadata_url"], src["licence_kind"]
        else:
            raw = src.get("index_licence_raw") or ""
            approval = licence([raw])
            body = json.dumps({"index_licence_raw": raw, "harvested_at": src["index_harvested_at"],
                               "dataset_key": src["dataset_key"]}).encode()
            evidence_sha = store("evidence", body)
            evidence_url, kind = src["landing_url"], "index"
    except (Refused, ValueError, KeyError, json.JSONDecodeError) as err:
        # A refusal keeps its evidence too: the statement we refused on is
        # the thing a reviewer needs to see, and the thing that proves we
        # were right — or lets the gate be widened on real wording.
        refused_sha = locals().get("evidence_sha")
        c.execute("""INSERT INTO jobs(id,family,dataset_key,publisher,portal,title,resource_url,format,
                     licence_kind,evidence_url,evidence_sha,state,detail,checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET state=excluded.state, detail=excluded.detail,
                     evidence_sha=COALESCE(excluded.evidence_sha, jobs.evidence_sha),
                     checked_at=excluded.checked_at""",
                  (job_id, family, src["dataset_key"], src["publisher"], src["portal"], src["title"],
                   src["resource"]["url"], src["resource"]["format"], src["licence_kind"],
                   src.get("metadata_url") or src["landing_url"], refused_sha, "not_admitted", str(err)[:400], checked))
        c.commit()
        print(f"  refused  {src['publisher'][:34]:34} {str(err)[:80]}", flush=True)
        return None
    c.execute("DELETE FROM jobs WHERE family=? AND dataset_key=? AND id<>?",
              (family, src["dataset_key"], job_id))          # a file-keyed job from before
    c.execute("""INSERT INTO jobs(id,family,dataset_key,publisher,portal,title,resource_url,format,
                 licence_kind,evidence_url,evidence_sha,licence_json,state,checked_at,candidates,series)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'queued',?,?,?)
                 ON CONFLICT(id) DO UPDATE SET evidence_sha=excluded.evidence_sha,
                 licence_json=excluded.licence_json, licence_kind=excluded.licence_kind,
                 evidence_url=excluded.evidence_url,
                 state=CASE WHEN jobs.state='needs_review' THEN 'needs_review' ELSE 'queued' END,
                 checked_at=excluded.checked_at, candidates=excluded.candidates, series=excluded.series""",
              (job_id, family, src["dataset_key"], src["publisher"], src["portal"], src["title"],
               src["resource"]["url"], src["resource"]["format"], kind, evidence_url, evidence_sha,
               json.dumps(approval), checked, json.dumps(src.get("candidates") or [src["resource"]]),
               1 if src.get("series") else 0))
    c.commit()
    return job_id


def _try_one(job: dict, cand: dict, out: Path) -> tuple[str, str, dict, int, str]:
    """Fetch and extract one candidate. Returns (blob, extraction, headers, bytes, detail)."""
    from extract import VERSION
    headers = {}
    same = cand["url"] == job["resource_url"]
    if same and job["blob_sha"] and (STORE / "blobs" / job["blob_sha"]).is_file():
        if job["etag"]:
            headers["If-None-Match"] = job["etag"]
        elif job["last_modified"]:
            headers["If-Modified-Since"] = job["last_modified"]
    body, rh, _ = fetch(cand["url"], LIMITS["max_file_bytes"], headers)
    downloaded = len(body) if body is not None else 0
    blob = store("blobs", body) if body is not None else job["blob_sha"]
    if not blob:
        raise Refused("304 without a stored original")
    if same and job["extraction_sha"] and job["blob_sha"] == blob and job["extractor"] == VERSION \
            and (STORE / "tables" / job["extraction_sha"]).is_file():
        return blob, job["extraction_sha"], rh, downloaded, "unchanged source; extraction reused"
    r = subprocess.run([sys.executable, str(HERE / "extract.py"), str(STORE / "blobs" / blob),
                        cand["format"], str(out), json.dumps(LIMITS)],
                       capture_output=True, text=True, timeout=LIMITS["job_timeout_seconds"])
    if r.returncode:
        raise Refused(r.stderr.strip()[-300:] or "extraction failed")
    return blob, store("tables", out.read_bytes()), rh, downloaded, "tables extracted; mapping needed"


def process(c: sqlite3.Connection, job_id: str) -> None:
    from extract import VERSION
    job = dict(c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    tmp = STORE / "tmp"
    tmp.mkdir(exist_ok=True)
    out = tmp / f"{job_id}.json"
    started, t0, downloaded, blob = now(), time.monotonic(), 0, None
    cands = json.loads(job.get("candidates") or "[]") or [{"url": job["resource_url"], "format": job["format"]}]
    series = bool(job.get("series"))
    errors, got = [], []
    try:
        capacity(LIMITS["max_file_bytes"] + LIMITS["max_output_bytes"])
        for cand in cands:
            prev = c.execute("SELECT * FROM files WHERE job_id=? AND url=?", (job_id, cand["url"])).fetchone()
            probe = dict(job)
            if prev:                      # let the conditional fetch see this file's own state
                probe.update(resource_url=cand["url"], blob_sha=prev["blob_sha"], extraction_sha=prev["extraction_sha"],
                             extractor=prev["extractor"], etag=prev["etag"], last_modified=prev["last_modified"])
            else:
                probe.update(resource_url=cand["url"], blob_sha=None, extraction_sha=None, etag=None, last_modified=None)
            try:
                blob, extraction, rh, downloaded, detail = _try_one(probe, cand, out)
                c.execute("""INSERT INTO files(job_id,url,format,name,blob_sha,extraction_sha,extractor,etag,last_modified,state,detail,fetched_at)
                             VALUES(?,?,?,?,?,?,?,?,?,'extracted',?,?)
                             ON CONFLICT(job_id,url) DO UPDATE SET blob_sha=excluded.blob_sha, extraction_sha=excluded.extraction_sha,
                             extractor=excluded.extractor, etag=excluded.etag, last_modified=excluded.last_modified,
                             state='extracted', detail=excluded.detail, fetched_at=excluded.fetched_at""",
                          (job_id, cand["url"], cand["format"], cand.get("name") or "", blob, extraction, VERSION,
                           rh.get("ETag"), rh.get("Last-Modified"), detail, now()))
                got.append((cand, blob, extraction, rh, downloaded, detail))
                if series:
                    print(f"    file {len(got):>3}  {downloaded:>9,} B  {cand['url'][-50:]}", flush=True)
                else:
                    break
            except Refused as err:
                errors.append(f"{cand['format']} {cand['url'][-60:]}: {str(err)[-120:]}")
                if prev and prev["extraction_sha"] and (STORE / "tables" / prev["extraction_sha"]).is_file():
                    c.execute("UPDATE files SET detail=? WHERE job_id=? AND url=?",
                              (f"latest attempt failed ({str(err)[-120:]}); previous snapshot kept", job_id, cand["url"]))
                    got.append((cand, prev["blob_sha"], prev["extraction_sha"], {}, 0, "previous snapshot kept"))
                    if not series:
                        break
                else:
                    c.execute("""INSERT INTO files(job_id,url,format,name,state,detail,fetched_at) VALUES(?,?,?,?,'failed',?,?)
                                 ON CONFLICT(job_id,url) DO UPDATE SET state='failed', detail=excluded.detail, fetched_at=excluded.fetched_at""",
                              (job_id, cand["url"], cand["format"], cand.get("name") or "", str(err)[-300:], now()))
                if "parked" in str(err):
                    break                      # the host said stop; the rest are on it too
        if not got:
            raise Refused(" | ".join(errors)[-400:])
        first = got[0]
        blob, extraction, rh, downloaded, detail = first[1], first[2], first[3], sum(g[4] for g in got), first[5]
        n_ok, n_all = len(got), len(cands)
        summary = (f"{n_ok} of {n_all} files extracted" if series else detail
                   + (f" (candidate {cands.index(first[0]) + 1} of {n_all})" if n_all > 1 else ""))
        c.execute("""UPDATE jobs SET state='needs_review', detail=?, blob_sha=?, extraction_sha=?,
                     extractor=?, etag=?, last_modified=?, resource_url=?, format=? WHERE id=?""",
                  (summary, blob, extraction, VERSION, rh.get("ETag"), rh.get("Last-Modified"),
                   first[0]["url"], first[0]["format"], job_id))
        print(f"  ok       {job['publisher'][:34]:34} {first[0]['format']:7} {downloaded:>9,} B  {summary}", flush=True)
    except Exception as err:  # noqa: BLE001 - recorded, never fatal to the run
        if job["extraction_sha"] and (STORE / "tables" / job["extraction_sha"]).is_file():
            # The last successful snapshot stays what we serve; the latest
            # attempt is recorded as refused. A rate limit or an outage is
            # never allowed to look like the data disappearing.
            c.execute("UPDATE jobs SET state='needs_review', detail=? WHERE id=?",
                      (f"latest fetch attempt failed ({str(err)[-200:]}); serving the previous snapshot", job_id))
            print(f"  kept     {job['publisher'][:34]:34} previous snapshot; attempt failed: {str(err)[-60:]}", flush=True)
        else:
            c.execute("UPDATE jobs SET state='fetch_failed', detail=? WHERE id=?", (str(err)[-400:], job_id))
            print(f"  failed   {job['publisher'][:34]:34} {str(err)[-80:]}", flush=True)
    finally:
        if out.exists():
            out.unlink()
        cur = c.execute("SELECT state, detail FROM jobs WHERE id=?", (job_id,)).fetchone()
        c.execute("INSERT INTO attempts(job_id,started_at,seconds,state,downloaded_bytes,blob_sha,detail) VALUES(?,?,?,?,?,?,?)",
                  (job_id, started, round(time.monotonic() - t0, 3), cur["state"], downloaded, blob, cur["detail"]))
        c.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("family")
    ap.add_argument("--limit", type=int, default=0, help="stop after N admitted sources")
    ap.add_argument("--only-portal", default=None)
    args = ap.parse_args()
    reg = json.loads((HERE / "registry" / f"{args.family}.json").read_text(encoding="utf-8"))
    c = connect()
    capacity()
    lock = sqlite3.connect(STORE / "worker-lock.db", timeout=0)
    lock.execute("BEGIN EXCLUSIVE")
    try:
        sources = [s for s in reg["sources"] if not args.only_portal or s["portal"] == args.only_portal]
        print(f"{args.family}: {len(sources)} sources in registry", flush=True)
        queued = []
        for s in sources:
            jid = admit(c, args.family, s)
            if jid:
                queued.append(jid)
            if args.limit and len(queued) >= args.limit:
                break
        print(f"{len(queued)} admitted on licence; fetching", flush=True)
        for jid in queued:
            process(c, jid)
        c.execute("DELETE FROM attempts WHERE id NOT IN (SELECT id FROM attempts ORDER BY id DESC LIMIT 2000)")
        c.commit()
        states = dict(c.execute("SELECT state, COUNT(*) FROM jobs WHERE family=? GROUP BY state", (args.family,)).fetchall())
        print(f"done: {states}; parked hosts: {_parked or 'none'}", flush=True)
    finally:
        lock.rollback()
        lock.close()
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
