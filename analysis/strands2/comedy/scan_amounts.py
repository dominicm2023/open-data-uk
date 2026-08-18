import sqlite3

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')

print("=== 1. Who publishes 'Panto Expenditure', 'Flag Flying', 'Civic Regalia', 'Mayor-making', 'Medals', horseracing, bumble bees ===")
for et in ['Panto Expenditure','Flag Flying','Civic Regalia','Mayor-making','Medals',
           'Bumble Bee Colonies (Audax) each 10-20 workers','Lifting arm for dog doublet',
           'Donation to the Swan Sanctuary','Mayoral Charity Dinner Dance']:
    for r in db.execute("SELECT publisher, count(*), sum(amount), min(date), max(date) FROM transactions WHERE expense_type=? GROUP BY publisher", (et,)):
        print(f"  {et!r}: {r}")
for ea in ['Tote Proceeds to Horseracing','Support for Horseracing']:
    for r in db.execute("SELECT publisher, supplier_raw, amount, date, source_file FROM transactions WHERE expense_area=? LIMIT 5", (ea,)):
        print(f"  {ea!r}: {r}")

print("\n=== 2. Tiny positive amounts (0 < amount <= 0.10), by publisher ===")
for r in db.execute("SELECT publisher, count(*) FROM transactions WHERE amount > 0 AND amount <= 0.10 AND is_dup=0 GROUP BY publisher ORDER BY 2 DESC LIMIT 15"):
    print(f"  {r}")

print("\n=== 3. Smallest 30 positive amounts with detail ===")
for r in db.execute("SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions WHERE amount > 0 AND amount < 0.05 AND is_dup=0 ORDER BY amount LIMIT 30"):
    print(f"  {r}")

print("\n=== 4. Penny payments (amount in 0.01, 0.02) to big-name suppliers ===")
for r in db.execute("""SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions
    WHERE amount IN (0.01, 0.02) AND is_dup=0 LIMIT 40"""):
    print(f"  {r}")

print("\n=== 5. Perfectly round 1,000,000s ===")
for r in db.execute("""SELECT publisher, supplier_raw, count(*), min(date), max(date) FROM transactions
    WHERE amount = 1000000 AND is_dup=0 GROUP BY publisher, supplier_raw ORDER BY 3 DESC LIMIT 25"""):
    print(f"  {r}")

print("\n=== 6. STALLION AND UNICORN detail ===")
for r in db.execute("SELECT * FROM transactions WHERE supplier_raw LIKE '%STALLION AND UNICORN%'"):
    print(f"  {r}")

print("\n=== 7. ITV TEXT SANTA detail ===")
for r in db.execute("SELECT * FROM transactions WHERE supplier_raw LIKE '%TEXT SANTA%'"):
    print(f"  {r}")
