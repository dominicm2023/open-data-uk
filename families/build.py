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
import os
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
API_ROWS = 50_000


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
    s = str(v).strip().replace(",", "").lstrip("£$€ ").replace("£", "")
    if s in ("", "-", "n/a", "N/A", "NA", "null", "None"):
        return None
    # accounting style: "(2,586.20)" is a credit of 2,586.20 (TfGM's returns)
    m_paren = re.fullmatch(r"\((\s*-?\d+(?:\.\d+)?)\s*\)", s)
    if m_paren:
        return -abs(float(m_paren.group(1)))
    m = re.fullmatch(r"-?\d+(?:\.\d+)?", s)
    if not m:
        # "<0.5" or "12 µg/m3" carry a number; "08-MAY-2024" does not
        m2 = re.fullmatch(r"(<|>)?\s*(-?\d+(?:\.\d+)?)(?:(?:\s+|[^\w\s.-]).*)?", s)
        return float(m2.group(2)) if m2 else None
    return float(s)


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%y", "%d/%m/%y %H:%M", "%d %B %Y", "%d %b %Y",
                 "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d/%b/%y", "%d-%B-%Y", "%d.%m.%Y", "%Y%m%d")
_US_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%m/%d/%Y %H:%M", "%m-%d-%Y")


def _date(v, us: bool = False):
    """An ISO date from what a body wrote: '15-Dec-11', '11-MAR-2026',
    '10/01/2014 00:00', an Excel serial number. Day comes before month
    unless the file as a whole says otherwise (see _us_dates)."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 10**11:
        # an ArcGIS epoch in milliseconds
        from datetime import datetime as _dt, timezone as _tz
        try:
            return _dt.fromtimestamp(v / 1000, tz=_tz.utc).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return None
    if isinstance(v, (int, float)) and 20000 <= v <= 70000:
        # an Excel serial: days since 1899-12-30
        from datetime import date, timedelta
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    s = re.sub(r"\s+", " ", str(v)).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}", s) and 20000 <= int(s) <= 70000:
        from datetime import date, timedelta
        return (date(1899, 12, 30) + timedelta(days=int(s))).isoformat()
    for fmt in (_US_FORMATS + _DATE_FORMATS) if us else _DATE_FORMATS:
        try:
            return datetime.strptime(s[:len(fmt) + 6 if "%B" in fmt else len(s)], fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", s)      # "2023/04/05 00:00:00+00" and the like
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if re.fullmatch(r"\d{12,13}", s):
        return _date(int(s))
    return None


def _us_dates(values) -> bool:
    """Does this file write month before day? Only a value like 3/13/2013
    can say so; a file with any of those, and none the other way round,
    is read month-first throughout — including its ambiguous 3/4/2013s,
    which the row-by-row parser would otherwise get silently wrong."""
    first_big = second_big = 0
    for v in values:
        m = re.match(r"\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", str(v or ""))
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12:
            first_big += 1
        if b > 12:
            second_big += 1
    return second_big > 0 and first_big == 0


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
        try:
            o, b = _map_file(job, f, spec, schema)
        except (KeyError, IndexError, ValueError) as err:
            # One file of a series in a layout the mapping does not know is
            # held, with its reason; the other files still publish.
            bad.append({"why": f"file {f.get('name') or f['url'][-50:]}: {str(err)[:120]}", "source_row": None,
                        "source_url": f["url"]})
            continue
        out += o
        bad += b
    return out, bad


def _norm(x) -> str:
    return re.sub(r"\s+", " ", str(x)).strip().lower()


def _fits(rows: list, candidates: list, h: int) -> list[tuple[int, int, dict]]:
    """Every (hits, header_row, layout) whose names the header carries well
    enough, best first. Names are compared stripped and case-folded, because
    publishers' trailing spaces are not information."""
    fits = []
    for hr in range(0, min(max(h, 0) + 4, len(rows))):     # a sibling file may lack the title row
        lowered = [_norm(c) for c in rows[hr]]
        for order, lay in enumerate(candidates):
            names = [_norm(v) for v in lay.values()]
            hits = sum(1 for n in names if n in lowered)
            if lay and hits >= max(2, int(0.6 * len(lay))):
                fits.append((hits, hr, order, lay))
    fits.sort(key=lambda t: (-t[0], t[2], t[1]))
    return [(hits, hr, lay) for hits, hr, order, lay in fits]


def _map_file(job: dict, f: dict, spec: dict, schema: dict) -> tuple[list[dict], list[dict]]:
    rows = _load_table(f["extraction_sha"], spec.get("table", 1))
    h = spec.get("header_row", 0)
    # A series' files do not all share a layout: Greenwich's returns gained
    # a "Payment Date" column one year. The mapping's own columns and its
    # alt_columns are each a layout; the header row of this file chooses
    # between them by how many of a layout's names it carries. The header
    # may also sit on a later row than declared when a file has a title
    # line the first one did not.
    candidates = [spec.get("columns", {})] + list(spec.get("alt_columns", []))
    fits = _fits(rows, candidates, h)
    if not fits:
        raise KeyError(f"no known layout fits the header {[str(x)[:18] for x in rows[h][:8]]}")
    hits, hr, lay = fits[0]
    out, bad = _map_rows(job, f, spec, schema, rows, lay, hr)
    held = sum(1 for b in bad if b.get("source_row") is not None)
    if held > len(out) and len(fits) > 1:
        # The header named a layout the cells do not follow (Wirral's
        # December 2025 return lists a date column its rows do not carry).
        # Only then do the other fitting layouts get a turn, and the one
        # that publishes the most rows wins; its rows say how they were read.
        for _, hr2, lay2 in fits[1:]:
            if lay2 is lay and hr2 == hr:
                continue
            try:
                o2, b2 = _map_rows(job, f, spec, schema, rows, lay2, hr2)
            except (KeyError, IndexError, ValueError):
                continue
            if len(o2) > len(out):
                note = "layout chosen by cell contents: the header labels do not match the values beneath them"
                for r in o2:
                    r["quality_note"] = (r["quality_note"] + "; " + note) if r.get("quality_note") else note
                out, bad = o2, b2
    return out, bad


def _map_rows(job: dict, f: dict, spec: dict, schema: dict, rows: list, best: dict, h: int) -> tuple[list[dict], list[dict]]:
    header = [str(x).strip() if x is not None else "" for x in rows[h]]
    # Every header cell by position — an unpivot names year columns directly
    # — with the layout's names laid over it case-insensitively.
    idx = {name: i for i, name in enumerate(header) if name}
    lowered = [_norm(c) for c in header]
    cols = {k: str(v).strip() for k, v in best.items()}
    for src in cols.values():
        pos = next((i for i, c in enumerate(lowered) if c == _norm(src)), None)
        if pos is None:
            raise KeyError(f"source column {src!r} not in header")
        idx[src] = pos
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
    date_cols = [cols[n] for n, t in types.items() if t == "date" and n in cols and cols[n] in idx]
    us = bool(date_cols) and _us_dates(
        r[idx[dc]] for r in rows[h + 1:] for dc in date_cols if idx[dc] < len(r))
    out, bad = [], []
    skipped_headers = [0, 0, 0]        # repeated header rows, one-cell dividers, rows outside the filter
    unpivot = spec.get("unpivot")
    # A source that mixes this family with something else — York's 2 waste
    # sites among 51 bring banks, Perth's centres among points — keeps only
    # the rows whose cell in one column matches the mapping's pattern. The
    # column and pattern are the reviewer's, and the count skipped is said.
    flt = spec.get("filter")
    flt_idx = flt_re = None
    if flt:
        flt_col = str(flt["column"]).strip()
        flt_idx = next((i for i, c in enumerate(lowered) if c == _norm(flt_col)), None)
        if flt_idx is None:
            raise KeyError(f"filter column {flt_col!r} not in header")
        flt_re = re.compile(flt["match"], re.I)

    def cell(r, name):
        if name not in cols or cols[name] not in idx:
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
                base[name] = _date(val, us)
            elif typ == "boolean":
                base[name] = str(val).strip().lower() in ("true", "yes", "y", "1")
            else:
                base[name] = re.sub(r"\s+", " ", str(val)).strip() or None
        quality = []
        if us and any(base.get(n) for n, t in types.items() if t == "date"):
            quality.append("dates read month-first: the file's own unambiguous dates are written that way")
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
    # A file made by concatenating monthly returns repeats its header
    # between blocks — and a block may use a *different* layout: DFID's
    # 2012 return switches from (date, supplier, amount, type, area) to
    # (date, type, area, supplier, reference, amount) in December, under a
    # header with different names. A mapping may therefore list
    # "alt_columns": further column dicts. A row that carries most of the
    # names of any known layout is a header: switch to that layout and
    # carry on. One-cell dividers ("Apr-12") are skipped and counted.
    layouts = [cols] + [{k: str(v).strip() for k, v in alt.items()} for alt in spec.get("alt_columns", [])]

    for rno, r in enumerate(rows[h + 1:], start=h + 2):
        cells = [str(x).strip() if x is not None else "" for x in r]
        if not any(cells):
            continue
        lowered = [_norm(c) for c in cells]
        best, best_hits = None, 0
        for lay in layouts:
            names = {_norm(v) for v in lay.values()}
            hits = sum(1 for n in names if n in lowered)
            if hits > best_hits:
                best, best_hits = lay, hits
        if best is not None and best_hits >= max(2, int(0.6 * len(best))):
            cols = dict(best)
            idx = {}
            for target, src_col in cols.items():
                pos = next((i for i, c in enumerate(lowered) if c == _norm(src_col)), None)
                if pos is not None:
                    idx[src_col] = pos
            skipped_headers[0] += 1
            continue
        if sum(1 for c in cells if c) == 1 and len(header_set) > 3:
            skipped_headers[1] += 1
            continue
        # a line with nothing in any mapped column is padding, not a row
        if all(not (idx.get(src_col) is not None and idx[src_col] < len(cells) and cells[idx[src_col]])
               for src_col in cols.values()):
            continue
        if flt_re is not None and not flt_re.search(str(cells[flt_idx]) if flt_idx < len(cells) else ""):
            skipped_headers[2] += 1
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
    if skipped_headers[2]:
        bad.append({"why": f"{skipped_headers[2]} rows outside the filter {flt['column']!r} ~ /{flt['match']}/ (not this family)",
                    "source_row": None})
    return out, bad


def _facets(rows: list[dict], schema: dict) -> dict:
    """What the page draws and answers with, computed once over every
    published row: years covered per body, the distinct sites with
    coordinates, how filled each column is, and the largest values. All of
    it is a fact about this table, never about the world."""
    types = {c["name"]: c["type"] for c in schema["columns"]}
    year_col = next((c for c in ("year", "payment_date", "as_of") if c in types), None)
    years: dict = {}
    body_years: dict = {}
    filled = {c: 0 for c in types}
    sites: dict = {}
    amount = {"total": 0.0, "max": None, "negative": 0} if "amount_gbp" in types else None
    means: dict = {}
    for r in rows:
        for c in types:
            if r.get(c) not in (None, ""):
                filled[c] += 1
        y = r.get(year_col) if year_col else None
        y = str(y)[:4] if y else None
        if y and y.isdigit() and 1990 <= int(y) <= 2030:
            years[y] = years.get(y, 0) + 1
            body_years.setdefault(r.get("body") or r.get("publisher"), {})[y] =                 body_years.get(r.get("body") or r.get("publisher"), {}).get(y, 0) + 1
        if r.get("lon") is not None and r.get("lat") is not None:
            k = (round(r["lon"], 4), round(r["lat"], 4))
            if k not in sites:
                sites[k] = {"name": r.get("site_name") or r.get("site_id") or "", "body": r.get("publisher"),
                            "lon": k[0], "lat": k[1], "n": 0}
            sites[k]["n"] += 1
        if amount is not None and r.get("amount_gbp") is not None:
            a = r["amount_gbp"]
            amount["total"] += a
            if a < 0:
                amount["negative"] += 1
            if amount["max"] is None or a > amount["max"]["amount_gbp"]:
                amount["max"] = {k: r.get(k) for k in ("body", "supplier", "amount_gbp", "payment_date", "period", "description")}
        if "annual_mean" in types and r.get("annual_mean") is not None:
            pol = r.get("pollutant") or "?"
            m = means.setdefault(pol, {"n": 0, "max": None, "min": None, "sites": set(), "unit": r.get("unit")})
            m["n"] += 1
            m["sites"].add(r.get("site_id") or r.get("site_name") or (r.get("lon"), r.get("lat")))
            for key, better in (("max", lambda a, b: a > b), ("min", lambda a, b: a < b)):
                if m[key] is None or better(r["annual_mean"], m[key]["annual_mean"]):
                    m[key] = {k: r.get(k) for k in ("site_name", "site_id", "publisher", "year", "annual_mean", "unit")}
    for m in means.values():
        m["sites"] = len(m["sites"])
    site_list = sorted(sites.values(), key=lambda x: -x["n"])
    return {"year_col": year_col, "years": dict(sorted(years.items())), "body_years": body_years,
            "sites": site_list[:2500], "sites_total": len(site_list), "filled": filled,
            "amount": amount, "annual_mean": means or None}


def _write_sqlite(path: Path, schema: dict, cols: list[str], rows: list[dict]) -> None:
    """The published table as one SQLite file, so the API can answer a
    filter — this body, that year, a word in the supplier — without
    scanning a 150 MB CSV. `yr` is the year of whichever column dates the
    row, so every family filters by year the same way. Written beside the
    old file and swapped in whole: a reader never sees a half-built table."""
    sql_type = {"integer": "INTEGER", "number": "REAL", "boolean": "INTEGER"}
    types = {c["name"]: c["type"] for c in schema["columns"]}
    year_col = next((c for c in ("year", "payment_date", "as_of") if c in types), None)
    tmp = path.with_suffix(".sqlite.tmp")
    if tmp.exists():
        tmp.unlink()
    c = sqlite3.connect(tmp)
    defs = ", ".join(f'"{col}" {sql_type.get(types.get(col, "text"), "TEXT")}' for col in cols)
    c.execute(f'CREATE TABLE rows ({defs}, "yr" INTEGER)')

    def rec(r):
        y = r.get(year_col) if year_col else None
        y = str(y)[:4] if y else None
        vals = []
        for col in cols:
            v = r.get(col)
            vals.append(v if v is None or isinstance(v, (int, float, str)) else str(v))
        vals.append(int(y) if y and y.isdigit() else None)
        return vals

    c.executemany(f'INSERT INTO rows VALUES ({",".join("?" * (len(cols) + 1))})', (rec(r) for r in rows))
    for col in ("body", "publisher", "yr", "pollutant"):
        if col in cols or col == "yr":
            c.execute(f'CREATE INDEX ix_{col} ON rows("{col}")')
    c.commit()
    c.close()
    os.replace(tmp, path)


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
        # The reviewer's first question about held rows is "which files, and
        # why": tally reasons per file, not the first five in file order.
        tally: dict = {}
        for b in bad:
            if b["why"].startswith("skipped "):
                continue
            k = (b.get("source_file") or b.get("source_url") or "", b["why"][:80])
            tally[k] = tally.get(k, 0) + 1
        entry["failures_sample"] = [b["why"] for b in bad[:5]]
        entry["held_by_file"] = [{"file": (k[0] or "")[-60:], "why": k[1], "rows": n}
                                 for k, n in sorted(tally.items(), key=lambda kv: -kv[1])[:8]]
        entry["notes"] = spec.get("notes")
        # the body as the table names it: two of a council's datasets can
        # arrive under two publisher spellings and must count as one body
        entry["body"] = (spec.get("constants") or {}).get("body") or job["publisher"]
        lic = json.loads(job["licence_json"]) if job["licence_json"] else {}
        if lic.get("mixed") or lic.get("basis"):
            # what the licence statement said besides the OGL, and what a
            # portal-level decision rests on: on the page, beside the body
            entry["licence_note"] = ((f"the statement also mentions {', '.join(lic['mixed'])}" if lic.get("mixed") else "")
                                     + ("; " if lic.get("mixed") and lic.get("basis") else "")
                                     + (lic.get("basis") or ""))
        if lic.get("os_acknowledgement"):
            entry["os_acknowledgement"] = lic["os_acknowledgement"]
        if spec.get("status") == "reviewed":
            entry["ladder"] = "published"; published += ok
        else:
            entry["ladder"] = "mapped (proposed)"
            if include_proposed:
                preview += ok
        summary.append(entry)
    out_dir = STORE / "out" / family
    out_dir.mkdir(parents=True, exist_ok=True)
    # A build that publishes far fewer rows than the last one is more likely
    # a bug than a fact — one such drop hid behind a green "0 preview rows"
    # line on 6 Sep — so it is said out loud and recorded, never silent.
    prev_path = out_dir / "summary.json"
    prev_rows = None
    if prev_path.exists():
        try:
            prev_rows = json.loads(prev_path.read_text(encoding="utf-8")).get("published_rows")
        except (ValueError, OSError):
            prev_rows = None
    regression = None
    if prev_rows and len(published) < 0.8 * prev_rows:
        regression = f"published rows fell from {prev_rows:,} to {len(published):,}"
        print(f"WARNING {family}: {regression}", file=sys.stderr, flush=True)
    cols = list(dict.fromkeys(
        [c["name"] for c in schema["columns"]] + schema["provenance"] + ["source_file", "source_row", "quality_note"]))
    for name, rows in (("published", published), ("preview", preview)):
        with (out_dir / f"{family}.{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
        # The complete table lives in the CSV. The JSON twin is capped: a
        # 588,000-row family made a 584 MB file that nothing read whole.
        (out_dir / f"{family}.{name}.json").write_text(json.dumps(rows[:API_ROWS], ensure_ascii=False), encoding="utf-8")
    _write_sqlite(out_dir / f"{family}.sqlite", schema, cols, published)
    ladder = {}
    for e in summary:
        ladder[e["ladder"]] = ladder.get(e["ladder"], 0) + 1
    report = {"family": family, "label": schema["label"], "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "published_rows": len(published), "preview_rows": len(preview), "ladder": ladder,
              "previous_published_rows": prev_rows, "regression": regression,
              "publishers_published": sorted({r["publisher"] for r in published}),
              "licences": sorted({r["licence_id"] for r in published}), "sources": summary,
              "facets": _facets(published, schema)}
    (out_dir / "summary.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    # The API payload, written once here so the server streams a file
    # rather than re-serialising a 12 MB table on every request.
    # JSON carries the first API_ROWS rows; a family can run to half a
    # million lines, and the complete table is the CSV.
    api = {"family": family, "label": schema["label"], "built_at": report["built_at"],
           "rows_total": len(published), "rows_in_this_response": min(len(published), API_ROWS),
           "complete_table_csv": f"/api/family/{family}.csv",
           "rows": published[:API_ROWS], "sources": summary,
           "attribution": "Contains public sector information licensed under the Open Government Licence v3.0 "
                          "and other licences as stated per row. Combined by the UK Open Data Index."}
    (out_dir / f"{family}.api.json").write_text(json.dumps(api, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("family")
    ap.add_argument("--include-proposed", action="store_true")
    a = ap.parse_args()
    r = build(a.family, a.include_proposed)
    print(f"{a.family}: {r['published_rows']} published rows from {len(r['publishers_published'])} publishers; "
          f"{r['preview_rows']} preview rows; ladder {r['ladder']}")
