"""Web UI + JSON API for the UK Open Data Index.

    uvicorn server:app --port 8000

Holds one warm SearchEngine so queries are fast; hot-reloads vectors as
embed_index.py checkpoints land. Public API: /api/search, /api/stats,
/api/sources — interactive docs at /docs.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               StreamingResponse)

import pagerender
from querylog import log_query
from search import SearchEngine

ROOT = Path(__file__).parent
REPO_URL = "https://github.com/dominicm2023/open-data-uk"
# Absolute URLs (canonical tags, sitemap, social previews) have to name the
# real host, so a dev copy must not advertise itself as production.
SITE_URL = os.environ.get("SITE_URL", "https://open-data.org.uk").rstrip("/")
ATTRIBUTION = ("Contains public sector information licensed under the Open "
               "Government Licence v3.0 and other licences as stated per "
               "dataset. Metadata collated by the UK Open Data Index.")

# Light per-IP rate limit for the search endpoint (protects the free host,
# not a security boundary)
RATE_LIMIT = 30          # requests
RATE_WINDOW = 60         # seconds
_hits: dict[str, deque] = defaultdict(deque)
_last_prune = 0.0

engine = SearchEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the model and vectors before the first request hits.

    Never fatal. If the index is missing or corrupt we still start, so
    /health can report *what* is wrong and a monitor can say so — rather
    than the unit refusing to boot and systemd restart-looping with a
    stack trace nobody sees.
    """
    for step, fn in (("model", lambda: engine.model),
                     ("index", engine.stats)):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"startup warning: could not warm {step}: "
                  f"{type(exc).__name__}: {exc}", flush=True)
    yield


app = FastAPI(
    title="UK Open Data Index API",
    description=(
        "One search across the UK's scattered open government data. "
        "Hybrid semantic + keyword search over the collated, normalised "
        "metadata of every dataset in the indexed portals. Metadata only — "
        "results link to the publisher's own pages.\n\n"
        f"{ATTRIBUTION}"
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _client_ip(request: Request) -> str:
    """The end user's IP, seeing through our own reverse proxies.

    In production the chain is user -> Cloudflare -> Caddy -> here, so
    request.client.host is always 127.0.0.1 and rate-limiting on it would
    put every visitor in the world into one shared bucket. Cloudflare sets
    CF-Connecting-IP; Caddy sets X-Forwarded-For.

    These headers are trivially forgeable, so we only believe them when the
    direct peer is loopback — i.e. the request genuinely arrived via our own
    proxy rather than from outside. Even then this is a fair-use limiter,
    not a security boundary.
    """
    peer = request.client.host if request.client else ""
    if peer in ("127.0.0.1", "::1"):  # arrived via our own Caddy
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return peer or "unknown"


def _prune_hits(now: float) -> None:
    """Drop buckets for IPs we haven't seen this window.

    Without this, _hits keeps one deque per IP that ever visited — a slow
    leak that matters for a process meant to run for months under a memory
    cap. Amortised: only sweeps once per window.
    """
    global _last_prune
    if now - _last_prune < RATE_WINDOW:
        return
    _last_prune = now
    cutoff = now - RATE_WINDOW
    for ip in [ip for ip, dq in _hits.items() if not dq or dq[-1] < cutoff]:
        del _hits[ip]


def _rate_check(request: Request, response: Response) -> None:
    """Enforce the fair-use limit, and always tell the client where it stands.

    Without Retry-After and a remaining count a client can only discover the
    limit by hitting it, then guess how long to wait — so a well-behaved
    integration ends up looking like a badly-behaved one.
    """
    ip = _client_ip(request)
    now = time.time()
    _prune_hits(now)
    dq = _hits[ip]
    while dq and dq[0] < now - RATE_WINDOW:
        dq.popleft()

    reset_in = int(dq[0] + RATE_WINDOW - now) + 1 if dq else RATE_WINDOW
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT)
    response.headers["X-RateLimit-Reset"] = str(reset_in)
    # Counts THIS request, as GitHub and friends do — reporting the budget
    # before consuming it makes a client think it has one more than it does,
    # then hit a 429 it thought it had room for.
    response.headers["X-RateLimit-Remaining"] = str(max(0, RATE_LIMIT - len(dq) - 1))

    if len(dq) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=(f"Rate limit: {RATE_LIMIT} requests per minute. "
                    f"Retry in {reset_in}s. Need more? The whole index is "
                    "rebuildable from open source — see "
                    f"{REPO_URL} — or open an issue there to talk about bulk access."),
            headers={"Retry-After": str(reset_in),
                     "X-RateLimit-Limit": str(RATE_LIMIT),
                     "X-RateLimit-Remaining": "0",
                     "X-RateLimit-Reset": str(reset_in)},
        )
    dq.append(now)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/about", include_in_schema=False)
def about() -> FileResponse:
    return FileResponse(ROOT / "web" / "about.html",
                        headers={"Cache-Control": "no-cache"})


RATE_LIMITED_RESPONSE = {
    429: {
        "description": (
            "Rate limit exceeded. Carries `Retry-After` (seconds) and "
            "`X-RateLimit-Reset`; every successful response also carries "
            "`X-RateLimit-Remaining` so you can pace yourself rather than "
            "discover the limit by hitting it.\n\n"
            "The limit is counted per server process, so with several "
            "processes running you will often get more headroom than the "
            "stated 30/min and `X-RateLimit-Remaining` may jump between "
            "responses. Stay under 30/min and you will never be limited; "
            "anything above that is luck, not contract."),
        "content": {"application/json": {
            "example": {"detail": "Rate limit: 30 requests per minute. Retry in 42s. ..."}}},
    }
}


@app.get("/api/search",
         summary="Search the index",
         responses=RATE_LIMITED_RESPONSE,
         description=(
             "Hybrid semantic + keyword search over dataset metadata, with a "
             "geographic arm when the query names a UK place.\n\n"
             "**What `confidence` means, and doesn't.** It measures how "
             "closely the index matched your *words* — `strong` means we "
             "found datasets that are clearly about your subject. It does "
             "**not** mean your question is answered: if the UK publishes no "
             "open data on that topic, a close match to the nearest subject "
             "will still read `strong`. Treat it as 'we understood the "
             "query', not 'here is the answer'.\n\n"
             "`geo.in_results` is the honest coverage signal: false means we "
             "hold no data published about that place, whatever the "
             "confidence says."))
def api_search(request: Request, response: Response,
               q: str = Query(min_length=1, max_length=500,
                              description="Plain-English search query"),
               k: int = Query(default=10, ge=1, le=50,
                              description="Results to return (max 50)"),
               offset: int = Query(default=0, ge=0, le=200,
                                   description="Skip this many results, for "
                                               "paging past the first page "
                                               "(max 200)")) -> dict:
    _rate_check(request, response)
    payload = engine.search(q, k, offset=offset)
    log_query(q, k, payload)   # anonymous; see querylog.py
    payload["attribution"] = ATTRIBUTION
    return payload


@app.get("/health",
         summary="Liveness and readiness",
         description="200 when the service can actually answer searches, 503 "
                     "when it can't. Deliberately not rate-limited so a "
                     "monitor can poll it, and deliberately does real work "
                     "(a query against the index) rather than just returning "
                     "OK — a process that is up but can't reach its data is "
                     "down as far as a user is concerned.")
def health(response: Response) -> dict:
    import sqlite3
    from paths import connect as db_connect

    checks: dict[str, object] = {}
    ok = True

    # Can we reach the index and does it hold anything?
    try:
        conn = db_connect()
        try:
            n = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        finally:
            conn.close()
        checks["datasets"] = n
        if n == 0:
            ok = False
            checks["datasets_error"] = "index is empty"
    except sqlite3.Error as exc:
        ok = False
        checks["datasets_error"] = str(exc)[:120]

    # Are the vectors loaded and consistent with the index?
    try:
        matrix, keys = engine._vectors()
        checks["embedded"] = 0 if matrix is None else int(matrix.shape[0])
        if matrix is None or matrix.shape[0] != len(keys):
            ok = False
            checks["embeddings_error"] = "vectors missing or out of step with keys"
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks["embeddings_error"] = str(exc)[:120]

    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", **checks}


@app.get("/api/stats", summary="Index statistics")
def api_stats() -> dict:
    return engine.stats()


def _dataset_record(key: str) -> dict | None:
    """Everything we hold about one dataset, or None if we hold nothing.

    Shared by the JSON API and the server-rendered page so the two can never
    drift apart — the page used to be built by JavaScript from this same
    payload, and the whole point of rendering it here is that it stays the
    same page.
    """
    import json as _json
    import sqlite3
    from paths import connect as db_connect

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM datasets WHERE key = ?", (key,)).fetchone()
        if not row:
            return None

        try:
            resources = [dict(r) for r in conn.execute(
                "SELECT r.url, r.name, r.format_norm, c.status, c.content_type, "
                "       c.size_bytes, c.verdict, c.columns, c.checked_at "
                "FROM resources r LEFT JOIN resource_checks c ON c.url = r.url "
                "WHERE r.dataset_key = ?", (key,))]
        except sqlite3.OperationalError:
            resources = []
        for r in resources:
            r["columns"] = _json.loads(r["columns"]) if r.get("columns") else None

        related = [dict(r) for r in conn.execute(
            "SELECT key, title, source_id AS source, landing_url AS url "
            "FROM datasets WHERE publisher = ? AND key != ? "
            "ORDER BY modified DESC LIMIT 6",
            (row["publisher"], key))] if row["publisher"] else []

        avail = None
        try:
            avail = row["availability"]
        except (IndexError, KeyError):
            pass

        dup = conn.execute("SELECT canonical_key FROM duplicates WHERE key = ?",
                           (key,)).fetchone()
        retired = conn.execute("SELECT 1 FROM retired WHERE key = ?",
                               (key,)).fetchone() is not None

        return {
            "key": key,
            "title": row["title"],
            "publisher": row["publisher"],
            "source": row["source_id"],
            "license": row["license_norm"],
            "license_raw": row["license_raw"],
            "created": row["created"],
            "modified": row["modified"],
            "landing_url": row["landing_url"],
            "description": row["description"],
            "tags": _json.loads(row["tags"] or "[]"),
            "formats": _json.loads(row["formats_norm"] or "[]"),
            "availability": avail,
            # Why search may not return this record. Both are absent from
            # search results, so without saying so the API looks inconsistent
            # with itself.
            "duplicate_of": dup["canonical_key"] if dup else None,
            "retired": retired,
            "resources": resources,
            "related": related,
            "attribution": ATTRIBUTION,
        }
    finally:
        conn.close()


@app.get("/dataset", include_in_schema=False)
def dataset_page(key: str = Query(default="", max_length=500)) -> HTMLResponse:
    """The dataset page, rendered here rather than in the browser.

    Not rate-limited, unlike /api/dataset: this is three indexed SQLite reads
    with no model involved, and it's the page we *want* crawled — a limiter
    here would turn a search engine indexing us into a wall of 429s.
    """
    rec = _dataset_record(key) if key else None
    if rec is None:
        return HTMLResponse(pagerender.render_missing(key or None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    return HTMLResponse(
        pagerender.render_dataset(rec, SITE_URL),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


@app.get("/api/dataset",
         summary="Dataset detail",
         responses=RATE_LIMITED_RESPONSE,
         description="Full record for one dataset: metadata, every resource "
                     "with its verified availability, CSV column names where "
                     "peeked, and related datasets.\n\n"
                     "`duplicate_of` and `retired` explain why a record you "
                     "can fetch here may never appear in `/api/search`: "
                     "duplicates are collapsed onto the canonical copy whose "
                     "key is given, and records the publisher has withdrawn "
                     "are excluded.")
def api_dataset(request: Request, response: Response,
                key: str = Query(min_length=3, max_length=500)) -> dict:
    _rate_check(request, response)
    rec = _dataset_record(key)
    if rec is None:
        raise HTTPException(status_code=404, detail="Unknown dataset key")
    return rec


# --- Crawlers -----------------------------------------------------------
#
# The sitemap lists only the canonical, non-retired records — about 55,000 of
# the 65,000 we hold. Offering a crawler 9,500 duplicate pages and 900
# withdrawn ones spends its patience on pages we don't want ranked, and the
# whole point of the exercise is the pages we do.

SITEMAP_CHUNK = 25_000   # the sitemap spec caps a single file at 50,000 URLs

INDEXABLE = ("FROM datasets d WHERE "
             "NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) AND "
             "NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)")


def _indexable_count() -> int:
    from paths import connect as db_connect
    conn = db_connect()
    try:
        return conn.execute(f"SELECT COUNT(*) {INDEXABLE}").fetchone()[0]
    finally:
        conn.close()


@app.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    """Crawl the pages, not the search box.

    Every /api/search call runs a sentence transformer — half a second of CPU.
    A crawler that discovers query URLs will happily fetch thousands of them,
    so the API is disallowed while the dataset pages, which are cheap and are
    the actual content, are wide open.
    """
    body = ("User-agent: *\n"
            "Allow: /\n"
            "Disallow: /api/\n"
            "Disallow: /docs\n"
            "Disallow: /redoc\n"
            "Disallow: /openapi.json\n"
            f"\nSitemap: {SITE_URL}/sitemap.xml\n")
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_index() -> Response:
    pages = max(1, -(-_indexable_count() // SITEMAP_CHUNK))   # ceil
    entries = "".join(
        f"<sitemap><loc>{SITE_URL}/sitemap-{n}.xml</loc></sitemap>"
        for n in range(1, pages + 1))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"{entries}</sitemapindex>")
    return Response(xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sitemap-{page}.xml", include_in_schema=False)
def sitemap_page(page: int) -> Response:
    """One sitemap file, streamed straight off the cursor.

    25,000 URLs is roughly 3 MB of XML. Built as a list that would be 3 MB of
    process memory on every request; streamed, it's one row at a time, which
    matters for a service running under a hard memory cap.
    """
    import sqlite3

    from paths import connect as db_connect

    if page < 1:
        raise HTTPException(status_code=404, detail="No such sitemap page")

    def rows():
        yield ('<?xml version="1.0" encoding="UTF-8"?>'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        if page == 1:
            for path, freq in (("/", "daily"), ("/about", "weekly")):
                yield (f"<url><loc>{SITE_URL}{path}</loc>"
                       f"<changefreq>{freq}</changefreq></url>")
        conn = db_connect()
        try:
            cur = conn.execute(
                f"SELECT d.key, d.modified {INDEXABLE} ORDER BY d.key "
                "LIMIT ? OFFSET ?", (SITEMAP_CHUNK, (page - 1) * SITEMAP_CHUNK))
            for key, modified in cur:
                loc = SITE_URL + pagerender.dataset_path(key)
                # &key= is a literal ampersand; XML needs it escaped or the
                # file is rejected wholesale, not just that one URL.
                loc = loc.replace("&", "&amp;")
                stamp = str(modified or "")[:10]
                lastmod = (f"<lastmod>{stamp}</lastmod>"
                           if len(stamp) == 10 and stamp[4] == stamp[7] == "-" else "")
                yield f"<url><loc>{loc}</loc>{lastmod}</url>"
        except sqlite3.Error:
            pass          # a half-written sitemap beats a 500 mid-stream
        finally:
            conn.close()
        yield "</urlset>"

    return StreamingResponse(rows(), media_type="application/xml",
                             headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/sources", summary="Harvested sources")
def api_sources() -> dict:
    with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
        sources = yaml.safe_load(fh)["sources"]
    counts = engine.stats()["sources"]
    return {
        "sources": [
            {
                "id": s["id"],
                "name": s["name"],
                "type": s["type"],
                "web": s["web"],
                "datasets": counts.get(s["id"], 0),
            }
            for s in sources
        ],
        "attribution": ATTRIBUTION,
    }
