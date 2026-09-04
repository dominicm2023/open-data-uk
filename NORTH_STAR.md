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

The star is what we are for. The site says only what we have done: the
front page says "194 portals", not "every portal", and it stays that way
until the gap is closed.

## What we measure

| | Now (4 Sep 2026) | Means |
|---|---|---|
| **Coverage** — UK public bodies with attributable data | 353 of 361 councils; 8 leave no trace | Do we know where it all lives? |
| **Certainty** — findable datasets with a verdict under 30 days old | 84% checked; 18,264 never | Can we say what is really there? |
| **Findability** — searches ending at a publisher, ours and Google's | 1 click recorded; ~2k of 90k pages indexed | Do people reach it through us? |
| **Guardrail** — verdicts that were wrong | 1,239 wrong for three weeks (launch-day 429s) | Are we still the people who know? |

The guardrail is a reputation metric. Being wrong for three weeks is worse
than saying "not verified" for three weeks.

## Not this

**Joined Up is separate.** The campaigning arm — the organogram cascades,
Pen's Parade, the sewage and spending joins, the posters — makes arguments
from data. That is *using* data, not finding it. From 4 September it lives
in its own repository (`../Joined Up`) and uses this site through the public
API like anyone else. Nothing under `/lab` is served from here any more.

The Findings page stays, but only for findings that are evidence *about
where data lives and whether it is there*: coverage, dead hosts, licence
gaps, attribution. Findings about Britain belong to Joined Up.

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
- The 1,065 who-publishes pages are our best organic landing pages: one
  page per thing many bodies publish. Extend the idea — per place, per
  format, per licence.
- Click-through is measured from 2 Sep. Watch it. A search that ends at a
  publisher is the only success we can see.
- Spelling correction shipped 3 Sep; watch the log for the next class of
  miss (synonyms? plurals we do not stem?).
- Machines are readers too: `llms.txt`, `openapi.json` and the API are how
  an AI client reaches us. MCP was shelved for friction on 2 Sep; revisit
  when a client makes it frictionless.
- Home page stats poll every 30 s and `/api/stats` now runs a full key
  scan per call; cheap today, worth caching when traffic is real.

### Guardrail — stay right
- Nightly digest already reports service health; add **verdict health**:
  how many verdicts are older than 30 days, how many flipped on recheck.
- A standing "what did we get wrong" section on the Findings page. The
  launch-day 429s are the first entry.

### Done
- 4 Sep — audit fixes: portal names on results, 103% → 100%, three 404s,
  security headers + CSP, mobile filters, `/docs` self-hosted,
  `unreachable` ranked below a working page. (`7aabef6`)
- 4 Sep — About page figures read live from the index. (`b80424b`)
- 4 Sep — recheck queue split 30/70, 429s first; 52x reclassified as
  unreachable. (`b059e99`)
- 3 Sep — did-you-mean; lexical evidence can rescue confidence. (`7be9f85`,
  `b1ea9c2`)
