"""Check that search filters constrain results without disturbing ranking.

Filters are applied after ranking and before paging. That ordering is the
whole design: filter after the slice and you hand back short pages with a
total that lied about them, filter before ranking and you change what the
scores mean. These cases pin both ends.

Needs a built index, so it runs locally and on the box rather than in CI.

Usage:  python scripts/filter_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from search import SearchEngine  # noqa: E402

engine = SearchEngine()
failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


QUERY = "recycling rates"
base = engine.search(QUERY, k=20)
base_keys = [r["key"] for r in base["results"]]
check(bool(base_keys), "the unfiltered query returns something to filter")
check(base["filters"] is None, "no filters means no filters echoed back")

# --- availability -------------------------------------------------------
usable = engine.search(QUERY, k=20, filters={"availability": {"data", "api"}})
check(all(r["availability"] in ("data", "api") for r in usable["results"]),
      "availability=data,api returns only fetchable things")
check(usable["available"] <= base["available"],
      "filtering never increases the number of candidates")
check(usable["filters"] == {"availability": ["api", "data"]},
      "the applied filter is echoed back as sorted lists")

# --- ranking order is preserved, not re-scored --------------------------
kept = [k for k in base_keys if k in {r["key"] for r in usable["results"]}]
check(kept == [r["key"] for r in usable["results"]][:len(kept)],
      "surviving results keep the order they had before filtering")

# --- format -------------------------------------------------------------
csv_only = engine.search(QUERY, k=20, filters={"format": {"csv"}})
check(all("CSV" in r["formats"] for r in csv_only["results"]),
      "format=CSV returns only datasets offering a CSV")
check(engine.search(QUERY, k=5, filters={"format": {"csv", "xlsx"}})["available"]
      >= csv_only["available"],
      "two formats match at least as much as one — OR within a field")

# --- licence, including the honest 'none' -------------------------------
ogl = engine.search(QUERY, k=20, filters={"license": {"ogl-uk-3.0"}})
check(all(r["license"] == "OGL-UK-3.0" for r in ogl["results"]),
      "license filtering is case-insensitive on the caller's side")
unlicensed = engine.search(QUERY, k=20, filters={"license": {"none"}})
check(all(r["license"] is None for r in unlicensed["results"]),
      "license=none finds the datasets that state no licence")

# --- source -------------------------------------------------------------
one_portal = engine.search(QUERY, k=20, filters={"source": {"data_gov_uk"}})
check(all(r["source"] == "data_gov_uk" for r in one_portal["results"]),
      "source filtering keeps one portal")

# --- fields combine with AND -------------------------------------------
both = engine.search(QUERY, k=20,
                     filters={"availability": {"data"}, "format": {"csv"}})
check(all(r["availability"] == "data" and "CSV" in r["formats"]
          for r in both["results"]),
      "two fields are ANDed, not ORed")
check(both["available"] <= min(usable["available"], csv_only["available"]),
      "and ANDing can only narrow")

# --- paging still tells the truth about a filtered set ------------------
page1 = engine.search(QUERY, k=3, filters={"availability": {"data", "api"}})
page2 = engine.search(QUERY, k=3, offset=3, filters={"availability": {"data", "api"}})
check(page1["available"] == page2["available"],
      "the candidate count is the same whichever page you ask for")
check(not ({r["key"] for r in page1["results"]}
           & {r["key"] for r in page2["results"]}),
      "paging a filtered search does not repeat results")
if page1["available"] > 3:
    check(len(page1["results"]) == 3,
          "a filtered page is full when there is more to come")

# --- a filter nothing matches is honest, not an error -------------------
empty = engine.search(QUERY, k=10, filters={"format": {"definitely-not-a-format"}})
check(empty["results"] == [] and empty["available"] == 0,
      "an unmatched filter returns nothing and says so")
check(empty["confidence"] == base["confidence"],
      "confidence describes the query, not the filter — it is unchanged")

print()
print("all filter rules hold" if not failures else f"{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
