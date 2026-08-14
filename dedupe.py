"""Mark cross-portal duplicate datasets and retired records in index.db.

data.gov.uk aggregates many of the portals we also harvest directly, so the
same dataset often appears 2-3 times. This script groups likely duplicates
and elects one canonical copy per group; search then collapses the rest.

Duplicate rule (deliberately conservative): identical normalised title AND
(identical normalised publisher OR exactly one of the pair comes from the
data_gov_uk aggregator). Generic titles like "Listed Buildings" from two
different councils both on data.gov.uk are NOT collapsed.

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

    def mergeable(a: sqlite3.Row, b: sqlite3.Row) -> bool:
        if norm(a["publisher"]) == norm(b["publisher"]):
            return True
        # aggregator copy of a directly-harvested portal's dataset
        return (a["source_id"] == AGGREGATOR) != (b["source_id"] == AGGREGATOR)

    def rank(r: sqlite3.Row) -> tuple:
        return (
            r["source_id"] != AGGREGATOR,      # prefer the source portal
            r["resource_count"] or 0,
            r["modified"] or "",
        )

    dup_rows: list[tuple[str, str]] = []
    groups = 0
    for candidates in by_title.values():
        if len(candidates) < 2:
            continue
        # union-find-lite: greedily cluster mergeable rows
        clusters: list[list[sqlite3.Row]] = []
        for r in candidates:
            for cl in clusters:
                if any(mergeable(r, other) for other in cl):
                    cl.append(r)
                    break
            else:
                clusters.append([r])
        for cl in clusters:
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
