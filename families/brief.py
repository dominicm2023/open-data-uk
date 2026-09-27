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
import re
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


def _header_row(rows: list) -> int:
    """The first row that looks like a header: three or more filled cells
    within the first few rows. Wirral's returns open with a one-cell title
    line naming the month; that line is not the layout."""
    for i, r in enumerate(rows[:6]):
        if sum(1 for x in r if x not in (None, "") and str(x).strip()) >= 3:
            return i
    return 0


# The brief is committed to a public repository, and its sample rows are the
# publisher's own rows. A family that does not carry people must not carry
# them here either: the organograms brief held 3,211 sample rows with a name,
# a work e-mail or a phone number in them until 27 Sep 2026. A schema may
# name the columns never to sample ("never_sample": patterns on the header),
# or say the family's rows are not to be sampled at all ("brief_samples":
# false), which is what a register of addresses needs. Headers always stay:
# a column's name is not anybody's.
_HIDE: list = []
_SAMPLES = True
HIDDEN = "(not sampled)"
# Where no rows are sampled, a header on a later row (under a title line)
# must still be checkable. The first rows are shown only where the whole row
# reads as column names: no postcode, date or number in it, and most of its
# filled cells made of header words. Any other row comes through empty, so
# a holder's or company's name in a data row never reaches the brief.
_HEAD_WORD = re.compile(r"address|post\s*code|postcode|licen|date|occup|person|people|storey|floor|holder|manag|type|"
                        r"number|no\.?\b|reference|ref\b|expir|issue|start|end|status|household|categor|property|"
                        r"premises|ward|description|agent|owner|valid|renew|name|room|kitchen|bath|toilet|amenit|condition|"
                        r"duration|commenc|scheme|area|council|register", re.I)
_DATA = re.compile(r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}\b|\d{1,4}[/.-]\d{1,2}[/.-]\d{2,4}|"
                   r"\b(?:ltd|limited|llp|plc|group|trust|estates?|lettings|homes|mr|mrs|ms|miss|dr)\b", re.I)


def _head_rows(rows: list) -> list:
    out = []
    for r in rows[:10]:
        cells = [("" if v is None else str(v)).strip() for v in r[:MAX_COLS]]
        filled = [c for c in cells if c and c != "None"]
        heady = [c for c in filled if _HEAD_WORD.search(c) and not re.search(r"\d{3,}", c) and len(c) < 80]
        # A table's header names several columns; a card's row is one label
        # beside one value ("Licence holder" | a name). Three column names at
        # least, a majority of the row, and every other cell blanked.
        ok = len(heady) >= 3 and len(heady) * 2 >= len(filled) and not any(_DATA.search(c) for c in filled)
        out.append([c if c in heady else "" for c in cells] if ok else [])
    return out


def _preview(table: dict) -> dict:
    rows = table["rows"]
    hr = _header_row(rows)
    header = [str(h) if h is not None else "" for h in (rows[hr] if rows else [])][:MAX_COLS]
    body = [[("" if v is None else str(v))[:80] for v in r[:MAX_COLS]] for r in rows[hr + 1:hr + 1 + SAMPLE_ROWS]]
    head_rows = None
    if not _SAMPLES:
        body = []
        head_rows = _head_rows(rows)
    elif _HIDE:
        hide = {i for i, h in enumerate(header) if any(p.search(h.strip()) for p in _HIDE)}
        body = [[(HIDDEN if i in hide and v.strip() else v) for i, v in enumerate(r)] for r in body]
    where = {k: v for k, v in table.items() if k != "rows"}
    extra = {"head_rows": head_rows} if head_rows is not None else {}
    return {**extra, "where": where, "header": header, "header_row": hr, "sample_rows": body,
            "row_count": max(len(rows) - hr - 1, 0), "column_count": max((len(r) for r in rows), default=0)}


def build(family: str) -> dict:
    schema = json.loads((HERE / "schema" / f"{family}.json").read_text(encoding="utf-8"))
    global _HIDE, _SAMPLES
    _HIDE = [re.compile(p, re.I) for p in schema.get("never_sample", [])]
    _SAMPLES = schema.get("brief_samples", True)
    c = sqlite3.connect(f"file:{STORE / 'families.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    entries = []
    for j in c.execute("SELECT * FROM jobs WHERE family=? AND state='needs_review' ORDER BY publisher", (family,)):
        doc = json.loads((STORE / "tables" / j["extraction_sha"]).read_text(encoding="utf-8"))
        layouts = []
        try:
            files = c.execute("SELECT url, name, extraction_sha FROM files WHERE job_id=? AND state='extracted' "
                              "ORDER BY name, url", (j["id"],)).fetchall()
            n_files = len(files)
            # Every distinct header across the dataset's files, with a
            # sample from the first file that carries it: a series proposer
            # needs to see each layout, not just the first.
            seen = {}
            for fr in files:
                d = json.loads((STORE / "tables" / fr["extraction_sha"]).read_text(encoding="utf-8"))
                t0 = d["tables"][0] if d["tables"] else None
                if not t0 or not t0["rows"]:
                    continue
                key = tuple(str(x).strip().lower() for x in t0["rows"][_header_row(t0["rows"])][:MAX_COLS])
                if key in seen:
                    seen[key]["files"] += 1
                    continue
                pv = _preview(t0)
                pv["example_file"] = fr["name"] or fr["url"][-60:]
                pv["files"] = 1
                seen[key] = pv
            layouts = list(seen.values())[:8]
        except sqlite3.OperationalError:
            n_files = 1
        entries.append({
            "job_id": j["id"], "publisher": j["publisher"], "title": j["title"], "portal": j["portal"],
            "format": j["format"], "resource_url": j["resource_url"], "licence": json.loads(j["licence_json"])["id"],
            "files_extracted": n_files,
            "note": ("This dataset has several files. 'layouts' lists every distinct header found across "
                     "them with a sample and how many files carry it; the first is 'columns', each further "
                     "one needs an entry in 'alt_columns'.") if n_files > 1 else None,
            "layouts": layouts if n_files > 1 else [],
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
