# THE LIBRARY LOTTERY — strand data notes

Chart-ready data for the libraries strand. Everything here is reshaped from
`analysis/ro/ro_per_head.csv` (MHCLG Revenue Outturn, RO5 library service
line) by `build_libraries.py` in this directory — run it to rebuild, read
`build_log.txt` for the recomputed headline figures. No new sources, no
network.

**Provenance chain:** RO5_2024-25.ods / RO5_LA_Data_202425 / col 97
("Library service — Net Current Expenditure (C7 = C3 − C6)") and the
2013-14/2018-19 equivalents, parsed by `analysis/ro/03_parse.py` into
`ro.sqlite`; per-head via ONS mid-year population on period-correct
boundaries; real terms via HMT GDP deflator (June 2026 QNA), 2024-25 prices
(2013-14 ×1.3693, 2018-19 ×1.2692). Full audit trail in
`analysis/ro/REPORT.md` and `findings.json`.

**Tier rule, applied throughout:** libraries are an upper-tier/unitary duty.
Library-responsible classes are LB (London borough), MD (met district),
UA (unitary), SC (shire county). Shire districts never appear. No table
mixes classes; every row states its class.

---

## Files

### (a) `league_2024-25_{LB,MD,UA,SC}.csv` — within-class league tables

One file per class, ranked by **net** (NCE) £/resident, 2024-25, with
**gross and income alongside** so the charging check is visible on the page
(`income_share_of_gross_pct` is the tell). City of London (£351/head,
pop ~11k) and Isles of Scilly are excluded from leagues project-wide.
SC is included beyond the brief because counties are library authorities
and the map/arc need them; ignore the file if unwanted.

Recomputed extremes (net £/head):

| class | n | max | min | median |
|---|---:|---|---|---:|
| LB | 32 | Kensington & Chelsea 43.84 | Barking & Dagenham 3.35 | 14.66 |
| MD | 36 | North Tyneside 23.74 | Sunderland 4.24 † | 11.96 |
| UA | 61 | Brighton & Hove 22.34 | Blackpool −1.42 † | 10.39 |
| SC | 21 | Nottinghamshire 15.64 | Leicestershire 6.37 | 10.34 |

† = annotated artefact, see below. All extremes were checked against the
hand-check graveyard in `analysis/ro/REPORT.md` before inclusion.

**Graveyard annotations (in the `note` column — do not rank or caption
these without the caveat):**
- **Blackpool (UA):** booked income (£2,606k) exceeds gross spend
  (£2,402k); the net line is negative. An accounting artefact, not a
  council without libraries. The true UA minimum on a clean read is
  Cornwall £3.75.
- **Enfield (LB):** income is ~47% of gross — the £6.03 net is partly a
  charging/income artefact.
- **Sunderland (MD):** culture delivered via trust; the library line may
  understate the library share of the trust grant. Named only with that
  caveat.
- **Wigan (MD), Luton (UA):** their 2013-14 library line was ~£0/head
  (trust/outsourced booking), so booked levels may not capture full
  service cost. Flagged wherever they appear.
- **Trafford (MD):** auto-flagged, income ≥ 40% of gross.

**Caption options (league bars):**
1. "Every council here has the same statutory duty: a 'comprehensive and
   efficient' library service. What that's worth ranges from £3.35 a
   resident to £43.84 — inside one class of council, inside one year."
2. "The library league table London's town halls don't publish: net spend
   per resident, gross alongside, so you can see who's charging and who's
   simply not spending."
3. "No formula, no floor, no national standard. Library funding is whatever
   your council decides it is — and identical councils decide numbers 13x
   apart."

### (b) `callout_kc_vs_bd.csv` — the 13.1x two-bar callout

Long format, ready for a grouped two-bar: authority × measure (net, gross)
× £/head. Kensington & Chelsea net **43.84** vs Barking & Dagenham
**3.35** = **13.1x**; gross **46.21** vs **4.04** = **11.4x**. The gap
survives the charging check — B&D's gross is genuinely that low; this is
the verified comparison in REPORT.md, not a booking quirk. Same class
(London borough), same city, same year.

**Caption options:**
1. "Thirteen times. Kensington & Chelsea puts £43.84 a resident into its
   libraries; Barking & Dagenham £3.35. Same duty, same class of council,
   same city, same year."
2. "And it isn't a charging quirk: before any income at all, the gap is
   still 11.4x. One borough is buying a library service; the other is
   keeping the lights on."
3. "The 13x gap, gross-checked. Net can lie when councils charge — so here
   is spend before income too. The story doesn't change."

### (c) `arc_class_real.csv` + `slope_authorities.csv` — the arc

**`arc_class_real.csv`** (long: cls, year, real £/head, n, population):
every library-responsible class cut hard and cut together —

| class | 2013-14 | 2018-19 | 2024-25 | change |
|---|---:|---:|---:|---:|
| LB | 27.24 | 19.57 | 16.29 | −40.2% |
| MD | 22.31 | 15.76 | 12.57 | −43.7% |
| UA | 18.62 | 13.78 | 10.67 | −42.7% |
| SC | 17.81 | 12.94 | 10.97 | −38.4% |

Caveat to carry: UA/SC class **composition changed** over the window (local
government reorganisation moved county+district areas into the UA class;
Cumberland filed no 2024-25 return and is excluded from both numerator and
denominator that year). LB and MD are stable classes, and they tell the
same story, so composition is not driving the direction. England-level
(all five principal classes): 20.44 → 14.79 → 12.00, **−41.3%**
(`analysis/ro/england_real_arc.csv`).

**`slope_authorities.csv`** (slope-chart-ready: ons_code, name, cls,
real_2013_14, real_2018_19, real_2024_25, change_pct, note): the
stable-authority census, recomputed identically to
`analysis/ro/04_analyse.py`. Same ONS code at both ends; guards drop a
2013-14 base under £2/head real (outsourced/misbooked, not a service) and
a non-positive 2024-25 net (income artefact). Exclusions listed with
reasons in `slope_excluded.csv` (Blackpool, Luton, Wigan).

**Recomputed and confirmed: n = 139, fell in 132, median change −42.4%.**
Deepest: Barking & Dagenham −86%, Enfield −79% (flagged: partly income
artefact), Slough −79%, Sunderland −77% (flagged: trust), Cornwall −76%.
Grew (all 7): Salford +56%, Camden +15%, Essex +14%, Brighton & Hove +8%,
Calderdale +3%, Gloucestershire +2%, Barnsley +2%.

Cite, don't claim novelty: direction reconciles with NAO 2018 (cultural
services −34.9% real, 2010-11 to 2016-17) and the IFS-documented
acute-vs-amenity squeeze — this is confirmation on a longer window.
Deflator caveat: the GDP deflator is not a council input-cost index, so if
anything the amenity cuts *understate* lost provision.

**Caption options (slope chart):**
1. "132 of 139. That's how many English library authorities spent less per
   resident, in real terms, in 2024-25 than in 2013-14. The median cut
   was 42%."
2. "This is what a national choice looks like drawn one council at a time:
   139 lines, 132 pointing down, a median 42% below where it started."
3. "Boroughs, mets, unitaries, counties — every class of library authority
   cut by roughly the same margin, around 40% real per resident since
   2013-14. Austerity didn't pick favourites; it took the libraries
   everywhere."

### (d) `map_2024-25.csv` — map/hex colouring

ons_code, name, cls, class_label, value (net £/head, 2024-25), note.
All 152 library-responsible authorities that filed (Cumberland filed no
return and is absent — leave it hollow, don't impute). Includes City of
London (351.36) and Isles of Scilly (27.28) with exclusion notes — clamp
or grey them rather than letting them eat the colour scale, and Blackpool's
−1.42 (artefact, grey it too). **Colour within class or bin carefully**:
classes do different jobs, and the tier rule holds on maps as much as in
tables.

**Caption options:**
1. "Postcode lottery is a cliché until you colour it in: net library spend
   per resident, every English library authority, 2024-25."
2. "Where you live sets what your library is worth — from under £4 a
   resident to over £40. No formula produced this map; 152 separate
   council decisions did."
3. "And before anyone says 'poorer places need less': within London and
   the mets, library spend shows no relationship with deprivation at all
   (Spearman ρ ≈ 0). This map is choices, not need."

---

## What a fair critic would say (carry into any published piece)

- Net lines follow booking choices (trusts, recharges, charging) — that is
  why gross is published alongside net and artefacts are annotated, never
  silently ranked.
- The GDP deflator is not a council cost index (cuts likely understated).
- 2024-25 is a single year; nothing here smooths.
- Class composition changed for UA/SC over the arc window (stated above).
- IMD is 2019-vintage; ρ ≈ 0 is no gradient, not proof of fairness.
- No partisan claims are possible from this build — no political control
  dataset was fetched.
