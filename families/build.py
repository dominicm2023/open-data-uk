"""Turn reviewed mappings into one combined table per family, with receipts.

Reads families/registry/<family>.mappings.json — one entry per intake job:

    "<job_id>": {
      "status": "proposed" | "reviewed" | "rejected",
      "reject": "why, if rejected",
      "table": 1 | "<sheet name>",        which extracted table holds the data
      "header_row": 0,                    index of the header row in it
      "columns": {"site_name": "Site Name", "postcode": "Post Code", ...},
      "constants": {"threshold_gbp": 500},
      "unpivot": {"year_columns": ["2019", "2020"], "key_to": "year", "value_to": "annual_mean",
                  "id_columns": {"site_id": "Site"}},
      "notes": "anything a reviewer must know",
      "reviewer": "name", "reviewed_at": "date"
    }

Only "reviewed" entries publish. "proposed" entries are built too, into a
separate preview, so a reviewer can see what publishing them would mean.

Every output row carries its receipts: publisher, dataset key, source URL
and SHA-256, table and row, licence id/url, licence evidence hash and kind,
adapter version. Validation is per schema (postcode regex, coordinate and
value ranges); a row that fails is not dropped silently — it goes to the
summary with its reason, and the source is held.

British National Grid eastings/northings are converted to WGS84 here so a
family can take either; the conversion is the standard OSGB36 → Helmert →
WGS84 chain and is accurate to a few metres, which is more than a recycling
centre needs and is recorded as coords_source = "bng_converted".

Usage:  DATA_DIR=... python families/build.py recycling_centres [--include-proposed]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paths import DATA_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
STORE = DATA_DIR / "families"
ADAPTER = "columns-v1"


# --- British National Grid -> WGS84 ------------------------------------------

def bng_to_wgs84(E: float, N: float) -> tuple[float, float]:
    """OSGB36 grid to WGS84 lon/lat. Airy 1830 inverse projection, then a
    7-parameter Helmert transformation. Good to ~5 m across Great Britain."""
    a, b = 6377563.396, 6356256.909
    F0, lat0, lon0 = 0.9996012717, math.radians(49), math.radians(-2)
    N0, E0 = -100000, 400000
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)
    lat, M = lat0, 0.0
    while True:
        lat = (N - N0 - M) / (a * F0) + lat
        Ma = (1 + n + 1.25 * n ** 2 + 1.25 * n ** 3) * (lat - lat0)
        Mb = (3 * n + 3 * n ** 2 + 2.625 * n ** 3) * math.sin(lat - lat0) * math.cos(lat + lat0)
        Mc = (1.875 * n ** 2 + 1.875 * n ** 3) * math.sin(2 * (lat - lat0)) * math.cos(2 * (lat + lat0))
        Md = (35 / 24) * n ** 3 * math.sin(3 * (lat - lat0)) * math.cos(3 * (lat + lat0))
        M = b * F0 * (Ma - Mb + Mc - Md)
        if abs(N - N0 - M) < 0.00001:
            break
    s, c, t = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = a * F0 / math.sqrt(1 - e2 * s * s)
    rho = a * F0 * (1 - e2) / (1 - e2 * s * s) ** 1.5
    eta2 = nu / rho - 1
    VII = t / (2 * rho * nu)
    VIII = t / (24 * rho * nu ** 3) * (5 + 3 * t ** 2 + eta2 - 9 * t ** 2 * eta2)
    IX = t / (720 * rho * nu ** 5) * (61 + 90 * t ** 2 + 45 * t ** 4)
    X = 1 / (c * nu)
    XI = 1 / (c * 6 * nu ** 3) * (nu / rho + 2 * t ** 2)
    XII = 1 / (c * 120 * nu ** 5) * (5 + 28 * t ** 2 + 24 * t ** 4)
    XIIA = 1 / (c * 5040 * nu ** 7) * (61 + 662 * t ** 2 + 1320 * t ** 4 + 720 * t ** 6)
    dE = E - E0
    lat_o = lat - VII * dE ** 2 + VIII * dE ** 4 - IX * dE ** 6
    lon_o = lon0 + X * dE - XI * dE ** 3 + XII * dE ** 5 - XIIA * dE ** 7
    # OSGB36 -> WGS84 Helmert
    H = 0.0
    sin_lat, cos_lat, sin_lon, cos_lon = math.sin(lat_o), math.cos(lat_o), math.sin(lon_o), math.cos(lon_o)
    nu = a / math.sqrt(1 - e2 * sin_lat ** 2)
    x = (nu + H) * cos_lat * cos_lon
    y = (nu + H) * cos_lat * sin_lon
    z = ((1 - e2) * nu + H) * sin_lat
    tx, ty, tz = 446.448, -125.157, 542.060
    rx, ry, rz = [math.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421)]
    sc = 1 + (-20.4894 / 1e6)
    x2 = tx + sc * x - rz * y + ry * z
    y2 = ty + rz * x + sc * y - rx * z
    z2 = tz - ry * x + rx * y + sc * z
    a2, b2 = 6378137.000, 6356752.3142
    e2b = 1 - (b2 * b2) / (a2 * a2)
    p = math.sqrt(x2 * x2 + y2 * y2)
    lat2 = math.atan2(z2, p * (1 - e2b))
    for _ in range(10):
        nu2 = a2 / math.sqrt(1 - e2b * math.sin(lat2) ** 2)
        lat2 = math.atan2(z2 + e2b * nu2 * math.sin(lat2), p)
    lon2 = math.atan2(y2, x2)
    return round(math.degrees(lon2), 6), round(math.degrees(lat2), 6)


def irish_to_wgs84(E: float, N: float) -> tuple[float, float]:
    """Irish Grid (TM75) to WGS84 lon/lat. Airy Modified inverse projection,
    then the Ireland 1965 Helmert transformation. Good to a few metres.
    Northern Ireland councils publish eastings/northings on this grid, not
    on British National Grid; the same six-digit numbers converted as BNG
    land in the North Sea."""
    a, b = 6377340.189, 6356034.447
    F0, lat0, lon0 = 1.000035, math.radians(53.5), math.radians(-8)
    N0, E0 = 250000, 200000
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)
    lat, M = lat0, 0.0
    while True:
        lat = (N - N0 - M) / (a * F0) + lat
        Ma = (1 + n + 1.25 * n ** 2 + 1.25 * n ** 3) * (lat - lat0)
        Mb = (3 * n + 3 * n ** 2 + 2.625 * n ** 3) * math.sin(lat - lat0) * math.cos(lat + lat0)
        Mc = (1.875 * n ** 2 + 1.875 * n ** 3) * math.sin(2 * (lat - lat0)) * math.cos(2 * (lat + lat0))
        Md = (35 / 24) * n ** 3 * math.sin(3 * (lat - lat0)) * math.cos(3 * (lat + lat0))
        M = b * F0 * (Ma - Mb + Mc - Md)
        if abs(N - N0 - M) < 0.00001:
            break
    s_, c, t = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = a * F0 / math.sqrt(1 - e2 * s_ * s_)
    rho = a * F0 * (1 - e2) / (1 - e2 * s_ * s_) ** 1.5
    eta2 = nu / rho - 1
    VII = t / (2 * rho * nu)
    VIII = t / (24 * rho * nu ** 3) * (5 + 3 * t ** 2 + eta2 - 9 * t ** 2 * eta2)
    IX = t / (720 * rho * nu ** 5) * (61 + 90 * t ** 2 + 45 * t ** 4)
    X = 1 / (c * nu)
    XI = 1 / (c * 6 * nu ** 3) * (nu / rho + 2 * t ** 2)
    XII = 1 / (c * 120 * nu ** 5) * (5 + 28 * t ** 2 + 24 * t ** 4)
    XIIA = 1 / (c * 5040 * nu ** 7) * (61 + 662 * t ** 2 + 1320 * t ** 4 + 720 * t ** 6)
    dE = E - E0
    lat_o = lat - VII * dE ** 2 + VIII * dE ** 4 - IX * dE ** 6
    lon_o = lon0 + X * dE - XI * dE ** 3 + XII * dE ** 5 - XIIA * dE ** 7
    # Ireland 1965 -> WGS84 Helmert (OSNI/OSi published parameters)
    sin_lat, cos_lat, sin_lon, cos_lon = math.sin(lat_o), math.cos(lat_o), math.sin(lon_o), math.cos(lon_o)
    nu = a / math.sqrt(1 - e2 * sin_lat ** 2)
    x = nu * cos_lat * cos_lon
    y = nu * cos_lat * sin_lon
    z = (1 - e2) * nu * sin_lat
    tx, ty, tz = 482.530, -130.596, 564.557
    rx, ry, rz = [math.radians(v / 3600) for v in (-1.042, -0.214, -0.631)]
    sc = 1 + (8.150 / 1e6)
    x2 = tx + sc * x - rz * y + ry * z
    y2 = ty + rz * x + sc * y - rx * z
    z2 = tz - ry * x + rx * y + sc * z
    a2, b2 = 6378137.000, 6356752.3142
    e2b = 1 - (b2 * b2) / (a2 * a2)
    pr = math.sqrt(x2 * x2 + y2 * y2)
    lat2 = math.atan2(z2, pr * (1 - e2b))
    for _ in range(10):
        nu2 = a2 / math.sqrt(1 - e2b * math.sin(lat2) ** 2)
        lat2 = math.atan2(z2 + e2b * nu2 * math.sin(lat2), pr)
    lon2 = math.atan2(y2, x2)
    return round(math.degrees(lon2), 6), round(math.degrees(lat2), 6)


def itm_to_wgs84(E: float, N: float) -> tuple[float, float]:
    """Irish Transverse Mercator (EPSG:2157) to WGS84. GRS80 on ETRS89, so no
    datum shift is needed; a straight inverse transverse Mercator. Eastings
    run from about 400,000 upward, which is how it is told apart from the
    older Irish Grid whose eastings never reach that."""
    a, f = 6378137.0, 1 / 298.257222101
    k0, lat0, lon0, E0, N0 = 0.99982, math.radians(53.5), math.radians(-8), 600000.0, 750000.0
    b = a * (1 - f)
    e2 = 1 - (b * b) / (a * a)
    n = (a - b) / (a + b)
    lat, M = lat0, 0.0
    while True:
        lat = (N - N0 - M) / (a * k0) + lat
        Ma = (1 + n + 1.25 * n ** 2 + 1.25 * n ** 3) * (lat - lat0)
        Mb = (3 * n + 3 * n ** 2 + 2.625 * n ** 3) * math.sin(lat - lat0) * math.cos(lat + lat0)
        Mc = (1.875 * n ** 2 + 1.875 * n ** 3) * math.sin(2 * (lat - lat0)) * math.cos(2 * (lat + lat0))
        Md = (35 / 24) * n ** 3 * math.sin(3 * (lat - lat0)) * math.cos(3 * (lat + lat0))
        M = b * k0 * (Ma - Mb + Mc - Md)
        if abs(N - N0 - M) < 0.00001:
            break
    s_, c, t = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = a * k0 / math.sqrt(1 - e2 * s_ * s_)
    rho = a * k0 * (1 - e2) / (1 - e2 * s_ * s_) ** 1.5
    eta2 = nu / rho - 1
    VII = t / (2 * rho * nu)
    VIII = t / (24 * rho * nu ** 3) * (5 + 3 * t ** 2 + eta2 - 9 * t ** 2 * eta2)
    IX = t / (720 * rho * nu ** 5) * (61 + 90 * t ** 2 + 45 * t ** 4)
    X = 1 / (c * nu)
    XI = 1 / (c * 6 * nu ** 3) * (nu / rho + 2 * t ** 2)
    XII = 1 / (c * 120 * nu ** 5) * (5 + 28 * t ** 2 + 24 * t ** 4)
    XIIA = 1 / (c * 5040 * nu ** 7) * (61 + 662 * t ** 2 + 1320 * t ** 4 + 720 * t ** 6)
    dE = E - E0
    lat_o = lat - VII * dE ** 2 + VIII * dE ** 4 - IX * dE ** 6
    lon_o = lon0 + X * dE - XI * dE ** 3 + XII * dE ** 5 - XIIA * dE ** 7
    return round(math.degrees(lon_o), 6), round(math.degrees(lat_o), 6)


# --- helpers -----------------------------------------------------------------

def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("£", "")
    if s in ("", "-", "n/a", "N/A", "NA", "null", "None"):
        return None
    m = re.fullmatch(r"-?\d+(?:\.\d+)?", s)
    if not m:
        m2 = re.match(r"(<|>)?\s*(-?\d+(?:\.\d+)?)", s)
        return float(m2.group(2)) if m2 else None
    return float(s)


def _date(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%y", "%d %B %Y", "%d %b %Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:len(fmt) + 6 if "%B" in fmt else len(s)], fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)} " .strip() if m else None


def _postcode(v):
    if not v:
        return None
    s = re.sub(r"\s+", "", str(v).upper())
    if len(s) < 5:
        return None
    return s[:-3] + " " + s[-3:]


def _load_table(extraction_sha: str, which) -> list[list]:
    doc = json.loads((STORE / "tables" / extraction_sha).read_text(encoding="utf-8"))
    for t in doc["tables"]:
        if which in (t.get("table"), t.get("sheet")):
            return t["rows"]
    if isinstance(which, int) and 0 < which <= len(doc["tables"]):
        return doc["tables"][which - 1]["rows"]
    raise KeyError(f"table {which!r} not in extraction")


def _validate(row: dict, schema: dict) -> str | None:
    v = schema.get("validation", {})
    types = {c["name"]: c["type"] for c in schema["columns"]}
    for c in schema["columns"]:
        if c["required"] and row.get(c["name"]) in (None, ""):
            return f"missing required {c['name']}"
    if "postcode_regex" in v and row.get("postcode") and not re.fullmatch(v["postcode_regex"], row["postcode"]):
        return f"postcode fails pattern: {row['postcode']!r}"
    for key, rng in (("lat", v.get("lat_range")), ("lon", v.get("lon_range")),
                     ("annual_mean", v.get("annual_mean_range"))):
        if rng and row.get(key) is not None and not (rng[0] <= row[key] <= rng[1]):
            return f"{key} out of range: {row[key]}"
    if "year_range" in v and row.get("year") is not None and not (v["year_range"][0] <= row["year"] <= v["year_range"][1]):
        return f"year out of range: {row['year']}"
    if "amount_abs_max" in v and row.get("amount_gbp") is not None and abs(row["amount_gbp"]) > v["amount_abs_max"]:
        return f"amount implausible: {row['amount_gbp']}"
    for name, typ in types.items():
        val = row.get(name)
        if val is None:
            continue
        if typ in ("number", "integer") and not isinstance(val, (int, float)):
            return f"{name} not numeric: {val!r}"
    return None


# --- the mapping ----------------------------------------------------------------

def map_source(job: dict, spec: dict, schema: dict) -> tuple[list[dict], list[dict]]:
    """Every extracted file of the job, through the same mapping."""
    out, bad = [], []
    files = job.get("files") or [{"extraction_sha": job["extraction_sha"], "blob_sha": job["blob_sha"],
                                  "url": job["resource_url"], "name": ""}]
    for f in files:
        o, b = _map_file(job, f, spec, schema)
        out += o
        bad += b
    return out, bad


def _map_file(job: dict, f: dict, spec: dict, schema: dict) -> tuple[list[dict], list[dict]]:
    rows = _load_table(f["extraction_sha"], spec.get("table", 1))
    h = spec.get("header_row", 0)
    header = [str(x).strip() if x is not None else "" for x in rows[h]]
    idx = {name: i for i, name in enumerate(header)}
    # Mappings quote headers exactly as the brief showed them, which may
    # carry a publisher's trailing space; the table's headers are stripped
    # above. Meet in the middle.
    cols = {k: str(v).strip() for k, v in spec.get("columns", {}).items()}
    for src in cols.values():
        if src not in idx:
            raise KeyError(f"source column {src!r} not in header")
    licence = json.loads(job["licence_json"])
    receipts = {
        "publisher": job["publisher"], "dataset_key": job["dataset_key"], "source_url": f["url"],
        "source_sha256": f["blob_sha"], "source_table": str(spec.get("table", 1)),
        "source_file": f.get("name") or "",
        "licence_id": licence["id"], "licence_url": licence["url"],
        "licence_evidence_sha256": job["evidence_sha"], "licence_evidence_kind": job["licence_kind"],
        "adapter_version": ADAPTER + ":" + (spec.get("version") or "1"),
    }
    types = {c["name"]: c["type"] for c in schema["columns"]}
    out, bad = [], []
    skipped_headers = [0, 0]           # repeated header rows, one-cell dividers
    unpivot = spec.get("unpivot")

    def cell(r, name):
        if name not in cols:
            return None
        i = idx[cols[name]]
        return r[i] if i < len(r) else None

    def finish(base: dict, r: list, rno: int):
        # coordinates: WGS84 given, else BNG converted, else none
        if "lon" in types and "lat" in types:
            if base.get("lon") is None and base.get("lat") is None and "easting" in cols and "northing" in cols:
                e, n = _num(r[idx[cols["easting"]]]), _num(r[idx[cols["northing"]]])
                if e is not None and n is not None and 0 < e < 800000 and 0 < n < 1400000:
                    if spec.get("grid") == "irish":
                        # Two Irish grids share six-digit numbers; the easting
                        # tells them apart (TM75 stays below ~370,000).
                        if e >= 400000:
                            base["lon"], base["lat"] = itm_to_wgs84(e, n)
                            base["coords_source"] = "itm_converted"
                        else:
                            base["lon"], base["lat"] = irish_to_wgs84(e, n)
                            base["coords_source"] = "irish_grid_converted"
                    else:
                        base["lon"], base["lat"] = bng_to_wgs84(e, n)
                        base["coords_source"] = "bng_converted"
            elif base.get("lon") is not None:
                base["coords_source"] = "wgs84"
            else:
                base["coords_source"] = "none"
        for k, v in spec.get("constants", {}).items():
            base[k] = v
        # "2010/2011" in a year column is a reporting period, not a year.
        # Keep the first year and say so, rather than lose the row or guess.
        if "year" in types and isinstance(base.get("year"), str):
            m = re.match(r"\s*((?:19|20)\d{2})\s*[/–-]\s*(?:19|20)?\d{2}\s*$", base["year"])
            if m:
                q = f"reporting period {base['year'].strip()}"
                base["qualifier"] = (base.get("qualifier") + "; " + q) if base.get("qualifier") else q
                base["year"] = m.group(1)
        for name, typ in types.items():
            val = base.get(name)
            if val is None or val == "":
                base[name] = None
            elif typ in ("number",):
                base[name] = _num(val)
            elif typ == "integer":
                nv = _num(val)
                base[name] = int(nv) if nv is not None else None
            elif typ == "date":
                base[name] = _date(val)
            elif typ == "boolean":
                base[name] = str(val).strip().lower() in ("true", "yes", "y", "1")
            else:
                base[name] = str(val).strip() or None
        quality = []
        if "postcode" in types:
            raw_pc = base.get("postcode")
            base["postcode"] = _postcode(raw_pc)
            pat = schema.get("validation", {}).get("postcode_regex")
            if base["postcode"] and pat and not re.fullmatch(pat, base["postcode"]):
                # The publisher's own typo. The site is still real; the
                # postcode is not, so it goes and the row says why.
                quality.append(f"postcode {str(raw_pc).strip()!r} fails the UK pattern; nulled")
                base["postcode"] = None
        # A published annual mean of exactly zero is a placeholder for a year
        # not yet measured (Camden fills future columns with 0.00), never an
        # observation. The schema names which columns that rule applies to.
        for name in schema.get("validation", {}).get("zero_is_missing", []):
            if base.get(name) == 0:
                bad.append({**base, **receipts, "source_row": rno, "why": f"{name} is 0: placeholder, not an observation"})
                return
        why = _validate(base, schema)
        rec = {**base, **receipts, "source_row": rno, "quality_note": "; ".join(quality) or None}
        (bad if why else out).append({**rec, "why": why} if why else rec)

    header_set = [x.strip().lower() for x in header]
    for rno, r in enumerate(rows[h + 1:], start=h + 2):
        cells = [str(x).strip() if x is not None else "" for x in r]
        if not any(cells):
            continue
        # A file made by concatenating monthly returns repeats its header
        # between blocks and drops a one-cell divider ("Apr-12") before
        # each. Neither is a payment; both are skipped, and counted.
        if [c.lower() for c in cells[:len(header_set)]] == header_set:
            skipped_headers[0] += 1
            continue
        if sum(1 for c in cells if c) == 1 and len(header_set) > 3:
            skipped_headers[1] += 1
            continue
        if unpivot:
            base_ids = {k: cell(r, k) if k in cols else (r[idx[v]] if v in idx else None)
                        for k, v in unpivot.get("id_columns", {}).items()}
            for yc in unpivot["year_columns"]:
                if yc not in idx:
                    continue
                val = r[idx[yc]] if idx[yc] < len(r) else None
                if _num(val) is None:
                    continue                       # a blank cell is no observation
                base = {name: cell(r, name) for name in types}
                base.update(base_ids)
                base[unpivot["key_to"]] = int(re.search(r"(19|20)\d{2}", yc).group(0)) if re.search(r"(19|20)\d{2}", yc) else None
                base[unpivot["value_to"]] = val
                finish(base, r, rno)
        else:
            base = {name: cell(r, name) for name in types}
            finish(base, r, rno)
    if skipped_headers[0] or skipped_headers[1]:
        bad.append({"why": f"skipped {skipped_headers[0]} repeated header rows and {skipped_headers[1]} divider rows (not payments)",
                    "source_row": None})
    return out, bad


def build(family: str, include_proposed: bool = False) -> dict:
    schema = json.loads((HERE / "schema" / f"{family}.json").read_text(encoding="utf-8"))
    mp = HERE / "registry" / f"{family}.mappings.json"
    mappings = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    c = sqlite3.connect(f"file:{STORE / 'families.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    jobs = {j["id"]: dict(j) for j in c.execute("SELECT * FROM jobs WHERE family=?", (family,))}
    try:
        for f in c.execute("SELECT * FROM files WHERE state='extracted' ORDER BY name, url"):
            if f["job_id"] in jobs:
                jobs[f["job_id"]].setdefault("files", []).append(dict(f))
    except sqlite3.OperationalError:
        pass
    c.close()
    published, preview, summary = [], [], []
    for jid, job in sorted(jobs.items(), key=lambda kv: (kv[1]["publisher"] or "", kv[0])):
        spec = mappings.get(jid)
        entry = {"publisher": job["publisher"], "title": job["title"], "dataset_key": job["dataset_key"],
                 "portal": job["portal"], "format": job["format"], "licence_kind": job["licence_kind"],
                 "licence": json.loads(job["licence_json"])["id"] if job["licence_json"] else None,
                 "intake_state": job["state"], "intake_detail": job["detail"],
                 "resource_url": job["resource_url"], "landing_url": None}
        if job["state"] != "needs_review":
            entry["ladder"] = "not admitted" if job["state"] == "not_admitted" else "fetch failed" if job["state"] == "fetch_failed" else job["state"]
            summary.append(entry); continue
        if not spec:
            entry["ladder"] = "extracted"; summary.append(entry); continue
        if spec.get("status") == "rejected":
            entry["ladder"] = "rejected"; entry["why"] = spec.get("reject"); summary.append(entry); continue
        try:
            ok, bad = map_source(job, spec, schema)
        except (KeyError, IndexError, ValueError) as err:
            entry["ladder"] = "mapping failed"; entry["why"] = str(err)[:200]; summary.append(entry); continue
        entry["rows"] = len(ok); entry["rows_failed_validation"] = len(bad)
        entry["files"] = len(job.get("files") or [])
        entry["failures_sample"] = [b["why"] for b in bad[:5]]
        entry["notes"] = spec.get("notes")
        if spec.get("status") == "reviewed":
            entry["ladder"] = "published"; published += ok
        else:
            entry["ladder"] = "mapped (proposed)"
            if include_proposed:
                preview += ok
        summary.append(entry)
    out_dir = STORE / "out" / family
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = [c["name"] for c in schema["columns"]] + schema["provenance"] + ["source_file", "source_row", "quality_note"]
    for name, rows in (("published", published), ("preview", preview)):
        with (out_dir / f"{family}.{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        (out_dir / f"{family}.{name}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    ladder = {}
    for e in summary:
        ladder[e["ladder"]] = ladder.get(e["ladder"], 0) + 1
    report = {"family": family, "label": schema["label"], "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "published_rows": len(published), "preview_rows": len(preview), "ladder": ladder,
              "publishers_published": sorted({r["publisher"] for r in published}),
              "licences": sorted({r["licence_id"] for r in published}), "sources": summary}
    (out_dir / "summary.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("family")
    ap.add_argument("--include-proposed", action="store_true")
    a = ap.parse_args()
    r = build(a.family, a.include_proposed)
    print(f"{a.family}: {r['published_rows']} published rows from {len(r['publishers_published'])} publishers; "
          f"{r['preview_rows']} preview rows; ladder {r['ladder']}")
