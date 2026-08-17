# Where the sewage meets the deprivation — join note

**Status: workshop note. Verdict at the end. Tier-4 cross-source join; human review required before anything derived from this is published.**

## What was joined

| input | vintage | file | licence |
|---|---|---|---|
| Storm overflow spills (EDM annual return, all English water & sewerage companies) | calendar year **2025** | `raw/EDM_2025_Storm_Overflow_Annual_Return.zip` (Environment Agency) | OGL-UK-3.0 |
| Index of Multiple Deprivation, LSOA rank/decile (File 7) | **IMD 2019** (underlying data mostly 2015-16; population denominators mid-2015) | `raw/IoD2019_File7_scores_ranks_deciles.csv` (MHCLG) | OGL-UK-3.0 |
| LSOA 2011 boundaries, generalised (BGC 20m / BSC 200m) + full-res (BFC, queried server-side) | Dec 2011 | `raw/lsoa2011_bgc.json`, `raw/lsoa2011_bsc.json` (ONS Open Geography) | OGL-UK-3.0 |
| LSOA 2011 population-weighted centroids | Dec 2011 (2022 republication) | `raw/lsoa2011_pwc.json` (ONS) | OGL-UK-3.0 |
| Rural-Urban Classification of LSOAs | RUC 2011 | `raw/ruc2011_lsoa.json` (ONS) | OGL-UK-3.0 |

The vintages do not match: spills are 2025, deprivation is measured as of 2019 (data 2015-16) on 2011 statistical geography. Any published use must carry both dates.

Scotland and Wales are excluded by construction: the EA annual return covers English WaSC operations only (Dwr Cymru appears with 120 EA-permitted sites that are physically in England), and IMD 2019 deciles exist only for English LSOAs. Different nations have incomparable deprivation indices.

## Mechanics and their honest error bars

* Coordinates are OS National Grid references from the EA consents database, parsed to easting/northing. The whole LSOA join runs in EPSG:27700 — **no datum transform touches the assignment**. (WGS84 lon/lat columns in `joined.csv` are convenience output via a Helmert transform, ~5 m accuracy.)
* 14,181 of 14,302 return rows parsed cleanly; skipped: 64 with unparseable duration, 57 with unparseable grid reference. 14,180 land in English LSOAs.
* Assignment method per row is recorded in `joined.csv`. Precedence: full-resolution BFC (server-side point-in-polygon, used for every point where the two generalised boundary sets disagreed or missed), then BGC (20 m), then BSC (200 m), then nearest population-weighted centroid as last resort. Method counts: BFC 1,952, BGC 11,195, BSC 346, centroid fallback 688 (offshore/estuarine points outside the clipped land polygons).
* **Nearest-centroid assignment is dead**: it disagrees with polygon assignment on 38.33% of LSOA codes and 30.95% of deciles. Do not let anyone publish a centroid-joined version of this.
* Generalised boundaries alone are also not good enough at this point density: BGC (20 m) vs BSC (200 m) disagree on 9.23% of deciles — overflows sit on watercourses, and watercourses are exactly where LSOA boundaries run. This is why the disputed points were arbitrated against full-resolution BFC boundaries. Arbitration of 1,654 disputed/missed points: BFC sided with BGC 1,373 times, with BSC 230, with neither 51.
* Residual error where both generalised sets agreed, estimated on a random sample of 300 arbitrated against BFC: 97.99% LSOA-confirmed, 98.99% decile-confirmed.
* Coastal flag: LSOA centroid within 5 km of the repo's ultra-generalised coastline (~1 km tolerance — coarse, disclosed, only used for the coastal/inland control).
* EDM coverage is not decile-biased: mean monitor uptime is ~97% in every decile, and restricting to monitors >=90% operational (13169 of 14180 overflows had EDM operational >=90% of the reporting period) does not change the shape.

## Headline numbers (England, calendar 2025)

14,180 monitored storm overflows, 290,124 counted spills (12-24h counting method), 1,864,871 spill-hours.

### All England

| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |
|---|---|---|---|---|---|---|---|---|---|---|
| LSOAs in stratum | 3284 | 3284 | 3285 | 3284 | 3285 | 3284 | 3284 | 3285 | 3284 | 3285 |
| monitored overflows | 1267 | 1102 | 1133 | 1456 | 1693 | 1848 | 1869 | 1602 | 1337 | 873 |
| overflows per 100 LSOAs | 38.6 | 33.6 | 34.5 | 44.3 | 51.5 | 56.3 | 56.9 | 48.8 | 40.7 | 26.6 |
| spills per LSOA | 6.9 | 5.4 | 6.6 | 9.9 | 11.4 | 12.8 | 11.8 | 10.1 | 8.7 | 4.8 |
| spill-hours per LSOA | 25.3 | 20.7 | 34.4 | 63.4 | 84.1 | 92.4 | 85.5 | 68.2 | 64.9 | 28.8 |
| spills per overflow | 17.8 | 16.2 | 19.0 | 22.4 | 22.1 | 22.7 | 20.8 | 20.8 | 21.3 | 17.9 |
| spills per 100k pop (mid-2015) | 417.9 | 323.2 | 383.1 | 584.4 | 676.7 | 755.7 | 718.8 | 613.2 | 528.4 | 294.4 |

Spearman rho (decile vs spills/LSOA): **0.152** (positive = more spills in *less* deprived deciles). Decile vs overflow density: 0.164; decile vs spills-per-overflow: 0.297. Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: **0.834**; hours per LSOA: 0.671.

### Urban LSOAs only (RUC 2011 A/B/C)

| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |
|---|---|---|---|---|---|---|---|---|---|---|
| LSOAs in stratum | 3230 | 3146 | 3042 | 2784 | 2550 | 2412 | 2416 | 2492 | 2505 | 2669 |
| monitored overflows | 1223 | 992 | 888 | 820 | 788 | 687 | 823 | 724 | 625 | 534 |
| overflows per 100 LSOAs | 37.9 | 31.5 | 29.2 | 29.5 | 30.9 | 28.5 | 34.1 | 29.1 | 24.9 | 20.0 |
| spills per LSOA | 6.7 | 5.0 | 5.0 | 4.6 | 4.7 | 4.7 | 5.6 | 5.4 | 4.2 | 3.4 |
| spill-hours per LSOA | 24.2 | 17.9 | 20.8 | 17.4 | 18.7 | 20.6 | 27.3 | 26.8 | 19.5 | 16.7 |
| spills per overflow | 17.7 | 16.0 | 17.0 | 15.6 | 15.2 | 16.4 | 16.4 | 18.6 | 16.8 | 17.0 |
| spills per 100k pop (mid-2015) | 406.9 | 298.8 | 288.3 | 268.6 | 276.6 | 276.9 | 338.9 | 329.5 | 257.8 | 211.2 |

Spearman rho (decile vs spills/LSOA): **-0.539** (positive = more spills in *less* deprived deciles). Decile vs overflow density: -0.745; decile vs spills-per-overflow: 0.224. Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: **1.118**; hours per LSOA: 0.893.

### Rural LSOAs only (RUC 2011 D/E)

| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |
|---|---|---|---|---|---|---|---|---|---|---|
| LSOAs in stratum | 54 | 138 | 243 | 500 | 735 | 872 | 868 | 793 | 779 | 616 |
| monitored overflows | 44 | 110 | 245 | 636 | 905 | 1161 | 1046 | 878 | 712 | 339 |
| overflows per 100 LSOAs | 81.5 | 79.7 | 100.8 | 127.2 | 123.1 | 133.1 | 120.5 | 110.7 | 91.4 | 55.0 |
| spills per LSOA | 17.3 | 14.4 | 26.6 | 39.6 | 34.6 | 35.2 | 29.3 | 25.0 | 23.0 | 10.7 |
| spill-hours per LSOA | 90.6 | 85.6 | 205.2 | 319.3 | 310.8 | 290.9 | 247.4 | 198.3 | 211.1 | 81.4 |
| spills per overflow | 21.2 | 18.1 | 26.4 | 31.1 | 28.1 | 26.5 | 24.3 | 22.6 | 25.2 | 19.4 |
| spills per 100k pop (mid-2015) | 1115.0 | 925.5 | 1650.4 | 2431.3 | 2115.0 | 2063.8 | 1769.1 | 1474.0 | 1373.5 | 649.1 |

Spearman rho (decile vs spills/LSOA): **-0.103** (positive = more spills in *less* deprived deciles). Decile vs overflow density: -0.018; decile vs spills-per-overflow: -0.03. Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: **1.076**; hours per LSOA: 0.983.

### Coastal LSOAs only (centroid within 5 km of coastline)

| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |
|---|---|---|---|---|---|---|---|---|---|---|
| LSOAs in stratum | 803 | 871 | 879 | 790 | 688 | 565 | 555 | 507 | 447 | 286 |
| monitored overflows | 329 | 276 | 249 | 389 | 372 | 316 | 313 | 203 | 189 | 91 |
| overflows per 100 LSOAs | 41.0 | 31.7 | 28.3 | 49.2 | 54.1 | 55.9 | 56.4 | 40.0 | 42.3 | 31.8 |
| spills per LSOA | 9.1 | 5.6 | 5.6 | 10.4 | 11.1 | 12.1 | 11.4 | 7.7 | 10.1 | 6.3 |
| spill-hours per LSOA | 39.7 | 22.6 | 31.6 | 59.9 | 78.5 | 75.0 | 79.2 | 46.2 | 80.9 | 34.2 |
| spills per overflow | 22.3 | 17.7 | 19.9 | 21.0 | 20.6 | 21.6 | 20.2 | 19.3 | 23.9 | 19.8 |
| spills per 100k pop (mid-2015) | 575.0 | 335.4 | 324.7 | 603.2 | 666.6 | 732.7 | 709.8 | 487.8 | 630.7 | 391.6 |

Spearman rho (decile vs spills/LSOA): **0.212** (positive = more spills in *less* deprived deciles). Decile vs overflow density: 0.212; decile vs spills-per-overflow: -0.03. Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: **0.879**; hours per LSOA: 0.736.

### Inland LSOAs only

| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |
|---|---|---|---|---|---|---|---|---|---|---|
| LSOAs in stratum | 2481 | 2413 | 2406 | 2494 | 2597 | 2719 | 2729 | 2778 | 2837 | 2999 |
| monitored overflows | 938 | 826 | 884 | 1067 | 1321 | 1532 | 1556 | 1399 | 1148 | 782 |
| overflows per 100 LSOAs | 37.8 | 34.2 | 36.7 | 42.8 | 50.9 | 56.3 | 57.0 | 50.4 | 40.5 | 26.1 |
| spills per LSOA | 6.1 | 5.4 | 6.9 | 9.8 | 11.4 | 12.9 | 11.9 | 10.6 | 8.4 | 4.6 |
| spill-hours per LSOA | 20.7 | 20.1 | 35.4 | 64.5 | 85.5 | 96.0 | 86.8 | 72.2 | 62.4 | 28.3 |
| spills per overflow | 16.2 | 15.7 | 18.8 | 22.9 | 22.5 | 23.0 | 20.9 | 21.0 | 20.8 | 17.7 |
| spills per 100k pop (mid-2015) | 369.3 | 318.8 | 404.8 | 578.4 | 679.4 | 760.3 | 720.6 | 635.0 | 512.6 | 285.2 |

Spearman rho (decile vs spills/LSOA): **0.176** (positive = more spills in *less* deprived deciles). Decile vs overflow density: 0.164; decile vs spills-per-overflow: 0.273. Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: **0.818**; hours per LSOA: 0.654.

### Sensitivity: monitors >=90% operational only

| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |
|---|---|---|---|---|---|---|---|---|---|---|
| LSOAs in stratum | 3284 | 3284 | 3285 | 3284 | 3285 | 3284 | 3284 | 3285 | 3284 | 3285 |
| monitored overflows | 1153 | 996 | 1043 | 1345 | 1571 | 1754 | 1740 | 1514 | 1244 | 809 |
| overflows per 100 LSOAs | 35.1 | 30.3 | 31.8 | 41.0 | 47.8 | 53.4 | 53.0 | 46.1 | 37.9 | 24.6 |
| spills per LSOA | 6.4 | 5.0 | 6.2 | 9.4 | 10.9 | 12.4 | 11.2 | 9.7 | 8.3 | 4.6 |
| spill-hours per LSOA | 23.9 | 19.1 | 32.7 | 60.9 | 81.0 | 90.3 | 80.8 | 65.7 | 62.6 | 28.4 |
| spills per overflow | 18.3 | 16.4 | 19.4 | 22.8 | 22.7 | 23.3 | 21.1 | 21.0 | 21.8 | 18.8 |
| spills per 100k pop (mid-2015) | 391.5 | 297.0 | 359.5 | 550.5 | 645.4 | 733.9 | 677.5 | 586.8 | 504.3 | 285.9 |

Spearman rho (decile vs spills/LSOA): **0.152** (positive = more spills in *less* deprived deciles). Decile vs overflow density: 0.152; decile vs spills-per-overflow: 0.297. Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: **0.819**; hours per LSOA: 0.663.


## The methodological finding: rivers ARE the boundaries

The point-to-single-LSOA join is intrinsically ill-posed for this data, and that is a finding, not a nuisance:

* Where the two generalised boundary sets disagree on the assignment, the overflow sits a **median 10.3 m** from an LSOA boundary (94.7% within 50 m). Where they agree, the median distance is 102.8 m. The disagreements are not data-quality noise — they are points sitting *on* boundary lines, because storm overflows discharge to watercourses and watercourses are exactly where LSOA (and ward) boundaries run.
* **51.4% of England's monitored storm overflows have more than one LSOA within 100 m**, and 43.3% have more than one candidate IMD decile. About one in nine changes LSOA just by switching between two reasonable generalisations of the same official boundaries.
* Anyone who joins EDM points to a single neighbourhood (LSOA, ward, constituency) without confronting this will get ~10-30% of assignments wrong depending on method, in a spatially structured way. This standalone result is checkable from `joined.csv` (columns `dist_to_lsoa_boundary_m`, `candidate_lsoas_100m`, `candidate_imd_deciles_100m`).

## The band: the decile analysis done honestly

Every overflow with any assignment ambiguity (method disagreement, or any second LSOA within 100 m) is pushed first to its most-deprived candidate LSOA, then to its least-deprived candidate. The truth lies between the edges.

| stratum | deprived-edge ratio (d1-5/d6-10 spills per LSOA) | affluent-edge ratio | deprived-edge rho | affluent-edge rho | outcome |
|---|---|---|---|---|---|
| all England | 1.148 | 0.584 | -0.273 | 0.624 | straddles 1.0 - no gradient survives |
| urban only | 1.856 | 0.675 | -0.964 | 0.818 | straddles 1.0 - no gradient survives |
| rural only | 1.397 | 0.811 | -0.43 | 0.248 | straddles 1.0 - no gradient survives |
| coastal only | 1.105 | 0.647 | -0.297 | 0.564 | straddles 1.0 - no gradient survives |
| inland only | 1.154 | 0.561 | -0.261 | 0.636 | straddles 1.0 - no gradient survives |

These edges are adversarial worst cases, so a weak-but-real gradient could still straddle 1.0. But here the *point estimates* were already flat-to-affluent-leaning; the band just confirms that assignment ambiguity alone can manufacture a gradient in either direction, which is precisely why the single-line decile chart must not be published.

## What it shows

1. **The raw national gradient runs the wrong way for the campaign story.** Spills per LSOA peak in mid-deciles (5-7) and are *lowest* in decile 10 — and second-lowest in deciles 1-2. The deprived half of England gets ~0.8x the spills per LSOA of the affluent half.
2. **The dominant variable is rural vs urban, not deprivation.** Rural LSOAs see several times the spills per LSOA of urban ones (small works serving dispersed settlements, long river frontage), and rural LSOAs skew mid-decile-to-affluent. That composition effect produces the national inverted-U.
3. **Within urban England a modest deprivation signal exists, but it is a density effect, not an intensity effect.** Most-deprived urban LSOAs host roughly twice the monitored overflows per LSOA of least-deprived urban LSOAs; spills *per overflow* are flat (~15-19) across all deciles. Deprived urban areas have more legacy combined-sewer overflows near them — the overflows there do not spill more. Deciles 2-9 are essentially flat; the gradient is carried by the endpoints.
4. **The coastal/inland split does not rescue the story.** Inland England shows the same affluent-leaning inverted-U; coastal deciles are noisy with no usable gradient.

## Verdict

**NOT SUPPORTED as an argument. PUBLISHABLE ONLY AS MAP — plus the methodological finding, which stands alone.**

Checked against all verdict options including PUBLISHABLE AS BAND: the band straddles "no gradient" in every stratum, so the deprivation gradient does not survive the both-sides treatment and the band option fails too.

"Sewage is dumped on deprived communities" is not what this data shows, under any of the controls tested. If Joined Up wants a defensible statement, the strongest version is the narrow one: *within urban England, the most-deprived tenth of neighbourhoods live near about twice as many monitored storm overflows as the least-deprived tenth — but those overflows spill no more often than anyone else's.* That is an infrastructure-legacy point, not a dumping point, and it must not be stretched further — and even it inherits the boundary-ambiguity caveat.

Two things ARE publishable:

1. **The map/data**: `joined.csv` is clean, mechanically honest, and fine to publish as an open dataset or map layer — points are plotted at their true coordinates, so the LSOA-assignment ambiguity does not infect a map the way it infects a decile chart. Keep the method and candidate columns intact.
2. **The methodological piece**: "one in nine storm overflows cannot be assigned to a single neighbourhood, because rivers are the boundaries" — quantified above, reproducible from the repo, and it protects everyone downstream who would otherwise do this join naively.

The decile bar chart as originally imagined would be misleading and should not be made.

Reproduce: `python fetch_geo.py && python resolve_bfc.py && python join.py && python make_report.py` (EDM zip fetched separately; see fetch history in this directory's scripts).
