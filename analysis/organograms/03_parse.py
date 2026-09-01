"""Parse the fetched organogram CSVs into one queryable corpus.

The schema is mandated, which is the only reason 262 publishers over 15
years can be joined at all — but "mandated" is not "obeyed". Headers arrive
with different capitalisation, stray currency symbols, "(£)" appended or
not, and occasional renamings. Everything funnels through one header map so
a column means the same thing whichever body wrote it.

Two shapes:

  senior  one row per named post: grade, job title, pay floor and ceiling,
          who it reports to, and the total salary cost of everything
          beneath it. This is the tree.
  junior  one row per (grade, generic job title): payscale range and how
          many full-time-equivalent posts sit in it. This is the base of
          the pyramid, and the reason a top-to-bottom pay ratio can be
          computed from an organisation's own published figures.

Pay is stored as pence-free integers and only when it reads as a number.
"N/D", "N/A", blanks and prose are dropped rather than coerced: a salary
that is actually a shrug must not come out as zero, because zero would be
averaged.

Usage:  python analysis/organograms/03_parse.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
RAW = HERE / "raw"
DB = HERE / "organograms.sqlite"

csv.field_size_limit(10 * 1024 * 1024)

SCHEMA = """
DROP TABLE IF EXISTS senior;
CREATE TABLE senior (
    publisher TEXT, edition TEXT, source_url TEXT,
    post_ref TEXT, name TEXT, grade TEXT, job_title TEXT,
    unit TEXT, organisation TEXT, parent_department TEXT,
    reports_to TEXT, prof_group TEXT,
    pay_floor INTEGER, pay_ceiling INTEGER, reports_salary_cost INTEGER,
    fte REAL
);
DROP TABLE IF EXISTS junior;
CREATE TABLE junior (
    publisher TEXT, edition TEXT, source_url TEXT,
    reporting_senior_post TEXT, grade TEXT, generic_job_title TEXT,
    unit TEXT, organisation TEXT, parent_department TEXT, prof_group TEXT,
    payscale_min INTEGER, payscale_max INTEGER, posts_fte REAL
);
CREATE INDEX idx_senior_pub ON senior (publisher, edition);
CREATE INDEX idx_junior_pub ON junior (publisher, edition);
CREATE INDEX idx_senior_ref ON senior (publisher, edition, post_ref);
"""

# One canonical name per column, and every spelling seen in the wild that
# means it. Matching is done on a squashed form (lower-case, letters and
# digits only), so punctuation and the "(£)" suffix stop mattering.
FIELDS: dict[str, tuple[str, ...]] = {
    "post_ref": ("postuniquereference", "postref", "uniquepostreference"),
    "name": ("name", "postholder", "postholdername"),
    "grade": ("gradeorequivalent", "grade"),
    "job_title": ("jobtitle", "posttitle"),
    "job_function": ("jobteamfunction", "jobfunction", "teamfunction"),
    "unit": ("unit", "team", "businessunit"),
    "organisation": ("organisation", "organization", "body"),
    "parent_department": ("parentdepartment", "department"),
    "reports_to": ("reportstoseniorpost", "reportsto", "reportingseniorpost"),
    "prof_group": ("professionaloccupationalgroup", "professionalgroup",
                   "occupationalgroup"),
    "pay_floor": ("actualpayfloor", "actualpayfloor", "salarycostfloor",
                  "actualpayfloorfulltimeequivalent"),
    "pay_ceiling": ("actualpayceiling", "salarycostceiling",
                    "actualpayceilingfulltimeequivalent"),
    "reports_salary_cost": ("salarycostofreports", "salarycostofreport"),
    "fte": ("fte", "fulltimeequivalent"),
    "payscale_min": ("payscaleminimum", "payscalemin", "payrangeminimum"),
    "payscale_max": ("payscalemaximum", "payscalemax", "payrangemaximum"),
    "generic_job_title": ("genericjobtitle", "jobtitle", "generictitle"),
    "posts_fte": ("numberofpostsinfte", "numberofposts", "postsinfte"),
}
_LOOKUP = {spelling: field
           for field, spellings in FIELDS.items() for spelling in spellings}


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def money(value: str) -> int | None:
    """Pounds as an integer, or None when the cell is not a number.

    Organograms are full of "N/D", "N/A", "0" meaning unknown, and prose.
    Only a genuine figure survives; everything else stays absent so it can
    be excluded from an average rather than dragging one down.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("£", "")
    text = re.sub(r"\.00?$", "", text)
    if not re.fullmatch(r"-?\d{1,9}", text):
        return None
    n = int(text)
    # A salary of zero is a placeholder, not a fact, and a negative one is a
    # typo. Neither belongs in a distribution.
    return n if 0 < n < 5_000_000 else None


def number(value: str) -> float | None:
    try:
        n = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return n if 0 <= n < 1_000_000 else None


def read_rows(path: Path) -> list[dict]:
    """The CSV as canonical-named dicts, or [] if the header isn't one."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, OSError):
            continue
    else:
        return []
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        return []
    mapping = {i: _LOOKUP[squash(h)] for i, h in enumerate(header)
               if squash(h) in _LOOKUP}
    if len(mapping) < 3:
        return []
    out = []
    for raw in reader:
        row = {mapping[i]: raw[i] for i in mapping if i < len(raw)}
        if any((v or "").strip() for v in row.values()):
            out.append(row)
    return out


def main() -> int:
    manifest = list(csv.DictReader(open(HERE / "manifest.csv", encoding="utf-8")))
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    stats = Counter()
    sen_rows, jun_rows = [], []
    for entry in manifest:
        path = RAW / (hashlib.sha1(entry["url"].encode("utf-8")).hexdigest() + ".csv")
        if not path.exists() or path.stat().st_size == 0:
            stats["not fetched"] += 1
            continue
        rows = read_rows(path)
        if not rows:
            stats["header not recognised"] += 1
            continue
        pub, ed, url = entry["publisher"], entry["edition"], entry["url"]
        if entry["half"] == "senior":
            for r in rows:
                sen_rows.append((
                    pub, ed, url, r.get("post_ref"), r.get("name"),
                    r.get("grade"), r.get("job_title"), r.get("unit"),
                    r.get("organisation"), r.get("parent_department"),
                    r.get("reports_to"), r.get("prof_group"),
                    money(r.get("pay_floor")), money(r.get("pay_ceiling")),
                    money(r.get("reports_salary_cost")), number(r.get("fte"))))
            stats["senior files"] += 1
        else:
            for r in rows:
                jun_rows.append((
                    pub, ed, url, r.get("reports_to"), r.get("grade"),
                    r.get("generic_job_title") or r.get("job_title"),
                    r.get("unit"), r.get("organisation"),
                    r.get("parent_department"), r.get("prof_group"),
                    money(r.get("payscale_min")), money(r.get("payscale_max")),
                    number(r.get("posts_fte"))))
            stats["junior files"] += 1

    conn.executemany(f"INSERT INTO senior VALUES ({','.join('?' * 16)})", sen_rows)
    conn.executemany(f"INSERT INTO junior VALUES ({','.join('?' * 13)})", jun_rows)
    conn.commit()

    print(f"{len(manifest):,} manifest entries")
    for k, v in stats.most_common():
        print(f"   {v:>6,}  {k}")
    print(f"\nsenior posts: {len(sen_rows):,}   junior rows: {len(jun_rows):,}")
    q = lambda s: conn.execute(s).fetchone()[0]  # noqa: E731
    print(f"publishers: {q('SELECT COUNT(DISTINCT publisher) FROM senior'):,}"
          f"   editions: {q('SELECT COUNT(DISTINCT edition) FROM senior'):,}")
    print(f"senior with a pay floor: {q('SELECT COUNT(*) FROM senior WHERE pay_floor IS NOT NULL'):,}")
    reports_to_q = ("SELECT COUNT(*) FROM senior WHERE reports_to IS NOT NULL "
                    "AND TRIM(reports_to) != ''")
    print(f"senior with a reports-to: {q(reports_to_q):,}")
    print(f"junior with a payscale:  {q('SELECT COUNT(*) FROM junior WHERE payscale_min IS NOT NULL'):,}")
    (HERE / "parse_summary.json").write_text(
        json.dumps({"stats": dict(stats), "senior": len(sen_rows),
                    "junior": len(jun_rows)}, indent=1), encoding="utf-8")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
