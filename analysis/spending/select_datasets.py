"""Select verified spending datasets from index.db and emit selection.json.

Findable filter (as specified for the spending-map analysis):
  - not a duplicate, not retired
  - availability='data', formats_norm LIKE '%CSV%', license_norm IS NOT NULL
  - title matches spending terms
Join to resources for URLs; dedupe by URL (first dataset wins).

Fetch policy: we only fetch resources whose declared format is CSV or NULL,
or whose URL contains '.csv'. Everything else is recorded in selection.json
with fetch=False so the skip is auditable, not silent.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

TERMS = ["spend", "expenditure", "payments to supplier", "supplier payment",
         "purchase card", "invoice"]

Q = """
SELECT d.key, d.publisher, d.title, res.url, res.format_norm
FROM datasets d JOIN resources res ON res.dataset_key = d.key
WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key=d.key)
  AND NOT EXISTS (SELECT 1 FROM retired r WHERE r.key=d.key)
  AND d.availability='data'
  AND d.formats_norm LIKE '%CSV%'
  AND d.license_norm IS NOT NULL
  AND ({title_clause})
ORDER BY d.publisher, d.key
""".format(title_clause=" OR ".join(f"lower(d.title) LIKE '%{t}%'" for t in TERMS))


def main():
    con = sqlite3.connect(ROOT / "index.db")
    rows = list(con.execute(Q))
    seen = {}
    for key, publisher, title, url, fmt in rows:
        if url in seen:
            continue
        csvish = (fmt == "CSV") or (fmt is None) or (".csv" in url.lower())
        seen[url] = {
            "dataset_key": key,
            "publisher": publisher,
            "title": title,
            "format_norm": fmt,
            "fetch": csvish,
        }
    n_datasets = len({v["dataset_key"] for v in seen.values()})
    n_pub = len({v["publisher"] for v in seen.values()})
    out = {"datasets": n_datasets, "publishers": n_pub,
           "urls": len(seen), "to_fetch": sum(v["fetch"] for v in seen.values()),
           "selection": seen}
    (HERE / "selection.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"datasets={n_datasets} publishers={n_pub} urls={len(seen)} "
          f"to_fetch={out['to_fetch']}")


if __name__ == "__main__":
    main()
