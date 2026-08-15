"""Mark cross-portal duplicate datasets and retired records in index.db.

data.gov.uk aggregates many of the portals we also harvest directly, so the
same dataset often appears 2-3 times. This script groups likely duplicates
and elects one canonical copy per group; search then collapses the rest.

Duplicate rule (deliberately conservative): identical normalised title AND
the two records name the same organisation — either the publisher strings
match outright, or one is the aggregator's copy of the other and the two
publisher names agree on who published it once the administrative wrapper
("City Council", "Metropolitan Borough of") is stripped.

Generic titles are the whole difficulty here. Councils publish dozens of
identically-named datasets — "Council Spending", "Business Rates", "Fraud" —
and collapsing Rochdale's onto Leeds's doesn't tidy the index, it deletes
Rochdale's data from search. When we can't confirm two records are the same
organisation we keep both: a duplicate we failed to spot costs a reader one
extra line of results, a wrong merge costs them the dataset entirely.

Canonical election: prefer a source portal over the aggregator, then more
resources, then most recently modified.

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
    clusters: list[list] = []
    for r in candidates:
        for cl in clusters:
            if all(mergeable(r, other) for other in cl):
                cl.append(r)
                break
        else:
            clusters.append([r])
    return clusters


def rank(r) -> tuple:
    """Which copy of a duplicate group to keep as the canonical one."""
    return (
        r["source_id"] != AGGREGATOR,      # prefer the source portal
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
        """
    )

    rows = conn.execute(
        "SELECT key, source_id, title, publisher, description, "
        "       resource_count, modified FROM datasets"
    ).fetchall()

    # --- retired records ------------------------------------------------
    retired = [(r["key"],) for r in rows
               if r["description"] and _RETIRED_RE.search(r["description"])]
    conn.executemany("INSERT INTO retired VALUES (?)", retired)

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
            canonical = max(cl, key=rank)
            dup_rows += [(r["key"], canonical["key"])
                         for r in cl if r["key"] != canonical["key"]]

    conn.executemany("INSERT INTO duplicates VALUES (?, ?)", dup_rows)
    conn.commit()

    total = len(rows)
    print(f"{total:,} datasets scanned")
    print(f"{len(retired):,} retired records flagged")
    print(f"{groups:,} duplicate groups; {len(dup_rows):,} non-canonical copies marked")
    conn.close()


if __name__ == "__main__":
    main()
