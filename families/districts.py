"""Where the licences are, by postcode district: the shapes and the counts
behind the HMO map.

The family table carries a postcode district on every row and nothing finer:
no address, no full postcode, no coordinates. This script counts the table
by district and lays each count on the district's shape, so the map can be
a map of districts and never of doors.

The shapes are the approximate postcode boundaries for Great Britain that
Mark Longair made at mySociety from open data (NSUL and Boundary-Line),
version 5, 27 August 2021, under the Open Government Licence v3:

    Contains OS data (c) Crown copyright and database right 2020
    Contains Royal Mail data (c) Royal Mail copyright and database right 2020
    Source: Office for National Statistics licensed under the Open
    Government Licence v.3.0

    https://longair.net/blog/2021/08/23/open-data-gb-postcode-unit-boundaries

They are approximate by their maker's own account, which suits a map that
says "about here". The archive (1 GB) is not in the repository: it is
unpacked once on the box under DATA_DIR/geo/mapit, without the per-postcode
unit shapes, which this project has no use for. Great Britain only: a
register from Northern Ireland would have counts and no shape.

Written to DATA_DIR/families/out/<family>/:
  districts.geojson   every district with a count, and the other districts
                      of the same postcode areas as unfilled context
  areas.geojson       the 120 postcode areas, simplified hard: the land

Usage:  DATA_DIR=... python families/districts.py hmo_registers
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paths import DATA_DIR  # noqa: E402

STORE = DATA_DIR / "families"
GEO = DATA_DIR / "geo" / "mapit" / "gb-postcodes-v5"
ATTRIBUTION = ("Postcode boundaries: approximate, by Mark Longair at mySociety (v5, 2021), Open Government Licence v3. "
               "Contains OS data © Crown copyright and database right 2020. "
               "Contains Royal Mail data © Royal Mail copyright and database right 2020. "
               "Source: Office for National Statistics licensed under the Open Government Licence v.3.0.")
_COS = math.cos(math.radians(54.5))
DISTRICT_TOL = 0.00025      # degrees of latitude: about 28 m
AREA_TOL = 0.004            # about 450 m: the areas are land under the map, not information
_AREA_OF = re.compile(r"^[A-Z]{1,2}")


def _simplify(ring: list, tol: float) -> list:
    """Douglas-Peucker, iteratively. Longitude is scaled so the tolerance is
    the same distance east-west as north-south."""
    if len(ring) < 5:
        return ring
    pts = [(x * _COS, y) for x, y in ring]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        far, far_d = -1, tol
        for i in range(a + 1, b):
            px, py = pts[i]
            d = (abs(dy * (px - ax) - dx * (py - ay)) / norm) if norm else math.hypot(px - ax, py - ay)
            if d > far_d:
                far, far_d = i, d
        if far >= 0:
            keep[far] = True
            stack.append((a, far))
            stack.append((far, b))
    out = [ring[i] for i, k in enumerate(keep) if k]
    return out if len(out) >= 4 else ring[:4]


def _area(ring: list) -> float:
    return abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))) / 2 * _COS


def _centroid(ring: list) -> tuple[float, float]:
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if not a:
        return ring[0][0], ring[0][1]
    return cx / (3 * a), cy / (3 * a)


def shape(path: Path, tol: float) -> tuple[dict, tuple[float, float]] | None:
    """One file's geometry, simplified: every part that is more than a
    sliver beside the largest, outer rings only, five decimal places. With
    the centroid of the largest part, which is where the district is."""
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    feats = doc["features"] if doc.get("type") == "FeatureCollection" else [doc]
    polys = []
    for f in feats:
        g = f["geometry"]
        for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            if poly and len(poly[0]) >= 4:
                polys.append(poly[0])
    if not polys:
        return None
    polys.sort(key=_area, reverse=True)
    biggest = _area(polys[0])
    kept = [p for p in polys if _area(p) >= biggest * 0.02]
    rings = [[[round(x, 5), round(y, 5)] for x, y in _simplify(p, tol)] for p in kept]
    rings = [r for r in rings if len(r) >= 4]
    cx, cy = _centroid(polys[0])
    geom = ({"type": "Polygon", "coordinates": [rings[0]]} if len(rings) == 1
            else {"type": "MultiPolygon", "coordinates": [[r] for r in rings]})
    return geom, (round(cx, 5), round(cy, 5))


def counts(family: str) -> dict[str, dict]:
    """The table, counted by district. 'licences' is summed, never the rows."""
    db = STORE / "out" / family / f"{family}.sqlite"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    # the register's own page, where the council shows it: that is the link a
    # reader wants, not the address of the file
    try:
        summary = json.loads((STORE / "out" / family / "summary.json").read_text(encoding="utf-8"))
        page = {s["dataset_key"]: s.get("landing_url") for s in summary.get("sources", []) if s.get("landing_url")}
    except (OSError, ValueError):
        page = {}
    out: dict[str, dict] = {}
    # a district worked out from a street or a point, not read from a
    # published postcode (DM 2026-09-28), is counted apart so the page can say so
    has_basis = any(r[1] == "district_basis" for r in c.execute("PRAGMA table_info(rows)"))
    worked = "SUM(CASE WHEN district_basis IN ('street', 'point') THEN licences ELSE 0 END)" if has_basis else "0"
    for r in c.execute(
            "SELECT postcode_district d, council, licence_type t, SUM(licences) n, SUM(max_occupants) occ, "
            "SUM(CASE WHEN max_occupants IS NOT NULL THEN licences ELSE 0 END) occ_of, MAX(as_of) as_of, "
            f"MIN(source_url) url, MIN(dataset_key) dk, {worked} w FROM rows GROUP BY 1, 2, 3"):
        e = out.setdefault(r["d"], {"licences": 0, "occupants": 0, "occupants_of": 0, "councils": {}, "types": {}})
        n = int(r["n"] or 0)
        e["licences"] += n
        e["occupants"] += int(r["occ"] or 0)
        e["occupants_of"] += int(r["occ_of"] or 0)
        k = e["councils"].setdefault(r["council"], {"licences": 0, "worked_out": 0, "as_of": None, "source_url": page.get(r["dk"]) or r["url"]})
        k["licences"] += n
        k["worked_out"] += int(r["w"] or 0)
        k["as_of"] = max(filter(None, [k["as_of"], r["as_of"]]), default=None)
        e["types"][r["t"] or "not stated"] = e["types"].get(r["t"] or "not stated", 0) + n
    return out


def build(family: str) -> dict:
    out_dir = STORE / "out" / family
    by = counts(family)
    if not GEO.is_dir():
        print(f"{family}: no boundaries under {GEO}; the map has nothing to draw", file=sys.stderr)
        return {"districts": 0}
    areas = sorted({_AREA_OF.match(d).group(0) for d in by if _AREA_OF.match(d)})
    feats, missing = [], []
    for d in sorted(by):
        got = shape(GEO / "districts" / f"{d}.geojson", DISTRICT_TOL)
        if got is None:
            missing.append(d)
            continue
        e = by[d]
        feats.append({"type": "Feature", "geometry": got[0], "properties": {
            "district": d, "licences": e["licences"], "lon": got[1][0], "lat": got[1][1],
            "occupants": e["occupants"], "occupants_of": e["occupants_of"],
            # MapLibre hands properties back as strings when they are objects: say so by encoding them here
            "councils": json.dumps([{"council": k, **v} for k, v in sorted(e["councils"].items(), key=lambda kv: -kv[1]["licences"])]),
            "types": json.dumps(sorted(e["types"].items(), key=lambda kv: -kv[1])),
        }})
    context = 0
    for p in sorted((GEO / "districts").glob("*.geojson")):
        d = p.stem
        m = _AREA_OF.match(d)
        if d in by or not m or m.group(0) not in areas:
            continue
        got = shape(p, DISTRICT_TOL * 2)
        if got:
            feats.append({"type": "Feature", "geometry": got[0], "properties": {"district": d, "licences": 0, "context": True}})
            context += 1
    worked_out = sum(k.get("worked_out", 0) for e in by.values() for k in e["councils"].values())
    import place
    attribution = ATTRIBUTION + (" " + place.ATTRIBUTION if worked_out else "")
    doc = {"type": "FeatureCollection", "attribution": attribution, "features": feats,
           "districts_without_a_shape": missing}
    (out_dir / "districts.geojson").write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    land = []
    for p in sorted((GEO / "areas").glob("*.geojson")):
        got = shape(p, AREA_TOL)
        if got:
            land.append({"type": "Feature", "geometry": got[0], "properties": {"area": p.stem}})
    (out_dir / "areas.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "attribution": ATTRIBUTION, "features": land},
                   separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return {"districts": len(by) - len(missing), "context": context, "areas": len(land), "missing": missing,
            "licences": sum(e["licences"] for e in by.values())}


def main() -> int:
    for fam in sys.argv[1:] or ["hmo_registers"]:
        r = build(fam)
        print(f"{fam}: {r.get('districts')} districts with {r.get('licences', 0):,} licences drawn, "
              f"{r.get('context', 0)} beside them for context, {r.get('areas', 0)} areas of land"
              + (f"; no shape for {', '.join(r['missing'])}" if r.get("missing") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
