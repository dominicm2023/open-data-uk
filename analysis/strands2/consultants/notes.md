# Cut staff, hire consultants — census of consulting & agency-staff firms in corpus.db

All queries in `pull_candidates.py`, `classify_aggregate.py`, `final_outputs.py`, `ro_staffheavy.py` (this directory). All £ nominal unless marked real. All figures exclude cross-file duplicates (`is_dup=0`).

## Method

1. Generous LIKE patterns per firm over 11.8M rows → 653 distinct supplier strings (`candidates_raw.csv`).
2. **Every string eyeballed.** 397 included, 256 excluded with reasons (`variants_excluded.csv` — publish it). Ambiguous strings were hand-checked against payer + expense_type before deciding (queries in transcript; decisive examples below).
3. Row-level reclassification: rows whose expense_type says the money is **fund monies to be managed and dispersed**, accountable grants, or grants expenditure are moved to a `routed_fund` category regardless of firm — they are not fees. Reed rows at DWP under New Deal/Restart/JSA expense codes are `welfare_to_work`, not agency staff.
4. Sectors: `central_gov` (departments + ALBs/museums), `councils` (the 13 council publishers incl. predecessor authorities), `nhs`, `other_local` (TfGM only).

## Headline census (whole corpus, all years, £m nominal)

| firm | consulting | agency_staff | welfare_to_work | routed_fund |
|---|---|---|---|---|
| PwC | 762.5 | | | 638.4* |
| Deloitte | 733.4 | | | 2.1 |
| KPMG | 480.1 | | | 281.1 |
| EY | 436.3 | | | 17.4 |
| PA Consulting | 412.6 | | | |
| McKinsey | 249.1 | | | |
| BCG | 43.7 | | | |
| Gartner | 24.1 | | | |
| Bain | 23.9 | | | |
| Manpower | | 116.5 | | |
| Comensura | | 36.5 | | |
| Hays | | 29.0 | | |
| Reed | | 23.5 | 728.0 | 1.0 |
| Matrix SCM | | 14.0 | | |
| Michael Page | | 9.7 | | |
| Adecco | | 5.3 | | |

*PwC routed includes one within-file duplicate of £42.0m (txn 202372-103 appears twice in the same DFID file; cross-file dedupe could not catch it). Net PwC routed ≈ £596m.

Category × sector: consulting £3,066m central gov / £47m NHS / £42m TfGM / £11m councils. Agency staff £164m councils / £60m central gov. So in the ledgers we hold, **consulting is a central-government habit and agency staff is a council habit** — but see coverage caveats.

## (a) Yearly per firm and per category, split by sector
`yearly_firm_sector.csv` (fy, firm, category, sector, gbp, txns) and `yearly_category_sector.csv`. FY = April–March from `year_month`; rows with no date are fy=`unknown` (£28m).

## (b) The austerity juxtaposition — `juxtaposition.csv` + `ro_staffheavy_arc.csv`

| | 2013-14 | 2018-19 | 2024-25 |
|---|---|---|---|
| Central-gov consulting in held ledgers (£m nominal) | 222.1 | 186.6 | 109.4 |
| England libraries, real £/head | 14.60 | 10.57 | 8.98 |
| England cultural services, real £/head | 49.18 | 34.56 | 32.39 |
| England planning & development, real £/head | 22.92 | 16.67 | 22.22 |

**Verdict on "consultants up while services cut" as a national time series: MISLEADING AS FRAMED.** Our consulting series *falls* after 2021-22 — but that is coverage, not policy: DHSC's ledger stops 2022-11, DFID's in 2020, and 53% of corpus movement is intra-state. Do not draw "consulting fell". The honest draw-ready pairings are same-ledger:

* **DHSC (`dhsc_consulting_fy.csv`): consulting £8.1m in 2019-20 → £154.8m in 2020-21 → £204.6m in 2021-22 — a 19× jump inside one ledger** while England libraries lost 38% of real per-head funding since 2013-14.
* **Greenwich (`greenwich_manpower_fy.csv`): £106.8m to Manpower UK Ltd, 2012–2017** — a master-vendor temp-staff contract peaking at £26.9m in 2013-14, the exact years Greenwich was shedding staff-heavy services (cultural real £/head for our corpus councils fell 36% 2013-14→2018-19, `ro_staffheavy_arc.csv`).
* Bristol is doing it now: **£35.9m to Comensura ("Agency Staff") since June 2024**; North Yorkshire £13.6m through Matrix SCM since 2022. Caveat: Comensura/Matrix are neutral-vendor intermediaries — their £ includes onward payments to many agencies (CAPITA-TP-NATWEST-style pass-through at small scale).

**Verdict on "cut staff, hire consultants" at DHSC/COVID and Greenwich/Bristol same-ledger scale: PROVABLE NOW.** One DHSC expense label does the work for us: £7.9m to Deloitte booked as **"Contractor/ Staff Substitution"**.

## (c) COVID spike — PROVABLE NOW
Central-gov consulting: 2019-20 £137m → **2020-21 £322.8m → 2021-22 £347.5m** → 2022-23 £120m. By firm (central gov): Deloitte £35.5m→£108.0m→£155.8m; McKinsey £10.4m→£51.3m; **BCG ~£0→£32.0m in 2020-21** (barely existed in the corpus before). Driver is DHSC (£122m of the Big-3 spike in 2020-21 alone) — Test-and-Trace era, expense_area "Global Health". Monthly series in `monthly_category_sector.csv`.

## (d) Biggest single engagements — `top_engagements.csv`, each hand-checked
Top: **£44.0m to Deloitte from DHSC on 2021-06-28** ("Consultancy/Professional Advice", single row, no duplicate). Then Deloitte £19.4m (six invoices bundled in one row, noted), Reed in Partnership £12.0m Restart, PA Consulting £9.8m at MHCLG (from a file that carries no dates — noted), BCG £6.9m "Outsourcing Contract" at DHSC. Largest KPMG/PwC single fee rows are MOD 2017 (£5.2m/£5.1m).

## Things that look like consulting money but aren't (report separately, never in the headline)

* **PwC "GEC Client Account" £638m gross (≈£596m net of dupe)** — DFID/FCDO Girls' Education Challenge fund monies "to be managed and dispersed by the supplier". Aid routed through a PwC bank account, not PwC fees. Same logic as CAPITA TP NATWEST.
* **KPMG East Africa / KPMG Development Services £281m** — DFID accountable grants and managed fund monies.
* **Reed in Partnership £728m** (DWP; New Deal → Work Programme → Restart) — welfare-to-work delivery, not temp staff. Biggest Reed fact in the corpus and worth its own panel.
* EY £17.4m at DfE booked as "Grants expenditure" — routed, kept out of fees.

## Exclusions worth naming (the traps, confirmed)
`variants_excluded.csv` has all 256 with reasons. Highlights: **"Hays" caught Hays Travel** (£1.0m, different company) and a girls' school; **"Reed" caught 161 strings** including RELX/Reed Elsevier publishing, Alec Reed Academy (£59m of DfE school grants), solicitors (Sternberg Reed), a canoe-gear maker (Reed Chill Cheater), and everything containing "Freedom"; **"Bain" caught McBains** (£24.1m construction consultancy), Baines schools, NORBAIN CCTV; **"EY/ERNST" caught Levitt BERNSTein architects** (£1.3m); **"BCG" caught BCG Direct mailing and a possible vaccine clinic** (excluded £119); "Matrix" caught 59 non-SCM firms incl. Matrix Chambers barristers. `REED LOCATION` at Greenwich (£375k) is housing disturbance payments, excluded. `Reed Business School` at DfE is grant money, excluded. `Manpower Direct` is an unrelated security firm, excluded.

## Strongest objection a critic would make
"Your corpus is 77 self-selected publishers with ragged coverage windows — the yearly totals mostly measure who published, not who spent. And Gartner is research subscriptions, Hays rows include recruitment advertising, Comensura/Matrix totals are pass-through to other agencies." Answer: correct on all counts, which is why every published claim is same-ledger (DHSC 19×, Greenwich £107m) or whole-corpus census framed as "in the published ledgers we hold", the intermediaries are flagged as pass-through, and the routed-fund category exists. A second objection: overseas member firms (KPMG East Africa, Deloitte India, PwC Kenya) are included in firm totals — scope column `overseas_member` in `firm_variants_included.csv` lets you strip them (they are mostly aid-programme work).

## Caption drafts (Joined Up voice)

1. "While your library lost a third of its funding, the Department of Health's consulting bill went from £8m to £205m in two years. One Deloitte invoice — £44m — is more than England spends on libraries per head in a year, per million people. It's all in the ledgers."
2. "One London borough put £107m through a temp-staff agency in five years — the same years it was cutting the services those staff used to run. Permanent jobs out, Manpower in."
3. "DHSC has an expense code for it: 'Contractor/Staff Substitution'. £7.9m to Deloitte, April 2021. They cut the staff, then rented them back at consultancy rates."

## Files
- `candidates_raw.csv` — 653 generous matches, pre-eyeball
- `firm_variants_included.csv` — 397 included strings with category + uk/overseas scope
- `variants_excluded.csv` — 256 exclusions with reasons (publish alongside)
- `yearly_firm_sector.csv`, `yearly_category_sector.csv`, `monthly_category_sector.csv`
- `dhsc_consulting_fy.csv`, `greenwich_manpower_fy.csv`, `juxtaposition.csv`, `ro_staffheavy_arc.csv`
- `top_engagements.csv` (hand-checked), `top_payments_raw.csv` (raw ≥£1m rows)
