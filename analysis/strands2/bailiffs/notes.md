# The debt collection economy — bailiffs strand

**Status: censused and eyeballed. Every number reproducible from `census_step1.py`,
`census_step2.py`, `build_final.py`, `meta2.py`, `meta3.py` (this folder) against
`../../spending/corpus.db`. No network. Nulls are results.**

Scope reminder: 77 publishers, of which 12 are councils or council-ish
(incl. two North Yorkshire eras and former Harrogate). Nothing here is a
national total; everything is "in the published ledgers we hold".

## Method

Generous LIKE patterns on `supplier_raw` for the ten named firms plus
Whyte & Co, Rundles, JBW, Ross & Roberts, Phoenix, Swift, Collectica,
Confero, STA International; then `%ENFORC%`, `%BAILIFF%`, `%SUTOR%`,
`%DEBT%`, `%COLLECTIONS%` in supplier names; then expense_type generics
(`%ENFORC%`, `%BAILIFF%`, `%DEBT%`, `%SUMMON%`, `%COLLECTION%`). Every
matched string eyeballed before counting — see
`eyeball_supplier_matches.csv`, `eyeball_supplier_catchall.csv`,
`eyeball_expense_types.csv` (kept as evidence). Included rows are the
exact (supplier_raw, publisher) pairs in `build_final.py`.

### Eyeball exclusions (the traps, so nobody re-falls in)

- **Jacobs**: JACOBS U.K. LIMITED / Jacobs Engineering / JACOBS UK LTD =
  the engineering consultancy (MoD £76.5m, DfE £24m, TfGM £8.7m…);
  BROWNE JACOBSON = law firm; Alderman Jacobs School = school. The
  enforcement Jacobs appears **only** as `JACOBS DEBT RECOVERY` at North
  Yorkshire, 10 rows, **netting £0.00** (see honesty check).
- **Marston**: Marston Vale/Green/South Marston schools (DfE grants),
  J Marston Engineers t/a Mortuary Solutions, Marston & Grundy, HS Marston
  Aerospace, Marston Book Services, Marston's hotels/properties/robing,
  Long Marston Parish Council. Only `MARSTON GROUP*` / `Marston (Holdings)`
  variants counted.
- **Rossendale(s)**: ROSSENDALE TRANSPORT (£55.1m of TfGM bus money),
  ROSSENDALE BC (the council, £29m of MHCLG grants), Accrington &
  Rossendale College, Rossendale Leisure Trust, Rossendale School Priory,
  ROSSENDALE GROUP (retail). `Rossendales Training Ltd` (South Glos £2,102,
  "Training Expenses") excluded as ambiguous.
- **Equita**: Equitas Academy Trust, Equitable Life, Aequitas (law/lettings).
- **Bristow**: BRISTOWS LLP and Collyer Bristow (law), J.E. Bristow
  (Electrical), Paul Bristow Associates.
- **Newlyn / Dukes / Excel / Andrew James / CDER-as-McDermott**: every match
  was a school, hotel, gallery, academy, taxi firm, aerospace supplier, HRH
  the Duke of York, or a private person (Greenwich's ANDREW JAMES rows are
  care direct payments, −£2,171). See null results below.
- **K BAILIFF & SON LTD** (Eden £22,984): surname, building contractor by
  context. Excluded.
- **Imperial Civil Enforcement Solutions / Conduent Parking Enforcement**
  (Greenwich £345k, Plymouth £178k, Rushmoor £141k, NYC £25k, Cheltenham
  £13k): parking-ticket processing/software, i.e. civil *parking*
  enforcement back office, not debt collection agents. Excluded from the
  firm census; noted as the adjacent industry.
- **"High Court Enforcement"** (Bristol £20,513, expense "Ex Gratia
  Payments"): not a firm name; a compensation payment. Excluded, flagged.
- **ENFORCEMENT SERVICES LTD** (NYC £9,220 under Roads > Surveys) excluded;
  **ENFORCEMENT SERVICES** (Blaby £189,200, 3 lump sums in 2014, expense_area
  "Finance, Efficiency & Assets") INCLUDED but flagged `generic_name_finance_area`
  — the Finance area says revenues work, the name says nothing more. Do not
  headline Blaby without this flag.

## (a) £ per firm per year, with payer — `firm_year_payer.csv`, `firm_totals.csv`

Gross outflow (sum of positive lines), gross inflow (negative lines) and
net, per firm × payer × year. Headlines (gross outflow / net, full windows):

| firm | payers | gross out | net |
|---|---|---:|---:|
| Marston | MoJ, DWP, Defra, Greenwich, Bristol, Rushmoor, N Yorks | £11.99m | £3.67m* |
| Rossendales | HMRC, MoJ, Greenwich, Blaby, Bristol | £5.45m | £5.35m |
| Equita | HMRC, Greenwich, N Yorks | £1.50m | £1.35m |
| Bristow & Sutor | Bristol, S Glos, Cheltenham, N Yorks, Blaby | £1.47m | £26k |
| Whyte & Co | Greenwich | £629k | £295k |
| Rundles | Greenwich, S Glos, Uttlesford, TfGM | £514k | £109k |
| Ross & Roberts | Greenwich, Bristol, Rushmoor | £430k | £116k |
| JBW Group | Greenwich, Plymouth | £107k | £16k |
| Jacobs (enforcement) | N Yorks | £19k | **£0.00** |

*Marston's MoJ "net" is polluted by income-coded lines — see honesty check.
The only clean MoJ expenditure line is `111620-Bailiff Fees (NOS)` =
**£328,684.61** (2011). MoJ also has £1.69m of Marston under
`130001-Other Income` and £1.36m under Debtors/VAT balance-sheet codes:
"MoJ paid Marston £3.4m" is **MISLEADING AS FRAMED**.

**Null results (publishable):** Newlyn Plc, Dukes Bailiffs, Andrew James
Enforcement, Excel Enforcement, Phoenix Commercial Collections, Swift
Credit Services, Collectica, Confero — no payments to any of them anywhere
in 11.8m rows. The enforcement census here is what these 77 publishers
published, not the industry.

## (b) Which councils pay, per resident — `council_enforcement_vs_ct_dependence.csv`

**9 of the 12 council-ish publishers** show payments to debt-enforcement
firms (all but Eden, former Harrogate, and Richmond's undated 2k-row
fragment). Windows differ — never compare councils against each other
without stating the window:

| council | firms | window | gross → firms | net cost | net/1000 residents |
|---|---|---|---:|---:|---:|
| Bristol | 5 | 2020–2026 | £9.22m | £86,958 | £176 |
| Greenwich | 8 | 2012–2017 | £2.19m | £624,996 | £2,367 |
| North Yorkshire | 8 | 2022–2026 | £256k | £28,821 | £45 |
| Blaby | 3 | 2013–2018 | £194k† | £194k† | £1,932† |
| S Gloucestershire | 2 | 2010–2011 | £12.8k | £12.8k | £48 |
| Uttlesford | 1 | 2019–2025 | £8.3k | £8.3k | £87 |
| Cheltenham | 2 | 2020 | £5.9k | £5.9k | £51 |
| Rushmoor | 3 | 2016–2023 | £5.0k | £3.9k | £41 |
| Plymouth | 1 | 2015 | £425 | £425 | £2 |

† £189,200 of Blaby's £194k is the flagged generic-name supplier.

Court-side costs sit alongside (`court_collection_costs.csv`): Greenwich
paid HMCTS **£164,754 in "Court Costs Summons Fees"** 2014–2017 — the fee
the council pays to issue council-tax summonses, recharged to debtors.
Rushmoor's ledger has "Council Tax Collection" £2,370 and "Cost of NNDR
Collection" £738 paid to HM Magistrates Court; North Yorkshire paid the
Traffic Enforcement Centre £30,000 to register parking debts.

## (c) The juxtaposition — same file, `ct_share_*` columns

Council-tax dependence (2024-25 financing share, from the counciltax
strand): North Yorkshire **76.0%**, South Glos 74.3%, Cheltenham 64.3%,
Rushmoor 64.2%, Bristol 60.5%, Uttlesford 59.2%, Plymouth 58.4%, Blaby
58.0%, Greenwich 45.6%. Every one of them pays private enforcement firms;
the most bill-dependent council in our corpus (North Yorkshire) routes
sundry debt, parking fines and council-tax recovery through at least six
collection suppliers plus the TEC. **With nine councils this is an
illustration, not a correlation** — do not fit a line through it. The safe
sentence: "the councils that now run mostly on residents' bills are the
same councils hiring private agents to enforce those bills" — true of
every billing authority in the ledgers we hold.

## (d) HONESTY CHECK — who actually pays the bailiff?

The statutory backdrop: since April 2014 (Taking Control of Goods (Fees)
Regs), enforcement-agent fees are charged **to the debtor** — £75
compliance stage, £235 enforcement stage, +7.5% of debt above £1,500. The
ledgers confirm the consequence three ways:

1. **North Yorkshire publishes the pass-through explicitly.** Every bailiff
   line appears twice, same day, same amount, + and − (`nyc_zero_rows.csv`):
   Marston +£27,991.75/−£27,991.75; Equita (parking "Fines Collection")
   +£9,350.75/−£9,350.75; Jacobs Debt Recovery, Bristow & Sutor the same.
   Across 2024–2026 those four firms show **£228,061 of gross legs, net
   £403.84**. The council's own
   accounts say its bailiffs cost it (almost) nothing.
2. **Bristol books same-day contra reversals** with small residuals
   (`amount_fingerprint.csv`, `firm_payer_expense_detail.csv`): B&S
   +£23,076.74/−£23,076.74 on 2026-02-03; residuals like +£144.31,
   +£176.70, +£235.81 — the last is the statutory enforcement-stage fee to
   the pound. Six years of Bristol↔5 firms: **£9.22m of ledger churn, £87k
   net**. Also seven bare £75.00 lines (the compliance fee) at B&S.
3. **Greenwich (2012–2017, straddling the 2014 regs) shows real net cost**:
   "Debt Collection Agency Charges" £98,667 + £96,355 unlabelled +
   £16,250 professional fees to Whyte & Co alone, net £295k across the
   firm; £625k net across 8 firms — ~44p/resident/year — plus the £165k of
   summons fees. Older regimes and non-collectable cases do land on the
   council.

**What can be claimed:** "Council ledgers show millions moving between
councils and enforcement firms, and pennies of net cost — because the law
makes people in arrears fund their own enforcement (£75 + £235 a time)."
PROVABLE NOW from rows 1–2 above plus the fee regs.

**What cannot:** "Councils spend £Xm on bailiffs" (gross legs are
remittance/reversal churn — NOT SUPPORTED); "residents paid £Xm in bailiff
fees" (debtor-side fees never enter the council ledger; the gross legs are
not fee income — NOT SUPPORTED); any read of Marston's MoJ £3.4m as
spending (income/balance-sheet codes — MISLEADING AS FRAMED); any national
total.

**Where the state genuinely pays collectors** (`central_debt_context.csv`,
`meta3.py`): HMRC paid debt-collection contractors at least **£381m**
(2010–2026: Indesser £199.4m, TDX Group £145.6m, iQor £8.4m, Commercial
Collection Services £8.1m, drydensfairfax £5.8m, Advantis £3.8m,
Rossendales £3.4m, Akinika £2.7m, Bluestone £1.6m, Equita £1.3m, Credit
Solutions £1.2m); DWP ~£19.9m more, including **"BAILIFF TRACE": £1.55m
paid by DWP to HMRC** for debtor-tracing data, and £448k of "BAILIFF
COMMISSION". Central government cannot pass its collection costs to
debtors the way the 2014 fee regs let councils' agents do — so there the
taxpayer visibly pays.

Curio for a footnote: Shropshire Community Health NHS Trust pays "WEST
MERCIA ENFORCEMENT CENTRE — Court Order Payment" (£1,277) — an NHS employer
remitting attachment-of-earnings deductions from staff wages to a court.
The debt economy reaches payroll.

## Strongest objection a critic would make

"Your net-zero contra pairs might be accrual reversals or redaction
artefacts, not proof the debtor pays — and your gross figures double-count
the same invoice." Fair on the first half: we cannot see the cash leg, only
that the council's published position nets to nil, which is exactly what
fee-shifted enforcement should look like and exactly what Greenwich's
pre-2014 ledger does NOT look like. We answer the second half by never
summing gross and net in one figure and shipping both columns. A second
objection: "nine councils, cherry-picked by who happens to publish" — yes;
every table says which nine and which years, and we make no industry-size
claim. Third: Blaby's biggest line is a supplier literally named
"ENFORCEMENT SERVICES" — we flag it in every output rather than resolve it
by wishful thinking.

## Caption drafts (Joined Up voice)

1. "North Yorkshire's ledger pays Marston's bailiffs £27,991.75 — then
   takes every penny back on the same line, the same day. Net cost to the
   council: nil. The law sends the bill to the people in arrears instead:
   £75 for the letter, £235 for the knock on the door."
2. "Bristol's accounts show £9.2m churning between the council and five
   bailiff firms since 2020 — and a net cost of £87,000. That gap is the
   design: enforcement is built to be free for the council and expensive
   for whoever couldn't pay the first bill."
3. "The bailiffs aren't just at the door for council tax. HMRC has paid
   debt-collection contractors at least £381m; the DWP even pays HMRC for
   'bailiff trace' data on people who owe it money. Private debt
   enforcement isn't a council quirk — it's national infrastructure."

## Files

| file | for |
|---|---|
| `firm_year_payer.csv` | (a) firm × payer × year, gross out/in + net |
| `firm_totals.csv` | (a) firm rollup across payers |
| `council_enforcement_vs_ct_dependence.csv` | (b)+(c) council table with per-1000-resident and CT-dependence columns |
| `court_collection_costs.csv` | court-side collection fees (HMCTS, magistrates, TEC) |
| `central_debt_context.csv` | HMRC/DWP/MoJ debt-collection contractor lines |
| `nyc_zero_rows.csv` | (d) the contra-pair evidence, row level |
| `amount_fingerprint.csv` | (d) modal amounts incl. £75/£235 statutory fees |
| `firm_payer_expense_detail.csv` | (d) expense-code split incl. MoJ income-coded Marston |
| `eyeball_*.csv` | the full match census with everything excluded still visible |
