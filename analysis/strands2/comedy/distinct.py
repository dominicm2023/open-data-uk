import sqlite3, csv

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')
rows = db.execute(
    "SELECT supplier_raw, publisher, count(*) c, sum(amount) s "
    "FROM transactions GROUP BY supplier_raw, publisher").fetchall()
print(len(rows))
with open(r'C:\Users\domin\Documents\Open Data\analysis\strands2\comedy\distinct_suppliers.csv','w',newline='',encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['supplier_raw','publisher','n','total'])
    for r in rows:
        w.writerow(r)
