"""Web UI + JSON API for the UK Open Data Index.

    uvicorn server:app --port 8000

Holds one warm SearchEngine so queries are fast; hot-reloads vectors as
embed_index.py checkpoints land. Public API: /api/search, /api/stats,
/api/sources — interactive docs at /docs.
"""

from __future__ import annotations

import functools
import os
import re
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
                     ("index", engine.stats),
                     ("browse aggregates", _aggregates)):
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


@functools.lru_cache(maxsize=4)
def _hand_written_page(name: str) -> str:
    """A static page, with the stylesheet URL stamped with its content hash."""
    return pagerender.with_assets(
        (ROOT / "web" / name).read_text(encoding="utf-8"))


@app.get("/", include_in_schema=False)
def home() -> HTMLResponse:
    return HTMLResponse(_hand_written_page("index.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/about", include_in_schema=False)
def about() -> HTMLResponse:
    return HTMLResponse(_hand_written_page("about.html"),
                        headers={"Cache-Control": "no-cache"})


# Static assets: one stylesheet and the icons, all immutable in practice.
# Named individually rather than mounting web/ as a static directory — that
# would also expose the HTML templates, and a request for /dataset.html
# would serve the raw file with its placeholders unfilled.
STATIC_FILES = {
    "site.css": "text/css; charset=utf-8",
    "favicon.svg": "image/svg+xml",
    "favicon.ico": "image/x-icon",
    "apple-touch-icon.png": "image/png",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "manifest.webmanifest": "application/manifest+json",
    # IndexNow ownership proof. Public by design — search engines fetch it
    # back from the site root to confirm the submissions are really ours,
    # so it belongs in the repo rather than in a secret.
    "ed89a51325644371a1b02829527a3cdf.txt": "text/plain; charset=utf-8",
}


def _static(name: str) -> FileResponse:
    # Safe to cache hard: the stylesheet is linked with a content hash in its
    # URL (pagerender.asset_version), so the address changes whenever the
    # bytes do and a stale copy can never be served for the current page.
    ttl = 86400
    return FileResponse(
        ROOT / "web" / name, media_type=STATIC_FILES[name],
        headers={"Cache-Control":
                 f"public, max-age={ttl}, stale-while-revalidate=604800"})


for _name in STATIC_FILES:
    # HEAD as well as GET: caches and link-preview fetchers ask for headers
    # before bodies, and a 405 on the favicon reads as a broken asset.
    app.add_api_route(f"/{_name}", (lambda n=_name: (lambda: _static(n)))(),
                      methods=["GET", "HEAD"], include_in_schema=False)


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
                                               "(max 200)"),
               availability: str = Query(
                   default="", max_length=120,
                   description="Keep only these link verdicts, comma-separated: "
                               "`data` (we fetched it and it is a data file), "
                               "`api`, `webpage`, `dead`, `blocked` (the "
                               "publisher refused our checker), `nofiles`, "
                               "`unchecked`. `availability=data,api` is the "
                               "useful one: only things you can actually load."),
               format: str = Query(
                   default="", max_length=120,
                   description="Keep only datasets offering one of these "
                               "formats, comma-separated and normalised — "
                               "`CSV`, `XLSX`, `GEOJSON`, `SHP`, `JSON`, `WMS`…"),
               license: str = Query(
                   default="", max_length=200,
                   description="Keep only these licences, comma-separated, as "
                               "returned in the `license` field — e.g. "
                               "`OGL-UK-3.0`. Use `none` for the third of the "
                               "catalogue that states no licence at all."),
               source: str = Query(
                   default="", max_length=200,
                   description="Keep only these portals, comma-separated, by "
                               "the `id` from /api/sources — e.g. "
                               "`data_gov_uk,london_datastore`.")) -> dict:
    _rate_check(request, response)

    # Filters are AND between fields, OR within one. Values are lower-cased
    # here so the caller need not care about case anywhere.
    filters = {name: {v.strip().lower() for v in raw.split(",") if v.strip()}
               for name, raw in (("availability", availability), ("format", format),
                                 ("license", license), ("source", source))
               if raw.strip()}
    payload = engine.search(q, k, offset=offset, filters=filters or None)
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
    try:
        agg = _aggregates()
        slug = _norm_title(rec.get("title") or "")
        if count := agg["shared_index"].get(slug):
            rec["also_published"] = {"title": agg["shared_label"][slug],
                                     "count": count}
    except Exception:  # noqa: BLE001 - a cross-link is never worth a 500
        pass
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


# --- Browse -------------------------------------------------------------
#
# Dataset pages had nothing linking to them: the only route in was the search
# box, which calls an API we ask crawlers not to touch, so all 60,000 sat in
# the sitemap as orphans. These two pages are the front door — and the browse
# mode the search box can't offer.

PER_PAGE = 100
_AGG_TTL = 1800          # the index only changes on the nightly refresh
_agg_cache: tuple[float, dict] = (0.0, {})

# A subject earns a page when more than one organisation publishes on it and
# there is a list worth reading. Below that it's one publisher's private
# vocabulary, and a page per stray tag is how you manufacture thin content.
TOPIC_MIN_DATASETS = 5
TOPIC_MIN_PUBLISHERS = 2
# Same idea for "who publishes this": two councils sharing a title is a
# coincidence, three is a pattern.
WHO_MIN_PUBLISHERS = 3

_NORM = re.compile(r"[^a-z0-9]+")


def _norm_title(text: str) -> str:
    return _NORM.sub(" ", (text or "").lower()).strip()


def _aggregates() -> dict:
    """Publishers, subjects and shared dataset types — one scan, cached.

    Each of these needs the whole findable set, and doing them separately
    meant three full scans. One pass takes ~2 s and is held for half an hour
    per worker; the result is a few hundred KB against a model that is
    already resident.
    """
    global _agg_cache
    import json as _json
    from collections import Counter, defaultdict

    from paths import connect as db_connect

    now = time.time()
    stamp, cached = _agg_cache
    if cached and now - stamp < _AGG_TTL:
        return cached

    conn = db_connect()
    try:
        rows = conn.execute(
            f"SELECT d.key, d.title, d.publisher, d.tags {INDEXABLE}").fetchall()
    finally:
        conn.close()

    pubs: Counter = Counter()
    tag_n: Counter = Counter()
    tag_pubs: defaultdict = defaultdict(set)
    title_pubs: defaultdict = defaultdict(set)

    for _key, title, publisher, tags in rows:
        if publisher and publisher.strip():
            pubs[publisher] += 1
        for raw in _json.loads(tags or "[]"):
            tag = " ".join(str(raw).lower().split())
            if tag and len(tag) > 1:
                tag_n[tag] += 1
                if publisher:
                    tag_pubs[tag].add(publisher)
        if title and publisher:
            slug = _norm_title(title)
            if len(slug) > 3:
                title_pubs[slug].add(publisher)

    topics = sorted(
        ((t, n, len(tag_pubs[t])) for t, n in tag_n.items()
         if n >= TOPIC_MIN_DATASETS and len(tag_pubs[t]) >= TOPIC_MIN_PUBLISHERS),
        key=lambda r: r[0])
    shared_slugs = {s for s, p in title_pubs.items() if len(p) >= WHO_MIN_PUBLISHERS}
    # Pick the label readers should see. The normalised slug is lower-case and
    # stripped of punctuation, and taking whichever spelling happened to come
    # first gave "Conservation_Areas" — one publisher's underscore standing in
    # for the 84 who wrote it normally. Take the commonest form instead, and
    # only for the few hundred titles that need one.
    forms: defaultdict = defaultdict(Counter)
    for _key, title, publisher, _tags in rows:
        if title and publisher:
            slug = _norm_title(title)
            if slug in shared_slugs:
                forms[slug][" ".join(title.split())] += 1
    title_label = {s: forms[s].most_common(1)[0][0] for s in shared_slugs if forms[s]}
    shared = sorted(((title_label[s], len(title_pubs[s]))
                     for s in shared_slugs if s in title_label),
                    key=lambda r: (-r[1], r[0].lower()))
    # Only ~3,000 of the 60,000 rows belong to a shared title, so holding
    # their keys costs little and turns the page into indexed lookups.
    shared_keys: defaultdict = defaultdict(list)
    for key, title, publisher, _tags in rows:
        if title and publisher:
            slug = _norm_title(title)
            if slug in shared_slugs:
                shared_keys[slug].append(key)

    _agg_cache = (now, {
        "publishers": sorted(pubs.items(), key=lambda r: r[0].lower()),
        "topics": topics,
        "topic_index": {t: (n, p) for t, n, p in topics},
        "shared": shared,
        "shared_index": {_norm_title(t): n for t, n in shared},
        "shared_label": {_norm_title(t): t for t, n in shared},
        "shared_keys": dict(shared_keys),
    })
    return _agg_cache[1]


def _publishers() -> list[tuple[str, int]]:
    return _aggregates()["publishers"]


@app.get("/publishers", include_in_schema=False)
def publishers_page() -> HTMLResponse:
    return HTMLResponse(
        pagerender.render_publishers(_publishers(), SITE_URL),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


@app.get("/publisher", include_in_schema=False)
def publisher_page(name: str = Query(default="", max_length=300),
                   page: int = Query(default=1, ge=1, le=1000)) -> HTMLResponse:
    import sqlite3

    from paths import connect as db_connect

    if not name:
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute(
            f"SELECT COUNT(*) {INDEXABLE} AND d.publisher = ?", (name,)).fetchone()[0]
        if not total:
            return HTMLResponse(pagerender.render_missing(None), status_code=404,
                                headers={"Cache-Control": "no-store"})
        pages = max(1, -(-total // PER_PAGE))
        if page > pages:
            return HTMLResponse(pagerender.render_missing(None), status_code=404,
                                headers={"Cache-Control": "no-store"})
        rows = [dict(r) for r in conn.execute(
            f"SELECT d.key, d.title, d.modified, d.availability {INDEXABLE} "
            "AND d.publisher = ? ORDER BY d.modified DESC, d.key "
            "LIMIT ? OFFSET ?", (name, PER_PAGE, (page - 1) * PER_PAGE))]
    finally:
        conn.close()

    return HTMLResponse(
        pagerender.render_publisher(name, rows, page, pages, total, SITE_URL,
                                    per_page=PER_PAGE),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


@app.get("/findings", include_in_schema=False)
def findings_page() -> HTMLResponse:
    """Findings, read from the file the nightly run writes.

    Deliberately not computed per request: these are expensive aggregate
    queries, and a page that recomputed them would let a crawler run a table
    scan on demand. The file is the published record — if it is missing, say
    so rather than inventing an empty page that reads as "we found nothing".
    """
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    path = Path(__file__).parent / "findings.json"
    if not path.exists():
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    findings = json.loads(path.read_text(encoding="utf-8"))
    measured = datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc).strftime("%d %B %Y")
    return HTMLResponse(
        pagerender.render_findings(findings, measured, SITE_URL),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


@app.get("/lab", include_in_schema=False)
def lab_page() -> HTMLResponse:
    """The private workshop. Auth is Caddy's job, not this function's.

    Deliberately no password check here. Putting one in application code
    means every future route under /lab has to remember it, and forgetting
    once publishes the unreviewed queue. Caddy gates the path prefix, so a
    route added here is behind the door by default rather than by discipline.
    Sending no-store as well: this page holds claims we have decided are not
    fit to publish, and a shared cache should not keep a copy.
    """
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    path = Path(__file__).parent / "findings.json"
    if not path.exists():
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    findings = json.loads(path.read_text(encoding="utf-8"))
    measured = datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc).strftime("%d %B %Y")
    return HTMLResponse(
        pagerender.render_lab(findings, measured, SITE_URL),
        headers={"Cache-Control": "no-store, private",
                 "X-Robots-Tag": "noindex, nofollow, noarchive"})


@app.get("/lab/posters", include_in_schema=False)
def lab_posters() -> HTMLResponse:
    """The reviewed findings at poster scale. Under /lab, so private by default."""
    from pathlib import Path

    path = Path(__file__).parent / "posters.html"
    if not path.exists():
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    return HTMLResponse(path.read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store, private",
                                 "X-Robots-Tag": "noindex, nofollow"})


@app.get("/lab/gallery", include_in_schema=False)
def lab_gallery() -> HTMLResponse:
    """The drawn index, behind the same gate as the rest of the workshop.

    Under /lab deliberately, which is the point of gating a path prefix
    rather than a handler: this route inherited its privacy without having
    to remember to ask for it.
    """
    from pathlib import Path

    path = Path(__file__).parent / "gallery.html"
    if not path.exists():
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    return HTMLResponse(path.read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store, private",
                                 "X-Robots-Tag": "noindex, nofollow"})


@app.get("/topics", include_in_schema=False)
def topics_page() -> HTMLResponse:
    return HTMLResponse(
        pagerender.render_topics(_aggregates()["topics"], SITE_URL),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


@app.get("/topic", include_in_schema=False)
def topic_page(tag: str = Query(default="", max_length=200),
               page: int = Query(default=1, ge=1, le=1000)) -> HTMLResponse:
    import json as _json
    import sqlite3

    from paths import connect as db_connect

    tag = " ".join(tag.lower().split())
    if not tag:
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})

    # Driven from dataset_tags, which dedupe.py flattens out of the JSON
    # array and indexes. Counting and paging separately means a page shows
    # 100 rows without building the other 6,400 as Python objects: 200ms to
    # under 1ms for a typical subject.
    FILTER = ("FROM dataset_tags dt JOIN datasets d ON d.key = dt.dataset_key "
              "WHERE dt.tag = ? "
              "AND NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) "
              "AND NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)")
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        try:
            total, publishers = conn.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT d.publisher) {FILTER}",
                (tag,)).fetchone()
            window = [dict(r) for r in conn.execute(
                "SELECT d.key, d.title, d.publisher, d.modified, d.availability "
                f"{FILTER} ORDER BY d.modified DESC, d.key LIMIT ? OFFSET ?",
                (tag, PER_PAGE, (page - 1) * PER_PAGE))]
        except sqlite3.OperationalError:
            # dataset_tags is built by dedupe.py. On an index that predates
            # it, fall back to the scan rather than 500 — a slow page beats a
            # broken one, and the nightly refresh will build the table.
            matches = [dict(r) for r in conn.execute(
                f"SELECT d.key, d.title, d.publisher, d.modified, d.availability, "
                f"d.tags {INDEXABLE} AND LOWER(d.tags) LIKE ? "
                "ORDER BY d.modified DESC, d.key", (f"%{tag}%",))
                if any(" ".join(str(t).lower().split()) == tag
                       for t in _json.loads(r["tags"] or "[]"))]
            total = len(matches)
            publishers = len({m["publisher"] for m in matches if m["publisher"]})
            window = matches[(page - 1) * PER_PAGE: page * PER_PAGE]
    finally:
        conn.close()

    pages = max(1, -(-total // PER_PAGE))
    if not total or page > pages:
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    return HTMLResponse(
        pagerender.render_topic(
            tag, window, page, pages, total, publishers, SITE_URL,
            per_page=PER_PAGE,
            indexable=(total >= TOPIC_MIN_DATASETS
                       and publishers >= TOPIC_MIN_PUBLISHERS)),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


@app.get("/who-publishes", include_in_schema=False)
def who_publishes(name: str = Query(default="", max_length=300)) -> HTMLResponse:
    import sqlite3

    from paths import connect as db_connect

    agg = _aggregates()
    if not name:
        return HTMLResponse(
            pagerender.render_who_index(agg["shared"], SITE_URL),
            headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})

    slug = _norm_title(name)
    if slug not in agg["shared_index"]:
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})

    keys = agg["shared_keys"].get(slug, [])
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(keys))
        rows = [dict(r) for r in conn.execute(
            "SELECT key, title, publisher, modified, availability FROM datasets "
            f"WHERE key IN ({placeholders})", keys)] if keys else []
    finally:
        conn.close()

    if not rows:
        return HTMLResponse(pagerender.render_missing(None), status_code=404,
                            headers={"Cache-Control": "no-store"})
    return HTMLResponse(
        pagerender.render_who(name, rows, SITE_URL),
        headers={"Cache-Control": "public, max-age=3600, stale-while-revalidate=86400"})


# --- Crawlers -----------------------------------------------------------
#
# The sitemap lists only the canonical, non-retired records — about 55,000 of
# the 65,000 we hold. Offering a crawler 9,500 duplicate pages and 900
# withdrawn ones spends its patience on pages we don't want ranked, and the
# whole point of the exercise is the pages we do.

SITEMAP_CHUNK = 25_000   # the sitemap spec caps a single file at 50,000 URLs

# Records with no text, no files, no tags and no formats. They stay
# reachable and crawlable, they are just not put forward for indexing —
# see pagerender.is_thin() for the reasoning.
NOTHING_TO_INDEX = ("LENGTH(TRIM(COALESCE(d.description,''))) < 40 "
                    "AND COALESCE(d.resource_count,0) = 0 "
                    "AND COALESCE(d.tags,'[]') IN ('[]','') "
                    "AND COALESCE(d.formats_norm,'[]') IN ('[]','')")

INDEXABLE = ("FROM datasets d WHERE "
             "NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) AND "
             "NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)")


def _indexable_count() -> int:
    from paths import connect as db_connect
    conn = db_connect()
    try:
        return conn.execute(
            f"SELECT COUNT(*) {INDEXABLE} AND NOT ({NOTHING_TO_INDEX})"
        ).fetchone()[0]
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
    body = (
        "# This index exists to make UK open government data findable, by\n"
        "# people and by the AI tools they ask. Assistants that read these\n"
        "# pages and cite the publisher are doing exactly what it is for.\n"
        "#\n"
        "# Content signals (contentsignals.org):\n"
        "#   search   = yes  build a search index over these pages\n"
        "#   ai-input = yes  read them live to answer someone's question\n"
        "#   ai-train = no   do not train or fine-tune models on them\n"
        "#\n"
        "# THE ai-train RESERVATION IS AN EXPRESS RESERVATION OF RIGHTS UNDER\n"
        "# ARTICLE 4 OF EU DIRECTIVE 2019/790. It covers our own work — the\n"
        "# collation, normalisation and link verification. The underlying\n"
        "# dataset metadata belongs to its publishers under their own\n"
        "# licences, most commonly the Open Government Licence v3.0.\n"
        "\n"
        "User-agent: *\n"
        "Content-Signal: search=yes, ai-input=yes, ai-train=no\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        # Behind HTTP auth anyway; listed so a crawler doesn't spend requests
        # collecting 401s, and so the exclusion survives if auth is ever
        # loosened for a while.
        "Disallow: /lab\n"
        "Disallow: /docs\n"
        "Disallow: /redoc\n"
        "Disallow: /openapi.json\n"
        f"\nSitemap: {SITE_URL}/sitemap.xml\n")
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_index() -> Response:
    pages = max(1, -(-_indexable_count() // SITEMAP_CHUNK))   # ceil
    entries = f"<sitemap><loc>{SITE_URL}/sitemap-browse.xml</loc></sitemap>"
    entries += "".join(
        f"<sitemap><loc>{SITE_URL}/sitemap-{n}.xml</loc></sitemap>"
        for n in range(1, pages + 1))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"{entries}</sitemapindex>")
    return Response(xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=21600"})


@app.get("/sitemap-browse.xml", include_in_schema=False)
def sitemap_browse() -> Response:
    """The browse hierarchy: the publisher index and every publisher page.

    Declared before /sitemap-{page}.xml, which takes an int — route order is
    what stops "browse" being tried as a page number.
    """
    agg = _aggregates()
    urls = [f"<url><loc>{SITE_URL}/{p}</loc><changefreq>weekly</changefreq></url>"
            for p in ("publishers", "topics", "who-publishes")]
    # Findings change every night the numbers move, unlike the browse hubs.
    urls.append(f"<url><loc>{SITE_URL}/findings</loc>"
                f"<changefreq>daily</changefreq></url>")
    for name, count in agg["publishers"]:
        for page in range(1, max(1, -(-count // PER_PAGE)) + 1):
            loc = (SITE_URL + pagerender.publisher_path(name, page)).replace("&", "&amp;")
            urls.append(f"<url><loc>{loc}</loc></url>")
    for tag, n, _pubs in agg["topics"]:
        for page in range(1, max(1, -(-n // PER_PAGE)) + 1):
            loc = (SITE_URL + pagerender.topic_path(tag, page)).replace("&", "&amp;")
            urls.append(f"<url><loc>{loc}</loc></url>")
    for title, _n in agg["shared"]:
        loc = (SITE_URL + pagerender.who_path(title)).replace("&", "&amp;")
        urls.append(f"<url><loc>{loc}</loc></url>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f'{"".join(urls)}</urlset>')
    return Response(xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=21600"})


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
                f"SELECT d.key, d.modified {INDEXABLE} AND NOT ({NOTHING_TO_INDEX}) "
                "ORDER BY d.key LIMIT ? OFFSET ?",
                (SITEMAP_CHUNK, (page - 1) * SITEMAP_CHUNK))
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
                             headers={"Cache-Control": "public, max-age=21600"})


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
