import sqlite3, csv, re

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')
db.row_factory = sqlite3.Row

def show(label, sql, args=()):
    print(f"\n=== {label} ===")
    for r in db.execute(sql, args):
        print(' | '.join(str(r[k]) for k in r.keys()))

Q = ("SELECT publisher, supplier_raw, amount, date, expense_type, expense_area, source_file "
     "FROM transactions WHERE {} ORDER BY date")

show("Fortune tellers MCC", Q.format("expense_type='AMUSEMENT PARKS,CARNIVALS,CIRCUS,FORTUNE TELLERS'"))
show("Aquariums MCC", Q.format("expense_type='AQUARIUMS, DOLPHINARIUMS, AND SEAQUARIUMS'"))
show("Pawn shops MCC", Q.format("expense_type='PAWN SHOPS'"))
show("Furriers MCC", Q.format("expense_type='FURRIERS AND FUR SHOPS'"))
show("Nightclub MCC top", "SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions WHERE expense_type='BAR,LOUNGE,DISCO,NIGHTCLUB,TAVERN-ALCOHOLIC DRINKS' ORDER BY amount DESC LIMIT 8")
show("Appleby horse ramp", Q.format("expense_type='APPLEBY HORSE RAMP'"))
show("Grotto expense", "SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions WHERE expense_type LIKE '%grotto%' OR supplier_raw LIKE '%grotto%' LIMIT 20")
show("Victoria Day donkeys context", "SELECT publisher, supplier_raw, amount, date, expense_type, source_file FROM transactions WHERE expense_type='Victoria Day' ORDER BY amount DESC LIMIT 15")

# second sweep over distinct suppliers
rows = []
with open(r'C:\Users\domin\Documents\Open Data\analysis\strands2\comedy\distinct_suppliers.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        rows.append(r)

PATTERNS = {
    'whippy': r'whippy', 'icecream': r'ice cream|icecream|gelato',
    'karaoke': r'karaoke', 'elvis': r'\belvis\b', 'majorettes': r'majorette|twirl',
    'cheer': r'cheerlead', 'grotto': r'grotto', 'mistletoe': r'mistletoe',
    'turkey_bird': r'\bturkeys\b', 'sprout': r'sprout', 'gravy': r'\bgravy\b',
    'pudding': r'pudding', 'custard': r'custard', 'trifle': r'trifle',
    'jelly': r'\bjelly\b', 'crumble': r'crumble', 'gnome': r'\bgnomes?\b',
    'fairy': r'\bfairy\b|\bfairies\b', 'pixie': r'\bpixies?\b', 'goblin': r'goblin',
    'troll': r'\btrolls?\b', 'yeti': r'\byeti\b', 'nessie': r'loch ness|nessie',
    'dodo': r'\bdodo\b', 'dinosaur': r'dinosaur|\bt-?rex\b', 'womble': r'womble',
    'muppet': r'muppet', 'walrus': r'walrus', 'penguin': r'penguin',
    'flamingo': r'flamingo', 'hedge': r'hedge fund circus',  # nonsense guard
    'punch': r'\bpunch\b', 'wrestl': r'wrestl', 'sumo': r'\bsumo\b',
    'disco': r'\bdisco\b', 'boogie': r'boogie', 'bingo': r'\bbingo\b',
    'whist': r'\bwhist\b', 'dominoes': r'domino', 'darts': r'\bdarts\b',
    'ferretlegging': r'ferret legg', 'gurning': r'gurn', 'shanty': r'shanty',
    'accordion': r'accordion', 'bagpipe': r'bagpipe', 'yodel': r'yodel',
    'stiltwalk': r'stilt', 'unicycle': r'unicycl', 'trampoline': r'trampolin',
    'soft play': r'soft play', 'petting': r'petting', 'zoolab': r'zoolab|animal encounter',
    'birdsofprey': r'birds? of prey', 'hawk': r'\bhawks?\b', 'kestrel': r'kestrel',
    'wormery': r'\bworms?\b|wormery', 'snail': r'\bsnails?\b', 'slug': r'\bslugs?\b',
    'crab': r'\bcrabs?\b', 'lobster': r'lobster', 'oyster': r'\boysters?\b',
    'whelk': r'whelk', 'eel': r'\beels\b', 'kipper': r'kipper', 'haggis': r'haggis',
    'toffee': r'toffee', 'fudge': r'\bfudge\b', 'humbug': r'humbug',
    'liquorice': r'liquorice|licorice', 'sherbet': r'sherbet', 'bonbon': r'bon ?bon',
    'wellies': r'welly|wellies|wellington boot', 'anorak': r'anorak',
    'cagoule': r'cagoule', 'flatcap': r'flat cap', 'whippet': r'whippet',
    'racingpigeon': r'racing pigeon', 'leek': r'\bleeks?\b', 'marrow': r'\bmarrows?\b',
    'giantveg': r'giant vegetable', 'conker': r'conker', 'tiddlywink': r'tiddlywink',
    'skittles': r'skittle', 'quoits': r'quoit', 'shovehapenny': r'shove',
    'cluedo': r'cluedo', 'scrabble': r'scrabble',
}
for name, pat in PATTERNS.items():
    rx = re.compile(pat, re.I)
    hits = [r for r in rows if rx.search(r['supplier_raw'])]
    if hits:
        hits.sort(key=lambda r: -int(r['n']))
        print(f"\n=== SUPP {name} ({len(hits)}) ===")
        for h in hits[:15]:
            print(f"  {h['supplier_raw']!r} | {h['publisher']} | n={h['n']} | sum={float(h['total']):.2f}")
        if len(hits) > 15:
            print(f"  ... {len(hits)-15} more")
