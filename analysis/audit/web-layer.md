# Web-layer bug audit — server.py / pagerender.py (local only)

Adversarial review, 21 Aug 2026. All evidence gathered locally: code reading, read-only
queries against `index.db`, and Starlette `TestClient` runs against the real app. No live
requests were made. Findings ranked by user impact.

---

## 1. Every page route returns 405 to HEAD — only the static files answer it

**Where:** every `@app.get` route in server.py; contrast server.py:215-219, the one place
HEAD is handled.

FastAPI's `APIRoute` does not auto-add HEAD to a GET route (plain Starlette `Route` does —
which is presumably where the assumption came from). The static-file loop registers
`methods=["GET", "HEAD"]` explicitly, with a comment saying exactly why it matters:
"caches and link-preview fetchers ask for headers before bodies, and a 405 on the favicon
reads as a broken asset." Every other route was left on the default.

**Reproduction (TestClient, local):**

```
HEAD /                -> 405        HEAD /robots.txt      -> 405
HEAD /about           -> 405        HEAD /sitemap.xml     -> 405
HEAD /dataset?key=x   -> 405        HEAD /publishers      -> 405
HEAD /api/search?q=t  -> 405        HEAD /favicon.svg     -> 200
```

**Impact:** `curl -I`, uptime checkers, link validators, and any crawler that probes with
HEAD before GET see the entire site — including robots.txt and the sitemaps — as broken,
by the project's own stated standard. The 405 body is JSON, on routes that otherwise serve
HTML/XML.

---

## 2. /who-publishes indexes unlimited duplicate URLs of itself — canonical echoes attacker/typo input

**Where:** server.py:815-848 (`who_publishes` accepts any `name` whose `_norm_title` slug
matches a shared title); pagerender.py:628-632 (`render_who` builds the canonical from
`who_path(title)` — the raw query param).

`_norm_title` collapses case and punctuation, so infinitely many spellings reach the same
200 page — and each one self-canonicalises to its own variant with `index,follow`.
Contrast `/topic`, which normalises the tag before building its canonical
(server.py:762, pagerender.py:100), so variants collapse correctly there.

**Reproduction (TestClient against index.db):**

```
/who-publishes?name=06.07.26      -> 200, canonical .../who-publishes?name=06.07.26
/who-publishes?name=06.07.26!!!   -> 200, canonical .../who-publishes?name=06.07.26%21%21%21
```

(pagerender unit test: "CONSERVATION---AREAS!!!" → 200, self-canonical, `index,follow`.)

**Impact:** duplicate-content pollution of exactly the pages built to be the site's front
door; anyone (or any stray link with different casing/punctuation) mints competing
indexable copies. Fix shape: canonicalise on `agg["shared_label"][slug]` rather than the
input, or 301 non-canonical spellings.

---

## 3. Rate limiter: loopback guard proves "came via Caddy", not "came via Cloudflare" — headers are attacker-choosable on direct origin hits

**Where:** server.py:89-110 (`_client_ip`).

The guard trusts `CF-Connecting-IP` (then `X-Forwarded-For[0]`) whenever the direct peer
is `127.0.0.1`/`::1`. In production the direct peer is *always* Caddy, so the check is
satisfied for every request — including one made straight to the origin IP, bypassing
Cloudflare. Unless Caddy strips/overwrites `CF-Connecting-IP` (its default `reverse_proxy`
passes unknown headers through and only *appends* to `X-Forwarded-For`), a direct client
sends a fresh `CF-Connecting-IP` per request and gets a fresh bucket per request —
unlimited `/api/search`, the endpoint that runs ~0.5 s of sentence-transformer CPU per
call. `X-Forwarded-For[0]` is likewise the client-appended end of the chain, so the XFF
fallback is spoofable the same way.

**Reproduction (unit test on `_client_ip` with crafted ASGI scopes):**

```
peer 127.0.0.1 + CF-Connecting-IP: "SPOOFED-ANYTHING at all !!"  -> bucket "SPOOFED-ANYTHING at all !!"
peer 127.0.0.1 + X-Forwarded-For: "spoofed, 198.51.100.7"        -> bucket "spoofed"
peer 127.0.0.1 + X-Forwarded-For: " , 198.51.100.7"              -> bucket ""  (all such clients share one bucket)
peer ::ffff:127.0.0.1 (v4-mapped loopback)                        -> not treated as loopback; headers ignored
peer 203.0.113.50 direct                                          -> headers correctly ignored
```

The code says explicitly this is f