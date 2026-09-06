"""Write the mapping brief for a family: what each extracted source looks like.

One JSON per family, one entry per source that reached `needs_review`:
the header row, a few sample rows, the row count, the publisher and title,
and the family schema — everything a person (or a model working for one)
needs to propose which source column feeds which schema column, and
nothing they do not. No network; reads the intake's stored tables.

The proposals come back as families/registry/<family>.mappings.json, in the
shape build.py reads (see its docstring). Every proposal starts as
"proposed"; a person marks it "reviewed" before build.py will publish it.

Usage:  DATA_DIR=... python families/brief.py recycling_centres
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paths import DATA_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
STORE = DATA_DIR / "families"
SAMPLE_ROWS = 6
MAX_COLS = 60


def _preview(table: dict) -> dict:
    rows = table["rows"]
    header = [str(h) if h is not None else "" for h in (rows[0] if rows else [])][:MAX_COLS]
    body = [[("" if v is None else str(v))[:80] for v in r[:MAX_COLS]] for r in rows[1:1 + SAMPLE_ROWS]]
    where = {k: v for k, v in table.items() if k != "rows"}
    return {"where": where, "header": header, "sample_rows": body, "row_count": max(len(rows) - 1, 0),
            "column_count": max((len(r) for r in rows), default=0)}


def build(family: str) -> dict:
    schema = json.loads((HERE / "schema" / f"{family}.json").read_text(encoding="utf-8"))
    c = sqlite3.connect(f"file:{STORE / 'families.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    entries = []
    for j in c.execute("SELECT * FROM jobs WHERE family=? AND state='needs_review' ORDER BY publisher", (family,)):
        doc = json.loads((STORE / "tables" / j["extraction_sha"]).read_text(encoding="utf-8"))
        try:
            n_files = c.execute("SELECT COUNT(*) FROM files WHERE job_id=? AND state='extracted'", (j["id"],)).fetchone()[0]
        except sqlite3.OperationalError:
            n_files = 1
        entries.append({
            "job_id": j["id"], "publisher": j["publisher"], "title": j["title"], "portal": j["portal"],
            "format": j["format"], "resource_url": j["resource_url"], "licence": json.loads(j["licence_json"])["id"],
            "files_extracted": n_files,
            "note": ("This dataset has several files; the tables shown are from the first. One mapping "
                     "applies to all of them.") if n_files > 1 else None,
            "tables": [_preview(t) for t in doc["tables"][:8]],
        })
    c.close()
    brief = {"family": family, "schema": schema, "sources": entries,
             "instructions": (
                 "For each source, propose which source column supplies each schema column. Use the "
                 "exact header text. Leave a schema column out if the source has nothing for it — never "
                 "guess. If coordinates are eastings/northings, map them to 'easting' and 'northing' and "
                 "build.py will convert. If a wide table has one column per year, give 'unpivot'. If the "
                 "table is not this family at all (a different subject, a summary, a lookup), say so in "
                 "'reject' with a reason. Note anything a reviewer must check in 'notes'.")}
    out = HERE / "registry" / f"{family}.brief.json"
    out.write_text(json.dumps(brief, indent=1, ensure_ascii=False), encoding="utf-8")
    return brief


if __name__ == "__main__":
    for fam in sys.argv[1:]:
        b = build(fam)
        print(f"{fam}: {len(b['sources'])} sources briefed -> registry/{fam}.brief.json")
