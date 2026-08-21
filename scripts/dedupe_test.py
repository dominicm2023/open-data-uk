"""Regression tests for the duplicate-collapsing rule.

The rule decides what search *hides*, so its failure mode is silent: a wrong
merge doesn't produce an error, it produces a dataset nobody can find any
more. These cases are the ones that were actually wrong in production —
Bristol's "Fraud" collapsed into Calderdale's, Rochdale's "Council Spending"
into Leeds's — and a handful of the real merges that must keep working.

The rule also fails the other way, quietly counting one dataset twice, and
the platform-label cases below are that failure: they must merge, while the
records a platform label must not reach stay next to them to prove the
bridge is a bridge and not a hole.

No database needed, so CI can run it on every push.

Usage:  python scripts/dedupe_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dedupe import cluster, mergeable, rank, who  # noqa: E402

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
    # Leeds on DataMill North, not on the Datastore: "Greater London
    # Authority" is now a platform label for data.london.gov.uk, and a Leeds
    # dataset sitting *on* the Datastore would genuinely be the GLA's copy.
    # What must never merge is the GLA's copy and Leeds's own portal.
    (False, rec(AGG, "Greater London Authority"), rec("datamillnorth", "Leeds City Council"),
     "a publisher whose name is entirely generic can't be confirmed"),

    (True, rec(AGG, "Leeds City Council"), rec("datamillnorth", "Leeds City Council"),
     "the aggregator's copy of a portal's own dataset"),
    (True, rec(AGG, "Calderdale Metropolitan Borough Council"),
     rec("calderdale", "Calderdale Council"),
     "same council, longer form of the same name"),
    (True, rec("bristol", "Bristol City Council"), rec("bristol", "Bristol City Council"),
     "same publisher, same portal"),

    # --- platform labels --------------------------------------------------
    # data.gov.uk files a whole portal's output under the portal's name, so
    # there is no organisation in the string for who() to agree with. The
    # portal itself has to stand in — but only for the portals that label
    # actually mirrors.
    (True, rec(AGG, "OpenDataNI"), rec("opendatani", "NI Water"),
     "the aggregator's copy of the NI portal, whose publishers it doesn't name"),
    (True, rec(AGG, "OpenDataNI"),
     rec("causeway_coast", "Causeway Coast and Glens Borough Council"),
     "the same mirror reaching the council hub the NI portal carries"),
    (True, rec(AGG, "Marine Environmental Data & Information Network"),
     rec("cefas", "Cefas Data Hub"),
     "a syndication network's copy of the catalogue it syndicates"),
    (True, rec(AGG, "Greater London Authority"),
     rec("london_datastore", "London Fire Brigade"),
     "the GLA re-publishes the whole Datastore under its own name"),

    (False, rec(AGG, "OpenDataNI"), rec("agol_green_action_trust", "Green Action Trust"),
     "a platform label does not reach a portal that platform never mirrors"),
    (False, rec(AGG, "OpenDataNI"), rec("datamillnorth", "Leeds City Council"),
     "nor does it reach a council on the other side of the Irish Sea"),
    (False, rec("opendatani", "NI Water"), rec("causeway_coast",
                                               "Causeway Coast and Glens Borough Council"),
     "two NI portals with no aggregator between them are still not bridged"),

    # --- one shared word is not an identity -------------------------------
    (False, rec(AGG, "Department for Transport"), rec("tfl", "Transport for London"),
     "DfT's national Cycle Routes are not TfL's London layer"),
    (False, rec(AGG, "Calderdale Metropolitan Borough Council"),
     rec("datamillnorth", "Citizens Advice Calderdale"),
     "a council and its local Citizens Advice share a place, not an identity"),
    (False, rec(AGG, "Plymouth City Council"), rec("plymouth", "Public Health Plymouth"),
     "one shared word reaching into a longer different name"),
    (True, rec(AGG, "London Borough of Camden"),
     rec("agol_camden", "London Borough of Camden Open Data"),
     "platform words stripped, the same borough remains"),
    (True, rec(AGG, "Aberdeen City Council"),
     rec("agol_aberdeen", "Aberdeen City Council ArcGIS Online"),
     "ArcGIS Online is the shelf, not the publisher"),
    (True, rec(AGG, "Natural England"), rec("agol_ne", "Natural England (Defra)"),
     "a two-word name agreeing in full is still a fuller form"),

    # --- a portal's own name is not a publisher ---------------------------
    # nbn_atlas's name in sources.yaml is "NBN Atlas (UK biodiversity
    # network)"; two same-titled records both carrying that fallback label
    # share a shelf, not an author.
    (False, rec("nbn_atlas", "NBN Atlas (UK biodiversity network)", key="nbn_atlas:a"),
     rec("nbn_atlas", "NBN Atlas (UK biodiversity network)", key="nbn_atlas:b"),
     "same-source records under the portal's own fallback label"),
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


def check_platform_does_not_chain() -> int:
    """A platform label bridges to a portal, not through it to a third party.

    "OpenDataNI" matches any publisher on the NI portal, so two unrelated NI
    bodies that happen to title a dataset the same way could be chained
    through the aggregator's copy — the Bristol/Calderdale bug again, with
    the platform label doing the chaining.
    """
    group = [rec("opendatani", "NI Water", "opendatani:consumption"),
             rec(AGG, "OpenDataNI", "data_gov_uk:consumption"),
             rec("opendatani", "Belfast City Council", "opendatani:consumption2")]
    keys = {frozenset(r["key"] for r in cl) for cl in cluster(group)}
    if any({"opendatani:consumption", "opendatani:consumption2"} <= k for k in keys):
        print("FAIL  a platform label chained two NI publishers into one cluster")
        return 1
    print("PASS  a platform label does not chain two publishers on the portal it names")
    return 0


def check_platform_yields_to_a_name() -> int:
    """A platform label must not evict the aggregator's own named copy.

    data.gov.uk holds some datasets twice — once mirrored from the portal
    and filed under the portal's name, once filed under the publisher's.
    Only the named one can be confirmed against the publisher's own record,
    and two aggregator copies can never share a cluster, so the labelled one
    has to give way or it takes the cluster and leaves the pair unmerged.
    """
    group = [rec(AGG, "OpenDataNI", "data_gov_uk:jobs-mirrored"),
             rec(AGG, "Belfast City Council", "data_gov_uk:jobs"),
             rec("opendatani", "Belfast City Council", "opendatani:jobs")]
    keys = {frozenset(r["key"] for r in cl) for cl in cluster(group)}
    if not any({"data_gov_uk:jobs", "opendatani:jobs"} <= k for k in keys):
        print("FAIL  a platform label displaced the aggregator's own named copy")
        return 1
    print("PASS  a platform label yields to the copy that names its publisher")
    return 0


def check_canonical() -> int:
    """The copy a reader is sent to must be one that has the files."""
    bad = 0
    empty_native = rec("opendatani", "NI Water", "opendatani:x", resources=0)
    full_agg = rec(AGG, "OpenDataNI", "data_gov_uk:x", resources=3)
    if max([empty_native, full_agg], key=rank) is not full_agg:
        print("FAIL  elected an empty copy over one carrying files")
        bad += 1
    else:
        print("PASS  a copy with files wins over an empty one, aggregator or not")

    full_native = rec("opendatani", "NI Water", "opendatani:y", resources=2)
    fuller_agg = rec(AGG, "OpenDataNI", "data_gov_uk:y", resources=9)
    if max([full_native, fuller_agg], key=rank) is not full_native:
        print("FAIL  elected the aggregator over the publisher's own copy")
        bad += 1
    else:
        print("PASS  with both carrying files, the publisher's own copy still wins")

    # Search drops a retired canonical AND everything filed as its duplicate,
    # so electing a withdrawn record buries its live twins — 553 datasets
    # were invisible behind exactly this.
    withdrawn = rec("opendatani", "NI Water", "opendatani:z", resources=9)
    live = rec(AGG, "OpenDataNI", "data_gov_uk:z", resources=1)
    marked = frozenset({"opendatani:z"})
    if max([withdrawn, live], key=lambda r: rank(r, marked)) is not live:
        print("FAIL  elected a withdrawn record and buried its live twin")
        bad += 1
    else:
        print("PASS  a live copy always beats a withdrawn one, whatever it carries")
    return bad


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
    failures = (check_who() + check_pairs() + check_no_chaining()
                + check_platform_does_not_chain()
                + check_platform_yields_to_a_name() + check_canonical())
    print()
    print("all dedupe rules hold" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
