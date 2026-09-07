"""The national monitoring networks' annual statistics, read from the files
their own sites publish for openair (`summary_annual_<NET>_<year>.rds`):
one row per site, with `<POLLUTANT>.mean` and `<POLLUTANT>.capture` for
every pollutant the site measures, and a metadata file with each site's
name, type, coordinates and how far its data is ratified.

These are not in any catalogue we harvest, so they do not go through the
registry. Each network is a source in its own right: fetched politely
through intake.fetch, kept by hash, unpivoted into the air_quality_annual
schema, and appended by build.py with the same receipts as every other row.
Only networks whose site states a licence a person has read are here; the
others are listed with the reason.

Usage:  DATA_DIR=... python families/networks.py            # fetch + write rows
        DATA_DIR=... python families/networks.py --no-fetch # rebuild rows from stored files
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA_DIR  # noqa: E402
from intake import LIMITS, Refused, fetch, store  # noqa: E402

STORE = DATA_DIR / "families"
OUT = STORE / "out" / "air_quality_annual"
STATE = STORE / "networks.json"
ADAPTER = "networks-v1"
THIS_YEAR = dt.date.today().year

# Pollutants published as annual means, with the unit UK-AIR reports them in.
POLLUTANTS = {
    "NO2": ("NO2", "µg/m³", None), "NO": ("NO", "µg/m³", None), "NOXasNO2": ("NOx as NO2", "µg/m³", None),
    "O3": ("O3", "µg/m³", None), "SO2": ("SO2", "µg/m³", None), "CO": ("CO", "mg/m³", None),
    "PM10": ("PM10", "µg/m³", None), "PM2.5": ("PM2.5", "µg/m³", None),
    "GR10": ("PM10", "µg/m³", "gravimetric"), "GR2.5": ("PM2.5", "µg/m³", "gravimetric"),
}

NETWORKS = {
    "aurn": {
        "publisher": "Defra (UK-AIR: Automatic Urban and Rural Network)",
        "title": "AURN annual statistics",
        "base": "https://uk-air.defra.gov.uk/openair/R_data/", "abbr": "AURN", "meta": "AURN_metadata.RData",
        "years": range(1990, THIS_YEAR + 1),
        "licence": {"id": "OGL-UK-3.0", "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                    "evidence_url": "https://uk-air.defra.gov.uk/data/",
                    "attribution": "© Crown copyright Defra via uk-air.defra.gov.uk, licenced under the Open Government Licence",
                    "read": "uk-air.defra.gov.uk/data states the OGL and the attribution line verbatim (read 7 September 2026)"},
    },
    "lmam": {
        "publisher": "Defra (UK-AIR: local authority network sites)",
        "title": "Local authority monitoring network annual statistics (LMAM)",
        "base": "https://uk-air.defra.gov.uk/openair/LMAM/R_data/", "abbr": "LMAM", "meta": "LMAM_metadata.RData",
        "years": range(2008, THIS_YEAR + 1),
        "licence": {"id": "OGL-UK-3.0", "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                    "evidence_url": "https://uk-air.defra.gov.uk/data/",
                    "attribution": "© Crown copyright Defra via uk-air.defra.gov.uk, licenced under the Open Government Licence",
                    "read": "the same UK-AIR site and terms as the AURN (read 7 September 2026)"},
    },
    "ni": {
        "publisher": "DAERA (Northern Ireland Air Quality)",
        "title": "Northern Ireland network annual statistics",
        "base": "https://www.airqualityni.co.uk/openair/R_data/", "abbr": "NI", "meta": "NI_metadata.RData",
        "years": range(1990, THIS_YEAR + 1),
        "licence": {"id": "OGL-UK-3.0", "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                    "evidence_url": "https://www.airqualityni.co.uk/data",
                    "attribution": "Contains public sector information licensed under the Open Government Licence v3.0; source airqualityni.co.uk",
                    "read": "airqualityni.co.uk's footer: 'All content is available under the Open Government Licence v3.0, except where otherwise stated' (read 7 September 2026)"},
    },
    "waqn": {
        "publisher": "Welsh Government (Air Quality Wales)",
        "title": "Welsh network annual statistics",
        "base": "https://airquality.gov.wales/sites/default/files/openair/R_data/", "abbr": "WAQ", "meta": "WAQ_metadata.RData",
        "years": range(1990, THIS_YEAR + 1),
        # Not a named open licence: the site's own terms, read and accepted
        # by Dominic on 7 September 2026, with the acknowledgement they ask for.
        "licence": {"id": "AQW-terms", "url": "https://airquality.gov.wales/terms-and-conditions",
                    "evidence_url": "https://airquality.gov.wales/terms-and-conditions",
                    "attribution": "Data from Air Quality Wales (airquality.gov.wales), which makes it freely available for public use with acknowledgement of the website as the source",
                    "read": "airquality.gov.wales/terms-and-conditions: 'Any data downloaded from these pages are freely available for public use, with acknowledgement of this web site as the source.' Not a named licence; accepted as permissive terms by decision DM 2026-09-07, the acknowledgement carried on every row"},
    },
}
# Networks whose sites state no licence a person could accept: listed, not fetched.
PARKED = {
    "saqn": ("Scottish Air Quality Network (scottishairquality.scot)",
             "the site's data pages state no licence; asked by email on 7 September 2026"),
    "aqe": ("Air Quality England (airqualityengland.co.uk, Ricardo for local authorities)",
            "no terms page found; the sites belong to individual councils, so the licence would be theirs to state"),
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _get(url: str, state: dict, kind: str) -> tuple[str | None, bytes | None]:
    """Fetch conditionally; return (blob_sha, body) — body None when unchanged."""
    prev = state.get(url) or {}
    headers = {"If-None-Match": prev["etag"]} if prev.get("etag") else {}
    try:
        body, rh, _ = fetch(url, LIMITS["max_file_bytes"], headers)
    except Refused as err:
        state[url] = {**prev, "error": str(err)[:160], "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        return prev.get("sha"), None
    if body is None:                                  # 304: what we have is current
        state[url] = {**prev, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "error": None}
        return prev.get("sha"), None
    if kind == "rds" and body[:2] != b"\x1f\x8b" and body[:5] != b"RDX3\n" and body[:1] != b"X":
        # an HTML "not found" page in place of a file
        state[url] = {**prev, "error": "not an R data file", "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        return prev.get("sha"), None
    sha = store("blobs", body)
    state[url] = {"sha": sha, "etag": rh.get("ETag"), "bytes": len(body), "error": None,
                  "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    return sha, body


def _read_r(path: Path):
    import pyreadr
    r = pyreadr.read_r(str(path))
    return next(iter(r.values()))


def _metadata(sha: str) -> dict:
    """site_id -> site fields; (site_id, parameter) -> ratified_to."""
    df = _read_r(STORE / "blobs" / sha)
    sites, ratified = {}, {}
    for rec in df.to_dict("records"):
        sid = str(rec.get("site_id") or "").strip()
        if not sid:
            continue
        sites.setdefault(sid, {
            "site_name": rec.get("site_name"), "site_type": rec.get("location_type"),
            "lat": rec.get("latitude"), "lon": rec.get("longitude"),
            "local_authority": rec.get("local_authority") or rec.get("provider"),
        })
        rt = rec.get("ratified_to")
        if rt and str(rt) not in ("nan", "NaT", "ongoing"):
            ratified[(sid, str(rec.get("parameter")))] = str(rt)[:10]
    return {"sites": sites, "ratified": ratified}


def _rows_for(net: str, spec: dict, year: int, sha: str, url: str, meta: dict, lic_sha: str) -> tuple[list[dict], list[str]]:
    import math
    df = _read_r(STORE / "blobs" / sha)
    out, held = [], []
    cols = set(df.columns)
    code_col = "code" if "code" in cols else "site_id"
    for i, rec in enumerate(df.to_dict("records")):
        sid = str(rec.get(code_col) or "").strip()
        site = meta["sites"].get(sid, {})
        for key, (pollutant, unit, method_note) in POLLUTANTS.items():
            v = rec.get(f"{key}.mean")
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            cap = rec.get(f"{key}.capture")
            cap_pct = None if cap is None or (isinstance(cap, float) and math.isnan(cap)) else round(float(cap) * 100, 1)
            quals = []
            rt = meta["ratified"].get((sid, key)) or meta["ratified"].get((sid, pollutant))
            if rt and rt < f"{year}-12-31":
                quals.append(f"provisional: ratified to {rt}")
            if cap_pct is not None and cap_pct < 75:
                quals.append("data capture below 75%: not a valid annual mean under LAQM.TG")
            if site.get("local_authority"):
                quals.append(f"{'operated by' if net == 'lmam' else 'local authority'}: {site['local_authority']}")
            out.append({
                "site_id": sid, "site_name": site.get("site_name") or rec.get("site"),
                "site_type": site.get("site_type"), "method": "automatic monitor" + (f" ({method_note})" if method_note else ""),
                "pollutant": pollutant, "year": int(year), "annual_mean": round(float(v), 3), "unit": unit,
                "bias_adjusted": None, "data_capture_pct": cap_pct,
                "lon": site.get("lon"), "lat": site.get("lat"), "coords_source": "wgs84" if site.get("lat") else "none",
                "qualifier": "; ".join(quals) or None,
                "publisher": spec["publisher"], "dataset_key": f"network:{net}", "source_url": url,
                "source_sha256": sha, "source_table": "summary_annual", "source_row": i + 1,
                "source_file": url.rsplit("/", 1)[-1],
                "licence_id": spec["licence"]["id"], "licence_url": spec["licence"]["url"],
                "licence_evidence_sha256": lic_sha, "licence_evidence_kind": "network-terms",
                "adapter_version": ADAPTER, "quality_note": None,
            })
    return out, held


def run(do_fetch: bool = True) -> dict:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    summary, rows = [], []
    for net, spec in NETWORKS.items():
        lic = spec["licence"]
        lic_sha = state.get(lic["evidence_url"], {}).get("sha")
        if do_fetch:
            lic_sha, _ = _get(lic["evidence_url"], state, "html")
        meta_url = spec["base"] + spec["meta"]
        meta_sha = state.get(meta_url, {}).get("sha")
        if do_fetch:
            meta_sha, _ = _get(meta_url, state, "rds")
        if not meta_sha:
            summary.append({"network": net, "publisher": spec["publisher"], "title": spec["title"], "ladder": "fetch failed",
                            "why": f"metadata: {state.get(meta_url, {}).get('error')}"})
            continue
        meta = _metadata(meta_sha)
        n_files, n_rows, years = 0, 0, []
        for year in spec["years"]:
            url = f"{spec['base']}summary_annual_{spec['abbr']}_{year}.rds"
            sha = state.get(url, {}).get("sha")
            if do_fetch:
                sha, _ = _get(url, state, "rds")
            if not sha:
                continue
            try:
                r, _held = _rows_for(net, spec, year, sha, url, meta, lic_sha or "")
            except Exception as err:  # noqa: BLE001 — one bad year must not sink the network
                state[url] = {**state.get(url, {}), "error": f"read: {str(err)[:120]}"}
                continue
            rows += r; n_rows += len(r); n_files += 1; years.append(year)
        summary.append({"network": net, "publisher": spec["publisher"], "title": spec["title"], "ladder": "published",
                        "rows": n_rows, "files": n_files, "years": f"{min(years)}-{max(years)}" if years else None,
                        "sites": len(meta["sites"]), "licence": lic["id"], "licence_url": lic["url"],
                        "licence_evidence_url": lic["evidence_url"], "licence_evidence_sha256": lic_sha,
                        "licence_note": lic["read"], "attribution": lic["attribution"],
                        "notes": (f"Review 2026-09-07: read from the network's own openair summary files, one per year; "
                                  f"a row per site, pollutant and year with the published mean and data capture. Rows past "
                                  f"the site's ratified date, or under 75% capture, say so in 'qualifier'. {lic['attribution']}.")})
    for net, (name, why) in PARKED.items():
        summary.append({"network": net, "publisher": name, "title": f"{name} annual statistics", "ladder": "not admitted", "why": why})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "networks.rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (OUT / "networks.summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return {"rows": len(rows), "networks": summary}


if __name__ == "__main__":
    r = run(do_fetch="--no-fetch" not in sys.argv)
    for n in r["networks"]:
        print(f"  {n['network']:5} {n['ladder']:14} rows {n.get('rows', 0):>7,} files {n.get('files', 0):>3} years {n.get('years')} "
              + (f"why: {n['why']}" if n.get("why") else ""))
    print(f"networks: {r['rows']:,} rows")
