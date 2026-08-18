import sqlite3

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')
db.row_factory = sqlite3.Row

def show(label, sql, args=()):
    print(f"\n=== {label} ===")
    for r in db.execute(sql, args):
        print(' | '.join(str(r[k]) for k in r.keys()))

Q = ("SELECT publisher, supplier_raw, amount, date, expense_type, expense_area, source_file "
     "FROM transactions WHERE {} ORDER BY date")

show("Flag Flying detail", Q.format("expense_type='Flag Flying'"))
show("Bumble bees", Q.format("expense_type LIKE '%Bumble Bee%'"))
show("Dog doublet", Q.format("expense_type LIKE '%dog doublet%'"))
show("Exotic Pest exercise", Q.format("expense_type LIKE '%Exotic Pest%'"))
show("Alpacas Bristol sample", Q.format("supplier_raw LIKE 'Alpacas Peopleton%'") + " LIMIT 12")
show("Donkeys Rushmoor", Q.format("supplier_raw IN ('Kelly''S Donkeys','South East Donkeys')"))
show("Reindeer Greenwich", Q.format("supplier_raw LIKE '%REINDEER%'"))
show("Camels", Q.format("supplier_raw LIKE '%AMAZING CAMELS%'"))
show("Jester", Q.format("supplier_raw LIKE '%CONWY JESTER%'"))
show("Ukulele", Q.format("supplier_raw LIKE '%Ukulele Orchestra%'"))
show("Cosmic Sausages", Q.format("supplier_raw='THE COSMIC SAUSAGES'"))
show("Falconry Greenwich", Q.format("supplier_raw LIKE '%COUNTRYWIDE FALCONRY%'"))
show("Bell ringers", Q.format("supplier_raw LIKE '%BELL RINGERS%'"))
show("Trump golf", Q.format("supplier_raw LIKE '%TRUMP INTERNATIONAL%'"))
show("Wig and toupee", Q.format("expense_type LIKE '%TOUPEE%'"))
show("MoD circus", Q.format("expense_type='Amusement/Entertainment' AND publisher='Ministry of Defence'") + " LIMIT 5")
show("Amusement Parks/Circus supplier", Q.format("supplier_raw='Amusement Parks/Circus'"))
show("Marmalade On Toast", Q.format("supplier_raw='Marmalade On Toast'"))
show("Giant Cheese", Q.format("supplier_raw='Giant Cheese Ltd'"))
show("Weaseltron", Q.format("supplier_raw LIKE '%WEASELTRON%'"))
show("Teapottery", Q.format("supplier_raw LIKE '%TEAPOTTERY%'"))
show("Mr Squirrell MoJ", Q.format("supplier_raw LIKE '%SQUIRRELL#DX%'"))
show("HMS Dragon", Q.format("supplier_raw='HMS DRAGON'"))
show("Sodexo Motivation millions", Q.format("supplier_raw LIKE '%SODEXO MOTIVATION%' AND amount=1000000"))
show("Taxidermy NHM", Q.format("supplier_raw LIKE '%TAXIDERM%' OR supplier_raw LIKE '%Taxiderm%'"))
show("DCMS 1p to X", Q.format("supplier_raw='X' AND amount=0.01"))
show("Kirkbymoorside brass band", Q.format("supplier_raw LIKE '%KIRKBYMOORSIDE BRASS%'"))
show("Sheep Dip Lane sample", Q.format("supplier_raw LIKE 'Sheep Dip Lane%'") + " LIMIT 3")
show("Monster Gov Solutions sample", Q.format("supplier_raw='MONSTER GOVERNMENT SOLUTIONS'") + " LIMIT 3")
show("Ponies 4 Parties", Q.format("supplier_raw LIKE 'PONIES 4%'"))
show("Bouncy castles Blaby", Q.format("supplier_raw LIKE '%BOUNCY CASTLES%'"))
show("Civic Regalia rows", Q.format("expense_type='Civic Regalia'"))
show("Mayor-making sample", Q.format("expense_type LIKE 'Mayor%aking%'") + " LIMIT 25")
show("Kennel/Feed Stray Dogs sample", Q.format("expense_type LIKE 'Kennel%Stray Dogs'") + " LIMIT 5")

print("\n=== MCC-style oddities in expense_type ===")
import re
rows = db.execute("SELECT expense_type, count(*) c, sum(amount) s FROM transactions GROUP BY expense_type").fetchall()
MCC = re.compile(r'dating|escort|massage|billiard|bowling alle|casino|gambl|betting|night ?club|amusement park|aquarium|golf course|video game|arcade|pawn|fortune|astrolog|palm read|tattoo|piercing|snowmobile|motor home|swimming pool|freezer|fur shop|carnival|tuxedo|babysitting', re.I)
for r in rows:
    if r['expense_type'] and MCC.search(r['expense_type']):
        print(f"  {r['expense_type']!r} | n={r['c']} | sum={r['s'] if r['s'] is not None else 0:.2f}")
