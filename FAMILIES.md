# Dataset families — the brief

Written 6 September 2026. This is the handover for building the index's
third promise; see `NORTH_STAR.md` for why.

## The promise being added

"Really there" has three levels: there is a link; the link works; and a
person can actually use what is behind it. The first two are done. The
third is this: **for the things many bodies publish, one combined,
attributed table, beside every original link.**

The unit of work is a **family** — a kind of dataset that many public
bodies publish separately (the `/who-publishes` pages list them: 102 bodies
publish *Conservation Areas*, 227 an organogram, dozens spend-over-£500 and
senior salaries). Digestion is a craft done per family: a publisher-layout
adapter, one schema, a review. It is not a pipeline switched on for 110,000
datasets. Codex's 100-record trial measured exactly that: 92 attempted, 68
yielded tables, 47 were clean-shaped, **4 reached a reviewed schema**.

## The rule: a provenance ladder, and only the top rung publishes

```
fetched  →  extracted  →  shape-checked  →  mapped  →  reviewed  →  published
```

Everything below *reviewed* is private evidence, kept by hash. A row on the
site carries: source URL, source file SHA-256, page/sheet/row, licence
evidence hash and URL, adapter version, and the attribution the licence
requires. If a source file's hash changes, its rows fall back to *mapped*
until someone looks. Missing stays null; a band limit is never relabelled
actual pay; nothing is annualised, inflated or harmonised silently. The
North Yorkshire pilot's `review_issues.csv` is the model: a discrepancy is
recorded and published *as a discrepancy*, with the publisher's figure
preserved.

## Licence: explicit or nothing

Admit a source only on an Open Government Licence stated unambiguously on
the record or resource. Custom, restrictive, unknown, conflicting or missing
terms do not pass. Resource-level restrictions override dataset-level
permission. Save the licence evidence by hash at fetch time. The combined
table carries the attribution line OGL requires, naming every contributing
publisher.

**Why "unambiguously" and not "with a version" (changed 6 September, first
full run).** The first rule required an explicit version and refused 32 of
60 spend-over-£500 returns on data.gov.uk's own identifier — `license_id`
`uk-ogl`, url `reference.data.gov.uk/id/open-government-licence` — which
names the OGL and no version. The National Archives states that material
licensed under any earlier OGL version may be used under the v3 terms; the
versions are compatible by design. So a versionless OGL is not an unknown
licence, it is the OGL, and the thing admission must establish is that the
statement *is* the OGL rather than a custom or restrictive licence. That
test is unchanged. The exact statement is kept as evidence and the version
recorded as stated, or "unstated (v3 terms apply)".

**The gate reads prose (changed later on 6 September).** ArcGIS `licenseInfo`
is a paragraph, not an identifier, and the first gate refused thirteen
councils for saying "Contains OS data © Crown copyright" or "supplied under
the Open Government License v3.0" in front of an OGL link. The rule now: a
statement that names a restricted or non-OGL licence (INSPIRE end-user
terms, OS PSMA/PSEUL, "derived data exemption", non-commercial, Creative
Commons) refuses, even with the OGL beside it — mixed terms need a person.
Otherwise it must name the OGL by URL or by name. OS attribution wording is
a condition the OGL allows, not a restriction. Every refusal now keeps its
evidence by hash, so the next widening can be argued from wording too.

**Mixed statements, read by a person (7 September).** Dominic read the
refused statements and decided: a statement that *names the OGL* is the
OGL even when it also mentions the Ordnance Survey mapping the data was
derived from ("derived data exemption", "Presumption to Publish", PSEUL,
INSPIRE end-user terms, "OS Licensing") or a portal's catalogue of every
licence it uses (Stirling's page, which also lists the Non-Commercial
Government Licence). Those words are recorded as `mixed` on the licence
and shown beside the body on the family page; the OS acknowledgement line
is kept verbatim and travels in the attribution. CC BY (plain) is open and
OGL-compatible and is accepted as itself (Northern Ireland Office). A
dataset-level field that is only an OS/LGIH acknowledgement is accepted for
a portal listed in `PORTAL_LICENCE` with the reason (Bristol: its datasets
harvested to data.gov.uk are `uk-ogl`). Still refused whatever else is
said: no derivatives, all rights reserved, CC NC/ND/SA. Still refused
without an OGL beside them: PSMA-only terms (Sheffield on data.gov.uk — the
PSMA licenses the council, not the public; only a derived-data release
under the OGL reaches us), INSPIRE end-user licences on their own
(Sheffield's hub), OSNI basemap copyright with no licence (Mid & East
Antrim), "no restrictions on public access" (an INSPIRE access constraint,
not a licence — Transport for West Midlands, left for now).

**Personal data is a separate decision from licence.** OGL excludes it.
Senior-salary returns name people by statute; republishing those names in a
combined table is a choice for Dominic, not a consequence of the licence.
The first three families below contain no personal data. Salaries and
organograms wait until that position is settled.

## Politeness: fix before anything scales

The pilot ran at four requests a second to one host and Brent answered 429.
Before the next fetch:

- per-host spacing of **1.5 s**, the same as `checker.py`;
- honour `Retry-After`; on 429/503 back off and record it — a rate limit is
  visible as "last attempt refused", never as "data gone";
- a retry budget per host per run; the last *successful* snapshot is kept
  separate from the latest *attempt*;
- the honest User-Agent from `agent.py`, unchanged.

Never probe registration-gated sources (Network Rail, TfL, CQC); listing
that they exist is on-star, fetching from them is not.

## Where the code goes

`pilot/` moves into the index repo as **`families/`** — it is now product,
not trial:

```
families/
  run.py, extract.py, ...      the intake (from pilot/), with the pacing above
  registry/<family>.json       sources per family: dataset keys from the index,
                               the chosen resource, its licence evidence
  adapters/<family>/           the mapping to the family schema, versioned
  schema/<family>.json         the columns, units, and what null means
  README.md                    how to add a family; the ladder; the tests
```

The `.venv` stays the index's. Storage: a separate SQLite file under
`data/families.db`, never inside `index.db`. The 100-record trial retained
92 MB; a family is small. Keep the pilot's byte budgets and free-disk
reserve.

Serving: a `/family/<name>` page (server-rendered, like everything else) with
the combined table's summary, the download, the provenance ladder state per
contributing source, and every original link. A `/api/family/<name>` JSON
and `.csv` endpoint. The `/who-publishes/<name>` page links to it when one
exists. Self-contained pages, CSP-compliant, no third-party requests.

## The first three families

Chosen because a reviewed mapping already exists, no personal data, and
obvious cross-council value:

1. **Household waste recycling centres** — Durham and North Yorkshire are
   already unified across two portals (31 locations). Extend to every
   council that publishes one. Schema: site, address, postcode, easting/
   northing or lat/lon with CRS stated, accepted materials if published,
   observation date.
2. **Air quality annual means** — Leicester mapped (184 site-years,
   1994–2023). Dozens of councils publish the same shape. Schema: site,
   pollutant, year, annual mean, unit, data capture %, site type.
3. **Spend over £500** — the family Joined Up's supplier work already
   depends on. Schema: body, date, supplier (as published — variant
   matching is eyeballed, never automatic), amount, expense area, reference.
   No supplier is renamed without a person confirming the variant.

Do them in that order; each proves something the next needs (multi-portal
union → time series → high volume).

## Measure

`NORTH_STAR.md` gains a fifth measure, **usability**: who-publishes families
with a reviewed, published combined table. Report per family: contributing
bodies / bodies that publish it; rows; the ladder state of every source;
review time; corrections after publication.

## Joined Up

Consumes the family tables through `/api/family/…` like anyone else. The
index digests and presents; Joined Up reads and argues. Nothing of Joined
Up's is served from here.

## What stays true

Every claim ships with its query. Nulls are published as findings. Named
companies require eyeballed variant matches. Nothing is published outward
without Dominic's approval per item. Pages are self-contained. And the
original link is always there, first.

## Status, 6 September 2026

Built and live. `families/registry.py` → `intake.py` → `brief.py` → (proposals)
→ `check_mappings.py` → `build.py`; served by `familypage.py` at
`/family/<name>` and `/api/family/<name>[.csv]`; nightly in `refresh.sh`.

| family | registry | extracted | reviewed & published |
|---|---|---|---|
| recycling_centres | 30 sources | 18 | 13 sources, 98 rows, 12 bodies |
| air_quality_annual | 56 + 5 national networks | 39 | 22 sources, ~55,000 rows, 10 bodies (AURN, LMAM, Scotland, Wales, Northern Ireland; 1990-2026) |
| brownfield_land | 176 sources / 129 authorities | 62 | (being published 8 September: the 2017 standard maps most files by name) |
| spend_over_500 | 212 (every edition) | 76 | 68 sources, 4,259,913 rows, 27 bodies (about 1,000 files across the series; 125 registry sources are dead 2010-16 links) |

Held in review, not published: Bradford's diffusion tubes (nothing in the
file, title or description names the pollutant); Perth & Kinross (mixes
recycling centres with bring banks and the mapping cannot filter rows);
National Highways' NAQMN PM10/PM2.5 columns (one pollutant per mapping).

Things the first day taught, now rules in the code: Northern Ireland bodies
publish on the Irish Grid or Irish Transverse Mercator, never BNG, and the
easting tells the two apart; a publisher's malformed postcode is nulled with
a note rather than costing the row; a year column can hold a reporting
period ("2010/2011") and is kept as the first year with a qualifier; a
published annual mean of exactly 0 is a placeholder; concatenated monthly
returns repeat their header and drop one-cell dividers; data.gov.uk
resources marked CSV are often HTML pages, so the intake tries ranked
candidates; and a source's last good snapshot outlives a failed re-fetch.

Second-day rules, now in the code: a series file's header chooses its
layout by names, and only when that layout holds most of the file's rows do
the other fitting layouts get a turn (Wirral's December 2025 return lists a
date column its rows do not carry; the rows that result say so in
`quality_note`). A number is a number only when nothing but a unit follows
it (`08-MAY-2024` is not 8). Currency prefixes (`$1,145.00`, an Excel
artefact in Wales Office files) are formatting. Line breaks inside a cell
are collapsed. The brief finds the real header row past a title line, so
the checker knows every layout of a series. Reviewer decisions live in the
mapping's `notes` after "Review <date>:" and show on the family page.

The page (7 September): `/combined` is the hub; each family page draws
itself from `summary.json` → `facets` (computed by `build.py` over every
published row): a dot map on the embedded UK outline (`families/ukmap.py`,
Natural Earth, no tiles), a body-by-year grid, a computed Q&A, and a
filled-bar per column. Filters (body, year, pollutant, a word) go to
`/api/family/<name>[.csv]?body=&year=&q=`, answered from
`<family>.sqlite`, written at build beside the CSV; a filtered CSV streams
every matching row. Dates: `_date` reads `15-Dec-11`, `11-MAR-2026`,
`10/01/2014 00:00` and Excel serials; a file whose unambiguous dates are
month-first is read month-first throughout and its rows say so in
`quality_note`.

Mappings can now `filter` rows: `{"column": "Type", "match": "<regex>"}`
keeps only rows whose cell matches (York's two waste sites among 51 bring
banks; Perth & Kinross's CENTRE rows among POINTs); the count skipped is
said on the page. A series fetches every *file* of a dataset, not every
*format* of one file (ArcGIS item ids are deduplicated). An ArcGIS Hub
export that answers "being generated, check back later" is retried,
politely, and never mistaken for a table. Accounting brackets,
"(2,586.20)", are credits and read as negative.

Widening the registry (7 September, evening): the title pattern now finds
"Payments to suppliers with a value over £500 from …" (the LGA's own
title), "Expenditure report", "Payments to Suppliers"; 187 sources where
there were 60. Of the 127 new, 54 extracted, 9 had no licence, and most of
the rest are departmental records from 2010-16 whose files are gone. The
extractor reads .xls (xlrd) and falls back to latin-1 for a CSV cp1252
cannot decode; the file cap is 80 MB (25 MB dropped Camden's export).
Reviewer decisions of note: £25,000 returns (ICBs, Ofsted) are a different
series and are rejected; a return of *all* payments carries
threshold_gbp 0; procurement-card (GPC) layouts inside MHCLG's bundles are
removed so those files hold; a layer's GeoService twin is never a second
file of a series; North Ayrshire's 2023-24 export lists every payment
twice, once without an amount.

**The national networks (7 September, night).** The annual means that
matter most are not in any catalogue: the AURN, the local-authority
network sites Defra hosts (LMAM), and the Scottish, Welsh and Northern
Irish networks publish them on their own sites as the files openair reads
(`summary_annual_<NET>_<year>.rds`, one per year, a row per site with
`<POLLUTANT>.mean` and `.capture`; a metadata file with coordinates, site
type and how far each site is ratified). `families/networks.py` fetches
them politely, keeps them by hash, unpivots them into the schema and
build.py appends them with the same receipts. Admitted: AURN and LMAM
(uk-air.defra.gov.uk states the OGL and the attribution line "© Crown
copyright Defra via uk-air.defra.gov.uk…", carried on every row) and
Northern Ireland (OGL v3 in the site footer); Scotland (its About page:
"use and re-use the information featured on this website … under the
terms of the Open Government Licence", version unstated); Wales, on its
own terms ("freely available for public use, with acknowledgement of this
web site as the source" — not a named licence; accepted by Dominic on 7
September, the acknowledgement carried on every row). Parked with the
reason on the page: Air Quality England (no terms found; the sites are
councils'). Rows past a site's ratified date, or under 75% data capture,
say so in `qualifier`. Pollutants: NO2, NO, NOx, O3, SO2, CO (mg/m³),
PM10, PM2.5 (gravimetric marked); hydrocarbons not taken.

**Editions and twins (8 September).** A series family's registry now
takes every edition of a dataset (Leicester's 2015-2021, Stirling's
2019-2023, Tunbridge Wells' 2014-2023: sixteen years, mapped by cloning
the reviewed sibling's mapping where the headers match). The same run
showed that a file fetched in two formats had been two files — Leicester
lists every year as `.csv` and `.json`, MHCLG every month as `.csv` and
`.xls`, Opendatasoft names both `…/exports/csv` and `…/exports/json` —
and 104 such twins had doubled those bodies' rows. A series keeps one copy
of each file, named by the path segment that names it. The storage budget
is 10 GB (2 GB was reached and fetches failed silently as "previous
snapshot kept").

**The fourth family: brownfield land registers (8 September).** Chosen
because publishers were told what columns to use: the 2017 Brownfield
Land Register data standard. The registry found 176 datasets from 129
planning authorities; 62 extracted (79 dead links, 35 refused on
licence). 53 of the 62 use the standard's own header names and were
mapped by the standard without a model (`scratchpad/brownfield_propose.py`
became the rule: SiteReference, SiteNameAddress, Hectares, OwnershipStatus,
PlanningStatus, PermissionType/Date, MinNetDwellings /
NetDwellingsRangeFrom/To, Deliverable, HazardousSubstances, SiteplanURL,
FirstAdded/LastUpdated, GeoX/GeoY); the nine with their own or
shapefile-truncated headings went to an agent. Things learned: an
authority publishes the same register on two portals (five duplicates
rejected, newest and fullest kept); GeoX/GeoY hold degrees as often as
metres and two councils swap them (the build reads both); the CSV
sniffer's quoting guesses split every address with a comma and shifted
the columns after it — the sniffer is now trusted for the delimiter only.
One row is one site on the authority's register as last published.

## The loop from here

Nightly, `refresh.sh` rebuilds each registry from the index, re-fetches
politely (a source's last good snapshot survives a failed attempt), and
rebuilds the tables from reviewed mappings. New sources arrive as
`extracted` and appear on the family page as "not in the table yet". To
bring them in: `brief.py <family>` → propose mappings (a model can; the
brief is headers and sample rows) → `check_mappings.py` → build with
`--include-proposed`, look at the preview → set `"status": "reviewed"` in
`families/registry/<family>.mappings.json`. That last edit is the publish
switch, and it is a person's.

A file that changes column layout between blocks (DFID's 2012 return has
three) takes `"alt_columns"`: further column dicts; a row carrying most of
a layout's names switches the build to it. A row with nothing in any
mapped column is padding and is skipped.

Known gaps worth doing next: one file per dataset is fetched, so a spend
return is one month of one body — fetching every monthly file makes it a
series; DFID-style files that change header layout mid-file need a second
mapping per block; ArcGIS hosts that refuse the REST query (Bristol) need
the export endpoint instead.
