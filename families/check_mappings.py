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
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWED = {"status", "reject", "table", "header_row", "columns", "constants", "unpivot",
           "notes", "version", "reviewer", "reviewed_at", "grid", "alt_columns", "filter"}
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
    problems, mapped, rejected, notes = [], 0, 0, []
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
        if table is None and isinstance(which, int) and 0 < which <= len(src["tables"]):
            table = src["tables"][which - 1]          # the build reads an XLSX's nth sheet the same way
        if table is None:
            problems.append(f"{tag}: table {which!r} not in brief"); continue
        header = [str(h).strip() for h in table["header"]]
        # A header on a later row: the brief's sample rows show it, and the
        # build reads it from there. Compare against the same row.
        hr = int(spec.get("header_row", 0) or 0)
        if hr > 0:
            if hr - 1 < len(table["sample_rows"]):
                header = [str(x).strip() for x in table["sample_rows"][hr - 1]]
            else:
                problems.append(f"{tag}: header_row {hr} beyond the sampled rows; cannot check"); continue
        cols = {k: str(v).strip() for k, v in spec.get("columns", {}).items()}
        # A series carries several layouts; a name is fine if any layout in
        # the brief (its header, or a row just under a title line) has it.
        known = {h.strip().lower() for h in header}
        for lay in src.get("layouts") or []:
            known |= {str(h).strip().lower() for h in lay.get("header", [])}
            for r in lay.get("sample_rows", [])[:3]:
                known |= {str(h).strip().lower() for h in r}
        for t in src["tables"]:
            for r in t.get("sample_rows", [])[:3]:
                known |= {str(h).strip().lower() for h in r}
        flt = spec.get("filter")
        if flt:
            if not isinstance(flt, dict) or not flt.get("column") or not flt.get("match"):
                problems.append(f"{tag}: filter needs 'column' and 'match'")
            elif str(flt["column"]).strip().lower() not in known:
                problems.append(f"{tag}: filter column {flt['column']!r} not found in any layout")
            else:
                try:
                    re.compile(flt["match"])
                except re.error as err:
                    problems.append(f"{tag}: filter pattern does not compile: {err}")
        layouts = [cols] + [{k: str(v).strip() for k, v in alt.items()} for alt in spec.get("alt_columns", [])]
        for n, lay in enumerate(layouts):
            for target, source_col in lay.items():
                if target not in names:
                    problems.append(f"{tag}: unknown schema column {target!r}")
                if source_col.lower() not in known:
                    if n and not src.get("layouts"):
                        # an alternate layout for a block *inside* one file: the
                        # brief cannot show it, so this is a note, not a fault
                        notes.append(f"{tag}: alt layout names {source_col!r}, unseen in the brief (in-file block?)")
                    else:
                        problems.append(f"{tag}: header {source_col!r} not found in any layout")
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
    for n in notes[:6]:
        print("  ~", n)
    for jid in list(unmapped)[:10]:
        print("  ? no proposal:", sources[jid]["publisher"][:40], "-", sources[jid]["title"][:40])
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(max(check(f) for f in sys.argv[1:]))
