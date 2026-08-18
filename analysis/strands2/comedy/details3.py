import sqlite3

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')
db.row_factory = sqlite3.Row

def show(label, sql, args=()):
    print(f"\n=== {label} ===")
    for r in db.execute(sql, args):
        print(' | '.join(str(r[k]) for k in r.keys()))

Q = ("SELECT publisher, supplier_raw, amount, date, expense_type, expense_area, source_file "
     "FROM transactions WHERE {} ORDER BY date")

show("MoD Colchester Oyster Fishery", Q.format("supplier_raw LIKE '%COLCHESTER OYSTER%'"))
show("Darts World NYC", Q.format("supplier_raw='DARTS WORLD LTD'"))
show("McCallum Bagpipes", Q.format("supplier_raw='MCCALLUM BAGPIPES'"))
show("Superslam Wrestling", Q.format("supplier_raw='All Star Superslam Wrestling'"))
show("Hawes Quoits Club", Q.format("supplier_raw='HAWES QUOITS CLUB'"))
show("Free Ice Cream", Q.format("supplier_raw='Free Ice Cream Limited'"))
show("Silent Disco King", Q.format("supplier_raw LIKE '%Silent Disco King%'"))
show("Portsmouth Shantymen", Q.format("supplier_raw='THE PORTSMOUTH SHANTYMEN'"))
show("Cumberland wrestling", Q.format("supplier_raw LIKE '%WESTMORLAND WRESTLING%'"))
show("Dinosaur Adventure Live", Q.format("supplier_raw='Dinosaur Adventure Live Ltd'"))
show("Hungry Yeti", Q.format("supplier_raw='HUNGRY YETI'"))
show("Mistletoe", Q.format("supplier_raw='MISTLETOE MEADOWS TREE'"))
show("Curious Hedgehogs sample", Q.format("supplier_raw='Curious Hedgehogs'") + " LIMIT 4")
show("Grazing Goat DSIT", Q.format("supplier_raw LIKE '%Grazing Goat%'"))
show("Petting farm", Q.format("supplier_raw='2Nd Chance Petting Farm'"))

print("\n=== files table columns ===")
for r in db.execute("PRAGMA table_info(files)"):
    print(tuple(r))

print("\n=== file URLs for key source_files ===")
for sf in ['abc00b61a2602e414de0c461abca917ebab8ea45.bin',   # Salisbury pennies
           '9df95375c3f8a4af0fe99fbdc3df499456cd33b3.bin',   # Norfolk ICB pennies
           '88ed355940d09f528ccfef7da0a9ad5c6452aad2.bin',   # UKSBS Oracle 1p
           'b2126ddd08d0de64021c88744b68099a41e452a9.bin',   # Trump golf
           '4211de5b8ca50714e782c605a52b509b91653cf1.bin',   # MoD circus
           '5429e6df9de094f5be6611413134ef693c4a945c.bin',   # Flag flying
           'e5e140c591fd8c09c35f0b8232ff5890332735b3.bin',   # bell ringers
           ]:
    for r in db.execute("SELECT url FROM files WHERE url LIKE '%'||?||'%' OR rowid IN (SELECT rowid FROM files LIMIT 0)", (sf.split('.')[0],)):
        print(sf, '->', r['url'])

# try matching on any column containing the hash
import re
cols = [c[1] for c in db.execute("PRAGMA table_info(files)")]
print("cols:", cols)
