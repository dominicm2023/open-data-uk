# Performance and operational robustness audit — open-data.org.uk

Measured 2026-08-21 from a UK residential connection, 5 samples per route at 1 req/s,
User-Agent from agent.py. Local costs measured against the dev copy of index.db
(106,609 datasets; live reports 107,491 via /api/stats, so local timings slightly
understate live).

## Timing table (live, via Cloudflare)

TTFB = time to first byte on a fresh connection (includes DNS+TCP+TLS).
post-TLS = request-sent to first-byte, i.e. ~network RTT + server time.
All routes returned 200 on every sample.

| route | TTFB samples (ms) | median TTFB | median post-TLS | wire / raw KB | content-encoding | cf-cache-status |
|---|---|---|---|---|---|---|
| / | 104, 64, 83, 107, 74 | 83 | 38 | 4.0 / 9.1 | zstd | DYNAMIC |
| /about | 61, 74, 63, 81, 77 | 74 | 25 | 4.8 / 11.2 | zstd | DYNAMIC |
| /dataset?key=agol_the_rivers_trust:… | 65, 69, 88, 70, 72 | 70 | 28 | 1.9 / 5.1 | zstd | DYNAMIC |
| /publishers | 101, 92, 113, 133, 107 | 107 | 57 | 38.2 / 239.3 | zstd | DYNAMIC |
| /publisher?name=The%20Rivers%20Trust | 90, 80, 70, 100, 98 | 90 | 33 | 4.8 / 20.5 | zstd | DYNAMIC |
| /topics | 93, 90, 115, 116, 156 | 115 | 62 | 32.0 / 217.7 | zstd | DYNAMIC |
| /topic?tag=environment (largest tag, 8,433 rows) | 165, 148, 222, 125, 131 | 148 | 100 | 5.6 / 25.9 | zstd | DYNAMIC |
| /who-publishes | 98, 85, 103, 84, 100 | 98 | 43 | 28.4 / 192.5 | zstd | DYNAMIC |
| /findings | 69, 84, 68, 85, 70 | 70 | 31 | 5.8 / 37.9 | zstd | DYNAMIC |
| /api/search?q=flooding | 168, 150, 138, 145, 119 | 145 | 103 | 1.9 / 5.4 | gzip | DYNAMIC |
| /api/stats | 114, 113, 131, 84, 111 | 113 | 61 | 2.0 / 5.0 | gzip | DYNAMIC |
| /sitemap-1.xml | 119, 68, 99, 83, 70 | 83 | 29 | 1,010 / 3,457 | zstd | DYNAMIC |
| /sitemap.xml (follow-up, 3 samples) | 436, 420, 486 | 436 | — | 0.17 raw | zstd | DYNAMIC |
| /api/sources (follow-up, 3 samples) | 372, 831, 302 | 372 | — | 4.9 wire | gzip | DYNAMIC |

Transport facts: HTTP/2 negotiated via ALPN (h2, TLS 1.3), HTTP/3 advertised
(`alt-svc: h3=":443"`), keep-alive confirmed (second request in one session reused the
connection, "Connection #0 … left intact"). Compression is on for every text route —
zstd at the edge for HTML/XML, gzip for JSON; Caddy also has `encode gzip`
(DEPLOY.md:272) for the origin leg. `/site.css` carries ETag + Last-Modified, is
edge-cached (cf-cache-status MISS then HIT with Age), and is linked with a content-hash
query (pagerender.py:368–386). Warm TTFB is healthy everywhere: 70–150 ms.

## Ranked findings

### 1. `_aggregates()` recomputes a ~2.4 s full scan on the user path, every 30 min per worker, with no lock — the worst user-visible latency on the site
- Evidence: server.py:500–583 (`_AGG_TTL = 1800`, server.py:481; module-global
  `_agg_cache` checked and rebuilt inline). Measured locally: **cold 2,373 ms, cached
  0.018 ms** (106k-row dev DB; live is larger).
- The dataset page itself calls it — server.py:441 (`agg = _aggregates()` for the
  "also published by" cross-link) — as do /publishers (server.py:593), /topics
  (server.py:750), /who-publishes (server.py:821) and /sitemap-browse.xml
  (server.py:945).
- Expected user impact: after every TTL expiry, the first request into each of the 4
  workers stalls ~2.4 s — up to ~192 multi-second page loads/day, and any **dataset
  page** (the pages you want ranked; crawlers measure TTFB) can be the one that pays it.
  There is no lock: concurrent requests that arrive during the rebuild each run their
  own full scan in threadpool threads, multiplying the stall under exactly the load
  (a crawl burst) most likely to trigger it. Startup is warmed per worker
  (server.py:58–65), so only expiry pays.
- Note the asymmetry: findings are precomputed nightly to a file precisely because
  "these are expensive aggregate queries" (server.py:640), but _aggregates does the
  same class of work on-request. Computing it in refresh.sh to a file (or refreshing in
  a background thread / serving stale while one thread rebuilds) removes the spike;
  the dataset-page cross-link could also tolerate reading only a stale copy.

### 2. Cloudflare caches nothing but static assets — every carefully set Cache-Control header on HTML/XML is ignored at the edge
- Evidence: `cf-cache-status: DYNAMIC` on all 14 routes sampled above, including
  /dataset, /publisher, /findings (`public, max-age=3600, stale-while-revalidate=86400`,
  server.py:450, 630, 655) and the sitemaps (`public, max-age=21600`, server.py:935,
  1021). Only /site.css showed MISS→HIT. This is Cloudflare's default: HTML/XML/JSON
  are not cached without a Cache Rule.
- Expected user impact: today, mostly latency left on the table (every view is an
  origin round trip; an edge HIT would serve dataset pages in ~15–30 ms globally
  instead of 70–150 ms UK / worse overseas). Operationally it is the missing safety
  net for finding 1 and the multiplier for findings 3 and 4: the ~83k sitemap-listed
  pages and four ~1 MB-wire sitemap chunks are re-served by the VPS on **every**
  crawler fetch. One Cache Rule ("Eligible for cache, respect origin headers" on
  non-/api, non-/lab paths) turns the origin's already-correct headers on. The
  no-store on /lab and 404s (server.py:682, 439) already defends those routes.

### 3. /sitemap.xml pays a ~600 ms table scan per request — TTFB 420–486 ms, the slowest human-or-crawler-facing route measured
- Evidence: server.py:924–935 calls `_indexable_count()` (server.py:873–881), which
  runs the INDEXABLE + NOT NOTHING_TO_INDEX filter (two NOT EXISTS subqueries plus
  LENGTH/COALESCE checks) over the whole datasets table on every request. Measured
  locally: **602 ms**. Live TTFB: 436/420/486 ms vs ~70–90 ms for ordinary pages —
  for a 172-byte response whose only content is "how many chunk files exist".
- Expected user impact: no human sees it, but every search-engine crawl session starts
  here, and it burns ~0.5 s of a CPUWeight-capped core per fetch. The count only
  changes nightly; caching it with the same TTL as _aggregates (or deriving pages from
  a cached count) makes this a constant-time response. Edge caching (finding 2) hides
  it entirely.

### 4. /api/sources does ~400–800 ms of work per request — yaml.safe_load of a 117 KB file plus full-table stats scans — and is not rate-limited
- Evidence: server.py:1024–1041 — `yaml.safe_load` of sources.yaml **per request**
  (measured locally: **378 ms**, pure-Python loader, 199 sources) plus
  `engine.stats()` (search.py:481–504: COUNT(*), GROUP BY source_id, COUNT(DISTINCT
  publisher), COUNT duplicates; measured 111 ms cold / 33 ms warm). Live TTFB:
  372/831/302 ms. No `_rate_check` on this route, unlike /api/search
  (server.py:289 vs 1025); confirmed live — no X-RateLimit-* headers on the response.
  The result changes at most nightly.
- Expected user impact: API consumers see the slowest JSON endpoint on the site; and
  it is the cheapest unauthenticated way to make the origin burn CPU — ~0.5 s per hit,
  no limiter, no edge cache. Same shape, smaller, for /api/stats (server.py:349–351:
  no rate check, no Cache-Control, recomputes scans; 113 ms live median). Both are
  one lru_cache-with-TTL (or a per-request-loop `functools` cache keyed on file mtime)
  away from ~1 ms. pagerender already caches the same YAML correctly
  (pagerender.py:70–75).

### 5. / and /about are `no-cache` with no validators — the most-visited page re-downloads in full on every visit
- Evidence: server.py:176, 182 (`Cache-Control: no-cache`); live response carries no
  ETag or Last-Modified (header capture, hdr_home.txt), so the mandated revalidation
  is always a full 4 KB transfer + origin round trip. The page body is a memory-cached
  static file (server.py:166–170) whose stylesheet link is already content-hash-busted
  (pagerender.py:384) — the usual reason for no-cache on HTML doesn't apply strongly.
- Expected user impact: small per-visit (~80 ms + 4 KB), but it is the front door and
  the highest-traffic route; even `max-age=300` or an ETag would remove most repeat
  fetches. Lowest severity of the five; listed because it is the one place the
  otherwise-thoughtful per-route cache design defaults to the most expensive option.

## Operational risks (not yet user-visible)

### 6. Memory: 4 private copies of a growing embedding matrix, doubled transiently on hot-reload, under MemoryMax=3G
- Evidence: search.py:97 `np.load(EMB_PATH)` — no `mmap_mode`, so each of the 4
  workers holds a private matrix. Live embedded count 107,508 × 384 × f32 =
  **158 MB per worker, ~630 MB total** (the local file is already 100 MB at 65k rows).
  DEPLOY.md:182–190: ~1.9 GB steady cgroup, MemoryMax=3G. Hot-reload
  (search.py:95–103) loads the new matrix before dropping the old — a per-worker
  transient of 2×, and all 4 workers reload on their first search after the nightly
  checkpoint lands.
- Expected impact: fine today; the growth path is the risk. At ~150–160k embedded
  datasets, steady state ≈ 2.3–2.4 GB and the reload transient approaches 3 G —
  an OOM kill mid-refresh, i.e. during the nightly window, restart-looping under
  systemd. `np.load(..., mmap_mode="r")` makes the matrix shared page cache across
  all workers (the file is rewritten, not mutated, so the mtime-swap logic still
  works), removing ~470 MB now and flattening the growth curve.

### 7. Small per-request costs on the search path — acceptable, listed for completeness
- Warm /api/search origin time ≈ 90–100 ms (145 ms TTFB − ~50 ms network), far better
  than the "half a second" the robots.txt comment assumes (server.py:888).
  Contributors per query: model encode (~12 ms, 1 torch thread — search.py:80–87),
  `_topic_match_keys` fetching up to 20,000 keys into a Python set (search.py:198–212),
  per-term FTS COUNTs in `_rare_term_keys` (search.py:138–164), a per-result
  `SELECT * FROM datasets` loop of up to k=50 point lookups (search.py:410–413), and a
  synchronous SQLite open+INSERT+commit into queries.db per search
  (querylog.py:49–82, swallowed on failure). None is broken; the 20k-key fetch is the
  first thing to revisit if search latency ever matters.
- `_dup_and_retired` is correctly cached against DB mtime (search.py:278–300) — the
  known past hotspot is fixed.

## Explicitly checked, nothing wrong

- **Compression**: on for every text route (zstd for HTML/XML, gzip for JSON at the
  edge; Caddy `encode gzip` origin-side). No uncompressed text response observed.
- **Findings-page weight**: the inline-SVG concern is unfounded — 37.9 KB raw,
  5.8 KB on the wire, and render_findings costs 5.1 ms cold / 1.6 ms warm locally
  (charts are string-built, no image rasterising). Reading findings.json (21.8 KB)
  per request is negligible.
- **HTTP/2 + HTTP/3 + keep-alive**: h2 negotiated (ALPN, TLS 1.3), h3 advertised,
  connection reuse confirmed.
- **Static asset caching**: correct and complete — long max-age + SWR
  (server.py:204–212), ETag/Last-Modified from FileResponse, edge HIT confirmed,
  content-hash cache-busting for the stylesheet.
- **Payload sizes**: dataset page 5.1 KB raw; hub pages 190–240 KB raw compress 6–8×
  to 28–38 KB wire — fine. Sitemap chunks stream (TTFB 83 ms on a 3.5 MB file), and
  the 20 Aug threading fix holds: 5/5 clean 200s at full length.
- **/lab pages read from disk per request** (server.py:673–744; gallery.html is
  1.1 MB): true, and fine — auth-gated at Caddy, near-zero traffic, and no-store is
  deliberate. Not worth caching.
- **Rate limiter hygiene**: per-IP buckets pruned once per window (server.py:113–126),
  headers count the current request honestly, per-process budget disclosed in the API
  docs (server.py:222–237). /health does real work by design and costs ~10 ms.
- **Startup**: lifespan warms model, index and aggregates per worker and never blocks
  boot on failure (server.py:49–66) — restart behaviour is sound.
