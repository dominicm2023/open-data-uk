import sqlite3, sys

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')
db.row_factory = sqlite3.Row

TERMS = [
    'llama','alpaca','falcon','donkey','ferret','hedgehog','badger','beekeep',
    'pigeon','swan ','reindeer','goat','owl ','alpaca',
    'clairvoyant','psychic','magician','magic','puppet','circus','brass band',
    'morris danc','town crier','pantomime','juggl','ventriloquist','hypno',
    'santa','bouncy','fairground','punch and judy','jester','wizard',
    'taxiderm','embalm','coffin','funeral',
    'pest','mole catcher','rat catcher','vermin',
    'crumpet','marmalade','cricket club','allotment','bowls club',
    "women's institute",'bell ring','campanolog','maypole','morris',
    'fish and chip','tea room','tearoom','scarecrow','duck ',
    'cheese','pie ','pork pie','sausage','gin ','ale ','brewery','brewing',
    'unicorn','dragon','mermaid','pirate','knight',
    'clown','elvis','abba','beatles',
]

seen = set()
for t in TERMS:
    q = f"%{t}%"
    rows = db.execute(
        "SELECT supplier_raw, publisher, count(*) c, sum(amount) s, min(amount) mn, max(amount) mx "
        "FROM transactions WHERE supplier_raw LIKE ? GROUP BY supplier_raw, publisher "
        "ORDER BY c DESC LIMIT 40", (q,)).fetchall()
    if rows:
        print(f"\n=== TERM: {t!r} ({len(rows)} distinct shown) ===")
        for r in rows:
            key = (r['supplier_raw'], r['publisher'])
            flag = '' if key not in seen else ' [dup]'
            seen.add(key)
            print(f"  {r['supplier_raw']!r} | {r['publisher']} | n={r['c']} | sum={r['s']:.2f} | min={r['mn']} max={r['mx']}{flag}")
