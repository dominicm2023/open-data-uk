"""Build gazetteer.json — UK place names to coordinates.

Source: the ONS Open Geography Portal's Local Authority Districts table,
which carries an authoritative LONG/LAT per district. We index that portal
already, so the gazetteer is derived from real published data rather than
coordinates typed in from memory.

Aliases are generated so everyday phrasing resolves: "Brighton and Hove"
also answers to "brighton" and "hove", "City of Edinburgh" to "edinburgh",
"County Durham" to "durham".

Usage:
    python scripts/build_gazetteer.py          # writes gazetteer.json
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
OUT = ROOT / "gazetteer.json"
UA = {"User-Agent": "uk-open-data-index/0.2 (gazetteer build; "
                    "+https://open-data.org.uk/about)"}

# Local Authority Districts (December 2025) Boundaries UK BFC — ONS Open Geography
LAD_CSV = ("https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
           "items/92150c7aa60540c5814abe3b26bce6d0/csv?layers=0")

# Words that describe the administrative wrapper rather than the place
_STRIP_PREFIX = ("city of ", "county of ", "the ")
_STRIP_SUFFIX = (", city of", ", county of")
_DROP_WORDS = {"city", "county", "district", "borough", "council", "the"}


def aliases(name: str) -> set[str]:
    """Everyday names people would actually type for this district."""
    low = " ".join(name.lower().split())
    out = {low}

    for pre in _STRIP_PREFIX:
        if low.startswith(pre):
            out.add(low[len(pre):])
    for suf in _STRIP_SUFFIX:
        if low.endswith(suf):
            out.add(low[: -len(suf)])

    # "Brighton and Hove" -> brighton, hove;  "Bath and North East Somerset"
    # -> bath (the trailing part is a region, not a second town people search)
    if " and " in low:
        parts = [p.strip() for p in low.split(" and ")]
        out.add(parts[0])
        if len(parts[-1].split()) == 1:
            out.add(parts[-1])

    # "County Durham" -> durham
    words = [w for w in low.replace(",", " ").split() if w not in _DROP_WORDS]
    if words:
        out.add(" ".join(words))

    return {a.strip() for a in out if len(a.strip()) > 2}


def main() -> int:
    print(f"downloading ONS Local Authority Districts ...")
    r = requests.get(LAD_CSV, headers=UA, timeout=180)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="replace"))))
    if not rows:
        print("empty CSV")
        return 1

    name_col = next((c for c in rows[0] if c.upper().startswith("LAD") and c.upper().endswith("NM")
                     and not c.upper().endswith("NMW")), None)
    if not name_col or "LONG" not in rows[0] or "LAT" not in rows[0]:
        print(f"unexpected columns: {list(rows[0])}")
        return 1
    print(f"{len(rows)} districts, using name column {name_col!r}")

    gaz: dict[str, list[float]] = {}
    collisions = 0
    for row in rows:
        try:
            lon, lat = float(row["LONG"]), float(row["LAT"])
        except (ValueError, TypeError):
            continue
        if not (-9 <= lon <= 3 and 49 <= lat <= 62):   # sanity: inside the UK
            continue
        for alias in aliases(row[name_col]):
            if alias in gaz and gaz[alias] != [lon, lat]:
                collisions += 1      # ambiguous name; first district wins
                continue
            gaz[alias] = [round(lon, 4), round(lat, 4)]

    OUT.write_text(json.dumps(gaz, indent=0, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(gaz):,} place names to {OUT.name} "
          f"({collisions} ambiguous names kept first-wins)")
    for probe in ("brighton", "leeds", "glasgow", "cardiff", "belfast", "durham"):
        print(f"   {probe:10} {gaz.get(probe)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
