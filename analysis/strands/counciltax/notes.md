# The burden moved to your council tax bill - counciltax strand

**Status: built and hand-checked. Every number comes from `build_counciltax.py`
(this folder), which reads `../../ro/ro.sqlite` plus the raw MHCLG RS
workbooks in `../../ro/raw/` - no network. Rebuild: `python
build_counciltax.py` (prints the witness checks); `python handcheck.py`
(prints the raw financing block for every named extreme).**

All real-terms figures are 2024-25 prices (HMT GDP deflator, June 2026 QNA:
2013-14 x1.3693, 2018-19 x1.2692). All comparisons within one MHCLG class;
England aggregates sum the five principal classes (SD, SC, UA, MD, LB).
City of London and Isles of Scilly stay in sums, never in rankings.
Cumberland 2024-25 filed no return and is absent throughout.

## Definitions (state on every output)

- **Council-tax share of NRE** = council tax requirement / net revenue
  expenditure, cash, same vintage (the REPORT.md headline measure). CTR
  includes parish precepts for districts. The ratio can exceed 100% for an
  authority topping up reserves - see graveyard.
- **Council-tax share of financing** = CTR / (CTR + RSG + police grant +
  retained rates + collection-fund surplus + other items). Same story,
  robust to the netting artefacts; **use this one to colour the map**.
- **Settlement funding** = Revenue Support Grant + retained income from the
  rate retention scheme. 2013-14 is the retention scheme's first year, so
  the pair is defined identically at both endpoints, and the sum is robust
  to the pilots that rolled RSG into rates. Police grant is excluded: the
  only principal-class recipient is the City of London (verified, all three
  vintages). Grants inside AEF are excluded because schools money dominates
  them and academisation moved schools off LA books.
- **Reserves** = other earmarked + unallocated, 31 March levels (verified:
  RS 2013-14 sheet (2) carries the 31 March 2014 levels; its flow columns
  are blank). Schools, public health and DSG reserves excluded.
- Financing lines are stored **negative** in every RS vintage. Proof: the
  workbook identity CTR = NRE + appropriations + financing holds to 2k /
  21m / 52m (on 55-74bn) with them negative, and fails by 54-67bn read
  positive. `build_counciltax.py` flips them; authority sums then match each
  workbook's own England row to 0 except the 2024-25 Cumberland imputation
  (RSG -12.1m, rates -33.5m, collection fund -82.3m).

## Findings

### (a) The burden moved - `ct_share_england.csv`, `ct_share_by_class.csv`

Council tax carried **47.0p of every pound of net revenue expenditure in
2013-14; 62.0p by 2018-19; 63.0p in 2024-25**. On the financing basis it is
45.1p -> 63.7p. Behind the ratio: real council tax raised went **£27.08bn ->
£34.17bn (+26.2%)** while real NRE *fell* £57.66bn -> £54.27bn (-5.9%) and
real settlement funding fell 43% (£32.77bn -> £18.72bn on the same un-gated
rows). The bill went up because the grant went away, not because councils
spent more.

Per class (CTR share of NRE, 2013-14 -> 2024-25):

| class | 2013-14 | 2024-25 | change |
|---|---:|---:|---:|
| SC shire counties | 58.2% | **76.5%** | +18.3pp |
| UA unitaries | 47.0% | 66.3% | +19.3pp |
| MD met districts | 35.8% | 50.1% | +14.3pp |
| LB London boroughs | 36.5% | 50.7% | +14.2pp |
| SD shire districts | 58.6% | 67.0% | +8.4pp |

Counties now raise three pounds in four from council tax; even the met
districts, historically grant-funded, crossed 50%.

### (b) Dependence map 2024-25 - `ct_dependence_2024_25.csv`

One row per principal authority: both share measures, within-class
percentile (computed on the financing share, clean rows only), real CTR per
head, 2013-14 share and pp change. **Colour `ct_share_financing_pct`,
within class**; rows with `share_artefact` or `fin_incomplete` True get a
"no data / not comparable" hatch, `excluded_from_rankings` covers City of
London and Isles of Scilly. Clean medians and spans (financing basis):
SD median 60.1% (min NW Leicestershire 27.2%), UA 66.0%, MD 52.5%
(Manchester 34.4% - North Tyneside 70.9%), LB 57.5% (Westminster 27.4% -
Richmond 83.3%), SC 78.0% (Lincolnshire 68.0% - Gloucestershire 90.9%).
The gradient is deprivation inverted, and strongly: Spearman rho between
financing share and population-weighted IMD 2019, within class, clean rows:
**UA -0.915, MD -0.858, LB -0.729, SD -0.479** (counties not computable at
LAD level; IMD is 2019-vintage against 2024-25 shares, same method and
caveat as REPORT.md). Read it forward for the campaign: the richer the
area, the more its council already runs on residents' bills; the poorer
the area, the more it still depends on the government that sets the next
settlement - cut exposure is concentrated in deprived places.

### (c) Reserves arc - `reserves_arc.csv`

England (principal classes), real: **£22.13bn (2013-14) -> £23.82bn
(2018-19) -> £24.63bn (2024-25)**, i.e. from 38.4% to 45.4% of NRE, while
real NRE fell 5.9%. Earmarked reserves did all the rising (£17.28bn ->
£20.39bn); unallocated fell slightly (£4.84bn -> £4.24bn). Per class the
shire districts are the outlier: SD reserves are now **162% of the class's
annual net spending** (£4.53bn vs £2.79bn). Frame as insurance against a
funding system that can move by double digits at a single settlement -
that reading stays within the data; "hoarding" or "prudence" would not.

### (d) Who lost most - `grant_settlement_league.csv`, `grant_class_arc.csv`

Real settlement funding per head, consistent panel, 2013-14 -> 2024-25
(`grant_class_arc.csv`): SD £83 -> £60, SC £369 -> £161, UA £619 -> £322,
MD £787 -> £458, LB £753 -> £403. England panel total: **£30.65bn ->
£17.74bn real, -42%**.

304 stable authorities matched on ONS code; 293 pass the completeness gate.
Clean within-class medians: **SC -56.6% (-£203/head), UA -47.5% (-£305),
LB -47.1% (-£324), MD -45.2% (-£318), SD -29.9% (-£25)**.

The percent league and the pounds league name different councils - use the
measure the caption states:

- **Percent, deepest (clean flags only):** North Tyneside MD -69.6%,
  Lewisham LB -69.2%, Wiltshire UA -69.2%, Staffordshire CC -60.1%,
  Bassetlaw SD -63.6%. (North Tyneside declines steadily across all three
  vintages but at nearly twice its class's post-2018 pace; prefer South
  Tyneside -52.6% for a bulletproof MD example.)
- **Pounds per head, deepest (clean):** Lewisham LB -£689, MD South
  Tyneside -£527, UA Middlesbrough -£484, SC Norfolk -£306, SD Bassetlaw
  -£85. Deprived places lost the most money; affluent places lost the
  biggest share of a smaller grant. Both are true; say which you mean.
- **The one that barely lost:** Westminster, -2.2% (-£20/head): its RSG per
  head fell £523 -> £172 but West End business-rates growth (£117 -> £684
  retained per head) filled the hole. That is a rates-boom story, not
  government generosity.
- **Districts:** the grant is simply gone - median district RSG **£3.57m in
  2013-14, £156k in 2024-25**. What replaced it is a business-rates
  lottery: 2024-25 retained-rates lines run p10 £1.9m / median £6.1m / p90
  £11.7m within the same class, and the only league gainers are
  logistics-growth districts (North West Leicestershire +197.7% - East
  Midlands Airport; Harborough +136.3%; North Warwickshire +87.1%; all
  flagged `gainer_rates_growth`). Host warehouses, win; host commuters,
  lose.

## The hand-check graveyard - what the naive versions lied about

- **Eleven authorities file a zero rates-retention line** with the money
  under collection fund, other items, or nowhere (East Herts books £14.4m
  as collection-fund surplus; Rugby £11.0m as other items; Watford and
  Central Bedfordshire's financing blocks simply don't add up to their
  NRE). The naive league called them "-99% cut". All excluded
  (`league_excluded`): Watford, Rugby, East Herts, Nuneaton & Bedworth,
  Guildford, Folkestone & Hythe, Hastings, South Derbyshire, Central
  Bedfordshire, Thurrock (2024-25); West Berkshire (zero in 2013-14, which
  killed its fake "+7.7% gain").
- **27 authorities file RSG = 0 with a live rates line** - exactly the
  enhanced-retention areas (all 10 Greater Manchester + 7 West Midlands
  mets, Liverpool City Region incl. Halton, Bristol/BANES/South Glos,
  Cornwall). Their 2024-25 rates baseline has other grants rolled in, so
  their "least cut" look (Manchester -26.9%, Halton -23.9%) is partly an
  accounting artefact. Flagged `rsg_zero_2024_check_rollin`; never headline
  them as least-cut.
- **Cliff after 2018** (`cliff_after_2018_one_year_check`): smooth decline
  to 2018-19 then a >50% real fall to 2024-25 - the shape of a one-year
  booking event (appeals provisions, deficit netting), not a policy arc.
  Catches Cheshire West (-82.5%), Wokingham (-74.3%), Gloucestershire CC
  (-84.4%), Hertsmere, Bromsgrove, Surrey Heath, Mid Sussex and other
  near-zero districts. Don't name them; the class medians don't need them.
- **CTR/NRE breaks on investment-income districts**: Woking's 2024-25 NRE
  is *negative* (-£21.6m); Runnymede's is £1.2m against a £6.8m CTR (share
  "547%"); Mid Suffolk "331%", Basingstoke "250%", Waverley "140%". Their
  commercial income nets NRE toward zero, so the financing-share measure
  exists precisely for them - and on it they are unremarkable (Woking
  66.4%, Runnymede 71.1%). All flagged.
- **2018-19 is a pilot-polluted midpoint**: London's one-year 100%
  retention pilot puts Westminster at £900/head retained rates in 2018-19.
  The settlement measure absorbs it (RSG+rates), but never read 2018-19
  RSG alone.
- **The £47->63p headline excludes the GLA** (class O, as in REPORT.md), so
  it understates what Londoners' full bill covers (the GLA precept is on
  top). Say "councils", not "local government".
- 2013-14 has no separate council-tax collection-fund line (it sits inside
  other items) - `collection_fund_ct` is 2018-19/2024-25 only; the
  financing-share denominator is unaffected (both routes sum the block).
- Standard caveats carried over from REPORT.md: GDP deflator is not a
  council cost index; the NRE definition absorbed rates retention across
  the period (both endpoints are in-scheme, pre-2013 comparisons would not
  be fair); 2024-25 is one un-smoothed year; no partisan claims possible
  from this build.

## Files

| file | for |
|---|---|
| `ct_share_england.csv` | (a) England arc, both share bases, real £bn |
| `ct_share_by_class.csv` | (a) per-class arc (settlement column here is un-gated; use grant_class_arc for settlement) |
| `ct_dependence_2024_25.csv` | (b) map/hex colouring, within class, flags included |
| `reserves_arc.csv` | (c) England + per-class reserves, earmarked/unallocated split |
| `grant_settlement_league.csv` | (d) per-authority league, components, `league_excluded` + `handcheck` flags |
| `grant_class_arc.csv` | (d) class arc, consistent 292-authority panel |

## Caption options (Joined Up voice)

**V1 - the share arc (England line + class small multiples)**
1. "In 2013, council tax paid for 47p of every pound your council spent.
   Today it pays 63p. Your bill didn't rise because councils got greedy -
   it rose because Whitehall left."
2. "Austerity didn't cut your council tax. It moved the bill to you: 47p in
   the pound in 2013, 63p now - while the money councils actually spend
   fell 6% in real terms."
3. "Shire counties now raise 76p of every pound they spend from council
   tax, up from 58p in 2013. The state didn't shrink the need. It shrank
   its share."

**V2 - the dependence map (colour: ct_share_financing_pct, within class)**
1. "How much of your council's budget comes off your bill? Manchester: a
   third. Harrow: four pounds in five. Same country, same duties, wildly
   different deals."
2. "The map of council-tax dependence is the map of deprivation, inverted
   (rho -0.9 among unitaries): the poorer the place, the more its budget
   still hangs on a settlement Whitehall can rewrite every year."
3. "Richmond funds 83% of its council from residents' bills; Westminster
   27%. Where business rates boom, the bill stays light."

**V3 - the reserves arc**
1. "Councils banked £2.5bn more in real terms while cutting services.
   Not greed - insurance. When your funding can vanish at a single
   settlement, you save like it's going to rain."
2. "£24.6bn now sits in council reserves, up from £22.1bn in 2013 in
   today's money. A funding system this volatile taught councils to hoard
   the roof money while it rained."
3. "Shire districts now hold 1.6 years of their entire net budget in
   reserve. That's what a decade of funding roulette does to public
   bodies: they stop spending and start bracing."

**V4 - the who-lost-most league (within class; state £ or %)**
1. "Since 2013, the government's core funding for councils fell 42% in real
   terms. Lewisham lost £689 per resident per year. Westminster - floated
   on West End business rates - lost £20."
2. "Counties lost the biggest share (median -57%). London boroughs lost the
   most money (median -£324 per head). Nobody outside a handful of
   warehouse districts gained."
3. "£689 per person per year: the central funding Lewisham no longer gets.
   Multiply by a family of four and ask what the council tax rise was
   actually replacing."

**V5 - the district lottery (RSG collapse vs rates spread, SD only)**
1. "The median shire district got £3.6m of Revenue Support Grant in 2013.
   Last year: £156,000. The grant system for districts wasn't cut - it was
   abolished in all but name."
2. "What replaced the grant? A lottery. Host East Midlands Airport's
   warehouses and your funding triples; host commuters and it goes to
   almost nothing. Need doesn't decide anymore - rateable floorspace does."
3. "North West Leicestershire's central funding is up 198% since 2013.
   Hyndburn, one of England's poorest districts, still gets £23 a head of
   Revenue Support Grant - the median district gets £1.25. That's not a
   grant system. That's a memorial to one."

Caption 3 of V3 uses the SD 162% figure - keep the "of their own class's
net budget" qualifier if used. V5 caption 3: Hyndburn RSG per head 2024-25
is £23.49 (the class maximum is £26.88), SD class median £1.25 - both from
`grant_settlement_league.csv` RSG columns over the dependence file's
populations.
