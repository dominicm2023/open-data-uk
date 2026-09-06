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
| recycling_centres | 30 sources | 10 | 7 sources, 75 rows, 6 bodies |
| air_quality_annual | 51 | 28 | 13 sources, 13,479 rows, 3 bodies |
| spend_over_500 | 60 | 20 | 15 sources, 98,884 rows, 13 bodies (series fetch of every monthly file in progress) |

Things the first day taught, now rules in the code: Northern Ireland bodies
publish on the Irish Grid or Irish Transverse Mercator, never BNG, and the
easting tells the two apart; a publisher's malformed postcode is nulled with
a note rather than costing the row; a year column can hold a reporting
period ("2010/2011") and is kept as the first year with a qualifier; a
published annual mean of exactly 0 is a placeholder; concatenated monthly
returns repeat their header and drop one-cell dividers; data.gov.uk
resources marked CSV are often HTML pages, so the intake tries ranked
candidates; and a source's last good snapshot outlives a failed re-fetch.

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

Known gaps worth doing next: one file per dataset is fetched, so a spend
return is one month of one body — fetching every monthly file makes it a
series; DFID-style files that change header layout mid-file need a second
mapping per block; ArcGIS hosts that refuse the REST query (Bristol) need
the export endpoint instead.
