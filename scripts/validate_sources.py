"""Validate every source in sources.yaml — run by CI on pull requests.

Checks each entry has the required fields, a unique id, and a live endpoint
that speaks its declared protocol. Exits non-zero with a readable report so
a PR adding a broken source fails with a useful message.

Usage:  python scripts/validate_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS
import yaml

ROOT = Path(__file__).parent.parent
REQUIRED = {"id", "name", "type", "api", "web", "dataset_url"}
UA = HEADERS


class Blocked(Exception):
    """The publisher refused us — says nothing about whether the source is good."""


# A refusal aimed at the client tells us nothing about the source. CI runs
# from datacenter IPs that portals routinely bot-block (north_yorkshire 403s
# from GitHub runners but is perfectly healthy from the server), so treating
# these as failures would reject valid community PRs at random.
BLOCKED_STATUSES = {401, 403, 429, 503}


def check_ckan(src: dict) -> str | None:
    r = requests.get(f"{src['api']}/package_search", params={"rows": 1},
                     headers=UA, timeout=30)
    if r.status_code in BLOCKED_STATUSES:
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return f"HTTP {r.status_code} from package_search"
    body = r.json()
    if not body.get("success"):
        return "package_search responded but success != true"
    result = body.get("result", {})
    if not isinstance(result.get("count"), int):
        return "package_search result has no dataset count"
    return None


def check_dcat(src: dict) -> str | None:
    r = requests.get(src["api"], headers=UA, timeout=60)
    if r.status_code in BLOCKED_STATUSES:
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return f"HTTP {r.status_code} from DCAT feed"
    datasets = r.json().get("dataset")
    if not isinstance(datasets, list) or not datasets:
        return "DCAT feed has no dataset list"
    # A title is required; an identifier is not. Aggregators like
    # opendata.scot carry neither identifier nor landingPage and are still
    # perfectly harvestable — harvester.py recovers a link from the
    # distributions and keys on publisher+title. The check must not be
    # stricter than the harvester, or CI rejects sources that work.
    first = datasets[0]
    if not first.get("title"):
        return "DCAT entries lack a title"
    has_link = bool(first.get("identifier") or first.get("landingPage")) or any(
        str(d.get("accessURL") or d.get("downloadURL") or "").startswith("http")
        for d in (first.get("distribution") or []))
    if not has_link:
        return "DCAT entries have no identifier, landing page or distribution"
    return None


def check_ods(src: dict) -> str | None:
    r = requests.get(src["api"], params={"limit": 1}, headers=UA, timeout=30)
    if r.status_code in BLOCKED_STATUSES:
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return f"HTTP {r.status_code} from OpenDataSoft catalogue"
    body = r.json()
    if not isinstance(body.get("total_count"), int):
        return "no total_count — not an ODS Explore v2.1 catalogue"
    if not body.get("results"):
        return "catalogue is empty"
    if not (body["results"][0].get("dataset_id")):
        return "entries lack dataset_id"
    return None


def check_geonode(src: dict) -> str | None:
    r = requests.get(src["api"], params={"page_size": 1}, headers=UA, timeout=60)
    if r.status_code in BLOCKED_STATUSES:
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return f"HTTP {r.status_code} from GeoNode API"
    body = r.json()
    layers = body.get("layers") or body.get("resources")
    if not isinstance(layers, list) or not layers:
        return "no layers — not a GeoNode v2 catalogue"
    if not isinstance(body.get("total"), int):
        return "no total — GeoNode v2 pagination missing"
    rec = layers[0]
    if not rec.get("title") or not (rec.get("uuid") or rec.get("pk")):
        return "layers lack title/uuid"
    # Without `alternate` there is no GeoServer feature type, so we could
    # index the record but never offer a download for it.
    if not rec.get("alternate"):
        return "layers lack `alternate` — no downloads could be built"
    return None


def check_json(src: dict) -> str | None:
    """A bespoke JSON catalogue, described by `json:` config on the source."""
    cfg = src.get("json") or {}
    r = requests.get(src["api"], params=cfg.get("params") or {}, headers=UA,
                     timeout=60)
    if r.status_code in BLOCKED_STATUSES:
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return f"HTTP {r.status_code} from JSON catalogue"
    body = r.json()
    path = cfg.get("list", "")
    items = body
    for step in filter(None, path.split(".")):
        items = items.get(step) if isinstance(items, dict) else None
    if not isinstance(items, list) or not items:
        return f"no record list at {path or '(root)'}"
    rec, first = items[0], cfg.get("id", "id")
    if not isinstance(rec, dict):
        return "records are not objects"
    if rec.get(first) in (None, ""):
        return f"records have no {first!r} to key on"
    if not rec.get(cfg.get("title", "title")) and not cfg.get("detail"):
        return "records have no title and no detail endpoint to fetch one"
    return None


CHECKS = {"ckan": check_ckan, "dcat": check_dcat, "ods": check_ods,
          "geonode": check_geonode, "json": check_json}


def main() -> int:
    with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
        sources = yaml.safe_load(fh)["sources"]

    failures: list[str] = []
    blocked: list[str] = []
    seen_ids: set[str] = set()
    for src in sources:
        sid = src.get("id", "<missing id>")
        missing = REQUIRED - src.keys()
        if missing:
            failures.append(f"{sid}: missing fields {sorted(missing)}")
            continue
        if sid in seen_ids:
            failures.append(f"{sid}: duplicate source id")
            continue
        seen_ids.add(sid)
        check = CHECKS.get(src["type"])
        if check is None:
            failures.append(f"{sid}: unknown type {src['type']!r} "
                            f"(supported: {sorted(CHECKS)})")
            continue
        try:
            problem = check(src)
        except Blocked as exc:
            blocked.append(f"{sid}: refused us ({exc})")
            print(f"skip    {sid}  (publisher blocked this checker)")
            continue
        except Exception as exc:  # noqa: BLE001
            problem = f"endpoint check failed: {exc}"
        if problem:
            failures.append(f"{sid}: {problem}")
        else:
            print(f"ok      {sid}")

    if blocked:
        print(f"\n{len(blocked)} source(s) could not be verified from here — "
              "not treated as failures:")
        for b in blocked:
            print(f"  SKIP  {b}")
        print("  (CI runs from datacenter IPs that some portals bot-block; a "
              "refusal tells us nothing about whether the source is valid.)")

    if failures:
        print("\nVALIDATION FAILED:")
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"\n{len(sources) - len(blocked)} of {len(sources)} sources verified"
          + (f", {len(blocked)} unverifiable from here" if blocked else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
