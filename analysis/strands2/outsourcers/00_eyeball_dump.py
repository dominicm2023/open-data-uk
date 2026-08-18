# 00_eyeball_dump.py — THE OUTSOURCED STATE, step 0.
# Broad nets over distinct supplier_raw strings (agg.db from ../../supplier),
# dumped for manual eyeballing. Nothing here is a census yet.
import sqlite3, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
AGG = os.path.join(HERE, "..", "..", "supplier", "agg.db")
con = sqlite3.connect(AGG)

NETS = {
    "Capita":       r"\bCAPITA\b",
    "Serco":        r"SERCO",
    "G4S":          r"G4S|GROUP 4",
    "Mitie":        r"MITIE",
    "Sodexo":       r"SODEXH?O",
    "Amey":         r"AMEY",
    "Interserve":   r"INTERSERVE",
    "Kier":         r"\bKIER\b",
    "Sopra Steria": r"SOPRA|STERIA",
    "Liberata":     r"LIBERATA",
    "Veolia":       r"VEOLIA|\bONYX\b",
    "Biffa":        r"BIFFA",
    "Suez":         r"\bSUEZ\b|\bSITA\b",
    "Carillion":    r"CARILLION|\bEAGA\b|PLANNED MAINTENANCE ENGINEERING",
}

rows = con.execute("SELECT supplier_raw, publishers, txns, gbp FROM s").fetchall()
for company, net in NETS.items():
    pat = re.compile(net, re.I)
    matched = [r for r in rows if pat.search(r[0])]
    matched.sort(key=lambda x: -x[3])
    print(f"\n=== {company} ({net}) — {len(matched)} strings, GBP {sum(m[3] for m in matched):,.0f} ===")
    for m in matched:
        # per-string span and top payer for context
        span = con.execute("SELECT MIN(first_ym), MAX(last_ym) FROM sp WHERE supplier_raw=?", (m[0],)).fetchone()
        toppay = con.execute("SELECT publisher FROM sp WHERE supplier_raw=? ORDER BY gbp DESC LIMIT 1", (m[0],)).fetchone()[0]
        print(f"  {m[3]:>15,.0f}  {m[2]:>7,}tx {m[1]:>2}pub  {span[0]}..{span[1]}  [{toppay[:38]:38}] |{m[0]}|")
