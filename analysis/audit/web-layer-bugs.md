# Web-layer adversarial review — server.py, pagerender.py

Scope: bugs in the web layer, local only. Escaping, cache headers, error
paths, the rate limiter, pagination, streaming, lru_cache staleness, route
shadowing, and concurrency across uvicorn workers. All findings reproduced
locally against `index.db` and the real render functions.

Ranked by user impact.

---

## 1. HIGH — Rate-limiter prune crashes under concurrent load → intermittent 500s on /api/search and /api/dataset

**server.py:125** (`_prune_hits`), reached from **server.py:138** (`_rate_check`).

FastAPI runs synchronous `def` routes in a threadpool, so several requests
execute `_rate_check` on different OS threads at once within one worker. Once
per `RATE_WINDOW` (60 s) a request runs `_prune_hits`, whose body is:

```python
for ip in [ip for ip, dq in _hits.items() if not dq or dq[-1] < cutoff]:
    del _hits[ip]
```

The list comprehension iterates `_hits` while another thread's `dq = _hits[ip]`
(server.py:139, a `defaultdict` access) inserts a new key. That raises
`RuntimeError: dictionary changed size during iteration`, which propagates out
of `_rate_check` as an unhandled 500 to whichever client happened to trip the
prune.

Reproduction (12 threads, mixed IPs, prune forced to run often — mirrors the
threadpool):

```
$ python - <<'PY'
import threading, random, server as s
s._hits.clear(); s._last_prune = 0.0; errs=[]
s._client_ip = lambda r: r._ip
class Rq:  __init__=lambda self,ip:setattr(self,'_ip',ip)
class Rs:  headers={}
def w():
    for _ in range(4000):
        ip=f"10.0.{random.randint(0,255)}.{random.randint(0,255)}"
        try: s._rate_check(Rq(ip), Rs())
        except s.HTTPException: pass
        if random.random()<0.01: s._last_prune=0.0
    ...
PY
   RuntimeError: dictionary changed size during iteration   (10 hits in 0.5s)
```

Impact: under real 4-worker production with concurrent traffic and a churn of
new client IPs, this fires intermittently — roughly when the once-a-minute
prune coincides with a concurrent first-request from a new IP — and returns a
500 to a random visitor instead of degrading. It is exactly the "500 instead
of degrade" / "breaks under concurrent workers on shared state" class the axis
targets. `_last_prune` is also read-then-written without a lock (server.py:120-123),
so two threads can both enter the body, widening the window. Fix is a snapshot:
iterate `list(_hits.items())`.

---

## 2. MEDIUM — HEAD returns 405 on every HTML page and crawler route

Only the static-asset routes register HEAD (server.py:218-219, `methods=["GET","HEAD"]`).
Every `@app.get` page route is GET-only, so HEAD gets a 405:

```
HEAD /                -> 405   (allow: GET)
HEAD /about           -> 405
HEAD /dataset?key=x   -> 405
HEAD /robots.txt      -> 405
HEAD /sitemap.xml     -> 405
HEAD /publishers      -> 405
HEAD /api/search?q=…  -> 405
HEAD /favicon.svg     -> 200   (the only routes that got HEAD)
```

(reproduced via `starlette.testclient`).

The author already knew this mattered — server.py:216-217 says, of the static
files, "caches and link-preview fetchers ask for headers before bodies, and a
405 on the favicon reads as a broken asset." That reasoning was applied only to
the icons, not to the dataset pages. Yet the entire point of `pagerender.py`
(its module docstring) is to serve `og:`/`twitter:` preview cards and crawlable
HTML. Link-preview bots and HTTP cache/CDN revalidators that issue HEAD-before-GET
get a 405 on precisely those pages, which reads as broken and can suppress the
preview card the SSR rewrite exists to produce. Monitoring tools that HEAD `/`
or `/health`'s neighbours see the same.

Caveat, stated honestly: Cloudflare in front may answer HEAD from an
already-cached GET for the cacheable pages, and Slackbot in particular uses GET,
so real-world exposure is partial rather than total. Still a gap on every page,
and the fix (add `HEAD` to the page routes) is what the code already does for
icons.

---

## 3. MEDIUM — /api/sources re-parses 117 KB of YAML per request; /api/sources and /api/stats are neither cached nor rate-limited

**server.py:1024-1027** (`api_sources`):

```python
with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
    sources = yaml.safe_load(fh)["sources"]
counts = engine.stats()["sources"]
```

`sources.yaml` is 117 KB / 199 sources and is parsed on **every** request:

```
sources.yaml parse: 249 ms per request      (measured, 5-run mean)
engine.stats():      ~90 ms                  (4 COUNT/GROUP BY over 106k rows)
```

So ~340 ms of CPU per hit — and `api_sources` calls neither `_rate_check` nor
sets any `Cache-Control`, unlike `/api/search` and `/api/dataset`. `pagerender.source_names()`
already lru-caches this same file (pagerender.py:70), but `api_sources` reads it
raw. `/api/stats` (server.py:349-351) is likewise unrate-limited and uncached
(~90 ms of aggregate queries per call). robots.txt disallows `/api/`, but that
is advisory: any client hitting `/api/sources` in a loop burns a
disproportionate slice of a deliberately small free host. Cache the parse
(module-level or `lru_cache`) and/or add `Cache-Control`.

---

## 4. LOW — Rate-limit client-IP resolution: forgeable leftmost XFF, and v4-mapped loopback not recognised

**server.py:103-110** (`_client_ip`). Two edge cases, both low because the
production topology masks them:

- `x-forwarded-for: spoofed, 198.51.100.7` resolves to `"spoofed"` (leftmost
  token, server.py:109) — client-controllable. But this branch is only reached
  when `cf-connecting-ip` is **absent** and the peer is loopback. Through
  Cloudflare, `cf-connecting-ip` is always set and cannot be forged by the
  client, so in the real chain the XFF branch is dead. Not exploitable as
  deployed; worth hardening only if CF is ever removed.
- `::ffff:127.0.0.1` (IPv4-mapped loopback) is **not** in the
  `("127.0.0.1", "::1")` allow-list (server.py:103), so it falls through to
  `return peer`. If Caddy ever connects to uvicorn over a v4-mapped socket,
  every visitor collapses into one shared bucket and the limiter throttles the
  whole world together. Currently Caddy→uvicorn is plain `127.0.0.1`, so this
  is latent, not live.

Verified:

```
'127.0.0.1' cf-connecting-ip=203.0.113.9      -> '203.0.113.9'      (correct)
'127.0.0.1' xff='spoofed, 198.51.100.7'       -> 'spoofed'          (forgeable)
'::ffff:127.0.0.1' cf-connecting-ip=203.0.113.9 -> '::ffff:127.0.0.1' (not trusted)
'203.0.113.50' cf-connecting-ip=1.2.3.4       -> '203.0.113.50'     (correct: direct peer wins)
```

---

## 5. LOW — /lab render_lab 500s on an empty or out-of-range findings file

**pagerender.py:776** `hero = next((…), findings[0])` raises `IndexError` if
`findings.json` is `[]`; **pagerender.py:811** `note[tier]` raises `KeyError` if
any finding carries a `tier` outside 1-5. Reproduced:

```
render_lab([])             -> IndexError: list index out of range
render_lab([{tier:9,…}])   -> KeyError: 9
```

`/lab` is auth-gated (out of the axis' main scope) and fed by our own nightly
`findings.json`, which today holds tiers 1-5 and is non-empty, so this is only
reachable by an operator with a malformed file — hence LOW. Still a hard 500
where the public routes (`/findings`) degrade to `render_missing`.

---

## Checked and clean (useful negatives)

- **Escaping is solid.** A record with `</script>` in the title, `"><img
  onerror=>` in the publisher, `javascript:`/`ftp:`/`https:no-slash` resource
  URLs, `<script>` tags and `a"b` in tags/columns, and a `<!--BODY-->` string
  in the description all render fully escaped through `render_dataset`,
  `render_missing`, `render_who`, `render_topic`. No injected `<script>`
  survived. `esc()` uses `quote=True` (pagerender.py:59-61); `safe_url` rejects
  non-http(s) schemes to `#` (pagerender.py:64-67).
- **JSON-LD is safe.** `json_ld` `.replace("<", "\\u003c")` (pagerender.py:201)
  neutralises `</script>` breakouts; the emitted block contained no `</` and
  parsed as valid JSON on the hostile record.
- **charts.py SVG** (public via `/findings`) escapes every publisher-derived
  string it interpolates — `esc()` on headline, detail, labels, hosts, byline,
  query (charts.py:73-74 and all call sites).
- **XML sitemaps** escape `&` to `&amp;` in every loc (server.py:953,957,960,1013);
  `lastmod` is gated to a real ISO date shape (server.py:1015-1016).
- **10 MB description**: `render_dataset` completes in 0.59 s → 10 MB page. No
  pathological blow-up.
- **lru_cache staleness — none found.** `source_names`, `asset_version`,
  `_template`, `_hand_written_page` all key on deploy-time files, which change
  only on a code deploy that restarts the process, so the caches clear when
  they must. `_aggregates` is a 30-min TTL cache that picks up the nightly
  refresh on its own (server.py:481,516). `search.py`'s dup/retired cache keys
  on `DB_PATH` mtime (search.py:288-291), so a nightly rebuild is picked up
  without restart. No cache outlives the data it summarises.
- **Route shadowing — none.** `/sitemap-browse.xml` is declared before
  `/sitemap-{page}.xml` (int) (server.py:938 vs 969), so "browse" is never
  parsed as a page number; confirmed both resolve. `/sitemap-0.xml` and
  `/sitemap--1.xml` → 404, `/sitemap-abc.xml` → 422, as intended.
- **SQLite streaming across threads** is handled: `sitemap_page` `fetchall()`s
  before the generator streams (server.py:1001-1004), avoiding the documented
  cross-thread cursor `ProgrammingError`; DB opened read-mostly with WAL +
  busy_timeout (paths.py).
- **Pagination edges** are bounded by `Query(ge=…, le=…)`: `page=0` → 422,
  huge pages → `render_missing` 404 (server.py:617-619). `offset`/`k` on
  `/api/search` are capped (le=200 / le=50).

## Minor note (not user-facing)

`/sitemap-{page}.xml` takes 4.6 s wall to emit 3.5 MB even though the SQL is
0.58 s and string-building 0.13 s — the rest is per-chunk ASGI overhead from
yielding 25,002 one-URL chunks through `StreamingResponse`. Crawler-only and
cached 6 h, so low impact, but batching the yields (e.g. 1,000 URLs per chunk)
would cut it by ~5×.
