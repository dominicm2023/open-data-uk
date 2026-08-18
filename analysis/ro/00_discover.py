"""Discover the per-year RO 'individual local authority data - outturn' pages.

The index's catalogue entries for 'Local Authority Revenue Expenditure and
Financing, England' are availability=webpage: data.gov.uk landing pages that
forward to the gov.uk statistical collection. This script walks the collection
page once and records every per-year outturn page URL, so the fetch step can
scope deliberately instead of hoovering.
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

COLLECTION = "https://www.gov.uk/government/collections/local-authority-revenue-expenditure-and-financing"
OUT = Path(__file__).parent / "discovered_pages.json"

resp = requests.get(COLLECTION, headers=HEADERS, timeout=60)
resp.raise_for_status()
html = resp.text

# Per-year statistics pages are /government/statistics/... links.
links = sorted(set(re.findall(r'href="(/government/statistics/[^"]+)"', html)))
outturn = [l for l in links if "outturn" in l and "individual" in l]
other = [l for l in links if l not in outturn]

OUT.write_text(json.dumps({
    "collection": COLLECTION,
    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "individual_la_outturn_pages": outturn,
    "other_statistics_pages": other,
}, indent=2))
print(f"{len(outturn)} individual-LA outturn pages, {len(other)} other pages")
for l in outturn:
    print("  ", l)
