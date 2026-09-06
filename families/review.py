"""What a reviewer looks at before flipping a mapping to "reviewed".

Builds the family with proposals included, then prints — per proposed
source — the row count, the held count and the first reasons, the date and
value spans, and a few random rows. Nothing here changes a mapping: the
decision, and the edit that records it, stay with a person.

Usage:  DATA_DIR=... python families/review.py spend_over_500 [--all]
        --all shows reviewed sources too, for a re-check after a rebuild.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import STORE, build  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("family")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--rows", type=int, default=3)
    a = ap.parse_args()
    rep = build(a.family, include_proposed=True)
    out = STORE / "out" / a.family
    preview = json.loads((out / f"{a.family}.preview.json").read_text(encoding="utf-8"))
    published = json.loads((out / f"{a.family}.published.json").read_text(encoding="utf-8"))
    schema = json.loads((Path(__file__).resolve().parent / "schema" / f"{a.family}.json").read_text(encoding="utf-8"))
    show_cols = [c["name"] for c in schema["columns"]][:6]
    by_key: dict[str, list] = collections.defaultdict(list)
    for r in preview + (published if a.all else []):
        by_key[r["dataset_key"]].append(r)
    print(f"{a.family}: {rep['published_rows']:,} published, {rep['preview_rows']:,} in preview; ladder {rep['ladder']}\n")
    random.seed(1)
    for e in rep["sources"]:
        want = ("mapped (proposed)", "mapping failed") + (("published",) if a.all else ())
        if e["ladder"] not in want:
            continue
        print(f"{e['publisher']} — {e['title'][:60]}")
        print(f"   {e['ladder']}; files {e.get('files', 1)}; rows {e.get('rows')}; held {e.get('rows_failed_validation')}"
              + (f"; {e['failures_sample'][:2]}" if e.get("failures_sample") else "")
              + (f"; why: {e['why']}" if e.get("why") else ""))
        if e.get("notes"):
            print(f"   notes: {e['notes'][:220]}")
        rows = by_key.get(e["dataset_key"], [])
        for col in ("payment_date", "year", "as_of"):
            vals = sorted(str(r[col]) for r in rows if r.get(col) is not None)
            if vals:
                print(f"   {col}: {vals[0]} .. {vals[-1]}")
                break
        for col in ("amount_gbp", "annual_mean"):
            vals = [r[col] for r in rows if r.get(col) is not None]
            if vals:
                print(f"   {col}: {min(vals):,} .. {max(vals):,}")
                break
        for r in random.sample(rows, min(a.rows, len(rows))):
            print("   ", {c: r.get(c) for c in show_cols})
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
