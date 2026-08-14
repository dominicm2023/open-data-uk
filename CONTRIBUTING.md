# Contributing

## Suggesting a new data source (the most useful contribution!)

Every portal we harvest is one entry in [`sources.yaml`](sources.yaml). To
suggest one, open a pull request adding an entry:

```yaml
  - id: my_council            # stable slug, lowercase, underscores
    name: My Council DataWorks
    type: ckan                # or "dcat" (ArcGIS Hub feeds etc.)
    api: https://data.example.gov.uk/api/3/action
    web: https://data.example.gov.uk
    dataset_url: https://data.example.gov.uk/dataset/{name}
```

Supported protocols:

- **ckan** — `api` must expose `{api}/package_search`
- **dcat** — `api` is a DCAT-US JSON feed URL. ArcGIS Hub portals expose
  this at `/api/feed/dcat-us/1.1.json`, and **Socrata portals expose it at
  `/data.json`** — so Socrata sites need no special handling, just point
  `dcat` at that URL
- **ods** — OpenDataSoft; `api` is the Explore v2.1 catalogue, e.g.
  `https://<host>/api/explore/v2.1/catalog/datasets`

If you don't know which a portal runs, try `/data.json`,
`/api/3/action/package_search?rows=1` and
`/api/explore/v2.1/catalog/datasets?limit=1` in a browser — or just open an
issue with the portal URL and we'll work it out.

CI validates the endpoint is alive and speaks its declared protocol; a
maintainer then merges and the next scheduled harvest picks it up. If the
portal uses another protocol (Socrata, bare files, custom APIs), open an
issue instead — new harvester types are welcome.

## Running the pipeline locally

```
pip install -r requirements.txt
python harvester.py            # harvest all sources into index.db
python embed_index.py          # build embeddings + keyword index
python dedupe.py               # mark duplicates and retired records
python report.py               # data-quality report
uvicorn server:app --port 8000 # web UI + API
```

`python harvester.py --source <id>` harvests one source; embedding is
incremental (only new datasets are embedded).

## Code contributions

Keep it boring: standard library where possible, no frameworks beyond
FastAPI, comments only where the code can't speak for itself. Run the niche
query tests before and after ranking changes — relevance regressions are
easy to introduce and hard to spot.
