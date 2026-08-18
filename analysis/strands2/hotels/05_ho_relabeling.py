# The Home Office labels went dark before the ledger did.
# Receipt: asylum-labeled lines fade after 2016-10 while overall publishing
# continues at ~1,000 rows/month until the ledger stops at 2018-06.
# Output: ho_relabeling_receipt.csv
import sqlite3, csv, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db")
cur = con.cursor()

with open("ho_relabeling_receipt.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["year_month", "ho_rows_total", "asylum_labeled_rows", "asylum_labeled_gbp"])
    tot = dict(cur.execute("""SELECT year_month, COUNT(*) FROM transactions
        WHERE is_dup=0 AND publisher='Home Office' AND year_month>='2016-01'
        GROUP BY 1""").fetchall())
    asy = {r[0]: (r[1], r[2]) for r in cur.execute("""SELECT year_month, COUNT(*), ROUND(SUM(amount))
        FROM transactions WHERE is_dup=0 AND publisher='Home Office' AND year_month>='2016-01'
        AND (expense_type LIKE '%asylum%' OR expense_type LIKE '%refugee%') GROUP BY 1""").fetchall()}
    for m in sorted(tot):
        a = asy.get(m, (0, 0))
        w.writerow([m, tot[m], a[0], a[1]])

# where the contractor money moved: labels used for Clearsprings/Serco/G4S/Sodexo after 2016-10
with open("ho_relabeling_contractor_labels.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["supplier_raw", "expense_type", "first_month", "last_month", "n", "gbp"])
    for r in cur.execute("""SELECT supplier_raw, expense_type, MIN(year_month), MAX(year_month),
        COUNT(*), ROUND(SUM(amount)) FROM transactions
        WHERE is_dup=0 AND publisher='Home Office' AND year_month>='2016-11'
        AND (supplier_raw LIKE 'CLEARSPRING%' OR supplier_raw LIKE 'SERCO%'
             OR supplier_raw LIKE 'G4S%' OR supplier_raw LIKE 'SODEXO%')
        GROUP BY 1,2 ORDER BY 6 DESC"""):
        w.writerow(r)
print("done")
