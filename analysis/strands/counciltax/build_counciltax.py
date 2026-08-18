"""THE BURDEN MOVED TO YOUR COUNCIL TAX BILL - counciltax strand build.

Sources (all local, no network):
  ../../ro/ro.sqlite        rs_summary (NRE, council tax requirement, reserves
                            levels), population (ONS mid-year on each RO year's
                            own boundary set), deflator (HMT GDP deflator,
                            June 2026 QNA, rebased to 2024-25 prices).
  ../../ro/raw/RS_*.{ods,xls}  financing block parsed fresh here: Revenue
                            Support Grant, police grant, retained income from
                            the rate retention scheme, collection-fund
                            surplus/deficit for council tax, other items.

Definitions, stated once:
  ct_share            council tax requirement / net revenue expenditure, both
                      in-year cash. CTR includes parish precepts for billing
                      authorities. The ratio can exceed 100% for an authority
                      that tops up reserves (appropriations sit between NRE
                      and CTR in the workbook identity).
  settlement funding  RSG + retained income from the rate retention scheme.
                      2013-14 is the first year of the retention scheme, so
                      the pair is defined identically at both endpoints, and
                      the sum is robust to the 100%-retention pilots that
                      rolled RSG into retained rates for some areas.
                      Police grant is ~0 for principal classes (verified
                      below) and excluded. Specific grants inside AEF are NOT
                      counted: they are dominated by schools money and
                      academisation moved schools off LA books.
  reserves            other earmarked + unallocated, 31 March levels;
                      schools / public health / DSG reserves excluded.

Tier rule: every per-authority table is within one MHCLG class; England
aggregates sum the five principal classes (SD, SC, UA, MD, LB). Class O
(police, fire, GLA, combined authorities) never enters a league.

Exclusions: City of London + Isles of Scilly from rankings (kept in England
sums); Cumberland 2024-25 filed no return (blank row, note M).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RO = HERE.parent.parent / "ro"
RAW = RO / "raw"

PRINCIPAL = ["SD", "UA", "MD", "LB", "SC"]
FREAKS = {"E09000001", "E06000053"}  # City of London, Isles of Scilly
ECODE = re.compile(r"^E\d{4}$")

con = sqlite3.connect(RO / "ro.sqlite")
rs = pd.read_sql("select * from rs_summary", con)
pop = pd.read_sql("select * from population", con)
defl = pd.read_sql("select * from deflator", con).set_index("year")["deflator"]
REAL = {y: defl["2024-25"] / defl[y] for y in ("2013-14", "2018-19", "2024-25")}
print("deflator to 2024-25 prices:", {k: round(v, 4) for k, v in REAL.items()})

# ---------------------------------------------------------------------------
# 1. Parse the financing block from the raw RS workbooks (fresh; the sqlite
#    only carries NRE, CTR and reserves).
# ---------------------------------------------------------------------------
FUNDING = {  # column header substring (lowercased) -> field
    "revenue support grant": "rsg",
    "police grant": "police_grant",
    "retained income from rate retention scheme": "rates_retention",
    "collection fund surplus": "collection_fund_ct",
    "other items": "other_items",
}

RS_SHEETS = [  # file, sheet, header row (0-based), engine, ecode col, name col
    ("RS_2024-25.ods", "RS_LA_Data_202425", "2024-25", 6, "odf", 0, 2),
    ("RS_2018-19.ods", "RS_LA_Data_2018-19", "2018-19", 6, "odf", 0, 2),
    ("RS_2013-14.xls", "RS LA Data 2013-14 (1)", "2013-14", 5, None, 0, 1),
]


def parse_financing(f, sheet, year, hdr, engine, ecol, ncol):
    kw = {"engine": engine} if engine else {}
    raw = pd.read_excel(RAW / f, sheet_name=sheet, header=None, **kw)
    cols = [re.sub(r"\s+", " ", str(c)).strip().lower() for c in raw.iloc[hdr]]
    idx_nre = next(i for i, c in enumerate(cols) if "net revenue expenditure" in c)
    idx_ctr = next(i for i, c in enumerate(cols) if "council tax requirement" in c)
    got, block_other = {}, []
    for i in range(idx_nre + 1, idx_ctr):  # the financing block only
        hit = next((v for k, v in FUNDING.items() if k in cols[i]), None)
        if hit and hit not in got:
            got[hit] = i
            print(f"  {year} {hit:<20} col {i}: {str(raw.iloc[hdr, i]).strip()[:70]}")
        else:
            block_other.append(i)  # appropriations, transfers
    body = raw.iloc[hdr + 1:]
    ecodes = body[ecol].astype(str).str.strip()
    keep = ecodes.str.match(ECODE)
    df = pd.DataFrame({"year": year, "ecode": ecodes[keep]})
    for field, i in got.items():
        df[field] = pd.to_numeric(body.loc[keep.values, i], errors="coerce").values
    df = df.drop_duplicates(subset="ecode")

    # England row = the workbook's own witness for sums and signs
    names = body[ncol].astype(str).str.strip().str.upper()
    eng = body[names.str.match(r"^ENGLAND")]
    assert len(eng) >= 1, f"no England row in {f}/{sheet}"
    eng = eng.iloc[0]
    num = lambda i: pd.to_numeric(eng[i], errors="coerce")
    # identity: CTR = NRE + (approps + transfers) - (funding lines), if the
    # funding lines are stored positive; or + everything if stored negative.
    nre_e, ctr_e = num(idx_nre), num(idx_ctr)
    adj = sum(num(i) for i in block_other if pd.notna(num(i)))
    fund = sum(num(i) for i in got.values() if pd.notna(num(i)))
    r_pos = ctr_e - (nre_e + adj - fund)
    r_neg = ctr_e - (nre_e + adj + fund)
    print(f"  {year} England: NRE {nre_e:,.0f}k CTR {ctr_e:,.0f}k | identity "
          f"residual if funding stored positive {r_pos:,.0f}k / stored negative {r_neg:,.0f}k")
    eng_wit = {f: num(i) for f, i in got.items()}
    return df, eng_wit


print("parsing RS financing blocks ...")
fin_frames, witnesses = [], {}
for f, sheet, year, hdr, engine, ecol, ncol in RS_SHEETS:
    df, wit = parse_financing(f, sheet, year, hdr, engine, ecol, ncol)
    fin_frames.append(df)
    witnesses[year] = wit
fin = pd.concat(fin_frames, ignore_index=True)

# The financing lines are stored NEGATIVE (income convention) in every
# vintage: the England-row identity CTR = NRE + adjustments + funding holds
# to ~0 with them as-is (residual 2k / 21m / 52m on 55-74bn), and fails by
# 54-67bn under the positive reading. Flip so grants are positive amounts.
for c in FUNDING.values():
    if c in fin.columns:
        fin[c] = -fin[c]

rs = rs.merge(fin, on=["year", "ecode"], how="left")

# authority-sum vs England-row witness per funding line (England row includes
# class O, so compare against ALL parsed rows; 2024-25 tolerates Cumberland)
print("witness check: authority sums vs the workbook's England row (Pmm thousand)")
for year, wit in witnesses.items():
    d = rs[rs.year == year]
    for field, eng_val in wit.items():
        ours = d[field].sum()
        eng_val = -eng_val  # England row carries the stored-negative sign
        flag = "" if abs(ours - eng_val) <= 600_000 else "  <-- MISMATCH"
        print(f"  {year} {field:<20} sum {ours:>13,.0f}  england {eng_val:>13,.0f}"
              f"  diff {ours - eng_val:>+11,.0f}{flag}")

# police grant must be ~0 for principal classes, else settlement def is wrong
pol = rs[rs.cls.isin(PRINCIPAL)].groupby("year").police_grant.sum()
print("police grant, principal classes only (should be ~0):", pol.to_dict())

# ---------------------------------------------------------------------------
# 2. Join population, build real-terms fields
# ---------------------------------------------------------------------------
rsp = rs[rs.cls.isin(PRINCIPAL)].merge(
    pop[["year", "ons_code", "population"]], on=["year", "ons_code"], how="left")
rsp["reserves_total"] = (rsp.reserves_other_earmarked.fillna(0)
                         + rsp.reserves_unallocated.fillna(0))
rsp["settlement"] = rsp[["rsg", "rates_retention"]].sum(min_count=1, axis=1)
FIN_COLS = ["rsg", "police_grant", "rates_retention", "collection_fund_ct",
            "other_items"]
rsp["total_financing"] = (rsp.council_tax_requirement
                          + rsp[FIN_COLS].fillna(0).sum(axis=1))
rsp["real"] = rsp.year.map(REAL)

# ---------------------------------------------------------------------------
# 3. (a) council-tax share of NRE: England + per class, three vintages
# ---------------------------------------------------------------------------
def share_rows(d, scope):
    out = []
    for y in ("2013-14", "2018-19", "2024-25"):
        g = d[(d.year == y) & d.net_revenue_expenditure.notna()]
        r = REAL[y]
        out.append({
            "scope": scope, "year": y, "n_authorities": len(g),
            "ctr_cash_bn": round(g.council_tax_requirement.sum() / 1e6, 2),
            "nre_cash_bn": round(g.net_revenue_expenditure.sum() / 1e6, 2),
            "ctr_real_bn": round(g.council_tax_requirement.sum() * r / 1e6, 2),
            "nre_real_bn": round(g.net_revenue_expenditure.sum() * r / 1e6, 2),
            "settlement_real_bn": round(g.settlement.sum() * r / 1e6, 2),
            "ct_share_of_nre_pct": round(100 * g.council_tax_requirement.sum()
                                         / g.net_revenue_expenditure.sum(), 1),
            "ct_share_of_financing_pct": round(
                100 * g.council_tax_requirement.sum()
                / g.total_financing.sum(), 1)})
    return out

eng_rows = share_rows(rsp, "England (5 principal classes)")
cls_rows = []
for cls in PRINCIPAL:
    cls_rows += share_rows(rsp[rsp.cls == cls], cls)
pd.DataFrame(eng_rows).to_csv(HERE / "ct_share_england.csv", index=False)
pd.DataFrame(cls_rows).to_csv(HERE / "ct_share_by_class.csv", index=False)
print("\nct share England:", [(r["year"], r["ct_share_of_nre_pct"]) for r in eng_rows])
print("ct share by class 2013-14 -> 2024-25:")
for cls in PRINCIPAL:
    a = next(r for r in cls_rows if r["scope"] == cls and r["year"] == "2013-14")
    b = next(r for r in cls_rows if r["scope"] == cls and r["year"] == "2024-25")
    print(f"  {cls}: {a['ct_share_of_nre_pct']}% -> {b['ct_share_of_nre_pct']}%")

# ---------------------------------------------------------------------------
# 4. (b) per-authority council-tax dependence 2024-25, within class
# ---------------------------------------------------------------------------
d24 = rsp[(rsp.year == "2024-25") & rsp.net_revenue_expenditure.notna()].copy()
d24["ct_share_pct"] = (100 * d24.council_tax_requirement
                       / d24.net_revenue_expenditure).round(1)
# Robust companion measure for colouring: council tax as a share of TOTAL
# financing (CTR + RSG + police grant + retained rates + collection fund +
# other items). The workbook identity makes this the share of the money that
# actually finances the budget, and it is immune to the tiny/negative-NRE
# netting artefacts that break CTR/NRE for investment-income districts.
d24["ct_share_financing_pct"] = (100 * d24.council_tax_requirement
                                 / d24.total_financing).round(1)
d24["ctr_per_head"] = (d24.council_tax_requirement * 1000
                       / d24.population).round(2)
d24["excluded_from_rankings"] = d24.ons_code.isin(FREAKS)
# CTR/NRE stops meaning "dependence" when NRE is tiny or negative (commercial
# investment income nets expenditure down: Woking, Runnymede, Mid Suffolk,
# Basingstoke) - and a handful of authorities file the rates-retention line
# as ZERO with the money booked under collection fund / other items / nowhere
# (hand-checked: Watford, Rugby, East Herts, Nuneaton, Guildford, Central
# Bedfordshire, Thurrock 2024-25), which fakes the financing share too.
# Flag every failure mode; colour only clean rows.
d24["fin_incomplete"] = (d24.rates_retention.isna()
                         | (d24.rates_retention <= 0))
d24["share_artefact"] = ((d24.net_revenue_expenditure <= 0)
                         | (d24.ct_share_pct > 150) | (d24.ct_share_pct < 0)
                         | (d24.ct_share_financing_pct > 100)
                         | (d24.ct_share_financing_pct < 0)
                         | d24.fin_incomplete)
ranked = d24[~d24.excluded_from_rankings & ~d24.share_artefact]
d24["class_percentile"] = (ranked.groupby("cls").ct_share_financing_pct
                           .rank(pct=True).mul(100).round(1))
d13 = rsp[(rsp.year == "2013-14") & rsp.net_revenue_expenditure.notna()]
d13s = (100 * d13.council_tax_requirement / d13.net_revenue_expenditure)
d24 = d24.merge(d13.assign(ct_share_pct_2013_14=d13s.round(1))
                [["ons_code", "ct_share_pct_2013_14"]], on="ons_code", how="left")
d24["ct_share_pp_change_2013_2024"] = (d24.ct_share_pct
                                       - d24.ct_share_pct_2013_14).round(1)
d24.sort_values(["cls", "ct_share_pct"], ascending=[True, False]).to_csv(
    HERE / "ct_dependence_2024_25.csv", index=False,
    columns=["ecode", "ons_code", "name", "cls", "council_tax_requirement",
             "net_revenue_expenditure", "ct_share_pct",
             "ct_share_financing_pct", "class_percentile",
             "population", "ctr_per_head", "ct_share_pct_2013_14",
             "ct_share_pp_change_2013_2024", "excluded_from_rankings",
             "share_artefact", "fin_incomplete"])
print("\nartefact-flagged (not coloured):",
      d24[d24.share_artefact][["name", "cls", "ct_share_pct",
                               "fin_incomplete"]].to_dict("records"))
print("\nct dependence 2024-25 medians / extremes by class:")
for cls in PRINCIPAL:
    g = d24[(d24.cls == cls) & ~d24.excluded_from_rankings
            & ~d24.share_artefact].dropna(
        subset=["ct_share_pct"]).sort_values("ct_share_pct")
    print(f"  {cls} n={len(g)} median {g.ct_share_pct.median():.1f}% "
          f"min {g.iloc[0]['name']} {g.iloc[0].ct_share_pct}% "
          f"max {g.iloc[-1]['name']} {g.iloc[-1].ct_share_pct}%")
print("ct share of TOTAL FINANCING 2024-25 (robust companion), by class:")
for cls in PRINCIPAL:
    g = d24[(d24.cls == cls) & ~d24.excluded_from_rankings].dropna(
        subset=["ct_share_financing_pct"]).sort_values("ct_share_financing_pct")
    print(f"  {cls} n={len(g)} median {g.ct_share_financing_pct.median():.1f}% "
          f"min {g.iloc[0]['name']} {g.iloc[0].ct_share_financing_pct}% "
          f"max {g.iloc[-1]['name']} {g.iloc[-1].ct_share_financing_pct}%")

# dependence vs deprivation: population-weighted LAD IMD 2019 (same method
# and vintage caveat as ../../ro/04_analyse.py); counties are not LADs
imd = pd.read_csv(HERE.parent.parent / "sewage" / "raw"
                  / "IoD2019_File7_scores_ranks_deciles.csv",
                  usecols=["Local Authority District code (2019)",
                           "Index of Multiple Deprivation (IMD) Score",
                           "Total population: mid 2015 (excluding prisoners)"])
imd.columns = ["lad19", "imd_score", "w"]
lad_imd = (imd.assign(x=imd.imd_score * imd.w).groupby("lad19")
           .agg(imd=("x", "sum"), w=("w", "sum")))
lad_imd = (lad_imd.imd / lad_imd.w).rename("imd_score").reset_index()
print("financing share vs IMD 2019, within class (clean rows):")
for cls in ["SD", "UA", "MD", "LB"]:
    g = (d24[(d24.cls == cls) & ~d24.excluded_from_rankings
             & ~d24.share_artefact]
         .merge(lad_imd, left_on="ons_code", right_on="lad19"))
    rho = g[["ct_share_financing_pct", "imd_score"]].corr(
        method="spearman").iloc[0, 1]
    print(f"  {cls} n={len(g)} spearman rho = {rho:.3f}")

# ---------------------------------------------------------------------------
# 5. (c) reserves arc, real
# ---------------------------------------------------------------------------
def reserves_rows(d, scope):
    out = []
    for y in ("2013-14", "2018-19", "2024-25"):
        g = d[(d.year == y) & d.net_revenue_expenditure.notna()]
        r = REAL[y]
        out.append({
            "scope": scope, "year": y, "n_authorities": len(g),
            "earmarked_real_bn": round(g.reserves_other_earmarked.sum() * r / 1e6, 2),
            "unallocated_real_bn": round(g.reserves_unallocated.sum() * r / 1e6, 2),
            "reserves_total_real_bn": round(g.reserves_total.sum() * r / 1e6, 2),
            "nre_real_bn": round(g.net_revenue_expenditure.sum() * r / 1e6, 2),
            "reserves_pct_of_nre": round(100 * g.reserves_total.sum()
                                         / g.net_revenue_expenditure.sum(), 1)})
    return out

res = reserves_rows(rsp, "England (5 principal classes)")
for cls in PRINCIPAL:
    res += reserves_rows(rsp[rsp.cls == cls], cls)
pd.DataFrame(res).to_csv(HERE / "reserves_arc.csv", index=False)
print("\nreserves arc England:",
      [(r["year"], r["reserves_total_real_bn"], r["nre_real_bn"]) for r in res[:3]])

# ---------------------------------------------------------------------------
# 6. (d) settlement funding league, real per head, 2013-14 -> 2024-25
# ---------------------------------------------------------------------------
per = rsp[~rsp.ons_code.isin(FREAKS)].copy()
per["settlement_real_ph"] = per.settlement * 1000 * per.real / per.population

# Completeness gate, from the hand-check: a billing or precepting authority
# always retains SOME rates, so a zero/blank rates-retention line means the
# financing block of that return cannot support the settlement measure
# (Watford, Rugby, East Herts, Nuneaton, Guildford, Central Bedfordshire,
# Thurrock file zero in 2024-25 with the money under collection fund /
# other items / nowhere; West Berkshire filed zero in 2013-14).
per["fin_ok"] = per.rates_retention.notna() & (per.rates_retention > 0)

# class arc (context): consistent panel - authorities with a complete
# financing block in all three vintages, so composition never shifts
panel_ok = (per.groupby("ons_code").fin_ok.sum() == 3)
panel = per[per.ons_code.map(panel_ok) & per.population.notna()]
arc = []
for y in ("2013-14", "2018-19", "2024-25"):
    for cls in PRINCIPAL:
        g = panel[(panel.year == y) & (panel.cls == cls)]
        arc.append({"cls": cls, "year": y, "n": len(g),
                    "settlement_real_bn": round(g.settlement.sum() * REAL[y] / 1e6, 2),
                    "settlement_real_per_head": round(
                        g.settlement.sum() * 1000 * REAL[y] / g.population.sum(), 2)})
pd.DataFrame(arc).to_csv(HERE / "grant_class_arc.csv", index=False)
print("\nsettlement real per head by class:")
for cls in PRINCIPAL:
    v = {r["year"]: r["settlement_real_per_head"] for r in arc if r["cls"] == cls}
    print(f"  {cls}: {v}")

# pivot on ons_code + cls only: name strings drift between vintages
# ("Gloucestershire" vs "Gloucestershire CC") and must not split rows
wide = per.pivot_table(index=["ons_code", "cls"],
                       columns="year",
                       values=["settlement_real_ph", "rsg", "rates_retention",
                               "population", "fin_ok"], aggfunc="first")
wide.columns = [f"{a}_{b}" for a, b in wide.columns]
wide = wide.reset_index()
latest_name = (per.sort_values("year").groupby("ons_code")["name"].last())
wide["name"] = wide.ons_code.map(latest_name)
lg = wide.dropna(subset=["settlement_real_ph_2013-14",
                         "settlement_real_ph_2024-25"]).copy()
lg["change_real_ph"] = (lg["settlement_real_ph_2024-25"]
                        - lg["settlement_real_ph_2013-14"])
lg["change_pct"] = 100 * (lg["settlement_real_ph_2024-25"]
                          / lg["settlement_real_ph_2013-14"] - 1)
# gates and machine-readable caution flags for the drawing side
lg["league_excluded"] = ~(lg["fin_ok_2013-14"].astype(bool)
                          & lg["fin_ok_2024-25"].astype(bool))
lg["handcheck"] = ""

def add_flag(mask, flag):
    lg.loc[mask, "handcheck"] = (lg.loc[mask, "handcheck"] + ";"
                                 + flag).str.lstrip(";")

add_flag(lg.change_pct > 25, "gainer_rates_growth")
# RSG = 0 with a live rates line mostly marks the enhanced-retention areas
# (GM, Merseyside, West Midlands mets, Cornwall) whose 2024-25 rates
# baseline has other grants rolled in - flatters their trajectory, don't
# headline as "least cut" without a hand-check
add_flag((lg["rsg_2024-25"] <= 0) & (lg["rates_retention_2024-25"] > 0),
         "rsg_zero_2024_check_rollin")
# smooth to 2018-19 then a >50% real fall to 2024-25 is the shape of a
# one-year booking event (appeals provision, deficit netting), not a policy
# arc - hand-check before naming (Cheshire West, Gloucestershire)
add_flag((lg["settlement_real_ph_2018-19"] > 0)
         & (lg["settlement_real_ph_2024-25"]
            / lg["settlement_real_ph_2018-19"] < 0.5),
         "cliff_after_2018_one_year_check")
add_flag(lg.league_excluded, "incomplete_financing_return")
lg = lg.sort_values(["cls", "change_pct"])
cols = ["ons_code", "name", "cls",
        "settlement_real_ph_2013-14", "settlement_real_ph_2018-19",
        "settlement_real_ph_2024-25", "change_real_ph", "change_pct",
        "rsg_2013-14", "rates_retention_2013-14",
        "rsg_2024-25", "rates_retention_2024-25",
        "league_excluded", "handcheck"]
lg[cols].round(2).to_csv(HERE / "grant_settlement_league.csv", index=False)
ok = lg[~lg.league_excluded]
print(f"\nleague: {len(lg)} stable authorities, {len(ok)} pass the "
      f"completeness gate ({ok.cls.value_counts().to_dict()}); excluded: "
      f"{lg[lg.league_excluded][['name', 'cls']].to_dict('records')}")
for cls in PRINCIPAL:
    g = ok[ok.cls == cls]
    print(f"  {cls} median change {g.change_pct.median():+.1f}% | deepest:")
    for _, r in g.head(4).iterrows():
        print(f"    {r['name']:<28} {r['settlement_real_ph_2013-14']:>8.2f} -> "
              f"{r['settlement_real_ph_2024-25']:>8.2f}  {r.change_pct:+.1f}%  "
              f"{r.handcheck}")
    for _, r in g.tail(3).iterrows():
        print(f"    (top) {r['name']:<22} {r['settlement_real_ph_2013-14']:>8.2f} -> "
              f"{r['settlement_real_ph_2024-25']:>8.2f}  {r.change_pct:+.1f}%  "
              f"{r.handcheck}")
