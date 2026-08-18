"""Rebuild work.sqlite (derived cache, ~318MB, deliberately not kept in repo).
Run from repo root: python analysis/strands2/hotels/make_work_db.py  (~2 min)
Then: python analysis/strands2/hotels/build_outputs.py  to regenerate every CSV.
"""
import sqlite3, os
ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
wpath = os.path.join(os.path.dirname(__file__), "work.sqlite")
if os.path.exists(wpath): os.remove(wpath)
con = sqlite3.connect(os.path.join(ROOT, "analysis", "spending", "corpus.db"))
con.execute("ATTACH ? AS w", (wpath,))
con.execute("""CREATE TABLE w.sup_year AS
  SELECT publisher, UPPER(TRIM(supplier_raw)) AS s, SUBSTR(year_month,1,4) AS yr,
         COUNT(*) AS n, SUM(amount) AS gbp
  FROM transactions WHERE is_dup=0 GROUP BY 1,2,3""")
con.execute("""CREATE TABLE w.exp_year AS
  SELECT publisher, UPPER(TRIM(COALESCE(expense_type,''))) AS et, SUBSTR(year_month,1,4) AS yr,
         COUNT(*) AS n, SUM(amount) AS gbp
  FROM transactions WHERE is_dup=0 GROUP BY 1,2,3""")
con.execute("""CREATE TABLE w.council AS
  SELECT * FROM transactions WHERE is_dup=0 AND publisher IN (
   'Blaby District Council','Bristol City Council','Cheltenham Borough Council',
   'Eden District Council','Former council of North Yorkshire','Former district of Harrogate',
   'London Borough of Richmond Upon Thames','North Yorkshire Council','Plymouth City Council',
   'Royal Borough of Greenwich','Rushmoor Borough Council','South Gloucestershire Council',
   'Uttlesford District Council')""")
con.commit(); con.close()
print("work.sqlite rebuilt")
