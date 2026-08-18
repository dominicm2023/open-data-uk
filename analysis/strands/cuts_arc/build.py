"""STRAND: what austerity actually cut - chart-ready data.

Reads analysis/ro/ro.sqlite (built by analysis/ro/03_parse.py, methodology in
analysis/ro/04_analyse.py and REPORT.md) and writes four chart-ready CSVs into
this directory. Every number is recomputed here from the sqlite substrate; no
figure is copied from findings.json.

Methodology carried over from 04_analyse.py, restated:
- Classes: MHCLG's own Class column. SD shire district, SC shire county,
  UA unitary, MD met district, LB London borough. No cross-class comparison;
  class O (police, fire, combined, GLA...) never enters.
- Measure: nce (net current expenditure) throughout - the headline measure.
- Real terms: HMT GDP deflator (June 2026 QNA), everything in 2024-25 prices.
- Synthetic refuse_and_recycling = waste_collection + recycling (councils
  split the same bin lorry between the two lines differently).
- England arc denominators: ONS England population (E92000001) for 2013-14 and
  2018-19; sum of LAD populations for 2024-25 (matches 04_analyse.py).
- Cumberland filed no 2024-25 return: its spend rows are null. It is excluded
  from class aggregates in 2024-25 (numerator AND denominator population).
- City of London / Isles of Scilly stay in aggregates (negligible), are
  excluded from the per-authority distribution (structurally meaningless
  per-head).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RO = HERE.parent.parent / "ro"
con = sqlite3.connect(RO / "ro.sqlite")

PRINCIPAL = ["SD", "SC", "UA", "MD", "LB"]
FREAKS = {"E09000001", "E06000053"}  # City of London, Isles of Scilly
YEARS = ["2013-14", "2018-19", "2024-25"]
CLS_LABEL = {"LB": "London borough", "MD": "Met district", "UA": "Unitary",
             "SC": "Shire county", "SD": "Shire district"}
EDU_CAVEAT = ("academisation moved schools off LA books over this period - "
              "NOT a cut, do not quote as one")
PH_CAVEAT = "public health grant was new in 2013-14 - base year is a ramp-up"

spend = pd.read_sql("select * from service_nce", con)
pop = pd.read_sql("select * from population", con)
defl = pd.read_sql("select * from deflator", con).set_index("year")["deflator"]
REAL = {y: defl["2024-25"] / defl[y] for y in YEARS}

# synthetic combined waste line, same construction as 04_analyse.py
comb = (spend[spend.service.isin(["waste_collection", "recycling"])]
        .groupby(["year", "ecode", "ons_code", "name", "cls", "measure"],
                 dropna=False)["gbp_thousand"].sum(min_count=1).reset_index())
comb["service"] = "refuse_and_recycling"
spend = pd.concat([spend, comb], ignore_index=True)

nce = spend[(spend.measure == "nce") & spend.cls.isin(PRINCIPAL)].copy()

# ---------------------------------------------------------------- (a) dumbbell
ARC_SERVICES = ["libraries", "cultural", "highways_transport",
                "planning_development", "environmental_regulatory",
                "refuse_and_recycling", "waste_disposal", "housing_gfra",
                "central", "public_health", "adult_social_care",
                "children_social_care", "education",
                "total_service_expenditure"]
LABEL = {"libraries": "Libraries", "cultural": "Culture & heritage",
         "highways_transport": "Highways & transport",
         "planning_development": "Planning & development",
         "environmental_regulatory": "Environmental & regulatory",
         "refuse_and_recycling": "Refuse & recycling",
         "waste_disposal": "Waste disposal", "housing_gfra": "Housing (GFRA)",
         "central": "Central services", "public_health": "Public health",
         "adult_social_care": "Adult social care",
         "children_social_care": "Children's social care",
         "education": "Education", "total_service_expenditure":
         "Total service expenditure"}

eng_pop = {}
for y in ("2013-14", "2018-19"):
    eng_pop[y] = float(pop[(pop.year == y) & (pop.ons_code == "E92000001")]
                       .population.iloc[0])
p24 = pop[(pop.year == "2024-25") & pop.ons_code.str.match(r"^E(06|08|09|10)")]
eng_pop["2024-25"] = float(p24.population.sum())

rows = []
for svc in ARC_SERVICES:
    row = {"service": svc, "service_label": LABEL[svc]}
    for y in YEARS:
        d = nce[(nce.year == y) & (nce.service == svc)
                & nce.gbp_thousand.notna()]
        row[f"real_per_head_{y.replace('-', '_')}"] = round(
            d.gbp_thousand.sum() * 1000 * REAL[y] / eng_pop[y], 2)
    b, e = row["real_per_head_2013_14"], row["real_per_head_2024_25"]
    row["change_pct_2013_2024"] = round(100 * (e / b - 1), 1) if b else None
    row["caveat"] = (EDU_CAVEAT if svc == "education"
                     else PH_CAVEAT if svc == "public_health" else "")
    rows.append(row)
arc = pd.DataFrame(rows)
arc.to_csv(HERE / "arc_dumbbell.csv", index=False)

# ------------------------------------------ class populations per year (filed)
# an authority is "in" a class-year if it filed (TSE nce non-null);
# Cumberland 2024-25 drops out here on its blank return
tse = nce[(nce.service == "total_service_expenditure")
          & nce.gbp_thousand.notna()][["year", "ons_code", "cls"]]
filed = tse.merge(pop[["year", "ons_code", "population"]],
                  on=["year", "ons_code"], how="left")
cls_pop = (filed.groupby(["year", "cls"])
           .agg(population=("population", "sum"), n_authorities=("ons_code",
                                                                 "count"))
           .reset_index())

# ------------------------------------- (b) small multiples: class x service
sm_services = [s for s in ARC_SERVICES]
agg = (nce[nce.service.isin(sm_services) & nce.gbp_thousand.notna()
           & nce.ons_code.isin(filed.ons_code)]
       .merge(tse.rename(columns={"cls": "cls_ok"}), on=["year", "ons_code"])
       .groupby(["year", "cls", "service"])["gbp_thousand"].sum()
       .reset_index()
       .merge(cls_pop, on=["year", "cls"]))
agg["real_per_head"] = (agg.gbp_thousand * 1000
                        * agg.year.map(REAL) / agg.population)
sm = agg.pivot_table(index=["cls", "service"], columns="year",
                     values="real_per_head").reset_index()
# drop class x service combos the class does not deliver (<1 GBP/head always)
deliverer = sm[YEARS].max(axis=1) >= 1.0
dropped = sm[~deliverer][["cls", "service"]]
sm = sm[deliverer].copy()
sm_long = sm.melt(id_vars=["cls", "service"], value_vars=YEARS,
                  var_name="year", value_name="real_per_head")
sm_long = sm_long.merge(cls_pop[["year", "cls", "n_authorities"]],
                        on=["year", "cls"])
sm_long["cls_label"] = sm_long.cls.map(CLS_LABEL)
sm_long["service_label"] = sm_long.service.map(LABEL)
sm_long["real_per_head"] = sm_long.real_per_head.round(2)
sm_long["caveat"] = sm_long.service.map(
    lambda s: EDU_CAVEAT if s == "education"
    else PH_CAVEAT if s == "public_health" else "")
sm_long = sm_long.sort_values(["cls", "service", "year"])
sm_long.to_csv(HERE / "class_service_small_multiples.csv", index=False,
               columns=["cls", "cls_label", "service", "service_label",
                        "year", "real_per_head", "n_authorities", "caveat"])

# --------------------------------------------- (c) care share of the budget
# denominator: total service expenditure MINUS fire & police lines (fire
# responsibility moved between councils and standalone authorities across the
# period; police left LA books long ago but lines exist). Reported-TSE share
# also given so the choice is auditable.
care_rows = []
for y in YEARS:
    for cls in PRINCIPAL:
        codes = filed[(filed.year == y) & (filed.cls == cls)].ons_code
        d = nce[(nce.year == y) & nce.ons_code.isin(codes)]
        s = (d.groupby("service")["gbp_thousand"].sum())
        tse_rep = s.get("total_service_expenditure", 0.0)
        fire = s.get("fire_rescue", 0.0) or 0.0
        police = s.get("police", 0.0) or 0.0
        tse_adj = tse_rep - fire - police
        asc = s.get("adult_social_care", 0.0)
        csc = s.get("children_social_care", 0.0)
        cp = cls_pop[(cls_pop.year == y) & (cls_pop.cls == cls)]
        popn, n = float(cp.population.iloc[0]), int(cp.n_authorities.iloc[0])
        care_rows.append({
            "cls": cls, "cls_label": CLS_LABEL[cls], "year": y,
            "n_authorities": n,
            "asc_share_pct": round(100 * asc / tse_adj, 1),
            "csc_share_pct": round(100 * csc / tse_adj, 1),
            "care_share_pct": round(100 * (asc + csc) / tse_adj, 1),
            "residual_civic_share_pct": round(
                100 * (tse_adj - asc - csc) / tse_adj, 1),
            "care_share_pct_of_reported_tse": round(
                100 * (asc + csc) / tse_rep, 1),
            "tse_excl_fire_police_real_per_head": round(
                tse_adj * 1000 * REAL[y] / popn, 2),
            "care_real_per_head": round(
                (asc + csc) * 1000 * REAL[y] / popn, 2),
            "residual_civic_real_per_head": round(
                (tse_adj - asc - csc) * 1000 * REAL[y] / popn, 2)})
care = pd.DataFrame(care_rows)
care.to_csv(HERE / "care_share.csv", index=False)

# ------------------------- (d) per-authority distribution of real change
# stable authorities only: same ons_code present (and filed) in 2013-14 and
# 2024-25. Guards from 04_analyse.py: base >= 2 GBP/head for libraries
# (below that the 2013-14 line is outsourced/misbooked, not a service),
# 2024-25 > 0 (negative = income exceeded spend, e.g. Blackpool libraries).
# CSC guard: base >= 10 GBP/head (a delivering authority spends far more).
per_head = nce.merge(pop[["year", "ons_code", "population"]],
                     on=["year", "ons_code"], how="left")
per_head["real_per_head"] = (per_head.gbp_thousand * 1000
                             * per_head.year.map(REAL) / per_head.population)

dist_rows, excl_summary = [], []
for svc, base_floor, classes in [
        ("libraries", 2.0, ["SC", "UA", "MD", "LB"]),
        ("children_social_care", 10.0, ["SC", "UA", "MD", "LB"])]:
    d = per_head[(per_head.service == svc) & per_head.cls.isin(classes)
                 & ~per_head.ons_code.isin(FREAKS)]
    w = d.pivot_table(index=["ons_code", "name", "cls"], columns="year",
                      values="real_per_head").reset_index()
    base_n = w["2013-14"].notna().sum()
    both = w.dropna(subset=["2013-14", "2024-25"]).copy()
    reorg = base_n - len(both)  # code gone or (Cumberland) return blank
    ok = both[(both["2013-14"] >= base_floor) & (both["2024-25"] > 0)].copy()
    guard = len(both) - len(ok)
    ok["change_pct"] = (100 * (ok["2024-25"] / ok["2013-14"] - 1)).round(1)
    ok = ok.sort_values("change_pct")
    for _, r in ok.iterrows():
        dist_rows.append({
            "service": svc, "service_label": LABEL[svc],
            "ons_code": r.ons_code, "name": r["name"], "cls": r.cls,
            "cls_label": CLS_LABEL[r.cls],
            "real_per_head_2013_14": round(r["2013-14"], 2),
            "real_per_head_2024_25": round(r["2024-25"], 2),
            "change_pct": r.change_pct})
    excl_summary.append({
        "service": svc, "authorities_2013_14": int(base_n),
        "excluded_reorganised_or_no_return": int(reorg),
        "excluded_by_data_guards": int(guard), "stable_n": len(ok),
        "fell_n": int((ok.change_pct < 0).sum()),
        "median_change_pct": round(ok.change_pct.median(), 1),
        "p25_change_pct": round(ok.change_pct.quantile(.25), 1),
        "p75_change_pct": round(ok.change_pct.quantile(.75), 1)})
pd.DataFrame(dist_rows).to_csv(HERE / "authority_change_distribution.csv",
                               index=False)
excl = pd.DataFrame(excl_summary)
excl.to_csv(HERE / "authority_change_summary.csv", index=False)

print("=== arc (England, real 2024-25 prices, per head) ===")
print(arc[["service", "real_per_head_2013_14", "real_per_head_2024_25",
           "change_pct_2013_2024"]].to_string(index=False))
print("\n=== care share ===")
print(care[["cls", "year", "care_share_pct", "residual_civic_share_pct",
            "care_share_pct_of_reported_tse"]].to_string(index=False))
print("\n=== distribution summary ===")
print(excl.to_string(index=False))
print("\n=== dropped class x service combos (non-deliverers) ===")
print(dropped.to_string(index=False))
print("\nclass populations (filed):")
print(cls_pop.to_string(index=False))
