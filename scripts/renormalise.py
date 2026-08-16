"""Re-apply normalise.py to an index that is already built.

Normalisation rules improve — a new licence spelling gets recognised, a
format alias gets added — and until now the only way to apply that was to
re-harvest all 51 sources, which takes far longer and asks every publisher
for data we already hold.

This re-derives the normalised columns from the raw ones we stored alongside
them. No network, no publishers bothered, a few seconds.

    python scripts/renormalise.py --dry-run    # what would change
    python scripts/renormalise.py              # change it
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from normalise import norm_formats, norm_license  # noqa: E402
from paths import connect as db_connect  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = db_connect()
    rows = conn.execute(
        "SELECT key, license_raw, license_norm, formats_raw, formats_norm "
        "FROM datasets").fetchall()

    lic_changes, fmt_changes = [], []
    moved: Counter = Counter()
    for key, lic_raw, lic_norm, fmt_raw, fmt_norm in rows:
        new_lic = norm_license(lic_raw)
        if new_lic != lic_norm:
            lic_changes.append((new_lic, key))
            moved[f"{lic_norm} -> {new_lic}"] += 1
        try:
            new_fmt = json.dumps(norm_formats(json.loads(fmt_raw or "[]")))
        except (TypeError, ValueError):
            new_fmt = fmt_norm
        if new_fmt != fmt_norm:
            fmt_changes.append((new_fmt, key))

    print(f"{len(rows):,} datasets")
    print(f"  licence  : {len(lic_changes):,} would change")
    print(f"  formats  : {len(fmt_changes):,} would change")
    if moved:
        print("\nlicence moves:")
        for label, n in moved.most_common(12):
            print(f"   {n:>6,}  {label}")

    if args.dry_run:
        print("\ndry run — nothing written")
    else:
        conn.executemany("UPDATE datasets SET license_norm = ? WHERE key = ?",
                         lic_changes)
        conn.executemany("UPDATE datasets SET formats_norm = ? WHERE key = ?",
                         fmt_changes)
        conn.commit()
        print(f"\nupdated {len(lic_changes) + len(fmt_changes):,} rows")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
