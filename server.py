"""Web UI + JSON API for the UK Open Data Index.

    uvicorn server:app --port 8000

Holds one warm SearchEngine so queries are fast; hot-reloads vectors as
embed_index.py checkpoints land. Public API: /api/search, /api/stats,
/api/sources — interactive docs at /docs.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from querylog import log_query
from search import SearchEngine

ROOT = Path(__file__).parent
REPO_URL = "https://github.com/dominicm2023/open-data-uk"
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
    # Load the model and vectors before the first request hits
    engine.model
    engine.stats()
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
            "discover the limit by hitting it."),
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


@app.get("/api/stats", summary="Index statistics")
def api_stats() -> dict:
    return engine.stats()


@app.get("/dataset", include_in_schema=False)
def dataset_page() -> FileResponse:
    return FileResponse(ROOT / "web" / "dataset.html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/dataset",
         summary="Dataset detail",
         responses=RATE_LIMITED_RESPONSE,
         description="Full record for one dataset: metadata, every resource "
                     "with its verified availability, CSV column names where "
                     "peeked, and related datasets.")
def api_dataset(request: Request, response: Response,
                key: str = Query(min_length=3, max_length=500)) -> dict:
    import json as _json
    import sqlite3
    from paths import connect as db_connect

    _rate_check(request, response)   # opens a DB connection per call
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM datasets WHERE key = ?", (key,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Unknown dataset key")

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
            "resources": resources,
            "related": related,
            "attribution": ATTRIBUTION,
        }
    finally:
        conn.close()


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
