"""Fetch the scoped RO workbooks plus population and deflator companions.

Scope, stated up front so nobody has to reverse-engineer it from the raw dir:

  Per vintage (2024-25, 2018-19, 2013-14):
    RS   revenue outturn summary        - financing, reserves, council tax
    RSX  service expenditure summary    - every authority x every service line
    RO5  cultural/environmental detail  - the only sheet where libraries are
                                          a line of their own

  Companions:
    ONS mid-year population estimates by local authority (nomis open CSV),
      one call per needed year - required for any per-resident figure.
    HMT GDP deflator (gov.uk CSV) - required for any across-year comparison;
      cash-terms time arcs are a known dunking.

Politeness: agent.py HEADERS on every request, <=2 req/s per host, 60s
timeout. Total is ~12 MB against a 1.5 GB cap.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent import HEADERS

HERE = Path(__file__).parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)

WANT = ("Revenue outturn summary (RS)",
        "Revenue outturn service expenditure summary (RSX)",
        "Revenue outturn cultural")  # RO5 title varies slightly across years

attachments = json.loads((HERE / "attachments.json").read_text())

manifest = []
last_req = 0.0


def polite_get(url: str) -> requests.Response:
    global last_req
    wait = 0.5 - (time.monotonic() - last_req)
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=HEADERS, timeout=60)
    last_req = time.monotonic()
    resp.raise_for_status()
    return resp


total = 0
for year, info in attachments.items():
    for att in info["attachments"]:
        if not any(att["title"].startswith(w) for w in WANT):
            continue
        url = att["url"]
        ext = url.rsplit(".", 1)[-1].lower()
        form = re.search(r"\((RS|RSX|RO5)\)", att["title"])
        form = form.group(1) if form else "RO5"
        dest = RAW / f"{form}_{year}.{ext}"
        if dest.exists():
            print(f"have    {dest.name}")
        else:
            resp = polite_get(url)
            dest.write_bytes(resp.content)
            print(f"fetched {dest.name}  {len(resp.content)/1024:.0f} KB")
        total += dest.stat().st_size
        manifest.append({"year": year, "form": form, "file": dest.name,
                         "title": att["title"], "url": url,
                         "bytes": dest.stat().st_size,
                         "source_page": info["page"]})

# --- ONS mid-year population --------------------------------------------
# NM_2002_1 on nomis is "Population estimates - local authority based by
# single year of age"; c_age=200 all ages, gender=0 total. Boundary vintages
# matter, and nomis only KEEPS values for geographies that still exist -
# probing showed every TYPE returns NaN for abolished districts and
# counties, whatever the date. So:
#   2024  TYPE423/424 (county+unitary / district+unitary, April 2023 set) -
#         complete for 2024-25 authorities.
#   2018  NOT from nomis (it deletes back-series values for abolished
#         geographies, which loses 42 of 353 principal councils). The ONS
#         archived mid-2018 reference table ON 2018 BOUNDARIES
#         (ukmidyearestimates20182018ladcodes.xls) is fetched below.
#   2013  NOT from nomis, same reason. The archived mid-2013 reference
#         table (MYE2, on 2013 boundaries) is fetched below.
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset/NM_2002_1.data.csv"
POP_CALLS = {
    "pop_upper_2024": ("2024", "TYPE423"),
    "pop_lower_2024": ("2024", "TYPE424"),
}
for name, (date, gtype) in POP_CALLS.items():
    dest = RAW / f"{name}.csv"
    url = (f"{NOMIS}?geography={gtype}&date={date}&gender=0&c_age=200"
           f"&measures=20100&select=geography_code,geography_name,date,obs_value")
    if dest.exists():
        print(f"have    {dest.name}")
    else:
        resp = polite_get(url)
        dest.write_bytes(resp.content)
        print(f"fetched {dest.name}  {len(resp.content)/1024:.0f} KB")
    manifest.append({"year": date, "form": "population", "file": dest.name,
                     "url": url, "bytes": dest.stat().st_size,
                     "source_page": "https://www.nomisweb.co.uk/ (ONS mid-year population estimates, NM_2002_1)"})
    total += dest.stat().st_size

# Archived ONS reference tables for the two historic years, on the boundary
# sets the RO authorities actually had.
ONS_DATASET_PAGE = ("https://www.ons.gov.uk/peoplepopulationandcommunity/"
                    "populationandmigration/populationestimates/datasets/"
                    "populationestimatesforukenglandandwalesscotlandandnorthernireland")
ONS_FILES = {
    "ukmye2013.zip": ONS_DATASET_PAGE.replace("https://www.ons.gov.uk", "https://www.ons.gov.uk/file?uri=") + "/mid2013/ukmye2013.zip",
    "ukmidyearestimates20182018ladcodes.xls": ONS_DATASET_PAGE.replace("https://www.ons.gov.uk", "https://www.ons.gov.uk/file?uri=") + "/mid20182019laboundaries/ukmidyearestimates20182018ladcodes.xls",
}
for fname, url in ONS_FILES.items():
    dest = RAW / fname
    if not dest.exists():
        resp = polite_get(url)
        dest.write_bytes(resp.content)
        print(f"fetched {dest.name}  {len(resp.content)/1024:.0f} KB")
    else:
        print(f"have    {dest.name}")
    manifest.append({"year": "2013" if "2013" in fname else "2018",
                     "form": "population", "file": dest.name, "url": url,
                     "bytes": dest.stat().st_size,
                     "source_page": ONS_DATASET_PAGE})
    total += dest.stat().st_size

# HMT GDP deflator (June 2026 QNA edition) - required for any across-year
# comparison; cash-terms time arcs are a known dunking.
DEFLATOR_URL = ("https://assets.publishing.service.gov.uk/media/"
                "6a43dbc7167a99cf0018d9a0/"
                "GDP_Deflators_Qtrly_National_Accounts_June_2026_update.xlsx")
dest = RAW / "gdp_deflator_jun2026.xlsx"
if not dest.exists():
    resp = polite_get(DEFLATOR_URL)
    dest.write_bytes(resp.content)
    print(f"fetched {dest.name}  {len(resp.content)/1024:.0f} KB")
else:
    print(f"have    {dest.name}")
manifest.append({"year": "1955-56 to 2025-26", "form": "gdp_deflator",
                 "file": dest.name, "url": DEFLATOR_URL,
                 "bytes": dest.stat().st_size,
                 "source_page": "https://www.gov.uk/government/statistics/gdp-deflators-at-market-prices-and-money-gdp-june-2026-quarterly-national-accounts"})
total += dest.stat().st_size

(HERE / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"\ntotal on disk {total/1024/1024:.1f} MB")
