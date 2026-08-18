"""Per-resident comparisons within class, the real-terms arc, and checks.

Tier handling, stated once and applied everywhere: English local government
classes do different jobs. Every comparison here is WITHIN one MHCLG class
(SD shire district, SC shire county, UA unitary, MD metropolitan district,
LB London borough), or an England-level sum across the five principal
classes with police and fire service lines excluded (their provision moved
between principal councils and standalone authorities over the period, so
including them would fake a change). Class O (police, fire, combined
authorities, parks, waste, GLA) is excluded from all league tables.

Measures: 'nce' (net current expenditure, the standard service-spend
measure, used for distributions and the real-terms arc) and 'gross' (total
expenditure) for the district dispersion claims - because net figures are
driven by charging policy (garden-bin fees, planning fees) as much as by
service size. The report states which measure each number uses.

Denominators: ONS mid-year population on the boundary set each RO year
actually had (mid-2013 / mid-2018 / mid-2024). Real terms: HMT GDP deflator
(June 2026 QNA edition), rebased so every figure is in 2024-25 prices.

Excluded rows, and why:
  City of London (LB, pop ~11k, runs its own police) and Isles of Scilly
  (UA, pop ~2.3k) - per-head figures are structurally meaningless; kept in
  England sums, dropped from class distributions and rankings.
  Cumberland 2024-25 - no return submitted; row is blank in the workbook.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
con = sqlite3.connect(HERE / "ro.sqlite")

PRINCIPAL = ["SD", "UA", "MD", "LB", "SC"]
FREAKS = {"E09000001", "E06000053"}  # City of London, Isles of Scilly

spend = pd.read_sql("select * from service_nce", con)
pop = pd.read_sql("select * from population", con)
defl = pd.read_sql("select * from deflator", con).set_index("year")["deflator"]
rs = pd.read_sql("select * from rs_summary", con)

REAL = {y: defl["2024-25"] / defl[y] for y in ("2013-14", "2018-19", "2024-25")}

# Synthetic combined service: waste collection + recycling. Districts split
# the same bin lorry between the two lines differently (Hart 2024-25 books
# 69k under collection and 1.1m under recycling), so neither line alone is
# comparable across councils; the sum is.
comb = (spend[spend.service.isin(["waste_collection", "recycling"])]
        .groupby(["year", "ecode", "ons_code", "name", "cls", "measure"],
                 dropna=False)["gbp_thousand"]
        .sum(min_count=1).reset_index())
comb["service"] = "refuse_and_recycling"
spend = pd.concat([spend, comb], ignore_index=True)

df = spend[spend.cls.isin(PRINCIPAL)].merge(
    pop[["year", "ons_code", "population"]], on=["year", "ons_code"], how="left")
df["gbp_per_head"] = df.gbp_thousand * 1000 / df.population
df["real_gbp_per_head"] = df.gbp_per_head * df.year.map(REAL)

df.to_csv(HERE / "ro_per_head.csv", index=False,
          columns=["year", "ecode", "ons_code", "name", "cls", "service",
                   "measure", "gbp_thousand", "population", "gbp_per_head",
                   "real_gbp_per_head"])

rank = df[~df.ons_code.isin(FREAKS) & df.gbp_thousand.notna()].copy()
nce = rank[rank.measure == "nce"]
gross = rank[rank.measure == "gross"]

# ---------------------------------------------------------------- distributions
q = (nce.groupby(["year", "cls", "service"])["gbp_per_head"]
     .agg(n="count",
          p10=lambda s: s.quantile(.10), p25=lambda s: s.quantile(.25),
          median="median",
          p75=lambda s: s.quantile(.75), p90=lambda s: s.quantile(.90))
     .reset_index())
q.to_csv(HERE / "distributions.csv", index=False, float_format="%.2f")

out: dict = {"vintages": ["2013-14", "2018-19", "2024-25"],
             "deflator_2024_25_prices": {y: round(REAL[y], 4) for y in REAL}}

# ------------------------------------------------- within-class extremes 24-25
def extremes(frame, year, cls, service, k=5):
    d = frame[(frame.year == year) & (frame.cls == cls) &
              (frame.service == service)].sort_values("gbp_per_head")
    cols = ["name", "ons_code", "gbp_thousand", "population", "gbp_per_head"]
    return {"n": len(d),
            "median_per_head": round(d.gbp_per_head.median(), 2),
            "p10": round(d.gbp_per_head.quantile(.10), 2),
            "p90": round(d.gbp_per_head.quantile(.90), 2),
            "bottom": d.head(k)[cols].round(2).to_dict("records"),
            "top": d.tail(k)[cols].round(2).to_dict("records")}

CROSS_NCE = [("LB", "cultural"), ("LB", "libraries"), ("MD", "libraries"),
             ("MD", "cultural"), ("UA", "adult_social_care"),
             ("UA", "children_social_care"), ("LB", "children_social_care"),
             ("SC", "highways_transport"), ("LB", "housing_gfra"),
             ("SD", "housing_gfra")]
out["within_class_2024_25_nce"] = {
    f"{c}:{s}": extremes(nce, "2024-25", c, s) for c, s in CROSS_NCE}
CROSS_GROSS = [("SD", "refuse_and_recycling"), ("SD", "planning_development"),
               ("LB", "libraries"), ("MD", "libraries")]
out["within_class_2024_25_gross"] = {
    f"{c}:{s}": extremes(gross, "2024-25", c, s) for c, s in CROSS_GROSS}

# --------------------------------------- same-county districts (true neighbours)
def county_dispersion(frame, services):
    sd = frame[(frame.year == "2024-25") & (frame.cls == "SD")].copy()
    sc = frame[(frame.year == "2024-25") & (frame.cls == "SC")].drop_duplicates("ecode")
    sc_names = sc.set_index(sc.ecode.str[1:3])["name"].to_dict()
    sd["county"] = sd.ecode.str[1:3].map(sc_names)
    rows = []
    for svc in services:
        d = sd[sd.service == svc]
        for county, g in d.groupby("county"):
            g = g.dropna(subset=["gbp_per_head"])
            if len(g) < 3:
                continue
            lo, hi = g.loc[g.gbp_per_head.idxmin()], g.loc[g.gbp_per_head.idxmax()]
            rows.append({"service": svc, "county": county, "districts": len(g),
                         "min_name": lo["name"],
                         "min_per_head": round(lo.gbp_per_head, 2),
                         "max_name": hi["name"],
                         "max_per_head": round(hi.gbp_per_head, 2),
                         "ratio": round(hi.gbp_per_head / lo.gbp_per_head, 2)
                         if lo.gbp_per_head > 0 else None})
    return pd.DataFrame(rows)

cty_gross = county_dispersion(gross, ["refuse_and_recycling",
                                      "planning_development", "cultural",
                                      "development_control"])
cty_gross.to_csv(HERE / "county_dispersion_gross.csv", index=False)
cty_nce = county_dispersion(nce, ["refuse_and_recycling", "housing_gfra"])
cty_nce.to_csv(HERE / "county_dispersion_nce.csv", index=False)
out["same_county_districts_2024_25_gross"] = {
    svc: cty_gross[cty_gross.service == svc]
    .sort_values("ratio", ascending=False).head(8).to_dict("records")
    for svc in cty_gross.service.unique()}
out["same_county_districts_2024_25_nce"] = {
    svc: cty_nce[cty_nce.service == svc]
    .sort_values("ratio", ascending=False).head(8).to_dict("records")
    for svc in cty_nce.service.unique()}

# ------------------------------------------------------------- the austerity arc
ARC_SERVICES = ["education", "highways_transport", "children_social_care",
                "adult_social_care", "public_health", "housing_gfra",
                "cultural", "environmental_regulatory", "planning_development",
                "central", "libraries", "refuse_and_recycling",
                "waste_disposal", "total_service_expenditure"]

eng_pop = {}
for y in ("2013-14", "2018-19"):
    eng_pop[y] = float(pop[(pop.year == y) & (pop.ons_code == "E92000001")]
                       .population.iloc[0])
p24 = pop[(pop.year == "2024-25") & pop.ons_code.str.match(r"^E(06|08|09|10)")]
eng_pop["2024-25"] = float(p24.population.sum())

d_nce = df[df.measure == "nce"]
arc_rows = []
for svc in ARC_SERVICES:
    row = {"service": svc}
    for y in ("2013-14", "2018-19", "2024-25"):
        d = d_nce[(d_nce.year == y) & (d_nce.service == svc)
                  & d_nce.gbp_thousand.notna()]
        cash = d.gbp_thousand.sum() * 1000
        row[f"real_per_head_{y}"] = round(cash * REAL[y] / eng_pop[y], 2)
    row["real_per_head_change_pct_2013_2024"] = round(
        100 * (row["real_per_head_2024-25"] / row["real_per_head_2013-14"] - 1), 1) \
        if row["real_per_head_2013-14"] else None
    arc_rows.append(row)
pd.DataFrame(arc_rows).to_csv(HERE / "england_real_arc.csv", index=False)
out["england_real_arc"] = arc_rows
out["england_population_used"] = {k: int(v) for k, v in eng_pop.items()}

# ---------------------------------------------------------------- IMD vs spend
imd_path = HERE.parent / "sewage" / "raw" / "IoD2019_File7_scores_ranks_deciles.csv"
imd = pd.read_csv(imd_path, usecols=[
    "Local Authority District code (2019)",
    "Index of Multiple Deprivation (IMD) Score",
    "Total population: mid 2015 (excluding prisoners)"])
imd.columns = ["lad19", "imd_score", "w"]
lad_imd = (imd.assign(x=imd.imd_score * imd.w).groupby("lad19")
           .agg(imd=("x", "sum"), w=("w", "sum")))
lad_imd = (lad_imd.imd / lad_imd.w).rename("imd_score").reset_index()

imd_tests = []
for cls, svc in [("LB", "cultural"), ("LB", "libraries"), ("MD", "libraries"),
                 ("MD", "cultural"), ("LB", "children_social_care"),
                 ("MD", "children_social_care"), ("MD", "adult_social_care"),
                 ("SD", "refuse_and_recycling"), ("SD", "planning_development")]:
    d = nce[(nce.year == "2024-25") & (nce.cls == cls) &
            (nce.service == svc)].merge(lad_imd, left_on="ons_code",
                                        right_on="lad19")
    if len(d) < 10:
        continue
    rho = d[["gbp_per_head", "imd_score"]].corr(method="spearman").iloc[0, 1]
    imd_tests.append({"cls": cls, "service": svc, "n": len(d),
                      "spearman_rho_per_head_vs_imd": round(rho, 3)})
out["imd_2019_correlations_2024_25"] = imd_tests

# ------------------------------------------------------- reserves + council tax
rsp = rs[rs.cls.isin(PRINCIPAL)].merge(
    pop[["year", "ons_code", "population"]], on=["year", "ons_code"], how="left")
rsp["reserves_total"] = (rsp.reserves_other_earmarked.fillna(0)
                         + rsp.reserves_unallocated.fillna(0))
res_rows = []
for y in ("2013-14", "2018-19", "2024-25"):
    d = rsp[(rsp.year == y) & rsp.net_revenue_expenditure.notna()]
    res_rows.append({
        "year": y, "n": len(d),
        "reserves_real_bn": round(d.reserves_total.sum() * REAL[y] / 1e6, 2),
        "nre_real_bn": round(d.net_revenue_expenditure.sum() * REAL[y] / 1e6, 2),
        "council_tax_requirement_real_bn": round(
            d.council_tax_requirement.sum() * REAL[y] / 1e6, 2),
        "ctr_share_of_nre_pct": round(100 * d.council_tax_requirement.sum()
                                      / d.net_revenue_expenditure.sum(), 1),
        "reserves_pct_of_nre": round(100 * d.reserves_total.sum()
                                     / d.net_revenue_expenditure.sum(), 1)})
out["reserves_and_council_tax"] = res_rows

# ------------------------------------------------ stable-authority library arc
lib = d_nce[d_nce.service == "libraries"].pivot_table(
    index=["ons_code", "name", "cls"], columns="year",
    values="real_gbp_per_head").reset_index()
lib = lib.dropna(subset=["2013-14", "2024-25"])
lib = lib[lib.cls.isin(["UA", "MD", "LB", "SC"]) & ~lib.ons_code.isin(FREAKS)]
# guards: a 2013-14 base under 2 pounds/head means the line is not credible
# (service outsourced or misbooked); a non-positive 2024-25 value means
# booked income exceeded spend (Blackpool 2024-25: gross 2,402k, income
# 2,606k) - both excluded from the fell/grew census.
lib = lib[(lib["2013-14"] >= 2) & (lib["2024-25"] > 0)]
lib["change_pct"] = 100 * (lib["2024-25"] / lib["2013-14"] - 1)
lib = lib.sort_values("change_pct")
out["library_stable_authorities"] = {
    "n": len(lib),
    "median_change_pct": round(lib.change_pct.median(), 1),
    "fell_count": int((lib.change_pct < 0).sum()),
    "deepest": lib.head(8)[["name", "cls", "2013-14", "2024-25", "change_pct"]]
    .round(1).to_dict("records"),
    "grew": lib.tail(5)[["name", "cls", "2013-14", "2024-25", "change_pct"]]
    .round(1).to_dict("records")}

(HERE / "analysis_out.json").write_text(json.dumps(out, indent=2))
print("written analysis_out.json")
