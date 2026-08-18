import sqlite3
con = sqlite3.connect(r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db")
print("objects:")
for r in con.execute("select type, name from sqlite_master where type in ('table','index')"):
    print(" ", r)
print("transactions schema:")
for r in con.execute("pragma table_info(transactions)"):
    print(" ", r)
