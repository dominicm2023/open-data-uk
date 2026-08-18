# 03_headline.py — chart-ready headline table: one row per censused firm.
import sqlite3, os, csv
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "..", "spending", "corpus.db")

v2c = {}
with open(os.path.join(HERE, "variants.csv"), newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        v2c[row["variant"]] = row["company"]
names = list(v2c)

con = sqlite3.connect(CORPUS)
agg = defaultdict(lambda: [0.0, 0, set(), None, None])  # gbp, txns, pubs, first, last
paypot = defaultdict(float)
for i in range(0, len(names), 500):
    chunk = names[i:i+500]
    q = ",".join("?" * len(chunk))
    for sup, pub, gbp, tx, lo, hi in con.execute(f"""
        SELECT supplier_raw, publisher, SUM(amount), COUNT(*), MIN(year_month), MAX(year_month)
        FROM transactions WHERE is_dup=0 AND supplier_raw IN ({q})
        GROUP BY supplier_raw, publisher""", chunk):
        c = v2c[sup]; a = agg[c]
        a[0] += gbp; a[1] += tx; a[2].add(pub)
        if lo: a[3] = lo if a[3] is None else min(a[3], lo)
        if hi: a[4] = hi if a[4] is None else max(a[4], hi)
        paypot[(c, pub)] += gbp

with open(os.path.join(HERE, "headline_firms.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["company", "gbp_total", "txns", "publishers", "first_ym", "last_ym", "top_payer", "top_payer_gbp"])
    for c, a in sorted(agg.items(), key=lambda kv: -kv[1][0]):
        top = max(((p, v) for (cc, p), v in paypot.items() if cc == c), key=lambda x: x[1])
        w.writerow([c, round(a[0], 2), a[1], len(a[2]), a[3], a[4], top[0], round(top[1], 2)])
        print(f"{c:28} {a[0]/1e6:>9,.1f}m {a[1]:>7,}tx {len(a[2]):>3}pub {a[3]}..{a[4]}  top: {top[0]} ({top[1]/1e6:,.0f}m)")
