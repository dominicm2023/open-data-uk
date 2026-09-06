"""Check proposed mappings against the brief before anything is built.

A proposal is only as good as its headers: every source column it names
must exist, character for character, in the table it points at; every
required schema column must be supplied by a column, a constant or an
unpivot; and the keys must be ones build.py understands. This catches the
mistakes a model makes most — a header paraphrased, a required column
quietly skipped — before they cost a build.

Usage:  python families/check_mappings.py recycling_centres
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWED = {"status", "reject", "table", "header_row", "columns", "constants", "unpivot",
           "notes", "version", "reviewer", "reviewed_at", "grid"}
EXTRA_COLS = {"easting", "northing"}


def check(family: str) -> int:
    brief = json.loads((HERE / "registry" / f"{family}.brief.json").read_text(encoding="utf-8"))
    mp = HERE / "registry" / f"{family}.mappings.json"
    if not mp.exists():
        print(f"{family}: no mappings file yet")
        return 1
    mappings = json.loads(mp.read_text(encoding="utf-8"))
    schema = brief["schema"]
    required = {c["name"] for c in schema["columns"] if c["required"]}
    names = {c["name"] for c in schema["columns"]} | EXTRA_COLS
    sources = {s["job_id"]: s for s in brief["sources"]}
    problems, mapped, rejected = [], 0, 0
    for jid, spec in mappings.items():
        src = sources.get(jid)
        tag = f"{(src or {}).get('publisher', '?')[:30]} [{jid[:8]}]"
        if not src:
            problems.append(f"{tag}: job id not in brief"); continue
        bad_keys = set(spec) - ALLOWED
        if bad_keys:
            problems.append(f"{tag}: unknown keys {sorted(bad_keys)}")
        if spec.get("status") == "rejected":
            rejected += 1
            if not spec.get("reject"):
                problems.append(f"{tag}: rejected without a reason")
            continue
        mapped += 1
        which = spec.get("table", 1)
        table = next((t for t in src["tables"] if which in (t["where"].get("table"), t["where"].get("sheet"))), None)
        if table is None:
            problems.append(f"{tag}: table {which!r} not in brief"); continue
        header = table["header"]
        # A header on a later row: the brief's sample rows show it, and the
        # build reads it from there. Compare against the same row.
        hr = int(spec.get("header_row", 0) or 0)
        if hr > 0:
            if hr - 1 < len(table["sample_rows"]):
                header = [str(x).strip() for x in table["sample_rows"][hr - 1]]
            else:
                problems.append(f"{tag}: header_row {hr} beyond the sampled rows; cannot check"); continue
        cols = {k: str(v).strip() for k, v in spec.get("columns", {}).items()}
        for target, source_col in cols.items():
            if target not in names:
                problems.append(f"{tag}: unknown schema column {target!r}")
            if source_col not in header:
                near = [h for h in header if h.strip().lower() == str(source_col).strip().lower()]
                problems.append(f"{tag}: header {source_col!r} not found" + (f" (did you mean {near[0]!r}?)" if near else ""))
        supplied = set(cols) | set(spec.get("constants", {}))
        up = spec.get("unpivot")
        if up:
            supplied |= {up.get("key_to"), up.get("value_to")} | set(up.get("id_columns", {}))
            missing_years = [y for y in up.get("year_columns", []) if y not in header]
            if missing_years:
                problems.append(f"{tag}: unpivot year columns not in header: {missing_years[:4]}")
        if ("easting" in cols) != ("northing" in cols):
            problems.append(f"{tag}: easting/northing must be mapped together")
        if "easting" in cols and "lon" in cols:
            problems.append(f"{tag}: both BNG and lon/lat mapped")
        missing = required - supplied
        if missing:
            problems.append(f"{tag}: required columns not supplied: {sorted(missing)}")
    unmapped = set(sources) - set(mappings)
    print(f"{family}: {mapped} mapped, {rejected} rejected, {len(unmapped)} sources without a proposal, {len(problems)} problems")
    for p in problems:
        print("  !", p)
    for jid in list(unmapped)[:10]:
        print("  ? no proposal:", sources[jid]["publisher"][:40], "-", sources[jid]["title"][:40])
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(max(check(f) for f in sys.argv[1:]))
