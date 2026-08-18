"""
Strand: THE GRADIENT THAT ISN'T THERE (gradient_null)

Builds chart-ready CSVs from analysis/sewage/joined.csv (EDM calendar-2025 storm
overflows joined to IMD 2019 LSOAs) and its raw inputs. No network. No drawing.

Outputs (this directory):
  decile_series.csv        - (a) spills/hours per IMD decile, absolute + per-LSOA,
                             all-England and urban-only control (RUC 2011 A/B/C)
  ambiguity_by_decile.csv  - (c) share of overflows with >1 candidate IMD decile
                             within 100 m, per assigned decile
  counterexample_cards.csv - (b) Wilmslow card + 3 rich-heavy + 3 poor-light,
                             anchored on named LSOA population-weighted centroids
  card_scan_decile10.csv / card_scan_decile1.csv - full ranked scans the cards
                             were picked from (audit trail)

Run: python build.py   (from this directory or repo root; paths are absolute-ish)
"""
import csv
import json
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SEW = os.path.join(ROOT, "analysis", "sewage")

# ---------------------------------------------------------------- load inputs
# joined.csv: one row per monitored storm overflow, England, calendar 2025
rows = []
with open(os.path.join(SEW, "joined.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append(r)
assert len(rows) == 14180, len(rows)

# IMD 2019 File 7: decile + LA name per English LSOA
imd_decile = {}
lsoa_la = {}
lsoa_name = {}
with open(os.path.join(SEW, "raw", "IoD2019_File7_scores_ranks_deciles.csv"),
          encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        code = r["LSOA code (2011)"]
        imd_decile[code] = int(r["Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)"])
        lsoa_la[code] = r["Local Authority District name (2019)"]
        lsoa_name[code] = r["LSOA name (2011)"]
assert len(imd_decile) == 32844, len(imd_decile)

# RUC 2011: urban = A*/B*/C* (major/minor conurbation, city and town)
ruc = {}
with open(os.path.join(SEW, "raw", "ruc2011_lsoa.json"), encoding="utf-8") as f:
    for feat in json.load(f)["features"]:
        a = feat["attributes"]
        ruc[a["LSOA11CD"]] = a["RUC11CD"]

def is_urban(code):
    c = ruc.get(code, "")
    return c[:1] in ("A", "B", "C")

# LSOA 2011 population-weighted centroids, EPSG:27700 (x=easting, y=northing)
pwc = {}
with open(os.path.join(SEW, "raw", "lsoa2011_pwc.json"), encoding="utf-8") as f:
    for feat in json.load(f)["features"]:
        a = feat["attributes"]
        g = feat["geometry"]
        pwc[a["lsoa11cd"]] = (g["x"], g["y"])

# ------------------------------------------------- (a) decile series + control
# Denominators: LSOAs per decile (all England; urban stratum via RUC A/B/C)
lsoas_all = defaultdict(int)
lsoas_urban = defaultdict(int)
for code, dec in imd_decile.items():
    lsoas_all[dec] += 1
    if is_urban(code):
        lsoas_urban[dec] += 1

series = {"all_england": defaultdict(lambda: [0, 0.0, 0.0]),
          "urban_only": defaultdict(lambda: [0, 0.0, 0.0])}  # dec -> [n, spills, hours]
for r in rows:
    dec = int(r["imd_decile"])
    n_sp = float(r["spill_count"])
    n_hr = float(r["total_duration_hours"])
    series["all_england"][dec][0] += 1
    series["all_england"][dec][1] += n_sp
    series["all_england"][dec][2] += n_hr
    if r["urban"] == "1":
        series["urban_only"][dec][0] += 1
        series["urban_only"][dec][1] += n_sp
        series["urban_only"][dec][2] += n_hr

with open(os.path.join(HERE, "decile_series.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["series", "imd_decile_2019", "decile_label", "lsoas_in_stratum",
                "monitored_overflows", "overflows_per_100_lsoas",
                "spills_2025", "spill_hours_2025",
                "spills_per_lsoa", "hours_per_lsoa", "spills_per_overflow"])
    for s, denom in (("all_england", lsoas_all), ("urban_only", lsoas_urban)):
        for dec in range(1, 11):
            n, sp, hr = series[s][dec]
            d = denom[dec]
            lab = ("1 most deprived" if dec == 1
                   else "10 least deprived" if dec == 10 else str(dec))
            w.writerow([s, dec, lab, d, n, round(100 * n / d, 1),
                        int(sp), round(hr, 1),
                        round(sp / d, 2), round(hr / d, 2),
                        round(sp / n, 1) if n else ""])

# ------------------------------------- (c) boundary ambiguity per decile
with open(os.path.join(HERE, "ambiguity_by_decile.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["imd_decile_2019", "decile_label", "monitored_overflows",
                "multi_lsoa_within_100m", "share_multi_lsoa",
                "multi_decile_within_100m", "share_multi_decile"])
    tot = [0, 0, 0]
    for dec in range(1, 11):
        sub = [r for r in rows if int(r["imd_decile"]) == dec]
        ml = sum(1 for r in sub if len(set(r["candidate_lsoas_100m"].split(";"))) > 1)
        md = sum(1 for r in sub if len(set(r["candidate_imd_deciles_100m"].split(";"))) > 1)
        tot[0] += len(sub); tot[1] += ml; tot[2] += md
        lab = ("1 most deprived" if dec == 1
               else "10 least deprived" if dec == 10 else str(dec))
        w.writerow([dec, lab, len(sub), ml, round(ml / len(sub), 3),
                    md, round(md / len(sub), 3)])
    w.writerow(["all", "England", tot[0], tot[1], round(tot[1] / tot[0], 3),
                tot[2], round(tot[2] / tot[0], 3)])
print(f"ambiguity all-England: {tot[1]}/{tot[0]} multi-LSOA ({tot[1]/tot[0]:.1%}), "
      f"{tot[2]}/{tot[0]} multi-decile ({tot[2]/tot[0]:.1%})")

# ----------------------------------------- (b) counter-example card machinery
E = np.array([float(r["easting"]) for r in rows])
N = np.array([float(r["northing"]) for r in rows])
SP = np.array([float(r["spill_count"]) for r in rows])
HR = np.array([float(r["total_duration_hours"]) for r in rows])

def within_5km(x, y):
    """Indices of overflows within 5 km (planar EPSG:27700 metres) of (x, y)."""
    d2 = (E - x) ** 2 + (N - y) ** 2
    return np.where(d2 <= 5000.0 ** 2)[0]

def card(anchor_code):
    x, y = pwc[anchor_code]
    idx = within_5km(x, y)
    n_over = len(idx)
    spills = int(SP[idx].sum())
    hours = float(HR[idx].sum())
    top = None
    if n_over:
        j = idx[np.argmax(SP[idx])]
        top = (rows[j]["site_name"], int(float(rows[j]["spill_count"])),
               round(float(rows[j]["total_duration_hours"]), 1))
    return n_over, spills, hours, top

def scan(decile, out_name):
    """Rank every LSOA of a given decile by spills within 5 km of its centroid."""
    codes = [c for c, d in imd_decile.items() if d == decile and c in pwc]
    res = []
    for c in codes:
        x, y = pwc[c]
        idx = within_5km(x, y)
        res.append((c, len(idx), int(SP[idx].sum()), round(float(HR[idx].sum()), 1)))
    res.sort(key=lambda t: -t[2])
    with open(os.path.join(HERE, out_name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lsoa_code", "lsoa_name", "local_authority",
                    "overflows_within_5km", "spills_within_5km", "hours_within_5km"])
        for c, n, sp, hr in res:
            w.writerow([c, lsoa_name[c], lsoa_la[c], n, sp, hr])
    return res

scan10 = scan(10, "card_scan_decile10.csv")
scan1 = scan(1, "card_scan_decile1.csv")
print("top decile-10 anchors by spills within 5km:")
for c, n, sp, hr in scan10[:15]:
    print(f"  {c} {lsoa_name[c]:28s} {lsoa_la[c]:28s} overflows={n:3d} spills={sp:5d} hours={hr:9.1f}")
print("decile-1 anchors, fewest spills (with at least 1 overflow monitored nearby shown separately):")
zero_over = [t for t in scan1 if t[1] == 0]
print(f"  decile-1 LSOAs with ZERO monitored overflows within 5km: {len(zero_over)} of {len(scan1)}")
light = sorted([t for t in scan1 if t[1] >= 3], key=lambda t: (t[2], -t[1]))
for c, n, sp, hr in light[:20]:
    print(f"  {c} {lsoa_name[c]:28s} {lsoa_la[c]:28s} overflows={n:3d} spills={sp:5d} hours={hr:9.1f}")

# ------------------------------------------------------------ the seven cards
# Anchors are LSOA 2011 population-weighted centroids; radius 5 km planar
# (EPSG:27700). Picked from the ranked scans above for recognisability and
# geographic/company spread; scans are shipped as the audit trail.
# Place labels were verified against EA site names inside each 5 km circle
# (evidence_sites column). Wilmslow anchor E01018602 reproduces the prior
# session's 521-spill figure exactly (it is also one of the candidate LSOAs
# of WILMSLOW PARK SOUTH CSO, itself sited in decile-10 E01018584).
CARDS = [
    ("rich_heavy", "Wilmslow, Cheshire", "E01018602",
     "WILMSLOW WASTEWATER TREATMENT WORKS; FULSHAW CROSS CSO 271U4; ALDERLEY EDGE WWTW ALDYE"),
    ("rich_heavy", "Bath", "E01014380",
     "RECREATION GROUND CSO; PRIOR PARK ROAD CSO; ENTRY HILL GARDENS CSO"),
    ("rich_heavy", "Harrogate (eastern side)", "E01027660",
     "HARROGATE NORTH SEWAGE TREATMENT; HARROGATE HYDRO CSOS; CRIMPLE LANE CSO"),
    ("rich_heavy", "central York (riverside)", "E01013358",
     "THE ESPLANADE YORK CSO; MARYGATE LANDING CSO (NO2); SKELDERGATE BRIDGE CSO"),
    ("poor_light", "Margate, Kent", "E01024657",
     "MARGATE HEADWORKS; ST MILDRED'S BAY CSO; MARINE TERRACE C S O"),
    ("poor_light", "north Coventry (Holbrooks)", "E01009709",
     "COVENTRY - NUNTS LANE (CSO); HOLBROOKS - WHITMORE PARK ROAD (CSO)"),
    ("poor_light", "Edmonton, north London", "E01001510",
     "DEEPHAMS WASTEWATER TREATMENT WORKS; Chingford Storm Tanks"),
]

with open(os.path.join(HERE, "counterexample_cards.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["card_type", "place_label", "anchor_lsoa_code", "anchor_lsoa_name",
                "local_authority", "imd_decile_2019", "urban_ruc2011",
                "overflows_within_5km", "spills_within_5km_2025",
                "hours_within_5km_2025", "top_site_name", "top_site_spills",
                "top_site_hours", "evidence_sites",
                "anchor_easting", "anchor_northing"])
    for ctype, label, code, evidence in CARDS:
        n_over, spills, hours, top = card(code)
        x, y = pwc[code]
        w.writerow([ctype, label, code, lsoa_name[code], lsoa_la[code],
                    imd_decile[code], 1 if is_urban(code) else 0,
                    n_over, spills, round(hours, 1),
                    top[0], top[1], top[2], evidence,
                    round(x, 1), round(y, 1)])
        print(f"card {label:30s} {code} d{imd_decile[code]:<2d} "
              f"overflows={n_over:3d} spills={spills:5d} hours={hours:8.1f}")
