"""Parse the RO workbooks into ro.sqlite: tidy rows per authority-service-measure.

Three measures per service line, because net-only comparisons mislead:
  gross   Total Expenditure (C3 = C1 + C2)
  income  Total Income (C6 = C4 + C5)  - sales, fees, charges + other income
  nce     Net Current Expenditure (C7 = C3 - C6)
A district that recovers waste costs through garden-bin charges shows tiny
NET spend while running a normal-size service (Rugby 2024-25: gross 2.25m,
income 1.76m, net 0.49m) - so the dispersion claims are made on gross, with
net shown as the charging-policy story.

Vintage layouts (all verified by inspection, header rows 0-based):
  RSX 2024-25  ODS  flat header row 6, 'Service - Measure' column names;
               E-code, ONS Code, Class, Detailed Class.
  RSX 2018-19  ODS  service names row 4 (ffill), measures row 6, data row 7+;
               E-code, ONS Code, Class.
  RSX 2013-14  XLS  service row 5, measures row 7, data row 8+; E-code and
               Class but NO ONS code - filled from the E-code -> ONS map
               taken from 2018-19 (no reorganisation in between).
  RO5          detail lines (libraries, waste); 2013-14 splits measures over
               three sheets: (1) C1-C3, (2) C4-C6, (3) C7-C9.
  RS           financing + reserves; 2013-14 flows on sheet (1), year-end
               (31 March 2014) reserve levels on sheet (2).

Everything is pounds thousand, as stated on each workbook's front page.
Row filter: E-code must match ^E\\d{4}$ (drops England, class totals,
footnotes); duplicate E-codes dropped (the 2024-25 CLASS BREAKDOWN block
repeats the GLA with its real E-code). Class 'L' normalised to 'LB'.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RAW = HERE / "raw"
DB = HERE / "ro.sqlite"

ECODE = re.compile(r"^E\d{4}$")

MEASURES = {  # header token -> measure name
    "Total Expenditure (C3": "gross",
    "Total Income (C6": "income",
    "Net Current Expenditure (C7": "nce",
}

SERVICE_NORM = {
    "education services": "education",
    "highways and transport services": "highways_transport",
    "children social care": "children_social_care",
    "children's social care": "children_social_care",
    "adult social care": "adult_social_care",
    "public health": "public_health",
    "housing services (gfra only)": "housing_gfra",
    "cultural and related services": "cultural",
    "environmental and regulatory services": "environmental_regulatory",
    "planning and development services": "planning_development",
    "police services": "police",
    "fire and rescue services": "fire_rescue",
    "central services": "central",
    "other services": "other",
    "total service expenditure": "total_service_expenditure",
}

RO5_WANT = {
    "library service": "libraries",
    "waste collection": "waste_collection",
    "waste disposal": "waste_disposal",
    "recycling": "recycling",
    "street cleansing (not chargeable to highways)": "street_cleansing",
    # statutory planning-application handling; every district does exactly
    # this job, unlike the broad planning_development RSX block
    "development control": "development_control",
}

provenance: list[dict] = []


def norm_class(c: str) -> str:
    c = str(c).strip()
    return "LB" if c == "L" else c


def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["ecode"].astype(str).str.match(ECODE)]
    df = df.drop_duplicates(subset="ecode").copy()
    df["cls"] = df["cls"].map(norm_class)
    return df


def measure_of(header: str) -> str | None:
    for token, m in MEASURES.items():
        if token in header:
            return m
    return None


def melt(df: pd.DataFrame, found: list[tuple[str, str, int, str]],
         values: pd.DataFrame, year: str, f: str, sheet: str) -> pd.DataFrame:
    """found: (service, measure, column index, header text)."""
    out = []
    for svc, meas, col, header in found:
        sub = df[["ecode", "ons_code", "name", "cls"]].copy()
        sub["year"] = year
        sub["service"] = svc
        sub["measure"] = meas
        sub["gbp_thousand"] = pd.to_numeric(values.iloc[df.index, col],
                                            errors="coerce")
        out.append(sub)
        provenance.append({"year": year, "service": svc, "measure": meas,
                           "file": f, "sheet": sheet,
                           "column_index_0based": col,
                           "column_header": header[:120]})
    return pd.concat(out, ignore_index=True)


def find_blocks(svc_row: pd.Series, col_row: pd.Series,
                norm: dict[str, str]) -> list[tuple[str, str, int, str]]:
    """Two-level headers: service names in svc_row (ffilled), measures below."""
    found, seen = [], set()
    for i in range(len(col_row)):
        meas = measure_of(str(col_row.iloc[i]))
        if meas is None or pd.isna(svc_row.iloc[i]):
            continue
        raw_name = re.sub(r"\*+", "", str(svc_row.iloc[i])).strip()
        svc = norm.get(raw_name.lower())
        if svc is None or (svc, meas) in seen:
            continue
        seen.add((svc, meas))
        found.append((svc, meas, i, f"{raw_name} | {str(col_row.iloc[i]).strip()}"))
    return found


def find_flat(col_row: pd.Series, norm: dict[str, str]) -> list[tuple[str, str, int, str]]:
    """Flat 'Service - Measure' headers (2024-25 workbooks)."""
    found, seen = [], set()
    for i in range(len(col_row)):
        c = str(col_row.iloc[i]).strip()
        m = re.match(r"^(.*?) - (Total Expenditure \(C3|Total Income \(C6|"
                     r"Net Current Expenditure \(C7)", c)
        if not m:
            continue
        svc = norm.get(m.group(1).strip().lower())
        meas = measure_of(c)
        if svc is None or meas is None or (svc, meas) in seen:
            continue
        seen.add((svc, meas))
        found.append((svc, meas, i, c))
    return found


def parse_flat(f: str, sheet: str, year: str, norm: dict[str, str]) -> pd.DataFrame:
    raw = pd.read_excel(RAW / f, engine="odf", sheet_name=sheet, header=None)
    cols = raw.iloc[6]
    body = raw.iloc[7:].reset_index(drop=True)
    named = {str(c).strip(): i for i, c in enumerate(cols)}
    df = clean_rows(pd.DataFrame({
        "ecode": body[named["E-code"]], "ons_code": body[named["ONS Code"]],
        "name": body[named["Local authority"]], "cls": body[named["Class"]]}))
    return melt(df, find_flat(cols, norm), body, year, f, sheet)


def parse_two_level(f: str, sheet: str, year: str, norm: dict[str, str],
                    svc_row: int, hdr_row: int,
                    col_map: dict[str, int], engine: str | None = "odf") -> pd.DataFrame:
    kw = {"engine": engine} if engine else {}
    raw = pd.read_excel(RAW / f, sheet_name=sheet, header=None, **kw)
    svc = raw.iloc[svc_row].ffill()
    cols = raw.iloc[hdr_row]
    body = raw.iloc[hdr_row + 1:].reset_index(drop=True)
    df = pd.DataFrame({k: body[v] for k, v in col_map.items()})
    if "ons_code" not in df:
        df["ons_code"] = None
    df = clean_rows(df)
    return melt(df, find_blocks(svc, cols, norm), body, year, f, sheet)


# ---------------------------------------------------------------- RS summaries
RS_PATTERNS = [
    ("net_revenue_expenditure", "net revenue expenditure"),
    ("council_tax_requirement", "council tax requirement"),
    ("reserves_other_earmarked", "other earmarked financial reserves level"),
    ("reserves_unallocated", "unallocated financial reserves level"),
]


def parse_rs(f: str, sheet: str, year: str, hdr_row: int, engine: str | None,
             col_map: dict[str, int]) -> pd.DataFrame:
    kw = {"engine": engine} if engine else {}
    raw = pd.read_excel(RAW / f, sheet_name=sheet, header=None, **kw)
    cols = raw.iloc[hdr_row]
    body = raw.iloc[hdr_row + 1:].reset_index(drop=True)
    df = pd.DataFrame({k: body[v] for k, v in col_map.items()})
    if "ons_code" not in df:
        df["ons_code"] = None
    df = clean_rows(df)
    got = {}
    for i in range(len(cols)):
        c = re.sub(r"\s+", " ", str(cols.iloc[i])).strip().lower()
        if "1 april" in c or "appropriation" in c or "sub component" in c:
            continue
        for field, want in RS_PATTERNS:
            if want in c and field not in got:
                got[field] = i
                provenance.append({"year": year, "service": f"rs:{field}",
                                   "measure": "rs_line", "file": f,
                                   "sheet": sheet, "column_index_0based": i,
                                   "column_header": str(cols.iloc[i]).strip()[:120]})
    out = df[["ecode", "ons_code", "name", "cls"]].copy()
    out["year"] = year
    for field, i in got.items():
        out[field] = pd.to_numeric(body.iloc[df.index, i], errors="coerce")
    return out


def main() -> None:
    frames = []
    print("RSX 2024-25 ...")
    frames.append(parse_flat("RSX_2024-25.ods", "RSX_LA_Data_202425",
                             "2024-25", SERVICE_NORM))
    print("RSX 2018-19 ...")
    frames.append(parse_two_level("RSX_2018-19.ods", "RSX_LA_Data_2018-19",
                                  "2018-19", SERVICE_NORM, 4, 6,
                                  {"ecode": 0, "ons_code": 1, "name": 2, "cls": 4}))
    print("RSX 2013-14 ...")
    frames.append(parse_two_level("RSX_2013-14.xls", "RSX LA Data 2013-14",
                                  "2013-14", SERVICE_NORM, 5, 7,
                                  {"ecode": 0, "name": 1, "cls": 3}, engine=None))
    print("RO5 2024-25 ...")
    frames.append(parse_flat("RO5_2024-25.ods", "RO5_LA_Data_202425",
                             "2024-25", RO5_WANT))
    print("RO5 2018-19 ...")
    frames.append(parse_two_level("RO5_2018-19.ods", "RO5_LA_Data_2018-19",
                                  "2018-19", RO5_WANT, 4, 6,
                                  {"ecode": 0, "ons_code": 1, "name": 2, "cls": 4}))
    print("RO5 2013-14 (three sheets) ...")
    for n in (1, 2, 3):
        frames.append(parse_two_level("RO5_2013-14.xls",
                                      f"RO5 LA Data 2013-14 ({n})",
                                      "2013-14", RO5_WANT, 10, 12,
                                      {"ecode": 0, "name": 1, "cls": 3},
                                      engine=None))
    spend = pd.concat(frames, ignore_index=True)

    # Known MHCLG typo: RSX 2018-19 gives North Yorkshire (E2721) the code
    # E10000022; ONS and the RO5 workbook of the same year say E10000023.
    spend.loc[(spend.ecode == "E2721") & (spend.ons_code == "E10000022"),
              "ons_code"] = "E10000023"

    emap = (spend[spend.year == "2018-19"][["ecode", "ons_code"]]
            .dropna().drop_duplicates().set_index("ecode")["ons_code"])
    assert emap.index.is_unique, "conflicting E-code -> ONS mappings"
    mask = spend.ons_code.isna()
    spend.loc[mask, "ons_code"] = spend.loc[mask, "ecode"].map(emap)

    print("RS 2024-25 / 2018-19 / 2013-14 ...")
    rs13_flows = parse_rs("RS_2013-14.xls", "RS LA Data 2013-14 (1)", "2013-14",
                          5, None, {"ecode": 0, "name": 1, "cls": 3})
    rs13_lvls = parse_rs("RS_2013-14.xls", "RS LA Data 2013-14 (2)", "2013-14",
                         5, None, {"ecode": 0, "name": 1, "cls": 3})
    rs13 = rs13_flows[["ecode", "ons_code", "name", "cls", "year",
                       "net_revenue_expenditure", "council_tax_requirement"]].merge(
        rs13_lvls[["ecode", "reserves_other_earmarked", "reserves_unallocated"]],
        on="ecode", how="left")
    rs = pd.concat([
        parse_rs("RS_2024-25.ods", "RS_LA_Data_202425", "2024-25", 6, "odf",
                 {"ecode": 0, "ons_code": 1, "name": 2, "cls": 4}),
        parse_rs("RS_2018-19.ods", "RS_LA_Data_2018-19", "2018-19", 6, "odf",
                 {"ecode": 0, "ons_code": 1, "name": 2, "cls": 4}),
        rs13,
    ], ignore_index=True)
    mask = rs.ons_code.isna()
    rs.loc[mask, "ons_code"] = rs.loc[mask, "ecode"].map(emap)

    # Population -----------------------------------------------------------
    pops = []
    for level in ("upper", "lower"):
        p = pd.read_csv(RAW / f"pop_{level}_2024.csv")
        p = p.rename(columns={"GEOGRAPHY_CODE": "ons_code",
                              "GEOGRAPHY_NAME": "pop_name",
                              "OBS_VALUE": "population"})
        p["year"] = "2024-25"
        pops.append(p[["year", "ons_code", "pop_name", "population"]])
    # Mid-2018 on 2018 boundaries, mid-2013 on 2013 boundaries: archived ONS
    # reference tables - nomis deletes back-series for abolished geographies.
    m18 = pd.read_excel(RAW / "ukmidyearestimates20182018ladcodes.xls",
                        sheet_name="MYE2 - All", header=4)
    m18 = m18.rename(columns={"Code": "ons_code", "Name": "pop_name",
                              "All ages": "population"})
    m18["year"] = "2018-19"
    m18["population"] = pd.to_numeric(m18["population"], errors="coerce")
    pops.append(m18[["year", "ons_code", "pop_name", "population"]]
                .dropna(subset=["ons_code", "population"]))
    import io
    import zipfile
    z = zipfile.ZipFile(RAW / "ukmye2013.zip")
    mye = pd.read_excel(io.BytesIO(
        z.read("MYE2_population_by_sex_and_age_for_local_authorities_UK.xls")),
        sheet_name="UK persons", header=2)
    mye = mye.rename(columns={"CODE": "ons_code", "NAME": "pop_name",
                              "ALL AGES": "population"})
    mye["year"] = "2013-14"
    mye["population"] = pd.to_numeric(mye["population"], errors="coerce")
    pops.append(mye[["year", "ons_code", "pop_name", "population"]]
                .dropna(subset=["ons_code", "population"]))
    pop = pd.concat(pops, ignore_index=True).drop_duplicates(["year", "ons_code"])

    # Deflator -------------------------------------------------------------
    defl_raw = pd.read_excel(RAW / "gdp_deflator_jun2026.xlsx", header=None)
    defl_rows = []
    for _, row in defl_raw.iterrows():
        fy, idx = row[1], row[2]
        if isinstance(fy, str) and re.match(r"^\d{4}-\d{2}$", fy.strip()) and pd.notna(idx):
            defl_rows.append({"year": fy.strip(), "deflator": float(idx)})
    defl = pd.DataFrame(defl_rows)

    # Write ----------------------------------------------------------------
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    spend.to_sql("service_nce", con, index=False)
    rs.to_sql("rs_summary", con, index=False)
    pop.to_sql("population", con, index=False)
    defl.to_sql("deflator", con, index=False)
    con.commit()
    (HERE / "provenance.json").write_text(json.dumps(provenance, indent=2))

    # Reconciliation gate: authority-row sums vs each workbook's England
    # row for Total Service Expenditure (nce). 2024-25 tolerates the
    # Cumberland gap: no return submitted, authority row blank, MHCLG's
    # England row carries an unpublished imputation for it.
    ENGLAND_TSE = {
        "2013-14": (91_808_865.0, 1.0),
        "2018-19": (91_416_761.43, 1.0),
        "2024-25": (134_233_179.34, 600_000.0),
    }
    nce = spend[spend.measure == "nce"]
    for y, (val, tol) in ENGLAND_TSE.items():
        ours = nce[(nce.year == y) &
                   (nce.service == "total_service_expenditure")].gbp_thousand.sum()
        assert abs(ours - val) <= tol, f"{y}: {ours} vs England row {val}"
        print(f"reconciled {y}: sum {ours:,.0f} vs England row {val:,.0f} "
              f"(diff {ours-val:+,.0f} k)")

    for y in ("2013-14", "2018-19", "2024-25"):
        s = nce[(nce.year == y) & (nce.service == "total_service_expenditure")]
        merged = s.merge(pop[pop.year == y], on=["year", "ons_code"], how="left")
        main_cls = merged[merged.cls.isin(["SD", "UA", "MD", "LB", "SC"])]
        print(f"{y}: {len(s)} authorities, {len(main_cls)} principal, "
              f"{main_cls.population.notna().sum()} with population, "
              f"{main_cls.cls.value_counts().to_dict()}")
    con.close()


if __name__ == "__main__":
    main()
