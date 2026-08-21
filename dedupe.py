"""Mark cross-portal duplicate datasets and retired records in index.db.

data.gov.uk aggregates many of the portals we also harvest directly, so the
same dataset often appears 2-3 times. This script groups likely duplicates
and elects one canonical copy per group; search then collapses the rest.

Duplicate rule (deliberately conservative): identical normalised title AND
the two records name the same organisation — either the publisher strings
match outright, or one is the aggregator's copy of the other and the two
publisher names agree on who published it once the administrative wrapper
("City Council", "Metropolitan Borough of") is stripped. Where the
aggregator names a platform instead of an organisation ("OpenDataNI") there
is no name to agree with, and the portal it mirrors stands in — see
_PLATFORM_SOURCES.

Generic titles are the whole difficulty here. Councils publish dozens of
identically-named datasets — "Council Spending", "Business Rates", "Fraud" —
and collapsing Rochdale's onto Leeds's doesn't tidy the index, it deletes
Rochdale's data from search. When we can't confirm two records are the same
organisation we keep both: a duplicate we failed to spot costs a reader one
extra line of results, a wrong merge costs them the dataset entirely.

Canonical election: prefer a copy that has resources at all, then a source
portal over the aggregator, then more resources, then most recently
modified.

Also flags retired/superseded records (publishers leave them in place with a
"this record has been retired" note) so search can exclude them.

Usage:  python dedupe.py
Re-runnable; recomputes from scratch each time.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
from paths import DB_PATH, connect as db_connect  # noqa: E402

AGGREGATOR = "data_gov_uk"

_RETIRED_RE = re.compile(
    r"(this (record|dataset) (has been|is) (retired|withdrawn|superseded))"
    r"|(record has been retired)|(has been superseded by)",
    re.I,
)


def norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# The administrative wrapper around an authority's name, and nothing else.
# Deliberately not geo._ORG_WORDS, which also strips topical words: that list
# reduces both "Historic England" and "Natural England" to "england", and two
# national bodies that publish very different things would look like one.
_PUBLISHER_NOISE = {
    "council", "city", "of", "the", "and", "for", "borough", "district",
    "county", "metropolitan", "royal", "greater", "combined", "unitary",
    "authority", "authorities", "london", "corporation", "cbc", "mbc", "dc",
    "cyngor", "bwrdeistref", "sirol", "comhairle",
}


def who(publisher: str | None) -> frozenset[str]:
    """The words that say *which* organisation this is.

    "Leeds City Council" and "Leeds" both come out as {leeds}; "Rochdale
    Borough Council" comes out as {rochdale} and so can never be confused
    with it.
    """
    return frozenset(norm(publisher).split()) - _PUBLISHER_NOISE


# Some of what data.gov.uk aggregates is filed under the name of the
# *platform* it was mirrored from rather than the body that published it:
# everything harvested from the Northern Ireland portal is "OpenDataNI",
# everything syndicated by the marine metadata network is "MEDIN", and the
# GLA re-publishes the whole London Datastore — the fire brigade's data and
# TfL's included — under "Greater London Authority". who() cannot match
# those against a real organisation, because there is no organisation there
# to match: "OpenDataNI" and "NI Water" share no word at all. So both copies
# survived and every count that rests on them was inflated.
#
# What identifies the publisher in these cases is the *portal*, not the
# name, so the bridge is to a named set of sources. Listing them out is the
# point rather than an inconvenience: a label allowed to match anything
# would merge data.gov.uk's Northern Irish "Boundary" into Green Action
# Trust's Scottish dataset of that name, which is the old wrong-merge bug
# wearing a new hat.
_PLATFORM_SOURCES: dict[str, frozenset[str]] = {
    # The Northern Ireland portal, plus the council and agency hubs whose
    # records that portal is itself carrying — verified by landing-URL
    # slugs that match all the way through, e.g. data.gov.uk's
    # /dataset/mid-ulster-council-public-toilets against Mid Ulster's own
    # midulster::mid-ulster-council-public-toilets.
    "opendatani": frozenset({
        "opendatani", "daera_ni", "agol_daera_agol", "causeway_coast",
        "mid_ulster",
    }),
    # MEDIN syndicates the Cefas Data Hub's marine catalogue.
    "marine environmental data information network": frozenset({"cefas"}),
    # data.gov.uk's copy of data.london.gov.uk. Note this reaches only the
    # Datastore: a Leeds dataset on DataMill North stays untouched, which
    # is what the entirely-generic-name test has always been guarding.
    "greater london authority": frozenset({"london_datastore"}),
}


def platform_of(publisher: str | None) -> frozenset[str]:
    """The portals this publisher name is a label for, if it is one at all."""
    return _PLATFORM_SOURCES.get(norm(publisher), frozenset())


def mirrors(a, b) -> bool:
    """Is `a` a platform-labelled copy of something from `b`'s portal?"""
    return b["source_id"] in platform_of(a["publisher"])


def mergeable(a, b) -> bool:
    """May these two same-titled records be treated as one dataset?"""
    if norm(a["publisher"]) == norm(b["publisher"]):
        return True
    # An aggregator copy of a portal's own dataset: same organisation, but
    # data.gov.uk may spell the name differently from the council's own
    # portal. Only bridge the two when the names still agree on who published
    # it — one being a fuller form of the other, never merely overlapping
    # ("North Yorkshire" and "North Somerset" share a word and are not the
    # same council).
    if (a["source_id"] == AGGREGATOR) == (b["source_id"] == AGGREGATOR):
        return False
    if mirrors(a, b) or mirrors(b, a):
        return True
    wa, wb = who(a["publisher"]), who(b["publisher"])
    return bool(wa) and bool(wb) and (wa <= wb or wb <= wa)


def cluster(candidates: list) -> list[list]:
    """Group same-titled records, every member agreeing with every other.

    Joining on *any* match made merging transitive, and the aggregator sits
    in the middle of everything: Bristol's "Fraud" merged with data.gov.uk's
    copy, which merged with Calderdale's, so Bristol's dataset vanished into
    Calderdale's. Requiring agreement with the whole cluster stops the chain
    forming.
    """
    # A platform label is the weaker kind of match: it agrees with anything
    # on the portal it names, where a publisher's own name agrees only with
    # itself. So the named records are placed first and the labelled ones
    # fall in around them. Left in database order, data.gov.uk's "OpenDataNI"
    # copy of a Belfast dataset would take the cluster first and lock out
    # data.gov.uk's *own* copy filed under "Belfast City Council" — two
    # aggregator records may never share a cluster — splitting a pair that
    # had been merged correctly for as long as the rule has existed.
    candidates = sorted(candidates, key=lambda r: bool(platform_of(r["publisher"])))

    clusters: list[list] = []
    for r in candidates:
        for cl in clusters:
            if all(mergeable(r, other) for other in cl):
                cl.append(r)
                break
        else:
            clusters.append([r])
    return clusters


def rank(r, retired: frozenset[str] = frozenset()) -> tuple:
    """Which copy of a duplicate group to keep as the canonical one.

    A withdrawn record must never be the copy we keep: search drops retired
    canonicals, and every live twin filed as its duplicate vanished with it —
    553 datasets were invisible behind exactly this. Then: a copy with no
    resources is a dead end — the reader follows it and finds nothing to
    download — so one carrying files outranks one that doesn't, the
    publisher's own copy included. 252 of data.gov.uk's Northern Ireland
    mirrors are empty while their twins hold the files.
    """
    return (
        r["key"] not in retired,           # never elect a withdrawn record
        bool(r["resource_count"]),         # prefer a copy that has files
        r["source_id"] != AGGREGATOR,      # then the source portal
        r["resource_count"] or 0,
        r["modified"] or "",
    )


def main() -> None:
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        DROP TABLE IF EXISTS duplicates;
        CREATE TABLE duplicates (
            key           TEXT PRIMARY KEY,   -- the non-canonical copy
            canonical_key TEXT NOT NULL
        );
        DROP TABLE IF EXISTS retired;
        CREATE TABLE retired (key TEXT PRIMARY KEY);

        -- Tags live in a JSON array on the dataset row, which means the
        -- subject pages had to scan the whole table and filter in Python:
        -- 200ms a page against 4ms for everything else, on the page type
        -- with the most URLs in the sitemap. Flattened here, once a night.
        DROP TABLE IF EXISTS dataset_tags;
        CREATE TABLE dataset_tags (
            tag         TEXT NOT NULL,   -- lower-case, whitespace collapsed
            dataset_key TEXT NOT NULL,
            PRIMARY KEY (tag, dataset_key)
        );
        """
    )

    rows = conn.execute(
        "SELECT key, source_id, title, publisher, description, "
        "       resource_count, modified, tags FROM datasets"
    ).fetchall()

    # --- tags -------------------------------------------------------------
    import json as _json
    tag_rows = {(" ".join(str(t).lower().split()), r["key"])
                for r in rows for t in _json.loads(r["tags"] or "[]")}
    tag_rows = {(t, k) for t, k in tag_rows if len(t) > 1}
    conn.executemany("INSERT INTO dataset_tags VALUES (?, ?)", sorted(tag_rows))
    conn.execute("CREATE INDEX idx_dataset_tags_tag ON dataset_tags (tag)")

    # --- retired records ------------------------------------------------
    retired = [(r["key"],) for r in rows
               if r["description"] and _RETIRED_RE.search(r["description"])]
    conn.executemany("INSERT INTO retired VALUES (?)", retired)
    retired_keys = frozenset(k for (k,) in retired)

    # --- duplicates -----------------------------------------------------
    by_title: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        t = norm(r["title"])
        if t:
            by_title[t].append(r)

    dup_rows: list[tuple[str, str]] = []
    groups = 0
    for candidates in by_title.values():
        if len(candidates) < 2:
            continue
        for cl in cluster(candidates):
            if len(cl) < 2:
                continue
            groups += 1
            canonical = max(cl, key=lambda r: rank(r, retired_keys))
            dup_rows += [(r["key"], canonical["key"])
                         for r in cl if r["key"] != canonical["key"]]

    conn.executemany("INSERT INTO duplicates VALUES (?, ?)", dup_rows)
    conn.commit()

    total = len(rows)
    print(f"{total:,} datasets scanned")
    print(f"{len(retired):,} retired records flagged")
    print(f"{groups:,} duplicate groups; {len(dup_rows):,} non-canonical copies marked")
    print(f"{len(tag_rows):,} tag/dataset pairs indexed")
    conn.close()


if __name__ == "__main__":
    main()
