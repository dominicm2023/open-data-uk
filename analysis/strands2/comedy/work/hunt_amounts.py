import sqlite3, csv
con = sqlite3.connect('C:/Users/domin/Documents/Open Data/analysis/spending/corpus.db')
cur = con.cursor()
W = 'is_dup=0 AND supplier_raw<>\'\''

print('=== micro-payments (0 < amount <= 0.05) count by publisher ===')
for r in cur.execute(f"SELECT publisher, COUNT(*), MIN(amount), SUM(amount) FROM transactions WHERE {W} AND amount>0 AND amount<=0.05 GROUP BY publisher ORDER BY 2 DESC LIMIT 15"):
    print(r)

print()
print('=== smallest positive payments overall (bottom 25) ===')
for r in cur.execute(f"SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions WHERE {W} AND amount>0 ORDER BY amount ASC LIMIT 25"):
    print(r)

print()
print('=== 1p payments to recognisable big suppliers ===')
for r in cur.execute(f"""SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions
  WHERE {W} AND amount=0.01 AND (UPPER(supplier_raw) LIKE '%CAPITA%' OR UPPER(supplier_raw) LIKE '%SERCO%' OR UPPER(supplier_raw) LIKE '%G4S%'
   OR UPPER(supplier_raw) LIKE '%AMAZON%' OR UPPER(supplier_raw) LIKE '%MICROSOFT%' OR UPPER(supplier_raw) LIKE '%BT %'
   OR UPPER(supplier_raw) LIKE '%VIRGIN%' OR UPPER(supplier_raw) LIKE '%DELOITTE%' OR UPPER(supplier_raw) LIKE '%KPMG%'
   OR UPPER(supplier_raw) LIKE '%PWC%' OR UPPER(supplier_raw) LIKE '%ERNST%' OR UPPER(supplier_raw) LIKE '%FUJITSU%'
   OR UPPER(supplier_raw) LIKE '%ATOS%' OR UPPER(supplier_raw) LIKE '%VODAFONE%' OR UPPER(supplier_raw) LIKE '%SODEXO%') LIMIT 30"""):
    print(r)

print()
print('=== exactly 1,000,000.00 rows: count and sample ===')
print(cur.execute(f"SELECT COUNT(*) FROM transactions WHERE {W} AND amount=1000000").fetchone())
for r in cur.execute(f"SELECT publisher, supplier_raw, amount, date, expense_type FROM transactions WHERE {W} AND amount=1000000 LIMIT 15"):
    print(r)

print()
print('=== Salisbury micro rows sample ===')
for r in cur.execute(f"SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions WHERE {W} AND publisher LIKE 'Salisbury%' AND amount>0 AND amount<=0.05 ORDER BY amount LIMIT 10"):
    print(r)
print(cur.execute(f"SELECT COUNT(*), MIN(amount) FROM transactions WHERE {W} AND publisher LIKE 'Salisbury%' AND amount>0 AND amount<1""").fetchone())
