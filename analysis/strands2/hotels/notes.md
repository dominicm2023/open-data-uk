# THE HOTEL BILL — homelessness and temporary accommodation money flowing to hotels and private landlords

Strand dir: `analysis/strands2/hotels/`. All corpus numbers exclude cross-file duplicates (`is_dup=0`).
Method per ground rules: pattern-match generously, eyeball every matched string, list exclusions, ship every number with its query.

**Reproduce:** `python make_work_db.py` (rebuilds `work.sqlite`, a ~318MB derived cache kept out of the repo per project convention), then `python build_outputs.py` (regenerates every CSV below). All queries are in those two scripts; extra one-off queries quoted inline.

---

## Headline verdicts

| # | Claim | Verdict |
|---|-------|---------|
| 1 | Bristol paid a Holiday Inn ~£4.3M, in two waves: COVID "Everyone In" (2020) and a bigger 2023-24 wave coded "Room Hire" | **PROVABLE NOW** |
| 2 | Bristol's nightly-paid/B&B TA line ("TPP - B&B payments to landlords") runs ~£20M/yr, ~£86M since 2020, and names every landlord | **PROVABLE NOW** |
| 3 | Uttlesford TA rose ~10x — verified at **11.5x** (£56k FY2019-20 → £642k FY2025-26), datable to two jumps: FY2022-23 and FY2024-25→25-26 | **PROVABLE NOW** |
| 4 | Rushmoor B&B placements tripled in two years (£58k FY2023-24 → £257k FY2025-26) and now include a Travelodge paid monthly | **PROVABLE NOW** |
| 5 | National hotel chains are the main recipients of TA money | **MISLEADING AS FRAMED** — in our ledgers the chain census is small (£8.4M total across all 77 publishers, most of it staff travel); the big TA money goes to *local* private landlords, guest houses and agents |
| 6 | "TA is the fastest-growing housing line nationally" tested in RO data | **NOT SUPPORTED from our extract** — our RO holdings are service-level only (`housing_gfra`), no TA sub-line exists in `ro.sqlite`/`ro_per_head.csv`. The enclosing line is consistent with it (England gross housing GFRA +27% real per head 2018-19→2024-25) but cannot isolate TA. Null with receipt. |
| 7 | Home Office asylum-hotel spending | **DARK AFTER JUNE 2018** — restated with receipt below. We can see the COMPASS-era providers to mid-2018 and a 2012 airport-hotel block-booking episode; the 2019-25 asylum-hotel era is invisible in our ledgers. |

---

## (a) Hotel-chain census — `hotel_chain_census.csv`

Census across all 77 publishers, per publisher per year. Include/exclude lists eyeballed string-by-string:
`hotel_census_included_strings.csv` (237 strings), `hotel_census_excluded_strings.csv` (68 strings).

Totals (all publishers, all years in ledger):

| Chain | txns | £ |
|---|---|---|
| Holiday Inn / IHG | 854 | **6,715,750** |
| Ibis / Novotel / Mercure (Accor) | 324 | 962,182 |
| Premier Inn / Whitbread | 124 | 583,846 |
| Travelodge | 79 | 77,678 |
| Britannia Hotels | 7 | 38,944 |

- **Holiday Inn / IHG is the only chain with material TA money**, and almost all of it is one payer: Bristol City Council, £4.28M to a bare "HOLIDAY INN" supplier string, 2020-2024 (see (a.1)). The rest is departmental staff travel (purchase-card strings like `PREMIER INN44521710 PLYMOUTH`) plus the Home Office's 2012 airport-hotel episode (see (d.2)).
- **Britannia Hotels** — the chain most criticised for asylum hotels — appears just 7 times, £38.9k, all staff travel (MoD 2012, UKTI). Their asylum income is Home Office money after our ledger goes dark. Null worth stating.
- Travelodge's only non-travel use is Rushmoor's B&B placements (below).
- Eyeballed exclusions (worth keeping for the traps file): `SAMUEL WHITBREAD ACADEMY/COMMUNITY COLLEGE` (£61.4M of DfE school funding, not Whitbread plc), `WHITBREAD PLC` at DfE (£529k, 2017-19 — apprenticeship/training grants to Whitbread as an employer-provider, coded `Training`/`ESFA ADULT APPRENTICESHIPS`, not hotel stays), `ACCORD HOUSING ASSOCIATION`/`GREENSQUAREACCORD`/`ACCORA LTD` (housing associations/care equipment, £25M+), `ACCOR SERVICES`/`EDENRED` (voucher business, ~£1.75M — historically Accor group but not hotels), `IBISWORLD` (market research), `IBIS DANIDA FRAME CEDI`/`IBIS DAKAR` (DFID rows, likely the Danish NGO IBIS, ambiguous — excluded), `BRITANNIA FIRE`/`PARKING`/`PRIMARY SCHOOL` etc., `HILTON`/`CHILTON` schools and nursing companies, `HILTON ABBEY LTD` at Greenwich (£1.75M — HRA refurbishment contractor, not Hilton hotels). Hilton, Marriott, Best Western were pattern-checked too: overwhelmingly staff travel, no TA use found; not included in the census CSV.
- **Expense-type-side traps** (census in `cand_expense_types.csv`): MoJ/Wales Office `532xxx-TA GBV ...` lines (£23M+) are **Tangible Assets Gross Book Value** account codes, not temporary accommodation; DWP `TA LPS BACS Payments` (£16.4M) is balance-sheet manual payments; Tate `Temporary Accommodation` (£527k) is Hewden Stuart plant/portacabin hire during gallery works. Uttlesford's `Radisson Blu Stansted` rows (£95k) are airport-consultation and Covid emergency codes, not TA — excluded from the hotel reading.

### (a.1) Bristol × Holiday Inn — `bristol_holiday_inn_monthly.csv`

Two distinct waves, different codings:

- **Wave 1 — "Everyone In": Apr-Nov 2020, £1,095,598**, expense_type `TPP - Accommodation Based Support`. Monthly block payments £88k-£198k. This is the COVID rough-sleeper hotel programme, visible line-by-line.
- **Wave 2 — Nov 2023-Apr 2024, £3,177,375 in six months**, mostly coded **`Room Hire`** — £1,200,467 in December 2023 alone (5 payments, avg £240k/invoice: whole-hotel block-booking scale). £537,530 of the November payments coded `TPP – Supported Accommodation`.
- The ledger never names which Holiday Inn site, and "Room Hire" is the same code Bristol uses for £500 meeting rooms. A £1.2M month under "Room Hire" is a finding about coding as much as spending.

Query: `SELECT year_month, COUNT(*), SUM(amount) FROM transactions WHERE is_dup=0 AND publisher='Bristol City Council' AND UPPER(supplier_raw) LIKE '%HOLIDAY INN%' GROUP BY 1`.

## (b) The landlords and agents — `bristol_ta_suppliers.csv`, `uttlesford_ta_suppliers.csv`, `rushmoor_bb_suppliers.csv`, `greenwich_lettings_probe.csv`

**Bristol, `TPP - B&B payments to landlords`, £85.7M over 22,765 payments (Jan 2020-May 2026)** — the fullest named register of nightly-paid TA providers we hold:

| Supplier | £ |
|---|---|
| CONNOLLY & CALLAGHAN LTD T/A BRISTOL FAMILY HOUSING | 17,332,607 |
| ALEX FRY RENTAL PROPERTIES LTD | 15,996,188 |
| CENTENNIAL PROPERTY LTD T/A THE HOUSING NETWORK | 10,429,231 |
| HOMES 4 ALL | 9,113,572 |
| DESIGNZ LTD | 6,457,684 |
| TOP DRAWER PROPERTIES | 3,794,343 |
| ASHLEY GUEST HOUSE LTD | 2,687,149 |
| (33 suppliers ≥£20k in CSV) | |

- **Cross-council, cross-decade echo:** Connolly & Callaghan (£197,310), Ashley Guest House (£75,672) and Bristol Housing & Support (£28,229) were already South Gloucestershire's top `Bed & Breakfast` suppliers in **2010-11** (`council_ta_lines.csv` window). The same private TA providers span two councils and fifteen years.
- **One oddity kept visible:** TRAVELPERK UK IRL LTD — a corporate travel-booking platform — took a single £646,571 payment (plus £7,218) inside Bristol's B&B-to-landlords line in June 2024, i.e. hotel block-booking routed through a travel platform, with a matching £129,314 `Input VAT` row. Whichever hotels received it are invisible behind the platform.
- Uttlesford's TA is **hotel-heavy**: DE SALIS HOTEL £743,701 (Hayes, from Dec 2020), OASIS HOTEL HARLOW £454,400, SKYLINE HOTEL £103,696, GEORGE (BISHOP STORTFORD) HOTEL £51,075, STANSTED AIRPORT LODGE £49,067 — plus one managing agent, NICKOLDS HMO MANAGEMENT & MAINTENANCE £535,845 (from Jan 2023).
- Rushmoor's is **guest-house-heavy**: ASHBEE GUEST HOUSE £731,483 across 15 years (2011-2026), ANNIES GUEST HOUSE £152,730, AIRPORT LODGE (two entities) £221,643, then from 2024 letting agents appear (MYLONDONLETS £37,740, LUCENT LEASES, KB REAL ESTATE) and from Mar 2025 **Travelodge Business £44,388** under expense_type `Bed and Breakfast`.
- **Greenwich (2012-2017) hides its TA**: only 2 rows ever say "Temporary Accommodation" (£5,509). But lodges and letting agents sit under `Rents Other / Housing Services`: HOUSE TO HOME LETTINGS £434,104, ASSETGROVE LETTINGS £115,494. Others that pattern-matched (Melba Lodge £426k, Meadow Croft Lodge £373k) turned out on eyeball to be adult social care and children's services placements — kept in `greenwich_lettings_probe.csv` with their codings, NOT claimed as TA. Verdict for any Greenwich TA number: **MISLEADING AS FRAMED** — the coding cannot isolate it.
- North Yorkshire codes TA as `321060 ... Temporary Accommodation - Unsupported` and `321021 ... Homeless Support`: £1.94M total 2022-2026, mostly to FOUNDATION housing charity (£1.13M) and HOMEMORE LTD (£434k); one seaside hotel (THE SELBOURNE HOTEL, Scarborough, £20,825).

## (c) The RO join — `england_housing_gfra.csv`, `payers_housing_gfra.csv`, `england_service_real_growth.csv`

All real figures in 2024-25 prices (GDP deflator from `ro.sqlite`; base checked against `ro_per_head.csv` ratio = 96.6694/70.5952). England per-head figures divide by billing-authority population only (SD+LB+MD+UA: 53.9M/56.0M/58.6M — summing all classes double-counts two-tier residents).

**England, housing GFRA, real £ per head:**

| measure | 2013-14 | 2018-19 | 2024-25 |
|---|---|---|---|
| gross | 76.67 | 71.06 | **90.51** |
| income | 25.73 | 33.83 | 37.14 |
| nce | 50.93 | 37.22 | 53.38 |

- Gross housing spend per head fell to 2018-19 then rose **+27% real in six years** — nationally consistent with the TA surge (TA is the biggest growing component of housing GFRA), but our extract has no TA sub-line, so the claim "RO data shows TA is the fastest-growing housing line" is **NOT SUPPORTED from what we hold** — receipt: `SELECT DISTINCT service FROM service_nce` returns 20 service-level lines, none below `housing_gfra`.
- In the all-service ranking (`england_service_real_growth.csv`), housing_gfra NCE is **+4.8%** real per head 2013-14→2024-25 — mid-table, far behind children's social care (+50.5%). But NCE nets off housing-benefit income; the gross line (+18% over the same span, +27% from the 2018-19 trough) is where TA pressure shows. (An earlier draft said +9.4% here; the CSV and an independent recomputation both say +4.8%.)
- **The payers we hold mostly show the squeeze, not the surge** (`payers_housing_gfra.csv`, gross real £/head 2013-14 → 2024-25): Bristol 102.71→110.68 (up), but Uttlesford 27.18→**14.18** and Rushmoor 43.14→**27.37** — falling *while their own ledgers show TA spend multiplying*. Their total housing line shrank around the growing TA core. That's the sharper, defensible story: TA is eating what's left of district housing budgets.
- Eden and Harrogate have no 2024-25 row (abolished 2023); North Yorkshire 2024-25 is the successor UA.

## (d) Uttlesford ×10 — VERIFIED at ×11.5 — `uttlesford_ta_fy.csv`

TA lines: `HOMELESSNESS - ACCOMMODATION` + `TEMPORARY ACCOMMODATION - THIRD PARTY` (new code from Apr 2025) + `BED & BREAKFAST THIRD PARTY - TEMP ACCOMM`. Ledger covers exactly FY2019-20 to FY2025-26 — all seven FYs complete.

| FY | txns | £ |
|---|---|---|
| 2019-20 | 62 | 56,020 |
| 2020-21 | 111 | 140,676 |
| 2021-22 | 116 | 153,284 |
| 2022-23 | 143 | 268,417 |
| 2023-24 | 271 | 231,462 |
| 2024-25 | 340 | 472,609 |
| 2025-26 | 531 | **641,990** |

- **11.46x nominal in six years** (~9.7x real at 2024-25 prices). Payment count grew 8.6x, so this is volume, not price alone. Dated: first doubling by FY2022-23; the steep leg is FY2024-25→FY2025-26.
- Trap check: it is not a transparency-threshold artefact — the lines include payments well under £250 in all years.
- Robustness (`uttlesford_ta_by_fy.csv`): the table above **excludes** Uttlesford's separate `Emerg Accommodation - Ukrainian Refugees` line (£290k across FY2022-23→FY2025-26, much of it also to De Salis Hotel). Including it, FY2024-25 is £616k and the multiple is ~11.7x — the finding does not depend on the exclusion. Named hotels take £279k-£373k of the recent FYs.

## (d.2) Home Office — the null, restated with its receipt — `home_office_asylum_receipt.csv`, `ho_relabeling_receipt.csv`

- **The Home Office ledger in our corpus stops at June 2018** (`SELECT MAX(year_month) FROM transactions WHERE publisher='Home Office'` → `2018-06`). Every asylum-hotel year that made national news (2019-2025, Britannia et al.) is invisible to us. We do not imply we can see it; we can only show what the ledger held before it went dark.
- **The labels went dark before the ledger did.** Asylum-labeled expense lines (`%asylum%`/`%refugee%`) run £14M-£81M a month to 2016-10, then almost vanish — 2017 has asylum-labeled rows in only three months — while overall Home Office publishing continues at ~1,000 rows/month to 2018-06 (`ho_relabeling_receipt.csv`). The same contractors keep getting paid, but under generic labels: `Business Process Outsourcing`, `Detention Centres`, `Public Order & Security Services` (`ho_relabeling_contractor_labels.csv`, from `05_ho_relabeling.py`). By fiscal year the asylum-labeled series reads FY2016-17 £223.5M → FY2017-18 £9.7M (`home_office_asylum_by_fy.csv`) — a label collapse, not a spending collapse, and the reason our pre-2018 asylum totals are floors, not totals.
- What it held: **Clearsprings** (Management → Ready Homes) £94.1M 2010-2018 with expense codings that literally read `Asylum accom Sec 95`, `Asylum accom Sect4 Accom`, `Asylum accom Sect 98`; **Serco** £418.8M and **G4S** £407.9M across all Home Office work 2010-2018 (COMPASS asylum contracts *plus* detention/justice — the ledger's codes do not split them, so we do not attribute those totals to asylum alone; Clearsprings is the clean asylum-only provider).
- Clearsprings anomalies kept honest: zero rows in 2013-14 (gap, not necessarily zero payment) and 2017 nets to **-£12.7M** (8 rows, large credit notes).
- **The 2012 airport-hotel episode**: the Home Office paid hotels directly — SERENA INVESTMENTS LTD T/A HOLIDAY INN EXPRESS T5 £449,308 (one invoice of £396,976), THISTLE HOTEL LONDON HEATHROW £369,489, HOLIDAY INN EXPRESS CRAWLEY-GATWICK £147,200, RADISSON BLU STANSTED £142,230, HOLIDAY INN GATWICK £117,300, HIX FOLKESTONE £73,440, HIX LUTON £56,430 — **£1.36M of direct airport-hotel block-bookings in calendar 2012**, coded `Travel & Food & Lodging.UK- Hotel Accommodation` and (for Crawley) `Hotels Personnel- Admin.Overseas Hotel Accom`. The ledger does not state the purpose; 2012 was the Olympics year and also an asylum-overflow year, so we describe the payments, not the reason.

---

## Strongest objections a critic would make

1. **"Nine councils isn't England."** Correct, and we never total across publishers. Every council number is per-payer, named. The England claim rests only on RO data, which is every English council.
2. **"Bristol's £85.7M B&B line isn't all hotels."** True — it's nightly-paid TA to private landlords and agents, which is the point of the strand: the money goes to Connolly & Callaghan, not Travelodge. We keep chain and landlord findings separate.
3. **"Room Hire could be conferences."** At £500 it is; at £1.2M/month to "HOLIDAY INN" during a declared housing-pressure winter it isn't — but we flag that the ledger itself doesn't say "homelessness" on those rows, and Bristol's own coding switched mid-wave (`TPP – Supported Accommodation` → `Room Hire`). We print the coding, both waves, and let the reader see it.
4. **"Bristol's ledger has holes."** Yes: 2021 is entirely absent and 2022 starts in June (`bristol_tpp_bb_fy.csv` carries a months_in_ledger column). We never interpolate across the hole; FY comparisons use complete FYs (2023-24 £21.1M, 2025-26 £19.0M).
5. **"Uttlesford's rise could be recoding."** The two accommodation codes are counted together across the whole span, payment counts rise in step with £, and sub-£250 rows exist throughout — it's volume.
6. **"Serco/G4S totals aren't asylum."** Agreed — stated in the file and above; only Clearsprings is claimed as asylum accommodation.
7. **"RO gross includes housing benefit admin and other non-TA lines."** It does; that's why the RO claim is limited to "consistent with", and the TA-specific claim is marked NOT SUPPORTED from our extract.

## Caption drafts (Joined Up voice)

1. **"One Holiday Inn, £1.2 million, one December."** Bristol's ledger calls it "Room Hire". Families without a home call it Christmas. Councils are block-booking hotels because there's nowhere left to put people — and the spending line barely admits it's happening.
2. **"The council that pays a guest house £731,483."** Fifteen years of Rushmoor's ledgers show homelessness money flowing to the same B&Bs, the same lodges — and since March 2025, a Travelodge, every month. Temporary accommodation is a permanent business now.
3. **"Uttlesford's homelessness hotel bill: up 11x in six years."** £56k in 2019. £642k last year — most of it to a handful of hotels near Stansted. A district of 92,000 people is quietly running a hotel operation because the housing system beneath it has gone.
4. **"£86 million to private landlords in one city."** Bristol names every landlord it pays for nightly-paid accommodation. Top of the list: one family firm, £17.3M since 2020 — a firm that was already top of the neighbouring council's B&B ledger in 2010. The crisis has incumbents.

## Files

| file | what |
|---|---|
| `hotel_chain_census.csv` | chain × publisher × year, £ and txns (eyeballed) |
| `hotel_census_included_strings.csv` / `hotel_census_excluded_strings.csv` | the eyeball, in full |
| `bristol_holiday_inn_monthly.csv` | the two waves, monthly, with codings |
| `bristol_tpp_bb_fy.csv` / `bristol_ta_suppliers.csv` | £85.7M nightly-paid line: FY arc (with coverage) + named landlords ≥£20k |
| `uttlesford_ta_fy.csv` / `uttlesford_ta_suppliers.csv` | the ×11.5, dated; the hotels |
| `rushmoor_bb_fy.csv` / `rushmoor_bb_suppliers.csv` | 16-year B&B arc; the guest houses |
| `council_ta_lines.csv` | every eyeballed TA/homelessness line per council we hold |
| `greenwich_lettings_probe.csv` | Greenwich's hidden TA — probe rows with codings, not claimed |
| `home_office_asylum_receipt.csv` | the null's receipt: Clearsprings/Serco/G4S/direct hotels by year, to 2018-06 |
| `england_housing_gfra.csv` / `payers_housing_gfra.csv` / `england_service_real_growth.csv` | RO join, real 2024-25 prices |
| `make_work_db.py` / `build_outputs.py` | full reproduction path from corpus.db |
| `ho_relabeling_receipt.csv` / `ho_relabeling_contractor_labels.csv` | the label collapse: asylum-labeled rows vs total HO rows by month; contractors' post-2016 labels (`05_ho_relabeling.py`) |
| `home_office_asylum_by_fy.csv` | asylum-labeled £ by FY, annotated (`06_replication_extras.py`) |
| `uttlesford_ta_by_fy.csv` | Uttlesford arc with the Ukraine line broken out (robustness) |
| `cand_expense_types.csv` | expense-type-side generous census, incl. the TA-GBV / TA-LPS / Tate traps |
| `01_census.py` / `02_drill.py` / `05_ho_relabeling.py` / `06_replication_extras.py` | independent replication pass (2026-08-18): one-pass census, eyeball drill, new receipts |

## Replication note (2026-08-18)

A second, independent pass re-derived the headline numbers from `corpus.db` and `ro_per_head.csv` without reading this file first. Everything material matched: Bristol B&B line £85.7M and FY arc to the pound; Dec-2023 Holiday Inn month £1,200,467 exact; Uttlesford ×11.5 (and ×11.7 with the Ukraine line included); Rushmoor FY arc identical once `Hostel Accommodation` (Society of St James, genuine TA, from Aug 2024) is included; England housing_gfra real per head 76.67/71.06/90.51 gross reproduced from the ro_per_head deflator ratios. One error found and fixed (NCE growth misquoted as +9.4%; correct +4.8%), and one new finding added (the Home Office label collapse, section d.2).
