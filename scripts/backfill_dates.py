"""Re-apply norm_date to an index that was built before it existed.

One `modified` value in six was not a date: epoch milliseconds from the
ArcGIS Hub feeds, Cefas timestamps cut at their first colon, and an ArcGIS
template the portal never rendered. See normalise.norm_date for the shapes.

Only the epoch values carry enough information to recover. The rest are set
to NULL: the date is genuinely not in the column any more, and a missing
date is something the freshness stats and the dataset page both handle
honestly, where a wrong one is silently believed.

The cut Cefas dates *are* recoverable — from Cefas, by re-harvesting that
source once the flatten_bag fix is in place:

    python harvester.py --source cefas

No network here, and no publisher bothered.

    python scripts/backfill_dates.py --dry-run    # what would change
    python scripts/backfill_dates.py              # change it
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from normalise import norm_date  # noqa: E402
from paths import connect as db_connect  # noqa: E402

COLUMNS = ("modified", "created")


def shape(value: str) -> str:
    """A value's family, for reporting: digits collapsed, so '18:15' -> '99:99'."""
    return "".join("9" if ch.isdigit() else ch for ch in value)[:24]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = db_connect()
    total_fixed = total_cleared = 0

    for column in COLUMNS:
        rows = conn.execute(
            f"SELECT key, source_id, {column} FROM datasets "
            f"WHERE {column} IS NOT NULL").fetchall()
        changes: list[tuple[str | None, str]] = []
        fixed: Counter = Counter()
        cleared: Counter = Counter()
        for key, source_id, old in rows:
            new = norm_date(old)
            if new == old:
                continue
            changes.append((new, key))
            (fixed if new else cleared)[(source_id, shape(old))] += 1

        n_fixed = sum(fixed.values())
        n_cleared = sum(cleared.values())
        total_fixed += n_fixed
        total_cleared += n_cleared
        print(f"\n{column}: {len(rows):,} stored, {n_fixed:,} recovered, "
              f"{n_cleared:,} cleared to NULL")
        for label, counter in (("recovered", fixed), ("cleared", cleared)):
            for (source_id, form), n in counter.most_common(8):
                print(f"    {label:9} {n:6,}  {source_id}  {form}")

        if changes and not args.dry_run:
            conn.executemany(
                f"UPDATE datasets SET {column} = ? WHERE key = ?", changes)

    if args.dry_run:
        print(f"\ndry run — {total_fixed:,} would be recovered, "
              f"{total_cleared:,} cleared")
    else:
        conn.commit()
        print(f"\n{total_fixed:,} recovered, {total_cleared:,} cleared to NULL")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
