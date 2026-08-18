# Step 1: generous pattern match on supplier_raw + expense_type generics.
# Output: eyeball files. NOTHING counts until eyeballed.
import sqlite3, csv, os

DB = r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db"
OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\bailiffs"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# Generous firm patterns (SQL LIKE, case-insensitive via upper())
FIRM_PATTERNS = {
    "MARSTON": "%MARSTON%",
    "BRISTOW": "%BRISTOW%",
    "JACOBS": "%JACOBS%",
    "EQUITA": "%EQUITA%",
    "ROSSENDALE": "%ROSSENDALE%",
    "NEWLYN": "%NEWLYN%",
    "DUKES": "%DUKE%",
    "CDER": "%CDER%",
    "ANDREW_JAMES": "%ANDREW JAMES%",
    "EXCEL": "%EXCEL%",
    # extra known enforcement/debt firms, generous
    "WHYTE": "%WHYTE%",
    "RUNDLE": "%RUNDLE%",
    "JBW": "%JBW%",
    "PHOENIX_COMM": "%PHOENIX COMMERCIAL%",
    "SWIFT_CREDIT": "%SWIFT CREDIT%",
    "ROSS_ROBERTS": "%ROSS & ROBERTS%",
    "CHANDLERS": "%CHANDLER%",
    "COLLECTICA": "%COLLECTICA%",
    "CONFERO": "%CONFERO%",
    "STA_INTL": "%STA INTERNATIONAL%",
}

with open(os.path.join(OUT, "eyeball_supplier_matches.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pattern", "supplier_raw", "publisher", "txns", "gbp", "first", "last", "expense_types_sample"])
    for name, pat in FIRM_PATTERNS.items():
        q = """
        select supplier_raw, publisher, count(*) txns, round(sum(amount),2) gbp,
               min(year_month) first, max(year_month) last,
               group_concat(distinct expense_type) ets
        from transactions
        where upper(supplier_raw) like ?
        group by supplier_raw, publisher
        order by gbp desc
        """
        for r in con.execute(q, (pat,)):
            ets = (r["ets"] or "")[:300]
            w.writerow([name, r["supplier_raw"], r["publisher"], r["txns"], r["gbp"], r["first"], r["last"], ets])

# expense_type generics
ET_PATTERNS = {
    "ENFORCEMENT": "%ENFORC%",
    "BAILIFF": "%BAILIFF%",
    "DEBT_RECOVERY": "%DEBT%",
    "SUMMONS": "%SUMMON%",
    "COLLECTION_AGENT": "%COLLECTION%",
}
with open(os.path.join(OUT, "eyeball_expense_types.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pattern", "expense_type", "publisher", "txns", "gbp", "n_suppliers", "top_suppliers"])
    for name, pat in ET_PATTERNS.items():
        q = """
        select expense_type, publisher, count(*) txns, round(sum(amount),2) gbp,
               count(distinct supplier_raw) ns
        from transactions
        where upper(expense_type) like ?
        group by expense_type, publisher
        order by gbp desc
        """
        for r in con.execute(q, (pat,)):
            top = con.execute(
                """select supplier_raw, round(sum(amount),2) s from transactions
                   where expense_type = ? and publisher = ?
                   group by supplier_raw order by s desc limit 5""",
                (r["expense_type"], r["publisher"])).fetchall()
            tops = "; ".join(f"{t[0]}={t[1]}" for t in top)[:300]
            w.writerow([name, r["expense_type"], r["publisher"], r["txns"], r["gbp"], r["ns"], tops])

print("done")
