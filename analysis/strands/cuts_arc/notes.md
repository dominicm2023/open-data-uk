# Strand: what austerity actually cut

Chart-ready data for the England real-terms per-head arc by service, 2013-14 /
2018-19 / 2024-25. Everything here is recomputed by `build.py` (this
directory) from `analysis/ro/ro.sqlite` — the MHCLG Revenue Outturn substrate
built and reconciled in `analysis/ro/` (provenance chain in
`analysis/ro/REPORT.md`). No figure is copied from earlier findings; the
recomputation reproduced them exactly.

Run: `python build.py` (reads `../../ro/ro.sqlite`, writes the four CSVs).

**Method, once:** net current expenditure (nce) throughout; real terms = HMT
GDP deflator (June 2026 QNA), all figures in 2024-25 prices; population = ONS
mid-year estimates on each RO year's own boundary set; classes are MHCLG's own
(LB / MD / UA / SC / SD) and no number crosses a class; class O (police, fire,
combined, GLA) never enters; `refuse_and_recycling` is the synthetic
collection+recycling sum (councils split the same bin lorry between the two
lines differently). Cumberland filed no 2024-25 return and is excluded from
2024-25 aggregates (spend and population). City of London and Isles of Scilly
stay in aggregates (negligible) but are excluded from the per-authority
distribution.

## Files

### 1. `arc_dumbbell.csv` — the headline slope/dumbbell (visual A)

One row per service: England aggregate real £/head at the three vintages plus
`change_pct_2013_2024`. England aggregate = sum over the five principal
classes; denominator is England population (the five classes tile England —
for upper-tier services like libraries this is the library-responsible-tier
aggregation, since SC+UA+MD+LB areas cover the country and shire districts
report zeros). Recomputed headline: **libraries -41.3%, highways & transport
-43.1%, culture -37.2%, planning -7.5%; children's social care +50.5%, adult
social care +16.0%; total service expenditure -4.6%.**

**Education carries a mandatory caveat (in the `caveat` column): -19.3% is
NOT a cut — academisation moved schools off LA books. Never quote it as a
cut; drop the row or grey it with the caveat visible.** Public health
(+10.2%) started as a new grant in 2013-14 (base year is a ramp-up).

### 2. `class_service_small_multiples.csv` — class × service × year (visual B)

Long format: `cls, cls_label, service, service_label, year, real_per_head,
n_authorities, caveat`. 63 class×service combos × 3 years (14 services;
combos a class does not deliver — under £1/head in all three years, e.g.
SD × adult_social_care — are dropped). Class per-head = class spend sum /
class population sum (authorities that filed).

**Composition caveat (state on the visual):** class membership changes across
vintages — 2019-2023 reorganisation moved Buckinghamshire, Northamptonshire,
Cumbria, North Yorkshire, Somerset, Dorset and Bournemouth/Poole areas from
SC+SD (or small UA) into new UAs. Filed counts: SC 27→27→21, SD 201→201→164,
UA 56→56→62 (63 minus Cumberland). Each class series describes *the areas
governed by that class in that year*, so SC/SD/UA level shifts partly reflect
membership churn; the LB and MD panels are clean (33 and 36 throughout).

### 3. `care_share.csv` — "care eats the budget" (visual C)

Per class × vintage: ASC, CSC and combined care share of total service
expenditure, plus the residual civic share, plus real £/head levels for a
stacked-area rendering. Denominator is **TSE minus fire & police service
lines** (fire responsibility moved between councils and standalone
authorities over the period; the column
`care_share_pct_of_reported_tse` shows the unadjusted number — the choice
never moves the share by more than 0.5pp).

Care share of the service budget, 2013-14 → 2018-19 → 2024-25:

| class | 2013-14 | 2018-19 | 2024-25 |
|---|---:|---:|---:|
| Shire county | 32.3% | 38.4% | 41.6% |
| Unitary | 29.1% | 36.5% | 40.5% |
| Met district | 27.2% | 32.9% | 38.5% |
| London borough | 27.0% | 30.9% | 32.7% |
| Shire district | 0.4% | 0.5% | 0.6% |

Shire districts are structurally ~0: social care is the county's statutory
duty in two-tier areas. Show SD separately or omit with a note — never on the
same axis as an implied "SD does no care work by choice".

### 4. `authority_change_distribution.csv` + `authority_change_summary.csv` — the distribution (visual D)

Per-authority real per-head change 2013-14 → 2024-25 for libraries and
children's social care, **stable authorities only** (same ONS code filed in
both vintages), classes SC/UA/MD/LB, City of London & Isles of Scilly out.

Exclusions, stated: of 150 upper-tier authorities in 2013-14, **8 were
excluded because reorganisation abolished their code** (Bournemouth, Poole,
Buckinghamshire CC, Cumbria CC, Dorset CC, Northamptonshire CC, North
Yorkshire CC, Somerset CC — Cumberland's non-return is inside the Cumbria
exclusion). Data guards (from the ro build): libraries need a credible base
(≥£2/head in 2013-14) and a positive 2024-25 line — this drops **3 more**
(Blackpool: 2024-25 income exceeded spend, line negative; Luton and Wigan:
2013-14 base ≤£0.01/head, service not on that line). CSC guard (base
≥£10/head) drops none.

Summary (in `authority_change_summary.csv`):

| service | stable n | fell | median | p25 | p75 |
|---|---:|---:|---:|---:|---:|
| libraries | 139 | **132** | **-42.4%** | -54.0% | -25.9% |
| children's social care | 142 | 3 | **+52.9%** | +28.4% | +77.4% |

Extremes for annotation: deepest library cuts Barking & Dagenham -86.3%,
Enfield -78.9% (income artefact caveat from the ro graveyard — say "partly
charging"), Slough -78.6%, Sunderland -77.3% (culture-trust caveat);
growers exist (7 of 139; Salford +56.2%). CSC: only Southwark, Hammersmith &
Fulham and Slough fell; top risers Tameside +161.3%, Hartlepool +147.0%.

## What a fair critic says (carry to every visual)

- **The deflator.** GDP deflator is not a council input-cost index; care
  wages outran it. So the ASC/CSC "rise" overstates extra service volume, and
  the amenity cuts *understate* lost provision. This cuts in our favour on
  amenities and against us on care volume — say so.
- **NCE follows booking choices.** Trusts, shared services and charging move
  single lines (Enfield, Sunderland above). Claims ride on distributions, not
  single councils.
- Direction reconciles with NAO 2018 and the IFS acute-vs-amenity literature —
  cite as confirmation on a longer window, not novelty.
- No politics: no reliable open control dataset in this build; no partisan
  claims possible.

## Caption options (Joined Up voice)

**Visual A — the dumbbell:**

1. "Twelve years of council budgets in one picture. Libraries -41%. Highways
   -43%. Culture -37%. Children's social care +50%. The money didn't
   disappear — the everyday council was cut to pay for the crisis council."
2. "Since 2013, councils in England have had 4.6% less to spend per person in
   real terms. Look where it came from: the library, the road, the museum.
   Look where it went: children's social care, up 50%."
3. "Austerity didn't shrink your council evenly. It hollowed out everything
   you could see — libraries, roads, culture — while the statutory care bill
   grew 50%. Both halves of that are the same policy."

**Visual B — small multiples:**

1. "Five kinds of council, one shape: care up, everything civic down. From
   London boroughs to shire counties, the same twelve-year squeeze."
2. "It doesn't matter which England you live in — met, borough, county,
   unitary — your council traded the visible services for the statutory
   ones. Every panel, same slope."
3. "Same duty, same direction: every class of English council cut libraries,
   culture and roads per person in real terms while children's social care
   climbed. This is structure, not local mismanagement."

**Visual C — care share:**

1. "In 2013, shire counties spent 32p of every service pound on social care.
   Now it's 42p — and rising in every class of council. Care is eating the
   budget that used to run everything else."
2. "The quiet takeover: adult and children's social care now take about £2 in
   every £5 counties and unitaries spend on services, up from less than £1.50
   in 2013. The civic remainder is what's left for everything you can see."
3. "Councils aren't choosing care over libraries — the law chooses for them.
   Care's share of the service budget is up in every single class of council
   since 2013."

**Visual D — the distribution:**

1. "This isn't a few bad councils. 132 of the 139 English authorities we can
   track cut real per-person library spending since 2013 — the median cut is
   42%. Meanwhile children's social care rose in 139 of 142."
2. "Name a council that protected its libraries. There are seven. The other
   132 cut, half of them by more than 42% per person in real terms."
3. "Every dot is a council. Almost every library dot fell; almost every
   children's-care dot rose. When the whole distribution moves, the cause
   isn't local."

(If education is shown anywhere, the caveat is not optional: academisation
moved schools off council books — the -19% education line is an accounting
migration, not a cut.)
