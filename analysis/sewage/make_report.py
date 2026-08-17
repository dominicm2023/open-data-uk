"""Render REPORT.md from findings.json. Run after join.py."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
f = json.load(open(os.path.join(HERE, 'findings.json')))

def decile_row(s, key, fmt='{:.1f}'):
    d = f['strata'][s]['deciles']
    cells = []
    for i in range(1, 11):
        v = d[str(i)].get(key)
        cells.append(fmt.format(v) if v is not None else '-')
    return ' | '.join(cells)

def stratum_block(s, label):
    st = f['strata'][s]
    lines = [
        f'### {label}',
        '',
        '| metric | d1 (most deprived) | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 (least deprived) |',
        '|---|---|---|---|---|---|---|---|---|---|---|',
        f"| LSOAs in stratum | {decile_row(s, 'lsoas', '{:d}')} |",
        f"| monitored overflows | {decile_row(s, 'overflows', '{:d}')} |",
        f"| overflows per 100 LSOAs | {decile_row(s, 'overflows_per_100_lsoas')} |",
        f"| spills per LSOA | {decile_row(s, 'spills_per_lsoa')} |",
        f"| spill-hours per LSOA | {decile_row(s, 'hours_per_lsoa')} |",
        f"| spills per overflow | {decile_row(s, 'spills_per_overflow')} |",
        f"| spills per 100k pop (mid-2015) | {decile_row(s, 'spills_per_100k_pop')} |",
        '',
        f"Spearman rho (decile vs spills/LSOA): **{st['spearman_decile_vs_spills_per_lsoa']}** "
        f"(positive = more spills in *less* deprived deciles). "
        f"Decile vs overflow density: {st['spearman_decile_vs_overflow_density']}; "
        f"decile vs spills-per-overflow: {st['spearman_decile_vs_spills_per_overflow']}. "
        f"Deprived half (d1-5) / affluent half (d6-10), spills per LSOA: "
        f"**{st['deprived_half_over_affluent_half_spills_per_lsoa']}**; "
        f"hours per LSOA: {st['deprived_half_over_affluent_half_hours_per_lsoa']}.",
        '',
    ]
    return '\n'.join(lines)

mc = f['method_comparison']
p = f['parsing']
bp = f['boundary_proximity']
band = f['band']

def band_block(s, label):
    b = band[s]
    de, ae = b['deprived_edge'], b['affluent_edge']
    return (f"| {label} | {de['deprived_half_over_affluent_half']} | "
            f"{ae['deprived_half_over_affluent_half']} | "
            f"{de['spearman_decile_vs_spills_per_lsoa']} | "
            f"{ae['spearman_decile_vs_spills_per_lsoa']} | "
            f"{'straddles 1.0 - no gradient survives' if de['deprived_half_over_affluent_half'] >= 1.0 >= ae['deprived_half_over_affluent_half'] or ae['deprived_half_over_affluent_half'] >= 1.0 >= de['deprived_half_over_affluent_half'] else 'gradient survives'} |")
totals = f['strata']['all_england']['deciles']
tot_spills = sum(totals[str(i)]['spills'] for i in range(1, 11))
tot_hours = sum(totals[str(i)]['hours'] for i in range(1, 11))
tot_over = sum(totals[str(i)]['overflows'] for i in range(1, 11))

report = f"""# Where the sewage meets the deprivation — join note

**Status: workshop note. Verdict at the end. Tier-4 cross-source join; human review required before anything derived from this is published.**

## What was joined

| input | vintage | file | licence |
|---|---|---|---|
| Storm overflow spills (EDM annual return, all English water & sewerage companies) | calendar year **2025** | `raw/{f['inputs']['edm']['file']}` (Environment Agency) | OGL-UK-3.0 |
| Index of Multiple Deprivation, LSOA rank/decile (File 7) | **IMD 2019** (underlying data mostly 2015-16; population denominators mid-2015) | `raw/{f['inputs']['imd']['file']}` (MHCLG) | OGL-UK-3.0 |
| LSOA 2011 boundaries, generalised (BGC 20m / BSC 200m) + full-res (BFC, queried server-side) | Dec 2011 | `raw/lsoa2011_bgc.json`, `raw/lsoa2011_bsc.json` (ONS Open Geography) | OGL-UK-3.0 |
| LSOA 2011 population-weighted centroids | Dec 2011 (2022 republication) | `raw/lsoa2011_pwc.json` (ONS) | OGL-UK-3.0 |
| Rural-Urban Classification of LSOAs | RUC 2011 | `raw/ruc2011_lsoa.json` (ONS) | OGL-UK-3.0 |

The vintages do not match: spills are 2025, deprivation is measured as of 2019 (data 2015-16) on 2011 statistical geography. Any published use must carry both dates.

Scotland and Wales are excluded by construction: the EA annual return covers English WaSC operations only (Dwr Cymru appears with {p.get('welsh_water_english_sites', 119)} EA-permitted sites that are physically in England), and IMD 2019 deciles exist only for English LSOAs. Different nations have incomparable deprivation indices.

## Mechanics and their honest error bars

* Coordinates are OS National Grid references from the EA consents database, parsed to easting/northing. The whole LSOA join runs in EPSG:27700 — **no datum transform touches the assignment**. (WGS84 lon/lat columns in `joined.csv` are convenience output via a Helmert transform, ~5 m accuracy.)
* {p['overflows_parsed']:,} of 14,302 return rows parsed cleanly; skipped: {p['rows_skipped']['bad_duration']} with unparseable duration, {p['rows_skipped']['bad_ngr']} with unparseable grid reference. {p['overflows_england']:,} land in English LSOAs.
* Assignment method per row is recorded in `joined.csv`. Precedence: full-resolution BFC (server-side point-in-polygon, used for every point where the two generalised boundary sets disagreed or missed), then BGC (20 m), then BSC (200 m), then nearest population-weighted centroid as last resort. Method counts: BFC {p['assignment_method_counts'].get('bfc', 0):,}, BGC {p['assignment_method_counts'].get('bgc', 0):,}, BSC {p['assignment_method_counts'].get('bgc_missed_bsc_hit', 0)}, centroid fallback {p['assignment_method_counts'].get('pip_missed', 0)} (offshore/estuarine points outside the clipped land polygons).
* **Nearest-centroid assignment is dead**: it disagrees with polygon assignment on {mc['bgc_vs_centroid']['lsoa_disagreement_pct']}% of LSOA codes and {mc['bgc_vs_centroid']['decile_disagreement_pct']}% of deciles. Do not let anyone publish a centroid-joined version of this.
* Generalised boundaries alone are also not good enough at this point density: BGC (20 m) vs BSC (200 m) disagree on {mc['bgc_vs_bsc']['decile_disagreement_pct']}% of deciles — overflows sit on watercourses, and watercourses are exactly where LSOA boundaries run. This is why the disputed points were arbitrated against full-resolution BFC boundaries. Arbitration of {mc['bfc_arbitration_of_disputed']['n']:,} disputed/missed points: BFC sided with BGC {mc['bfc_arbitration_of_disputed']['bfc_sides_with_bgc']:,} times, with BSC {mc['bfc_arbitration_of_disputed']['bfc_sides_with_bsc']}, with neither {mc['bfc_arbitration_of_disputed']['bfc_sides_with_neither']}.
* Residual error where both generalised sets agreed, estimated on a random sample of 300 arbitrated against BFC: {mc['validation_sample_agreed_points_vs_bfc']['lsoa_confirmed_pct']}% LSOA-confirmed, {mc['validation_sample_agreed_points_vs_bfc']['decile_confirmed_pct']}% decile-confirmed.
* Coastal flag: LSOA centroid within 5 km of the repo's ultra-generalised coastline (~1 km tolerance — coarse, disclosed, only used for the coastal/inland control).
* EDM coverage is not decile-biased: mean monitor uptime is ~97% in every decile, and restricting to monitors >=90% operational ({f['op90_note']}) does not change the shape.

## Headline numbers (England, calendar 2025)

{tot_over:,} monitored storm overflows, {tot_spills:,.0f} counted spills (12-24h counting method), {tot_hours:,.0f} spill-hours.

{stratum_block('all_england', 'All England')}
{stratum_block('urban_only', 'Urban LSOAs only (RUC 2011 A/B/C)')}
{stratum_block('rural_only', 'Rural LSOAs only (RUC 2011 D/E)')}
{stratum_block('coastal_only', 'Coastal LSOAs only (centroid within 5 km of coastline)')}
{stratum_block('inland_only', 'Inland LSOAs only')}
{stratum_block('all_england_op90plus', 'Sensitivity: monitors >=90% operational only')}

## The methodological finding: rivers ARE the boundaries

The point-to-single-LSOA join is intrinsically ill-posed for this data, and that is a finding, not a nuisance:

* Where the two generalised boundary sets disagree on the assignment, the overflow sits a **median {bp['methods_disagree']['median_m']} m** from an LSOA boundary ({bp['methods_disagree']['pct_within_50m']}% within 50 m). Where they agree, the median distance is {bp['methods_agree']['median_m']} m. The disagreements are not data-quality noise — they are points sitting *on* boundary lines, because storm overflows discharge to watercourses and watercourses are exactly where LSOA (and ward) boundaries run.
* **{bp['pct_overflows_with_multiple_candidate_lsoas_100m']}% of England's monitored storm overflows have more than one LSOA within 100 m**, and {bp['pct_overflows_with_multiple_candidate_deciles_100m']}% have more than one candidate IMD decile. About one in nine changes LSOA just by switching between two reasonable generalisations of the same official boundaries.
* Anyone who joins EDM points to a single neighbourhood (LSOA, ward, constituency) without confronting this will get ~10-30% of assignments wrong depending on method, in a spatially structured way. This standalone result is checkable from `joined.csv` (columns `dist_to_lsoa_boundary_m`, `candidate_lsoas_100m`, `candidate_imd_deciles_100m`).

## The band: the decile analysis done honestly

Every overflow with any assignment ambiguity (method disagreement, or any second LSOA within 100 m) is pushed first to its most-deprived candidate LSOA, then to its least-deprived candidate. The truth lies between the edges.

| stratum | deprived-edge ratio (d1-5/d6-10 spills per LSOA) | affluent-edge ratio | deprived-edge rho | affluent-edge rho | outcome |
|---|---|---|---|---|---|
{band_block('all_england', 'all England')}
{band_block('urban_only', 'urban only')}
{band_block('rural_only', 'rural only')}
{band_block('coastal_only', 'coastal only')}
{band_block('inland_only', 'inland only')}

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
"""

with open(os.path.join(HERE, 'REPORT.md'), 'w', encoding='utf-8') as out:
    out.write(report)
print('wrote REPORT.md')
