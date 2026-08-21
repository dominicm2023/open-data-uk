# SEO audit — open-data.org.uk

Audited 2026-08-21. ~43 live fetches (all with `agent.py` HEADERS, ≤1/sec) + code review of
`pagerender.py` / `server.py` head/JSON-LD/sitemap logic. Findings ranked by user impact.

---

## 1. ~2,900 indexable dataset pages emit JSON-LD with **no `description`** — ineligible for Google Dataset Search

- Code: `pagerender.py:164-165` — `if desc := plain_text(rec.get("description")): data["description"] = ...`
  The JSON-LD only gets a description when the publisher wrote one. `meta_description()`
  (`pagerender.py:123-145`) fabricates an honest fallback for the meta tag, but it is never
  reused in the JSON-LD.
- Live: `https://open-data.org.uk/dataset?key=datamillnorth%3A2z7z6` → 200, `robots index,follow`,
  JSON-LD parses as `@type: Dataset` with `name` present and `description` absent (desc_len=0).
- Scale (local index.db, using the exact `INDEXABLE AND NOT NOTHING_TO_INDEX` SQL from
  `server.py:863-870`): **2,915** sitemap-listed pages have no JSON-LD description at all, and a
  further **4,218** have one under 50 chars — ~8.5% of the 83,568-page corpus.
- Why it matters: `description` is a **required** property for Google's Dataset rich result
  (50–5,000 chars recommended). These pages are exactly the "no-prose but real files" records the
  site deliberately keeps indexable (`is_thin` comment, `pagerender.py:213-216`), yet they are
  invisible to Dataset Search — the one vertical this site exists to win. Fix is one line: fall
  back to `meta_description(rec)` in `json_ld()`.

## 2. `www.open-data.org.uk` serves the full site with 200 — no host canonicalisation redirect

- Live: `GET https://www.open-data.org.uk/` → `HTTP/1.1 200 OK` (no redirect).
  `GET https://www.open-data.org.uk/about` → 200 with body canonical
  `https://open-data.org.uk/about`.
- The absolute canonical tag (SITE_URL, `server.py:34`) mitigates it, but every www URL is a
  crawlable duplicate of the whole ~90k-page site, and canonical tags are hints, not directives.
  A 301 from www→apex at Cloudflare/Caddy is the standard fix. (Contrast: `http://` → apex is
  already a clean single `308` to `https://` — that half is done right.)

## 3. `/who-publishes` serves every case/punctuation variant of a name as a 200 that declares **itself** canonical

- Code: `server.py:827-847` — the handler normalises `name` to a slug to find the records, but
  passes the **raw** `name` to `render_who()`; `pagerender.py:628-632` builds the canonical from
  that raw title (`who_path(title)`).
- Live: `/who-publishes?name=Conservation%20Areas` → 200,
  `<link rel="canonical" href=".../who-publishes?name=Conservation%20Areas">`;
  `/who-publishes?name=conservation%20areas` → 200, **same 106-organisation content**, but
  `<link rel="canonical" href=".../who-publishes?name=conservation%20areas">` and a lower-cased
  `<title>`/h1. Unbounded spelling variants each self-canonicalise → classic duplicate-content
  split if anyone links a variant. Fix: render with `agg["shared_label"][slug]` instead of `name`
  (the topic handler already does this correctly — `/topic?tag=ENVIRONMENT&page=2` → 200 with
  canonical to the lower-case form, verified live).

## 4. Trailing-slash redirects downgrade to `http://` (proxy scheme not forwarded)

- Live: `GET https://open-data.org.uk/about/` → `307` with `location: http://open-data.org.uk/about`,
  then Cloudflare 308 back to https (2 hops, verified with `-L`: ends 200 at the https URL).
  Same for `/dataset/` → `location: http://open-data.org.uk/dataset`.
- Starlette's `redirect_slashes` builds the Location from the scheme uvicorn sees, and uvicorn
  behind Caddy isn't honouring `X-Forwarded-Proto` (needs `--proxy-headers` +
  `--forwarded-allow-ips`, or Caddy stripping/setting the header). Every slash-variant link
  anyone creates costs an https→http→https chain and a 307 (temporary) hop that passes weaker
  signals than a single 308/301. Also worth an edge rule: redirect trailing-slash at Caddy.

## 5. HEAD returns 405 on every HTML page

- Live: `curl -I https://open-data.org.uk/dataset?key=datamillnorth%3Avqxw4` →
  `HTTP/1.1 405 Method Not Allowed`, `Content-Type: application/json`.
- Code: FastAPI's `@app.get` registers GET only; unlike plain Starlette it does **not** auto-add
  HEAD. The static files were given explicit HEAD for exactly this reason
  (`server.py:216-219` — "a 405 on the favicon reads as a broken asset") but the pages weren't.
  Link-preview fetchers and some crawlers probe with HEAD first; a 405 there makes the page look
  broken. Add `methods=["GET","HEAD"]` (or a small middleware) for the HTML routes.

## 6. Unknown paths 404 as bare JSON, not a page

- Live: `GET https://open-data.org.uk/this-page-does-not-exist` → 404,
  `Content-Type: application/json`, body `{"detail":"Not Found"}`.
- The status code is correct (no soft-404 problem), so search engines are fine — but a person
  following a mistyped link gets raw JSON with no navigation. `render_missing()`
  (`pagerender.py:658-667`) already exists and is used for unknown dataset keys
  (verified live: `/dataset?key=nope%3Adoesnotexist` → 404 with a proper HTML page, noindex).
  Register it as the app-wide 404 exception handler.

## 7. No `og:image` / `twitter:image` anywhere on the site

- Code: `pagerender.py:243-256` (`head_tags`), `pagerender.py:401-417` (`simple_head`),
  `web/index.html`, `web/about.html` — grep for `og:image` across the repo: zero hits.
- Every share on Slack/WhatsApp/LinkedIn/X renders a text-only card. `web/icon-512.png` exists
  and would do as a site-wide default (`twitter:card` can stay `summary`). Low effort, visible
  payoff on exactly the pages ("Who publishes X?", /findings) built to be shared.

## 8. Minor

- **Deep pagination chains**: publisher pages link only prev/next (`pagerender.py:493-496`).
  ONS has 5,356 datasets → 54 pages; a dataset on page 54 is ~55 clicks from home. All paginated
  pages are in sitemap-browse.xml (verified: `...&page=2` variants present and 200), so discovery
  is fine, but internal PageRank flow to deep pages is a long chain. Consider first/last links or
  a larger PER_PAGE for the giants.
- **Paginated pages reuse one meta description** verbatim (only the title gains "(page N)") —
  e.g. ONS pages 1 and 2, verified live. Harmless while canonical+title differ, but easy to add
  the range ("datasets 101–200 of…").
- **`/docs` is nav-linked on every page but `Disallow: /docs` in robots.txt** — Google can index
  it URL-only ("no information available" stub). Either drop the disallow (it's a cheap static
  Swagger page) or accept the stub.
- **About page title says the brand twice**: "About — how the UK Open Data Index works — UK Open
  Data Index" (`web/about.html` line 6). Home title is 71 chars and will truncate in SERPs; fine
  but trimmable.
- **Retired-record descriptions leak markdown**: ds nhsbsa:d5d7cd63… meta description begins
  "##This dataset is retired" — `plain_text()` strips tags but not markdown heads. Cosmetic.

## Checked and healthy (no action)

- **Sitemap coverage vs reality**: index lists sitemap-browse + sitemap-1..4; 9/9 sampled URLs
  (6 datasets across sm1/sm4, 2 publisher incl. a `&page=2`, 1 who-publishes) → 200 and
  `index,follow`. Hub pages (/publishers, /topics, /who-publishes, /findings) are all in
  sitemap-browse.xml (7,112 URLs) with home + /about in sitemap-1. lastmod values all
  `YYYY-MM-DD`, none in the future; the two pre-2000 dates (1997, 1999) are genuine publisher
  metadata. Ampersands correctly `&amp;`-escaped.
- **Noindex-thin logic**: neither too lax nor too aggressive on the evidence. The SQL sitemap
  filter (`server.py:863-866`) and the Python `is_thin()` (`pagerender.py:204-222`) are worded
  differently (raw vs tag-stripped length; resource_count vs joined rows), but a full scan of
  index.db found **0** records where they disagree — nothing noindexed sits in the sitemap.
  Live: thin `datamillnorth:2l6p5` → noindex,follow; no-desc-with-files `datamillnorth:2z7z6` →
  index,follow (correct per the documented AND rule); retired → noindex,follow; duplicate
  `data_gov_uk:c7a7c892…` → 200, index,follow with canonical to `datamillnorth:e6q0n`. All as
  designed.
- **Canonical hygiene elsewhere**: `?utm_source=` on a dataset URL → canonical stays clean;
  `?page=1` collapses to the bare URL (`publisher_path`, `pagerender.py:88-91`); topic case
  variants canonicalise to the normalised tag; `/publisher` case variants 404 rather than
  duplicate. Out-of-range pages (`&page=999`) → real 404.
- **robots.txt**: sane — pages open, `/api/`, `/lab`, `/docs` blocked, sitemap declared,
  correct absolute sitemap URL.
- **Titles/descriptions across page types**: distinct patterns per type (dataset "T — Publisher —
  Site", publisher "N — open datasets", topic "T — UK open data", who "Who publishes T data? N UK
  organisations"); fabricated descriptions state facts rather than boilerplate-only. No
  cross-type duplication found in the 25 pages fetched.
- **JSON-LD validity**: all 11 dataset pages parsed cleanly; `@type: Dataset`, `name`, `url`,
  `identifier`, `includedInDataCatalog`, capped `distribution` (≤50) present; licence URLs only
  asserted for known ids. Home page carries a valid WebSite+SearchAction whose `?q=` target the
  front-end really honours (`web/index.html:203`).
- **Page weight / render-blocking**: one 20KB system-font stylesheet, content-hashed URL,
  `max-age=86400`; no external fonts, no JS on rendered pages, dataset pages ~6KB gzipped; HTML
  cacheable (`max-age=3600, stale-while-revalidate`). Hub pages up to ~245KB raw but compress
  well and are pure HTML.
- **http→https**: single 308 at the edge. `/health`, `/api` correctly out of the crawl path.
