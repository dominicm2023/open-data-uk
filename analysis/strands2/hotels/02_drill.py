import sqlite3, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db")
cur = con.cursor()

def q(title, sql, args=()):
    print("=" * 10, title)
    for r in cur.execute(sql, args).fetchall():
        print(" | ".join(str(x) for x in r))
    print()

# A: Bristol Holiday Inn — what expense_type/area, by year
q("Bristol 'Holiday Inn' by year/expense", """
SELECT substr(year_month,1,4) y, expense_type, expense_area, COUNT(*), ROUND(SUM(amount))
FROM transactions WHERE is_dup=0 AND publisher='Bristol City Council' AND supplier_raw='Holiday Inn'
GROUP BY y, expense_type, expense_area ORDER BY y""")

# B: Bristol TPP B&B line by year
q("Bristol 'TPP - B&B payments to landlords' by year", """
SELECT substr(year_month,1,4) y, COUNT(*), ROUND(SUM(amount)), COUNT(DISTINCT supplier_raw)
FROM transactions WHERE is_dup=0 AND publisher='Bristol City Council' AND expense_type='TPP - B&B payments to landlords'
GROUP BY y ORDER BY y""")

q("Bristol TPP B&B top 40 recipients", """
SELECT supplier_raw, COUNT(*), ROUND(SUM(amount))
FROM transactions WHERE is_dup=0 AND publisher='Bristol City Council' AND expense_type='TPP - B&B payments to landlords'
GROUP BY supplier_raw ORDER BY SUM(amount) DESC LIMIT 40""")

# C: Uttlesford — all homelessness/TA lines by year
q("Uttlesford homelessness/TA expense lines by year", """
SELECT substr(year_month,1,4) y, expense_type, COUNT(*), ROUND(SUM(amount))
FROM transactions WHERE is_dup=0 AND publisher='Uttlesford District Council'
AND (expense_type LIKE '%omeless%' OR expense_type LIKE '%emporary Accommodation%' OR expense_type LIKE '%Emerg Accommodation%')
GROUP BY y, expense_type ORDER BY y, SUM(amount) DESC""")

q("Uttlesford TA top suppliers (all homeless/TA lines)", """
SELECT supplier_raw, MIN(year_month), MAX(year_month), COUNT(*), ROUND(SUM(amount))
FROM transactions WHERE is_dup=0 AND publisher='Uttlesford District Council'
AND (expense_type LIKE '%omeless%' OR expense_type LIKE '%emporary Accommodation%' OR expense_type LIKE '%Emerg Accommodation%')
GROUP BY supplier_raw ORDER BY SUM(amount) DESC LIMIT 30""")

# D: Rushmoor B&B by year
q("Rushmoor 'Bed and Breakfast' by year", """
SELECT substr(year_month,1,4) y, COUNT(*), ROUND(SUM(amount)), COUNT(DISTINCT supplier_raw)
FROM transactions WHERE is_dup=0 AND publisher='Rushmoor Borough Council' AND expense_type='Bed and Breakfast'
GROUP BY y ORDER BY y""")

q("Rushmoor B&B top suppliers", """
SELECT supplier_raw, MIN(year_month), MAX(year_month), COUNT(*), ROUND(SUM(amount))
FROM transactions WHERE is_dup=0 AND publisher='Rushmoor Borough Council' AND expense_type='Bed and Breakfast'
GROUP BY supplier_raw ORDER BY SUM(amount) DESC LIMIT 25""")

# E: Home Office asylum lines per year — the receipt for the null
q("Home Office asylum-type lines by year", """
SELECT substr(year_month,1,4) y, COUNT(*), ROUND(SUM(amount)/1e6,1)
FROM transactions WHERE is_dup=0 AND publisher='Home Office'
AND (expense_type LIKE '%asylum%' OR expense_type LIKE '%refugee%')
GROUP BY y ORDER BY y""")

q("Home Office asylum top suppliers", """
SELECT supplier_raw, MIN(year_month), MAX(year_month), COUNT(*), ROUND(SUM(amount)/1e6,1)
FROM transactions WHERE is_dup=0 AND publisher='Home Office'
AND (expense_type LIKE '%asylum%' OR expense_type LIKE '%refugee%')
GROUP BY supplier_raw ORDER BY SUM(amount) DESC LIMIT 25""")

# F: eyeball ambiguous lines
q("DWP 'TA LPS BACS Payments' rows", """
SELECT year_month, supplier_raw, amount, expense_area FROM transactions
WHERE is_dup=0 AND publisher='Department for Work and Pensions' AND expense_type='TA LPS BACS Payments'""")

q("Tate 'Temporary Accommodation' suppliers", """
SELECT supplier_raw, COUNT(*), ROUND(SUM(amount)) FROM transactions
WHERE is_dup=0 AND publisher='Tate' AND expense_type LIKE 'Temporary Accommodation%'
GROUP BY supplier_raw ORDER BY SUM(amount) DESC""")

# G: Britannia Hotels check across whole corpus (the asylum chain)
q("Britannia Hotels / Serco / Clearsprings / Mears / G4S accommodation check", """
SELECT publisher, supplier_raw, MIN(year_month), MAX(year_month), COUNT(*), ROUND(SUM(amount)/1e6,2)
FROM transactions WHERE is_dup=0 AND (
  supplier_raw LIKE '%BRITANNIA HOTEL%' OR supplier_raw LIKE '%CLEARSPRING%'
  OR supplier_raw LIKE '%SERCO%' OR supplier_raw LIKE '%MEARS%' OR supplier_raw LIKE '%G4S%')
GROUP BY publisher, supplier_raw HAVING SUM(amount) > 500000 ORDER BY SUM(amount) DESC LIMIT 30""")
