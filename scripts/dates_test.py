"""Regression tests for date normalisation, and an audit of the built index.

A date column is only useful if every value in it is a date. Ours wasn't:
17,041 of 106,626 `modified` values — one in six — were epoch milliseconds,
a time fragment, or an unrendered ArcGIS template. Nothing failed, because
the column is text and text sorts: a dataset updated last month simply read
as the year 1786, and the freshness figures were computed over it anyway.

The unit cases below need no database and run on every push. The audit at
the end needs index.db and is skipped without one, so CI stays offline.

Usage:
    python scripts/dates_test.py           # unit cases (+ audit if index.db)
    python scripts/dates_test.py --audit   # audit only, fail if the DB is bad
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from normalise import DATE_FLOOR_YEAR, norm_date  # noqa: E402

failures: list[str] = []

# Fixed, so the window cases below mean the same thing in 2030 as today.
NOW = datetime(2026, 8, 17, tzinfo=timezone.utc)


def check(got, want, label: str) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}"
          f"{'' if ok else f'  (got {got!r}, wanted {want!r})'}")
    if not ok:
        failures.append(label)


# --- epoch timestamps are converted, not read as years -------------------
# The ArcGIS Hub DCAT feeds report `modified` as epoch milliseconds. Stored
# verbatim, 1786367211609 reads as the year 1786 — the single biggest cause,
# 15,559 rows across 40-odd agol_* sources.
check(norm_date("1786367211609", NOW), "2026-08-10T13:06:51Z",
      "epoch milliseconds become a real date, not the year 1786")
check(norm_date("1755000000", NOW), "2025-08-12T12:00:00Z",
      "epoch seconds become a real date, not the year 1755")
# 1900-01-01 as epoch ms: a sentinel three City of London layers use for
# "no date". It converts cleanly and is still not a date anyone meant.
check(norm_date("-2208988800000", NOW), None,
      "the 1900 no-date sentinel is dropped rather than converted")

# --- values that are not dates at all ------------------------------------
check(norm_date("{{modified:toISO}}", NOW), None,
      "an unrendered ArcGIS template is not a date")
check(norm_date("18:15", NOW), None,
      "a Cefas timestamp cut at its colon is not a date")
check(norm_date("00:00.000Z", NOW), None,
      "a cut Cefas created-date is not a date")
check(norm_date(None, NOW), None, "absent date stays absent")
check(norm_date("", NOW), None, "empty date stays absent")
check(norm_date("   ", NOW), None, "whitespace is not a date")

# --- real dates survive untouched ----------------------------------------
# Six portal families, six spellings. None may be rewritten: the column is
# compared and sliced as text elsewhere, so churn here would move rankings.
for spelling in ("2026-07-15T10:14:34.432215", "2017-10-10T13:14:00.000Z",
                 "2024-10-01T15:17:06Z", "2026-08-16",
                 "2026-08-11T20:38:20.378000+00:00",
                 "2019-10-29 10:09:31.747"):
    check(norm_date(spelling, NOW), spelling, f"{spelling!r} passes through")
# Truncated, but true — and it still sorts and slices correctly.
check(norm_date("2018-12", NOW), "2018-12", "a year-month is kept")

# --- the plausibility window ---------------------------------------------
check(norm_date("1989-12-31", NOW), None,
      f"a record older than {DATE_FLOOR_YEAR} is not a catalogue timestamp")
check(norm_date(f"{DATE_FLOOR_YEAR}-01-01", NOW), f"{DATE_FLOOR_YEAR}-01-01",
      "the floor year itself is kept")
# Next year is allowed: publishers post-date records, and clock skew around
# New Year shouldn't null a good date.
check(norm_date("2027-03-01", NOW), "2027-03-01", "next year is allowed")
check(norm_date("2028-01-01", NOW), None, "two years out is not")


# --- audit: no stored date may fail the rule above ------------------------

def audit() -> int:
    """Re-run the rule over every stored date. Returns the number of bad ones."""
    from paths import DB_PATH, connect as db_connect

    if not Path(DB_PATH).exists():
        print(f"\nno index.db at {DB_PATH} — skipping the audit")
        return 0

    conn = db_connect()
    bad = 0
    print()
    for column in ("modified", "created"):
        rows = conn.execute(
            f"SELECT source_id, key, {column} FROM datasets "
            f"WHERE {column} IS NOT NULL").fetchall()
        offenders = [(s, k, v) for s, k, v in rows if norm_date(v) is None]
        bad += len(offenders)
        verdict = "FAIL" if offenders else "PASS"
        print(f"{verdict}  every stored {column} is a date "
              f"({len(rows):,} values, {len(offenders):,} bad)")
        by_source: dict[str, tuple[int, str]] = {}
        for source_id, _key, value in offenders:
            count, example = by_source.get(source_id, (0, value))
            by_source[source_id] = (count + 1, example)
        for source_id, (count, example) in sorted(
                by_source.items(), key=lambda kv: -kv[1][0])[:10]:
            print(f"        {source_id}: {count:,}  e.g. {example!r}")
    conn.close()
    return bad


if __name__ == "__main__":
    audit_only = "--audit" in sys.argv
    if audit_only:
        failures = []
    else:
        print()
    if audit() and audit_only:
        failures.append("stored dates")

    print()
    print("all date rules hold" if not failures
          else f"{len(failures)} failure(s): " + "; ".join(failures))
    sys.exit(1 if failures else 0)
