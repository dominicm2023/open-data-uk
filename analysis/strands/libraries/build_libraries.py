"""THE LIBRARY LOTTERY - chart-ready data build.

Substrate: analysis/ro/ro_per_head.csv (MHCLG Revenue Outturn, RO5 library
service line, parsed by analysis/ro/03_parse.py; per-head via ONS mid-year
population on period-correct boundaries; real terms via HMT GDP deflator,
2024-25 prices). This script only reshapes that substrate - no new numbers
are invented here.

Tier rule: libraries are an upper-tier/unitary duty. Library-responsible
classes are LB (London borough), MD (met district), UA (unitary), SC (shire
county). Shire districts (SD) are never included. Every output row states
its class, and no table mixes classes.

Outputs (all in this directory):
  league_2024-25_LB.csv / _MD.csv / _UA.csv / _SC.csv  - within-class
      league, net AND gross per head + income share, artefact notes
  callout_kc_vs_bd.csv       - two-bar callout, K&C vs Barking & Dagenham
  arc_class_real.csv         - per-class real per-head arc, three vintages
  slope_authorities.csv      - per-authority slope 2013-14 -> 2024-25
  slope_excluded.csv         - authorities dropped from the census, and why
  map_2024-25.csv            - latest net per head for map/hex colouring
  build_log.txt              - recomputed headline figures (census, ratios)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
SRC = HERE.parent.parent / "ro" / "ro_per_head.csv"

LIB_CLASSES = ["LB", "MD", "UA", "SC"]
CLASS_LABEL = {"LB": "London borough", "MD": "Metropolitan district",
               "UA": "Unitary authority", "SC": "Shire county"}
FREAKS = {"E09000001": "City of London", "E06000053": "Isles of Scilly"}

# Known artefacts from the hand-check graveyard (analysis/ro/REPORT.md,
# findings.json hand_check_queue_killed). Annotated, never silently ranked.
# Matched on name prefix because RO names carry suffixes ("Blackpool UA").
GRAVEYARD = {
    "Blackpool": ("ARTEFACT: booked income (2,606k) exceeds gross spend "
                  "(2,402k); net line is negative. Do not rank on net."),
    "Enfield": ("CAUTION: income is ~47% of gross - low net is partly a "
                "charging/income artefact, not service size."),
    "Sunderland": ("CAUTION: culture delivered via trust; the library line "
                   "may understate the library share of the trust grant."),
}


def graveyard_note(name: str) -> str | None:
    for key, note in GRAVEYARD.items():
        if name.startswith(key):
            return note
    return None

log: list[str] = []

df = pd.read_csv(SRC)
lib = df[(df.service == "libraries") & df.cls.isin(LIB_CLASSES)].copy()
log.append(f"library rows loaded: {len(lib)} "
           f"(measures: {sorted(lib.measure.unique())})")

# Authorities whose 2013-14 real base was under 2 pounds/head: the line was
# outsourced/misbooked back then (Wigan 0.00, Luton 0.01 - trust booking),
# so their levels deserve a caution wherever they appear.
nce = lib[lib.measure == "nce"]
_base = nce[(nce.year == "2013-14") & nce.gbp_thousand.notna()]
LOW_BASE = set(_base[_base.real_gbp_per_head < 2].ons_code)

# ---------------------------------------------------------------- (a) leagues
cur = lib[(lib.year == "2024-25") & lib.gbp_thousand.notna()]
wide = (cur.pivot_table(index=["ons_code", "ecode", "name", "cls",
                               "population"],
                        columns="measure", values="gbp_per_head")
        .reset_index()
        .rename(columns={"nce": "net_gbp_per_head",
                         "gross": "gross_gbp_per_head",
                         "income": "income_gbp_per_head"}))
wide["income_share_of_gross_pct"] = (
    100 * wide.income_gbp_per_head / wide.gross_gbp_per_head).round(1)


def note_for(row) -> str:
    notes = []
    gy = graveyard_note(row["name"])
    if gy:
        notes.append(gy)
    elif row["income_share_of_gross_pct"] >= 40:
        notes.append("CAUTION: income >= 40% of gross - net reflects "
                     "charging/recharges as much as service size.")
    if row["ons_code"] in LOW_BASE:
        notes.append("CAUTION: 2013-14 library line was under 2 pounds/head "
                     "real (trust/outsourced booking) - booked level may "
                     "not capture full service cost.")
    if row["ons_code"] in FREAKS:
        notes.append("Excluded from rankings project-wide (structurally "
                     "unrepresentative per-head base).")
    return " ".join(notes)


wide["note"] = wide.apply(note_for, axis=1)
wide["class_label"] = wide.cls.map(CLASS_LABEL)

for cls in LIB_CLASSES:
    t = wide[(wide.cls == cls) & ~wide.ons_code.isin(FREAKS)].copy()
    t = t.sort_values("net_gbp_per_head", ascending=False)
    t["rank_net"] = range(1, len(t) + 1)
    cols = ["rank_net", "ons_code", "ecode", "name", "cls", "class_label",
            "net_gbp_per_head", "gross_gbp_per_head", "income_gbp_per_head",
            "income_share_of_gross_pct", "population", "note"]
    t = t[cols].round({"net_gbp_per_head": 2, "gross_gbp_per_head": 2,
                       "income_gbp_per_head": 2})
    t.to_csv(HERE / f"league_2024-25_{cls}.csv", index=False)
    named = t[t.note == ""]
    log.append(
        f"league {cls}: n={len(t)} (clean n={len(named)}); "
        f"net max {t.net_gbp_per_head.max():.2f} ({t.iloc[0]['name']}), "
        f"net min {t.net_gbp_per_head.min():.2f} "
        f"({t.iloc[-1]['name']}), median {t.net_gbp_per_head.median():.2f}")

# ---------------------------------------------------------------- (b) callout
pair = wide[wide.name.isin(["Kensington & Chelsea", "Kensington and Chelsea",
                            "Barking & Dagenham", "Barking and Dagenham"])]
assert len(pair) == 2, f"callout pair match failed: {pair.name.tolist()}"
rows = []
for _, r in pair.iterrows():
    rows.append({"authority": r["name"], "ons_code": r.ons_code,
                 "cls": r.cls, "class_label": CLASS_LABEL[r.cls],
                 "measure": "net", "gbp_per_head": round(r.net_gbp_per_head, 2)})
    rows.append({"authority": r["name"], "ons_code": r.ons_code,
                 "cls": r.cls, "class_label": CLASS_LABEL[r.cls],
                 "measure": "gross",
                 "gbp_per_head": round(r.gross_gbp_per_head, 2)})
callout = pd.DataFrame(rows)
callout.to_csv(HERE / "callout_kc_vs_bd.csv", index=False)
kc = pair[pair.name.str.startswith("Kensington")].iloc[0]
bd = pair[pair.name.str.startswith("Barking")].iloc[0]
log.append(f"callout: K&C net {kc.net_gbp_per_head:.2f} vs B&D "
           f"{bd.net_gbp_per_head:.2f} -> "
           f"{kc.net_gbp_per_head / bd.net_gbp_per_head:.1f}x; gross "
           f"{kc.gross_gbp_per_head:.2f} vs {bd.gross_gbp_per_head:.2f} -> "
           f"{kc.gross_gbp_per_head / bd.gross_gbp_per_head:.1f}x")

# ------------------------------------------------------------ (c) class arc
# Aggregate real cash over every class member that filed (Cumberland 2024-25
# filed no return: its cash AND its population are both excluded, so the
# per-head stays internally consistent). Freaks stay in class sums, as in
# the England arc. NOTE: class composition changes across the window - LGR
# moved county+district areas into the UA class (and shrank SC); LB and MD
# are stable classes. Stated in notes.md.
REAL = {}
for y in ("2013-14", "2018-19", "2024-25"):
    d = nce[(nce.year == y) & nce.gbp_thousand.notna()
            & (nce.gbp_per_head != 0)]
    ratio = (d.real_gbp_per_head / d.gbp_per_head).round(4).mode()
    REAL[y] = float(ratio.iloc[0])
log.append(f"deflator factors recovered from substrate: {REAL}")

arc_rows = []
for cls in LIB_CLASSES:
    for y in ("2013-14", "2018-19", "2024-25"):
        d = nce[(nce.year == y) & (nce.cls == cls) & nce.gbp_thousand.notna()]
        cash = d.gbp_thousand.sum() * 1000
        popn = d.population.sum()
        arc_rows.append({
            "cls": cls, "class_label": CLASS_LABEL[cls], "year": y,
            "real_gbp_per_head": round(cash * REAL[y] / popn, 2),
            "n_authorities": len(d), "population_used": int(popn)})
arc = pd.DataFrame(arc_rows)
arc.to_csv(HERE / "arc_class_real.csv", index=False)
for cls in LIB_CLASSES:
    a = arc[arc.cls == cls].set_index("year")["real_gbp_per_head"]
    log.append(f"arc {cls}: {a['2013-14']:.2f} -> {a['2018-19']:.2f} -> "
               f"{a['2024-25']:.2f} "
               f"({100 * (a['2024-25'] / a['2013-14'] - 1):.1f}%)")

# ------------------------------------------- (c) per-authority slope + census
# Reproduces analysis/ro/04_analyse.py exactly: stable ons_code across both
# end years, library-responsible classes, freaks out; guards: 2013-14 base
# >= 2 pounds/head real (below that the line is outsourced/misbooked, not a
# service), 2024-25 > 0 (Blackpool's negative net is an income artefact).
piv = (nce.pivot_table(index=["ons_code", "name", "cls"], columns="year",
                       values="real_gbp_per_head").reset_index())
piv = piv.dropna(subset=["2013-14", "2024-25"])
piv = piv[~piv.ons_code.isin(FREAKS)]
guard_base = piv["2013-14"] < 2
guard_neg = piv["2024-25"] <= 0
excl = piv[guard_base | guard_neg].copy()
excl["reason"] = ""
excl.loc[guard_base, "reason"] = ("2013-14 base under 2 pounds/head real - "
                                  "line not credible (outsourced/misbooked)")
excl.loc[guard_neg, "reason"] = ("2024-25 net non-positive - booked income "
                                 "exceeds spend (income artefact)")
census = piv[~(guard_base | guard_neg)].copy()
census["change_pct"] = (100 * (census["2024-25"] / census["2013-14"] - 1))
census = census.sort_values("change_pct")
census["class_label"] = census.cls.map(CLASS_LABEL)
census["note"] = census.name.map(lambda n: graveyard_note(n) or "")
out = census.rename(columns={"2013-14": "real_2013_14",
                             "2018-19": "real_2018_19",
                             "2024-25": "real_2024_25"})
out = out[["ons_code", "name", "cls", "class_label", "real_2013_14",
           "real_2018_19", "real_2024_25", "change_pct", "note"]].round(
    {"real_2013_14": 2, "real_2018_19": 2, "real_2024_25": 2,
     "change_pct": 1})
out.to_csv(HERE / "slope_authorities.csv", index=False)
excl = excl.rename(columns={"2013-14": "real_2013_14",
                            "2018-19": "real_2018_19",
                            "2024-25": "real_2024_25"})
excl[["ons_code", "name", "cls", "real_2013_14", "real_2018_19",
      "real_2024_25", "reason"]].round(2).to_csv(
    HERE / "slope_excluded.csv", index=False)
n, fell = len(census), int((census.change_pct < 0).sum())
log.append(f"census recomputed: n={n}, fell={fell}, "
           f"median change {census.change_pct.median():.1f}% "
           f"(excluded: {len(excl)} -> {excl.name.tolist()})")
log.append("deepest cuts: " + "; ".join(
    f"{r['name']} ({r.cls}) {r.change_pct:.0f}%"
    for _, r in census.head(5).iterrows()))
log.append("grew: " + "; ".join(
    f"{r['name']} ({r.cls}) +{r.change_pct:.0f}%"
    for _, r in census.tail(5).iterrows()))

# ----------------------------------------------------------------- (d) map
mp = wide.copy()
mp["value"] = mp.net_gbp_per_head.round(2)
mp = mp.sort_values(["cls", "name"])
mp[["ons_code", "name", "cls", "class_label", "value", "note"]].to_csv(
    HERE / "map_2024-25.csv", index=False)
log.append(f"map rows: {len(mp)} across classes "
           f"{mp.cls.value_counts().to_dict()}; "
           f"negative values: {mp[mp.value < 0].name.tolist()}")

(HERE / "build_log.txt").write_text("\n".join(log), encoding="utf-8")
print("\n".join(log))
