"""Ask ArcGIS Hub about each council we have no source for.

Most councils that publish spatial data do it through an ArcGIS Online
organisation with no catalogue of its own — no CKAN, no DCAT feed, nothing a
hostname guess would ever find. Hub's federated search knows about them, so
this asks it by name, one council at a time.

Why by name rather than by sampling: paginating Hub's GB results finds
whoever publishes most, which is Esri UK and a handful of large councils.
Asking about each council in COUNCIL_COVERAGE.md that we're missing found 54
in 307 — including the only Welsh council with an ArcGIS organisation, which
no amount of sampling would have surfaced.

Matching is on exact identity, deliberately. Subset matching credited Devon
County Council's portal to East, Mid, North and West Devon, and gave Neath
Port Talbot to the Port of London Authority — four different councils and a
harbour, all sharing a word.

Usage:
    python scripts/find_council_portals.py            # report matches
    python scripts/find_council_portals.py --yaml     # emit sources.yaml entries
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS  # noqa: E402

ROOT = Path(__file__).parent.parent
COVERAGE = ROOT / "council_coverage.json"
HUB = "https://hub.arcgis.com/api/v3/datasets"
PAUSE = 0.15
MIN_DATASETS = 20        # below this an org isn't really publishing


def _coverage_module():
    """Load council_coverage once, for its identity() rule."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "council_coverage", Path(__file__).parent / "council_coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_COVERAGE = _coverage_module()


def identity(name: str) -> frozenset[str]:
    """The words that say which council this is — the coverage tracker's rule.

    Shared with the tracker on purpose: if the two disagreed about what
    counts as the same council, this would propose sources the tracker would
    then refuse to credit.
    """
    return _COVERAGE.identity(name)


def slug(name: str) -> str:
    return re.sub(r"_+", "_",
                  re.sub(r"[^a-z0-9]+", "_", name.lower().strip()).strip("_"))[:28]


def search(council: str, want: frozenset[str]) -> tuple[str, str, int] | None:
    """(orgName, orgId, total) for an organisation that IS this council."""
    try:
        r = requests.get(HUB, params={"filter[region]": "GB", "q": council,
                                      "page[size]": 25},
                         headers=HEADERS, timeout=45)
        data = r.json().get("data", [])
    except Exception:  # noqa: BLE001
        return None
    for d in data:
        a = d.get("attributes", {})
        org = " ".join((a.get("orgName") or "").split())
        if not org or identity(org) != want:
            continue
        try:
            t = requests.get(HUB, params={"filter[orgId]": a["orgId"], "page[size]": 1},
                             headers=HEADERS, timeout=45)
            total = (t.json().get("meta") or {}).get("total", 0)
        except Exception:  # noqa: BLE001
            total = 0
        if total >= MIN_DATASETS:
            return (org, a["orgId"], total)
    return None


def entry(council: str, org: str, org_id: str) -> str:
    return f'''
  - id: agol_{slug(council)}
    name: "{org.replace('"', "'")}"
    type: json
    api: {HUB}
    web: https://hub.arcgis.com
    dataset_url: "unused-for-json"
    json:
      list: data
      total: meta.total
      page_param: "page[number]"
      params: {{"filter[orgId]": "{org_id}", "page[size]": 100}}
      id: id
      title: attributes.name
      description: attributes.description
      license: attributes.license
      modified: attributes.modified
      landing: "https://hub.arcgis.com/datasets/{{id}}"
      resources:
        - [attributes.url, "=Esri REST"]
      require_description: 40'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yaml", action="store_true",
                    help="print sources.yaml entries for anything new")
    args = ap.parse_args()

    if not COVERAGE.exists():
        print("council_coverage.json not found — run scripts/council_coverage.py")
        return 1
    councils = json.loads(COVERAGE.read_text(encoding="utf-8"))
    todo = [c for c in councils if c["state"] != "own"]

    src_text = (ROOT / "sources.yaml").read_text(encoding="utf-8")
    known_orgs = set(re.findall(r'"filter\[orgId\]": "(\w+)"', src_text))
    known_ids = {s["id"] for s in yaml.safe_load(src_text)["sources"]}

    print(f"asking about {len(todo)} councils without their own source\n")
    new = []
    for c in todo:
        want = identity(c["name"])
        if not want:
            continue
        hit = search(c["name"], want)
        time.sleep(PAUSE)
        if not hit:
            continue
        org, org_id, total = hit
        if org_id in known_orgs or f"agol_{slug(c['name'])}" in known_ids:
            continue
        new.append((c, org, org_id, total))
        print(f"   {c['nation'][:3]} {c['name'][:28]:28} -> {org[:38]:38} {total:>6,}")

    print(f"\n{len(new)} councils with an ArcGIS organisation we don't yet harvest")
    if args.yaml and new:
        print("\n# --- paste into sources.yaml ---")
        for c, org, org_id, _ in new:
            print(entry(c["name"], org, org_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
