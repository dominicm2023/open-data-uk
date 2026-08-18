"""Render the comparison strands — every strand in more than one form.

Six strands of council-to-council and place-to-place comparison, each drawn
two or three ways: a league for the ranking, a map pair (real boundaries and
the population-fair hex twin) for the geography, a slope for what changed
between vintages, a scatter where the claim is a relationship. The forms
follow the format research: Reddit's standing objections — land shouting over
people, truncated axes, missing sources — are answered in the drawing rather
than the comments.

Everything reads the chart-ready CSVs the strand builders wrote in
analysis/strands/. Their artefact flags are honoured mechanically: a row
marked excluded_from_rankings or carrying a note never enters a league
silently — it is either dropped or drawn with its annotation.

These are Joined Up material (teal, signed), drafts for the workshop.

Usage:
    python scripts/strands_page.py          # write strands.html
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import charts  # noqa: E402

ROOT = Path(__file__).parent.parent
STRANDS = ROOT / "analysis" / "strands"
OUT = ROOT / "strands.html"
SITE = "open-data.org.uk"
MEASURED = "18 August 2026"
BYLINE = "Joined Up"


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(open(path, encoding="utf-8")))


def num(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) or default)
    except ValueError:
        return default


def panel(title: str, body: str, height: float, query: str) -> str:
    band, band_h = charts._provenance(int(height), query,
                                      f"{SITE} · measured {MEASURED}",
                                      byline=BYLINE)
    svg = charts._with_fallbacks(charts._frame(
        body + band, int(height) + band_h, title, query))
    return (f'<article class="finding joined-up"><h2>{charts.esc(title)}</h2>'
            f"<figure>{svg}</figure></article>")


# --- strand renderers ----------------------------------------------------

def libraries() -> list[str]:
    out = []
    league = rows(STRANDS / "libraries" / "league_2024-25_LB.csv")
    clean = [r for r in league if not (r.get("note") or "").strip()]
    ends = clean[:6] + clean[-6:]
    body, h = charts.hbar(
        [(r["name"], num(r, "net_gbp_per_head")) for r in ends],
        "£ per resident on libraries, 2024-25, London boroughs only — the top "
        "and bottom six of one class in one city. Kensington & Chelsea to "
        "Barking & Dagenham is 13x, and it survives the charging check on "
        "gross spend. Same duty, same city, thirteen times the library.")
    out.append(panel("The library lottery, inside one city", body, h,
                     "analysis/strands/libraries/league_2024-25_LB.csv — nce per "
                     "head, RO 2024-25, artefact-flagged rows excluded"))

    values = {r["ons_code"]: num(r, "value")
              for r in rows(STRANDS / "libraries" / "map_2024-25.csv")
              if not (r.get("note") or "").strip()}
    for form, name in ((charts.choropleth, "on real boundaries"),
                       (charts.hexmap, "one equal hex per council")):
        body, h = form(
            values,
            f"Net library spend per resident, 2024-25, {name}. Grey councils "
            f"are a different tier (districts do not run libraries) or filed "
            f"no return. "
            + ("Equal hexes so London is visible: the population-fair view."
               if form is charts.hexmap else
               "True geography: rural acres dominate, which is why the hex "
               "twin ships alongside."),
            "£")
        if body:
            out.append(panel(f"Libraries per head, {name}", body, h,
                             "analysis/strands/libraries/map_2024-25.csv over "
                             "vendored ONS boundaries (OGL)"))

    arc = rows(STRANDS / "libraries" / "arc_class_real.csv")
    by_cls: dict[str, dict[str, float]] = {}
    for r in arc:
        by_cls.setdefault(r["class_label"], {})[r["year"]] = num(r, "real_gbp_per_head")
    pairs = [(cls, v.get("2013-14", 0), v.get("2024-25", 0))
             for cls, v in by_cls.items() if v.get("2013-14")]
    body, h = charts.slope(
        pairs, "2013-14", "2024-25",
        "Real library spend per resident by council class, 2024-25 prices. "
        "Every class fell; the England figure is -41% and 132 of 139 stable "
        "authorities cut. This is what a discretionary service looks like "
        "after statutory demand has eaten the budget.", unit="")
    out.append(panel("Every class of council cut libraries", body, h,
                     "analysis/strands/libraries/arc_class_real.csv — real "
                     "2024-25 prices via HMT deflator"))
    return out


def cuts_arc() -> list[str]:
    out = []
    arc = rows(STRANDS / "cuts_arc" / "arc_dumbbell.csv")
    pairs = [(r["service_label"], num(r, "real_per_head_2013_14"),
              num(r, "real_per_head_2024_25"))
             for r in arc if not (r.get("caveat") or "").strip()]
    body, h = charts.slope(
        pairs, "2013-14", "2024-25",
        "England, real £ per resident by service. The lines that cross are "
        "the story: children's social care up 50% and adult social care up "
        "16% while libraries, culture and highways fell by around 40%. "
        "Austerity did not shrink the state evenly — it traded civic life "
        "for statutory care. Education is excluded here: academisation moved "
        "schools out of council accounts, and drawing it would be misread.",
        highlight={"Libraries", "Children's social care"})
    out.append(panel("What austerity actually cut", body, h,
                     "analysis/strands/cuts_arc/arc_dumbbell.csv — England "
                     "aggregate, real 2024-25 prices, education excluded "
                     "(academisation caveat in findings.json)"))

    care = rows(STRANDS / "cuts_arc" / "care_share.csv")
    latest = {r["cls_label"]: r for r in care if r["year"] == "2024-25"}
    first = {r["cls_label"]: r for r in care if r["year"] == "2013-14"}
    pairs = [(cls, num(first[cls], "care_share_pct"),
              num(latest[cls], "care_share_pct"))
             for cls in latest if cls in first
             and num(latest[cls], "care_share_pct") > 5]
    body, h = charts.slope(
        pairs, "2013-14", "2024-25",
        "Share of service spending going to adult and children's social care, "
        "by class. Upper-tier councils now put most of their money through "
        "care — the residual is everything else a council is: parks, "
        "libraries, roads, planning. Districts are excluded (they do not run "
        "care).", unit="%")
    out.append(panel("Care eats the budget", body, h,
                     "analysis/strands/cuts_arc/care_share.csv — ASC+CSC share "
                     "of total service expenditure per class"))
    return out


def care_deprivation() -> list[str]:
    out = []
    sc = rows(STRANDS / "care_deprivation" / "scatter_care_vs_deprivation.csv")
    rho = {(r["cls"], r["service"]): num(r, "spearman_rho")
           for r in rows(STRANDS / "care_deprivation" / "spearman_by_class_service.csv")}
    ua = [r for r in sc if r["cls"] == "UA"]
    fills = {"LB": "var(--cat-1)", "MD": "var(--cat-5)", "UA": "var(--cat-3)"}

    pts = [{"x": num(r, "imd_avg_score"), "y": num(r, "csc_net_per_head_real2425"),
            "fill": fills.get(r["cls"], "var(--cat-2)"),
            "label": r["authority"] if r["authority"] in
            ("Blackpool", "North Yorkshire", "Kensington & Chelsea") else None}
           for r in sc if r["cls"] in ("LB", "MD", "UA")]
    body, h = charts.scatter(
        pts, "IMD 2019 average score (higher = more deprived)",
        "children's social care £ per resident, real 2024-25",
        "Every upper-tier council. The slope is need arriving as a bill: "
        "Blackpool spends £599 per resident on children's social care, North "
        "Yorkshire £136. Spearman 0.57 in London, 0.44 in the mets. This is "
        "not generosity — it is what deprivation costs, itemised.",
        rho=rho.get(("UA", "children_social_care")))
    out.append(panel("Need is not evenly spread", body, h,
                     "analysis/strands/care_deprivation/scatter_care_vs_"
                     "deprivation.csv — population-weighted IMD per authority"))

    pts = [{"x": num(r, "imd_avg_score"), "y": num(r, "lib_net_per_head_real2425"),
            "fill": fills.get(r["cls"], "var(--cat-2)")}
           for r in sc if r["cls"] in ("LB", "MD", "UA")
           and r.get("lib_net_negative") != "True"]
    body, h = charts.scatter(
        pts, "IMD 2019 average score (higher = more deprived)",
        "libraries £ per resident, real 2024-25",
        "The same councils, libraries instead of care: flat. Rich and poor "
        "areas cut libraries alike — so 'poor areas lost their libraries' is "
        "not supported, and we say so. The steep chart above and this flat "
        "one are the same method; only the service differs.",
        rho=rho.get(("UA", "libraries")))
    out.append(panel("The null twin: libraries don't track deprivation",
                     body, h,
                     "same file, same method, libraries — the null ships "
                     "beside the gradient on purpose"))
    return out


def counciltax() -> list[str]:
    out = []
    cls_arc = rows(STRANDS / "counciltax" / "ct_share_by_class.csv")
    by_cls: dict[str, dict[str, float]] = {}
    for r in cls_arc:
        by_cls.setdefault(r["scope"], {})[r["year"]] = num(r, "ct_share_of_nre_pct")
    labels = {"LB": "London boroughs", "MD": "Met districts", "SC": "Shire counties",
              "SD": "Shire districts", "UA": "Unitaries"}
    pairs = [(labels.get(cls, cls), v.get("2013-14", 0), v.get("2024-25", 0))
             for cls, v in by_cls.items()
             if v.get("2013-14") and cls in labels]
    body, h = charts.slope(
        pairs, "2013-14", "2024-25",
        "Council tax as a share of net revenue expenditure. England moved "
        "from 47% to 63% in eleven years: as grant fell, the burden shifted "
        "from national taxation to the most regressive major tax in the "
        "system — the one that ignores what your house is actually worth "
        "and what you actually earn.", unit="%")
    out.append(panel("The burden moved to your council tax bill", body, h,
                     "analysis/strands/counciltax/ct_share_by_class.csv — "
                     "council tax requirement over NRE, per class"))

    league = rows(STRANDS / "counciltax" / "grant_settlement_league.csv")
    lb = [r for r in league if r["cls"] == "LB"
          and r.get("league_excluded") != "True"
          and not (r.get("handcheck") or "").strip()]
    lb.sort(key=lambda r: num(r, "change_pct"))
    body, h = charts.hbar(
        [(r["name"], abs(num(r, "change_real_ph"))) for r in lb[:10]],
        "Real government settlement lost per resident since 2013-14, London "
        "boroughs, the ten biggest falls. Lewisham lost £689 per resident "
        "per year — 69% of its settlement — and its council tax share rose "
        "to match. Within one class, so the duties are comparable.")
    out.append(panel("Who lost the grant", body, h,
                     "analysis/strands/counciltax/grant_settlement_league.csv "
                     "— RSG + rates retention, real per head, hand-checked "
                     "rows only"))

    dep = {r["ons_code"]: num(r, "ct_share_pct")
           for r in rows(STRANDS / "counciltax" / "ct_dependence_2024_25.csv")
           if r.get("excluded_from_rankings") != "True"
           and r.get("share_artefact") != "True"}
    body, h = charts.hexmap(
        dep, "Council tax share of net spending, 2024-25, one hex per "
             "council. The darker the hex, the more of the council is paid "
             "for by the local bill rather than national grant. Grey: no "
             "return or excluded as an accounting artefact.", "%")
    if body:
        out.append(panel("Where the bill carries the council", body, h,
                         "analysis/strands/counciltax/ct_dependence_2024_25.csv "
                         "over the vendored hex layout"))
    return out


def seaside() -> list[str]:
    out = []
    league = rows(STRANDS / "seaside" / "seaside_league.csv")
    body, h = charts.hbar(
        [(r["town"], num(r, "hours_2025")) for r in league[:12]],
        "Hours of monitored sewage discharge within 10km of the town centre, "
        "2025, English seaside towns. Plymouth: 33,275 hours across 163 "
        "overflows. The method is crude and printed here: a 10km radius from "
        "the town centroid, which puts Birkenhead's works in Sefton's count "
        "across the estuary. England only — Wales and Scotland report under "
        "different regimes.")
    out.append(panel("The seaside sewage league", body, h,
                     "analysis/strands/seaside/seaside_league.csv — EA EDM "
                     "2025 annual return, 10km centroid radius, method stated"))

    pts = [{"lon": num(r, "lon"), "lat": num(r, "lat"),
            "value": num(r, "spills_2025"), "fill": "var(--cat-4)"}
           for r in rows(STRANDS / "seaside" / "map_points.csv")
           if num(r, "spills_2025") >= 100]
    body, h = charts.uk_map(
        pts, "Every English storm overflow that spilled 100 or more times in "
             "2025, at its true position, circle area proportional to spill "
             "count. The coast is where the pattern lives — and where the "
             "swimmers are.",
        [("100+ spills in 2025", "var(--cat-4)")])
    out.append(panel("Where the spilling is", body, h,
                     "analysis/strands/seaside/map_points.csv — EDM 2025, "
                     "sites over 100 spills drawn"))

    comp = rows(STRANDS / "seaside" / "company_totals.csv")
    comp.sort(key=lambda r: -num(r, "hours_seaside_league"))
    body, h = charts.hbar(
        [(r["company"], num(r, "hours_seaside_league")) for r in comp[:9]],
        "Seaside spill-hours by water company, 2025. South West Water alone "
        "is 42% of all coastal discharge hours near seaside towns — 1.9x its "
        "nearest rival — while holding the coastline people actually holiday "
        "on. One company, most of the problem.")
    out.append(panel("One company, most of the coast", body, h,
                     "analysis/strands/seaside/company_totals.csv — seaside-"
                     "league scope column"))
    return out


def gradient_null() -> list[str]:
    out = []
    series = [r for r in rows(STRANDS / "gradient_null" / "decile_series.csv")
              if r["series"] == "all_england"]
    series.sort(key=lambda r: int(r["imd_decile_2019"]))
    body, h = charts.timeline(
        [(r["decile_label"].split()[0], num(r, "spills_per_lsoa"))
         for r in series],
        "Spills per neighbourhood by deprivation decile, England 2025 — "
        "decile 1 is most deprived, 10 least. The shape is an inverted U, "
        "not a slope: the middle of England gets the most sewage, and the "
        "poorest tenth sits near the richest. We went looking for the "
        "gradient everyone assumes. It is not there, and this chart is us "
        "saying so with the working attached.",
        highlight={"1": "var(--cat-3)", "10": "var(--cat-3)"})
    out.append(panel("The gradient that isn't there", body, h,
                     "analysis/strands/gradient_null/decile_series.csv — EDM "
                     "2025 x IMD 2019, spills per LSOA in each decile"))

    amb = rows(STRANDS / "gradient_null" / "ambiguity_by_decile.csv")
    body, h = charts.hbar(
        [(r["decile_label"], 100 * num(r, "share_multi_decile")) for r in amb],
        "Share of monitored overflows with more than one candidate "
        "deprivation decile within 100m, by decile. Sewers discharge to "
        "rivers; rivers are where the statistical boundaries were drawn. "
        "Anyone assigning an overflow to exactly one neighbourhood is "
        "flipping a coin for roughly half their points — which is why our "
        "decile chart above uses radii, not point-in-polygon membership.")
    out.append(panel("Rivers are the boundaries — per decile", body, h,
                     "analysis/strands/gradient_null/ambiguity_by_decile.csv"))
    return out


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Strands — UK Open Data Index</title>
<link rel="stylesheet" href="/site.css">
</head><body><div class="wrap">
<h1>Comparison strands</h1>
<p>Six strands of comparison about Britain, each drawn more than one way —
league, map pair, slope, scatter — so the form can be chosen per platform.
All Joined Up livery, all signed, all carrying the query. Drafts for the
workshop; nothing here is published.</p>
<p class="note">Map pairs exist because both complaints are right: a
boundary map lets acres shout over people, a hex map distorts geography.
Ship the pair, let the reader triangulate.</p>
{panels}
</div></body></html>
"""


def main() -> int:
    sections = []
    for name, fn in [("libraries", libraries), ("cuts_arc", cuts_arc),
                     ("care_deprivation", care_deprivation),
                     ("counciltax", counciltax), ("seaside", seaside),
                     ("gradient_null", gradient_null)]:
        try:
            panels = fn()
            sections.extend(panels)
            print(f"   {name}: {len(panels)} charts")
        except Exception as exc:  # noqa: BLE001 — one strand must not sink the page
            print(f"   {name} FAILED: {type(exc).__name__}: {exc}")
    OUT.write_text(PAGE.replace("{panels}", "".join(sections)),
                   encoding="utf-8")
    print(f"\n{len(sections)} charts — wrote {OUT.name} "
          f"({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
