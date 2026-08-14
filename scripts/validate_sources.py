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
import yaml

ROOT = Path(__file__).parent.parent
REQUIRED = {"id", "name", "type", "api", "web", "dataset_url"}
UA = {"User-Agent": "uk-open-data-index/0.1 (source validation)"}


def check_ckan(src: dict) -> str | None:
    r = requests.get(f"{src['api']}/package_search", params={"rows": 1},
                     headers=UA, timeout=30)
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
    if r.status_code != 200:
        return f"HTTP {r.status_code} from DCAT feed"
    datasets = r.json().get("dataset")
    if not isinstance(datasets, list) or not datasets:
        return "DCAT feed has no dataset list"
    if not (datasets[0].get("title") and
            (datasets[0].get("identifier") or datasets[0].get("landingPage"))):
        return "DCAT entries lack title/identifier"
    return None


def check_ods(src: dict) -> str | None:
    r = requests.get(src["api"], params={"limit": 1}, headers=UA, timeout=30)
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


CHECKS = {"ckan": check_ckan, "dcat": check_dcat, "ods": check_ods}


def main() -> int:
    with open(ROOT / "sources.yaml", encoding="utf-8") as fh:
        sources = yaml.safe_load(fh)["sources"]

    failures: list[str] = []
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
        except Exception as exc:  # noqa: BLE001
            problem = f"endpoint check failed: {exc}"
        if problem:
            failures.append(f"{sid}: {problem}")
        else:
            print(f"ok      {sid}")

    if failures:
        print("\nVALIDATION FAILED:")
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"\nall {len(sources)} sources valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
