# What the state pays for the same thing — supplier identity across public bodies

**Status: analysis #9, on the spending corpus. The finding it extends: in UK spending data the supplier is a name, not a number. This measures what that costs. Blindness first: the corpus is 9 councils and 68 central departments/NHS bodies/ALBs — "the bodies that publish, parsed", never "the UK". Nothing here may be summed across publishers and called spending.**

Every number traces to a script here: the rollup to `00_build_agg.py` (verified against the corpus build: 11,806,377 clean transactions, GBP 3,269,164,975,567.92, 77 publishers, **241,495 distinct supplier_raw strings**; clean set `is_dup=0 AND supplier_raw<>''`), the variant census to `01_variant_census.py`, cross-body presence to `02_cross_body.py`, flows to `03_flows.py`, the price test to `04_prices.py`, assembly to `05_findings.py` -> `findings.json`. The eyeballing tools (`explore_variants.py`, `explore_pubbody.py`) are kept because the eyeballing is the method.

## Q1 — The name-variant census

Method: per company, a deliberately broad regex net over all 241,495 distinct strings, then **every matched string eyeballed**. Exclusions are exact strings with a written reason (`variants_excluded.csv`, 65 strings; also embedded in `census_summary.json`). A company is the corporate group (BT Global Services counts as BT; G4S Kenya counts as G4S). Joint ventures (BT Al-Saudia, Severn Trent Costain, Wave), unverifiable lookalikes (Royal Mail Courier Services Ltd, Serco Projects LLC) and pass-through accounts are excluded and listed. Virgin is split by construction: only Virgin Media is censused; Virgin Atlantic/Care/Trains/Money/Holidays/Active are separate companies and stayed out.

| company | distinct spellings | publishers | txns | GBP |
|---|---:|---:|---:|---:|
| Amazon (incl. AWS) | 566 | 25 | 8,086 | 780,940,308 |
| Capita | 141 | 49 | 48,062 | 3,408,356,855 |
| BT Group | 116 | 57 | 16,808 | 3,743,940,572 |
| Microsoft | 94 | 24 | 945 | 175,965,385 |
| G4S | 91 | 30 | 91,569 | 2,990,252,899 |
| HMRC (as payee) | 76 | 48 | 7,039 | 6,934,563,641 |
| EDF Energy | 52 | 42 | 11,766 | 1,471,815,412 |
| NHS Supply Chain (SCCL) | 48 | 23 | 1,263,219 | 8,656,309,778 |
| British Gas / Centrica | 32 | 32 | 6,671 | 69,931,922 |
| Royal Mail | 31 | 38 | 224,466 | 1,412,812,855 |
| Serco | 31 | 32 | 57,634 | 3,722,514,231 |
| Virgin Media | 21 | 31 | 2,855 | 48,739,216 |
| Thames Water | 12 | 15 | 1,062 | 19,475,912 |
| Anglian Water | 11 | 11 | 1,194 | 24,727,991 |
| Severn Trent | 10 | 10 | 553 | 223,532,757 |
| South West Water (Pennon) | 7 | 9 | 80 | 1,115,146 |
| Yorkshire Water | 6 | 7 | 84 | 2,936,643 |
| NHS Professionals | 5 | 6 | 3,629 | 631,778,541 |

**The deliverable sentence: BT Group appears under 116 different spellings across 57 of the 77 publishers; the tax office itself is paid under 76 names (including `HMRC ACCOUNTS RECIEVABLE`); NHS Supply Chain's 1.26M transactions arrive under 48 labels.** Full lists in `variants.csv` (1,350 rows).

Two variant counts need their own honesty: Amazon's 566 and Microsoft's 94 are inflated by purchase-card exports, where every order can mint a new string (`AMAZON.CO.UK MU5VK08U4`, `Microsoft-G055446887`). That is itself a finding — card statements multiply variants without limit — but it is not the same failure as `BRITISH TELECOMMUNIC` vs `BRITISH TELECOMMUICATIONS PLC` vs `BRITISH TELECOMMUNCATIONS` (all real, all hand-keyed).

Ambiguities excluded after eyeballing (the full 65 are in `variants_excluded.csv`), the four that matter:

1. **`CAPITA TP NATWEST` — GBP 35.61bn — is not payments to Capita.** It is DfE's "Funding to pay Teachers' Pensions" routed through Capita's third-party bank account (1,042 rows, 2010-04 to 2014-07; sibling `CAPITA TP HSBC`, GBP 246.5m; verified against expense_type in the corpus). Teachers' pension money sits in the published data under a contractor's bank-account label. Any naive supplier league table makes Capita ten times its real size.
2. **`EUROPEAN COMMISSION (EDF)` — GBP 3.17bn — is the European Development Fund**, not EDF Energy. The acronym match every quick analysis would do hands the electricity company three billion pounds of aid money.
3. **Corona Energy is not British Gas.** An early draft of this census netted it under Centrica; it is Macquarie-owned. Kept in the script as a documented near-miss because the eyeball was the control that caught it.
4. **`BT Al Saudia`, `SEVERN TRENT COSTAIN WATER`, `WAVE ANGLIAN WATER BUSINESS`** — joint ventures, excluded from group totals.

## Q2 — Cross-body presence, and the gap that is the finding

Exact match (`02_cross_body.py`, from the per-publisher rollup): of 241,495 distinct strings, **15,989 appear in 2+ publishers, 1,324 in 5+, 181 in 10+, 12 in 20+**.

After a deliberately conservative normalisation (upper-case; punctuation to space; drop LTD/LIMITED/PLC/AND tokens; drop leading THE — no fuzzy matching at all): 218,542 distinct names, of which **18,758 in 2+, 2,108 in 5+, 482 in 10+, 66 in 20+**.

The gap is the measurable cost of name-only publication: **the trivial normalisation grows the 10+-publisher set 2.7x and the 20+-publisher set 5.5x.** Softcat is one supplier by any human reading; its best single spelling reaches 18 publishers, its normalised name 41 (`cross_body_gainers.csv`, top 200). And this is the floor — hand-keyed typos (`DUDELEY MBC`, `AMAZONS SVCS`) survive even this normalisation, so the true overlap is larger still.

## Q3 — Public-body-to-public-body flows: SUPPORTED — `flows.csv`

Scope (stated because it decides the numbers): UK **core** public bodies as payees — central departments, local government (including `X MBC`/`LBC` abbreviations, which alone hid GBP 31.8bn from the first token pass), NHS bodies incl. state-owned companies, police/fire, national agencies, LGPS funds, NDPBs. Excluded and quantified in `flows_summary.json`: education institutions GBP 6.37bn (academies are state schools, but token-matching catches them too patchily to be honest), foreign governments GBP 3.21bn (DFID/FCDO grants to overseas ministries), charities-with-council-names GBP 0.79bn, fee-funded regulators GBP 55m, private ambulance firms GBP 20m, payee-unclear labels GBP 80m. Every included name >= GBP 1M was eyeballed; the unreviewed rule-matched tail is GBP 428m across 2,626 small names — the bounded residual risk.

Result: **9,523 publisher-to-body flows, 4,919 bodies, GBP 1,724bn — 53.7% of the corpus's clean total (after setting aside the two DHSC mega-transfers) is one arm of the state paying another.** The two mega-transfers are reported separately, never averaged: DHSC -> `HM TREASURY (HMT)`, GBP 34bn on 2021-03-24 and GBP 25bn on 2020-11-05, each a single row.

Shares of each publisher's GBP going to public bodies (full table in `flows_summary.json`): DHSC **91.0%** (the NHS England block grants: the corpus's largest "supplier" is the ledger code `NHS ENGLAND CBA033`, GBP 951.6bn in 307 rows), Home Office **70.1%** (police: GBP 12.4bn to the Greater London Authority alone), DfE **26.9%** (councils' schools funding — would be far higher if academies were counted), MHCLG **24.4%**, MoJ 26.2%, DWP 13.7%, MoD 4.8%, DFID 1.9%. `flows.csv` carries a `self_flag` column (crude substring match) for internal-recharge rows.

## Q4 — Same thing, different prices: NOT SUPPORTED

Payment lines are invoice totals, not unit prices, and the one honest candidate fails on inspection. `04_prices.py` found 334,200 (supplier, publisher, amount) triples recurring in 3+ months, and 1,034 (normalised supplier, exact amount) pairs recurring in 2+ publishers — the exact shape a licence-fee comparison would need. Eyeballed (`recurring_candidates.csv`), they are: round-number grants (WFP/ICRC/UNDP contributions from DFID and FCO), statutory fixed fees (the ICO's GBP 500 registration, identical everywhere *because it is set by law*), franking-machine top-ups (Neopost GBP 2,000/4,000 — round because they are top-ups, not prices), redaction labels (`REDACTED`, `SUPPLIER NAME WITHHELD` — which recur like suppliers), and NHS pharmacy stock (identical Janssen lines of GBP 32,450.52 across four trusts — same pack at the same national list price, so where units ARE comparable the price is nationally uniform and there is no story; where amounts differ, the quantity is unknowable). Without a unit — seats, litres, licences — a difference in amounts cannot be told apart from a difference in scope, and this corpus never publishes a unit. That conclusion is the protection: the "council A pays twice what council B pays" story cannot be done honestly from spending CSVs, by us or by anyone.

## The three most striking verified things

1. **GBP 35.6bn of teachers' pension money is filed under `CAPITA TP NATWEST`.** The supplier column records the bank account of the administrator, not the destination of the money — the strongest single exhibit that names-as-published cannot be read as recipients.
2. **The state cannot spell itself.** HMRC is paid by 48 of the 77 publishers under 76 different names; councils appear as `SANDWELL MBC`, `SANWELL MBC`, `SANDWELL METRO BOROUGH COUNCIL` — and 53.7% of the corpus's money is these bodies paying each other under free-text names.
3. **One trivial normalisation quintuples the most-shared suppliers.** 12 exact strings reach 20+ publishers; 66 normalised names do. Every analysis that joins on the raw string — including any naive "biggest suppliers to government" table — is wrong by at least that factor, before typos.

## Rebuild

```
python 00_build_agg.py      # agg.db from ../spending/corpus.db (one scan)
python 01_variant_census.py # variants.csv, variants_excluded.csv, census_summary.json
python 02_cross_body.py     # cross_body.json, cross_body_gainers.csv
python 03_flows.py          # flows.csv, flows_summary.json
python 04_prices.py         # recurring_candidates.csv
python 05_findings.py       # findings.json
```

If the corpus is rebuilt, the census nets re-run open-eyed: any new string a net catches lands in `variants.csv` for re-eyeballing rather than being silently excluded.
