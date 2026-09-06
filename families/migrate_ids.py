"""One-off: job ids were keyed on the resource URL; they are keyed on the
dataset now. Rewrite the mappings files and the database to match, so no
reviewed mapping is lost and no dataset appears twice.

Run on the box with DATA_DIR set, from the repo root, once:
    python families/migrate_ids.py
Idempotent: a second run finds nothing to change.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paths import DATA_DIR  # noqa: E402

HERE = Path(__file__).resolve().parent
STORE = DATA_DIR / "families"


def new_id(family: str, dataset_key: str) -> str:
    return hashlib.sha256((family + "\n" + dataset_key).encode()).hexdigest()


def main() -> int:
    c = sqlite3.connect(STORE / "families.db", timeout=15)
    c.row_factory = sqlite3.Row
    jobs = [dict(j) for j in c.execute("SELECT * FROM jobs")]
    # old id -> new id, and which old job per dataset to keep (best state)
    rank = {"needs_review": 0, "queued": 1, "fetch_failed": 2, "not_admitted": 3}
    best: dict[tuple, dict] = {}
    for j in jobs:
        k = (j["family"], j["dataset_key"])
        if k not in best or rank.get(j["state"], 9) < rank.get(best[k]["state"], 9):
            best[k] = j
    remap = {j["id"]: new_id(j["family"], j["dataset_key"]) for j in jobs}
    # database: keep one row per dataset under the new id
    c.execute("CREATE TABLE IF NOT EXISTS files(job_id TEXT, url TEXT, format TEXT, name TEXT, blob_sha TEXT, "
              "extraction_sha TEXT, extractor TEXT, etag TEXT, last_modified TEXT, state TEXT, detail TEXT, "
              "fetched_at TEXT, PRIMARY KEY (job_id, url))")
    have = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
    if "series" not in have:
        c.execute("ALTER TABLE jobs ADD COLUMN series INTEGER DEFAULT 0")
    changed = 0
    for (family, key), j in best.items():
        nid = new_id(family, key)
        if j["id"] == nid:
            continue
        c.execute("DELETE FROM jobs WHERE family=? AND dataset_key=?", (family, key))
        cols = [k for k in j.keys() if k != "id"]
        c.execute(f"INSERT INTO jobs(id,{','.join(cols)}) VALUES(?,{','.join('?' * len(cols))})",
                  [nid] + [j[k] for k in cols])
        if j["state"] == "needs_review" and j["extraction_sha"]:
            c.execute("INSERT OR REPLACE INTO files(job_id,url,format,name,blob_sha,extraction_sha,extractor,etag,"
                      "last_modified,state,detail,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,'extracted',?,?)",
                      (nid, j["resource_url"], j["format"], "", j["blob_sha"], j["extraction_sha"], j["extractor"],
                       j["etag"], j["last_modified"], j["detail"], j["checked_at"]))
        c.execute("UPDATE attempts SET job_id=? WHERE job_id=?", (nid, j["id"]))
        changed += 1
    c.commit()
    print(f"database: {changed} datasets re-keyed; {len(jobs) - len(best)} duplicate file-keyed jobs removed")
    # mappings files: rename keys, keep the best-state entry when two old ids collapse
    for mp in (HERE / "registry").glob("*.mappings.json"):
        m = json.loads(mp.read_text(encoding="utf-8"))
        out: dict = {}
        moved = 0
        for old, spec in m.items():
            nid = remap.get(old, old)
            if nid != old:
                moved += 1
            if nid in out and out[nid].get("status") == "reviewed" and spec.get("status") != "reviewed":
                continue
            out[nid] = spec
        mp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{mp.name}: {moved} keys re-keyed, {len(m) - len(out)} collapsed")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
