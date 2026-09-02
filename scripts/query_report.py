"""What are people actually searching for, and where are we failing them?

Reads the anonymous query log (see querylog.py) and surfaces the things that
should drive the next round of relevance work — above all the searches that
came back weak, empty, or geographically unanswerable.

Usage:
    DATA_DIR=~/opendata-index/data python scripts/query_report.py [--days 7]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from querylog import LOG_PATH  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    if not LOG_PATH.exists():
        print(f"no query log yet at {LOG_PATH}")
        return 0
    conn = sqlite3.connect(LOG_PATH)
    conn.row_factory = sqlite3.Row
    since = f"-{args.days} days"
    rows = conn.execute(
        "SELECT * FROM queries WHERE ts > datetime('now', ?)", (since,)
    ).fetchall()
    if not rows:
        print(f"no queries logged in the last {args.days} days")
        return 0

    print(f"{len(rows):,} searches in the last {args.days} days\n")

    conf = Counter(r["confidence"] for r in rows)
    for level in ("strong", "weak", "none"):
        n = conf.get(level, 0)
        print(f"  {level:7} {n:>6,}  ({100 * n / len(rows):.0f}%)")

    def section(title: str, items) -> None:
        print(f"\n=== {title} ===")
        if not items:
            print("  (none)")
        for text, n in items:
            print(f"  {n:>4}x  {text}")

    # The whole point: what disappointed people.
    section("Weak / no match — these need better data or better ranking",
            Counter(r["query"] for r in rows
                    if r["confidence"] in ("weak", "none")).most_common(args.top))

    section("Returned nothing at all",
            Counter(r["query"] for r in rows if not r["n_results"]).most_common(args.top))

    section("Places asked about that we could not geolocate "
            "(gazetteer gaps, or somewhere we hold nothing)",
            Counter(r["query"] for r in rows
                    if r["place"] is None and " in " in (r["query"] or "")
                    ).most_common(args.top))

    section("Most common searches", Counter(r["query"] for r in rows).most_common(args.top))

    # A dataset that wins a lot of *weak* searches is usually a magnet bug.
    section("Datasets that top weak/none results (possible magnets)",
            Counter(r["top_key"] for r in rows
                    if r["confidence"] in ("weak", "none") and r["top_key"]
                    ).most_common(args.top))

    # Whether a search worked is not in the queries table: the result title
    # links off-site, so success used to leave no trace at all. Clicks are
    # recorded from 2026-09-02 on; older windows will show none.
    try:
        clicks = conn.execute(
            "SELECT query, key, rank, kind FROM clicks WHERE ts > datetime('now', ?)",
            (since,)).fetchall()
    except sqlite3.OperationalError:
        clicks = []
    # Only searches typed in the site's own box can produce a click, so the
    # rate is over those, not over the health checks and test suites.
    human = [r for r in rows if r["k"] == 15]
    answered = {c["query"] for c in clicks}
    print()
    print(f"{len(human):,} searches from the site's search box, "
          f"{len(clicks):,} results opened; "
          f"{len({r['query'] for r in human} & answered)} of "
          f"{len({r['query'] for r in human})} distinct searches led somewhere")
    section("Ranks people opened (1 means the top result was the answer)",
            Counter(str(c["rank"]) for c in clicks).most_common(args.top))
    section("Searched from the box, opened nothing — look at these first",
            Counter(r["query"] for r in human
                    if r["query"] not in answered).most_common(args.top))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
