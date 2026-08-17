"""Remove unrendered ArcGIS Hub templates from an index that is already built.

The harvester now refuses them (normalise.norm_title and normalise.strip_html),
but records harvested before that are still in the index: 17 datasets titled
literally "{{name}}" and 807 whose whole description is "{{description}}" or
"{{default.description}}". They are indexed, they appear in search and on
publisher listing pages, and there is nothing in them to read.

The two fields are treated differently, exactly as the harvester treats them:

  - a title that never rendered leaves no record at all, so the dataset row
    and everything hanging off it is deleted;
  - a description that never rendered is blanked, because the rest of the
    record may be perfectly sound and the page falls back to its generated
    summary.

Derived tables (duplicates, retired, dataset_tags, and the FTS index itself)
are rebuilt wholesale by dedupe.py and embed_index.py, so the nightly refresh
puts them right. The `fts` rows are corrected here anyway, so a server that is
already running stops returning the deleted keys before then.

No network, no publishers bothered, a couple of seconds.

    python scripts/backfill_placeholders.py --dry-run   # what would change
    python scripts/backfill_placeholders.py             # change it
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from normalise import unrendered  # noqa: E402
from paths import connect as db_connect  # noqa: E402


def report(label: str, counts: Counter) -> None:
    print(f"\n{label}: {sum(counts.values()):,}")
    for source, n in counts.most_common():
        print(f"   {n:>6,}  {source}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = db_connect()
    rows = conn.execute(
        "SELECT key, source_id, title, description FROM datasets "
        "WHERE title LIKE '%{{%' OR description LIKE '%{{%'").fetchall()

    drop: list[tuple[str]] = []
    blank: list[tuple[str]] = []
    dropped_by_source: Counter = Counter()
    blanked_by_source: Counter = Counter()
    for key, source_id, title, description in rows:
        # A title decides whether the record exists, so it is checked first:
        # a dataset being deleted needs no description blanked.
        if unrendered(title):
            drop.append((key,))
            dropped_by_source[source_id] += 1
        elif unrendered(description):
            blank.append((key,))
            blanked_by_source[source_id] += 1

    total = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
    print(f"{total:,} datasets in the index")
    report("records with no rendered title (deleted)", dropped_by_source)
    report("descriptions that never rendered (blanked)", blanked_by_source)

    if not drop and not blank:
        print("\nnothing to do")
        conn.close()
        return 0

    if args.dry_run:
        print("\ndry run — nothing written")
        conn.close()
        return 0

    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'fts'").fetchone()

    for table, column in (("resources", "dataset_key"),
                          ("dataset_geo", "dataset_key"),
                          ("datasets", "key")):
        conn.executemany(f"DELETE FROM {table} WHERE {column} = ?", drop)
    conn.executemany("UPDATE datasets SET description = NULL WHERE key = ?",
                     blank)

    if has_fts:
        # `key` is UNINDEXED in the FTS5 table, so a statement per row means a
        # full scan per row — 800 scans of 106k rows, which takes minutes.
        # Both statements below are one pass each, against a temp table.
        # Deleted datasets simply don't come back in the re-insert.
        conn.execute("CREATE TEMP TABLE touched (key TEXT PRIMARY KEY)")
        conn.executemany("INSERT INTO temp.touched VALUES (?)", drop + blank)
        conn.execute("DELETE FROM fts WHERE key IN (SELECT key FROM temp.touched)")
        # Column list mirrors embed_index.build_fts, which owns this table.
        conn.execute(
            """
            INSERT INTO fts (key, title, description, publisher, tags)
            SELECT key, coalesce(title,''), coalesce(description,''),
                   coalesce(publisher,''), coalesce(tags,'')
            FROM datasets WHERE key IN (SELECT key FROM temp.touched)
            """)
    conn.commit()
    conn.close()

    print(f"\ndeleted {len(drop):,} records, blanked {len(blank):,} descriptions")
    print("run embed_index.py and dedupe.py to rebuild what derives from them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
