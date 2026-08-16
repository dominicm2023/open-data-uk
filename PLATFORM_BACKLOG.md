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
| — | — | — | all three attempted; see below |

**A generic JSON adapter, not three bespoke ones.** The differences between
these were entirely *where the fields are*, which is data rather than code,
so `harvest_json()` takes the shape as config under `json:` in sources.yaml
— list path, id/title/licence fields, an optional per-record detail URL.

**NBN Atlas: harvested, 2,955.** Its listing carries no description, licence
or download, but all three are one request away, so the adapter fetches
detail per record. Every record ends up with a real archive download.

**Cefas: attempted and dropped.** The listing gives a title and nothing else,
and `/api/holdings/{id}` returns 403 for all but a handful — holding 5
answers, 100/500/1200/2000 do not. 2,299 records with a title and no
description, licence or file is exactly what the thin-page rule exists to
keep out of the index. Config is written and works; it needs the detail
endpoint opened up, not more code.

**Dept for Business & Trade: attempted and dropped.** 14 datasets whose
titles are slugs (`kings-award-for-enterprise-recipients`) with no
description and no working metadata endpoint — `/versions/latest/metadata`
400s with or without `format=json`. Not worth 14 thin records.

**GeoNode: done.** DataMap Wales (1,927 layers) is harvested — see
`harvest_geonode` in harvester.py. It closed the Welsh *data* gap but not the
Welsh *council* gap: DataMap Wales records four publishers for the whole
catalogue and none of them is a council, so COUNCIL_COVERAGE.md is unchanged
for Wales. Scotland's Spatial Hub, by contrast, names the council on each
dataset. Same kind of platform, opposite provenance habits.

**Suggested next: the two custom APIs** (NBN, Cefas). Biggest counts left
but the worst leverage — bespoke code serving exactly one source each. Worth
doing for the ~5,000 datasets now that the platform adapters are exhausted.

## ArcGIS Hub: the largest pool, and how to reach it

Most UK councils that publish spatial data do it through an ArcGIS Online
organisation with **no catalogue of its own**. There is no CKAN, no DCAT
feed, and the Hub site hostname is a vanity domain that cannot be derived
from anything — Bristol's is `opendata.bristol.gov.uk`, Tunbridge Wells'
is `opendatanew-tunbridgewells.opendata.arcgis.com`. Guessing hostnames will
never find them.

Hub's federated search does know about them:

    https://hub.arcgis.com/api/v3/datasets?filter[region]=GB      370,797
    https://hub.arcgis.com/api/v3/datasets?filter[orgId]=<id>     per org

Two ways to use it, and the second is much better:

- **Sampling** the GB results finds whoever publishes most. 10,000 records
  surfaced 247 organisations, but weighted towards Esri UK (86,260 datasets
  of demo content) and a handful of large councils.
- **Asking by name**, one council at a time, found 54 more in 307 — including
  the only Welsh council with an ArcGIS organisation, which no amount of
  sampling would have reached. `scripts/find_council_portals.py` does this.

Match on **exact** identity. Subset matching credited Devon County Council's
portal to East, Mid, North and West Devon, and handed Neath Port Talbot to
the Port of London Authority.

**An ArcGIS organisation is not a curated catalogue.** It exposes everything
the organisation ever shared: working layers, survey forms, logo graphics. A
10-council pilot returned 12,874 records of which 28% had nothing at all and
only 12% carried a description — titles like "Family Hub Logo form" and
"surveyPoint". Two rules make it usable:

- `require_description: 40` on the source — keep what the publisher bothered
  to describe. It cut 73,278 available records to 11,639, all described,
  none thin.
- Boilerplate detection in the harvester — a description shared by five or
  more records in a source is about the organisation, not the dataset.

Throwing away six sevenths is the right trade. The alternative was doubling
the index with form definitions.

## Real, but nothing survives the quality gate

**Neath Port Talbot County Borough Council** — 139 items in its ArcGIS
organisation, not one of them carrying a description. The gate rejected the
entire source, so it is out of sources.yaml rather than sitting there
yielding nothing every night.

It is tempting to make an exception: Neath Port Talbot would be only the
second Welsh council with a portal, and 139 titles with working service
endpoints is not nothing. But the gate exists because an ArcGIS organisation
shares its working layers alongside its data, and with no descriptions at all
there is no way to tell which of the 139 are datasets. A rule applied
everywhere except where it is inconvenient is not a rule.

If they describe their layers, it qualifies automatically.

## Verified but unreachable from production

| Portal | Datasets | Why |
|---|---:|---|
| SP Energy Networks | 153 | TLS handshake refused from the VPS |
| Electricity North West | 148 | TLS handshake refused from the VPS |

Both are real OpenDataSoft portals. They verify from a UK consumer
connection and fail from our OVH box with `tlsv1 alert internal error` —
server-side, on every TLS version, in curl and Python alike. They are on
OpenDataSoft's eu-1 (Ireland) cluster; the four tenants we harvest
successfully are on eu-central-1 (Frankfurt).

Left out of sources.yaml deliberately. Including them would fail every night
while CI kept passing, because GitHub's runners can reach them and the
machine that does the work cannot — the worst kind of green build. Worth
retrying from a different egress, or asking OpenDataSoft.

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
