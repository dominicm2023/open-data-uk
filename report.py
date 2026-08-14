"""Generate a data-quality report over the harvested index (index.db).

Usage:
    python report.py            # print to console and write quality_report.md
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
STALE_YEARS = 2


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> None:
    from paths import DB_PATH, connect as db_connect
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM datasets").fetchall()
    if not rows:
        print("index.db is empty — run harvester.py first")
        return

    now = datetime.now(timezone.utc)
    lines: list[str] = []
    out = lines.append

    out("# UK Open Data Index — data quality report")
    out("")
    out(f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')} over **{len(rows):,} datasets**.")
    out("")

    # --- per-source summary ------------------------------------------------
    out("## Per-source summary")
    out("")
    out("| Source | Datasets | No licence | No/short description | Zero resources | Stale (>2y) |")
    out("|---|---:|---:|---:|---:|---:|")

    by_source: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by_source.setdefault(r["source_id"], []).append(r)

    def stats(group: list[sqlite3.Row]) -> dict:
        n = len(group)
        no_lic = sum(1 for r in group if not r["license_norm"])
        no_desc = sum(1 for r in group
                      if not r["description"] or len(r["description"].strip()) < 50)
        no_res = sum(1 for r in group if not r["resource_count"])
        stale = 0
        for r in group:
            dt = parse_dt(r["modified"])
            if dt and (now - dt.replace(tzinfo=dt.tzinfo or timezone.utc)).days > 365 * STALE_YEARS:
                stale += 1
        return {"n": n, "no_lic": no_lic, "no_desc": no_desc,
                "no_res": no_res, "stale": stale}

    totals = Counter()
    for sid in sorted(by_source):
        s = stats(by_source[sid])
        totals.update(s)
        out(f"| {sid} | {s['n']:,} | {pct(s['no_lic'], s['n'])} "
            f"| {pct(s['no_desc'], s['n'])} | {pct(s['no_res'], s['n'])} "
            f"| {pct(s['stale'], s['n'])} |")
    out(f"| **all** | **{totals['n']:,}** | **{pct(totals['no_lic'], totals['n'])}** "
        f"| **{pct(totals['no_desc'], totals['n'])}** | **{pct(totals['no_res'], totals['n'])}** "
        f"| **{pct(totals['stale'], totals['n'])}** |")
    out("")

    # --- licences ----------------------------------------------------------
    out("## Licences (normalised)")
    out("")
    lic_counter = Counter((r["license_norm"] or "(none)") for r in rows)
    raw_variants = {r["license_raw"] for r in rows if r["license_raw"]}
    out(f"{len(raw_variants)} raw licence spellings collapse to "
        f"{len([k for k in lic_counter if k != '(none)'])} canonical licences.")
    out("")
    for lic, n in lic_counter.most_common(12):
        out(f"- {lic}: {n:,} ({pct(n, len(rows))})")
    out("")

    # --- formats -----------------------------------------------------------
    out("## Formats (normalised)")
    out("")
    fmt_counter: Counter = Counter()
    raw_fmt_variants: set[str] = set()
    for r in rows:
        fmt_counter.update(json.loads(r["formats_norm"]))
        raw_fmt_variants.update(json.loads(r["formats_raw"]))
    out(f"{len(raw_fmt_variants)} raw format spellings collapse to "
        f"{len(fmt_counter)} canonical formats. Top 15 (datasets offering each):")
    out("")
    for fmt, n in fmt_counter.most_common(15):
        out(f"- {fmt}: {n:,}")
    out("")

    # --- staleness ---------------------------------------------------------
    out("## Freshness")
    out("")
    buckets = Counter()
    for r in rows:
        dt = parse_dt(r["modified"])
        if not dt:
            buckets["unknown"] += 1
            continue
        age = (now - dt.replace(tzinfo=dt.tzinfo or timezone.utc)).days
        if age <= 90:
            buckets["<3 months"] += 1
        elif age <= 365:
            buckets["3-12 months"] += 1
        elif age <= 365 * 2:
            buckets["1-2 years"] += 1
        elif age <= 365 * 5:
            buckets["2-5 years"] += 1
        else:
            buckets[">5 years"] += 1
    for label in ["<3 months", "3-12 months", "1-2 years", "2-5 years", ">5 years", "unknown"]:
        if buckets[label]:
            out(f"- {label}: {buckets[label]:,} ({pct(buckets[label], len(rows))})")
    out("")

    # --- publishers --------------------------------------------------------
    out("## Publishers")
    out("")
    pub_counter = Counter(r["publisher"] or "(none)" for r in rows)
    out(f"{len(pub_counter):,} distinct publishers. Top 10:")
    out("")
    for pub, n in pub_counter.most_common(10):
        out(f"- {pub}: {n:,}")
    out("")

    report = "\n".join(lines)
    (ROOT / "quality_report.md").write_text(report, encoding="utf-8")
    print(report)
    print("\n(written to quality_report.md)")


if __name__ == "__main__":
    main()
