"""Build the manifest of organogram CSVs worth fetching.

Every UK department, agency and a good many councils have published an
"organogram" twice a year since the 2010 transparency agenda: two CSVs per
edition, one naming senior posts with their pay bands and who they report
to, one aggregating junior posts into payscale ranges and FTE counts. The
schema is mandated, which is what makes 227 separately-published files
joinable at all.

This step only decides what to fetch. It reads the index for organogram
resources, works out for each one whether it is the senior or junior half
and which edition it belongs to, and writes a manifest. Nothing is
downloaded here, so it is cheap to re-run while the rules are being tuned.

Usage:  python analysis/organograms/01_discover.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from paths import connect  # noqa: E402

OUT = Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)

# An edition date, however the publisher chose to write it into the URL or
# the resource name. The transparency releases are pinned to 31 March and
# 30 September, but plenty of files carry only a month or a year.
_DATE_PATTERNS = (
    re.compile(r"(20\d{2})[-_/]?(0[1-9]|1[0-2])[-_/]?(0[1-9]|[12]\d|3[01])"),
    re.compile(r"(20\d{2})[-_/](0[1-9]|1[0-2])"),
    re.compile(r"\b(20\d{2})\b"),
)


def edition(text: str) -> str | None:
    """The edition this file belongs to, as far into a date as we can read."""
    for pattern in _DATE_PATTERNS:
        if m := pattern.search(text):
            return "-".join(g for g in m.groups() if g)
    return None


def half(text: str) -> str | None:
    """Senior or junior. Anything ambiguous is left out rather than guessed:
    parsing a junior file with the senior schema silently produces rubbish."""
    low = text.lower()
    senior = re.search(r"senior|\bsen[-_]|top[-_ ]?post", low)
    junior = re.search(r"junior|\bjun[-_]|sub[-_ ]?post", low)
    if senior and not junior:
        return "senior"
    if junior and not senior:
        return "junior"
    return None


def main() -> int:
    conn = connect()
    rows = conn.execute(
        """SELECT d.key, d.publisher, d.title, d.source_id,
                  r.url, r.name, r.format_norm, c.verdict
           FROM datasets d
           JOIN resources r ON r.dataset_key = d.key
           LEFT JOIN resource_checks c ON c.url = r.url
           WHERE LOWER(d.title) LIKE '%organogram%'
             AND NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
             AND NOT EXISTS (SELECT 1 FROM retired t WHERE t.key = d.key)"""
    ).fetchall()
    conn.close()

    manifest, skipped = [], Counter()
    for key, publisher, title, source, url, name, fmt, verdict in rows:
        if (fmt or "").upper() != "CSV":
            skipped[f"not a CSV ({fmt})"] += 1
            continue
        # The checker already told us which links answer. No point queueing a
        # fetch for one we have watched fail.
        if verdict in ("dead", "unreachable"):
            skipped[f"link {verdict}"] += 1
            continue
        blob = f"{name or ''} {url}"
        side = half(blob)
        if not side:
            skipped["cannot tell senior from junior"] += 1
            continue
        manifest.append({
            "dataset_key": key, "publisher": publisher, "source": source,
            "url": url, "resource_name": name or "", "half": side,
            "edition": edition(blob) or "",
        })

    # One row per (publisher, half, edition): publishers re-list the same
    # file across several dataset records, and fetching it four times is
    # rude to them and pointless for us.
    seen, deduped = set(), []
    for row in manifest:
        sig = (row["publisher"], row["half"], row["edition"], row["url"])
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(row)

    with open(OUT / "manifest.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(deduped[0]))
        w.writeheader()
        w.writerows(deduped)
    (OUT / "discover_summary.json").write_text(
        json.dumps({"queued": len(deduped), "skipped": dict(skipped)}, indent=1),
        encoding="utf-8")

    eds = Counter(r["edition"][:4] for r in deduped if r["edition"])
    print(f"{len(rows):,} organogram resources in the index")
    for reason, n in skipped.most_common():
        print(f"   skipped {n:>5,}  {reason}")
    print(f"\n{len(deduped):,} queued for fetch")
    print(f"   senior {sum(1 for r in deduped if r['half']=='senior'):,}"
          f"   junior {sum(1 for r in deduped if r['half']=='junior'):,}")
    print(f"   distinct publishers: {len({r['publisher'] for r in deduped}):,}")
    print(f"   no edition date readable: "
          f"{sum(1 for r in deduped if not r['edition']):,}")
    print("   by year:", dict(sorted(eds.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
