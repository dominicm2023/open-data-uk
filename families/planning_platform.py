"""MHCLG's planning data platform (planning.data.gov.uk) collects every
planning authority's brownfield land register into one national dataset,
under the OGL. For the family it is a second route to the same registers:
an authority whose own file is dead, unlicensed or not in any catalogue
we harvest can still be in the table through the platform's copy, said
so on every row. An authority whose own file is published is taken from
that file, never twice.

Fetched politely through intake.fetch (one 20 MB CSV and the organisation
lookup), kept by hash, mapped from the platform's field names to the
schema, and appended by build.py with the same validation and receipts.

Usage:  DATA_DIR=... python families/planning_platform.py            # fetch + write rows
        DATA_DIR=... python families/planning_platform.py --no-fetch # rows from stored files
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA_DIR  # noqa: E402
from intake import LIMITS, Refused, fetch, store  # noqa: E402
from build import _date, _num  # noqa: E402

STORE = DATA_DIR / "families"
STATE = STORE / "platform.json"
ADAPTER = "platform-v1"

FEEDS = {
    "brownfield_land": {
        "dataset": "brownfield-land",
        "publisher": "MHCLG (planning.data.gov.uk)",
        "title": "Brownfield land: the national collection on planning.data.gov.uk",
        "csv": "https://files.planning.data.gov.uk/dataset/brownfield-land.csv",
        "organisations": "https://files.planning.data.gov.uk/organisation-collection/dataset/organisation.csv",
        "licence": {"id": "OGL-UK-3.0", "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                    "evidence_url": "https://www.planning.data.gov.uk/dataset/brownfield-land",
                    "attribution": "Contains public sector information licensed under the Open Government Licence v3.0; "
                                   "collected by the Ministry of Housing, Communities and Local Government at planning.data.gov.uk",
                    "read": "planning.data.gov.uk/dataset/brownfield-land: 'Licensed under the Open Government Licence v.3.0' (read 8 September 2026)"},
        # platform field -> schema column
        "columns": {"reference": "site_reference", "site-address": "site_name_address", "hectares": "hectares",
                    "ownership-status": "ownership_status", "planning-permission-status": "planning_status",
                    "planning-permission-type": "permission_type", "planning-permission-date": "permission_date",
                    "minimum-net-dwellings": "min_net_dwellings", "maximum-net-dwellings": "max_net_dwellings",
                    "deliverable": "deliverable", "hazardous-substances": "hazardous_substances",
                    "site-plan-url": "site_plan_url", "start-date": "first_added_date", "entry-date": "last_updated_date",
                    "notes": "notes"},
    },
}


def _get(url: str, state: dict) -> str | None:
    prev = state.get(url) or {}
    headers = {"If-None-Match": prev["etag"]} if prev.get("etag") else {}
    try:
        body, rh, _ = fetch(url, LIMITS["max_file_bytes"], headers)
    except Refused as err:
        state[url] = {**prev, "error": str(err)[:160], "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        return prev.get("sha")
    if body is None:
        state[url] = {**prev, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "error": None}
        return prev.get("sha")
    sha = store("blobs", body)
    state[url] = {"sha": sha, "etag": rh.get("ETag"), "bytes": len(body), "error": None,
                  "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    return sha


def _read_csv(sha: str) -> list[dict]:
    text = (STORE / "blobs" / sha).read_bytes().decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def _point(wkt: str | None) -> tuple[float | None, float | None]:
    m = re.match(r"\s*POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)", wkt or "")
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def run(family: str, do_fetch: bool = True) -> dict:
    spec = FEEDS[family]
    schema = json.loads((Path(__file__).resolve().parent / "schema" / f"{family}.json").read_text(encoding="utf-8"))
    types = {c["name"]: c["type"] for c in schema["columns"]}
    out_dir = STORE / "out" / family
    out_dir.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    lic = spec["licence"]
    lic_sha = _get(lic["evidence_url"], state) if do_fetch else state.get(lic["evidence_url"], {}).get("sha")
    org_sha = _get(spec["organisations"], state) if do_fetch else state.get(spec["organisations"], {}).get("sha")
    csv_sha = _get(spec["csv"], state) if do_fetch else state.get(spec["csv"], {}).get("sha")
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    summary = {"platform": spec["dataset"], "publisher": spec["publisher"], "title": spec["title"],
               "licence": lic["id"], "licence_url": lic["url"], "licence_evidence_url": lic["evidence_url"],
               "licence_evidence_sha256": lic_sha, "licence_note": lic["read"], "attribution": lic["attribution"]}
    if not csv_sha or not org_sha:
        summary.update({"ladder": "fetch failed", "why": state.get(spec["csv"], {}).get("error") or state.get(spec["organisations"], {}).get("error")})
        rows: list[dict] = []
    else:
        orgs = {r.get("entity"): r.get("name") for r in _read_csv(org_sha)}
        rows = []
        for i, rec in enumerate(_read_csv(csv_sha)):
            if (rec.get("end-date") or "").strip():
                continue                                   # a site the authority has since removed
            body = orgs.get(rec.get("organisation-entity")) or rec.get("organisation") or ""
            lon, lat = _point(rec.get("point"))
            row = {"body": body, "coords_source": "wgs84" if lon is not None else "none", "lon": lon, "lat": lat}
            for src, target in spec["columns"].items():
                v = (rec.get(src) or "").strip()
                row[target] = v or None
            if not row.get("site_name_address"):
                row["site_name_address"] = rec.get("name") or None
            # the CSV is text; the schema says what each column is
            for col, typ in types.items():
                v = row.get(col)
                if v in (None, ""):
                    row[col] = None
                elif typ == "number":
                    row[col] = _num(v)
                elif typ == "integer":
                    nv = _num(v)
                    row[col] = int(nv) if nv is not None else None
                elif typ == "date":
                    row[col] = _date(v)
                elif typ == "boolean":
                    row[col] = str(v).strip().lower() in ("true", "yes", "y", "1")
            row.update({
                "publisher": spec["publisher"], "dataset_key": f"platform:{spec['dataset']}", "source_url": spec["csv"],
                "source_sha256": csv_sha, "source_table": "brownfield-land.csv", "source_row": i + 1,
                "source_file": "brownfield-land.csv",
                "licence_id": lic["id"], "licence_url": lic["url"], "licence_evidence_sha256": lic_sha or "",
                "licence_evidence_kind": "platform-terms", "adapter_version": ADAPTER,
                "quality_note": "via MHCLG's planning data platform, not the authority's own file; "
                                "values are the platform's normalised spellings (e.g. 'not-owned-by-a-public-authority')",
            })
            rows.append(row)
        summary.update({"ladder": "published", "rows": len(rows), "files": 1,
                        "bodies": len({r["body"] for r in rows}),
                        "notes": (f"Review 2026-09-08: the platform's national collection ({len(rows):,} current sites from "
                                  f"{len({r['body'] for r in rows})} authorities) fills in authorities whose own file is not in the "
                                  "table; an authority published from its own file is never taken from here as well. "
                                  f"{lic['attribution']}.")})
    (out_dir / "platform.rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (out_dir / "platform.summary.json").write_text(json.dumps([summary], indent=1, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    fam = next((a for a in sys.argv[1:] if not a.startswith("--")), "brownfield_land")
    r = run(fam, do_fetch="--no-fetch" not in sys.argv)
    print(f"{fam}: platform {r['ladder']} rows {r.get('rows', 0):,} bodies {r.get('bodies', 0)}" + (f" why: {r['why']}" if r.get("why") else ""))
