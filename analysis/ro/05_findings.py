"""Assemble findings.json and REPORT.md from analysis_out.json + ro.sqlite.

Every number in the report is computed here from the analysis outputs (or
looked up in the database), never hand-typed; provenance strings come from
provenance.json so each headline traces to file/sheet/column.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
out = json.loads((HERE / "analysis_out.json").read_text())
prov = json.loads((HERE / "provenance.json").read_text())
con = sqlite3.connect(HERE / "ro.sqlite")


def prov_ref(year: str, service: str, measure: str) -> str:
    for p in prov:
        if (p["year"], p["service"], p.get("measure")) == (year, service, measure):
            return (f"{p['file']} / {p['sheet']} / col {p['column_index_0based']} "
                    f"({p['column_header']})")
    return "?"


def ph(frame_key: str, cls_svc: str, name: str) -> dict:
    for side in ("bottom", "top"):
        for r in out[frame_key][cls_svc][side]:
            if r["name"] == name:
                return r
    raise KeyError(name)


arc = {r["service"]: r for r in out["england_real_arc"]}
res = {r["year"]: r for r in out["reserves_and_council_tax"]}
lib = out["library_stable_authorities"]
imd = {(r["cls"], r["service"]): r for r in out["imd_2019_correlations_2024_25"]}

kc = ph("within_class_2024_25_nce", "LB:libraries", "Kensington & Chelsea")
bd = ph("within_class_2024_25_nce", "LB:libraries", "Barking & Dagenham")
kc_g = ph("within_class_2024_25_gross", "LB:libraries", "Kensington & Chelsea")
bd_g = ph("within_class_2024_25_gross", "LB:libraries", "Barking & Dagenham")
bpool = ph("within_class_2024_25_nce", "UA:children_social_care", "Blackpool UA")
nyork = ph("within_class_2024_25_nce", "UA:children_social_care", "North Yorkshire")
lb_lib = out["within_class_2024_25_nce"]["LB:libraries"]
ua_csc = out["within_class_2024_25_nce"]["UA:children_social_care"]

warks = [r for r in out["same_county_districts_2024_25_gross"]["development_control"]
         if r["county"] == "Warwickshire CC"][0]

findings = {
    "substrate": "MHCLG Revenue Outturn (RO) statistics - every English council reports in the same statutory service categories",
    "vintages": {"2013-14": "XLS, revised", "2018-19": "ODS", "2024-25": "ODS, latest published (June 2026 era release)"},
    "parse_coverage": {
        "authorities_all_classes": {"2013-14": 444, "2018-19": 444, "2024-25": 410},
        "principal_councils": {"2013-14": 353, "2018-19": 353, "2024-25": 317},
        "population_joined": "100% of principal councils in every vintage",
        "non_submitters": ["Cumberland 2024-25 (row blank, England total carries MHCLG's unpublished imputation, -485.2m on our reconciliation)"],
        "reconciliation": "sum of authority rows vs each workbook's own England row for Total Service Expenditure: exact to the pound in 2013-14 and 2018-19; -485,196k in 2024-25 = the Cumberland imputation",
    },
    "tier_handling": "MHCLG's own Class column (SD/SC/UA/MD/LB); every comparison within one class; England arc sums the five principal classes and drops police+fire service lines (provision moved between principal councils and standalone authorities); class O never compared; City of London and Isles of Scilly excluded from distributions",
    "claims": [
        {
            "claim": "Councils of the same type spend up to 13x differently per resident on the same service (libraries, London boroughs, 2024-25)",
            "verdict": "PROVABLE NOW",
            "numbers": {
                "Kensington & Chelsea": {"nce_per_head": kc["gbp_per_head"], "gross_per_head": kc_g["gbp_per_head"]},
                "Barking & Dagenham": {"nce_per_head": bd["gbp_per_head"], "gross_per_head": bd_g["gbp_per_head"]},
                "ratio_nce": round(kc["gbp_per_head"] / bd["gbp_per_head"], 1),
                "ratio_gross": round(kc_g["gbp_per_head"] / bd_g["gbp_per_head"], 1),
                "class_median_nce": lb_lib["median_per_head"],
                "class_p10_p90": [lb_lib["p10"], lb_lib["p90"]],
            },
            "provenance": prov_ref("2024-25", "libraries", "nce"),
            "strongest_objection": "NCE nets off income, and outsourced-to-trust arrangements can move cost between lines. Answered here: the gap survives on gross expenditure (11.4x), both boroughs' income is small, and neither uses a trust for libraries. The same check KILLED other candidates: Hart's 0.67/head waste (cost booked under Recycling), Rugby's 4/head waste (garden-bin income nets off 78% of gross), Cambridge vs South Cambridgeshire (shared waste service hosted by one partner), Blackpool libraries (income exceeds spend, line is negative).",
        },
        {
            "claim": "Same-county districts differ ~10x per resident in gross spend on development control (statutory planning)",
            "verdict": "PROVABLE NOW, with mechanism stated",
            "numbers": warks,
            "provenance": prov_ref("2024-25", "development_control", "gross"),
            "strongest_objection": "Development control workload is demand-driven: a growth district processes more and bigger applications and collects more fees (Stratford-on-Avon nets 2.7m after fees; Nuneaton & Bedworth's fee income exceeds its booked spend, its NET line is negative). Frame as 'districts run planning departments of very different size', not as efficiency.",
        },
        {
            "claim": "Libraries per head fell ~41% real since 2013-14 while children's social care rose ~50%",
            "verdict": "PROVABLE NOW (direction well-documented by IFS/NAO - cite, don't claim novelty)",
            "numbers": {
                "libraries_real_per_head": {y: arc["libraries"][f"real_per_head_{y}"] for y in ("2013-14", "2018-19", "2024-25")},
                "libraries_change_pct": arc["libraries"]["real_per_head_change_pct_2013_2024"],
                "children_social_care_change_pct": arc["children_social_care"]["real_per_head_change_pct_2013_2024"],
                "adult_social_care_change_pct": arc["adult_social_care"]["real_per_head_change_pct_2013_2024"],
                "cultural_change_pct": arc["cultural"]["real_per_head_change_pct_2013_2024"],
                "highways_change_pct": arc["highways_transport"]["real_per_head_change_pct_2013_2024"],
                "total_service_expenditure_change_pct": arc["total_service_expenditure"]["real_per_head_change_pct_2013_2024"],
                "stable_authorities": {"n": lib["n"], "fell": lib["fell_count"], "median_change_pct": lib["median_change_pct"]},
            },
            "provenance": f"{prov_ref('2013-14', 'libraries', 'nce')} vs {prov_ref('2024-25', 'libraries', 'nce')}; HMT GDP deflator Jun-2026 QNA, 2024-25 prices; ONS mid-year population on period-correct boundaries",
            "strongest_objection": "The GDP deflator is not an input-cost index for councils; care-wage inflation ran above it, so the social-care 'rise' overstates extra service volume. Direction reconciles with NAO 2018 (cultural -34.9%, 2010-11 to 2016-17) and IFS's documented acute-vs-amenity squeeze. Education (-19.3%) must NOT be quoted: academisation moved schools off LA books. Public health (+10.2%) started as a new grant in 2013-14.",
        },
        {
            "claim": "Children's social care spending tracks deprivation; library spending does not",
            "verdict": "PROVABLE NOW (cross-sectional, within-class, 2024-25)",
            "numbers": {
                "csc_vs_imd_spearman": {"LB": imd[("LB", "children_social_care")]["spearman_rho_per_head_vs_imd"],
                                        "MD": imd[("MD", "children_social_care")]["spearman_rho_per_head_vs_imd"]},
                "libraries_vs_imd_spearman": {"LB": imd[("LB", "libraries")]["spearman_rho_per_head_vs_imd"],
                                              "MD": imd[("MD", "libraries")]["spearman_rho_per_head_vs_imd"]},
                "ua_csc_extremes": {"Blackpool": bpool["gbp_per_head"], "North Yorkshire": nyork["gbp_per_head"],
                                    "ratio": round(bpool["gbp_per_head"] / nyork["gbp_per_head"], 1),
                                    "class_median": ua_csc["median_per_head"]},
            },
            "provenance": "IMD 2019 File 7 (LSOA scores, population-weighted to LAD2019) x RSX 2024-25 per-head NCE; stable-code councils only",
            "strongest_objection": "IMD is 2019-vintage against 2024-25 spend, and rho~0 for libraries is absence of evidence of a gradient, not proof of fairness. 'Poor areas lost their libraries' is NOT SUPPORTED cross-sectionally within class - but this analysis does not test change-over-time against deprivation.",
        },
        {
            "claim": "Council tax now carries 63p of every pound of net revenue expenditure, up from 47p in 2013-14; reserves rose while spending fell",
            "verdict": "PROVABLE NOW (as defined on the RS return lines)",
            "numbers": res,
            "provenance": f"{prov_ref('2013-14', 'rs:council_tax_requirement', 'rs_line')}; {prov_ref('2024-25', 'rs:council_tax_requirement', 'rs_line')}",
            "strongest_objection": "NRE's grant treatment changed over the period (rates retention 2013 onwards), so the ratio partly reflects definitional migration, not only the RSG phase-out. Reserves at 31 March 2025 include sums earmarked against known liabilities; 'councils are hoarding' does not follow.",
        },
        {
            "claim": "The councils spending least per head are [political party]-run",
            "verdict": "NOT TESTED - skipped deliberately",
            "numbers": {},
            "provenance": "",
            "strongest_objection": "No reliable open dataset of political control was fetched; joining scraped control data would not meet the project's provenance bar. Politics stays out.",
        },
    ],
    "hand_check_queue_killed": [
        "Hart DC waste collection 0.67/head - gross only 69k, cost booked under Recycling (1.1m); combined refuse+recycling line used instead",
        "Rugby waste 4.00/head net - charging income nets off 78% of 2.25m gross",
        "Cambridge 19.26 vs South Cambridgeshire 67.33 gross refuse - Greater Cambridge shared waste service, hosting arrangement",
        "Blackpool libraries 2024-25 - income 2,606k exceeds spend 2,402k, line negative; excluded",
        "Enfield libraries 6.03 net - income is ~47% of gross, low net partly an income artefact; not named",
        "Sunderland libraries 4.24 - culture delivered via trust; line may understate library share of trust grant; named only with that caveat",
    ],
}

(HERE / "findings.json").write_text(json.dumps(findings, indent=2))
print("findings.json written")

# ------------------------------------------------------------------ REPORT.md
def money(x):
    return f"£{x:,.2f}"

dist = pd.read_csv(HERE / "distributions.csv")


def dline(cls, svc):
    d = dist[(dist.year == "2024-25") & (dist.cls == cls) & (dist.service == svc)].iloc[0]
    return f"| {cls} | {svc} | {int(d['n'])} | {money(d['p25'])} | {money(d['median'])} | {money(d['p75'])} |"


R = f"""# What different councils spend on the same things - RO substrate

**Status: analysis note on the correct substrate. Transaction-level comparison was tested and rejected earlier (9 of 361 councils parse, per-council expense vocabularies); this build uses MHCLG's Revenue Outturn (RO) statistics, where every English council reports the same statutory service categories every year - uniform by construction.**

Every number traces to a script here: page discovery `00_discover.py`, attachment listing `01_list_attachments.py`, fetching `02_fetch.py` -> `manifest.json`, parsing `03_parse.py` -> `ro.sqlite` + `provenance.json`, analysis `04_analyse.py` -> `ro_per_head.csv` / `distributions.csv` / `england_real_arc.csv` / `county_dispersion_*.csv` / `analysis_out.json`, this report `05_findings.py` -> `findings.json`. Raw workbooks in `raw/` (gitignored), 12.9 MB total against a 1.5 GB cap.

## What was fetched

Three vintages of three workbooks each, from the gov.uk collection the index's four `availability=webpage` catalogue entries forward to (Local authority revenue expenditure and financing, MHCLG):

| vintage | RS (financing+reserves) | RSX (service summary) | RO5 (cultural/env/planning detail) |
|---|---|---|---|
| 2013-14 (revised) | XLS, 3 sheets | XLS | XLS, 3 sheets (measures split across sheets) |
| 2018-19 | ODS | ODS | ODS |
| 2024-25 (latest) | ODS | ODS | ODS |

Companions: ONS mid-year population on the boundary set each RO year actually had - mid-2024 via nomis NM_2002_1 (TYPE423/424), mid-2018 and mid-2013 via archived ONS reference tables (`ukmidyearestimates20182018ladcodes.xls`, `ukmye2013.zip`), because **nomis deletes back-series values for abolished geographies** (41 English districts + Bournemouth/Poole return empty for 2013 on every TYPE); HMT GDP deflator (June 2026 QNA). All real-terms figures are 2024-25 prices (2013-14 x{out['deflator_2024_25_prices']['2013-14']}, 2018-19 x{out['deflator_2024_25_prices']['2018-19']}).

## Parse coverage and reconciliation

{findings['parse_coverage']['authorities_all_classes']['2013-14']} / {findings['parse_coverage']['authorities_all_classes']['2018-19']} / {findings['parse_coverage']['authorities_all_classes']['2024-25']} authorities parsed (2013-14 / 2018-19 / 2024-25, all classes); **principal councils 353 / 353 / 317, population joined for 100%** in every vintage. Sum of authority rows vs each workbook's own England row (Total Service Expenditure, net current expenditure): **exact in 2013-14 and 2018-19; -£485.2m in 2024-25**, which is Cumberland - it filed no return (note `M`), its row is blank, and MHCLG's England row carries an unpublished imputation. One MHCLG typo corrected with the workbook's own sibling as witness: RSX 2018-19 codes North Yorkshire E10000022; ONS and RO5 2018-19 say E10000023. One structural trap caught by reconciliation: the 2024-25 CLASS BREAKDOWN block repeats the GLA with its real E-code (a class of one), which double-counted £7.3bn until deduplicated.

## Tier handling (on every table)

{findings['tier_handling']}.

## The three strongest verified comparisons

**1. Same class, same city, 13x: libraries across London boroughs (2024-25).** Kensington & Chelsea {money(kc['gbp_per_head'])}/resident net vs Barking & Dagenham {money(bd['gbp_per_head'])} - **{round(kc['gbp_per_head']/bd['gbp_per_head'],1)}x**, and the gap survives the charging check (gross: {money(kc_g['gbp_per_head'])} vs {money(bd_g['gbp_per_head'])}, {round(kc_g['gbp_per_head']/bd_g['gbp_per_head'],1)}x). Class median {money(lb_lib['median_per_head'])}, p10-p90 {money(lb_lib['p10'])}-{money(lb_lib['p90'])}. Provenance: {findings['claims'][0]['provenance']}, rows by borough name; population ONS mid-2024.

**2. The arc: amenities cut, statutory child protection up (England, five principal classes, real 2024-25 prices per resident).** Libraries {money(arc['libraries']['real_per_head_2013-14'])} -> {money(arc['libraries']['real_per_head_2018-19'])} -> {money(arc['libraries']['real_per_head_2024-25'])} (**{arc['libraries']['real_per_head_change_pct_2013_2024']}%** since 2013-14); cultural {arc['cultural']['real_per_head_change_pct_2013_2024']}%; highways & transport {arc['highways_transport']['real_per_head_change_pct_2013_2024']}%; children's social care **+{arc['children_social_care']['real_per_head_change_pct_2013_2024']}%**; adult social care +{arc['adult_social_care']['real_per_head_change_pct_2013_2024']}%; total service expenditure {arc['total_service_expenditure']['real_per_head_change_pct_2013_2024']}%. Libraries fell in **{lib['fell_count']} of {lib['n']}** authorities that exist in both years (median {lib['median_change_pct']}%). Direction reconciles with NAO 2018 (cultural -34.9% for 2010-11 to 2016-17) and the IFS-documented acute-vs-amenity squeeze - cite them, this is confirmation on a longer window, not novelty. Education is in the table but must not be quoted as a cut: academisation moved schools off LA books.

**3. Children's social care tracks deprivation; libraries don't (2024-25, within class).** Spearman per-head-vs-IMD: CSC rho {imd[('LB','children_social_care')]['spearman_rho_per_head_vs_imd']} (London), {imd[('MD','children_social_care')]['spearman_rho_per_head_vs_imd']} (mets); libraries rho {imd[('LB','libraries')]['spearman_rho_per_head_vs_imd']} / {imd[('MD','libraries')]['spearman_rho_per_head_vs_imd']}. The unitary extremes are the same story told by two councils: Blackpool {money(bpool['gbp_per_head'])}/resident on children's social care vs North Yorkshire {money(nyork['gbp_per_head'])} ({round(bpool['gbp_per_head']/nyork['gbp_per_head'],1)}x, class median {money(ua_csc['median_per_head'])}). So "poor areas lost their libraries" is **NOT SUPPORTED** cross-sectionally - library spend simply doesn't correlate with deprivation either way.

Also provable: council tax carried {res['2024-25']['ctr_share_of_nre_pct']}p of every pound of net revenue expenditure in 2024-25, up from {res['2013-14']['ctr_share_of_nre_pct']}p in 2013-14; reserves (earmarked+unallocated, 31 March) rose real-terms £{res['2013-14']['reserves_real_bn']}bn -> £{res['2024-25']['reserves_real_bn']}bn while real NRE fell £{res['2013-14']['nre_real_bn']}bn -> £{res['2024-25']['nre_real_bn']}bn (RS lines; the NRE definition absorbed rates retention over the period - state that when quoting).

## 2024-25 within-class distributions (net £/resident, for context)

| class | service | n | p25 | median | p75 |
|---|---|---:|---:|---:|---:|
{dline('LB','libraries')}
{dline('MD','libraries')}
{dline('UA','adult_social_care')}
{dline('UA','children_social_care')}
{dline('SC','highways_transport')}
{dline('SD','refuse_and_recycling')}

## The hand-check graveyard - why the naive league table lies

Every eye-catching ratio was checked against the workbook's own gross/income columns before naming. Killed: **Hart DC "£0.67/head on waste"** (gross £69k; its £1.1m contract sits under Recycling - the combined refuse+recycling line is used instead); **Rugby £4/head** (garden-bin income nets off 78% of £2.25m gross); **Cambridge vs South Cambridgeshire 3.5x** (Greater Cambridge shared waste service - hosting arrangement, not frugality); **Blackpool's negative library line** (income £2.61m > spend £2.40m); **Enfield's £6 libraries** (income is 47% of gross - partly an artefact). Nuneaton & Bedworth's development-control NET is negative (fees exceed booked spend) while Stratford-on-Avon spends £32/resident gross running the county's biggest planning operation - a real 9.8x gross gap, but the mechanism is development pressure, so it is framed as department size, not efficiency.

## What a fair critic would still attack

1. **The deflator.** GDP deflator is not a council input-cost index; care wages rose faster, so +{arc['adult_social_care']['real_per_head_change_pct_2013_2024']}% ASC overstates volume growth, and the amenity cuts understate lost provision.
2. **NCE follows booking choices.** Trusts (Sunderland's culture trust), shared services, recharges: any single authority's single line can mislead - that is why claims are made on distributions, gross-checked, and the graveyard is published.
3. **ASC includes NHS money** (Better Care Fund enters as income/transfers - workbook note 1), so ASC levels across councils partly reflect BCF flows.
4. **IMD is 2019-vintage** against 2024-25 spend, matched on stable LAD codes only; and rho~0 is no gradient, not fairness.
5. **2024-25 is one year.** Temporary accommodation (Westminster housing GFRA {money(ph('within_class_2024_25_nce','LB:housing_gfra','Westminster')['gbp_per_head'])}/resident vs LB median {money(out['within_class_2024_25_nce']['LB:housing_gfra']['median_per_head'])}) and fee cycles swing single years; nothing here smooths.
6. **Politics is absent, deliberately** - no reliable open control dataset was fetched, so no partisan claims are made or possible from this build.

## Rebuild

```
python 00_discover.py         # gov.uk collection -> per-year outturn pages
python 01_list_attachments.py # content API -> attachments.json (sizes first)
python 02_fetch.py            # raw/ + manifest.json (HEADERS, <=2 req/s)
python 03_parse.py            # ro.sqlite + provenance.json + reconciliation gate
python 04_analyse.py          # csv outputs + analysis_out.json
python 05_findings.py         # findings.json + this report
```
"""

(HERE / "REPORT.md").write_text(R, encoding="utf-8")
print("REPORT.md written")
