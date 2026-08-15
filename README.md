# UK Open Data Index

**One search across 75,000+ UK government datasets, from 43 portals.**
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

Three things make it different from searching a catalogue directly:

- **It searches meaning, not just keywords.** Ask in plain English; results
  come back ranked by what you meant, from every portal at once.
- **It tells you whether there's actually data behind the link.** We follow
  every resource link and label it: a verified data file, an API, just
  another webpage, or a dead end. Most catalogue links lead to another page,
  not a download — you find out before you click, not after.
- **It admits what it doesn't have.** No results for your town? It says so,
  instead of quietly showing you Glasgow.

**Metadata only.** We never rehost anyone's data — every result links to the
publisher's own page, under the publisher's own licence.

### What we found building it

Measured across the whole catalogue: **33%** of datasets state no licence,
**40%** haven't been updated in two years, **25%** are duplicate copies of
another portal's entry, and of the links we've verified only **40%** give
you machine-readable data — **36%** just lead to another webpage.

Those numbers are worse than they need to be, and we're careful not to make
them look worse than they are. A publisher whose server blocks our checker
is reported as "not verified", never "dead". A dataset that declares it will
never be updated again isn't counted as neglected. An API endpoint counts as
usable data, not a miss. And a licence recorded in a non-standard field
still counts as a licence — fixing that one bug alone moved the "no licence"
figure from 56% to 33%.

## What's here

| Piece | File(s) |
|---|---|
| Source registry ("registry as code") | [`sources.yaml`](sources.yaml) — add a portal via PR, CI validates it |
| Harvesters (CKAN, DCAT/ArcGIS Hub/Socrata, OpenDataSoft) | [`harvester.py`](harvester.py) |
| Licence/format normalisation | [`normalise.py`](normalise.py) |
| Embeddings + keyword index | [`embed_index.py`](embed_index.py) |
| Duplicate & retired-record detection | [`dedupe.py`](dedupe.py) |
| Link availability verification | [`checker.py`](checker.py) — follows every resource link and reports what's really there: `data` / `api` / `webpage` / `dead` / `blocked` |
| Hybrid search engine | [`search.py`](search.py) — semantic + BM25 fusion, rare-term and publisher boosts, confidence signal |
| Query-time geography | [`geo.py`](geo.py) — place detection, honest coverage reporting |
| Web UI + JSON API | [`server.py`](server.py), [`web/`](web) — docs at `/docs` |
| Data-quality report | [`report.py`](report.py) |
| Relevance regression suite | [`scripts/relevance_test.py`](scripts/relevance_test.py) — 12 cases; **run it before and after any ranking change** |
| What people actually search for | [`scripts/query_report.py`](scripts/query_report.py) — over the anonymous query log |

Currently indexing **75,000+ datasets from 43 portals** — data.gov.uk, the
ONS Open Geography Portal, London Datastore, NHSBSA, OpenDataNI, Natural
England, the Forestry Commission, NatureScot, Scotland's Spatial Hub, the
North Sea Transition Authority, Historic England, and councils from
Aberdeen to Canterbury. The full, live list is at
[`/api/sources`](https://open-data.org.uk/api/sources).

New portals are found deterministically rather than by hand: see
[`scripts/discover_sources.py`](scripts/discover_sources.py), which mines
our own resource URLs for portals we don't yet harvest and probes generated
council hostnames against the API patterns we support.

## Run it

```
pip install -r requirements.txt
python harvester.py            # full harvest (~65k datasets, ~10 min)
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

**Not there yet:** no filtering by source, licence or format, and no bulk
export endpoint. If you want either, say so in an issue — knowing what
people actually need beats guessing.

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

- **A GeoNode harvester**, mainly for DataMap Wales (1,927 datasets). Welsh
  coverage is our weakest geography, so this is the highest-value single
  adapter left.
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
