# THE IMPROVEMENT BACKLOG — open-data.org.uk
Synthesis of 7 audits (code:web, code:pipeline, search:quality, seo, perf, a11y, claims-drift), 2026-08-21.
Deduplicated; ranked by (user impact × confidence) / effort. /lab findings discarded per rules; nothing from the known-fixed list re-reported.

## QUICK WINS (under an hour each, high confidence)

Q1. Fix rate-limiter concurrent-mutation crash — snapshot `list(_hits.items())` in `_prune_hits`, lock `_last_prune`.
  Evidence: server.py:125,139; reproduced locally, 10 RuntimeErrors in 0.5 s with 12 threads. Random visitors get 500s once/min under load today. Effort: 15 min. [code:web]

Q2. Cloudflare Cache Rule: respect origin Cache-Control on non-/api, non-/lab paths.
  Evidence: cf-cache-status DYNAMIC on all 14 routes sampled despite correct max-age headers (server.py:450,630,935); only /site.css HITs. Turns 70–150 ms origin round trips into ~20 ms edge hits for ~83k pages and 3.5 MB sitemap chunks; also shields origin from the perf items below. Effort: config only. [perf]

Q3. JSON-LD `description` fallback to `meta_description(rec)`.
  Evidence: pagerender.py:164-165 vs :123-145; 2,915 sitemap-listed pages emit Dataset JSON-LD with desc_len=0 (live: /dataset?key=datamillnorth%3A2z7z6), +4,218 under 50 chars. `description` is required for Google Dataset Search — one line unlocks ~7k pages. Effort: minutes. [seo]

Q4. Checker: test content-type before API_HINTS.
  Evidence: checker.py:138-140; 1,563 api-verdicts serve text/csv (3,496 incl. spreadsheets/geojson), 2,162 datasets mis-badged 'api', leicester 393/393, 63,444 unchecked AGOL URLs growing nightly. Reorder + let column-peek (checker.py:202) fire. Verdicts self-heal over the check cycle. Regenerate /findings dead-based figures afterwards. Effort: small reorder. [pipeline]

Q5. opendata.scot resource-loop ident mismatch — reuse `normalise_dcat_dataset`'s key in the resource loop.
  Evidence: harvester.py:318-329 vs :379-384; 2,467/2,467 opendata_scot datasets have zero resource rows; 536 carry literal `sha1:…` in landing_url — the same 536 that render "Open at publisher" as dead `href="#"` (pagerender.py:354, safe_url :64-67). One source's entire resource data restored next harvest. Effort: <1 h code + rerun. [pipeline + a11y F4]

Q6. Add HEAD to all GET routes (or a HEAD middleware).
  Evidence: server.py:218 gives HEAD only to static assets; /, /dataset, /robots.txt, /sitemap.xml all 405 (live curl -I confirmed). Link-preview fetchers probing HEAD-first see a broken page. Effort: small. [code:web + seo]

Q7. /api/sources + /api/stats: cache the YAML (pagerender.source_names already lru-caches it), add `_rate_check` and Cache-Control.
  Evidence: server.py:1024-1041 yaml.safe_load of 117 KB per request, 372–831 ms live TTFB, no rate limit (no X-RateLimit headers observed). Cheapest unauthenticated origin-CPU burn. Effort: small. [code:web + perf]

Q8. Cache `_indexable_count()` for /sitemap.xml.
  Evidence: server.py:873-881,924-935; ~600 ms table scan per request for a 172-byte response; slowest route measured (436 ms median). Count changes nightly. Effort: small. [perf]

Q9. `np.load(..., mmap_mode="r")` for the embedding matrix.
  Evidence: search.py:97; ~158 MB × 4 workers, transient doubling on nightly hot-reload vs MemoryMax=3G — OOM trajectory at ~150k datasets. Effort: one arg + verify. [perf]

Q10. Tag-chip overflow: `overflow-wrap:anywhere`/truncate on `.chip`, and split comma-blob tags upstream in norm_tag.
  Evidence: site.css:241-247, pagerender.py:339-340; 341 tags >45 chars, worst 1,132 chars; live page spatialdata_scot:1577d05b… renders a ~7,000px chip forcing whole-page horizontal scroll (WCAG 1.4.10). Effort: CSS now, upstream split later. [a11y F1]

Q11. Skip link + `<main>` landmark in the shared template.
  Evidence: only web/index.html:63 has `<main>`; live /publishers has 0 main/skip (WCAG 2.4.1 A). One template edit covers ~60k pages. Effort: minutes. [a11y F2]

Q12. Correct the drifted static claims in index.html/about.html (one batch edit).
  Evidence: "every link verified" vs own About's 73% (index.html:7,12); "1,400-odd bodies" vs 1,799; "70% never to be updated" vs 47–52%; "10% broken" vs 7.0%; "15% no files" vs 18.1%; "82,000-odd" vs 84,486; "dozens of licence variants" vs 1,239 raw (magnitude backwards vs formats). Credibility site whose pitch is honesty. Effort: <1 h. Also: regenerate findings.json (Wales 8→7) and add the 🟠 filtered state to COUNCIL_COVERAGE.md summary. [claims-drift]

Q13. 301 www→apex at the edge.
  Evidence: https://www.open-data.org.uk/ → 200, full duplicate of ~90k pages (canonical mitigates). Effort: CF rule. [seo]

Q14. uvicorn `--proxy-headers --forwarded-allow-ips` (or edge slash rule) to stop the https→http 307 downgrade on trailing slashes.
  Evidence: /about/ → 307 to http:// → CF 308 back to https, 2-hop chain. Effort: flag change. [seo]

Q15. Register `render_missing()` as the app-wide 404 handler.
  Evidence: /this-page-does-not-exist → bare JSON `{"detail":"Not Found"}`; the HTML 404 already exists and works for unknown keys. Effort: minutes. [seo]

Q16. Default og:image/twitter:image (icon-512.png).
  Evidence: zero hits repo-wide; text-only share cards on pages built to be shared. Effort: minutes. [seo]

Q17. /who-publishes: render canonical from `agg["shared_label"][slug]`, not the raw query param.
  Evidence: server.py:827-847, pagerender.py:628-632; ?name=Conservation%20Areas and lowercase variant both 200 self-canonical — unbounded duplicate URLs. Topic handler does it right. Effort: small. [seo]

Q18. Search live region: announce a short count in `role="status"`, not 15 innerHTML cards.
  Evidence: index.html:72,150-174; SR behaviour is dump-everything or silence (WCAG 4.1.3). Effort: small JS. [a11y F3]

Q19. Focus outline on search input: remove the later `outline:none` that kills the designed :focus-visible style; lift the 1.55:1 resting border toward 3:1.
  Evidence: site.css:82-86 vs 199-210. Effort: CSS. [a11y F6]

Q20. Format alias table: fold case/dot variants (.XLSX 1,151 resources, .PDF 650, .XLS 179; 2,194 resources invisible to format filters).
  Evidence: normalise.py:444,496. Effort: small dict. [pipeline]

Q21. Alias `license=ogl` → `ogl-uk-*` in the filter (currently silently 0 results).
  Evidence: stored value ogl-uk-3.0; search F10. Effort: small. [search]

Q22. ETag or short max-age on / and /about.
  Evidence: server.py:176,182 no-cache with no validators on the highest-traffic, memory-cached, hash-busted page. Effort: minutes. [perf]

## REAL WORK (days, worth it)

R1. Dedupe correctness pass — the biggest data-quality cluster, all in dedupe.py:
  a) Missed merges: consult the shared source UUID — 716 of 2,701 same-UUID cross-source groups (26%) undeduplicated; live top-3 slots burned by identical pairs (`inpatient waiting times`, `potholes`), aggregator copy ranked above publisher (dedupe.py:75-88). [search F1]
  b) Retired-canonical black hole: rank() ignores retired (dedupe.py:111-117), search drops the whole group (search.py:397-402), subject pages/sitemap exclude both sides (server.py:773-774,868-870) — 553 live datasets invisible; 9 groups hide a verified copy behind a dead canonical. [pipeline]
  c) False merges: fallback source-name-as-publisher satisfies "publishers match" (2,473 pairs, NBN "1"×13 collapsed); "london" in _PUBLISHER_NOISE merges DfT national Cycle Routes into TfL's London layer (dedupe.py:57-62,77). [pipeline]
  Impact: hundreds of datasets recovered, duplicate top-3s gone, wrong merges undone. Effort: 2–4 days + re-run + relevance-suite regression.

R2. Geo/place quality pass:
  a) Bbox sanity: reject UK-spanning bboxes on borough/district publishers (3,654 total, 22 on councils) and rebalance GEO×dead so 1.45 × 0.85 can't put a dead wrong-place record at #1 (search.py:45-52; live `air quality cardiff` → dead Rushcliffe #1). [search F3]
  b) Gazetteer: window ≥3-word places (62 unreachable keys incl. "newcastle upon tyne"), purge corrupt "of london"/"of edinburgh" keys, add counties, add Welsh-language aliases (geo.py:113-133; `caerdydd air quality` → Durham/Bristol/Belfast). [search F2, F6]
  Effort: 2–3 days + regression.

R3. Ghost-row removal: harvester only UPSERTs (harvester.py:171-184) — 2,112 deleted-at-source records live in search and sitemap (data_gov_uk 1,926 frozen ≤13 Aug). Needs a seen-in-run tombstone policy with a safety margin for partial harvests. Effort: 1–2 days. [pipeline]

R4. `_aggregates()` precompute or lock: 2.4 s full scan on the user path (dataset page included, server.py:441,500-583), per worker per 30 min, unlocked so concurrent expiry multiplies. Move to the nightly-file pattern /findings already uses, or add a lock + serve-stale. Effort: half a day; big tail-latency win (partially masked once Q2 lands). [perf]

R5. Licence normalisation round 2: 752 distinct license_norm values — "custom" leaks as a chip on 7,598 datasets (harvester.py:917), OS INSPIRE EUL family 1,170 datasets across 20+ spellings, 4,684 truncated "..." chips, HTML entities never unescaped (normalise.py:355-382), "No licence"/"unpublished" kept as licences. Effort: 1–2 days mapping work. [pipeline + claims-drift #7]

R6. Title quality: prettify 1,439 machine-slug titles (ENV_ALLOTMENTS, PS_SD_…POLY_CURRENT) that reach #1 in real queries and don't match user vocabulary; tighten norm_title's junk gate (153 NBN titles ≤3 chars, "1"×13) (normalise.py:34-42). Interacts with R1c. Effort: 1–2 days. [search F5 + pipeline #11]

R7. Edition-series collapse + recency tiebreak: `heritage at risk register` fills top-5 with 5 yearly editions ordered 2022-first; ONSPD returns 5 monthly User Guides, not the data. Effort: 2–3 days design + tuning. [search F8]

R8. UK-scope gate for research-catalogue imports: Panama/Brazil/Uganda/Vietnam datasets in a UK index via EIDC/CEDA on data_gov_uk. Effort: 1 day (bbox or publisher scoping). [search F9]

R9. "Strong" confidence honesty: strong + no banner on place-only garbage (`conservation area basildon`, `east sussex SEND rates`); SIM_STRONG=0.55 knife-edge (`councl spending` = 0.556); confidence computed pre-filter so "strong" can head zero filtered results. Recalibrate thresholds + require keyword corroboration. Effort: 1–2 days + suite. [search F4, F11, F10]

R10. Dead-verdict evidence policy: 34% of dead datasets (1,889/5,534) have ≥1 never-checked resource; 2,182 dead verdicts are status 0 (DNS/timeout folded into dead, checker.py:197-198,281-293). Split "unreachable" from "dead", require full evidence before the rollup. Effort: 1 day + recheck cycle. Do after Q4 so figures settle once. [pipeline]

R11. Harvest key collisions: sha1(publisher|title) and landing-URL idents silently overwrite 48 records/harvest (opendata_scot feed 2,507 → 2,467 stored); harvest_runs reports pre-collision counts, hiding it. Salt the key with source ident or position. Effort: 1 day + key-migration care. [pipeline]

## QUESTIONED (plausible, verify before coding)

X1. Availability-nudge inversion (search F7): single-query evidence (`ambulance response times`: ×1.15 data-badge spending dataset beats the on-topic ×0.97 webpage). Tune only after checking the relevance suite doesn't depend on the current multipliers.

X2. require_description zeroing whole councils (agol_neath_port_talbot 139→0, agol_rochdale 71→0): evidenced, but the gate is deliberate policy — decide whether desc-less AGOL layers are wanted before touching it. Meanwhile: add a harvest alert for sources at 0 (enwl, spen have never yielded a dataset — 3 page errors each, only witness is harvest_runs; harvester.py:472-477). [pipeline]

X3. Rate-limit IP resolution (leftmost XFF forgeable; `::ffff:127.0.0.1` not in loopback list, server.py:103-110): both dead code in the real CF chain per the auditor. Verify Caddy's socket family before spending time.

X4. /docs Swagger a11y + robots-disallowed-but-linked (a11y F7, seo minor): real but the fix choice (self-host with lang attr vs replace with a static API page) needs a decision.

X5. Sitemap chunk ASGI overhead (~4 s in 25k tiny yields, code:web minor): crawler-only, cached, and Q2 would edge-cache it — likely never worth touching. Re-check after Q2.

X6. a11y small fry to batch when convenient: aria-current in server template (F8), inconsistent new-tab behaviour (F9), geo banner CTA with no link (F10), h1→h3 jump (F11), duplicate id="hatch" (F12), autofocus debate (F13), mobile nav scroll cue (F5). None urgent; fold into the next template pass alongside Q11.

## DO FIRST — three picks

1. Q1 rate-limiter crash: live users are eating 500s today; 15-minute fix with a local repro to verify against.
2. Q2 Cloudflare Cache Rule: zero code, converts the site's already-correct cache headers into edge hits for ~83k pages, and halves the urgency of R4/Q7/Q8 in one stroke.
3. Q3 JSON-LD description fallback: one line puts ~2,900 currently-ineligible pages (plus 4,218 thin ones) into Google Dataset Search — the single largest discovery lever found anywhere in the seven audits.
(First real-work slot after those: R1 dedupe pass — it's the root cause behind duplicate top-3s, 553 invisible datasets, and wrong merges at once.)

## AGREED HEALTHY — don't touch
- Escaping/XSS: hostile input, JSON-LD, SVG, XML all clean (code:web, deep battery).
- Sitemaps: structure, lastmod, escaping, 20 Aug threading fix holding (perf 5/5, seo 9/9).
- Canonical/noindex hygiene: thin-page logic 0 divergent records in a full scan; utm stripping, page=1 collapse, out-of-range 404s (seo).
- Search baseline: 12/12 relevance suite; typo robustness, synonyms, honesty labels where the gap is real; filter AND/OR semantics sound (search).
- Transport/perf plumbing: HTTP/2+3, keep-alive, compression everywhere, static-asset caching, warm TTFB 70–150 ms, startup warming, /health (perf).
- Contrast: every text token pair ≥4.5:1 in both themes; charts hatch + label, never colour-alone (a11y).
- Stated rate limit and privacy claims verified true in code (claims-drift #13); hub pages compute figures live so cannot drift.
- Pipeline negatives: no {{template}} remnants, no mojibake, no orphan rows, dates fully ISO, Cefas regression gone (pipeline).
