# Austerity was a postcode policy — regressive strand

**Status: built and hand-checked. Every number from `build_regressive.py` (this
folder), pure on-disk join, no network, no corpus. Rebuild: `python
build_regressive.py` (prints all witness checks).**

Inputs: `../../strands/counciltax/grant_settlement_league.csv` (real settlement
funding per head, 2024-25 prices, 2013-14 -> 2024-25, with `league_excluded` +
`handcheck` flags), `../../strands/care_deprivation/scatter_care_vs_deprivation.csv`
(population-weighted IMD 2019 average score, upper-tier authorities),
`../../strands/counciltax/ct_dependence_2024_25.csv` (real CTR per head,
financing share, flags). **Shire-district IMD** is derived in this build from
the raw LSOA file `../../sewage/raw/IoD2019_File7_scores_ranks_deciles.csv`
by the same method as the care_deprivation strand (population-weighted average
of LSOA IMD scores, weights = the file's own mid-2015 populations; LAD-2019
codes are district codes and the league's stable panel excludes every district
reorganised since). Witness: on the 123 boundary-stable upper-tier authorities
the derivation reproduces the validated strand values to max abs dev 0.005.
All comparisons within MHCLG class. "Clean" = `league_excluded` False and
`handcheck` empty. `loss_ph` = -change_real_ph (positive = money lost per
resident per year). IMD coverage is 304/304 league rows.

## Verdicts

### (a) The pounds claim — PROVABLE NOW (LB, SC, UA, SD); SUPPORTED, NOT CLEAN (MD)

Within class, the more deprived the authority, the more real settlement
funding per head it lost 2013-14 -> 2024-25. Spearman rho, IMD score vs loss
per head, clean rows (`spearman_by_class.csv`):

| class | n clean | rho | p | all-matched rho (n) |
|---|---:|---:|---:|---:|
| LB | 32 | **+0.624** | 1.4e-4 | +0.624 (32) |
| MD | 14 | +0.437 | 0.12 | +0.515 (36, p=0.0013) |
| SC | 20 | **+0.869** | 6.6e-7 | +0.769 (21) |
| SD | 135 | **+0.398** | 1.7e-6 | +0.246 (162) |
| UA | 43 | **+0.816** | 2.6e-11 | +0.668 (53) |

The SD gradient is real but half the strength of the upper tiers — the
business-rates lottery scrambles it (see extremes), and the pounds at stake
are a tenth of the upper-tier scale (clean median -£25/head vs -£203 to
-£324). Every class points the same way; four of five are provable clean.

MD honesty: 22 of 36 mets carry `rsg_zero_2024_check_rollin` (enhanced-
retention accounting), leaving only 14 clean — direction right, not
significant at n=14. The all-matched rho is significant but the flagged rows'
"least-cut look" is partly artefact; say "the pattern holds in every class,
provable beyond doubt in three" and lean on LB/SC/UA.

Quartile witness (clean, within class, medians): most-deprived quartile lost
**1.9x** the least-deprived quartile's money in London (-£431 vs -£226/head)
and among unitaries (-£403 vs -£215), 1.5x in counties, 1.4x in mets.

### (b) The percent claim — MISLEADING AS FRAMED. Never say "biggest share"

Within class, percent change in settlement runs the OTHER way: rho(IMD, %
loss) is **negative** — LB -0.524, SC -0.459, UA -0.356 (MD and SD ~0). Affluent
authorities lost a larger share of a much smaller grant (RSG abolition took
their grants to near-zero: Devon RSG £134.8m -> £0.7m, Hampshire £157.9m ->
£58k — yes, fifty-eight thousand pounds). The correct sentence is always
"lost the most money per head", never "lost the biggest share".

**Reconciliation with IFS/NAO** (who found deprived areas MOST cut, including
in percent terms): no contradiction, two differences. (1) Their measure is
spending power / total funding percent cuts; settlement is a far bigger slice
of a deprived council's budget, so an equal settlement-percent cut is a bigger
spending-power-percent cut where deprivation is high. (2) Their window starts
2009-10/2010-11; ours starts 2013-14, after the steepest need-targeted cuts
had already landed. Our pounds-per-head leg reproduces their direction on the
data we hold; our percent leg measures a different (narrower) thing. The
quartile table shows the mechanism: percent cuts roughly flat across
deprivation quartiles (LB Q1 -54% vs Q4 -41%; UA -48% vs -46%) applied to
starting grants ~2.3x higher in the most deprived quartile (LB £1,027 vs
£442/head; UA £912 vs £440) = double the pounds taken from the poorest places.

### (c) SD leg — COMPUTED (first draft of this note wrongly called it a gap)

`scatter_care_vs_deprivation.csv` is upper-tier only, but the raw LSOA IMD
file in `../../sewage/raw/` covers every district; this build derives
district IMD from it (method + witness in the header). Result: the gradient
holds among districts too (rho +0.398, n=135 clean, p=1.7e-6), at a tenth of
the pound stakes. The class's own story stays the rates lottery: 14 of 135
clean districts GAINED in real terms, and the eyeballed gainers (South
Cambridgeshire +£18/head, Winchester +£13, Wychavon +£11) all show the same
components — RSG to near-zero, retained rates tripled-to-quadrupled
(S Cambs £4.8m -> £15.8m, Winchester £2.0m -> £9.4m) — growth-corridor wins,
not government favour. Keep SD out of headline captions; use it as "the
pattern holds even among districts".

### (d) The compounding claim — PROVABLE via deprivation; direct link UA + SD

"Deprived areas lost the grant AND have the weakest tax base" — both legs
hold, but be precise about the join (`compound_spearman_by_class.csv`):

- **IMD vs real CTR per head, within class, clean both sides: negative in all
  five classes** — LB -0.570 (p=6.5e-4), MD -0.697 (p=0.006), SC -0.472
  (p=0.04), SD -0.375 (p=1.2e-5), UA -0.737 (p=1.8e-8). The places that lost
  most cannot replace it from council tax: PROVABLE.
- Direct loss-vs-taxbase (loss_ph vs ctr_per_head): significant for UA
  (-0.511, p=4.7e-4) and SD (-0.205, p=0.019); LB/MD/SC directionally
  negative, not significant. So the compounding flows through deprivation,
  not as a tight authority-by-authority lockstep. Quartile witness: UA
  biggest-loser quartile raises a median **£450/head** of council tax vs
  **£593** for the smallest losers; LB £442 vs £554; SD £85 vs £100
  (district-share only, includes parish precepts). State it that way.

## The extreme pairs, hand-checked (`extremes_by_class.csv`)

All named rows: clean flags, smooth arcs (65-100% of the fall done by
2018-19 — none catch the post-2018 cliff artefact). IMD rank 1 = most
deprived in class.

- **LB:** Lewisham lost **-£689/head** (deprivation rank 7/32) vs Westminster
  **-£20** (rank 19; West End rates boom, £26.5m -> £147.6m retained — a
  rates story, not generosity). Bromley (-£205, rank 29) and Barnet (-£189,
  rank 26) are the true affluent-and-spared pair. Counterexample to name
  before a critic does: Kensington & Chelsea lost -£613/head at mid-table
  deprivation (rank 17) — London polarisation, the borough average hides
  Golborne-vs-Holland-Park extremes.
- **MD:** South Tyneside **-£527** (rank 13/36) vs Kirklees -£200 (rank 30).
  North Tyneside (-£503) is clean-flagged but rank 33/36 — a genuine
  counterexample; per the counciltax notes, headline South Tyneside.
- **SC:** the two most deprived counties in England top the loss league:
  Lancashire (rank 1, -£254) and Norfolk (rank 2, -£306) vs Oxfordshire
  (rank 20/21, -£144) and Leicestershire (rank 19, -£146).
- **UA:** Middlesbrough (rank 3/53) lost **-£484/head**; Hartlepool (rank 5)
  -£442. Windsor & Maidenhead and Rutland (joint rank 51/53, the least
  deprived in class) lost -£145 and -£166. Middlesbrough vs W&M is the
  postcard: **W&M lost a bigger share (-56% vs -49%); Middlesbrough lost
  3.3x the money.** (North Lincolnshire and Rutland's settlements partly
  recovered after 2018-19 on rates growth — endpoints fine, arcs eyeballed.)
- **SD:** Bassetlaw -£85 (rank 27/162) and Preston -£82 (rank 9) fit the
  pattern; Rushmoor -£85 (rank 74) does not — the SD gradient is the noisiest
  (rho 0.40). At the bottom, affluent gainers: South Cambridgeshire +£18
  (rank 151/162), Winchester +£13 (rank 144), Wychavon +£11 (rank 77) — all
  rates-growth stories (components eyeballed, above). District IMD here is
  this build's File7 derivation.

## The strongest objection a critic would make

*"Mechanical: deprived areas lost more per head only because they had more
per head. Any uniform cut to need-based grants produces your correlation."*
Answer, from the data: (1) the cut was NOT uniform — within class, percent
cuts were flat-to-shallower for deprived areas, meaning ministers had every
opportunity to protect need in pounds and did not; equal-share cuts to
need-scaled grants ARE the regressive choice, made annually for eleven years.
(2) The compounding leg is not mechanical at all: nothing forces the places
that lost the most grant to also raise the least council tax per head — that
is the tax-base geography (band D homes vs band A terraces), and it is why
the loss could not be replaced locally. Concede freely: IMD is 2019-vintage
against a 2013->2024 window; scores are authority averages (K&C shows the
limit); settlement funding is not total spending power.

Second objection: *"You dropped 60 authorities."* — every one carries a named
flag from the counciltax hand-check graveyard: 27 enhanced-retention roll-ins
(`rsg_zero_2024_check_rollin`), 22 post-2018 one-year cliffs, 11 incomplete or
zero-rates financing returns (the `league_excluded` set), 9 genuine
rates-growth gainers held out conservatively (they'd help the percent story,
not hurt the pounds one). All still present in the CSVs with their flags,
none silently dropped; all-matched rhos are shown alongside and the story
survives them. Separately, 8 reorganised unitaries (BCP, Dorset, Bucks, the
Northants pair, Westmorland, N Yorks, Somerset) plus Cumberland have no
stable 2013 comparator and are absent from the league itself, and City of
London/Scilly never rank.

## Files

| file | for |
|---|---|
| `scatter_settlement_loss_vs_imd.csv` | (a) per-class scatter, all 304: IMD score x loss per head, ranks, flags |
| `spearman_by_class.csv` | (a) rho/p per class, clean and all-matched, pounds and percent |
| `map_loss_per_head.csv` | (b) all 304 authorities: ons_code, loss_ph, change_pct, IMD, flags |
| `extremes_by_class.csv` | (c) top/bottom 3 per class, clean only, with deprivation ranks |
| `compound_join.csv` | (d) loss x IMD x ctr_per_head x financing share per authority |
| `compound_spearman_by_class.csv` | (d) the compounding correlations |

## Caption drafts (Joined Up voice)

1. "Between 2013 and 2024, Middlesbrough — the third most deprived unitary
   in England — lost £484 per resident per year in central funding. Windsor
   & Maidenhead, the least deprived, lost £145. That's not a spreadsheet
   accident. That's a postcode policy, renewed every year for eleven years."
2. "The two most deprived counties in England, Lancashire and Norfolk, top
   the funding-cut league. The gentlest cuts went to Oxfordshire and
   Leicestershire. Rank councils by deprivation and you've ranked them by
   what Whitehall took (rho up to 0.87)."
3. "Here's the trap built into austerity: the poorest places lost twice the
   money per head — and they're exactly the places where council tax raises
   the least (£450 a head in the hardest-hit unitaries vs £593 in the
   spared ones). Cut the grant, point at the tax base, call it local
   choice."

Caption discipline: always "per head" and "within class"; never "biggest
share" (that ran the other way — see (b)); districts only as "the pattern
holds even among districts", never as headline examples (rho 0.40, rates
lottery); MD claims lean on South Tyneside, not North Tyneside, and cite the
all-classes direction rather than an MD-only rho. The rho quoted in caption 2
is the counties' 0.869; say "up to" or name the class.
