# AUSTERITY WAS A POSTCODE POLICY — settlement loss per head vs deprivation, within class.
# Pure on-disk join. Inputs:
#   ../../strands/counciltax/grant_settlement_league.csv   (real settlement change per head 2013-14 -> 2024-25, flags)
#   ../../strands/care_deprivation/scatter_care_vs_deprivation.csv  (imd_avg_score, population-weighted IMD 2019, upper-tier only)
#   ../../strands/counciltax/ct_dependence_2024_25.csv     (ctr_per_head, financing share, flags)
# Rebuild: python build_regressive.py  (prints every witness check)
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from pathlib import Path

HERE = Path(__file__).resolve().parent
STR = HERE.parent.parent / "strands"

league = pd.read_csv(STR / "counciltax" / "grant_settlement_league.csv")
imd = pd.read_csv(STR / "care_deprivation" / "scatter_care_vs_deprivation.csv")
ct = pd.read_csv(STR / "counciltax" / "ct_dependence_2024_25.csv")

print("rows: league", len(league), "imd", len(imd), "ct", len(ct))
league["handcheck"] = league["handcheck"].fillna("")
league["loss_ph"] = -league["change_real_ph"]          # positive = lost money per head
league["clean"] = (~league["league_excluded"]) & (league["handcheck"] == "")

# ---- district-level IMD from the raw LSOA file (same method as care_deprivation:
# population-weighted average of LSOA IMD scores, weights = the file's own mid-2015
# populations, mirroring the official LAD summary construction). LAD2019 codes ARE
# district codes; the league's stable panel excludes every district reorganised since.
raw = pd.read_csv(HERE.parent.parent / "sewage" / "raw" / "IoD2019_File7_scores_ranks_deciles.csv")
raw.columns = [c.strip() for c in raw.columns]
raw = raw[["Local Authority District code (2019)",
           "Index of Multiple Deprivation (IMD) Score",
           "Total population: mid 2015 (excluding prisoners)"]]
raw.columns = ["lad19", "score", "pop15"]
lad_imd = (raw.assign(wx=raw.score * raw.pop15).groupby("lad19")
              .agg(wx=("wx", "sum"), w=("pop15", "sum")))
lad_imd["imd_lad19"] = lad_imd.wx / lad_imd.w
# witness: on boundary-stable upper-tier authorities my aggregation must reproduce
# the care_deprivation strand's published values
chk = imd.merge(lad_imd["imd_lad19"], left_on="ons_code", right_index=True, how="inner")
dev = (chk.imd_avg_score - chk.imd_lad19).abs()
print(f"witness vs care_deprivation IMD: {len(chk)} stable authorities, max abs dev {dev.max():.3f}")
assert dev.max() < 0.05, "LSOA aggregation does not reproduce the validated strand values"

# ---- join IMD: upper tier from the validated scatter file, SD from File7 ----
imd_j = imd[["ons_code", "imd_avg_score", "population_mid2024"]]
m = league.merge(imd_j, on="ons_code", how="left")
sd_mask = (m.cls == "SD") & m.imd_avg_score.isna()
m.loc[sd_mask, "imd_avg_score"] = m.loc[sd_mask, "ons_code"].map(lad_imd["imd_lad19"])
print("IMD matched by class:")
print(m.groupby("cls")["imd_avg_score"].agg(matched="count", total="size").to_string())
# witness: which league rows failed the IMD join
print("league rows without IMD:", m[m.imd_avg_score.isna()]["name"].tolist())
# and which IMD rows aren't in the league (reorganised unitaries etc.)
print("IMD rows not in league:", sorted(set(imd.ons_code) - set(league.ons_code)))

# ---- (a) scatter + Spearman per class ----
sc = m[m.imd_avg_score.notna()].copy()
sc["imd_rank_in_class"] = sc.groupby("cls")["imd_avg_score"].rank(ascending=False, method="min").astype(int)  # 1 = most deprived
sc["class_n"] = sc.groupby("cls")["ons_code"].transform("size")

rows = []
for cls, g in sc.groupby("cls"):
    for label, gg in [("clean", g[g.clean]), ("all_matched", g)]:
        if len(gg) < 5:
            continue
        r_ph, p_ph = spearmanr(gg.imd_avg_score, gg.loss_ph)
        r_pc, p_pc = spearmanr(gg.imd_avg_score, -gg.change_pct)  # positive rho = deprived lost bigger SHARE
        rows.append(dict(cls=cls, subset=label, n=len(gg),
                         rho_loss_ph_vs_imd=round(r_ph, 3), p_loss_ph=f"{p_ph:.2g}",
                         rho_loss_pct_vs_imd=round(r_pc, 3), p_loss_pct=f"{p_pc:.2g}"))
spear = pd.DataFrame(rows)
print("\nSpearman (positive = more deprived lost more), per class:")
print(spear.to_string(index=False))
spear.to_csv(HERE / "spearman_by_class.csv", index=False)

scatter_out = sc[["ons_code", "name", "cls", "imd_avg_score", "imd_rank_in_class", "class_n",
                  "settlement_real_ph_2013-14", "settlement_real_ph_2024-25",
                  "loss_ph", "change_pct", "clean", "league_excluded", "handcheck"]].copy()
scatter_out = scatter_out.sort_values(["cls", "loss_ph"], ascending=[True, False])
scatter_out.to_csv(HERE / "scatter_settlement_loss_vs_imd.csv", index=False)

# ---- (b) map/hex-ready: all 304 league authorities ----
mapd = m[["ons_code", "name", "cls", "loss_ph", "change_pct", "imd_avg_score",
          "clean", "league_excluded", "handcheck"]].copy()
mapd = mapd.sort_values("ons_code")
mapd.to_csv(HERE / "map_loss_per_head.csv", index=False)
print("\nmap rows:", len(mapd), "| clean:", int(mapd.clean.sum()))

# ---- (c) extremes within class, clean rows only, with deprivation ranks ----
ext_rows = []
for cls, g in sc[sc.clean].groupby("cls"):
    g = g.sort_values("loss_ph", ascending=False)
    for tag, sel in [("biggest_loser", g.head(3)), ("smallest_loser", g.tail(3))]:
        for _, r in sel.iterrows():
            ext_rows.append(dict(cls=cls, position=tag, name=r["name"], ons_code=r.ons_code,
                                 loss_ph=round(r.loss_ph, 2), change_pct=r.change_pct,
                                 imd_avg_score=r.imd_avg_score,
                                 imd_rank_in_class=r.imd_rank_in_class, class_n=r.class_n))
ext = pd.DataFrame(ext_rows)
print("\nExtremes (clean only, IMD rank 1 = most deprived in class):")
print(ext.to_string(index=False))
ext.to_csv(HERE / "extremes_by_class.csv", index=False)

# ---- (d) the compounding join: loss vs current council-tax base ----
ct2 = ct[["ons_code", "ctr_per_head", "ct_share_financing_pct",
          "excluded_from_rankings", "share_artefact", "fin_incomplete"]].copy()
comp = sc.merge(ct2, on="ons_code", how="left")
comp["ct_clean"] = (~comp.excluded_from_rankings.fillna(True)) & \
                   (~comp.share_artefact.fillna(True)) & (~comp.fin_incomplete.fillna(True))
print("\ncompound join: matched ctr_per_head", comp.ctr_per_head.notna().sum(), "of", len(comp))

crows = []
for cls, g in comp[comp.clean & comp.ct_clean & comp.ctr_per_head.notna()].groupby("cls"):
    if len(g) < 5:
        continue
    r1, p1 = spearmanr(g.imd_avg_score, g.ctr_per_head)     # expect negative: deprived -> weak tax base
    r2, p2 = spearmanr(g.loss_ph, g.ctr_per_head)           # expect negative: biggest losers -> weakest base
    crows.append(dict(cls=cls, n=len(g),
                      rho_imd_vs_ctr_ph=round(r1, 3), p1=f"{p1:.2g}",
                      rho_lossph_vs_ctr_ph=round(r2, 3), p2=f"{p2:.2g}"))
cspear = pd.DataFrame(crows)
print("\nCompounding Spearman per class (negative = deprived/biggest-losers have weaker tax base):")
print(cspear.to_string(index=False))
cspear.to_csv(HERE / "compound_spearman_by_class.csv", index=False)

comp_out = comp[["ons_code", "name", "cls", "imd_avg_score", "imd_rank_in_class",
                 "loss_ph", "change_pct", "ctr_per_head", "ct_share_financing_pct",
                 "clean", "ct_clean", "handcheck"]].sort_values(["cls", "loss_ph"], ascending=[True, False])
comp_out.to_csv(HERE / "compound_join.csv", index=False)

# quartile witness: within class, top-loss-quartile vs bottom-loss-quartile median ctr_per_head
print("\nQuartile witness (clean rows, within class): median ctr_per_head, top vs bottom loss quartile")
for cls, g in comp[comp.clean & comp.ct_clean & comp.ctr_per_head.notna()].groupby("cls"):
    if len(g) < 8:
        continue
    q = g.loss_ph.quantile([0.25, 0.75])
    top = g[g.loss_ph >= q[0.75]]
    bot = g[g.loss_ph <= q[0.25]]
    print(f"  {cls}: biggest losers median ctr £{top.ctr_per_head.median():.0f}/head "
          f"(median IMD {top.imd_avg_score.median():.1f}) vs smallest losers £{bot.ctr_per_head.median():.0f}/head "
          f"(IMD {bot.imd_avg_score.median():.1f})")

# per-class medians of loss for context
print("\nClean class medians: loss_ph / change_pct")
print(m[m.clean].groupby("cls")[["loss_ph", "change_pct"]].median().round(1).to_string())
