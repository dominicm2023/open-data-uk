# UK Open Data Index

**One search across 84,000+ UK datasets, from 54 portals.**
Live at **[open-data.org.uk](https://open-data.org.uk)** ·
[open API](https://open-data.org.uk/docs) · no tracking, no sign-up.

[![Validate sources](https://github.com/dominicm2023/open-data-uk/actions/workflows/validate-sources.yml/badge.svg)](https://github.com/dominicm2023/open-data-uk/actions/workflows/validate-sources.yml)

UK open data is scattered across dozens of portals that don't know about
each other, with metadata so inconsistent it's effectively invisible to both
people and AI tools. Ask *"flood risk in Brighton"* on data.gov.uk and you
get keyword matches on the word "Brighton". Ask it here and you get the
Environment Agency's England-wide flood maps — because we know their
published boundary actually covers Brighton, even though the word never
appears in them.

Four things make it different from searching a catalogue directly:

- **It searches meaning, not just keywords.** Ask in plain English; results
  come back ranked by what you meant, from every portal at once.
- **It tells you whether there's actually data behind the link.** We follow
  every resource link and label it: a verified data file, an API, just
  another webpage, or a dead end. Most catalogue links lead to another page,
  not a download — you find out before you click, not after.
- **It admits what it doesn't have.** No results for your town? It says so,
  instead of quietly showing you Glasgow.
- **It answers questions no single portal can.** 91 councils publish a
  dataset called *Conservation Areas*, 77 publish *Tree Preservation Orders*,
  227 publish an organogram. Each portal knows only its own, so nobody could
  list them together — see
  [who publishes what](https://open-data.org.uk/who-publishes).

**Metadata only.** We never rehost anyone's data — every result links to the
publisher's own page, under the publisher's own licence.

### What we found building it

Measured across the whole catalogue: **34%** of datasets state no licence,
**40%** haven't been updated in two years, **20%** are duplicate copies of
another portal's entry, and of the links we've verified only **36%** give
you machine-readable data — **30%** just lead to another webpage, and for
**14%** the publisher lists no files at all.

Those numbers are worse than they need to be, and we're careful not to make
them look worse than they are. A publisher whose server blocks our checker
is reported as "not verified", never "dead". A dataset that declares it will
never be updated again isn't counted as neglected. An API endpoint counts as
usable data, not a miss. And a licence recorded in a non-standard field
still counts as a licence — fixing that one bug alone moved the "no licence"
figure from 56% to 34%.

## What's here

| Piece | File(s) |
|---|---|
| Source registry ("registry as code") | [`sources.yaml`](sources.yaml) — add a portal via PR, CI validates it |
| Harvesters (CKAN, DCAT/ArcGIS Hub/Socrata, OpenDataSoft, GeoNode, bespoke JSON) | [`harvester.py`](harvester.py) |
| How we introduce ourselves, and why the wording matters | [`agent.py`](agent.py) |
| Licence/format normalisation | [`normalise.py`](normalise.py) |
| Embeddings + keyword index | [`embed_index.py`](embed_index.py) |
| Duplicate & retired-record detection | [`dedupe.py`](dedupe.py) |
| Link availability verification | [`checker.py`](checker.py) — follows every resource link and reports what's really there: `data` / `api` / `webpage` / `dead` / `blocked` |
| Hybrid search engine | [`search.py`](search.py) — semantic + BM25 fusion, rare-term and publisher boosts, confidence signal |
| Query-time geography | [`geo.py`](geo.py) — place detection, honest coverage reporting |
| Web UI + JSON API | [`server.py`](server.py), [`web/`](web) — docs at `/docs` |
| Server-rendered pages | [`pagerender.py`](pagerender.py) — titles, snippets, canonical URLs and schema.org markup for 60,000 dataset pages, plus the browse hierarchy below |
| Data-quality report | [`report.py`](report.py) |
| Relevance regression suite | [`scripts/relevance_test.py`](scripts/relevance_test.py) — 12 cases; **run it before and after any ranking change** |
| Unit tests (no index needed) | [`scripts/dedupe_test.py`](scripts/dedupe_test.py), [`scripts/render_test.py`](scripts/render_test.py) — the rules that decide what search hides, and what gets escaped |
| What people actually search for | [`scripts/query_report.py`](scripts/query_report.py) — over the anonymous query log |
| Change notification | [`scripts/indexnow.py`](scripts/indexnow.py) — announces only the pages whose content actually moved |

Currently indexing **84,000+ datasets from 54 portals** — data.gov.uk, the
ONS Open Geography Portal, London Datastore, NHSBSA, OpenDataNI, Natural
England, the Forestry Commission, NatureScot, Scotland's Spatial Hub, the
North Sea Transition Authority, Historic England, and councils from
Aberdeen to Canterbury, plus the energy networks, the water
industry's shared platform and the UK biodiversity network. The full, live
list is at
[`/api/sources`](https://open-data.org.uk/api/sources).

## Browsing it

Search is one way in; the site is also a plain, crawlable hierarchy, which
matters because a catalogue nobody can link into is a catalogue nobody finds.

| Page | What it is |
|---|---|
| [`/publishers`](https://open-data.org.uk/publishers) | all 1,493 organisations, grouped by initial |
| [`/publisher?name=…`](https://open-data.org.uk/publisher?name=Leeds%20City%20Council) | everything one organisation publishes |
| [`/topics`](https://open-data.org.uk/topics) | 2,088 subjects more than one organisation publishes on |
| [`/topic?tag=…`](https://open-data.org.uk/topic?tag=allotments) | one subject, pooled across every portal |
| [`/who-publishes`](https://open-data.org.uk/who-publishes) | 570 dataset types that three or more organisations each publish |
| [`/who-publishes?name=…`](https://open-data.org.uk/who-publishes?name=Conservation%20Areas) | every organisation publishing that one, and whether their links work |

Every dataset page is reachable in three hops from the home page without
JavaScript, and links back to its publisher, its subjects, and the other
organisations publishing the same thing.

Records with nothing on them — no description, no files, no tags, no formats
(646 of them) — and subjects only one publisher uses carry `noindex` and stay
out of the sitemap. They remain reachable; they're just not put forward as
worth ranking.

## Coverage trackers

Two checklists, both regenerated from the index rather than maintained by
hand, so "what are we missing?" has an answer instead of a guess.

## Council coverage

[COUNCIL_COVERAGE.md](COUNCIL_COVERAGE.md) checks all 361 UK local
authorities from the ONS register against what the index actually holds.
**330 (91%) have data; only 26 (7%) run a data portal of their own that we
harvest** — most reach us through a regional hub or through data.gov.uk.
Wales is the gap: no Welsh council has an own portal or hub here, and ten
have nothing at all.

It regenerates from the index
([`scripts/council_coverage.py`](scripts/council_coverage.py)) and feeds
straight back into discovery — `discover_sources.py --from-councils
--missing-only` probes the councils we hold nothing for, rather than only
the publishers we already have. That found Stirling (578 datasets) and
Brent (310).

### Utilities, transport and roads

[UTILITIES_COVERAGE.md](UTILITIES_COVERAGE.md) does the same for the
organisations running the physical infrastructure — energy networks, water
companies, road and rail operators. There is no register for these, so
[`utilities.yaml`](utilities.yaml) is a curated candidate list built against
the sectors Ofgem and Ofwat license, and
[`scripts/utility_coverage.py`](scripts/utility_coverage.py) probes every
candidate against every catalogue API we can harvest.

Of 36 organisations: **7 run a catalogue we harvest** (~1,300 datasets),
4 serve a real data site with no catalogue behind it, 3 sit behind a
registration gate we deliberately don't try to bypass, and the rest had no
portal at any address we could guess. This sector mostly publishes CSVs
linked from corporate pages, which a person can find and a harvester cannot.

Two of those seven were found only after fixing our own User-Agent. Several
publishers' firewalls refuse any request whose UA contains "discovery" or
"harvester" while waving through the same request calling itself "bot" — so
SSEN was recorded as having no catalogue API while running an entirely
ordinary CKAN. See [`agent.py`](agent.py).

New portals are found deterministically rather than by hand: see
[`scripts/discover_sources.py`](scripts/discover_sources.py), which mines
our own resource URLs for portals we don't yet harvest and probes generated
council hostnames against the API patterns we support.

## Run it

```
pip install -r requirements.txt
python harvester.py            # full harvest (~81k datasets, ~13 min)
python embed_index.py          # embed + build keyword index (CPU, ~40 min first run)
python dedupe.py               # mark duplicates + retired records
uvicorn server:app --port 8000 # UI at /, API docs at /docs
```

Refreshes are incremental — see [`refresh.sh`](refresh.sh) for the cron
job, and the [`Dockerfile`](Dockerfile) for deployment.

## API

Everything the search box does is a public JSON API — CORS enabled, no key
needed, 30 searches/minute per IP. Interactive docs at
[`/docs`](https://open-data.org.uk/docs).

```bash
curl "https://open-data.org.uk/api/search?q=flood+risk+in+brighton&k=3"
```

```jsonc
{
  "confidence": "strong",          // strong | weak | none — is this a real match?
  "geo": {
    "place": "brighton",
    "point": [-0.1508, 50.8465],
    "bbox_matches": 3,             // results whose published boundary covers it
    "in_results": false            // we hold no Brighton-published data for this
  },
  "results": [{
    "key": "data_gov_uk:...",      // stable id, for /api/dataset
    "title": "Risk of Flooding from Rivers and Sea",
    "publisher": "Environment Agency",
    "source": "data_gov_uk",
    "license": "OGL-UK-3.0",       // null when the publisher states none
    "formats": ["SHP", "ZIP"],
    "modified": "2026-04-24",
    "availability": "data",        // data | api | webpage | dead | blocked
    "covers_place": true,          // its published boundary contains the place
    "columns": ["..."],            // CSV headers, where we could read them
    "url": "https://www.data.gov.uk/dataset/..."
  }],
  "attribution": "Contains public sector information licensed under the OGL v3.0 ..."
}
```

Also `GET /api/dataset?key=...`, `GET /api/stats`, `GET /api/sources`, and a
machine-readable spec at [`/openapi.json`](https://open-data.org.uk/openapi.json).
Please keep the `attribution` field when republishing results.

**Paging.** `k` returns up to 50; add `offset` (max 200) to page further.
Responses carry `offset` and `available` — how many ranked candidates exist
for that query, so you know when to stop.

**Rate limiting.** 30 requests/minute per IP. Every response carries
`X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset`, so you
can pace yourself rather than discover the limit by hitting it; a 429 also
carries `Retry-After`. The count is kept per server process, so in practice
you'll often get more headroom and `Remaining` can jump between responses —
stay under 30/min and you'll never be limited; above that is luck, not a
contract. If you need more than that, don't scrape us — the
whole index is rebuildable from this repo in about an hour, or
[open an issue](https://github.com/dominicm2023/open-data-uk/issues) and
let's talk.

**Filtering.** Four optional filters, comma-separated, AND between fields and
OR within one:

```bash
# recycling data you can actually load, as a spreadsheet
curl "https://open-data.org.uk/api/search?q=recycling+rates&availability=data,api&format=CSV"
```

| Filter | Values |
|---|---|
| `availability` | `data`, `api`, `webpage`, `dead`, `blocked`, `nofiles`, `unchecked` |
| `format` | normalised format names — `CSV`, `XLSX`, `GEOJSON`, `SHP`, `WMS`… |
| `license` | as returned in `license`, e.g. `OGL-UK-3.0`; `none` for the third that state none |
| `source` | portal ids from [`/api/sources`](https://open-data.org.uk/api/sources) |

Filters apply after ranking and before paging, so `available` stays an honest
count of what you can page through, and the surviving results keep the order
they had. The response echoes back the filters it applied, so a mistyped value
shows up as `filters` rather than as a mysteriously empty page.

**Not there yet:** no bulk export endpoint. If you want one, say so in an
issue — knowing what people actually need beats guessing.

## Contributing

The most valuable contribution is a new data source — one YAML entry.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

The **code** in this repository is MIT licensed — see [LICENSE](LICENSE).

The **data it indexes is not ours to license.** Each dataset stays under
whatever licence its publisher set, most commonly the Open Government
Licence v3.0, and around a third state no licence at all. We only ever hold
metadata and link out to the publisher, so check the licence shown on a
dataset (and on the publisher's own page) before reusing it. API responses
carry an `attribution` field for this reason; please keep it.

## Roadmap

Verified-but-not-yet-harvestable portals are tracked in
[PLATFORM_BACKLOG.md](PLATFORM_BACKLOG.md) — roughly 7,000 datasets behind
three adapters. Next up:

- **An MCP endpoint**, so other people's AI tools can query the index
  directly — the cheapest way to make UK open data visible to assistants.
- **Change alerts** — tell me when this dataset updates, goes stale, or
  disappears. Nobody offers this and the harvester already detects it.
- **Metadata enrichment** for the third of datasets with no stated licence
  and the many with unusable descriptions — clearly marked as inferred,
  never presented as harvested fact.
- **A settlement-level gazetteer.** Place lookup currently resolves local
  authorities, so "Hackney Wick" doesn't geocode.
- **Series grouping and a reranker** — annual editions currently appear as
  separate results.
