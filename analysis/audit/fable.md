# Search-quality audit (local SearchEngine replay) — Fable

Method: ran `scripts/relevance_test.py` as baseline, then replayed all 75 distinct
human-looking production queries from `analysis\queries_prod.db` (197 distinct minus
load test/ratelimit/final/count/flood-risk-test synthetic families), then a
robustness/honesty/ranking/filter battery (~50 extra queries) against the local
`index.db` + `embeddings.npy` via `from search import SearchEngine`. Replay dump:
scratchpad `replay_out.json`; battery script `battery.py`.

**Baseline: `scripts/relevance_test.py` = 12/12 PASS.** The regression suite is green;
everything below is outside its coverage.

Findings ranked by how often real users hit them.

---

## F1 — Aggregator/portal duplicate pairs escape dedupe; both copies burn top-3 slots, aggregator copy often outranks the source portal

- Evidence (index): 2,701 same-UUID groups exist across sources; **716 (26%) have no
  `duplicates` entry at all**. Example pair: `opendatani:a593a0b3-29ef-48f2-b2b2-ceb83d841a3c`
  and `data_gov_uk:a593a0b3-29ef-48f2-b2b2-ceb83d841a3c`, both titled "Inpatient waiting
  times".
- Evidence (queries): replay of logged query family `sussex/brighton hosptial waiting times`
  and probe `inpatient waiting times` → #1 "Inpatient waiting times | OpenDataNI |
  data_gov_uk", #2 "Inpatient waiting times | Department of Health — Hospital Information
  Branch | opendatani". Same for `potholes` (#1/#2 both "Pothole Enquiries"),
  `household waste recycling rates borough` (#1 london_datastore, #2 identical-title
  data_gov_uk copy), `hosptial waiting times` (#1/#2 both "Diagnostic Waiting Times"),
  `defense spending` (#2/#3 same ESRI API twice).
- Root cause: `dedupe.py:75-88` — `mergeable()` demands publisher-name subset agreement,
  but data.gov.uk credits the *portal* ("OpenDataNI") while the portal credits the
  *department* ("Department of Health - Hospital Information Branch"); `who()` sets are
  disjoint, and the shared UUID is never consulted.
- Impact: also inverts the publisher-above-aggregator rule (the data_gov_uk copy ranked
  #1 above opendatani). Hits every NI health query, York, and any portal that data.gov.uk
  re-crawls — waiting-times queries are among the most frequent real queries in the log.

## F2 — Place detection cannot match 3+-word places; gazetteer contains corrupt partial keys; county names missing

- `geo.py:113-133` `detect_place` windows only single tokens and bigrams. **62 gazetteer
  keys have ≥3 words and are unreachable**: "newcastle upon tyne", "kingston upon hull",
  "bath and north east somerset", "blackburn with darwen", "bournemouth christchurch and
  poole", …
- Corrupt bigram keys exist and DO match: gazetteer.json holds **"of london" and
  "of edinburgh"**; logged query `list of london councillors` detected `place='of london'`.
- Observed harm (all local replay):
  - `newcastle upon tyne bin collections` → conf strong, top-3 = Newcastle conservation
    areas / allotments / procurement — **zero bin datasets**; the shorter
    `newcastle bin collections` does better (Mid Ulster litter bins at #2). Full official
    name performs worse than the colloquial one.
  - `kingston upon hull traffic counts` → place detected 'hull' (no coords → no geo arm),
    #1-2 = "Royal Borough of **Kingston upon Thames**" boundary datasets, conf strong.
    Wrong city, 300 km away.
  - `flood management hertfordshire` (logged real query) → no place detected at all
    (Hertfordshire is a county, not a LAD; gazetteer is LAD-only and `MAJOR_PLACES` lacks
    it) → #1/#2 North Lincolnshire flood strategy, Hertfordshire's own row only #3.
- Impact: any user who types a full official place name or a county. High frequency —
  place+topic is roughly a third of the human query log.

## F3 — Bogus UK-wide bounding boxes + multiplicative GEO×dead lets dead, wrong-place datasets take #1

- Logged real query `air quality cardiff` → **#1 "RBC Air Quality Management Areas",
  Rushcliffe Borough Council (Nottinghamshire), availability=dead**, above live Welsh
  air-quality data; conf strong.
- Root cause A: its `dataset_geo` row is `west=-8.655, south=49.9, east=1.79, north=60.85`
  — the whole UK — on a single-borough dataset, so the geo arm "covers" Cardiff.
  3,654 dataset_geo rows (12%) are UK-spanning; 22 sit on borough/district/county council
  datasets (North Kesteven 14, Rother 2, Rushcliffe…).
- Root cause B: `search.py:45-52` — boosts multiply, so GEO 1.45 × dead 0.85 = **1.23 net
  lift for a dead geo-matched result**; the dead-link demotion can never win against the
  geo boost.
- Also observed: `brent parking` (logged) → #1 "Parking Zones" [dead], #2 "Open Spaces"
  [dead, not even parking]. `Liverpool` (logged) → #2/#3 dead.
- Impact: dead links at rank 1 on place queries is the single worst-trust outcome the
  checker was built to prevent.

## F4 — "Strong" label + no banner on place-only garbage: the honesty machinery has a blind spot

When confidence is strong and the place appears somewhere in results, the UI shows no
caveat (`web/index.html:134-140`; geo banner suppressed when `in_results` true). Real
logged queries that hit it:

- `conservation area basildon` → strong; top-3 = `basildon_heca`,
  `basildon_open_space_cemetaries`, `basildon_open_space_countryparks`. The only true
  answer, `basildon_constraints2013_conservationareas`, can't keyword-match — its title
  tokenises to `conservationareas` (df=8, vs `conservation` df=5,812) — and is absent
  from top-5.
- `east sussex SEND rates` → strong (0.589); top-3 = council petitions, NHS trust
  spending, spending over £500. Nothing SEND. (The spelled-out variants find DfE SEN
  data, so the acronym is the failure.)
- `brent councillors` → strong (0.654); top-3 = Brent Council news / offices / "Brent
  Open Data". FTS `councillors AND brent` = **0 rows** — we hold nothing, and say
  "strong".
- `gp appointment availability by surgery` → strong; results are opening times and a
  patient survey, not appointment availability.
- Impact: strong+wrong is worse than weak+wrong; these are exactly the queries where the
  index should say "we don't have this".

## F5 — 1,439 machine-slug titles pollute both ranking and display

`SELECT COUNT(*) FROM datasets WHERE title GLOB '*_*' AND title NOT GLOB '* *'` → 1,439.
They reach top-3 in real queries: `conservation area basildon` #1 `basildon_heca`;
`allotments` #1 `ENV_ALLOTMENTS` (Medway); `article 4 areas` #1 `article_4_areas`
(Swale); `scheduled monuments wales` #3/#4 `PS_SD_HBSMRScheduledMonuments_POLY_CURRENT`.
Underscore-joined tokens don't match user vocabulary (see F4 basildon case), and the
titles are unreadable in the UI. normalise.py doesn't prettify them.

## F6 — Welsh: adjectival and Welsh-language place forms find nothing

- `welsh historic monuments` (logged real query) → top-3 = Historic England field
  monuments (England), Bristol Monuments, NI Sites and Monuments. The index holds
  "Scheduled Monuments", "Cadw Guardianship Monuments" and "National Monuments Record of
  Wales" (all datamap_wales) — none surface. 'welsh' is in no vocab; only 'wales'.
- `scheduled monuments wales` → strong, `in_results=False`, top-5 = City of London,
  Scotland, Cheshire ×2, Craven. The Cadw/DataMap Wales records still don't rank.
- `caerdydd air quality` → weak, Durham/Bristol/Belfast. No Welsh-language aliases
  (caerdydd, abertawe) in gazetteer.json (verified absent).
- Impact: a nation-sized blind spot; DataMap Wales is one of the biggest sources in the
  index (3,967 'wales' matches) yet Welsh phrasing can't reach it.

## F7 — Availability nudge inverts topical ranking

`ambulance response times` (logged real query) → **#1 "South Central Ambulance Service
Spending over £25,000"** [data → ×1.15], above "Ambulance Services, England" quality
indicators [webpage → ×0.97] at #3. A supplier-payments file outranks the actual
response-time statistics because the format nudge + rare-term 'ambulance' boost stack on
a topically wrong result. Same shape as F3: multiplicative stacking lets a
quality-of-file signal beat relevance.

## F8 — Edition series crowd out the whole top-k, stale edition first

- `heritage at risk register` → top-5 = five yearly Historic England editions, ordered
  **2022, 2025, 2023, 2024, 2021**. Nothing else can rank, and the freshest isn't first.
- `onspd postcode directory` → top-5 = five monthly "User Guide" editions (2018-2020) —
  not even the data product. No series collapsing or recency tiebreak exists in
  search.py (score ties are decided by dict order).

## F9 — Non-UK research datasets surface in a UK index

`bird records survey` (logged real query) → #2 "Barro Colorado Island" (Panama),
#3 "Atlantic Forest of Brazil". `battle` (logged) → #1 mongoose mortality in Uganda.
`flood` + availability=data → #4 "Modelled fluvial flood hazard maps in Vietnam".
EIDC/CEDA records harvested via data_gov_uk have no UK-scope gate.

## F10 — Filters: sound, two paper cuts (minor)

Tested availability/format/license/source alone and in combination against `flood` and
`recycling rates`: all verdicts respected, AND-between/OR-within works, `unchecked`
works, counts stay honest, dead-only works. Two paper cuts:

1. Values must exactly equal the normalised strings — `license=ogl` silently returns 0
   (stored value is `ogl-uk-3.0`); no near-miss hint, though the echo of applied filters
   does help.
2. `confidence` is computed pre-filter (`search.py:435-440` vs filtering at :405), so a
   "strong" label can sit above zero filtered results.

## F11 — Knife-edge strong threshold on typos (minor)

`councl spending` → sim 0.556 vs SIM_STRONG=0.55 → labelled strong on visibly degraded
results (Warwickshire "Spending Allocations" #1). One threshold hair separates it from
an honest "weak".

---

## What is genuinely fine (checked, not padded)

- **Baseline suite 12/12.**
- **Typo robustness via the semantic arm is good**: `hosptial waiting times` still
  returns waiting-times data; `brighton hosptials` degrades but is honestly labelled weak.
- **Singular/plural agree** (car park/car parks; allotments/allotment sites).
- **Synonyms mostly agree**: rubbish/waste/refuse/bin collection all return collection
  datasets; lorry/truck half-agree (truck→Fleet Vehicles #1 is a miss but Truck Stops #2).
- **Honesty labels work where the semantic gap is real**: `allotment waiting lists` →
  weak (correct — we have allotment sites, not waiting lists); `asylum hotel spending` →
  weak (correct); `SW1A 1AA` → none; `xyzzy nonsense query` → none.
- **Publisher-above-aggregator holds when metadata is clean**: camden article 4 (#1
  camden portal), defibrillators calderdale (#1 calderdale), leeds air quality (#1
  datamillnorth), recorded flood outlines (EA #1, Rivers Trust copies below).
- **Geo honesty banner fires correctly** for `brighton recycling rates` / `recycling
  rates in brighton` (in_results=False → banner; DEFRA borough table in top-3, brownfield
  regression has not returned).

## Quick-reference: real logged queries with bad outcomes

| Logged query | Outcome | Finding |
|---|---|---|
| air quality cardiff | dead Notts dataset #1, strong | F3 |
| brent parking | two dead results #1-2 | F3 |
| conservation area basildon | slug junk top-3, true answer unfindable | F4/F5 |
| east sussex SEND rates | petitions/spending, strong | F4 |
| brent councillors | zero real data, strong, no banner | F4 |
| welsh historic monuments | England/NI results, Wales data buried | F6 |
| flood management hertfordshire | North Lincs #1-2, no place detected | F2 |
| list of london councillors | place='of london' artifact | F2 |
| ambulance response times | spending file #1 | F7 |
| sussex/brighton hosptial waiting times | NI duplicates pair in top-3 | F1 |
| bird records survey | Panama/Brazil at #2-3 | F9 |
