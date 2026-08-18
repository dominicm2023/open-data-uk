# THE SEASIDE SEWAGE LEAGUE — strand notes

**Scope: England only.** Source is `analysis\sewage\joined.csv` — the 14,180 English storm
overflows in the water companies' Event Duration Monitoring (EDM) annual return, calendar
2025, with the geographic joins documented in `analysis\sewage\REPORT.md`. Scotland, Wales
and Northern Ireland are not in the return and are never compared. Dŵr Cymru rows are its
assets *in England* (border catchments), not Wales.

Everything here is reproduced by **`build_seaside.py`** in this folder (pure stdlib Python,
no network). Run it from anywhere; paths are absolute.

## Files

| file | what it is |
|---|---|
| `seaside_league.csv` | (a) the coastal league: 46 seaside districts ranked by 2025 spill-hours within 10 km of the district centroid |
| `town_cards.csv` | (d) per-town cards: overflows within 10 km, spills, hours, worst site by name + distance, caveat column |
| `company_totals.csv` | (b) per-company totals, three scopes: all England / seaside-league union / LSOA-coastal-5km flag |
| `map_points.csv` | (c) all 14,180 overflows: lon/lat, spills, hours, league flag, nearest league town + km |
| `top20_sites.csv` | (c) top-20 sites by hours, two scopes (`england`, `seaside_league`), named, with nearest league town |

## Method (printed here so it can be printed on the image)

1. **Universe** — gazetteer places matching an English local authority in the RO 2024-25
   register (names normalised: `UA/DC/BC/MBC` suffixes stripped, `&`→`and`; aliases such as
   "Medway Towns"→Medway, "Durham"→County Durham, "Newcastle"→Newcastle upon Tyne; duplicate
   gazetteer aliases deduped). England only, by construction.
2. **Coastal candidates** — district centroid within **12 km** of the ultra-generalised
   coastline (`coastline.json`, ONS/OS countries boundary, ~1.3 km tolerance). Rationale:
   10 km search radius + 2 km generalisation slack, i.e. the search circle must plausibly
   reach the sea. Not a curated-only list: the threshold does the first cut.
3. **Curated exclusions, every one named** (50 applied; full list with reasons printed by
   the script): all London boroughs — the generalised boundary treats the tidal Thames as
   coast — plus estuary/tidal-river districts with no recognised seaside resort (Liverpool,
   Hull, Southampton, Bristol, Medway, Middlesbrough, Preston, Warrington, St Helens, …).
   Kept despite estuary frontage, because they have recognised resorts: Swale (Sheerness/
   Leysdown), Castle Point (Canvey seafront), Southend-on-Sea.
4. **League metric** — total monitored spill events and spill-hours in calendar 2025 at
   overflows within **10 km (haversine) of the district centroid**. This is a
   *place-radius* measure: it is *not* a bathing-water claim (no bathing-water dataset
   held) and not a council-duty comparison — the class column (UA/MD/SD) is stated on
   every row, and cross-class rows sit together only because the radius is geographic.

**The 46:** Adur, Arun, Blackpool, Bournemouth Christchurch and Poole, Brighton & Hove,
Canterbury, Castle Point, Cornwall, Cumberland, Dover, East Devon, East Suffolk,
Eastbourne, Folkestone & Hythe, Fylde, Gosport, Great Yarmouth, Hartlepool, Hastings,
Havant, Isle of Wight, King's Lynn & West Norfolk, Lancaster, Lewes, New Forest,
North East Lincolnshire, North Somerset, North Tyneside, Plymouth, Portsmouth,
Redcar & Cleveland, Rother, Sefton, Somerset, South Hams, South Tyneside,
Southend-on-Sea, Sunderland, Swale, Tendring, Thanet, Torbay, Torridge, Wirral,
Worthing, Wyre.

## Headline recomputed numbers (all verified this run)

- League top 5 (hours within 10 km, 2025): **Plymouth 33,275** (163 overflows) —
  **Cumberland 21,276** — **East Devon 16,508** — **South Hams 16,426** —
  **South Tyneside 13,328**. Bottom: Dover 88, Thanet 96, Canterbury 138.
- CONTENT_SLATE cross-checks all reproduce exactly: East Devon 16,507.5; Torbay 13,223.1;
  Sefton 7,046.5; Blackpool 2,158.2; Thanet 96.1.
- Companies (England 2025): **South West Water 407,006 hours** — most of any company,
  21.8% of England's total from 9.6% of its monitored overflows. Then United Utilities
  327,452; Yorkshire Water 285,586.
- Coastal (LSOA-within-5km flag, the slate's definition — reproduced): SWW **141,190
  hours**, **1.88x** United Utilities (75,219), **42.0%** of all coastal spill-hours.
  Under this strand's league-union definition SWW is 96,593 hours, 1.92x UU, 42.3% —
  the "1.9x nearest rival" claim survives both definitions.
- 1,672 overflows sit within 10 km of at least one league town.
- Worst coastal site: **Salcombe Regis WWTW CSO** (South West Water), above the coast
  east of Sidmouth — 235 spills, **5,446 hours** in 2025. It is also England's worst
  site outright.

## Caveats — print these, don't bury them

1. **Centroid-radius is crude, and here is the worked example.** Sefton's 10 km circle
   crosses the Mersey and captures three **Birkenhead WWTW** monitors on the Wirral bank,
   9.44–9.49 km from the Sefton centroid: 146 spills and 1,498 of Sefton's 7,046 hours.
   Birkenhead WWTW (1,272.5 h) is in fact listed as Sefton's *worst site* on its card —
   the caveat column says so. Same crudeness class: large-district centroids (Cornwall,
   Somerset, Cumberland, East Suffolk) measure the circle, not the famous resorts;
   caveats are on those cards too.
2. **Rows are not additive.** Neighbouring circles overlap (Blackpool/Fylde/Wyre,
   Adur/Worthing/Brighton, Plymouth/South Hams). Company league-union columns dedupe
   sites; the league itself must never be summed.
3. **The league cannot see some famous seaside.** Districts whose centroid is >12 km
   inland are honestly excluded, and their resorts are invisible at LAD level:
   East Lindsey 18.7 km (Skegness, Mablethorpe), North Yorkshire 58.7 (Scarborough,
   Whitby, Filey), East Riding 16.4 (Bridlington, Hornsea, Withernsea), Dorset 17.8
   (Weymouth, Swanage, Lyme Regis), North Devon 15.7 (Ilfracombe, Woolacombe),
   Chichester 13.8 (the Witterings, Selsey), North Norfolk 13.3 (Cromer, Sheringham),
   Teignbridge 12.5 (Dawlish, Teignmouth), Wealden 17.4 (Pevensey Bay), Northumberland
   17.3 (Amble, Seahouses), County Durham 35.9 (Seaham), Westmorland & Furness 32.7
   (Grange), Isles of Scilly 44.9 (no Scilly ring in `coastline.json`). **Consequence:
   the league-union company columns understate the Yorkshire/Lincolnshire coast — use the
   coastal-5km-flag columns for company comparisons.** The fix, if this strand graduates:
   a town-level gazetteer (Skegness, Margate, Scarborough…), not LAD centroids.
4. **Hours are hours.** EDM measures spill *duration* at monitored overflows — not volume,
   not concentration. Monitor uptime is ~97% and not geographically biased
   (`analysis\sewage\REPORT.md`). 98 sites carry a literal `#N/A` name in the companies'
   own return — including England's #2 site by hours (SBB01407, South West Water,
   4,967 h, near Bude). Keep the id when naming.
5. **"Coast near seaside towns", not bathing waters.** No bathing-water dataset is held;
   no claim about beach water quality is made — only monitored spill-hours near places.

## Caption options (Joined Up voice)

**Visual 1 — the league table**
1. "The English seaside, ranked by hours of sewage. Within 10 km of Plymouth's centre,
   storm overflows discharged for 33,275 hours in 2025. Dover's total: 88. Book
   accordingly."
2. "46 seaside districts, one league, straight from the water companies' own monitors:
   Plymouth 33,275 spill-hours, Cumberland 21,276, East Devon 16,508 — and Thanet on 96.
   The coast is not one story."
3. "Where the sewage went on holiday in 2025. Every English seaside district ranked by
   monitored spill-hours within 10 km — method printed on the image, full table published
   for anyone to re-cut."

**Visual 2 — the dot map**
1. "England's 14,180 monitored storm overflows, 2025. Every dot is a pipe; the darker the
   dot, the longer it spilled. Find your beach."
2. "One dot per storm overflow — 1,672 of them within 10 km of a seaside district centre.
   The worst on the coast: Salcombe Regis WWTW CSO, east of Sidmouth, 5,446 hours."
3. "The sewage map of England, drawn from the companies' own event-duration monitors.
   The 20 longest-spilling sites are named. None of them asked to be."

**Visual 3 — the company chart**
1. "South West Water: 407,006 hours of monitored spills in 2025 — the most of any company —
   and 141,190 of them within 5 km of the coast. That is 42% of England's coastal
   spill-hours from one firm. Holiday country."
2. "Ten companies, one podium nobody wants. South West Water leads England on total
   spill-hours and runs the coast at 1.9x its nearest rival."
3. "A fifth of England's spill-hours, two-fifths of the seaside's. South West Water's own
   monitors, South West Water's own numbers."

**Visual 4 — the town cards**
1. "Your seaside town's 2025 sewage card: the overflows within 10 km, the hours they ran,
   and the worst pipe by name. Sefton's worst 'local' site is Birkenhead WWTW — across
   the Mersey — and the card says so."
2. "Pick your resort, get the receipts. Sefton: 56 overflows within 10 km, 1,507 spills,
   7,046 hours; worst site Birkenhead WWTW, 1,273 hours. Method and caveats printed on
   every card."
3. "Personalised, not personal: each card names the pipes near your beach town and the
   company that runs them. Straight from the EDM return, radius stated, caveats included."

## Publication guardrails

- Tier 4 content (names towns and companies): per the Joined Up split, **does not
  auto-publish** — human review required.
- Single-year cross-section (2025 only): the monitors-growth trend trap does not apply,
  and no year-on-year claim is available from these files.
- State "England" and "monitored" in every caption; never let a crop remove the method
  line.
