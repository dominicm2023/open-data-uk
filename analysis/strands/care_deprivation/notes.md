# STRAND: Need is not evenly spread — children's social care tracks deprivation; libraries don't

Everything here is produced by `build_care_deprivation.py` in this folder (run:
`python analysis/strands/care_deprivation/build_care_deprivation.py`). It reads only
`analysis/ro/ro_per_head.csv` (MHCLG Revenue Outturn, net current expenditure, real
2024-25 prices) and `analysis/sewage/raw/IoD2019_File7_scores_ranks_deciles.csv`
(IMD 2019, full LSOA file). No network. The script asserts its own pins (Blackpool
£598.75, North Yorkshire £136.14, K&C £43.84, B&D £3.35, London CSC rho ≈ 0.567) and
fails loudly if any input drifts.

## Files

| file | what it is |
|---|---|
| `scatter_care_vs_deprivation.csv` | one row per authority (150 rows: 61 UA, 36 MD, 32 LB, 21 SC): class, IMD average score, and net-real / gross / income-share per head for CSC, ASC, libraries. The libraries columns ARE the null foil — same authorities, same file, so the steep and flat scatters ship together. |
| `spearman_by_class_service.csv` | Spearman rho + n + p per class per service, recomputed on this build. |
| `extreme_pairs.csv` | five verified within-class extreme pairs, gross-checked, with both IMD scores and the class median. |

Class is stated on every row of every file. No cross-class comparison anywhere.
Excluded: City of London, Isles of Scilly (house convention — non-comparable),
Cumberland (filed no 2024-25 return). SD excluded by design: shire districts do not
run social care or libraries.

## The IMD aggregation (documented, with limits)

IMD 2019 File 7 carries an April-2019 LAD code on every LSOA row. We compute each
authority's **population-weighted average IMD score**: sum(LSOA score x LSOA total
population mid-2015) / sum(population), which mirrors how MHCLG's own official LAD
summary ("average score", File 10) is constructed — but on **2024-25 boundaries**:

- **Unchanged authorities** (all 32 LBs, all 36 MDs, 54 of 61 UAs): LAD19 code used as-is.
- **Post-2019 reorganisations**: LSOAs of abolished districts are pooled into the
  7 successor unitaries via an explicit map in the script (Buckinghamshire 2020;
  North & West Northamptonshire 2021; Cumberland, Westmorland & Furness,
  North Yorkshire, Somerset 2023). This is why our UA correlation covers n=61 —
  the earlier `analysis/ro` pass matched stable codes only and silently dropped these.
- **Shire counties**: the 164 district LSOA sets are pooled into their 21 counties via
  a district→county map. Validation: the map's code set must equal the RO file's own
  2024-25 SD code set exactly (both directions — it does, 164=164), per-county district
  counts are asserted, county E10 codes are taken from the RO file not typed from
  memory, and six spot names (Adur→W Sussex, Welwyn Hatfield→Herts, East Suffolk→Suffolk…)
  are asserted against RO names.

**Limits, stated plainly:** IMD is 2019-vintage (indicator data mostly 2015-16) set
against 2024-25 spend; the population weights are the IMD file's own mid-2015 counts,
not mid-2024; boundary aggregation is exact for LSOA membership (no LSOA splits across
these mergers). Rank correlation limits sensitivity to all of this, but a 2019 score is
still yesterday's deprivation. And rho ≈ 0 means *no gradient*, not *fairness*.

## Recomputed correlations (net real £/head 2024-25 vs IMD average score)

| class | CSC rho (p) | ASC rho (p) | libraries rho (p) | n |
|---|---|---|---|---|
| LB | **0.569** (0.0007) | 0.281 (0.12) | 0.036 (0.84) | 32 |
| MD | **0.442** (0.007) | 0.093 (0.59) | -0.050 (0.77) | 36 |
| UA | **0.822** (<0.0001) | 0.111 (0.40) | -0.018 (0.89) | 61 |
| SC | 0.235 (0.31) | 0.548 (0.01) | 0.158 (0.49) | 21 |

Reading, carefully:

- **CSC is the deprivation service.** Significant in every class with real variation in
  deprivation. The UA figure (0.822) is much stronger than the previously reported
  because the successor-boundary aggregation brings the reorganised unitaries back in —
  including low-deprivation/low-spend North Yorkshire and the shire-ish new UAs that
  anchor the bottom-left of the scatter.
- **The mechanism is demand, not generosity.** Child protection is statutory and
  demand-led: referrals, child protection plans, children in care. Councils in deprived
  places spend more because more children arrive at the door, not because anyone chose
  to fund them better. Do not caption this as "deprived areas get more money."
- **ASC does not track deprivation** in LB/MD/UA — its demand driver is age structure
  (see the Isle of Wight pair below), and Better Care Fund money enters as income,
  blurring net levels. The SC cell (0.548, n=21) is the odd one out: small n, compressed
  deprivation range across counties — report it, don't build on it.
- **Libraries are the null foil**: 0.04 / -0.05 / -0.02 / 0.16, nothing significant in
  any class. "Poor areas lost their libraries" is not supported cross-sectionally; the
  supported claim is bleaker — library provision is unrelated to need in either direction.

## The five verified pairs (`extreme_pairs.csv`)

Selection rule (from the hand-check graveyard): highest vs lowest net per head within
class, skipping any authority whose net is negative or whose income offsets ≥25% of
gross (charging/BCF artefacts). Every surviving pair's gap is confirmed in **gross**
spend too — none is an accounting trick.

| class | service | pair | net £/head | ratio (gross ratio) | IMD scores |
|---|---|---|---|---|---|
| UA | CSC | **Blackpool vs North Yorkshire** | 598.75 vs 136.14 | 4.4x (4.4x) | 45.0 vs 14.8 |
| LB | CSC | Islington vs Harrow | 419.83 vs 182.91 | 2.3x (2.7x) | 27.5 vs 15.0 |
| MD | CSC | Bradford vs Kirklees | 455.87 vs 217.62 | 2.1x (2.0x) | 34.7 vs 25.2 |
| UA | ASC | Isle of Wight vs Slough | 617.15 vs 346.34 | 1.8x (1.9x) | 23.3 vs 23.0 |
| LB | libraries | Kensington & Chelsea vs Barking & Dagenham | 43.84 vs 3.35 | 13.1x (11.4x) | 21.5 vs 32.8 |

Notes per pair: Blackpool/NY is the strand's spine — most-deprived unitary in England
vs one of the least, same statutory duties, 4.4x. The ASC pair is deliberately a
*counter*-example: near-identical deprivation scores, 1.8x gap — adult care money sorts
on age, not poverty (Thurrock and Derby were skipped at the low end as income
artefacts, ≥25% of gross offset — likely BCF routing; that's in the CSV's
`skipped_as_artefact` column). The K&C/B&D pair inverts need outright: the *less*
deprived borough spends 13x more. Bradford's children's services run through a trust —
NCE follows booking choices; the gross check holds, but say "books" not "delivers"
if pressed.

## What a fair critic would still attack

1. IMD 2019 against 2024-25 spend (stated above). 2. Net lines follow booking
choices — that's why gross columns ship in every file and pairs are gross-checked.
3. ASC net is BCF-contaminated; we make no ASC-vs-deprivation claim beyond "no
gradient". 4. SC has n=21 and a narrow deprivation range — its cells are context, not
findings. 5. Cross-sectional 2024-25 only; nothing here says spend *rose* where
deprivation rose. 6. Correlation is not sufficiency: rho 0.82 does not mean deprived
areas get *enough*, only that rank order follows need.

---

## Caption drafts (Joined Up voice)

### V1 — the paired scatters (CSC steep, libraries flat; same 150 authorities)

1. "Two scatters, same councils. Children's social care climbs with deprivation —
   rho 0.82 across England's unitaries — because child protection is demand-led and
   the demand is where the poverty is. Libraries, the same councils, the same axis:
   flat. One budget answers need. The other answers nothing."
2. "Blackpool spends £599 a head keeping children safe; North Yorkshire spends £136.
   That's not generosity to poor places — it's the statutory bill for concentrated
   deprivation, and it lands on the councils least able to raise the money. Library
   spend, plotted for the very same councils, shows no relationship to need at all."
3. "Where deprivation is high, children's social care spending is high — in London
   boroughs, in the mets, in the unitaries. Nobody designed that; referrals did it.
   Now look at libraries on the same page: no slope, no pattern, no plan."

### V2 — the correlation ladder (Spearman by class and service)

1. "Rank councils by deprivation, then by spend, class by class. Children's social
   care tracks need everywhere it can be measured: 0.82 in unitaries, 0.57 in London,
   0.44 in the mets. Libraries never clear zero. The only service that follows
   poverty is the one the law makes follow it."
2. "Adult social care follows age. Children's social care follows deprivation.
   Libraries follow nothing — rho of 0.04, -0.05, -0.02 across 129 councils. When
   provision is discretionary, need stops being the sorting variable."
3. "'Poor areas lost their libraries' — we checked, and the truth is worse: library
   spending simply has no relationship to deprivation, in any direction, in any class
   of council. Need doesn't decide. Nothing visible in the data decides."

### V3 — the extreme pairs (dumbbell)

1. "Same class of council, same legal duties, four-fold gap: Blackpool £599 per
   resident on children's social care, North Yorkshire £136. The gap survives the
   gross-spending check — it isn't accounting, it's need. Demand-led budgets go where
   deprivation is, and deprivation is not evenly spread."
2. "Islington books 2.3 times Harrow's children's social care spend; Bradford twice
   Kirklees'. In every pair the more deprived place spends more — not as a reward,
   as a consequence. Child protection doesn't wait for funding formulas."
3. "The counter-examples prove the rule. Isle of Wight and Slough have near-identical
   deprivation scores and a 1.8x gap in adult social care — that money follows age,
   not poverty. And Kensington & Chelsea outspends Barking & Dagenham on libraries
   13-to-1, with B&D far more deprived. Only children's social care tracks need —
   because only there does need force the spend."
