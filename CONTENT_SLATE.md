# The Joined Up content slate

Researched 18 August 2026: four web studies (formats, case studies, failure modes; the topics leg failed transiently and was not replaced) and three database inventories (tested joins, fetch unlocks, personalisation), synthesised under the standing rule that every concept needs a researched format, a live subject and a TESTED join.

THE JOINED UP CONTENT SLATE
12 concepts, ranked by share-potential x defensibility. Every join cited below was tested in the db reports; every fetch was verified fetchable from index evidence. Windows and denominators stated because that is where content dies.

---

1. TITLE: YOUR NEAREST OUTFALL (the per-area card)
HOOK (template, Blackpool FY1 shown): "MANCHESTER SQUARE PS is 0.9 km from your front door, on the seafront. In 2025 it spilled sewage 42 times for 238 hours — more spills than 84% of England's 14,180 monitored overflows. Within 5 km of you: 12 overflows, 188 spills, 476 hours. Find yours."
FORMAT: Find-your-area personalisation (archetype 1), rendered as a 4:5 per-area card so the X version is self-contained (link suppression). This is the format the research ranks first: identity-sharing at scale, one dataset = thousands of local headlines, and the Top of the Poops precedent proves it in exactly this domain. Feeds the league-table and map formats downstream.
DATA: HAVE — analysis/sewage/joined.csv (14,180 sites, 2025 spills/hours, true coordinates), IoD2019 File7, lsoa2011_pwc.json; 97.4% of England's population within 5 km of a monitored overflow, so ~84% of GB gets a rich card. FETCH — ONSPD (~200MB zipped, verified in index, ONS Geography Licence) to enable the postcode entry box and correct LSOA assignment; until then, place-name entry via gazetteer.json works.
RECEIPT: EDM 2025 Annual Return, named site, distance-calculation method (great-circle from postcode centroid), "monitored overflows only", IMD 2019 row cited, executable query.
TIER: 4 for the card template and copy (names sites and water companies); instances are then mechanical fills of the approved template — the sign-off is of the generator, logged as such.
OBJECTION: "Absence of a monitor is not absence of a spill, and 52% of overflows sit on LSOA boundaries." Both pre-armoured: the card uses distance radii, never LSOA membership, and the band says "monitored overflows only". Wales/Scotland get an honest data-border card, not a fake one. "Storm spills are permitted" — the card claims counts and hours, not illegality.

2. TITLE: THE SEASIDE SEWAGE LEAGUE
HOOK: "The English seaside, ranked by hours of sewage. Within 10 km of the coast at East Devon: 16,508 spill-hours in 2025. Torbay: 13,223. Sefton: 7,046. Blackpool: 2,158. Thanet: 96. One company — South West Water — accounts for 141,190 coastal spill-hours, 1.9x its nearest rival. Book accordingly."
FORMAT: League table (archetype 5) plus a one-variable coastal map (archetype 4). Rankings give every reader a search task and every local paper a headline — the Top of the Poops / Bureau Local local-multiplier mechanic. August publication is the news peg.
DATA: HAVE — tested join 11: joined.csv spill-hours x gazetteer seaside-LAD centroids, 10 km radius; company totals from same table (South West Water 407,006 total spill-hours, most of any company).
RECEIPT: EDM 2025, the 10 km centroid-radius method stated in the image, "coast near seaside towns — not a bathing-water claim" (no bathing-water dataset held), the known crudeness example (Birkenhead WWTW lands in "Sefton" across the Mersey) disclosed, query attached.
TIER: 4 — names towns and companies.
OBJECTION: "Centroid-radius is crude and hours are not volume." Answer is in the band: method printed inside the image where crops can't remove it, claim limited to hours of monitored discharge, full table published for anyone to re-cut. Single-year cross-section, so the monitors-growth trend trap (spills "rose 36x") does not apply — and we never compare against Scotland/Wales, which aren't in the return.

3. TITLE: THE GRADIENT THAT ISN'T THERE
HOOK: "We assumed sewage gets dumped on the poor. So we checked: all 14,180 monitored overflows in England against the official deprivation index. There is no gradient. Wilmslow — in England's richest tenth — has 521 spills within 5 km. Sewage is one of the few things in Britain that is not worse for being poor. We publish what we find, including this."
FORMAT: Expectation-vs-reality pair (archetype 6) — the single strongest share trigger is surprise (+190.9%), and in a feed of manufactured outrage "we checked and it isn't there" is the surprise. The formats report explicitly recommends publishing this null as a map.
DATA: HAVE — the join was run and checked hard (project known fact); Wilmslow E01018602, decile 10, 521 spills/3,185 hours within 5 km verified in the local-hooks report.
RECEIPT: join method, distance-radius framing, the 52%-on-boundaries caveat, IMD 2019 vintage stated, executable query, and a standing invitation to re-run it.
TIER: 3 — no body accused; still human-reviewed first time as a flagship methods piece.
OBJECTION: "Your null is an artefact — monitors follow sewers, not people, and IMD 2019 is seven years stale." Answer: the claim is exactly scoped to monitored spill counts vs IMD 2019, stated in the image; and we pre-commit to the re-test — Universal Credit by LSOA (nomis, free CSV, tens of MB, verified route in index) re-runs the check against 2026 deprivation. If the null breaks, that's the follow-up post. This piece is also armour: it proves the provenance band is real, which every later claim borrows.

4. TITLE: CARILLION: THE LAST DECADE, IN RECEIPTS
HOOK (carousel, slide 1): "The state paid Carillion £2.05bn. Its best year ever was 2017 — £359.8m — the year before it collapsed. Swipe for the whole ride, ending with the supplier name the ledger itself records: 'CARILLION CONSTRUCTION LIMITED - IN LIQUIDATION'."
FORMAT: Carousel (archetype 3): 3.1x engagement, 22-23% more saves, and this is a born 6-slide arc (£55.2m in 2010 → the ramp → £359.8m peak → January 2018 collapse → £270.6m still flowing in 2018 → the liquidation string verbatim). Final slide is an annotated receipt (archetype 8) — verbatim primary text as punchline, the Led By Donkeys mechanic.
DATA: HAVE — tested join 3: 43 supplier strings LIKE %CARILLION%, JVs excluded, yearly series verified; CarillionAmey MoD housing £1.21bn is the biggest component.
RECEIPT: all 43 strings listed, the two excluded JV strings named, publisher coverage windows, query.
TIER: 4 — names companies and departments (the company is dead, which lowers legal risk, not editorial duty).
OBJECTION: "2018 payments are contract wind-down and receiver continuity, not endorsement." Correct, and we never say otherwise: the claim is payment flows with dates, not procurement decisions. We do not claim payments rose into the death-month — the verified series is yearly, so the hook claims the yearly facts only.

5. TITLE: THE MARCH SPLURGE
HOOK: "Use it or lose it: 4 in 5 public-body financial years end in a March spending spike. The median body puts 10.8% of its year's cash through in the final month — a tenth of bodies put through nearly a fifth. 11.8 million published transactions, £3.27tn, and the same shape every year. Budgets that punish saving get exactly this."
FORMAT: Annotated single chart with narrative title (archetype 2) — twelve monthly bars, March in the accent colour, title-as-claim, annotations doing the explaining. Survives as a screenshot, needs no link.
DATA: HAVE — tested join 1: n=286 publisher-fiscal-years with all 12 months present; median March share 10.77% vs 8.33% uniform; above-uniform in 234/286 (82%); top decile >18.1%; survives removing DHSC; holds in councils-only (10.05%).
RECEIPT: definition of the panel (complete publisher-years only), clean-set filter (is_dup=0, non-empty supplier), the state-to-state share noted, query.
TIER: 3 — aggregate pattern, no body named. First-run human review regardless.
OBJECTION: "March is legitimate year-end invoice settlement, not waste." We claim the distribution, not waste — the editorial line ("budgets that punish saving get this") is an argument about incentives sitting on an unchallengeable shape. The transfer trap (failure mode 3) is dodged by claiming a pattern, never "cost of" anything.

6. TITLE: WHEN THE STATE PANICKED, IT PHONED THE USUAL THREE
HOOK: "Serco, from the published ledgers: £77.6m in 2019, £494.2m in 2021. G4S: £60.2m to £573.9m. The pandemic didn't diversify the state's suppliers — it concentrated them. DHSC alone paid Serco £704.3m and G4S £545.1m across 2020-21, the Test and Trace era. Then the tide went out on schedule."
FORMAT: Annotated chart (archetype 2), two or three lines with the spike annotated per-payer; the per-publisher attribution is drawn on the chart, VIP-lane style — the join is the argument.
DATA: HAVE — tested join 2: censused variants.csv exact-string lists against 11.8M rows; drivers verified to paying department.
RECEIPT: variant lists, per-publisher figures, window, the note that these are actual payments (not contract values), query.
TIER: 4 — named companies.
OBJECTION: The £37bn trap in reverse — conflating payments with programme cost or wrongdoing. Armour: these are transaction outturns (the very thing Full Fact used to beat the £37bn claim), attributed to paying bodies, with no "wasted" claim. "Contracts were delivered as specified" — possibly; the claim is who and how fast, which stands either way.

7. TITLE: £6.25bn, PAYEE WITHHELD
HOOK: "The single biggest 'supplier' in Britain's spending transparency data is the phrase 'Supplier Name withheld' — £5.89bn, most of it aid money. Add every redaction label and £6.25bn is published as paid to nobody we can name. Some of it is defensible — aid partners in dangerous places, 70,868 social-care payments in Greenwich. That's exactly the problem: the redactions are where the judgment calls live, and nobody publishes the rules."
FORMAT: Annotated receipt (archetype 8) — the verbatim redaction strings ARE the graphic — plus one bar chart of the top labels. Provenance as punchline.
DATA: HAVE — tested join 5: 69 redaction-shaped strings, £6.25bn; DFID £5.40bn 2012-2020 then FCDO £482m; Greenwich 'REDACTED PERSONAL INFORMATION' £177.6m.
RECEIPT: all 69 strings, per-publisher split, dates, query.
TIER: 4 — names departments.
OBJECTION: "Redaction is lawful and often protective." Conceded inside the hook — the claim is scale plus absence of stated policy, never insinuated cover-up. Attack the number, not the mind: no motive is asserted anywhere.

8. TITLE: THE AMAZON STATE
HOOK: "2011: the bodies that publish their spending recorded £40,000 to Amazon. 2025: £138.5m. Same ledgers, same method: BT fell from £652m to £41m. Britain's public procurement didn't shrink — it changed address, to Seattle."
FORMAT: Annotated single chart (archetype 2), two lines crossing — Amazon up ~3,000x, BT down — which is also an expectation-vs-reality pair in one frame.
DATA: HAVE — tested join 4: 566 censused Amazon/AWS strings, yearly series verified; BT comparison from same corpus, same method.
RECEIPT: variant-census method, the publisher-mix caveat stated in the image, note that central departments present throughout show the same direction, window, query.
TIER: 4 — named companies.
OBJECTION: "Your panel of publishers changed over the window — this is coverage, not growth" (the instrumentation-trend trap, our most-flagged failure mode). Armour: the BT counter-series is same-corpus/same-method and moves the opposite way, which a pure coverage artefact cannot explain; the constant-panel (departments present throughout) subseries goes in the band. Whoever holds the boring full-window number wins the exchange — so we publish it first.

9. TITLE: THE GRADIENT THAT IS THERE (fuel poverty)
HOOK (numbers pending fetch — placeholders marked, nothing publishes until filled from the real file): "Sewage doesn't check your income — we tested that. Fuel poverty does. [X]% of households in England's most deprived neighbourhoods can't afford to heat their homes, against [Y]% in the richest. One of these maps is flat. The other is a staircase."
FORMAT: Expectation-vs-reality pair (archetype 6) with our own null as the foil, drawn as population-fair cartograms, not raw LSOA choropleths (failure mode 7).
DATA: FETCH — DESNZ Fuel Poverty in England sub-regional (LSOA), <100MB, OGL, verified fetchable (17 XLSX resources, sample checked 200); direct LSOA-code join to IoD2019 already on disk, no postcode lookup needed.
RECEIPT: DESNZ release year, LILEE definition quoted, LSOA join, cartogram method, query.
TIER: 3.
OBJECTION: The 5G-map trap — fuel poverty (Low Income Low Energy Efficiency) shares an income component with IMD, so part of the gradient is definitional, two poverty maps correlated with each other. This is the strongest attack on the slate and it ships pre-answered: the band states the definitional overlap and we additionally plot against the IMD non-income domains. If the gradient collapses without the income domain, that becomes the finding — either result publishes.

10. TITLE: EMPTY HOMES, FULL WAITING LISTS
HOOK (per-council card, real numbers after fetch): "[Council] has [N] households waiting for a home and [M] homes standing long-term empty. Both numbers are official. Both are published by government. They are almost never printed side by side. Find your council."
FORMAT: Find-your-area card (archetype 1) + council league table (archetype 5); the Bureau Local mechanic — one national join, hundreds of local stories, dataset published for local journalists to mine.
DATA: FETCH — MHCLG Live Table 615 (vacants, verdict=data, 0.3-1.1MB) + Live Table 600 (waiting lists, XLSX behind gov.uk webpage), <20MB total, verified in fetch-unlocks; HAVE — ONS council register + centroids for the map.
RECEIPT: both table vintages, MHCLG's definition of "long-term vacant", counts AND per-1,000-household rates (small-council denominator trap), query.
TIER: 4 — names councils.
OBJECTION: "Empty homes can't simply house waiting lists — probate, renovation, wrong place." True, and the claim is the juxtaposition, not a policy arithmetic; no "could house X families" conversion is made without a matching-geography basis. Waiting-list definitions vary by council — stated in the band; and per Bureau Local's precedent, MHCLG's own figures can be wrong, so the correction loop is designed in, not feared.

11. TITLE: THE LIGHTS GO OUT WHERE THE ARGUMENT IS
HOOK (carousel of nulls): "Asylum hotels are the most fought-over £2bn a year in Britain. In the published spending ledgers we can read, Home Office data stops in June 2018 — the entire hotels era is dark. Food banks: £225,000 ever, across 11.8 million transactions. Allotment waiting lists: 166 allotment datasets in the national index, zero waiting lists. The state publishes least exactly where you'd look hardest."
FORMAT: Carousel (archetype 3), one null per slide, each with its receipt. Saves-bait: this is an argument people keep.
DATA: HAVE — tested joins 9 and 14 (Clearsprings £95.8m ends 2018-06; Trussell Trust zero rows; 7 real food banks £225k) plus index nulls from the fetch-unlocks report (0 waiting-list datasets in 84,486 findable).
RECEIPT: exactly which files were read and where they end, the 12-council coverage caveat carried loudly, string-match exclusions (MATTHEW TRUSSELLE), queries.
TIER: 4 — names the Home Office.
OBJECTION: "That's your parser failing, not their transparency failing" — the organisation-vs-infrastructure conflation we ourselves documented. Armour: every claim attaches to the artefact measured ("the files we can read", file list published, correction invited), never "the Home Office stopped publishing". One acknowledged tension: this is the slate's only inside-baseball-adjacent piece; it earns its slot because the subject (asylum, food banks) is Britain, not catalogue hygiene — and it ranks 11th accordingly.

12. TITLE: THE GAZPROM ROW
HOOK: "9 March 2023 — thirteen months after the invasion of Ukraine — Transport for Greater Manchester's published ledger records its last payment to a supplier named Gazprom. £126.9k flowed after the invasion began. One caveat, printed on the image: the UK retail arm was seized and renamed SEFE in late 2022. The name on the ledger is the finding. Checkable to the row."
FORMAT: Annotated receipt (archetype 8) — a single ledger row, circled, provenance band as caption.
DATA: HAVE — tested join 8: 6 Gazprom strings, TfGM £99.9k (2022) + £27.0k (2023), last payment 2023-03-09.
RECEIPT: the row itself, the SEFE seizure caveat inside the image where crops can't remove it, query.
TIER: 5 — names one public body over a small sum with a beneficial-ownership complication; the highest-care rung exists for exactly this.
OBJECTION: "By then it was effectively state-controlled SEFE fulfilling legacy contracts; the sum is trivial." Both true, both printed on the graphic. The claim never exceeds "this name, this date, this ledger". If review judges the caveat swamps the point, it drops — the row costs nothing to hold.

---

BUILD FIRST (three, plus one fetch to start immediately)

1. THE SEASIDE SEWAGE LEAGUE (concept 2). Entirely on disk, join already tested to the number, and it is August — peak seaside salience. League + local unit is the proven one-dataset/650-stories mechanic; every coastal MP and local paper is an amplifier. Highest immediate share-potential of anything we can ship this week.
2. THE GRADIENT THAT ISN'T THERE (concept 3). On disk, already verified hard. Surprise is the strongest measured share trigger, and a published null is the cheapest credibility we will ever buy: it demonstrates the provenance band is real before we publish anything a critic wants to attack. It is also the load-bearing foil for concept 9.
3. CARILLION (concept 4). On disk, tested, the strongest carousel material we hold (the best-measured engagement format), and the named villain is a dead company — the safest possible first outing for the receipts style before it is used on the living.
In parallel, start the ONSPD fetch (~200MB, one file, verified endpoint) now: it is the sole blocker on concept 1, which is the highest-ceiling build on the slate and also upgrades concepts 2 and 10 with postcode entry.

CONSIDERED AND REJECTED

- Water companies paid by the state while spilling: tested (join 12) and the join says nothing — the sums are utility bills; building the insinuation is the 5G-overlay error with a ledger.
- NHS agency-staff national series: "Agency" matches £12.8bn of Executive Agency block funding; partial trust coverage kills the series. Survives only as a methods footnote.
- Austerity in council budgets (Rushmoor): n=1 district, no CPI deflator held; not publishable as "austerity in the data".
- Energy-crisis council spending: coverage-confounded (suppliers' big payers exit the corpus mid-series); Bristol-only vignette too thin to lead.
- Council spending league table: 12 publishing councils cannot stand in for 300+ (incomparable-geography failure mode). The Bristol card in concept 1 makes the coverage gap the story instead.
- BT under 116 names as a standalone: catalogue hygiene, not Britain — precisely the inside-baseball the brief retires. It survives as a provenance-band caveat, not content.
- Uttlesford temporary accommodation 10x: real and verified, but two small district ledgers honestly framed is micro; hold until the MHCLG homelessness fetch lets it sit beside national TA tables.
- Prescribing vs deprivation (EPD): endpoint 403-blocked from our vantage and a 200-500MB slice; defer until a home-vantage fetch is proven.
- Companies House supplier-geography match: the biggest eventual unlock, but fuzzy-matching 11.8M free-text names is a project with its own accuracy audit, not a post; no claim before the match rate is measured.
- Council tax regressivity: VOA banding data absent from the index entirely; a London+Scotland partial sample would be dunked on geography.
- Record-level EPC: registration-gated non-OGL licence conflicts with the executable-provenance rule.
- Bar-chart-race video: 10x production cost, moratorium-grade format fatigue, and no finding on the slate needs a reveal arc a static pair can't deliver.
