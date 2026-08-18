"""Hand-check the extremes against the raw RS workbooks before naming anyone.

Prints, for each authority of interest, the full financing block (signs
flipped to income-positive), per-head values, and the workbook's own Notes
cell, for all three vintages. Also lists every principal-class authority
with a non-zero police grant line.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RO = HERE.parent.parent / "ro"
RAW = RO / "raw"
ECODE = re.compile(r"^E\d{4}$")

con = sqlite3.connect(RO / "ro.sqlite")
pop = pd.read_sql("select * from population", con)
rs = pd.read_sql("select * from rs_summary", con)

SHEETS = [
    ("2024-25", "RS_2024-25.ods", "RS_LA_Data_202425", 6, "odf", 0, 2, 3),
    ("2018-19", "RS_2018-19.ods", "RS_LA_Data_2018-19", 6, "odf", 0, 2, 3),
    ("2013-14", "RS_2013-14.xls", "RS LA Data 2013-14 (1)", 5, None, 0, 1, 2),
]
FIELDS = {
    "revenue support grant": "rsg",
    "police grant": "police",
    "retained income from rate retention scheme": "rates_ret",
    "collection fund surplus": "cf_ct",
    "other items": "other",
    "net revenue expenditure": "nre",
    "council tax requirement": "ctr",
}

frames = {}
for year, f, sheet, hdr, engine, ecol, ncol, notecol in SHEETS:
    kw = {"engine": engine} if engine else {}
    raw = pd.read_excel(RAW / f, sheet_name=sheet, header=None, **kw)
    cols = [re.sub(r"\s+", " ", str(c)).strip().lower() for c in raw.iloc[hdr]]
    got = {}
    for i, c in enumerate(cols):
        for k, v in FIELDS.items():
            if k in c and v not in got and "1 april" not in c \
                    and "sub component" not in c and "reserves" not in c:
                got[v] = i
    body = raw.iloc[hdr + 1:]
    ecodes = body[ecol].astype(str).str.strip()
    keep = ecodes.str.match(ECODE)
    df = pd.DataFrame({"ecode": ecodes[keep],
                       "name": body.loc[keep.values, ncol].astype(str).str.strip(),
                       "note": body.loc[keep.values, notecol].astype(str)
                       .str.strip().replace("nan", "")})
    for v, i in got.items():
        sign = -1 if v in ("rsg", "police", "rates_ret", "cf_ct", "other") else 1
        df[v] = sign * pd.to_numeric(body.loc[keep.values, i], errors="coerce").values
    frames[year] = df.drop_duplicates("ecode").set_index("ecode")

emap = rs[["ecode", "ons_code", "cls"]].drop_duplicates("ecode").set_index("ecode")
popmap = {(r.year, r.ons_code): r.population for r in
          pop.itertuples() if pd.notna(r.population)}

CHECK = [
    # dependence artefacts / extremes
    "Woking BC", "Runnymede", "Mid Suffolk", "Basingstoke & Deane",
    "Malvern Hills", "Waverley", "Hyndburn BC", "Thurrock UA",
    "North Tyneside", "Harrow", "Westminster", "Gloucestershire CC",
    # league deepest
    "Watford", "Rugby", "East Hertfordshire", "Nuneaton & Bedworth",
    "Guildford", "Central Bedfordshire UA", "Cheshire West and Chester UA",
    "Lewisham", "Richmond upon Thames", "Staffordshire CC", "Surrey CC",
    "Sandwell",
    # league gainers
    "North West Leicestershire", "Harborough", "North Warwickshire",
    "Dartford", "Test Valley", "South Staffordshire", "West Berkshire UA",
    "Halton UA",
]

for year in ("2013-14", "2018-19", "2024-25"):
    df = frames[year]
    print("=" * 110)
    print(year)
    name_to_ecode = {n: e for e, n in df.name.items()}
    for want in CHECK:
        hits = [e for e, n in df.name.items()
                if n.lower().startswith(want.lower()[:12])]
        if not hits:
            print(f"  {want:<30} NOT PRESENT")
            continue
        e = hits[0]
        r = df.loc[e]
        ons = emap.ons_code.get(e)
        p = popmap.get((year, ons))
        ph = lambda v: (f"{v * 1000 / p:8.2f}/hd" if p and pd.notna(v) else "        -")
        print(f"  {r['name']:<30} {emap.cls.get(e, '?'):<3} note[{r.note:<3}] "
              f"NRE {r.nre:>10,.0f}k CTR {r.ctr:>10,.0f}k | "
              f"RSG {r.rsg:>9,.0f}k {ph(r.rsg)} | "
              f"rates {r.rates_ret:>10,.0f}k {ph(r.rates_ret)} | "
              f"other {r.other:>9,.0f}k"
              + (f" | cf_ct {r.cf_ct:>8,.0f}k" if "cf_ct" in df.columns
                 and pd.notna(r.get("cf_ct")) else ""))

print("=" * 110)
print("principal-class authorities with non-zero police grant:")
for year, df in frames.items():
    d = df.join(emap.cls)
    d = d[d.cls.isin(["SD", "SC", "UA", "MD", "LB"]) & d.police.fillna(0).ne(0)]
    for e, r in d.iterrows():
        print(f"  {year} {r['name']:<32} {r.cls} police {r.police:>9,.0f}k")
