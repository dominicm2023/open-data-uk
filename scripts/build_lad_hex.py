"""Fetch a hexagonal cartogram layout for UK local authorities, vendor it.

Choropleths lie about people: rural districts are huge and empty, urban
boroughs tiny and full. A hex cartogram gives every authority the same visual
weight — one hex each — at the cost of exact geography. This vendors a layout
the same way build_coastline.py vendors geometry: fetched once, committed with
its licence and attribution inside, no network at view time.

The layout is ODI Leeds' (now Open Innovations) hand-designed hexJSON for UK
local authority districts, from the MIT-licensed odileeds/hexmaps repository.
The 2023 vintage carries exactly the December 2024 LAD codes (nothing changed
between April 2023 and December 2024), so every code in lad_boundaries.json
matches without any merger mapping. (The repo's 2025 file re-codes Barnsley
and Sheffield to E08000038/39, which is why it is *not* used here.)

Usage:
    python scripts/build_lad_hex.py            # fetch, verify, write
    python scripts/build_lad_hex.py --check    # report what is vendored
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "lad_hex.json"
BOUNDARIES = ROOT / "lad_boundaries.json"

URL = ("https://raw.githubusercontent.com/odileeds/hexmaps/master/maps/"
       "uk-local-authority-districts-2023.hexjson")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what is already vendored and stop")
    args = ap.parse_args()

    if args.check:
        if not OUT.exists():
            print("no lad_hex.json vendored")
            return 1
        data = json.loads(OUT.read_text(encoding="utf-8"))
        print(f"{len(data['hexes'])} hexes, layout {data['layout']}, "
              f"{OUT.stat().st_size / 1024:.0f} KB")
        print(f"source: {data.get('source')}")
        return 0

    print("fetching ODI Leeds LAD hexjson layout")
    r = requests.get(URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    raw = r.json()
    layout = raw.get("layout", "odd-r")
    hexes = raw["hexes"]
    print(f"   {len(hexes)} hexes, layout {layout}")

    # one hex per authority, no two on the same cell
    cells = Counter((h["q"], h["r"]) for h in hexes.values())
    clashes = [c for c, n in cells.items() if n > 1]
    if clashes:
        raise SystemExit(f"overlapping hexes at {clashes}; refusing to write")

    # every boundary code must have a hex, and vice versa
    if BOUNDARIES.exists():
        bcodes = {f["code"] for f in
                  json.loads(BOUNDARIES.read_text(encoding="utf-8"))["features"]}
        missing_hex = sorted(bcodes - set(hexes))
        missing_boundary = sorted(set(hexes) - bcodes)
        if missing_hex or missing_boundary:
            print(f"   WARNING boundary codes without hex: {missing_hex}")
            print(f"   WARNING hex codes without boundary: {missing_boundary}")
        else:
            print(f"   all {len(bcodes)} boundary codes matched, both ways")

    out_hexes = [{"code": code, "name": h["n"], "q": h["q"], "r": h["r"]}
                 for code, h in sorted(hexes.items())]

    OUT.write_text(json.dumps({
        "source": "ODI Leeds / Open Innovations hexmaps "
                  "(github.com/odileeds/hexmaps), "
                  "uk-local-authority-districts-2023.hexjson, MIT licence. "
                  "Codes are LAD24CD (unchanged since the 2023 vintage).",
        "note": "One equal hex per local authority. Axial odd-r offset "
                "coordinates: q is column, r is row, odd rows shifted right. "
                "Rough geography only — Scotland top, London a cluster.",
        "layout": layout,
        "hexes": out_hexes,
    }, separators=(",", ":")), encoding="utf-8")

    rows = [h["r"] for h in out_hexes]
    print(f"   rows span {min(rows)}..{max(rows)}")
    print(f"wrote {OUT.name}, {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
