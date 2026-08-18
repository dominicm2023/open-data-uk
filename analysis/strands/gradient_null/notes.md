# Strand: The gradient that isn't there (gradient_null)

Chart-ready data for publishing the sewage/deprivation **null** — monitored storm
overflow spills (calendar 2025) vs IMD 2019, England — together with its honesty
layer. Everything here is derived from `analysis\sewage\joined.csv` and the raw
files already on disk; no network was used. Reproduce with `python build.py`
(this directory). Parent analysis and verdict: `analysis\sewage\REPORT.md` —
**"NOT SUPPORTED as an argument"** for the dumped-on-the-poor story; the null
plus the methodological finding are the publishable pieces, and this strand is
exactly that package.

Tier rule note: all strata here are LSOAs (one statistical class), so the
never-compare-across-council-classes rule does not bite; the stratum is stated
on every row anyway (`series` / `decile_label` columns).

## Files

| file | visual | what it is |
|---|---|---|
| `decile_series.csv` | (a) | spills and spill-hours per IMD 2019 decile, absolute and per-LSOA-in-decile, England 2025; two series: `all_england` and the `urban_only` control (RUC 2011 A/B/C) |
| `ambiguity_by_decile.csv` | (c) | per assigned decile: share of overflows with >1 candidate LSOA / >1 candidate IMD decile within 100 m — the honesty layer that must ship with (a) |
| `counterexample_cards.csv` | (b) | 7 verified cards: Wilmslow + 3 more rich-area-heavy examples, 3 poor-area-light examples |
| `card_scan_decile10.csv`, `card_scan_decile1.csv` | (b) audit | every decile-10 / decile-1 LSOA ranked by spills within 5 km of its centroid — the scans the cards were picked from |
| `build.py` | — | the only query; regenerates all of the above |

## (a) The decile series — what the chart shows

England 2025: 14,180 monitored storm overflows, 290,124 counted spills,
1,864,871 spill-hours (totals re-verified in this build against REPORT.md).

- **All England**: an inverted U. Spills per LSOA peak in deciles 5–7
  (11.4–12.8) and are lowest at both ends — 4.77 in the least-deprived tenth,
  6.87 in the most-deprived, 5.43 in decile 2. The deprived half gets ~0.83x
  the spills per LSOA of the affluent half. No gradient toward the poor.
- **Urban-only control** (the rural/urban flag IS on disk — `urban` column of
  `joined.csv`, RUC 2011 A/B/C, denominators from `raw/ruc2011_lsoa.json`):
  deciles 2–9 are essentially flat (4.2–5.6 spills per LSOA); decile 1 is
  modestly higher (6.69) and decile 10 lowest (3.41). Per REPORT.md this is a
  **density** effect — most-deprived urban LSOAs host roughly twice the
  monitored overflows per LSOA of least-deprived ones — while spills **per
  overflow** are flat (15.2–18.6 across all urban deciles; column included).
  The inverted U in the national series is rural composition: rural LSOAs see
  several times the spills per LSOA and skew mid-decile-to-affluent. The full
  rural / coastal / inland strata and the >=90%-uptime sensitivity live in
  `analysis\sewage\REPORT.md`.
- Robustness (from REPORT.md, carried as chart smallprint): pushing every
  ambiguous overflow to its most-deprived candidate LSOA gets the deprived
  half only to 1.15x; to its least-deprived candidate, 0.58x. The band
  straddles 1.0 in every stratum. Nothing resembling a deprivation gradient
  survives any assignment choice — which is also why visual (c) is not
  optional.

## (b) The counter-example cards

Method: anchor = ONS population-weighted centroid of a named LSOA; count
monitored overflows / spills / hours within a 5 km planar radius (EPSG:27700,
no datum transform). Cards were picked from the full ranked scans (shipped as
the audit CSVs) for recognisability and company/geographic spread; place labels
were verified against EA site names inside each circle (`evidence_sites`
column). The prior session's Wilmslow figure **reproduces exactly**: 521 spills
within 5 km of decile-10 LSOA E01018602 (Cheshire East 006C — the same count
as from the WILMSLOW PARK SOUTH CSO point itself, which sits in decile-10
E01018584 with candidate LSOAs E01018584/E01018600/E01018602).

| place (anchor LSOA, decile) | overflows <=5 km | spills 2025 | hours |
|---|---|---|---|
| Wilmslow, Cheshire (E01018602, d10) | 18 | 521 | 3,185 |
| Bath (E01014380, d10) | 106 | 1,812 | 4,296 |
| Harrogate, eastern side (E01027660, d10) | 50 | 945 | 3,194 |
| central York riverside (E01013358, d10) | 68 | 1,929 | 15,793 |
| Margate, Kent (E01024657, d1) | 5 | 8 | 17 |
| north Coventry, Holbrooks (E01009709, d1) | 4 | 2 | 0.2 |
| Edmonton, north London (E01001510, d1) | 3 | 6 | 55 |

Card discipline, non-negotiable:
- These are **selected extremes that illustrate the null; the evidence is the
  decile chart**, not the cards. Say "within 5 km of", never "in". The scans
  show the pattern is not cherry-picked from nothing — the top of the
  decile-10 scan is dominated by Bristol's and Calderdale's affluent LSOAs at
  ~2,000 spills, while 2 decile-1 LSOAs have zero monitored overflows within
  5 km at all.
- Spill counts are the EDM 12–24h counting method; "monitored" matters — a
  quiet card can mean quiet sewers or few monitors nearby (the overflow count
  is on every card so the reader can see which).
- Vintage smallprint on every card: spills calendar 2025; deprivation IMD 2019
  (data mostly 2015–16) on 2011 LSOA geography.

## (c) The boundary-ambiguity figure

Share of monitored overflows with more than one candidate LSOA (and more than
one candidate IMD decile) within 100 m, by assigned decile. All-England:
**51.4%** multi-LSOA, **43.3%** multi-decile — overflows discharge to
watercourses and watercourses are where the boundaries run. New wrinkle worth
the chart: the ambiguity is **worst in deprived deciles** (67% multi-LSOA in
decile 1, 58% multi-decile in decile 2, minimum 35% in decile 6) — dense urban
boundary networks sit exactly where the deprived-end bars would be, so anyone
claiming a precise deprived-end number is standing on the shakiest ground of
all. This figure ships alongside (a), always.

## Caption drafts (Joined Up voice)

### Visual (a) — the decile chart with urban control

1. "We went looking for the sewage class divide. It isn't there — and we're
   publishing that. 290,124 monitored spills in England in 2025, laid against
   the official deprivation index: the curve peaks in middle England and is
   *lowest* in the poorest and richest tenths alike. Monitored spill counts vs
   IMD 2019. No gradient. The water companies are failing everyone with
   remarkable even-handedness."
2. "Everyone 'knows' sewage gets dumped on poor communities. The monitoring
   data says something more damning: it gets dumped on everyone. Spills per
   neighbourhood, 2025, against IMD 2019 — flat-to-inverted-U, with the
   least-deprived tenth actually lowest. The real divide is rural pipes vs
   urban pipes, not rich vs poor. We checked so you don't have to pretend."
3. "Strip out rural England (grey line vs coloured line) and the one honest
   deprivation signal appears — and it's about hardware, not spills: the
   most-deprived urban tenth lives near roughly twice as many monitored storm
   overflows as the least-deprived tenth, but those overflows spill no more
   often than anyone else's (15–19 spills each, every decile). That's a
   Victorian-infrastructure inheritance, not targeted dumping. Precision is
   the point: we say what the data says, and stop."

### Visual (b) — the counter-example cards

1. "Wilmslow — golden-triangle Cheshire, richest tenth of England — had 521
   monitored sewage spills within 5 km in 2025. Margate, poorest tenth: eight.
   If sewage dumping were classist, it's doing it backwards. It isn't classist
   — it follows rivers and old pipes. These pairs are what a null looks like
   on the ground."
2. "Bath, richest tenth: 1,812 spills within 5 km. Riverside York, richest
   tenth: 1,929 — nearly 16,000 hours of them. Holbrooks in north Coventry,
   poorest tenth: two spills, twelve minutes. The sewage scandal is real; the
   'dumped on the poor' framing is not what the monitors show. We'd rather be
   right than tidy."
3. "Four of the most affluent neighbourhoods in England, four of the most
   deprived, same yardstick: monitored spills within 5 km, 2025. The affluent
   four: 521, 945, 1,812, 1,929. The deprived three: 2, 6, 8. Picked as
   extremes, verified one by one — the full ranked list ships with the data.
   The average story is the same (see chart): there is no deprivation
   gradient in England's sewage spills."

### Visual (c) — the ambiguity figure

1. "Honesty layer: half of England's storm overflows can't be pinned to a
   single neighbourhood at all — 51% have more than one LSOA within 100
   metres, 43% more than one deprivation decile. Overflows discharge to
   rivers, and rivers are where the boundaries run. Any chart that assigns
   each spill to exactly one neighbourhood is quietly guessing. Ours shows
   you the guesswork, decile by decile."
2. "The catch nobody prints: the poorest areas are where the map is blurriest.
   In the most-deprived tenth, two-thirds of overflows sit within 100 m of a
   neighbourhood boundary. Whoever tells you a precise deprived-end sewage
   number is standing on the shakiest ground in the dataset. We publish the
   blur with the bars."
3. "One in two of England's monitored storm overflows has more than one
   candidate neighbourhood within 100 metres. That's not a data error — it's
   geography: sewers end at rivers, and rivers are the boundaries. This chart
   is why our headline finding is a proud null, not a precise gradient in
   either direction."

## Provenance

EDM Storm Overflow Annual Return, calendar 2025 (Environment Agency, OGL-UK-3.0);
IMD 2019 File 7 (MHCLG, OGL-UK-3.0); LSOA 2011 boundaries/centroids and RUC 2011
(ONS Open Geography, OGL-UK-3.0). Join mechanics, error bars and the arbitration
against full-resolution boundaries: `analysis\sewage\REPORT.md`. Build
cross-checks performed: decile tables, ambiguity shares, LSOA denominators and
national totals all match REPORT.md; Wilmslow 521 reproduced from two
independent anchors.
