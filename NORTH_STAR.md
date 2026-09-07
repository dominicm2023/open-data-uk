# North star

> **Anyone looking for UK open data finds it here first — and knows, before
> they click, whether it's really there.**

Set 4 September 2026. Two words carry the ambition: *first* and *really*.

**First** means completeness and findability together. We know where all of
it lives — every portal, every council, including the sources we know about
but cannot harvest — and a person who wants it reaches us before they reach
anything else, whether they arrive by our search box or by Google.

**Really there** is the thing nobody else can say. We followed the link. We
can tell you it is a data file, an API, a webpage, a dead end, or that we
could not tell — and we say which, before you click.

**Really there has a third level (added 6 September):** can a person use
what is behind the link? A four-page PDF of senior salaries is really there
by the first two tests and useless by any practical one. So, for the things
many bodies publish, we also offer **one combined, attributed table beside
every original link** — digested per family, published only when a person
has reviewed the mapping, every row traceable to its source file and line.
`FAMILIES.md` is the brief. The index finds, verifies and digests; Joined
Up reads and argues.

The star is what we are for. The site says only what we have done: the
front page says "194 portals", not "every portal", and it stays that way
until the gap is closed.

## What we measure

| | Now (4 Sep 2026) | Means |
|---|---|---|
| **Coverage** — UK public bodies with attributable data | 353 of 361 councils; 8 leave no trace | Do we know where it all lives? |
| **Certainty** — findable datasets with a verdict under 30 days old | 84% checked; 18,264 never | Can we say what is really there? |
| **Findability** — searches ending at a publisher, ours and Google's | Google: 16 clicks/day, 1,395 impressions/day, avg position 17 (2 Sep); 8,746 indexed, 78,306 waiting | Do people reach it through us? |
| **Guardrail** — verdicts that were wrong | 1,239 wrong for three weeks (launch-day 429s) | Are we still the people who know? |
| **Usability** — who-publishes families with a reviewed, published combined table | 3 published (6 Sep): recycling centres 84 rows/9 bodies; air quality annual means 14,412 rows/4 bodies; spend over £500 825,841 rows/13 bodies (262 monthly files) — of 30, 51 and 60 bodies in each registry | Can a person use it without doing the extraction themselves? |

The guardrail is a reputation metric. Being wrong for three weeks is worse
than saying "not verified" for three weeks.

## Not this

**Joined Up is separate.** The campaigning arm — the organogram cascades,
Pen's Parade, the posters — makes arguments from data. From 4 September it
lives in its own repository (`../Joined Up`) and uses this site through the
public API like anyone else. Nothing under `/lab` is served from here.
Refined 6 September: the *extraction* Joined Up used to do for itself is
the index's job now (the family tables); the *messages and stories* drawn
from them remain Joined Up's, entirely.

**The Findings page stays, and is measurements only.** Facts about the
data: who publishes what, under which terms, whether the links work, which
councils leave no trace. The generator's tier ladder stops at 3 (a
measurement about a named body, checked by a person first). The two rungs
above it — cross-source joins, and framing and argument — were removed on
4 September and belong to Joined Up.

## Ideas and strategies

A living list. Add freely; move to "Done" with the commit that did it.

### Coverage — know where it all lives
- The 8 councils with no trace (5 England, 1 Scotland, 2 Wales): find the
  portal or record that there isn't one. `COUNCIL_COVERAGE.md` has the list.
- `PLATFORM_BACKLOG.md`: verified portals we have no harvester for.
- **A directory of sources we know but do not harvest** — Network Rail,
  TfL, CQC and the other registration-gated ones. Listing where something
  lives is not probing it. Knowing it exists is on-star.
- The five description-gated AGOL councils (barnet, bolton,
  buckinghamshire, rochdale, rushmoor): decide the `require_description`
  gate.
- Publisher aliasing as a first-class registry: Stirling was four
  publishers until today. Same organisation under several names is a
  coverage error as well as a dedupe one.

### Certainty — say what is really there
- The 255,301 resources never checked. At 2,500 a night with 30% reserved
  for rechecks, the backlog is ~150 nights. Either more budget per night
  (politeness is per host; parallelism across hosts is free) or prioritise
  by what people actually reach.
- **Verdict age as a first-class number.** A verdict is a claim with a
  date. Show it; re-verify anything a visitor is about to click if it is
  older than N days.
- `nofiles` at #1: a record with nothing behind it currently beats a
  working API of the same name (exact-title ×3.0 outweighs nofiles ×0.95).
- No recency signal at all in ranking: "crime in my area" → a 2007 dataset
  first. Decide whether recency belongs in relevance or only in display.
- The `allotment waiting lists` case: the rare-term boost picks the wrong
  word when two terms have near-equal document frequency. Needs a better
  notion of "decisive" than raw DF.
- Publishers' own upstream errors (data.gov.uk attributing Newcastle's
  payments to Sunderland): reproduce faithfully, but name them as findings.

### Findability — be reached first
- **Google is the search box.** 70 searches in ours in three weeks; the
  Search Console shows the rest. The ~90k unindexed pages are the single
  largest gap. Internal linking depth, crawl budget, sitemap hygiene.
- **Search Console, 4 Sep (3 months):** dataset pages carry 73% of
  impressions and 74% of clicks; publisher pages have the best CTR (1.2%);
  topic pages rank badly (avg position 42); who-publishes pages have barely
  surfaced (46 impressions in total) — so they are *not yet* our best
  landing pages, whatever the theory says. 90% of clicks come from queries
  Google hides as too rare: we win in the long tail. We lose on site-name
  queries ("catchment data explorer": top 10, 55 impressions, 0 clicks) —
  people want the publisher's own tool, and should.
- **"Crawled - currently not indexed" (2,013) is not thin pages.** The URL
  export (4 Sep, 1,000 of them) classified against the index: 90% are good
  pages with real prose and files. What they have in common is the URL:
  89% carry a dataset key that is itself a URL (`?key=source:https://www.
  arcgis.com/...?id%3D...%26sublayer%3D18`), against 11% of the index —
  7.8x over-represented. Sources with such keys lose 10-15% of their pages;
  data.gov.uk, with UUID keys, loses 0.1%. Second cause: 26% are one
  edition among many of the same title (34 ONS UPRN Directory pages), which
  Google collapses; index-wide 11,710 pages sit in 1,719 such series.
  Levers: short clean dataset URLs with a 301 from the old form; canonical
  from older editions to the latest.
- 78,306 pages "discovered - currently not indexed": the crawl-budget queue.
  Levers are internal link depth (pagination fixed 22 Aug: 431 → 8,746
  indexed), sitemap `lastmod` accuracy, and not wasting fetches on thin
  pages.
- Page-2 opportunities with real volume: "employment by occupation" (pos
  15), "hospital episode statistics" (pos 20), "ons annual business survey"
  (pos 21) — all ONS pages.
- The pattern that wins: council-published *documents* with weak native
  SEO — North Yorkshire pay scales and Article 4 took 5 of the 50 clicks.
- Click-through is measured from 2 Sep. Watch it. A search that ends at a
  publisher is the only success we can see.
- Spelling correction shipped 3 Sep; watch the log for the next class of
  miss (synonyms? plurals we do not stem?).
- Machines are readers too: `llms.txt`, `openapi.json` and the API are how
  an AI client reaches us. MCP was shelved for friction on 2 Sep; revisit
  when a client makes it frictionless.
- Home page stats poll every 30 s and `/api/stats` now runs a full key
  scan per call; cheap today, worth caching when traffic is real.

### Usability — one table for the things many bodies publish
- The brief is `FAMILIES.md`. First three families, in order: household
  waste recycling centres (two portals already unified), air quality annual
  means (Leicester mapped, 184 site-years), spend over £500 (Joined Up's
  supplier work depends on it). Each proves what the next needs.
- Only the top rung of the ladder publishes: fetched → extracted →
  shape-checked → mapped → reviewed → published. Below that is private
  evidence, kept by hash.
- Licence: explicit OGL v1–3 only. Personal data is a separate decision
  from licence; salaries and organograms wait on it.
- Politeness before scale: 1.5 s per host, `Retry-After`, a retry budget.
  The pilot hit Brent at four requests a second and was told 429.
- The site's promise changes with this: originals always linked, and a
  combined table only where the licence explicitly allows it. About,
  README, `llms.txt` and the API description say so from 6 September.

### Guardrail — stay right
- Nightly digest already reports service health; add **verdict health**:
  how many verdicts are older than 30 days, how many flipped on recheck.
- A standing "what did we get wrong" section on the Findings page. The
  launch-day 429s are the first entry.

### Done
- 6 Sep — `families/` built (registry from the index, polite licence-gated
  intake, mapping engine with BNG/Irish Grid/ITM conversion, provenance on
  every row, `/family/<name>` pages and API). First two families published;
  mapping proposals delegated to Sonnet agents and reviewed.
- 6 Sep — third promise adopted: digest per family, publish only reviewed.
  Site wording changed; `FAMILIES.md` written as the brief for Codex.
- 6 Sep (later) — series layouts per file, content-chosen layouts when a
  header lies, Irish grids, per-file held-row tallies for reviewers; spend
  over £500 grew from 114k to 826k rows, 13 new recycling/air sources reviewed.
- 7 Sep — Combined data section (`/combined`, nav); family pages redrawn:
  map or years grid, computed Q&A, column fill, filters with filtered CSV
  download from a SQLite twin of each table. Date parser widened (28% of
  spend rows had lost their date); month-first files detected per file.
- 7 Sep — licence gate widened on read wording: OGL named beside OS /
  INSPIRE / portal-catalogue words is the OGL (York, Wiltshire, Stirling);
  CC BY accepted; Bristol's acknowledgement-only fields accepted by portal
  decision. PSMA-only, INSPIRE-only and OSNI-only stay refused.
- 5 Sep — older editions of a series canonicalise to the latest when the
  description matches: 4,231 pages in 1,144 series, out of the sitemap,
  still served and searchable. (B of the not-indexed fix.)
- 5 Sep — every dataset page moved to `/dataset/<source>/<id>`; the old
  `?key=` form 301s. Cause: URL-shaped keys were 7.8x over-represented in
  "crawled, currently not indexed". Measure in the next Coverage export.
- 4 Sep — Findings page reduced to measurements: tier 4/5 prompts removed
  from the generator; arguments are Joined Up's.
- 4 Sep — audit fixes: portal names on results, 103% → 100%, three 404s,
  security headers + CSP, mobile filters, `/docs` self-hosted,
  `unreachable` ranked below a working page. (`7aabef6`)
- 4 Sep — About page figures read live from the index. (`b80424b`)
- 4 Sep — recheck queue split 30/70, 429s first; 52x reclassified as
  unreachable. (`b059e99`)
- 3 Sep — did-you-mean; lexical evidence can rescue confidence. (`7be9f85`,
  `b1ea9c2`)
