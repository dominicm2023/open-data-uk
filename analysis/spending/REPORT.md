# The spending corpus — build note

**Status: corpus build note. This is the fetched-data foundation for "The spending map of Britain" and the later supplier-price analysis. The headline total is dominated by central-government transfer payments — read the coverage section before quoting any number as "council spending", because this corpus is not that.**

Every number below traces to a script in this directory: selection to `select_datasets.py`, fetching to `fetch_corpus.py` + `manifest.json`, parsing to `parse_corpus.py`, duplicate flagging to `dedupe_flag.py`, aggregates to `compute_findings.py` -> `findings.json`. The corpus itself is `corpus.db` (SQLite): `transactions` (supplier_raw held VERBATIM — normalisation is deliberately the next analysis's job) and `files` (one row per fetched URL with parse status).

## What was selected

From `index.db`: findable datasets (not duplicate, not retired) with `availability='data'`, `formats_norm LIKE '%CSV%'`, a non-null normalised licence, and a title matching the spending terms (spend, expenditure, payments to supplier, supplier payment, purchase card, invoice). That query (`select_datasets.py`) returned **193 datasets across 85 publishers -> 7,863 unique resource URLs**, of which **7,180** were CSV-shaped (declared CSV, undeclared, or `.csv` in the URL) and fetched. The 683 declared-PDF/XLS/XLSX/ODS/etc resources were recorded and skipped, not silently dropped (`selection.json`, `fetch=false`).

Fetching (2 req/s per host, 60s timeout, one retry max on 403/429, 150 MB per-file cap, 4 GB total cap): **6,965 of 7,180 URLs saved, 2.16 GB**. No file hit the size cap.

## Reconciliation — how the headline number was earned

| step | rows | GBP |
|---|---:|---:|
| raw parsed rows | 11,859,379 | 3,416,191,526,209.61 |
| minus cross-file duplicates (same publisher+date+supplier+amount+txn seen in more than one file: monthly + roll-up publications) | 42,861 | 16,615,696,025.86 |
| minus blank-supplier rows (subtotal/unattributable lines; includes two £10bn+ DHSC total-rows) | 10,141 | 130,410,854,615.83 |
| **= clean corpus** | **11,806,377** | **3,269,164,975,567.92** |
| dates outside [2008-01-01, 2026-08-17] dropped at parse | 1 | 87,940.56 |

**11,806,377 transactions, £3.269 trillion, 2008-04-01 to 2026-08-10, 77 publishers with rows** (queries in `compute_findings.py`; the clean set is `WHERE is_dup=0 AND supplier_raw<>''`).

The £3.27tn passes the sniff test only once you see what it is: the ten largest transactions are all Department of Health and Social Care rows — a £34bn payment to HM Treasury (2021-03-24), a £25bn one (2020-11-05), and monthly £8.8–12bn grant-in-aid block payments to NHS England. DHSC alone is £1.43tn of the total and DfE £1.01tn (academies funding: 2.19M transactions); MHCLG £0.36tn (local-government grants). These are real rows in real published files, but they are **transfers between arms of government**, and the same pound can appear again downstream (DHSC -> NHS England -> a trust's own spend file). Do not sum this corpus and call it "public spending"; per-publisher and per-supplier views are the honest units. Peak month: 2021-03, £58.0bn across 53,734 transactions.

67 files whose median transaction is >=100x their own dataset-series median are flagged in `findings.json` -> `reconciliation.scale_outlier_files_for_hand_checking` (£19.4bn). Hand-checks during the build found **no confirmed pence-for-pounds unit error** — every one inspected was genre mixture (an over-£25k-shaped file inside a series that publishes every transaction down to pennies), so no unit adjustment was applied. They remain a hand-check queue, not a correction.

Other row-level facts: 73,199 rows (0.62%) have no parseable date; 436,532 rows (3.7%) are negative (credit notes/reversals) summing to -£131.7bn — kept, because dropping them would double-count the corrected payments.

## Coverage — who is in, and who is not

**This cannot be published as "council spending in Britain."** Of the 361 councils on the ONS register, exactly **9** have transaction rows here: Blaby, Cheltenham, Greenwich, North Yorkshire, Plymouth, Richmond upon Thames, Rushmoor, South Gloucestershire, Uttlesford. The other 352 are absent — most publish their over-£500 files on their own websites or data.gov.uk under titles/formats the index's verified-spending filter doesn't catch, and six more (Bristol, City of London, Sandwell, Trafford, Wigan, Rochdale) were selected but every file failed (see census). The remaining 68 publishers with rows are central departments, NHS bodies, and arm's-length bodies. It is "the publishers that publish, parsed" — the map must say so.

Publishers whose every file failed (8): Wigan (all XLS-in-.csv), Weston Area Health NHS Trust (all HTML), Trafford + Sandwell (XLSX-in-.csv), Rochdale (per-school aggregates, no supplier), City of London (a dead tracker URL serving "Hi This page is no more valid" with HTTP 200), Food Standards Agency (approvals data, not payments), MOD Head Office & Corporate Services (ditto).

## The parse-failure census — how 7,180 files break

| status | files | meaning |
|---|---:|---|
| parsed | 5,593 | rows extracted (77.9% of fetched URLs) |
| excluded-approvals-dataset | 570 | title says exceptions-to-moratoria / spend-control / approvals: permission-to-spend records (often in £M), not payments — wrong genre, excluded wholesale |
| not-csv-html-or-xml | 354 | "CSV" URL served an HTML page (gov.uk landing pages, error pages, dead redirects) |
| fetch-failed | 215 | 94 x HTTP 403, 88 x 404, 19 x 202 (WAF challenge), 13 connection errors, 1 x 400 |
| no-amount-column | 148 | header found, no usable amount (incl. NHSBSA files whose data rows carry one more column than the header names, shifting zero-padded transaction numbers under "Amount" — caught by an id-column guard) |
| no-header | 147 | no plausible header in the first 30 lines |
| not-csv-xlsx-zip | 52 | PK magic bytes: XLSX with a .csv name |
| no-supplier-column | 50 | header found, no supplier column (mostly residual approvals-shaped files) |
| not-csv-xls-ole | 49 | OLE magic bytes: legacy XLS with a .csv name |
| not-csv-pdf | 2 | %PDF |

So **22.1% of fetched "CSV" resources yielded no rows**, and 457 of them (6.4%) were not CSV files at all. Encoding: 2,546 parsed files needed the cp1252 fallback, 190 were UTF-16 (Milton Keynes's entire archive), 2 carried replacement characters. Dates: 38 files were m/d/Y against the UK's d/m/Y (per-file detection, never per-row); Coventry & Warwickshire publishes compact `yyyymmdd`.

## The three most surprising things

1. **Datasets titled "Spend over £25,000" that contain everything.** Salisbury NHS FT's over-£25k series actually publishes every invoice line down to £0.03 (median transaction: £5.42). The threshold in the title is a fiction; the median-per-file distribution inside one series spans four orders of magnitude.
2. **The Cabinet Office template breaks in ways that carry money.** NHSBSA published months of files whose header names nine columns while the data rows have ten — every parser that trusts the header reads zero-padded transaction IDs (~£50-80M each) as amounts. Uncaught, that single misalignment injected £5.2bn of phantom spend.
3. **The corpus's £ total is a hall of mirrors of intra-government transfers.** Two DHSC rows — £34bn and £25bn to HM Treasury in the COVID years — are each larger than the combined 18-year total of all nine councils in the corpus. Anything published from this must aggregate per publisher, never across them.

## Rebuild

```
python select_datasets.py   # selection.json from ../../index.db
python fetch_corpus.py      # raw/ + manifest.json (resumable, polite)
python parse_corpus.py      # corpus.db
python dedupe_flag.py       # sets transactions.is_dup
python compute_findings.py  # findings.json
```
