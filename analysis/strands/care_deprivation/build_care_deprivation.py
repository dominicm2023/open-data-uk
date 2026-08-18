"""
STRAND: NEED IS NOT EVENLY SPREAD
Builds chart-ready data for the deprivation relationship:
  (a) scatter_care_vs_deprivation.csv  - per-authority IMD avg score (pop-weighted,
      LSOA->LAD on 2024-25 boundaries) + CSC / ASC / libraries real net per head 2024-25,
      with gross and income-share verification columns
  (b) spearman_by_class_service.csv    - Spearman rho per class per service, recomputed
  (c) extreme_pairs.csv                - verified within-class extreme pairs (gross-checked)
  (d) the null foil ships inside (a): libraries column for the same authorities

Inputs (all local, no network):
  analysis/ro/ro_per_head.csv
  analysis/sewage/raw/IoD2019_File7_scores_ranks_deciles.csv

Tier rule: within class only (LB / MD / UA / SC). SD excluded: shire districts do not
run social care or libraries. City of London and Isles of Scilly excluded (tiny,
non-comparable - same convention as analysis/ro). Cumberland excluded (filed no
2024-25 return).
"""
import sys
from pathlib import Path

import pandas as pd

try:
    from scipy.stats import spearmanr
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

HERE = Path(__file__).resolve().parent
OPEN_DATA = HERE.parent.parent.parent          # ...\Open Data
RO = OPEN_DATA / "analysis" / "ro" / "ro_per_head.csv"
IMD = OPEN_DATA / "analysis" / "sewage" / "raw" / "IoD2019_File7_scores_ranks_deciles.csv"

SERVICES = ["children_social_care", "adult_social_care", "libraries"]
CLASSES = ["LB", "MD", "UA", "SC"]
EXCLUDE_ONS = {
    "E09000001",  # City of London - class of its own in practice
    "E06000053",  # Isles of Scilly
    "E06000063",  # Cumberland - no 2024-25 return filed (blank row, MHCLG imputes England)
}

# ---------------------------------------------------------------------------
# 1. LAD(2019) -> 2024-25 authority mapping.
# IMD 2019 File7 carries April-2019 LAD codes per LSOA row. Since then:
#   2020: Buckinghamshire UA;  2021: North & West Northamptonshire UAs;
#   2023: Cumberland, Westmorland & Furness, North Yorkshire, Somerset UAs.
# Successor map (predecessor LAD19 -> successor UA code):
SUCCESSOR = {
    # Buckinghamshire E06000060 (2020)
    "E07000004": "E06000060", "E07000005": "E06000060",
    "E07000006": "E06000060", "E07000007": "E06000060",
    # North Northamptonshire E06000061 (2021): Corby, E Northants, Kettering, Wellingborough
    "E07000150": "E06000061", "E07000152": "E06000061",
    "E07000153": "E06000061", "E07000156": "E06000061",
    # West Northamptonshire E06000062 (2021): Daventry, Northampton, S Northants
    "E07000151": "E06000062", "E07000154": "E06000062", "E07000155": "E06000062",
    # Cumberland E06000063 (2023): Allerdale, Carlisle, Copeland
    "E07000026": "E06000063", "E07000028": "E06000063", "E07000029": "E06000063",
    # Westmorland and Furness E06000064 (2023): Barrow, Eden, South Lakeland
    "E07000027": "E06000064", "E07000030": "E06000064", "E07000031": "E06000064",
    # North Yorkshire E06000065 (2023): Craven..Selby
    **{f"E070001{n}": "E06000065" for n in range(63, 70)},
    # Somerset E06000066 (2023): Mendip, Sedgemoor, South Somerset, Somerset West & Taunton
    "E07000187": "E06000066", "E07000188": "E06000066",
    "E07000189": "E06000066", "E07000246": "E06000066",
}

# District -> shire county (2024-25's 21 two-tier counties). E07 codes were allocated
# alphabetically by county in contiguous blocks (2009 allocation); the only later
# recodes among surviving counties are E07000240-243 (Herts) and E07000244-245 (Suffolk).
def _rng(a, b):
    return [f"E{n:08d}"[:1] + f"{n:08d}" for n in range(a, b + 1)]

def _codes(a, b):
    return [f"E070{n:05d}" for n in range(a, b + 1)]

COUNTY_DISTRICTS = {
    "Cambridgeshire":   _codes(8, 12),
    "Derbyshire":       _codes(32, 39),
    "Devon":            _codes(40, 47),
    "East Sussex":      _codes(61, 65),
    "Essex":            _codes(66, 77),
    "Gloucestershire":  _codes(78, 83),
    "Hampshire":        _codes(84, 94),
    "Hertfordshire":    _codes(95, 96) + _codes(98, 99) + _codes(102, 103) + _codes(240, 243),
    "Kent":             _codes(105, 116),
    "Lancashire":       _codes(117, 128),
    "Leicestershire":   _codes(129, 135),
    "Lincolnshire":     _codes(136, 142),
    "Norfolk":          _codes(143, 149),
    "Nottinghamshire":  _codes(170, 176),
    "Oxfordshire":      _codes(177, 181),
    "Staffordshire":    _codes(192, 199),
    "Suffolk":          _codes(200, 200) + _codes(202, 203) + _codes(244, 245),
    "Surrey":           _codes(207, 217),
    "Warwickshire":     _codes(218, 222),
    "West Sussex":      _codes(223, 229),
    "Worcestershire":   _codes(234, 239),
}
EXPECTED_DISTRICT_COUNTS = {
    "Cambridgeshire": 5, "Derbyshire": 8, "Devon": 8, "East Sussex": 5, "Essex": 12,
    "Gloucestershire": 6, "Hampshire": 11, "Hertfordshire": 10, "Kent": 12,
    "Lancashire": 12, "Leicestershire": 7, "Lincolnshire": 7, "Norfolk": 7,
    "Nottinghamshire": 7, "Oxfordshire": 5, "Staffordshire": 8, "Suffolk": 5,
    "Surrey": 11, "Warwickshire": 5, "West Sussex": 7, "Worcestershire": 6,
}

# ---------------------------------------------------------------------------
ro = pd.read_csv(RO)
ro24 = ro[ro.year == "2024-25"].copy()

# county name -> E10 ons_code from the RO file itself (no memory-typed E10 codes)
sc_rows = ro24[ro24.cls == "SC"][["ons_code", "name"]].drop_duplicates()
county_code = dict(zip(
    sc_rows.name.str.replace(r"\s+CC$", "", regex=True).str.strip(), sc_rows.ons_code))
assert len(county_code) == 21, f"expected 21 shire counties, got {len(county_code)}"
missing = set(COUNTY_DISTRICTS) - set(county_code)
assert not missing, f"county name mismatch vs RO file: {missing}"

for county, codes in COUNTY_DISTRICTS.items():
    assert len(codes) == EXPECTED_DISTRICT_COUNTS[county], (county, len(codes))
district_to_county = {c: county_code[county]
                      for county, codes in COUNTY_DISTRICTS.items() for c in codes}
assert len(district_to_county) == 164, len(district_to_county)

# validate: the mapping's key set == the RO file's 2024-25 SD code set (both directions)
sd_codes = set(ro24[ro24.cls == "SD"].ons_code.unique())
assert sd_codes == set(district_to_county), (
    "SD codes vs district map mismatch: "
    f"only-in-RO={sorted(sd_codes - set(district_to_county))} "
    f"only-in-map={sorted(set(district_to_county) - sd_codes)}"
)
# spot checks against RO names (guards against a whole-block misassignment)
sd_names = dict(zip(ro24[ro24.cls == "SD"].ons_code, ro24[ro24.cls == "SD"].name))
for code, want in [("E07000223", "Adur"), ("E07000008", "Cambridge"),
                   ("E07000241", "Welwyn Hatfield"), ("E07000244", "East Suffolk"),
                   ("E07000218", "North Warwickshire"), ("E07000136", "Boston")]:
    got = sd_names[code].strip()
    assert want.lower() in got.lower(), (code, want, got)

# ---------------------------------------------------------------------------
# 2. IMD: LSOA -> 2024-25 authority, population-weighted average score.
# Mirrors the official LAD summary construction (population-weighted average of
# LSOA combined scores) but on 2024-25 boundaries. Weights are the IMD file's own
# mid-2015 total population (the denominators the IMD itself uses).
imd = pd.read_csv(IMD)
imd.columns = [c.strip() for c in imd.columns]
imd = imd[["LSOA code (2011)", "Local Authority District code (2019)",
           "Index of Multiple Deprivation (IMD) Score",
           "Total population: mid 2015 (excluding prisoners)"]]
imd.columns = ["lsoa", "lad19", "score", "pop15"]
assert imd.lsoa.nunique() == 32844, imd.lsoa.nunique()   # all English LSOAs

def to_2024(code):
    if code in SUCCESSOR:
        return SUCCESSOR[code]
    if code in district_to_county:
        return district_to_county[code]
    return code                                            # unchanged LAD / UA / MD / LB

imd["auth24"] = imd.lad19.map(to_2024)
lad_imd = (imd.assign(sw=imd.score * imd.pop15)
              .groupby("auth24")
              .agg(imd_avg_score=("sw", "sum"), imd_pop_2015=("pop15", "sum"),
                   n_lsoas=("lsoa", "count")))
lad_imd["imd_avg_score"] = lad_imd.imd_avg_score / lad_imd.imd_pop_2015
lad_imd = lad_imd.reset_index()

# every 2024-25 principal authority in LB/MD/UA/SC must land an IMD score
principal = ro24[ro24.cls.isin(CLASSES)][["ons_code", "name", "cls"]].drop_duplicates()
no_imd = set(principal.ons_code) - set(lad_imd.auth24)
assert not no_imd, f"authorities with no IMD aggregation: {no_imd}"

# ---------------------------------------------------------------------------
# 3. Wide per-authority spend table (net real per head 2024-25 = nominal for 2024-25),
# with gross and income for verification.
svc = ro24[ro24.cls.isin(CLASSES) & ro24.service.isin(SERVICES)
           & ~ro24.ons_code.isin(EXCLUDE_ONS)].copy()
wide = svc.pivot_table(index=["ons_code", "name", "cls", "population"],
                       columns=["service", "measure"], values="real_gbp_per_head",
                       aggfunc="first")
wide.columns = [f"{s}_{m}" for s, m in wide.columns]
wide = wide.reset_index().merge(lad_imd.rename(columns={"auth24": "ons_code"}),
                                on="ons_code", how="left")
assert wide.imd_avg_score.notna().all()

out = pd.DataFrame({
    "authority": wide.name.str.replace(" UA", "", regex=False).str.strip(),
    "ons_code": wide.ons_code,
    "cls": wide.cls,
    "population_mid2024": wide.population,
    "imd_avg_score": wide.imd_avg_score.round(2),
})
for s, short in [("children_social_care", "csc"), ("adult_social_care", "asc"),
                 ("libraries", "lib")]:
    out[f"{short}_net_per_head_real2425"] = wide[f"{s}_nce"].round(2)
    out[f"{short}_gross_per_head"] = wide[f"{s}_gross"].round(2)
    share = (wide[f"{s}_income"] / wide[f"{s}_gross"]).replace(
        [float("inf"), float("-inf")], pd.NA)
    out[f"{short}_income_share_of_gross"] = share.astype(float).round(3)
out["lib_net_negative"] = out.lib_net_per_head_real2425 < 0
out = out.sort_values(["cls", "authority"]).reset_index(drop=True)

# sanity pins from analysis/ro/REPORT.md
def val(name, col):
    return out.loc[out.authority == name, col].iloc[0]
assert abs(val("Blackpool", "csc_net_per_head_real2425") - 598.75) < 0.5
assert abs(val("North Yorkshire", "csc_net_per_head_real2425") - 136.14) < 0.5
assert abs(val("Kensington & Chelsea", "lib_net_per_head_real2425") - 43.84) < 0.05
assert abs(val("Barking & Dagenham", "lib_net_per_head_real2425") - 3.35) < 0.05

out.to_csv(HERE / "scatter_care_vs_deprivation.csv", index=False)

# ---------------------------------------------------------------------------
# 4. Spearman per class per service (net real per head vs IMD avg score).
rows = []
for cls in CLASSES:
    d = out[out.cls == cls]
    for s, short in [("children_social_care", "csc"), ("adult_social_care", "asc"),
                     ("libraries", "lib")]:
        col = f"{short}_net_per_head_real2425"
        dd = d[[col, "imd_avg_score"]].dropna()
        rho = dd[col].corr(dd.imd_avg_score, method="spearman")
        p = None
        if HAVE_SCIPY and len(dd) > 2:
            p = spearmanr(dd[col], dd.imd_avg_score).pvalue
        rows.append({"cls": cls, "service": s, "n": len(dd),
                     "spearman_rho": round(rho, 3),
                     "p_value": (round(p, 5) if p is not None else "")})
sp = pd.DataFrame(rows)
sp.to_csv(HERE / "spearman_by_class_service.csv", index=False)

lb_csc = sp[(sp.cls == "LB") & (sp.service == "children_social_care")].spearman_rho.iloc[0]
lb_lib = sp[(sp.cls == "LB") & (sp.service == "libraries")].spearman_rho.iloc[0]
assert abs(lb_csc - 0.567) < 0.02, lb_csc   # pin to analysis/ro recompute
assert abs(lb_lib - 0.036) < 0.02, lb_lib

# ---------------------------------------------------------------------------
# 5. Extreme pairs, gross-checked, within class.
def pick_pair(cls, service, short):
    d = out[(out.cls == cls)].dropna(subset=[f"{short}_net_per_head_real2425"]).copy()
    col = f"{short}_net_per_head_real2425"
    d = d.sort_values(col)
    med = d[col].median()

    def clean(row):
        # artefact rules from the hand-check graveyard: net must be positive and
        # not mostly an income offset (income > 25% of gross flagged for care;
        # libraries charging artefacts documented separately)
        share = row[f"{short}_income_share_of_gross"]
        return row[col] > 0 and (pd.isna(share) or share < 0.25)

    low = next((r for _, r in d.iterrows() if clean(r)), None)
    high = next((r for _, r in d[::-1].iterrows() if clean(r)), None)
    skipped_low = [r.authority for _, r in d.iterrows()
                   if not clean(r) and r[col] <= low[col]]
    return high, low, med, skipped_low

pairs = []
for cls, service, short in [("UA", "children_social_care", "csc"),
                            ("LB", "children_social_care", "csc"),
                            ("MD", "children_social_care", "csc"),
                            ("UA", "adult_social_care", "asc"),
                            ("LB", "libraries", "lib")]:
    hi, lo, med, skipped = pick_pair(cls, service, short)
    net_ratio = hi[f"{short}_net_per_head_real2425"] / lo[f"{short}_net_per_head_real2425"]
    gross_ratio = hi[f"{short}_gross_per_head"] / lo[f"{short}_gross_per_head"]
    pairs.append({
        "cls": cls, "service": service,
        "high_authority": hi.authority, "high_net_per_head": hi[f"{short}_net_per_head_real2425"],
        "high_gross_per_head": hi[f"{short}_gross_per_head"],
        "high_imd_avg_score": hi.imd_avg_score,
        "low_authority": lo.authority, "low_net_per_head": lo[f"{short}_net_per_head_real2425"],
        "low_gross_per_head": lo[f"{short}_gross_per_head"],
        "low_imd_avg_score": lo.imd_avg_score,
        "net_ratio": round(net_ratio, 2), "gross_ratio": round(gross_ratio, 2),
        "class_median_net": round(med, 2),
        "skipped_as_artefact": "; ".join(skipped),
    })
pairs = pd.DataFrame(pairs)
p0 = pairs.iloc[0]
assert p0.high_authority == "Blackpool" and p0.low_authority == "North Yorkshire", pairs.iloc[0]
pairs.to_csv(HERE / "extreme_pairs.csv", index=False)

print("scatter rows:", len(out), "by class:", out.cls.value_counts().to_dict())
print(sp.to_string(index=False))
print(pairs.to_string(index=False))
print("OK - all assertions passed")
