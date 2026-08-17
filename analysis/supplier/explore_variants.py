# explore_variants.py — throwaway eyeballing tool for Q1.
# Casts DELIBERATELY BROAD nets per target company and prints every distinct
# supplier_raw caught, with publisher count / txns / gbp, so the false
# inclusions can be seen and excluded by hand in 01_variant_census.py.
import sqlite3, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, "agg.db"))
con.create_function("REGEXP", 2, lambda p, s: 1 if s and re.search(p, s, re.I) else 0)

NETS = {
    "BT": r"\bB\.?T\b|BRITISH TELECOM",
    "ROYAL MAIL": r"ROYAL\s*MAIL|ROYALMAIL",
    "EDF": r"\bEDF\b|EDF ENERGY",
    "BRITISH GAS / CENTRICA": r"BRITISH\s*GAS|CENTRICA|CORONA ENERGY",
    "CAPITA": r"CAPITA",
    "SERCO": r"SERCO",
    "G4S": r"G4S|GROUP 4",
    "VIRGIN": r"VIRGIN",
    "MICROSOFT": r"MICROSOFT|MICROSFT|MICOSOFT",
    "AMAZON": r"AMAZON|\bAWS\b",
    "HMRC": r"HMRC|HM REVENUE|H M REVENUE|INLAND REVENUE",
    "WATER-THAMES": r"THAMES WATER",
    "WATER-SEVERN": r"SEVERN TRENT",
    "WATER-ANGLIAN": r"ANGLIAN WATER",
    "WATER-SOUTHWEST": r"SOUTH WEST WATER|PENNON",
    "WATER-YORKSHIRE": r"YORKSHIRE WATER",
    "NHS-PROFESSIONALS": r"NHS PROFESSIONALS",
    "NHS-SUPPLYCHAIN": r"SUPPLY CHAIN",
}

targets = sys.argv[1:] or list(NETS)
for t in targets:
    pat = NETS[t]
    rows = con.execute(
        "SELECT supplier_raw, publishers, txns, gbp FROM s WHERE supplier_raw REGEXP ? ORDER BY gbp DESC", (pat,)
    ).fetchall()
    print(f"\n=== {t}  ({len(rows)} distinct strings) pattern: {pat}")
    for r in rows[:400]:
        print(f"  {r[1]:>2}pub {r[2]:>7}tx {r[3]:>18,.2f}  |{r[0]}|")
    if len(rows) > 400:
        print(f"  ... {len(rows)-400} more")
