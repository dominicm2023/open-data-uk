# 02_series.py — THE OUTSOURCED STATE: time series from the censused variants.
# Reads variants.csv (built by 01_census.py), queries corpus.db directly.
# Clean set everywhere: is_dup=0 AND supplier_raw<>''.
# Year = calendar year from year_month; rows with NULL year_month land in year=''
# (kept and reported, never silently dropped — this is the Richmond ledger).
import sqlite3, os, csv, time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "..", "spending", "corpus.db")

COUNCILS = [  # every council-like publisher in the corpus; canonical-9 flag from spending/findings.json council_coverage
    ("Blaby District Council", 1),
    ("Bristol City Council", 0),      # register-match artifact in findings.json; it IS a council, flagged 0 only to mirror the canonical-9 list
    ("Cheltenham Borough Council", 1),
    ("Eden District Council", 0),     # abolished 2023, not in the register the canonical 9 was matched against
    ("Former council of North Yorkshire", 1),
    ("Former district of Harrogate", 0),
    ("London Borough of Richmond Upon Thames", 1),
    ("North Yorkshire Council", 0),   # successor of 'Former council of North Yorkshire'
    ("Plymouth City Council", 1),
    ("Royal Borough of Greenwich", 1),
    ("Rushmoor Borough Council", 1),
    ("South Gloucestershire Council", 1),
    ("Uttlesford District Council", 1),
]
COUNCIL_NAMES = [c for c, _ in COUNCILS]
FIRMS_PROPER = ["Capita", "Serco", "G4S", "Mitie", "Sodexo", "Amey", "Interserve",
                "Kier", "Sopra Steria", "Liberata", "Veolia", "Biffa", "Suez", "Carillion"]
ARC_COMPANIES = ["Carillion", "CarillionAmey (JV)", "CarillionEnterprise (JV)", "Interserve", "Amey"]
WASTE = ["Veolia", "Biffa", "Suez"]

def main():
    t0 = time.time()
    v2c = {}
    with open(os.path.join(HERE, "variants.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v2c[row["variant"]] = row["company"]
    names = list(v2c)
    print(f"{len(names)} included variant strings across {len(set(v2c.values()))} companies")

    con = sqlite3.connect(CORPUS)
    # one pass: per (supplier_raw, publisher, year_month) for censused strings
    rows = []
    for i in range(0, len(names), 500):
        chunk = names[i:i+500]
        q = ",".join("?" * len(chunk))
        rows += con.execute(f"""
            SELECT supplier_raw, publisher, COALESCE(year_month,''), SUM(amount), COUNT(*)
            FROM transactions
            WHERE is_dup=0 AND supplier_raw IN ({q})
            GROUP BY supplier_raw, publisher, year_month
        """, chunk).fetchall()
    print(f"censused scan: {len(rows)} cells in {time.time()-t0:.0f}s")

    firm_year   = defaultdict(float); firm_year_tx = defaultdict(int)
    firm_py     = defaultdict(float)
    firm_month  = defaultdict(float)
    for sup, pub, ym, gbp, tx in rows:
        c = v2c[sup]; y = ym[:4]
        firm_year[(c, y)] += gbp; firm_year_tx[(c, y)] += tx
        firm_py[(c, pub, y)] += gbp
        if c in ARC_COMPANIES:
            firm_month[(c, ym)] += gbp

    with open(os.path.join(HERE, "yearly_by_firm.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "year", "gbp", "txns"])
        for (c, y) in sorted(firm_year):
            w.writerow([c, y, round(firm_year[(c, y)], 2), firm_year_tx[(c, y)]])

    with open(os.path.join(HERE, "yearly_by_firm_payer.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "publisher", "year", "gbp"])
        for (c, p, y) in sorted(firm_py):
            w.writerow([c, p, y, round(firm_py[(c, p, y)], 2)])

    with open(os.path.join(HERE, "collapse_arcs_monthly.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "year_month", "gbp"])
        for (c, ym) in sorted(firm_month):
            w.writerow([c, ym, round(firm_month[(c, ym)], 2)])

    # ---- council shares: denominator = ALL clean spend per council-year ----
    denom = {}
    qmarks = ",".join("?" * len(COUNCIL_NAMES))
    for pub, y, gbp, tx in con.execute(f"""
        SELECT publisher, COALESCE(substr(year_month,1,4),''), SUM(amount), COUNT(*)
        FROM transactions
        WHERE is_dup=0 AND supplier_raw<>'' AND publisher IN ({qmarks})
        GROUP BY publisher, substr(year_month,1,4)
    """, COUNCIL_NAMES):
        denom[(pub, y)] = (gbp, tx)

    canon = dict(COUNCILS)
    with open(os.path.join(HERE, "council_share.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["publisher", "canonical9", "year", "ledger_gbp", "ledger_txns", "outsourcer_gbp", "outsourcer_share_pct"])
        for (pub, y) in sorted(denom):
            tot, tx = denom[(pub, y)]
            out = sum(firm_py.get((c, pub, y), 0.0) for c in FIRMS_PROPER)
            share = 100.0 * out / tot if tot else None
            w.writerow([pub, canon[pub], y, round(tot, 2), tx, round(out, 2),
                        round(share, 3) if share is not None else ""])

    with open(os.path.join(HERE, "council_share_by_firm.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["publisher", "year", "company", "gbp"])
        for (c, p, y) in sorted(firm_py):
            if p in canon and c in FIRMS_PROPER and abs(firm_py[(c, p, y)]) > 0.005:
                w.writerow([p, y, c, round(firm_py[(c, p, y)], 2)])

    # ---- waste giants per payer-year ----
    with open(os.path.join(HERE, "waste_by_payer_year.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "publisher", "year", "gbp"])
        for (c, p, y) in sorted(firm_py):
            if c in WASTE and abs(firm_py[(c, p, y)]) > 0.005:
                w.writerow([c, p, y, round(firm_py[(c, p, y)], 2)])

    # quick console digests
    print("\n-- yearly totals, firms proper (GBP m) --")
    years = sorted({y for (c, y) in firm_year if y})
    for c in FIRMS_PROPER + ["CarillionAmey (JV)", "CarillionEnterprise (JV)", "SSCL (Sopra Steria JV)"]:
        tot = sum(firm_year[(c, y)] for y in years + [""] if (c, y) in firm_year)
        print(f"  {c:26} total {tot/1e6:>9,.1f}m")
    nullers = [(c, firm_year[(c, '')]) for c in set(v2c.values()) if (c, '') in firm_year]
    print(f"  NULL-year cells (Richmond etc.): {[(c, round(g)) for c, g in nullers]}")
    print(f"done in {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
