# Verified portals we can't harvest yet

These expose a real, working catalogue API — each URL was fetched and
returned a genuine dataset list (see `scripts/verify_proposals.py`). We have
no harvester for their platform yet: `harvester.py` speaks CKAN, DCAT and
OpenDataSoft.

## Done

| Portal | Platform | Datasets | How |
|---|---|---:|---|
| Camden | Socrata | 646 | **No adapter needed** — see below |
| Leicester | OpenDataSoft | 393 | `type: ods` adapter (Explore v2.1) |

**Socrata needs no Socrata code.** Socrata portals publish a DCAT-US
catalogue at `/data.json`, which the existing DCAT harvester reads directly
— so Camden went in as `type: dcat` pointing at that URL. Any other UK
Socrata portal can be added the same way, with no new code. Worth trying
`/data.json` on any unknown portal before writing an adapter for it.

The OpenDataSoft adapter is genuinely new: ODS exposes its catalogue as
plain JSON (not DCAT), keeps nearly all metadata under `metas.default`, and
lists no resources — data comes from predictable per-format export
endpoints, so `harvest_ods()` synthesises the resource list from the formats
each dataset can export. Licence coverage from it is excellent: 296 of 300
sampled datasets carried a resolvable licence, against ~44% index-wide.

## Remaining

| Portal | Platform | Datasets | Verified endpoint |
|---|---|---:|---|
| NBN Atlas (biodiversity) | custom (bare JSON list) | 2,951 | `registry.nbnatlas.org/ws/dataResource` |
| Cefas (marine science) | custom (paginated `items`) | 2,299 | `data-api.cefas.co.uk/api/holdings` |
| Dept for Business & Trade | custom | 14 | `data.api.trade.gov.uk/v1/datasets?format=json` |

**GeoNode: done.** DataMap Wales (1,927 layers) is harvested — see
`harvest_geonode` in harvester.py. It closed the Welsh *data* gap but not the
Welsh *council* gap: DataMap Wales records four publishers for the whole
catalogue and none of them is a council, so COUNCIL_COVERAGE.md is unchanged
for Wales. Scotland's Spatial Hub, by contrast, names the council on each
dataset. Same kind of platform, opposite provenance habits.

**Suggested next: the two custom APIs** (NBN, Cefas). Biggest counts left
but the worst leverage — bespoke code serving exactly one source each. Worth
doing for the ~5,000 datasets now that the platform adapters are exhausted.

## Not pursued

`environment.data.gov.uk`, `osdatahub.os.uk`, `dataportal.orr.gov.uk`,
`archaeologydataservice.ac.uk` and similar publish real data but have **no
catalogue API** — per-product APIs or a search UI only. Harvesting them
would mean scraping HTML, which breaks silently whenever a page changes.
Better recorded as known gaps than built fragile.

## Adding a platform

1. `normalise_<platform>_dataset()` + `harvest_<platform>()` in
   `harvester.py`, and a branch in `main()`.
2. A `check_<platform>()` in `scripts/validate_sources.py` and an entry in
   its `CHECKS` dict — otherwise CI rejects every source using the new type.
3. Add the source to `sources.yaml` and run `validate_sources.py`.
