# UK Open Data Index

One search across the UK's scattered open government data — collated from
national, devolved, regional and NHS portals. We index **metadata only** and
link back to the source; the data itself stays where it's published.

**Why:** the UK's open data is spread across dozens of portals with
inconsistent, often broken metadata — effectively invisible to both people
and AI tools. Measured across the full catalogue: **32%** of datasets state
no licence, **41%** haven't been touched in two years, **24%** are duplicate
copies, and of the links we've verified only **16%** lead to an actual data
file — most lead to another webpage. This project normalises that mess into
one searchable index with an open API, and verifies every link so you know
what's actually there before you click.

We are deliberately careful never to claim a publisher's data is broken
unless we actually got a broken response: if their server refuses our
checker, we report "not verified", not "dead".

## What's here

| Piece | File(s) |
|---|---|
| Source registry ("registry as code") | [`sources.yaml`](sources.yaml) — add a portal via PR, CI validates it |
| Harvesters (CKAN + DCAT/ArcGIS Hub) | [`harvester.py`](harvester.py) |
| Licence/format normalisation | [`normalise.py`](normalise.py) |
| Embeddings + keyword index | [`embed_index.py`](embed_index.py) |
| Duplicate & retired-record detection | [`dedupe.py`](dedupe.py) |
| Link availability verification | [`checker.py`](checker.py) — follows every resource link and reports what's really there: `data` / `api` / `webpage` / `dead` / `blocked` |
| Hybrid search engine | [`search.py`](search.py) — semantic + BM25 fusion, rare-term and publisher boosts, confidence signal |
| Query-time geography | [`geo.py`](geo.py) — place detection, honest coverage reporting |
| Web UI + JSON API | [`server.py`](server.py), [`web/`](web) — docs at `/docs` |
| Data-quality report | [`report.py`](report.py) |

Currently indexing **70,000+ datasets from 39 portals** — data.gov.uk, the
ONS Open Geography Portal, London Datastore, NHSBSA, OpenDataNI, Natural
England, the Forestry Commission, NatureScot, Scotland's Spatial Hub, the
North Sea Transition Authority, Historic England, and councils from
Aberdeen to Canterbury.

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

`GET /api/search?q=...&k=10` — hybrid search with confidence + geography
signals. `GET /api/stats`, `GET /api/sources`. CORS enabled, 30
searches/minute per IP. Retain the `attribution` field when republishing
results.

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

## Roadmap (post-MVP)

- AI discovery assistant (RAG over the metadata) and MCP endpoint
- Dataset change alerts / monitoring
- LLM metadata enrichment for the 56% with no licence
- More harvester protocols: Socrata, ONS API, bare-file sources
- Series grouping and a proper reranker
