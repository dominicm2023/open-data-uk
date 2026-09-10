"""Every council's Annual Status Report monitoring results, from Defra's
Local Air Quality Dashboard (uk-air.defra.gov.uk/local-authorities-dashboard).

The dashboard is an R Shiny app: it holds, for each of 361 authorities, the
site-by-site annual means from the authority's latest LAQM Annual Status
Report — site id, name, type, easting/northing, method, data capture,
annual mean NO2 and its compliance status — and offers them as a CSV, but
only through a per-session download link. So this script drives a real
browser (Playwright, headless Chromium) once through the authority list,
one authority every ten seconds or so, and keeps each CSV by authority.
The data changes once a year, when reports are submitted; a run is
skipped while the cache is younger than 30 days (--force to refetch).

UK-AIR's terms: OGL v3 with the attribution "© Crown copyright Defra via
uk-air.defra.gov.uk"; the dashboard states the data is "provided by local
authorities in their latest Annual Reports", and every row says which.

Usage:  DATA_DIR=... python families/laqm_dashboard.py [--force] [--limit N] [--no-fetch]
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA_DIR  # noqa: E402
from build import bng_to_wgs84  # noqa: E402

STORE = DATA_DIR / "families"
CACHE = STORE / "laqm_dashboard"
OUT = STORE / "out" / "air_quality_annual"
URL = "https://uk-air.defra.gov.uk/local-authorities-dashboard/"
UA = "open-data.org.uk index (a UK open-data index; contact via the site) Playwright"
ADAPTER = "laqm-dashboard-v1"
MAX_AGE_DAYS = 30
PAUSE = 1.5
LICENCE = {
    "id": "OGL-UK-3.0", "url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "evidence_url": "https://uk-air.defra.gov.uk/data/",
    "attribution": "© Crown copyright Defra via uk-air.defra.gov.uk, licenced under the Open Government Licence; "
                   "data provided by each local authority in its Annual Status Report",
}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _num(v):
    try:
        return float(str(v).replace(",", "")) if str(v).strip() not in ("", "NA", "None") else None
    except ValueError:
        return None


def fetch(force: bool = False, limit: int | None = None) -> dict:
    """Drive the dashboard through every authority; one CSV per authority."""
    from playwright.sync_api import sync_playwright
    CACHE.mkdir(parents=True, exist_ok=True)
    state_path = CACHE / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    fetched, skipped, errors = 0, 0, 0
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        page.goto(URL, wait_until="load", timeout=90000)          # Shiny long-polls: never "networkidle"
        page.wait_for_selector("input[type=radio]", timeout=60000)
        time.sleep(3)
        page.get_by_label("Local Authority", exact=True).check()
        time.sleep(PAUSE)
        opts = page.evaluate("""() => { const sz = document.querySelector('#enterLA').selectize; const o = sz.options;
            return Object.keys(o).map(k => [k, o[k][sz.settings.labelField]]); }""")
        authorities = [(code, name) for code, name in opts if code]
        if limit:
            authorities = authorities[:limit]
        print(f"[laqm_dashboard] {len(authorities)} authorities listed", flush=True)
        started = False
        for i, (code, name) in enumerate(authorities, 1):
            prev = state.get(code) or {}
            age = (now - dt.datetime.fromisoformat(prev["fetched_at"])).days if prev.get("fetched_at") else 10**6
            if not force and age < MAX_AGE_DAYS and (CACHE / f"{code}.csv").exists():
                skipped += 1
                continue
            try:
                if started:
                    # the landing panel (select + Start) hides once an authority is shown;
                    # the nav's "Select Local Authority" brings it back
                    page.locator("#navLanding").click()
                    time.sleep(PAUSE)
                page.evaluate("(code) => document.querySelector('#enterLA').selectize.setValue(code)", code)
                time.sleep(PAUSE)
                page.locator("#submit").click()
                time.sleep(5)
                started = True
                page.get_by_role("tab", name=re.compile("Air Quality Monitoring")).click()
                time.sleep(3)
                # NO2 annual mean is the table the download follows; PM10 is in the same CSV where reported
                radio = page.locator("input[name=mapMonitoring][value='no2_annual']")
                if radio.count():
                    radio.check()
                    time.sleep(PAUSE)
                note = page.inner_text("body")
                m = re.search(r"(\d{4}) LAQM Annual Report, presenting .{0,80}?year (\d{4})", note)
                href = page.evaluate("""() => { const a = [...document.querySelectorAll('a')].find(a => /Download Monitoring Data/i.test(a.innerText)); return a ? a.href : null; }""")
                if not href:
                    raise RuntimeError("no download link")
                r = page.request.get(href)
                if r.status != 200:
                    raise RuntimeError(f"download HTTP {r.status}")
                body = r.body()
                (CACHE / f"{code}.csv").write_bytes(body)
                state[code] = {"name": name, "fetched_at": now.isoformat(), "sha256": _sha(body), "bytes": len(body),
                               "report_year": m.group(1) if m else None, "data_year": m.group(2) if m else None, "error": None}
                fetched += 1
                if fetched % 25 == 0:
                    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
                    print(f"[laqm_dashboard]   {i}/{len(authorities)} ({fetched} fetched)", flush=True)
                time.sleep(PAUSE)
            except Exception as exc:  # noqa: BLE001 — one authority must not end the run
                errors += 1
                state[code] = {**prev, "name": name, "error": str(exc)[:160], "checked_at": now.isoformat()}
                if errors <= 5:
                    print(f"[laqm_dashboard]   {name}: {str(exc)[:120]}", flush=True)
                time.sleep(PAUSE)
        b.close()
    state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    print(f"[laqm_dashboard] fetched {fetched}, kept {skipped} fresh, {errors} errors", flush=True)
    return state


def rows_from_cache() -> tuple[list[dict], dict]:
    """The cached CSVs as air_quality_annual rows, with the same receipts as
    every other row of the family."""
    state_path = CACHE / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    rows, bodies, years = [], set(), set()
    for code, st in sorted(state.items()):
        path = CACHE / f"{code}.csv"
        if not path.exists():
            continue
        body = st.get("name") or code
        text = path.read_bytes().decode("utf-8-sig", "replace")
        for i, rec in enumerate(csv.DictReader(io.StringIO(text)), 1):
            year = rec.get("report_year") or st.get("data_year")
            try:
                year = int(year)
            except (TypeError, ValueError):
                continue
            e, n = _num(rec.get("easting")), _num(rec.get("northing"))
            lon = lat = None
            if e and n and 0 < e < 800000 and 0 < n < 1400000:
                lon, lat = bng_to_wgs84(e, n)
            method = (rec.get("method") or "").strip().lower()
            method = ("diffusion tube" if "non-automatic" in method else "automatic monitor" if "automatic" in method else None)
            for pol, mean_col, cap_col, status_col in (("NO2", "no2_annual_mean", "no2_data_capture_percent", "no2_annual_mean_status"),
                                                       ("PM10", "pm10_annual_mean", "pm10_data_capture_percent", "pm10_annual_mean_status"),
                                                       ("PM2.5", "pm25_annual_mean", "pm25_data_capture_percent", "pm25_annual_mean_status")):
                mean = _num(rec.get(mean_col))
                if mean is None:
                    continue
                quals = [f"as reported in the authority's {st.get('report_year') or year + 1} Annual Status Report, via Defra's Local Air Quality Dashboard"]
                if rec.get(status_col):
                    quals.append(f"objective status: {rec[status_col]}")
                if (rec.get("distance_corrected") or "").strip().lower() == "yes":
                    quals.append("distance-corrected to the nearest receptor")
                rows.append({
                    "site_id": rec.get("site_id") or None, "site_name": rec.get("site_name") or rec.get("site_id"),
                    "site_type": rec.get("site_type") or None, "method": method, "pollutant": pol, "year": year,
                    "annual_mean": mean, "unit": "µg/m³", "bias_adjusted": None, "data_capture_pct": _num(rec.get(cap_col)),
                    "lon": lon, "lat": lat, "coords_source": "bng_converted" if lon is not None else "none",
                    "qualifier": "; ".join(quals), "body": body,
                    "publisher": "Defra (UK-AIR Local Air Quality Dashboard)", "dataset_key": "dashboard:laqm",
                    "source_url": URL, "source_sha256": st.get("sha256") or "", "source_table": f"{code}.csv",
                    "source_row": i, "source_file": f"{code}.csv",
                    "licence_id": LICENCE["id"], "licence_url": LICENCE["url"], "licence_evidence_sha256": "",
                    "licence_evidence_kind": "network-terms", "adapter_version": ADAPTER, "quality_note": None,
                })
                bodies.add(body); years.add(year)
    summary = {"platform": "laqm", "publisher": "Defra (UK-AIR Local Air Quality Dashboard)",
               "title": "Local authorities' Annual Status Report monitoring results, via Defra's Local Air Quality Dashboard",
               "ladder": "published" if rows else "fetch failed", "rows": len(rows), "files": len({r["source_table"] for r in rows}),
               "bodies": len(bodies), "years": f"{min(years)}-{max(years)}" if years else None,
               "licence": LICENCE["id"], "licence_url": LICENCE["url"], "licence_evidence_url": LICENCE["evidence_url"],
               "licence_note": "uk-air.defra.gov.uk/data states the OGL and the attribution line; the dashboard says its data is 'provided by local authorities in their latest Annual Reports' (read 10 September 2026)",
               "attribution": LICENCE["attribution"],
               "notes": (f"Review 2026-09-10: {len(bodies)} authorities' latest Annual Status Report results, one CSV per authority from the "
                         f"dashboard's own download, driven by a headless browser once a month. Site-level annual means as each "
                         f"authority reported them (NO2 diffusion-tube results in a Status Report are already bias-adjusted and "
                         f"annualised by the authority). An authority whose own file is in the table is not taken from here for the "
                         f"same year. {LICENCE['attribution']}.")}
    return rows, summary


def main() -> int:
    force, no_fetch = "--force" in sys.argv, "--no-fetch" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    lock = CACHE / "run.lock"
    if not no_fetch:
        # one browser at a time: a full pass is hours, and the nightly must
        # not start a second one beside a manual run
        import os
        CACHE.mkdir(parents=True, exist_ok=True)
        if lock.exists():
            try:
                os.kill(int(lock.read_text().strip() or 0), 0)
                print("[laqm_dashboard] another run is in progress; skipping the fetch", flush=True)
                no_fetch = True
            except (ValueError, ProcessLookupError, PermissionError):
                pass
    if not no_fetch:
        lock.write_text(str(os.getpid()))
        try:
            fetch(force=force, limit=limit)
        finally:
            lock.unlink(missing_ok=True)
    rows, summary = rows_from_cache()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dashboard.rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (OUT / "dashboard.summary.json").write_text(json.dumps([summary], indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[laqm_dashboard] {len(rows):,} rows from {summary['bodies']} authorities ({summary['years']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
