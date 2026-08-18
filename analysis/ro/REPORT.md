# What different councils spend on the same things - RO substrate

**Status: analysis note on the correct substrate. Transaction-level comparison was tested and rejected earlier (9 of 361 councils parse, per-council expense vocabularies); this build uses MHCLG's Revenue Outturn (RO) statistics, where every English council reports the same statutory service categories every year - uniform by construction.**

Every number traces to a script here: page discovery `00_discover.py`, attachment listing `01_list_attachments.py`, fetching `02_fetch.py` -> `manifest.json`, parsing `03_parse.py` -> `ro.sqlite` + `provenance.json`, analysis `04_analyse.py` -> `ro_per_head.csv` / `distributions.csv` / `england_real_arc.csv` / `county_dispersion_*.csv` / `analysis_out.json`, this report `05_findings.py` -> `findings.json`. Raw workbooks in `raw/` (gitignored), 12.9 MB total against a 1.5 GB cap.

## What was fetched

Three vintages of three workbooks each, from the gov.uk collection the index's four `availability=webpage` catalogue entries forward to (Local authority revenue expenditure and financing, MHCLG):

| vintage | RS (financing+reserves) | RSX (service summary) | RO5 (cultural/env/planning detail) |
|---|---|---|---|
| 2013-14 (revised) | XLS, 3 sheets | XLS | XLS, 3 sheets (measures split across sheets) |
| 2018-19 | ODS | ODS | ODS |
| 2024-25 (latest) | ODS | ODS | ODS |

Companions: ONS mid-year population on the boundary set each RO year actually had - mid-2024 via nomis NM_2002_1 (TYPE423/424), mid-2018 and mid-2013 via archived ONS reference tables (`ukmidyearestimates20182018ladcodes.xls`, `ukmye2013.zip`), because **nomis deletes back-series values for abolished geographies** (41 English districts + Bournemouth/Poole return empty for 2013 on every TYPE); HMT GDP deflator (June 2026 QNA). All real-terms figures are 2024-25 prices (2013-14 x1.3693, 2018-19 x1.2692).

## Parse coverage and reconciliation

444 / 444 / 410 authorities parsed (2013-14 / 2018-19 / 2024-25, all classes); **principal councils 353 / 353 / 317, population joined for 100%** in every vintage. Sum of authority rows vs each workbook's own England row (Total Service Expenditure, net current expenditure): **exact in 2013-14 and 2018-19; -£485.2m in 2024-25**, which is Cumberland - it filed no return (note `M`), its row is blank, and MHCLG's England row carries an unpublished imputation. One MHCLG typo corrected with the workbook's own sibling as witness: RSX 2018-19 codes North Yorkshire E10000022; ONS and RO5 2018-19 say E10000023. One structural trap caught by reconciliation: the 2024-25 CLASS BREAKDOWN block repeats the GLA with its real E-code (a class of one), which double-counted £7.3bn until deduplicated.

## Tier handling (on every table)

MHCLG's own Class column (SD/SC/UA/MD/LB); every comparison within one class; England arc sums the five principal classes and drops police+fire service lines (provision moved between principal councils and standalone authorities); class O never compared; City of London and Isles of Scilly excluded from distributions.

## The three strongest verified comparisons

**1. Same class, same city, 13x: libraries across London boroughs (2024-25).** Kensington & Chelsea £43.84/resident net vs Barking & Dagenham £3.35 - **13.1x**, and the gap survives the charging check (gross: £46.21 vs £4.04, 11.4x). Class median £14.66, p10-p90 £8.96-£27.72. Provenance: RO5_2024-25.ods / RO5_LA_Data_202425 / col 97 (Library service - Net Current Expenditure (C7 = C3 - C6)), rows by borough name; population ONS mid-2024.

**2. The arc: amenities cut, statutory child protection up (England, five principal classes, real 2024-25 prices per resident).** Libraries £20.44 -> £14.79 -> £12.00 (**-41.3%** since 2013-14); cultural -37.2%; highways & transport -43.1%; children's social care **+50.5%**; adult social care +16.0%; total service expenditure -4.6%. Libraries fell in **132 of 139** authorities that exist in both years (median -42.4%). Direction reconciles with NAO 2018 (cultural -34.9% for 2010-11 to 2016-17) and the IFS-documented acute-vs-amenity squeeze - cite them, this is confirmation on a longer window, not novelty. Education is in the table but must not be quoted as a cut: academisation moved schools off LA books.

**3. Children's social care tracks deprivation; libraries don't (2024-25, within class).** Spearman per-head-vs-IMD: CSC rho 0.567 (London), 0.442 (mets); libraries rho 0.036 / -0.051. The unitary extremes are the same story told by two councils: Blackpool £598.75/resident on children's social care vs North Yorkshire £136.14 (4.4x, class median £268.07). So "poor areas lost their libraries" is **NOT SUPPORTED** cross-sectionally - library spend simply doesn't correlate with deprivation either way.

Also provable: council tax carried 63.0p of every pound of net revenue expenditure in 2024-25, up from 47.0p in 2013-14; reserves (earmarked+unallocated, 31 March) rose real-terms £22.13bn -> £24.63bn while real NRE fell £57.66bn -> £54.27bn (RS lines; the NRE definition absorbed rates retention over the period - state that when quoting).

## 2024-25 within-class distributions (net £/resident, for context)

| class | service | n | p25 | median | p75 |
|---|---|---:|---:|---:|---:|
| LB | libraries | 32 | £10.62 | £14.66 | £18.81 |
| MD | libraries | 36 | £9.28 | £11.96 | £14.67 |
| UA | adult_social_care | 61 | £392.01 | £444.50 | £480.87 |
| UA | children_social_care | 61 | £236.51 | £268.07 | £336.30 |
| SC | highways_transport | 21 | £53.31 | £62.19 | £73.58 |
| SD | refuse_and_recycling | 164 | £21.28 | £26.46 | £33.61 |

## The hand-check graveyard - why the naive league table lies

Every eye-catching ratio was checked against the workbook's own gross/income columns before naming. Killed: **Hart DC "£0.67/head on waste"** (gross £69k; its £1.1m contract sits under Recycling - the combined refuse+recycling line is used instead); **Rugby £4/head** (garden-bin income nets off 78% of £2.25m gross); **Cambridge vs South Cambridgeshire 3.5x** (Greater Cambridge shared waste service - hosting arrangement, not frugality); **Blackpool's negative library line** (income £2.61m > spend £2.40m); **Enfield's £6 libraries** (income is 47% of gross - partly an artefact). Nuneaton & Bedworth's development-control NET is negative (fees exceed booked spend) while Stratford-on-Avon spends £32/resident gross running the county's biggest planning operation - a real 9.8x gross gap, but the mechanism is development pressure, so it is framed as department size, not efficiency.

## What a fair critic would still attack

1. **The deflator.** GDP deflator is not a council input-cost index; care wages rose faster, so +16.0% ASC overstates volume growth, and the amenity cuts understate lost provision.
2. **NCE follows booking choices.** Trusts (Sunderland's culture trust), shared services, recharges: any single authority's single line can mislead - that is why claims are made on distributions, gross-checked, and the graveyard is published.
3. **ASC includes NHS money** (Better Care Fund enters as income/transfers - workbook note 1), so ASC levels across councils partly reflect BCF flows.
4. **IMD is 2019-vintage** against 2024-25 spend, matched on stable LAD codes only; and rho~0 is no gradient, not fairness.
5. **2024-25 is one year.** Temporary accommodation (Westminster housing GFRA £558.20/resident vs LB median £126.52) and fee cycles swing single years; nothing here smooths.
6. **Politics is absent, deliberately** - no reliable open control dataset was fetched, so no partisan claims are made or possible from this build.

## Rebuild

```
python 00_discover.py         # gov.uk collection -> per-year outturn pages
python 01_list_attachments.py # content API -> attachments.json (sizes first)
python 02_fetch.py            # raw/ + manifest.json (HEADERS, <=2 req/s)
python 03_parse.py            # ro.sqlite + provenance.json + reconciliation gate
python 04_analyse.py          # csv outputs + analysis_out.json
python 05_findings.py         # findings.json + this report
```
