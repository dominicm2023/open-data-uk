# 04_prices.py — Q4: "same thing, different prices" — the one honest candidate.
# Payment lines are invoice totals, not unit prices, so price comparison is only
# even conceivable where a supplier charges a FIXED RECURRING amount. Test:
# find (normalised supplier, exact amount) pairs where the same amount recurs in
# >= 3 distinct months within a publisher, for >= 2 different publishers —
# i.e. two bodies each paying the same supplier a steady monthly amount.
# Then inspect expense_type to see whether the recurring amounts are ever
# comparable units (same product) or just different contract totals.
import sqlite3, os, re, csv
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "spending", "corpus.db")

DROP = {"LTD", "LIMITED", "PLC", "AND"}
_punct = re.compile(r"[^A-Z0-9 ]+")
def norm(s):
    s = _punct.sub(" ", s.upper())
    t = [x for x in s.split() if x not in DROP]
    if t and t[0] == "THE":
        t = t[1:]
    return " ".join(t)

def main():
    con = sqlite3.connect(CORPUS)
    # recurring identical amounts per (supplier, publisher): >=3 distinct months
    rows = con.execute("""
        SELECT supplier_raw, publisher, amount,
               COUNT(DISTINCT year_month) AS months, COUNT(*) AS n,
               MIN(year_month), MAX(year_month),
               GROUP_CONCAT(DISTINCT expense_type)
        FROM transactions
        WHERE is_dup=0 AND supplier_raw<>'' AND amount > 100 AND year_month IS NOT NULL
        GROUP BY supplier_raw, publisher, amount
        HAVING months >= 3
    """).fetchall()
    print(f"recurring (supplier_raw, publisher, amount) triples with >=3 months: {len(rows):,}")

    by_key = defaultdict(list)
    for raw, pub, amt, months, n, ym0, ym1, etypes in rows:
        by_key[(norm(raw), amt)].append((pub, months, n, ym0, ym1, etypes))
    multi = {k: v for k, v in by_key.items() if len({p for p, *_ in v}) >= 2}
    print(f"(normalised supplier, amount) pairs recurring in >=2 publishers: {len(multi):,}")

    out = os.path.join(HERE, "recurring_candidates.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["supplier_normalised", "amount", "publisher", "months", "payments", "first_ym", "last_ym", "expense_types"])
        for (nn, amt), pubs in sorted(multi.items(), key=lambda kv: -kv[0][1]):
            for p in pubs:
                w.writerow([nn, amt, p[0], p[1], p[2], p[3], p[4], (p[5] or "")[:120]])
    print(f"wrote {out}")

    # and the counter-test: same normalised supplier recurring monthly in >=2
    # publishers with DIFFERENT amounts (the shape a price story would need)
    sup_pubs = defaultdict(set)
    for (nn, amt), pubs in by_key.items():
        for p, *_ in pubs:
            sup_pubs[nn].add((p, amt))
    diff = {nn: v for nn, v in sup_pubs.items()
            if len({p for p, a in v}) >= 2 and len({a for p, a in v}) >= 2}
    print(f"suppliers with recurring amounts in >=2 publishers at different amounts: {len(diff):,}")
    for nn, (pubs) in sorted(multi.items(), key=lambda kv: -kv[0][1])[:25]:
        print(f"  {nn[0][:50]:50} {nn[1]:>12,.2f}  x{len(pubs)} publishers")

if __name__ == "__main__":
    main()
