"""Fetch a UK coastline once, simplify it, and vendor it into the repo.

The maps had no land under them, so a hundred circles sat in blank space with
nothing to read them against. A real coastline fixes that, and the question is
only where it comes from.

Not from a tile server. MapLibre and friends need external JavaScript and a
stream of tile requests to somebody else's host, which would break two things
this project has promised: the About page says the site makes no third-party
requests, and every graphic is built to survive being saved and reposted with
its provenance band intact. A chart that needs a network to draw itself is not
self-contained.

So the geometry is fetched here, once, simplified hard, and committed as
`coastline.json` — a few hundred points per nation in plain lon/lat. It is
Ordnance Survey and ONS material under the Open Government Licence, and the
attribution travels with it in the file.

Simplification is Douglas-Peucker with a deliberately coarse tolerance. These
maps are 720px wide showing ten degrees of latitude, so roughly a kilometre
lands on a pixel; keeping more detail than that adds bytes to every page and
changes nothing anyone can see.

Usage:
    python scripts/build_coastline.py            # fetch, simplify, write
    python scripts/build_coastline.py --check    # report what is vendored
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "coastline.json"

# ONS Open Geography Portal, countries at the coarsest published generalisation
# ("BUC" — ultra generalised, clipped to the coastline). Several service names
# have been used over the years, so try them in order rather than pinning one.
CANDIDATES = [
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Countries_December_2024_Boundaries_UK_BUC/FeatureServer/0/query",
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Countries_December_2023_Boundaries_UK_BUC/FeatureServer/0/query",
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Countries_December_2022_UK_BUC/FeatureServer/0/query",
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Countries_December_2021_UK_BUC/FeatureServer/0/query",
]
PARAMS = {"where": "1=1", "outFields": "*", "outSR": "4326",
          "f": "geojson", "returnGeometry": "true"}

TOLERANCE = 0.012      # degrees; about a kilometre, which is one pixel here
MIN_RING = 12          # drop islands too small to see at this scale


def simplify(points: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas-Peucker, iterative so a long coastline cannot blow the stack."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5
        worst, worst_i = 0.0, -1
        for i in range(start + 1, end):
            px, py = points[i]
            if norm == 0:
                dist = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                dist = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if dist > worst:
                worst, worst_i = dist, i
        if worst > tol and worst_i > 0:
            keep[worst_i] = True
            stack.append((start, worst_i))
            stack.append((worst_i, end))
    return [p for p, k in zip(points, keep) if k]


def rings_of(geometry: dict) -> list[list[list[float]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return coords
    if kind == "MultiPolygon":
        return [ring for poly in coords for ring in poly]
    return []


def fetch() -> dict:
    for url in CANDIDATES:
        try:
            r = requests.get(url, params=PARAMS, headers=HEADERS, timeout=180)
            if r.status_code != 200:
                print(f"   {r.status_code} from {url.rsplit('/', 4)[-4]}")
                continue
            data = r.json()
            if data.get("features"):
                print(f"   got {len(data['features'])} features from "
                      f"{url.rsplit('/', 4)[-4]}")
                return data
        except (requests.RequestException, ValueError) as exc:
            print(f"   {type(exc).__name__} from {url.rsplit('/', 4)[-4]}")
    raise SystemExit("no ONS countries service answered; nothing written")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what is already vendored and stop")
    args = ap.parse_args()

    if args.check:
        if not OUT.exists():
            print("no coastline.json vendored")
            return 1
        data = json.loads(OUT.read_text(encoding="utf-8"))
        pts = sum(len(r) for r in data["rings"])
        print(f"{len(data['rings'])} rings, {pts:,} points, "
              f"{OUT.stat().st_size / 1024:.0f} KB")
        print(f"source: {data.get('source')}")
        return 0

    print("asking ONS Open Geography for UK country boundaries")
    raw = fetch()

    rings, before = [], 0
    for feature in raw["features"]:
        for ring in rings_of(feature.get("geometry") or {}):
            before += len(ring)
            thin = simplify([[round(x, 4), round(y, 4)] for x, y in ring],
                            TOLERANCE)
            if len(thin) >= MIN_RING:
                rings.append(thin)
    rings.sort(key=len, reverse=True)
    after = sum(len(r) for r in rings)

    OUT.write_text(json.dumps({
        "source": "Office for National Statistics / Ordnance Survey, "
                  "Countries Boundaries UK (ultra generalised), "
                  "Open Government Licence v3.0",
        "note": "Simplified with Douglas-Peucker at 0.012 degrees for drawing "
                "at 720px. Not for measurement or navigation.",
        "tolerance_degrees": TOLERANCE,
        "rings": rings,
    }, separators=(",", ":")), encoding="utf-8")

    print(f"\n{len(rings)} rings kept, {before:,} points reduced to {after:,} "
          f"({100 * after / max(before, 1):.1f}%)")
    print(f"wrote {OUT.name}, {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
