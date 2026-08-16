"""Verify catalogue-API URLs proposed by research agents.

Agents propose; this script decides. Nothing an agent returns is trusted:
each URL is fetched here and must actually yield a *list of many datasets*
before it can become a source. A hallucinated or optimistic URL fails and is
discarded, which is why the agents are told a wrong guess is worse than
"none".

Reads a JSON array of {domain, platform, api_url} on stdin or from a file,
and prints ready-to-review sources.yaml entries for whatever survives.

Usage:
    python scripts/verify_proposals.py proposals.json
    cat proposals.json | python scripts/verify_proposals.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS

UA = HEADERS
TIMEOUT = 25
MIN_DATASETS = 5   # below this it's a single product, not a catalogue


# Catalogue APIs all say the same two things in different words: "here is a
# page of records" and "here is how many there are in total". Rather than
# enumerate every platform, recognise those two shapes generically — the
# first version of this hard-coded CKAN/DCAT/Socrata and wrongly rejected
# GeoNode, OpenDataSoft and two custom APIs that were perfectly real.
LIST_KEYS = ("results", "datasets", "dataset", "layers", "items", "records",
             "packages", "views", "resources", "data")
COUNT_KEYS = ("count", "total", "total_count", "totalItems", "totalCount",
              "resultSetSize", "numFound", "numberMatched")


def count_datasets(payload) -> tuple[str, int] | None:
    """Recognise a dataset listing in any common catalogue shape."""
    if isinstance(payload, list):
        # Socrata /api/views.json, DKAN metastore items, NBN registry
        return ("list", len(payload)) if payload and isinstance(payload[0], dict) else None
    if not isinstance(payload, dict):
        return None

    # CKAN nests everything under "result"
    res = payload.get("result")
    if isinstance(res, dict) and isinstance(res.get("count"), int):
        return ("ckan", res["count"])
    if isinstance(res, list):                      # Data Mill North variant
        return ("ckan", len(res))

    # DCAT-US uses the singular "dataset" — distinguish it from the generic
    # case so the harvester type comes out right.
    if isinstance(payload.get("dataset"), list) and payload["dataset"]:
        return ("dcat", len(payload["dataset"]))

    listed = next((k for k in LIST_KEYS
                   if isinstance(payload.get(k), list) and payload[k]
                   and isinstance(payload[k][0], dict)), None)
    if not listed:
        return None
    total = next((payload[k] for k in COUNT_KEYS
                  if isinstance(payload.get(k), int)), None)
    return (f"generic:{listed}", total if total is not None else len(payload[listed]))


def verify(item: dict) -> dict:
    out = dict(item)
    url = item.get("api_url")
    out["verified"] = False
    out["dataset_count"] = 0
    if not url or not str(url).startswith("http"):
        out["reason"] = "no URL proposed"
        return out
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"unreachable ({type(exc).__name__})"
        return out
    if not r.ok:
        out["reason"] = f"HTTP {r.status_code}"
        return out
    try:
        payload = r.json()
    except ValueError:
        out["reason"] = f"not JSON ({r.headers.get('content-type', '?')[:40]})"
        return out
    hit = count_datasets(payload)
    if not hit:
        out["reason"] = "JSON, but no recognisable dataset list"
        return out
    shape, n = hit
    out["detected_shape"] = shape
    out["dataset_count"] = n
    if n < MIN_DATASETS:
        out["reason"] = f"only {n} datasets — not a catalogue"
        return out
    out["verified"] = True
    out["reason"] = f"ok, {n:,} datasets ({shape})"
    return out


# Labels that carry no identity: every portal is called "data" something
_GENERIC = {"data", "odata", "opendata", "www", "www2", "api", "hub", "maps",
            "geodata", "portal", "dataportal", "ws", "datashare", "map", "open",
            "gov", "uk", "scot", "wales", "org", "com", "ac", "net", "io", "info",
            "co", "nhs"}


def slug_for(domain: str) -> str:
    """Pick the distinctive label — 'data.spatialhub.scot' -> 'spatialhub',
    not 'data', which would collide with every other portal.

    Hyphenated labels are filtered piecewise too, so 'ws-data.nisra.gov.uk'
    skips the all-generic 'ws-data' and lands on 'nisra'.
    """
    parts = [p for p in domain.lower().split(".") if p]
    meaningful = []
    for p in parts:
        sub = [s for s in p.split("-") if s and s not in _GENERIC]
        if sub:
            meaningful.append("_".join(sub))
    return meaningful[0] if meaningful else parts[0].replace("-", "_")


def yaml_entry(item: dict) -> str:
    domain = item["domain"]
    slug = slug_for(domain)
    shape = item.get("detected_shape")
    kind = "ckan" if shape == "ckan" else "dcat" if shape == "dcat" else shape
    api = item["api_url"]
    if kind == "ckan":
        api = api.split("/package_search")[0].split("/api/3/action")[0] + "/api/3/action"
        durl = f"https://{domain}/dataset/{{name}}"
    else:
        durl = '"unused-for-dcat"'
    return (f"  - id: {slug}\n"
            f"    name: TODO ({item['dataset_count']:,} datasets - {item.get('notes','')[:60]})\n"
            f"    type: {kind}\n"
            f"    api: {api}\n"
            f"    web: https://{domain}\n"
            f"    dataset_url: {durl}\n")


def main() -> None:
    raw = (open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1
           else sys.stdin.read())
    items = json.loads(raw)
    if isinstance(items, dict):
        items = items.get("findings", [])

    with ThreadPoolExecutor(max_workers=12) as pool:
        checked = list(pool.map(verify, items))

    good = [c for c in checked if c["verified"]]
    bad = [c for c in checked if not c["verified"]]

    print(f"=== {len(good)} of {len(checked)} proposals verified ===")
    for c in sorted(good, key=lambda c: -c["dataset_count"]):
        print(f"  OK   {c['domain'][:46]:46} {c['reason']}")
    print(f"\n=== {len(bad)} rejected ===")
    for c in bad:
        print(f"  --   {c['domain'][:46]:46} {c['reason']}")

    if good:
        print("\n=== sources.yaml entries (names need a human) ===")
        for c in sorted(good, key=lambda c: -c["dataset_count"]):
            print(yaml_entry(c))


if __name__ == "__main__":
    main()
