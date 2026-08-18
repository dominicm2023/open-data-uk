# One-pass census: distinct supplier strings + distinct expense_type strings
# matched against hotel / TA / B&B patterns. Output: candidate lists to eyeball.
import sqlite3, re, csv, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db")
cur = con.cursor()

print("building supplier aggregate (one scan)...", flush=True)
cur.execute("""
CREATE TEMP TABLE sup AS
SELECT supplier_raw, publisher, COUNT(*) n, SUM(amount) amt
FROM transactions WHERE is_dup=0
GROUP BY supplier_raw, publisher
""")
print("building expense_type aggregate...", flush=True)
cur.execute("""
CREATE TEMP TABLE et AS
SELECT expense_type, publisher, COUNT(*) n, SUM(amount) amt
FROM transactions WHERE is_dup=0
GROUP BY expense_type, publisher
""")

sup_pat = re.compile(
    r"TRAVELODGE|TRAVEL\s*LODGE|PREMIER\s*INN|WHITBREAD|BRITANNIA|HOLIDAY\s*INN|"
    r"INTERCONTINENTAL|\bIHG\b|\bIBIS\b|ACCOR\b|HOTEL|B\s*&\s*B|BED\s*(&|AND)\s*BREAKFAST|"
    r"GUEST\s*HOUSE|GUESTHOUSE|\bLODGE\b|MARRIOTT|HILTON|BEST\s*WESTERN|NOVOTEL|RAMADA|"
    r"DAYS\s*INN|COMFORT\s*INN|\bINN\b|MOTEL|SERVICED\s*APART", re.I)
et_pat = re.compile(
    r"TEMPORARY\s*ACCOM|TEMP\.?\s*ACCOM|NIGHTLY|B\s*&\s*B|BED\s*(&|AND)\s*BREAKFAST|"
    r"HOMELESS|HOTEL|HOUSING\s*BENEFIT|ROUGH\s*SLEEP|ASYLUM|REFUGEE|RESETTLE|"
    r"\bTA\b|EMERGENCY\s*ACCOM|PRIVATE\s*SECTOR\s*LEAS", re.I)

with open("cand_suppliers.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["supplier_raw", "publisher", "n", "amount"])
    cur.execute("SELECT supplier_raw, publisher, n, amt FROM sup")
    kept = 0
    for name, pub, n, amt in cur.fetchall():
        if name and sup_pat.search(name):
            w.writerow([name, pub, n, amt]); kept += 1
print("supplier candidates:", kept)

with open("cand_expense_types.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["expense_type", "publisher", "n", "amount"])
    cur.execute("SELECT expense_type, publisher, n, amt FROM et")
    kept = 0
    for et_, pub, n, amt in cur.fetchall():
        if et_ and et_pat.search(et_):
            w.writerow([et_, pub, n, amt]); kept += 1
print("expense_type candidates:", kept)
