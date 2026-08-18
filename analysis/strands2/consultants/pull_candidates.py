"""Pull candidate supplier_raw strings for consultant/agency firms — generous match, for eyeballing."""
import sqlite3, csv, os

DB = r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db"
OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\consultants"

# firm -> list of LIKE patterns (uppercased match against upper(supplier_raw))
PATTERNS = {
    "Deloitte":   ["%DELOITTE%"],
    "PwC":        ["%PWC%", "%PRICEWATERHOUSE%", "%PRICE WATERHOUSE%"],
    "EY":         ["%ERNST%", "EY", "EY %", "% EY", "% EY %", "EY-%", "EY.%", "EY,%", "%(EY)%"],
    "KPMG":       ["%KPMG%"],
    "McKinsey":   ["%MCKINSEY%", "%MC KINSEY%", "%MACKINSEY%"],
    "Bain":       ["%BAIN%"],
    "BCG":        ["%BCG%", "%BOSTON CONSULTING%"],
    "PA Consulting": ["%PA CONSULTING%", "%P A CONSULTING%", "%P.A. CONSULTING%"],
    "Gartner":    ["%GARTNER%"],
    # agency staff
    "Hays":       ["%HAYS%"],
    "Reed":       ["%REED%"],
    "Michael Page": ["%MICHAEL PAGE%", "%PAGE PERSONNEL%", "%PAGEGROUP%", "%PAGE GROUP%"],
    "Matrix SCM": ["%MATRIX%"],
    "Comensura":  ["%COMENSURA%"],
    "Adecco":     ["%ADECCO%"],
    "Manpower":   ["%MANPOWER%"],
}

con = sqlite3.connect(DB)
cur = con.cursor()

rows_out = []
for firm, pats in PATTERNS.items():
    where = " OR ".join("upper(supplier_raw) LIKE ?" for _ in pats)
    q = f"""
      SELECT supplier_raw, COUNT(*) n, ROUND(SUM(amount),2) gbp,
             COUNT(DISTINCT publisher) npub,
             GROUP_CONCAT(DISTINCT publisher)
      FROM transactions
      WHERE is_dup=0 AND ({where})
      GROUP BY supplier_raw
      ORDER BY SUM(amount) DESC
    """
    for r in cur.execute(q, pats):
        rows_out.append([firm, r[0], r[1], r[2], r[3], r[4]])

with open(os.path.join(OUT, "candidates_raw.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["firm", "supplier_raw", "txns", "gbp", "n_publishers", "publishers"])
    w.writerows(rows_out)

print(f"{len(rows_out)} candidate strings written")
# quick per-firm counts
from collections import Counter
c = Counter(r[0] for r in rows_out)
for k, v in c.items():
    print(f"{k:15s} {v:5d} distinct strings")
