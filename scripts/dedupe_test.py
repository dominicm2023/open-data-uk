"""Regression tests for the duplicate-collapsing rule.

The rule decides what search *hides*, so its failure mode is silent: a wrong
merge doesn't produce an error, it produces a dataset nobody can find any
more. These cases are the ones that were actually wrong in production —
Bristol's "Fraud" collapsed into Calderdale's, Rochdale's "Council Spending"
into Leeds's — and a handful of the real merges that must keep working.

No database needed, so CI can run it on every push.

Usage:  python scripts/dedupe_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dedupe import cluster, mergeable, who  # noqa: E402

AGG = "data_gov_uk"


def rec(source: str, publisher: str, key: str = "", resources: int = 1):
    return {"key": key or f"{source}:{publisher}", "source_id": source,
            "publisher": publisher, "resource_count": resources,
            "modified": "2026-01-01"}


# (should_merge, record A, record B, why)
PAIRS = [
    (False, rec(AGG, "Rochdale Borough Council"), rec("datamillnorth", "Leeds City Council"),
     "two councils' identically-titled datasets are not one dataset"),
    (False, rec("bristol", "Bristol City Council"), rec("calderdale", "Calderdale Council"),
     "neither is the aggregator, so there is nothing to bridge them"),
    (False, rec(AGG, "Historic England"), rec("historic_england", "Natural England"),
     "two national bodies that differ only in a topical word"),
    (False, rec(AGG, "North Yorkshire Council"), rec("north_yorkshire", "North Somerset Council"),
     "sharing the word 'north' is not sharing an identity"),
    (False, rec(AGG, "Greater London Authority"), rec("london_datastore", "Leeds City Council"),
     "a publisher whose name is entirely generic can't be confirmed"),

    (True, rec(AGG, "Leeds City Council"), rec("datamillnorth", "Leeds City Council"),
     "the aggregator's copy of a portal's own dataset"),
    (True, rec(AGG, "Calderdale Metropolitan Borough Council"),
     rec("calderdale", "Calderdale Council"),
     "same council, longer form of the same name"),
    (True, rec("bristol", "Bristol City Council"), rec("bristol", "Bristol City Council"),
     "same publisher, same portal"),
]


def check_pairs() -> int:
    bad = 0
    for expected, a, b, why in PAIRS:
        for x, y in ((a, b), (b, a)):        # the rule must be symmetric
            got = mergeable(x, y)
            if got != expected:
                verb = "merged" if got else "kept apart"
                print(f"FAIL  {x['publisher']} + {y['publisher']}: {verb}, "
                      f"expected the opposite — {why}")
                bad += 1
            else:
                print(f"PASS  {'merge ' if expected else 'keep  '} "
                      f"{x['publisher'][:32]:32} + {y['publisher'][:32]:32}")
    return bad


def check_no_chaining() -> int:
    """The bug itself: A–agg–B must not put A and B in one cluster."""
    group = [rec("bristol", "Bristol City Council", "bristol:fraud"),
             rec(AGG, "Bristol City Council", "data_gov_uk:fraud"),
             rec("calderdale", "Calderdale Council", "calderdale:fraud")]
    clusters = cluster(group)
    keys = {frozenset(r["key"] for r in cl) for cl in clusters}
    together = any({"bristol:fraud", "calderdale:fraud"} <= k for k in keys)
    if together:
        print("FAIL  clustering chained Bristol to Calderdale through data.gov.uk")
        return 1
    print("PASS  clustering does not chain two councils through the aggregator")
    return 0


def check_who() -> int:
    bad = 0
    for name, expected in (("Leeds City Council", {"leeds"}),
                           ("London Borough of Hounslow", {"hounslow"}),
                           ("Wakefield Metropolitan District Council", {"wakefield"}),
                           ("Historic England", {"historic", "england"}),
                           ("Greater London Authority", set())):
        got = set(who(name))
        if got != expected:
            print(f"FAIL  who({name!r}) = {got or '{}'}, expected {expected or '{}'}")
            bad += 1
        else:
            print(f"PASS  who({name[:38]!r:40}) = {got or '{} (nothing distinctive)'}")
    return bad


def main() -> int:
    failures = check_who() + check_pairs() + check_no_chaining()
    print()
    print("all dedupe rules hold" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
