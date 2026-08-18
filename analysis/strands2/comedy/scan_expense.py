import sqlite3

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')

print("=== distinct expense_type count ===")
print(db.execute("SELECT count(DISTINCT expense_type) FROM transactions").fetchone())

import re
rows = db.execute("SELECT expense_type, count(*) c, sum(amount) s FROM transactions GROUP BY expense_type").fetchall()
rows2 = db.execute("SELECT expense_area, count(*) c, sum(amount) s FROM transactions GROUP BY expense_area").fetchall()
print(len(rows), len(rows2))

PATS = {
    'regalia': r'regalia', 'mayor': r'mayor', 'towncrier': r'town crier|crier',
    'civic': r'civic', 'allotment': r'allotment', 'pest': r'pest',
    'bandstand': r'bandstand', 'christmas': r'christmas|xmas', 'santa': r'santa',
    'flag': r'\bflags?\b', 'clock': r'clock', 'pigeon': r'pigeon',
    'dog': r'\bdog\b|\bdogs\b', 'horse': r'horse', 'donkey': r'donkey',
    'wig': r'\bwigs?\b', 'gown': r'gown', 'robes': r'\brobes?\b',
    'medal': r'medal', 'trophy': r'troph', 'tea': r'\btea\b',
    'biscuit': r'biscuit', 'cake': r'\bcakes?\b', 'sandwich': r'sandwich',
    'entertain': r'entertain', 'hospitality': r'hospitality',
    'panto': r'panto', 'fireworks': r'firework', 'bunting': r'bunting',
    'queen': r'queen|jubilee|coronation', 'royal': r'royal visit',
    'toilets': r'toilet|public convenience', 'cemetery': r'cemeter|burial|exhum',
    'witchcraft': r'witch', 'ghost': r'ghost', 'lost': r'\blost\b',
    'miscellaneous': r'^misc', 'sundry': r'sundr', 'other': r'^other$',
    'bees': r'\bbees?\b', 'swan': r'swan', 'falcon': r'falcon',
    'taxidermy': r'taxiderm', 'stuffed': r'stuffed',
}

for label, dataset in [('EXPENSE_TYPE', rows), ('EXPENSE_AREA', rows2)]:
    print(f"\n########## {label} ##########")
    for name, pat in PATS.items():
        rx = re.compile(pat, re.I)
        hits = [(t, c, s) for (t, c, s) in dataset if t and rx.search(t)]
        if hits:
            hits.sort(key=lambda x: -x[1])
            print(f"\n=== {name} ({len(hits)}) ===")
            for t, c, s in hits[:20]:
                print(f"  {t!r} | n={c} | sum={s if s is not None else 0:.2f}")
            if len(hits) > 20:
                print(f"  ... {len(hits)-20} more")
