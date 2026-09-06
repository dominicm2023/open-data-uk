"""Which datasets belong to a family, and which resource of each to fetch.

Built from the index, never by hand: the index already knows every dataset
whose title says "household waste recycling centre", who published it, on
which portal, with what licence stated and which files behind it. A family
registry is a *query* over that knowledge, re-runnable nightly, with the
exclusions written down beside the rule.

For each admitted dataset one resource is chosen, by preference: a CSV, a
GeoJSON or JSON file, an ArcGIS REST layer (queried for its rows), an
XLSX. HTML, WMS and PDF are not fetched by this pass — a PDF family needs a
layout adapter, and a WMS is a picture.

Licence evidence comes in two strengths and the registry says which:
  fresh   the portal's own API for that dataset, fetched at intake and kept
          by hash (CKAN package_show, ArcGIS item metadata);
  index   what the harvester recorded, with its date — weaker, because it
          is our reading of the portal on the night we read it.
The intake refuses anything that is not an explicit Open Government Licence
v1–3 either way.

Usage:  DATA_DIR=... python families/registry.py recycling_centres
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paths import DB_PATH  # noqa: E402

import yaml  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "registry"

FAMILIES: dict[str, dict] = {
    "recycling_centres": {
        "label": "Household waste recycling centres",
        "include": r"(household\s+waste\s+recycling|recycling\s+cent|hwrc|civic\s+amenity|waste\s+recycling\s+cent|recycling\s+sites?\b)",
        "exclude": r"\brates?\b|tonnage|performance|collected|composition|survey",
    },
    "air_quality_annual": {
        "label": "Air quality: annual mean concentrations",
        "include": r"(air\s+quality.*(annual|mean|monitor|no2|nitrogen|diffusion)|nitrogen\s+dioxide|diffusion\s+tube|no2\b.*(annual|mean|monitor|tube))",
        # Site *locations* and management-area boundaries are a different family.
        "exclude": r"management\s+area|aqma\b|boundar|\bsites?\s+location|monitoring\s+sites?\s*$|monitors\s*$|action\s+plan",
    },
    "spend_over_500": {
        "label": "Spend over £500",
        "include": r"(spend|spending|expenditure|payments?|transactions?|invoices?)\s+(over|above|exceeding|greater\s+than|>)\s*£?\s*(500|250)\b",
        "exclude": r"\bgpc\b|procurement\s+card|credit\s+card",
    },
}

# Preference order for the resources fetched per dataset. A dataset can list
# dozens of files (a spend return has one a month), and on data.gov.uk a
# resource marked CSV is often a link to an HTML page. So the registry ranks
# up to CANDIDATES per dataset — a URL that ends .csv first, then the newest
# by any year in its name — and the intake tries them in order until one
# extracts. The first 60-source spend run lost 19 datasets to "HTML
# response, not CSV" on a first and only try.
FORMAT_RANK = {"CSV": 0, "GEOJSON": 1, "JSON": 2, "ESRI-REST": 3, "XLSX": 4, "XLS": 5}
CANDIDATES = 6
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def _rank(r: dict) -> tuple:
    url = (r["url"] or "").lower()
    fmt = (r["format_norm"] or "").upper()
    ends_csv = url.split("?")[0].endswith(".csv")
    looks_page = url.rstrip("/").endswith((".html", ".htm", ".aspx", ".php")) or "/dataset/" in url and not ends_csv
    years = [int(y) for y in _YEAR.findall((r["name"] or "") + " " + url)]
    return (0 if ends_csv else 1, FORMAT_RANK[fmt], 1 if looks_page else 0, -max(years, default=0))
INDEXABLE = ("FROM datasets d WHERE "
             "NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) AND "
             "NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key) AND "
             "NOT EXISTS (SELECT 1 FROM editions e WHERE e.key = d.key)")
_ARCGIS_ITEM = re.compile(r"[?&]id=([0-9a-f]{32})(?:&sublayer=(\d+))?")


def _sources() -> dict[str, dict]:
    with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
        return {s["id"]: s for s in yaml.safe_load(fh)["sources"]}


def _metadata_url(rec: dict, src: dict) -> tuple[str, str | None]:
    """('ckan'|'arcgis'|'index', url or None): where fresh licence evidence lives."""
    kind = src.get("type")
    if kind == "ckan" and rec.get("ckan_id"):
        api = ("https://ckan.publishing.service.gov.uk/api/3/action"
               if rec["source_id"] == "data_gov_uk" else src["api"].rstrip("/"))
        return "ckan", f"{api}/package_show?id={quote(rec['ckan_id'], safe='')}"
    m = _ARCGIS_ITEM.search(rec["key"])
    if m:
        return "arcgis", f"https://www.arcgis.com/sharing/rest/content/items/{m.group(1)}?f=json"
    # A Hub landing page names its item too: .../datasets/<32 hex>_<layer>/...
    # Without this, every DCAT-fed council was refused on the harvested word
    # "custom", when the item's own licenseInfo usually links the OGL.
    m = re.search(r"/datasets/(?:[a-z0-9-]+::)?([0-9a-f]{32})", rec.get("landing_url") or "")
    if m:
        return "arcgis", f"https://www.arcgis.com/sharing/rest/content/items/{m.group(1)}?f=json"
    return "index", None


def _resource_url(url: str, fmt: str) -> tuple[str, str]:
    """An ArcGIS REST layer is fetched as its rows, not its landing page."""
    if fmt == "ESRI-REST":
        base = url.split("/query", 1)[0].rstrip("/")
        if not re.search(r"/\d+$", base):
            base += "/0"
        return (base + "/query?where=1%3D1&outFields=*&returnGeometry=true"
                "&outSR=4326&f=json&resultRecordCount=2000"), "ESRI"
    return url, fmt


def build(family: str) -> dict:
    spec = FAMILIES[family]
    inc, exc = re.compile(spec["include"], re.I), re.compile(spec["exclude"], re.I)
    srcs = _sources()
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    admitted, skipped = [], []
    for d in conn.execute(f"SELECT d.* {INDEXABLE} ORDER BY d.publisher, d.title"):
        title = d["title"] or ""
        if not inc.search(title):
            continue
        if exc.search(title):
            skipped.append({"key": d["key"], "title": title, "why": "title matches exclusion"})
            continue
        res = [dict(r) for r in conn.execute(
            "SELECT url, name, format_norm FROM resources WHERE dataset_key = ?", (d["key"],))]
        cands = [r for r in res if (r["format_norm"] or "").upper() in FORMAT_RANK and r["url"]]
        if not cands:
            skipped.append({"key": d["key"], "title": title,
                            "why": "no CSV/JSON/GeoJSON/ArcGIS/XLSX resource",
                            "formats": sorted({(r["format_norm"] or "?") for r in res})})
            continue
        cands.sort(key=_rank)
        best = cands[0]
        url, fmt = _resource_url(best["url"], best["format_norm"].upper())
        ranked = []
        for r in cands[:CANDIDATES]:
            u, f = _resource_url(r["url"], r["format_norm"].upper())
            ranked.append({"url": u, "name": r["name"] or "", "format": f})
        src = srcs.get(d["source_id"], {})
        kind, meta = _metadata_url(dict(d), src)
        admitted.append({
            "dataset_key": d["key"], "title": title, "publisher": d["publisher"],
            "portal": d["source_id"], "landing_url": d["landing_url"],
            "licence_kind": kind, "metadata_url": meta,
            "index_licence_raw": d["license_raw"], "index_licence_norm": d["license_norm"],
            "index_harvested_at": d["harvested_at"],
            "resource": {"url": url, "name": best["name"] or "", "format": fmt},
            "candidates": ranked,
            "other_resources": len(res),
        })
    conn.close()
    reg = {"family": family, "label": spec["label"], "rule": spec,
           "sources": admitted, "skipped": skipped}
    OUT.mkdir(exist_ok=True)
    (OUT / f"{family}.json").write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    return reg


def main() -> int:
    fams = sys.argv[1:] or list(FAMILIES)
    for fam in fams:
        reg = build(fam)
        kinds = {}
        for s in reg["sources"]:
            kinds[s["licence_kind"]] = kinds.get(s["licence_kind"], 0) + 1
        fmts = {}
        for s in reg["sources"]:
            fmts[s["resource"]["format"]] = fmts.get(s["resource"]["format"], 0) + 1
        print(f"{fam}: {len(reg['sources'])} sources admitted, {len(reg['skipped'])} skipped; "
              f"licence evidence {kinds}; formats {fmts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
