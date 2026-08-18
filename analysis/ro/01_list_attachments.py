"""List attachments (title, URL, format, size) for the chosen RO vintages.

Uses the gov.uk content API rather than scraping HTML: every statistics page
is available as JSON at /api/content/<path>, with attachment metadata
including content_type and file_size. Three vintages, deliberately:

  2024-25  latest published outturn
  2018-19  a pre-pandemic mid point
  2013-14  the earliest cheap vintage with the modern form layout

Nothing is downloaded here except three small JSON documents.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent import HEADERS

YEARS = {
    "2024-25": "/government/statistics/local-authority-revenue-expenditure-and-financing-england-2024-to-2025-individual-local-authority-data-outturn",
    "2018-19": "/government/statistics/local-authority-revenue-expenditure-and-financing-england-2018-to-2019-individual-local-authority-data-outturn",
    "2013-14": "/government/statistics/local-authority-revenue-expenditure-and-financing-england-2013-to-2014-individual-local-authority-data-outturn",
}

OUT = Path(__file__).parent / "attachments.json"

result = {}
for year, path in YEARS.items():
    url = "https://www.gov.uk/api/content" + path
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    doc = resp.json()
    atts = []
    for det in doc.get("details", {}).get("attachments", []):
        atts.append({
            "title": det.get("title"),
            "url": det.get("url"),
            "content_type": det.get("content_type"),
            "file_size": det.get("file_size"),
        })
    result[year] = {"page": "https://www.gov.uk" + path, "attachments": atts}
    print(f"{year}: {len(atts)} attachments")
    for a in atts:
        size = a["file_size"]
        size_kb = f"{size/1024:.0f} KB" if size else "?"
        print(f"    {size_kb:>10}  {a['title']}")
    time.sleep(0.5)

OUT.write_text(json.dumps(result, indent=2))
