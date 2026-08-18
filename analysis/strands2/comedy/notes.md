# THE RECEIPTS, FOR FUN — verified comedy from the published ledgers

**Method.** Keyword sweep over 267,995 distinct (supplier_raw, publisher) pairs plus full scans
of 40,891 distinct expense_type strings and 18,084 expense_area strings in corpus.db (11.86M rows,
77 publishers). Every candidate row was pulled back with publisher, date, expense_type and
source_file, and re-summed with `is_dup=0`. Every row quoted below exists verbatim in a published
transparency file; `receipts.csv` carries the source_file hash (and, where the manifest has it,
the original dataset title and URL) for every single row. RO finding computed from
`analysis/ro/ro_per_head.csv` (2024-25, gross, per head, class = London boroughs).

**The bar applied:** would it survive a community note? Nothing below claims more than the ledger
says. Where the explanation is boring, the caption says so — the joke is that the row exists.

**Queries:** `scan_suppliers.py` / `match.py` (supplier sweep), `scan_expense.py` (expense vocab),
`scan_amounts.py` (pennies + round millions), `details1-3.py` (row-level eyeballing),
`build_receipts.py` (final CSV, dedupe-safe).

---

## THE TOP 15

### 1. "Panto Expenditure" — £948,252.50 and rising — PROVABLE NOW
Rushmoor Borough Council has a ledger category literally called **Panto Expenditure**: 508
payments, £948,252.50, 2018-03-22 to 2026-05-21 (dedupe-checked). They also have "Civic Regalia",
"Mayor-making" and "Mayoral Charity Dinner Dance" (£68,911.44), all real category names.
*Objection a critic would make:* Rushmoor runs the Princes Hall theatre; the panto sells tickets,
so this is gross cost of a trading show, not money down a well. Correct — and irrelevant to the
joke, which is that a council finance system contains a near-million-pound line called Panto.
**Caption:** "Rushmoor Borough Council's ledgers contain a budget line called 'Panto Expenditure'.
It stands at £948,252. Is that a lot? Oh yes it is."

### 2. Flag Flying, £267,187.56 — PROVABLE NOW
DCMS, eight payments coded **"Flag Flying"** under "State Ceremonials Prog Costs", Apr 2011 –
Nov 2012 — including **£56,500 to a company called The Flag Consultancy Ltd** (2011-05-10) and
£56,667.27 to Piggotts (2012-11-21). *Objection:* Jubilee year; ceremonial flags on Whitehall are
a real statutory-ish function; the money bought flagpole maintenance, not vibes. All true. The
category is still called Flag Flying and there is still a flag consultancy.
**Caption:** "2011: austerity. Also 2011: the culture department begins an 18-month, £267,188
programme of 'Flag Flying', including £56,500 to consultants. Flag consultants."

### 3. The Foreign Office's card statement at Trump International Golf — PROVABLE NOW
FCO Government Procurement Card, 2013-08-19: **£2,360.00 and £4,545.00 at "TRUMP INTERNATIONAL
GO"**, merchant category **"Public Golf Courses"**. On 2013-09-16, **-£4,545.00** comes back.
Net: £2,360. *Objection:* card data; likely venue/event hire at the Aberdeenshire resort, and the
big line was refunded — no minister provably golfed. The caption must not allege golf, only quote
the ledger. **Caption:** "August 2013: the Foreign Office puts £6,905 on the government credit
card at Trump International Golf Links, category 'Public Golf Courses'. September 2013: £4,545
of it quietly comes back. The ledger offers no further comment, and neither do we."

### 4. Stallion and Unicorn Limited, £620,000 — twice — PROVABLE NOW (as a ledger fact)
FCDO transparency data: **£620,000.00 to "STALLION AND UNICORN LIMITED"** on 2021-01-06, and
**another £620,000.00** on 2021-12-23. Same spelling, two separate monthly files, both is_dup=0.
No expense_type given; area "FCO". *Objection:* we could not verify (offline task) what the
company does; the caption must claim nothing beyond the rows. **Caption:** "In 2021 the Foreign
Office paid £620,000 to Stallion and Unicorn Limited. Then, eleven months later, another
£620,000. We don't know what for. The file just says: Stallion and Unicorn. £1.24m."

### 5. "Lifting arm for dog doublet", £780 — PROVABLE NOW
Environment Agency procurement card (published via Defra GPC releases), 2012-07-20, VP
FABRICATION LTD, £780.00, description verbatim: **"Lifting arm for dog doublet"**. The
Dog-in-a-Doublet is a real sluice on the River Nene near Peterborough, named after a pub.
*Objection:* none. This is exactly what it looks like: Britain maintaining a piece of critical
flood infrastructure called the Dog-in-a-Doublet. **Caption:** "£780 of public money for a
'lifting arm for dog doublet' is a completely normal Environment Agency purchase, because the
Dog-in-a-Doublet is a sluice near Peterborough, which is named after a pub. No notes."

### 6. The Square Mile's culture budget — PROVABLE NOW (RO 2024-25, gross)
City of London, gross cultural spend 2024-25: **£92.0m for 15,497 residents = £5,940 per head —
102× the positive London-borough median (£58.28)**. Also 24× median on libraries, 21× on street
cleansing, £33,031 per resident on all services vs a borough median of £2,961. *Objection:*
gross figures (Barbican income offsets a chunk), and the City serves half a million commuters
plus City's Cash endowment funds — this is explainable. That's the joke: it's all legal and it's
still another planet. **Caption:** "Gross culture spending per resident, 2024-25: your borough,
about £58. The City of London: £5,940. It helps to own the Barbican and have 15,497 residents."

### 7. The Government texted Santa half a million pounds — PROVABLE NOW
Cabinet Office to **ITV TEXT SANTA LTD**: £500,000.00 on 2014-03-04 and £50,000.00 on
2015-03-25, expense_type "RESOURCE GRANTS PRIVATE SECTOR", area **"CHARITABLE GIVING"**.
*Objection:* these were match-funding grants to ITV's Christmas charity appeal — worthy cause,
money went to charities. Yes. The Cabinet Office still has a supplier called ITV Text Santa Ltd.
**Caption:** "In March 2014 the Cabinet Office paid £500,000 to a supplier named ITV Text Santa
Ltd, filed under 'charitable giving'. His Majesty's Government texted Santa. Santa replied."

### 8. Asylum support from "Motivation Solutions", in round millions — MISLEADING IF OVERCLAIMED, PROVABLE AS STATED
Home Office (UK Border Agency), 2013-05-08 to 2014-01-14: **ten payments of exactly
£1,000,000.00 each to SODEXO MOTIVATION SOLUTIONS UK LTD**, expense_type "Asylum Provision".
*Objection (real):* Sodexo's "Motivation Solutions" arm ran the Azure prepaid card for asylum
seekers — these are card-float top-ups, not fees, and the money reached claimants. Caption must
carry that. **Caption:** "How did the Home Office fund asylum subsistence in 2013? Ten flat
payments of exactly £1,000,000 to the prepaid-card arm of a catering giant — a division called,
genuinely, Sodexo Motivation Solutions."

### 9. The one-penny payments in the "over £25,000" files — PROVABLE NOW
Salisbury NHS Foundation Trust's file titled "Spend over £25,000" (April 2010) contains payments
to NHS Logistics of **£0.01** (several, plus 2p rows). NHS Norfolk & Suffolk ICB's "Expenditure
Over Threshold Report" (2026) pays GP practices **1p and 2p**. UK Shared Business Services has
paid **Oracle Corporation UK Ltd one or two pence, seventeen times since 2022 — 23p in total —
for "Computer Software Licences"** (alongside a £21.4m, 745-payment relationship). *Objection:*
these are credit-note remnants and ledger adjustments, not actual penny cheques. Of course. They
are still individually itemised in files that say "over £25,000" on the tin.
**Caption:** "NHS bodies publish everything they spend over £25,000. Sample entry: one penny.
Transparency, but make it homeopathic."

### 10. The MoD pays rent to an oyster fishery — PROVABLE NOW
Ministry of Defence to **COLCHESTER OYSTER FISHERY LIMITED**: 8 deduplicated payments,
£377,000, 2010–2016 — £165,000 "Fees for professional services" (Defence Estates), then a steady
£26,500 twice a year from the Defence Infrastructure Organisation under **"Rent and rates"**.
*Objection:* the MoD's Essex ranges sit on the Colne estuary; paying the fishery for
rights/access is rational estate management. Fine. It is still the Ministry of Defence paying
rent to an oyster fishery, twice a year, like clockwork. **Caption:** "Items on the MoD's estate
bill: £26,500, twice yearly, to the Colchester Oyster Fishery. Defence of the realm includes the
realm's oysters."

### 11. Diplomacy, per the card machine — PROVABLE NOW
Foreign Office card statements carry the merchant's category code, verbatim: **"AMUSEMENT PARKS,
CARNIVALS, CIRCUS, FORTUNE TELLERS"** (8 payments, £8,226.52 — including £3,720 at Tivoli
Gardens, Copenhagen, 2017); **"PAWN SHOPS"** (£608.32, Finland, 2015); **"WIG AND TOUPEE SHOPS"**
(£634.16, 2015); and **"FURRIERS AND FUR SHOPS"** — one of which is IKEA Long Island (£922.57).
The MoD's version anonymises suppliers to the category, so its ledger shows £999.84 paid to
"Amusement Parks/Circus" and £3,000 to "Health & Beauty Spas" (Jan–Feb 2020). *Objection:*
MCC codes are assigned by banks, embassy events happen at odd venues, and IKEA is not a furrier —
which is precisely the point. **Caption:** "Things the Foreign Office card statement files under:
fortune tellers (£8,226), a Finnish pawn shop (£608), a wig and toupee shop (£634). The MoD's
says only: 'Amusement Parks/Circus, £999.84'. We may never know which."

### 12. Real Reindeer Limited (accept no substitute) — PROVABLE NOW
Royal Borough of Greenwich: **£4,500 to REAL REINDEER LIMITED** (Woolwich Winter Warmer, 2016)
and £1,680 to THE REINDEER CENTRE (2014). Same borough also hired **JOSEPH`S AMAZING CAMELS
LIMITED** (£3,180, 2016). *Objection:* councils put on Christmas events; both are real
livestock-hire firms. Yes — and one of them had to be called Real Reindeer because fake ones
exist. **Caption:** "Greenwich Council, faced with a choice of reindeer suppliers, went with the
one called Real Reindeer Limited. £4,500. You can't put a price on authenticity, but they did."

### 13. The week Greenwich hired a jester and a shanty crew — PROVABLE NOW
Royal Borough of Greenwich, May 2017, both filed under **"Green Flag Parks Other Items"**:
£1,950 to **RUSS ERWYD T/AS CONWY JESTER** (2017-05-10 — a working jester) and £600 to **THE
PORTSMOUTH SHANTYMEN** (2017-05-17). *Objection:* park events programming, entirely normal.
Agreed. The line item is still "parks: other". **Caption:** "In one week in May 2017, Greenwich
Council booked an actual jester and a sea-shanty crew, and filed both under 'Parks: Other Items'.
Correctly, to be fair. What else would you call a jester?"

### 14. Bell ringers, filed under Public Health — PROVABLE NOW
North Yorkshire Council paid **ALL SAINTS KIRKBYMOORSIDE BELL RINGERS £1,000** (2026-05-27),
procurement category verbatim: **"151510 Healthcare > Public Health"**. The same council pays
brass bands (Kirkbymoorside Brass Band £1,265.74 — "Arts & Leisure > Organised Activities") and
**HAWES QUOITS CLUB £1,495** ("Sports & Playground Equipment"). *Objection:* small community
grants get shoved into whatever category tree the finance system offers; the classification is
an artefact. The artefact is the joke. **Caption:** "North Yorkshire Council gave the
Kirkbymoorside bell ringers £1,000 and classified it as Public Health spending. Honestly? Hard
to disagree."

### 15. Darts is performing arts now — PROVABLE NOW
North Yorkshire Council paid **DARTS WORLD LTD £28,814.05 on Christmas Eve 2025**, category
verbatim: **"291300 Arts & Leisure Services > Performing Arts"**. *Objection:* almost certainly
a staged darts exhibition night at a council venue, so arguably… correct. **Caption:** "On
Christmas Eve, North Yorkshire Council paid Darts World Ltd £28,814 under 'Performing Arts'.
Anyone who has watched a nine-darter knows the classification is right."

---

## HONOURABLE MENTIONS (all verified, all in receipts.csv)

- **The rival donkey suppliers.** Rushmoor paid South East Donkeys £325 a time (2019, once for
  "Victoria Day") then switched to Kelly's Donkeys, also £325 a time (2021, "Aldershot
  Promotions"). The going rate for donkeys in Hampshire is £325 and the market is contested.
- **The Ukulele Orchestra of Great Britain** — six bookings by Rushmoor, £35,468.16, expense_type
  "Payment to Artistes" (2010–2015).
- **All Star Superslam Wrestling** — Rushmoor again, 11 payments, £22,648.85, also "Payment to
  Artistes". Rushmoor's artiste budget covers ukuleles and suplexes.
- **Dinosaur Adventure Live Ltd** — Rushmoor, £13,761.32 over three summers.
- **Giant Cheese Ltd** — Rushmoor paid an events firm called Giant Cheese £1,940 under "Climate
  Change Project" (2021-09-16), then £8,988 more under "Aldershot Promotions".
- **HMS Dragon** — UK Trade & Investment paid a Royal Navy destroyer £1,000 for "Catering
  Supplies" (2015). The state, catering to itself, at sea.
- **THE COSMIC SAUSAGES** — Greenwich, £4,100 across 2012–13; a real covers band.
- **COUNTRYWIDE FALCONRY & PEST CONTROL SERVICES LTD** — Greenwich, £520 a year, three years
  running. The most honest company name in the corpus: the falcon IS the pest control.
- **McCallum Bagpipes** — the FCDO bought £4,881.50 of bagpipes (2023, 2024). Merchant category
  5733: music shops. Diplomacy by drone.
- **"Bumble Bee Colonies (Audax) each 10-20 workers"** — FERA card, £2,121.60 to Agralan Ltd
  (2012). The public sector procures bees by the colony, with headcount in the line item.
- **"Exercise Incursion of Exotic Pest"** — Defra booked a lodge for 15 people to rehearse an
  invasive-species emergency (£1,385.50, 2012). Sleep well.
- **Alpacas Peopleton Brook Farm** — Bristol City Council, 91 payments, £162,870.50 since 2022,
  expense_type "Services - Professional Fees". Care-farm provision — a real and good service;
  the funny part is strictly that the alpacas are professionals now.
- **Supplier named "X"** — DCMS-era Natural History Museum ledgers paid £0.01 to a supplier
  recorded only as "X" (Entomology Research, 2011). A penny, to X, for insects.
- **Mayor-making** — Rushmoor's recurring category for inaugurating mayors (£16,180.32 since
  2010), including £650 to Veolia — the bin company — at Mayor-making, twice, and regular
  regalia work by Thomas Fattorini Ltd (actual civic-regalia makers since 1827).
- **Free Ice Cream Limited** — Bristol paid £1,000 to a company called Free Ice Cream. So it
  wasn't.
- **HUNGRY YETI** — The National Archives, £10.00 flat (2013). The nation's records, powered by
  a tenner of street food.
- **Wombleton Parish Council** — North Yorkshire transfers to the parish of Wombleton, which is
  a real place and should be prouder of it.
- **The Grazing Goat, London** — DSIT expensed £506.22 at a pub called The Grazing Goat (2025).
- **WEASELTRON ENTERTAINMENT LIMITED** — UKTI paid £441.55 to Weaseltron under "First Time
  Exporter Credits". Britain's newest export: Weaseltron.
- **THE TEAPOTTERY LTD** — UKTI trade-mission support to a maker of novelty teapots (£665,
  2012). Soft power, brewed properly.
- **Marmalade On Toast** — the Queen Elizabeth II Conference Centre pays £500 a time in
  "Marketing" to a firm called Marmalade On Toast (8 payments; dates blank in the source file —
  weaker provenance, flagged).
- **"APPLEBY HORSE RAMP"** — Eden District Council's expense category for the Appleby Horse
  Fair: £1,400 of plant hire, filed under APFAIR.
- **Fools Paradise Limited** — Rushmoor's Victoria Day street theatre, £1,380. A council event
  named after a dead queen, staffed by Fools Paradise. No notes.
- **"Kennel Feed Stray Dogs"** — Rushmoor's monthly line for Bowenhurst Kennels, ~£800/month.
  Dry category, noble cause.
- **Tote proceeds to horseracing** — DCMS passed £58.9m of Tote money to The Racing Foundation
  (2012–14), categories "Support for Horseracing" and "Tote Proceeds to Horseracing". Not a
  joke, just a very large amount of horse.

## DEAD ENDS (nulls worth recording)
- **No clairvoyants, no morris dancers, no town criers, no taxidermy outside the Natural History
  Museum** (where it is simply procurement). The NHM's London Taxidermy and McKenzie Taxidermy
  payments (£2,717.69 total) are the least surprising rows in the corpus.
- "Llama" matches only a Spanish-language card merchant ("IZI EL TALLER SE LLAMA" — "the
  workshop is called"). Not a llama. Excluded.
- 'Sheep Dip Lane Academy', 'Eat That Frog CIC', 'Womble Bond Dickinson', 'Curious Hedgehogs',
  'Snap Dragons Nursery' etc. are ordinary schools/providers/law firms with good names — kept in
  receipts.csv (curious_hedgehogs) but not captioned, because the joke is on the name alone and
  they didn't choose to be in a government ledger. MR B SQUIRRELL (MoJ, £36,525 criminal legal
  aid) excluded from captions for the same reason: named individual.
- **"Same thing, different price" stays dead** — nothing here prices comparable units.

## EXCLUDED AMBIGUITIES (eyeballed and rejected)
- 'HYPNOS LIMITED' / 'HYPNOS CONTRACT BEDS' — bed manufacturer, not hypnotists.
- 'SANTA FE', 'SANTA MARIA', 'TOYOTA SANTA FE' — geography/cars, not Father Christmas.
- 'BADGER SOFTWARE', 'FERRET INFORMATION SYSTEMS' — software firms (Ferret does benefits
  calculators; the name is theirs but the joke is thin).
- 'MOLE VALLEY DC' (£22.1m) — a district council, not a mole.
- 'Witchcraft' pattern matched only network switches. The state buys no witchcraft.
- 'DINOSAUR' at TfGM (£510k) — a Manchester design agency called Dinosaur; real but the sums are
  boring design invoices.
- 'STALLION AND UNICORN' caption is limited to the ledger fact because the company's business
  could not be verified offline (flagged in Top 15 #4).

## Chart-ready files
- `receipts.csv` — 151 verified rows, one per receipt, columns: finding, publisher, supplier_raw,
  amount, date, expense_type, expense_area, source_file, dataset_title, source_url.
- Working queries in this directory reproduce every number (`build_receipts.py` prints the
  dedupe-checked aggregates used above).
