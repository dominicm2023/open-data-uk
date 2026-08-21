# Data pipeline audit — harvester.py, normalise.py, dedupe.py, checker.py

Adversarial review, local only. Every count below is from the local `index.db`
(106,609 datasets, 342,075 resources, 52,272 checks) on 2026-08-21. Ranked by
user impact.

---

## 1. opendata.scot: every one of its 2,467 datasets has zero resource rows; 536 have a broken landing link

**Code:** `harvester.py:379-384` vs `harvester.py:318-329`.

`normalise_dcat_dataset` keys a record on `ds.get("identifier") or landing`,
where `landing = _dcat_landing(ds)` (falls through to a distribution URL) or,
failing that, a synthetic `sha1:` id. But the resource-linking loop rebuilds
the ident as `ds.get("identifier") or ds.get("landingPage")` — the *raw*
field, not `_dcat_landing`. opendata.scot's feed carries neither `identifier`
nor `landingPage` (sources.yaml says so itself), so the loop `continue`s on
every record and no resources are ever written.

```sql
SELECT CASE WHEN ckan_id LIKE 'sha1:%' THEN 'sha1' ELSE 'url' END, COUNT(*),
       SUM(NOT EXISTS (SELECT 1 FROM resources r WHERE r.dataset_key=datasets.key))
FROM datasets WHERE source_id='opendata_scot' GROUP BY 1;
-- sha1 | 536  | 536 no resources
-- url  | 1931 | 1931 no resources    (all 2,467 of the source)
```

Consequences, all verified:
- 1,931 records have `resource_count > 0` so they can never become `nofiles`,
  and with no resource rows the checker can never reach them: the whole
  source is frozen at `availability = 'unchecked'` forever.
- Second bug in the same path: `harvester.py:329` `landing = landing or ident`
  writes the literal synthetic id into `landing_url` — 536 dataset pages link
  to `sha1:dd85adc455c4b78f` instead of a URL.
  `SELECT COUNT(*) FROM datasets WHERE landing_url NOT LIKE 'http%'` → 536,
  all opendata_scot.

## 2. Checker files direct CSV downloads under "api" — availability lies for ~2,200 datasets and will get worse nightly

**Code:** `checker.py:138-140` — `classify()` tests `API_HINTS` (which
includes `"/api/"`) *before* looking at the content type.

Every OpenDataSoft export (`/api/explore/v2.1/.../exports/csv`) and every
ArcGIS Hub download (`/api/download/v1/items/.../csv`) matches `/api/` even
when the response is `text/csv`:

```sql
SELECT COUNT(*) FROM resource_checks WHERE verdict='api' AND content_type LIKE 'text/csv%';        -- 1,563
SELECT COUNT(*) FROM resource_checks WHERE verdict='api' AND (content_type LIKE 'text/csv%'
  OR content_type LIKE '%spreadsheet%' OR content_type LIKE '%geo+json%'
  OR url LIKE '%/exports/csv%' OR url LIKE '%/download/v1/items/%');                               -- 3,496
SELECT COUNT(*) FROM resource_checks WHERE url LIKE '%/api/explore/v2.1/%/exports/%';              -- 782, ALL verdict='api'
SELECT COUNT(DISTINCT r.dataset_key) FROM resources r JOIN resource_checks c ON c.url=r.url
JOIN datasets d ON d.key=r.dataset_key WHERE d.availability='api' AND c.verdict='api'
AND (c.content_type LIKE 'text/csv%' OR c.content_type LIKE '%spreadsheet%'
     OR c.content_type LIKE '%geo+json%');                                                          -- 2,162 datasets
```

Leicester's ODS portal is the cleanest receipt: all 393 checked datasets show
`availability='api'` although their resources are literal CSV/JSON exports.
Sample check rows: `https://opendata-daerani.hub.arcgis.com/api/download/v1/
items/a818bd537d854296851186fcb1df2090/csv?layers=5`, status 200,
`text/csv`, verdict `api`.

Knock-on: CSV column peeking only runs when verdict is `data`
(`checker.py:202`), so none of these ever get column names in search either.
The backlog guarantees growth: 63,444 rows in `resources` are AGOL
`/api/download/v1/items/` URLs waiting to be checked.

## 3. Retired canonical + duplicate collapse = 553 live datasets invisible everywhere

**Code:** `dedupe.py:111-117` (`rank()` ignores retired status when electing
the canonical copy) + `search.py:397-402` (`canon = dups.get(key, key); if
canon in retired: continue` — the *whole group* is dropped) +
`server.py:773-774` and `server.py:868-870` (subject pages and the sitemap
exclude both duplicates and retired rows).

```sql
SELECT COUNT(*) FROM duplicates dup
WHERE dup.canonical_key IN (SELECT key FROM retired)
  AND dup.key NOT IN (SELECT key FROM retired);   -- 553 (550 on data_gov_uk)
```

A live, non-retired record whose elected canonical happens to carry the
"this record has been retired" note is unreachable by search, by subject
pages, and absent from the sitemap. Typical victims: Environment Agency
"Water Body ..." series where the retired cycle-1 record won the election
(more resources / newer `modified`) over the live copy. Related smaller
variant of the same election blindness: 9 groups where the canonical is
`dead` while a hidden copy is verified `data`.

## 4. Dedupe false merges: the fallback publisher counts as "same organisation", and the noise list eats real names

**Code:** `dedupe.py:75-88` (`mergeable`), `dedupe.py:57-62`
(`_PUBLISHER_NOISE`), plus every harvester's `publisher or src["name"]`
fallback (`harvester.py:288, 433, 947, 993`).

a) When we invented the publisher ourselves (source-name fallback), the
"publishers match outright" branch merges records that merely share a title:

```sql
SELECT COUNT(*) FROM duplicates dup JOIN datasets a ON a.key=dup.key
JOIN datasets b ON b.key=dup.canonical_key
WHERE a.source_id=b.source_id AND a.publisher=b.publisher
  AND a.publisher IN (<source names from sources.yaml>);   -- 2,473 pairs
```

NBN Atlas alone contributes 492 pairs, and they are provably distinct
datasets: 13 different registry entries literally titled "1" collapse onto
`nbn_atlas:dr3979`, 10 titled "a", 14 titled "bird". DataMap Wales adds 159
pairs among unattributed layers that may come from different Welsh bodies.

b) `_PUBLISHER_NOISE` contains "london", so `who("Transport for London")` =
`{transport}`, which is a subset of `who("Department for Transport")` =
`{department, transport}` — and the aggregator bridge merges them:

```sql
-- data_gov_uk:47f0a282-3356-4530-8e7b-f67aaf4bec63 (publisher: Department for Transport)
-- is marked duplicate_of agol_transport_for_london:1b72598c29a54ddea2de89f3499cd8b9_11
-- (publisher: Transport for London), title 'Cycle Routes'
```

DfT's national record is hidden behind TfL's London-only layer. Same
mechanism: Calderdale MBC's record absorbed by "Citizens Advice Calderdale"
(a charity, not the council); "North Yorkshire Fire and Rescue" merged with
North Yorkshire County Council (6 pairs); "Public Health Plymouth" with
Plymouth City Council (6 pairs). The blank-publisher variant
(`norm(None) == norm(None)` → mergeable) has **zero** live instances — that
axis is clean.

## 5. Records deleted at the portal are never removed: 2,112 ghost rows

**Code:** `harvester.py:171-184` — the pipeline only UPSERTs; nothing
anywhere deletes a dataset row that stopped appearing at its source.

```sql
WITH latest AS (SELECT source_id, MAX(harvested_at) mx FROM datasets GROUP BY source_id)
SELECT COUNT(*) FROM datasets d JOIN latest l ON l.source_id=d.source_id
WHERE substr(d.harvested_at,1,10) < substr(l.mx,1,10);   -- 2,112
-- data_gov_uk 1,926 · nhsbsa 181 · london_datastore 4 · datamillnorth 1
```

Cross-check: data_gov_uk's latest run stored 59,736 but the table holds
61,661; nhsbsa's latest run stored 2,069 vs 2,250 held (181 rows frozen at
2026-07-31). These ghosts stay in search, subject pages and the sitemap
indefinitely, pointing at portal pages that will 404.

## 6. Key collisions silently overwrite 48 records per harvest, and the stats hide it

**Code:** `harvester.py:318-325` — DCAT ident falls back to a landing/
distribution URL or `sha1(publisher|title)`. Two distinct datasets with the
same publisher and title (or the same landing URL) produce the same key; the
second UPSERT overwrites the first.

```sql
-- latest run per source: reported harvested vs unique keys actually written
-- opendata_scot: harvested 2,507, keys written 2,467  -> 40 records lost
-- lambeth 2, glasgow 2, wigan 1, edinburgh 1, causeway_coast 1  (DCAT id reuse)
-- total: 48 (data_gov_uk's 1 is likely page-shift, not loss)
```

`harvest_runs.harvested` records the pre-collision count (2,507), so the
"stored" figure the pipeline reports disagrees with the table by 40 and
nobody is told.

## 7. Licence normalisation gaps: 752 distinct license_norm values where ~20 canonical ids should exist

**Code:** `normalise.py:355-382` — anything unmatched is passed through as a
sub-60-char chip; `harvester.py:915-918` filters "other/none/unknown" but not
"custom".

```sql
SELECT COUNT(DISTINCT license_norm) FROM datasets;                            -- 752
SELECT COUNT(*) FROM datasets WHERE license_norm='custom';                    -- 7,598 (AGOL feeds)
SELECT COUNT(*) FROM datasets WHERE license_norm LIKE '%INSPIRE%'
   OR license_norm LIKE '%End User Licence%';                                 -- 1,170 across 20+ spellings
SELECT COUNT(*) FROM datasets WHERE license_norm LIKE '%...';                 -- 4,684 truncated free-text chips (458 distinct)
SELECT COUNT(*) FROM datasets WHERE license_norm LIKE '%&amp;%'
   OR license_norm LIKE '%&nbsp;%' OR license_norm LIKE '%&lt;%';             -- 242 with raw HTML entities
SELECT COUNT(*) FROM datasets WHERE license_norm LIKE '%CC%BY%'
   AND license_norm NOT LIKE 'CC-BY%';                                        -- 23 unrecognised CC grants
```

Details: "custom" (7,598 datasets) renders as if it were a licence name; the
OS "Public Sector End User Licence – INSPIRE" family splits into 20+ chips
(en-dash vs hyphen vs "?" vs U+FFFD mojibake variants of the same licence);
`norm_license` never unescapes entities ("Data Licensing &nbsp; Data
published by the Council at a ..." is a licence chip on 209+263 datasets);
`_CC_TRIGGER` (`normalise.py:313`) misses "Open Access; CC-BY" because "cc"
is neither at the start nor spelled "creative commons". ~1,100 datasets have
a bare URL as their licence chip. Only exact `notspecified` maps to None
(413 rows correctly nulled) — "No licence" (438) and "unpublished" (344) are
kept as if they were licences.

## 8. "dead" asserted on partial or no evidence

**Code:** `checker.py:281-293` — the availability rollup aggregates *checked*
resources only; `checker.py:188-198` — any exception (DNS, TLS failure, our
own 12s timeout) becomes status 0, and `classify` maps 0 to `dead`.

```sql
SELECT COUNT(*) FROM datasets d WHERE d.availability='dead'
AND EXISTS (SELECT 1 FROM resources r LEFT JOIN resource_checks c ON c.url=r.url
            WHERE r.dataset_key=d.key AND c.url IS NULL);   -- 1,889 of 5,534 'dead' (34%)
SELECT status, COUNT(*) FROM resource_checks WHERE verdict='dead' GROUP BY 1;
-- 0: 2,182 · 404: 1,758 · 500: 302 · 521: 57 ...
```

A dataset with one checked-dead link and four never-checked links is shown as
dead; and 2,182 dead verdicts (half of them) rest on status 0, which bundles
"host gone" with "handshake failed" and "slow". Given the project's own
history (the 429/403 false-dead episode), status-0 deserves its own
"unreachable" state or a recheck lane like `blocked` gets.

## 9. Format normalisation: the ".csv" alias was added, its siblings weren't

**Code:** `normalise.py:444` aliases only `.csv`; `normalise.py:496` then
passes any dotted token through the `[A-Za-z0-9+.\-]{1,20}` gate verbatim.

```sql
SELECT format_norm, COUNT(*) FROM resources WHERE format_norm LIKE '.%' GROUP BY 1;
-- .XLSX 1,151 · .PDF 650 · .XLS 179 · .ODS 88 · .HTML 43 · .ZIP 33 ... total 2,194 resources
SELECT COUNT(*) FROM datasets WHERE formats_norm LIKE '%".%';  -- 382 datasets carry a dot-token
```

`.XLSX` and `XLSX` are separate facets, so a format filter misses these.
Long tail through the same passthrough: `EXEL`, `EXCELL`, `.CVS`, `CVC`,
`VSV`, `HTMLHTML`, `OTHER` (41), `H`, `DO` — noise, but small.

## 10. Two sources are silently dark; one gate silently zeroes whole councils

**Code:** `harvester.py:472-477` — after 3 page errors an ODS source is
abandoned with only a console print; nothing downstream surfaces it.

```sql
SELECT source_id, total_at_source, harvested, errors FROM harvest_runs
WHERE source_id IN ('enwl','spen');
-- enwl: None, 0, 3 · spen: None, 0, 3   (single run each, 2026-08-16; zero datasets ever)
```

`enwl` and `spen` (two DNO energy portals) have never contributed a record.
Also 0 stored in their latest runs: agol_neath_port_talbot (catalogue lists
139), agol_rochdale (71), agol_rushmoor (12), agol_barnet/bolton/
buckinghamshire — the `require_description` gate can eat a source whole and
the run log is the only witness.

## 11. Junk titles pass the quality gate

**Code:** `normalise.py:34-42` — `norm_title` rejects only empty and "{{".

```sql
SELECT COUNT(*) FROM datasets WHERE source_id='nbn_atlas' AND LENGTH(TRIM(title))<=3;  -- 153
-- 'bird' x14, 'INNS' x14, '1' x13, 'a' x10, 'James' x10 ...
SELECT COUNT(*) FROM datasets WHERE LENGTH(TRIM(title))<=2;                            -- 91 corpus-wide
```

These are search results and sitemap pages titled "1" and "a", and they feed
finding 4a's false merges.

## Minor / latent (verified, low current impact)

- `dataset_geo.reference_date` is stored unnormalised (`harvester.py:49`,
  `normalise.py:215-232`, geonode path `harvester.py:1147`): 2 rows read
  "0201-07-14". Everything else in that column parses.
- CSW `--limit` trims `rows`/`keys` but not `res_rows`
  (`harvester.py:625-627`) — would write orphan resources; prototyping flag
  only, 0 orphans in the current db.
- `harvest_json` stops after one page if a paginated source lacks a `total`
  path (`harvester.py:727`, `len(records) >= (total or 0)`); every current
  `page_param` source configures `total`, so latent.
- CKAN error path skips a whole page (`start += PAGE_SIZE`,
  `harvester.py:209`) — up to 500 records lost per error; all current CKAN
  runs show errors=0.
- 14 titles still carry `&amp;`-style entities and 6 carry tags
  (`norm_title` does no `strip_html`/unescape, unlike descriptions).

## Explicitly clean (checked, nothing wrong)

- Template junk: 0 `{{` remnants in titles, descriptions, publishers,
  license_raw, landing_url, tags, and resource URLs.
- Mojibake: 0 in titles and publishers, 1 residual description; the cp1252
  fix works.
- Referential integrity: 0 orphan `resources` rows, 0 orphan `dataset_geo`
  rows.
- Dedupe blank-publisher merges: 0 pairs.
- Date columns: `created`/`modified` all ISO-shaped, all within 1990..2026;
  no epoch or time-fragment junk survived the 20 Aug sanitisation.
- The Cefas colon-cut regression is gone: all 2,299 Cefas `modified` values
  are full timestamps.
