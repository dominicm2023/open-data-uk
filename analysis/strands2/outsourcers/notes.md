# THE OUTSOURCED STATE — census of the big outsourcing firms in corpus.db

**Strand:** analysis\strands2\outsourcers\ · built 2026-08-18
**Corpus:** analysis\spending\corpus.db, clean set everywhere (`is_dup=0 AND supplier_raw<>''`).
**Method:** the censused name-variant method (broad regex net per firm over distinct
`supplier_raw` strings, then every matched string eyeballed; exact-string exclusion
lists with reasons). Eyeball record: `eyeball_dump.txt` (672 lines, all read).
Capita/Serco/G4S nets and exclusions inherited from analysis\supplier\ (already
eyeballed there); the £35.86bn CAPITA TP NATWEST/HSBC teachers'-pension pass-through
stays **out** of Capita, per the known trap.

**Files:**
- `01_census.py` → `variants.csv` (591 included strings), `variants_excluded.csv`
  (70 excluded strings, every one with a reason), `census_summary.json`
- `02_series.py` → `yearly_by_firm.csv`, `yearly_by_firm_payer.csv`,
  `collapse_arcs_monthly.csv`, `council_share.csv`, `council_share_by_firm.csv`,
  `waste_by_payer_year.csv`
- `03_headline.py` → `headline_firms.csv`

**Grouping rule (inherited):** a firm = the corporate group; subsidiaries in, JVs out.
Three JVs are censused as their own flagged lines instead of being dropped, because
they carry the story: **CarillionAmey (JV)** £1,212.7m, **CarillionEnterprise (JV)**
£498.9m, **SSCL (Sopra Steria JV)** £603.3m. Excluded-and-listed JVs: Keolis Amey
(Metrolink + DLR, £693.9m — Keolis-led), GEOAmey PECS (£93.2m), Kier Graham Defence
(£52.2m), CarillionAramark (£5.2m), Carillion Alawi / Al Futtaim Carillion (Gulf JVs).

## The census (headline_firms.csv)

| firm | £m | txns | payers | span | top payer |
|---|---:|---:|---:|---|---|
| Serco | 3,722.5 | 57,634 | 32 | 2010-04..2026-06 | DWP (£1,003m) |
| Capita | 3,408.4 | 48,062 | 49 | 2010-04..2026-06 | DWP (£1,437m) |
| G4S | 2,990.3 | 91,569 | 30 | 2010-04..2026-06 | DWP (£1,457m) |
| Mitie | 2,082.8 | 13,278 | 25 | 2010-04..2026-08 | DWP (£1,200m) |
| Interserve | 1,898.8 | 40,262 | 18 | 2010-04..2024-03 | MoD (£808m) |
| Sodexo | 1,529.3 | 8,891 | 18 | 2010-04..2026-06 | MoD (£479m) |
| CarillionAmey (JV) | 1,212.7 | 830 | 1 | 2014-06..2018-10 | MoD (all) |
| Sopra Steria | 1,051.9 | 4,589 | 18 | 2010-04..2026-02 | Home Office (£385m) |
| Kier | 883.3 | 2,373 | 24 | 2010-04..2026-06 | DfE (£384m) |
| Amey | 788.0 | 4,280 | 12 | 2010-05..2026-06 | MoD (£494m) |
| SSCL (Sopra Steria JV) | 603.3 | 1,389 | 6 | 2013-12..2026-06 | DWP (£531m) |
| CarillionEnterprise (JV) | 498.9 | 503 | 1 | 2010-04..2014-06 | MoD (all) |
| Carillion | 333.6 | 868 | 13 | 2008-12..2021-03 | MoD (£238m) |
| Veolia | 253.5 | 6,547 | 18 | 2010-04..2026-08 | MoD (£132m — water, not bins) |
| Liberata | 112.7 | 645 | 12 | 2010-04..2024-04 | MoJ (£105m) |
| Suez | 26.7 | 153 | 10 | 2010-07..2022-11 | South Glos (£25m, as SITA) |
| Biffa | 3.1 | 999 | 9 | 2010-04..2026-06 | HMRC (£2m) |

13 firms proper: **£19.08bn** across the published ledgers we hold; +£2.31bn through
the three censused JV lines. This is "in the ledgers we hold", never "the UK spends":
77 self-publishing bodies, 9 canonical councils, wildly different publication windows.

## (a) Yearly £ per firm — and the coverage trap that governs every trend claim

`yearly_by_firm.csv`, `yearly_by_firm_payer.csv`. Calendar years from `year_month`;
rows with no parseable month (74k rows, £3.1bn corpus-wide — MoJ alone £2.4bn) are
kept in a `year=''` bucket, never dropped.

**The trap:** publisher ledger windows differ. MoJ stops 2014-12. Home Office stops
2018-06. FCO stops 2018-07 (FCDO restarts 2020-09). MoD effectively stops 2020-Q1.
DfE stops 2022-03. DHSC stops 2022-11. Only DWP, HMRC, TfGM, Rushmoor, Uttlesford,
North Yorkshire and Bristol run to 2025/26. **Any cross-payer firm trend is
coverage-shaped, not fact-shaped.** Liberata's "collapse to zero after 2016" is
100% the MoJ ledger ending; Sopra Steria's fade is Home Office + MoJ + MoD windows
closing, not lost contracts (SSCL runs to 2026 in DWP's ledger).

**Verdicts:**
- PROVABLE NOW — *DWP is the single biggest published payer of Serco, Capita, G4S
  and Mitie alike* (£1.0bn, £1.44bn, £1.46bn, £1.20bn respectively). The
  jobcentre/assessment/FM state is the outsourcers' anchor client in our corpus.
- PROVABLE NOW — *the COVID surge*: in calendar 2020+2021 DHSC's ledger shows
  £705m to Serco, £545m to G4S, £315m to Sodexo (test-and-trace era). G4S's two
  best corpus years are 2021 and 2025; Mitie's are 2021-2025 (DWP estate + the
  Interserve FM book it bought in Dec 2020).
- PROVABLE NOW (within-payer) — *Capita's DWP line peaked at £205m in 2016 (PIP
  assessment era) and has not returned there since* (2024: £82m; 2025: £149m).
- MISLEADING AS FRAMED — "firm X's government revenue fell" from our cross-payer
  totals. Say "in the ledgers we hold, within payer Y". 
- NOT SUPPORTED — any national market-share or total-outsourcing figure.

## (b) The collapse arcs — Carillion and Interserve died differently

`collapse_arcs_monthly.csv` (Carillion, both Carillion JVs, Amey, Interserve, monthly).

**Carillion (liquidated 15 Jan 2018) is a relay, not a cliff.** The MoD money never
stopped — it changed nameplate three times:
- CarillionEnterprise (JV): £42m→£146m/yr 2010-2013, dies mid-2014 when the old
  Regional Prime contracts end.
- CarillionAmey (JV): starts 2014-06, runs £182m→£312m/yr, still drawing £23-54m a
  month through summer 2018 — *after* the parent's liquidation, because the JV was
  a separate legal entity propped by Amey. Last payment month: 2018-10 (£10.7m).
- Amey Defence Services: first appears 2018-10 — **the same month** — at £53.2m,
  then £30-60m/month until the MoD ledger itself ends (2020-Q1).
- Carillion proper: £2-9m/month through 2017 (the profit-warning year), £958k in
  the liquidation month, then only tail lines explicitly marked "IN LIQUIDATION"
  (£689k MoD 2018, £622k DfE 2019-01, last £-trace 2021-03).

**Interserve (pre-pack administration, March 2019) is a phoenix.** Payments did not
stop; some payers paid it *more* after the collapse: DWP £62m (2018) → £75m (2019)
→ £103m (2020); DfE and FCDO keep paying into 2022. The fade to zero over 2021-22
is Mitie's Dec-2020 purchase of Interserve's FM arm (the book moves into Mitie's
line) plus ledger windows closing — not the state walking away. Last corpus sighting:
FCDO card lines to 2024-03.

**Verdicts:**
- PROVABLE NOW — the relay (CarillionEnterprise → CarillionAmey → Amey Defence
  Services, with the Oct-2018 same-month handover) and the phoenix (Interserve paid
  through and beyond administration). Every number ships with its month.
- PROVABLE NOW — Carillion proper's payments in the ledgers we hold collapse at
  liquidation; the "in liquidation" strings are in variants.csv.
- MISLEADING AS FRAMED — "MoD spent £1.2bn on Carillion": CarillionAmey was a 50:50
  JV; we censused it separately for exactly this reason. Also any claim that curves
  ending 2020 mean contracts ending — that is the MoD ledger ending.

## (c) The 9 councils — is outsourcing share rising or falling?

`council_share.csv` (all 13 council-like publishers, canonical-9 flagged),
`council_share_by_firm.csv`. Denominator = ALL clean ledger spend per publisher-year
(includes housing benefit, intra-public transfers, capital); numerator = the 13
firms proper. So this is "share of the published ledger going to the 13 censused
giants", not "outsourcing share" writ large — councils can outsource plenty to
firms not on this list, and North Yorkshire visibly does its business elsewhere.

**There is no single direction. The honest answer is divergence:**
- **Rushmoor** (17 continuous years, the best series we hold): 18.6% (2010),
  ~26-36% every year 2011-2016, ~25-30% every year since. A quarter to a third of
  the ledger, every year, for 17 years — first via Veolia, then Serco. High and flat.
- **Eden**: 0.4% (2013) → 15-27% (2014-2018) — Amey plc arrives mid-2014 and instantly
  becomes a fifth of the ledger. Rising, sharply, until the ledger ends.
- **Greenwich**: 4.3% (2012) → 1.1% (2017). Falling.
- **Bristol**: 0.3% (2020) → 0.37% (2023) → ~0.0% (2025-26): Kier Transportation,
  Mitie Property and Liberata lines all end by early 2025. Low and falling (but see
  objection: Bristol's 2021 is entirely missing from the corpus).
- **North Yorkshire** (both eras): 0.00-0.01% of a £670m+ ledger. A publishable
  null: England's biggest new unitary pays effectively nothing to these 13 firms.
- Blaby ≤1.2%, Uttlesford ≤0.5%, Cheltenham 0.3% (single year), Plymouth 8.3%
  (single year, Amey), South Glos 12-17% (2010-11 only: SITA + Kier + Interserve).
- Richmond upon Thames: 18.8% — but its whole ledger is undated (year='' bucket),
  so it's a level, not a trend.

**Verdicts:**
- PROVABLE NOW — per-council shares and directions as above, each with its window.
- NOT SUPPORTED — "council outsourcing is rising" or "falling" as a general claim
  from these ledgers; the nine canonical councils split high-flat / rising / falling
  / near-zero. Also NOT SUPPORTED as "councils spend X% on outsourcing": the
  denominator is the whole published ledger and the numerator only these 13 firms.

## (d) The waste giants — bins are the story, and mostly a null

`waste_by_payer_year.csv`. Veolia £253.5m / Suez £26.7m / Biffa £3.1m.

- **The Rushmoor bin handover, clean in one ledger:** Veolia £2.9-4.8m/yr 2010→2016,
  £2.4m in 2017, then zero; Serco £1.3m in 2017 rising to £3.4-4.9m/yr ever since.
  The contract changed badge mid-2017; the money stream didn't blink.
- **Greenwich:** Veolia £4.7-6.7m/yr 2012-2017 (ledger ends).
- **South Glos:** SITA (now Suez) £25.3m in just 2010-11 — waste disposal was already
  the single biggest private line in its short ledger window.
- **Veolia's biggest government line is not bins:** MoD £132m 2010-2020 is Veolia
  Water Nevis/Outsourcing — Project Aquatrine water SPVs. East Sussex Healthcare's
  £30.7m (2021-2026, £16.3m spike in 2023) is hospital *energy*, not waste.
- **Biffa is a null:** £3.1m total across 9 payers in 16 years — mostly HMRC office
  waste. The most-outsourced council service barely touches our corpus because we
  hold so few council ledgers, and two of the big ones (North Yorkshire, Bristol)
  use other arrangements (Bristol Waste is council-owned).

**Verdicts:** PROVABLE NOW — the Rushmoor handover, the South Glos SITA
concentration, the Biffa null, the "Veolia's state money is water and energy, not
just bins" correction. MISLEADING AS FRAMED — "councils pay Veolia £X for bins"
from the MoD/NHS lines.

## Excluded ambiguities worth knowing (all in variants_excluded.csv)

- Keolis Amey Metrolink/Docklands £693.9m — Keolis-led JVs; TfGM's tram operator is
  not "Amey revenue".
- GEOAmey PECS £93.2m; Kier Graham Defence £52.2m; CarillionAramark £5.2m — JVs.
- SSCL accounts-receivable/on-behalf labels (£2.9m) — money owed to client
  departments, not SSCL; same logic as the Capita TP trap.
- GDF Suez strings £3.7m — the energy group (now Engie, £136m in the corpus under
  its own name, deliberately not censused) has been separate from Suez's waste
  business since 2008.
- eaga plc lines (£81k) — payments at/before Carillion's April-2011 acquisition.
- Academy trusts named for their sponsor (Interserve £5.6m, Carillion £125k) —
  beneficiaries are schools.
- HM Courts Service (Liberata) / MOJ LIBERATA £1.2m — payee presents as the courts.
- Not censused, noted: Mouchel £33.8m (mostly pre-dates Kier's 2015 acquisition),
  May Gurney £1.4m (pre-2013 Kier), Amazon-style predecessor brands otherwise absent
  (Onyx: zero strings — a checked null).

## The strongest objections a critic would make

1. **Coverage is the whole game.** 77 self-selecting publishers; windows from 8
   months (Cheltenham) to 17 years (Rushmoor); MoD — the biggest outsourcing payer —
   goes dark in early 2020; Bristol is missing calendar 2021 entirely; Richmond is
   entirely undated; South Glos has £190.6m (40% of its ledger) undated. Every curve
   end may be a ledger end. We flag this on every claim, but a hostile reader will
   still quote a curve as a contract.
2. **Cash ≠ revenue ≠ contract value.** These are payment lines above disclosure
   thresholds (£250/£500, varying by body and era), net of visible credits, not the
   firms' government revenue (ONS/NAO put UK public procurement at hundreds of £bn/yr;
   our £19bn over 16 years is a keyhole, not the market).
3. **The 13-firm list and JV judgments move numbers.** CarillionAmey inside Carillion
   would quadruple "Carillion"; Keolis Amey inside Amey would double Amey. We show
   both choices explicitly rather than making them silently.
4. **Calendar-year binning** disagrees with fiscal years; month-level data is in
   collapse_arcs_monthly.csv for the claims where it matters.
5. **Name-matching risk**: mitigated by eyeballing all 661 netted strings, but a
   subsidiary trading under an unrelated name (e.g. a rebranded acquisition) would
   be missed — undercounting, not overcounting.

## Caption drafts (Joined Up voice)

1. *The relay:* "Carillion collapsed in January 2018. The Ministry of Defence's
   housing money didn't even pause. Through 2018 it flowed to CarillionAmey — the
   joint venture — at £20-50m a month. Its last payment lands in October 2018, and
   in the very same month 'Amey Defence Services' appears: £53m. The firm died. The
   contract just changed its name badge."
2. *The phoenix:* "Interserve went into administration in March 2019. In the ledgers
   we hold, the DWP paid it more after the collapse than before — £62m in 2018, £75m
   in 2019, £103m in 2020. When an outsourcer holds your jobcentres, it is too
   embedded to fail."
3. *The anchor client:* "One department is the biggest published payer of Serco,
   Capita, G4S and Mitie alike: the DWP — £5.1bn across the four in the ledgers we
   hold. The benefits system doesn't just assess claimants. It underwrites an
   industry."
4. *The bins:* "In Rushmoor's ledger, a quarter to a third of every published pound
   has gone to a giant outsourcer every year since 2010. Veolia collected the bins
   until 2017; Serco has collected them since. The badge on the truck changed. The
   share of the budget didn't."

## Reproduce

```
python 01_census.py    # variants.csv, variants_excluded.csv, census_summary.json
python 02_series.py    # all time series + council shares (13s)
python 03_headline.py  # headline_firms.csv
```
Every CSV row traces to `SELECT ... FROM transactions WHERE is_dup=0 AND supplier_raw IN (variants of firm) GROUP BY ...` with the variant lists in variants.csv.
