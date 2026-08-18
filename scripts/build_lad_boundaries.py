"""Fetch UK local-authority district boundaries once, simplify, vendor them.

Same reasoning as build_coastline.py: choropleths need land under the numbers,
and the site promises no third-party requests at view time, so the geometry is
fetched here once from the ONS Open Geography portal, simplified hard, and
committed as `lad_boundaries.json` with its licence and attribution inside.

The source is the Local Authority Districts (December 2024) Boundaries UK BUC
layer — "BUC" is the coarsest published generalisation (ultra generalised,
clipped to the coastline), which is the right starting point because the maps
are 720px wide: at that scale roughly a kilometre lands on a pixel.

Simplification is the same iterative Douglas-Peucker as the coastline, at a
slightly finer tolerance (0.008 degrees) because district boundaries carry the
meaning here — two adjacent districts must stay visually distinct. Every
feature keeps at least its largest ring, so no authority vanishes (the Isles
of Scilly stay on the map).

Usage:
    python scripts/build_lad_boundaries.py            # fetch, simplify, write
    python scripts/build_lad_boundaries.py --check    # report what is vendored
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "lad_boundaries.json"

# ONS Open Geography Portal. Service names drift between vintages, so try a
# few, newest first, rather than pinning one.
CANDIDATES = [
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_December_2024_Boundaries_UK_BUC/FeatureServer/0/query",
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "LAD_Dec_2024_Boundaries_UK_BUC/FeatureServer/0/query",
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_May_2024_Boundaries_UK_BUC/FeatureServer/0/query",
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Local_Authority_Districts_December_2023_Boundaries_UK_BUC/FeatureServer/0/query",
]
PARAMS = {"where": "1=1", "outFields": "*", "outSR": "4326",
          "f": "geojson", "returnGeometry": "true"}

TOLERANCE = 0.008      # degrees; finer than the coastline because borders matter
MIN_RING = 10          # drop islets too small to see, but never a whole feature


def simplify(points: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas-Peucker, iterative so a long boundary cannot blow the stack."""
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


def fetch() -> list[dict]:
    """Fetch every feature, following resultOffset paging politely."""
    for url in CANDIDATES:
        features: list[dict] = []
        offset = 0
        try:
            while True:
                params = dict(PARAMS, resultOffset=offset)
                r = requests.get(url, params=params, headers=HEADERS,
                                 timeout=180)
                if r.status_code != 200:
                    print(f"   {r.status_code} from {url.rsplit('/', 4)[-4]}")
                    features = []
                    break
                data = r.json()
                page = data.get("features") or []
                if not page and not features:
                    break                       # dead service name
                features.extend(page)
                print(f"   page at offset {offset}: {len(page)} features")
                if data.get("properties", {}).get("exceededTransferLimit") \
                        or data.get("exceededTransferLimit"):
                    offset += len(page)
                    time.sleep(0.5)             # 2 req/s, politely
                    continue
                break
        except (requests.RequestException, ValueError) as exc:
            print(f"   {type(exc).__name__} from {url.rsplit('/', 4)[-4]}")
            features = []
        if features:
            print(f"   got {len(features)} features from "
                  f"{url.rsplit('/', 4)[-4]}")
            return features
    raise SystemExit("no ONS LAD service answered; nothing written")


def code_fields(props: dict) -> tuple[str, str]:
    """Find the LADyyCD / LADyyNM field names, whatever the vintage."""
    for key in props:
        m = re.fullmatch(r"(LAD\d\d)CD", key)
        if m and f"{m.group(1)}NM" in props:
            return key, f"{m.group(1)}NM"
    raise SystemExit(f"no LADyyCD field among {sorted(props)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what is already vendored and stop")
    args = ap.parse_args()

    if args.check:
        if not OUT.exists():
            print("no lad_boundaries.json vendored")
            return 1
        data = json.loads(OUT.read_text(encoding="utf-8"))
        pts = sum(len(r) for f in data["features"] for r in f["rings"])
        print(f"{len(data['features'])} authorities, {pts:,} points, "
              f"{OUT.stat().st_size / 1024:.0f} KB")
        print(f"source: {data.get('source')}")
        return 0

    print("asking ONS Open Geography for LAD boundaries")
    raw = fetch()

    cd, nm = code_fields(raw[0].get("properties") or {})
    print(f"   code field {cd}, name field {nm}")

    out_features, before, after = [], 0, 0
    for feature in raw:
        props = feature.get("properties") or {}
        thinned = []
        for ring in rings_of(feature.get("geometry") or {}):
            before += len(ring)
            thin = simplify([[round(x, 4), round(y, 4)] for x, y in ring],
                            TOLERANCE)
            thinned.append(thin)
        thinned.sort(key=len, reverse=True)
        # keep the big rings; always keep the largest so nothing vanishes
        kept = [r for r in thinned if len(r) >= MIN_RING] or thinned[:1]
        after += sum(len(r) for r in kept)
        out_features.append({"code": props[cd], "name": props[nm],
                             "rings": kept})
    out_features.sort(key=lambda f: f["code"])

    OUT.write_text(json.dumps({
        "source": "Office for National Statistics / Ordnance Survey, "
                  "Local Authority Districts (December 2024) Boundaries UK "
                  "BUC (ultra generalised), Open Government Licence v3.0. "
                  "Contains OS data (C) Crown copyright and database right "
                  "2024.",
        "note": "Simplified with Douglas-Peucker at 0.008 degrees for drawing "
                "at 720px. Not for measurement or navigation.",
        "tolerance_degrees": TOLERANCE,
        "features": out_features,
    }, separators=(",", ":")), encoding="utf-8")

    print(f"\n{len(out_features)} authorities kept, {before:,} points "
          f"reduced to {after:,} ({100 * after / max(before, 1):.1f}%)")
    print(f"wrote {OUT.name}, {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
