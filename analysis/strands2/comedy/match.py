import csv, re, sys

rows = []
with open(r'C:\Users\domin\Documents\Open Data\analysis\strands2\comedy\distinct_suppliers.csv',encoding='utf-8') as f:
    for r in csv.DictReader(f):
        rows.append(r)

PATTERNS = {
    # animals & rural
    'llama': r'\bllamas?\b', 'alpaca': r'\balpacas?\b', 'falconry': r'falconry|\bfalconer',
    'donkey': r'\bdonkeys?\b', 'ferret': r'\bferrets?\b', 'hedgehog': r'hedgehog',
    'badger': r'\bbadgers?\b', 'bees': r'\bbee\b|beekeep|apiar', 'pigeon': r'pigeon',
    'swan': r'\bswans?\b', 'reindeer': r'reindeer', 'goat': r'\bgoats?\b',
    'owl': r'\bowls?\b', 'sheep': r'\bsheep\b', 'alpaca2': r'llama|alpaca',
    'duck': r'\bducks?\b', 'pony': r'\bpony\b|\bponies\b', 'camel': r'\bcamels?\b',
    # entertainment / occult
    'clairvoyant': r'clairvoyan|psychic', 'magician': r'magician|\bmagic\b|illusionist',
    'puppet': r'puppet', 'circus': r'\bcircus\b', 'brassband': r'brass band|silver band|colliery band',
    'morris': r'morris danc|morris men|morris side', 'towncrier': r'town crier',
    'panto': r'pantomime|\bpanto\b', 'juggle': r'juggl', 'ventriloquist': r'ventriloqu',
    'hypnotist': r'hypno', 'santa': r'\bsanta\b|father christmas', 'bouncy': r'bouncy',
    'punchjudy': r'punch (and|&) judy', 'jester': r'\bjesters?\b', 'wizard': r'\bwizards?\b',
    'clown': r'\bclowns?\b', 'stilt': r'\bstilts?\b', 'fire eater': r'fire.?eat',
    'balloon model': r'balloon',
    # trades
    'taxidermy': r'taxiderm', 'coffin': r'\bcoffins?\b', 'funeral': r'funeral',
    'pest': r'pest control|pest force|pestforce|molecatch|mole catch|rat catch|vermin|\bwasps?\b',
    'chimney': r'chimney sweep',
    # peak British
    'crumpet': r'crumpet', 'marmalade': r'marmalade', 'cricket': r'cricket club',
    'allotment': r'allotment', 'bowls': r'bowls club|bowling club',
    'wi': r"women'?s institute", 'bells': r'bell ring|campanolog|bellfound|bell found',
    'maypole': r'maypole', 'fishchip': r'fish (and|&|n) chip', 'tearoom': r'tea room|tearoom',
    'scarecrow': r'scarecrow', 'cheese': r'\bcheese\b', 'pie': r'\bpies?\b',
    'sausage': r'sausage', 'brewery': r'brewer|\bales?\b', 'gin': r'\bgin\b',
    'scone': r'\bscones?\b', 'teapot': r'teapot', 'bunting': r'bunting',
    'village hall': r'village hall', 'steam': r'steam rally|traction engine',
    'brass': r'\bbrass\b', 'oompah': r'oompah', 'ukulele': r'ukulele',
    'knit': r'\bknit', 'crochet': r'crochet',
    # whimsical names
    'unicorn': r'unicorn', 'dragon': r'\bdragons?\b', 'mermaid': r'mermaid',
    'pirate': r'\bpirates?\b', 'knight?': r'\bknights\b', 'ghost': r'\bghosts?\b',
    'witch': r'\bwitch(es)?\b', 'monster': r'monster', 'ninja': r'\bninjas?\b',
    'zombie': r'zombie', 'banana': r'banana', 'sparkle': r'sparkle', 'wonky': r'wonky',
    'grumpy': r'grumpy', 'soggy': r'soggy', 'muddy': r'muddy', 'naughty': r'naughty',
    'cheeky': r'cheeky', 'wig': r'\bwigs?\b', 'corgi': r'\bcorgi\b',
    'trump': r'\btrumps?\b', 'boring': r'\bboring\b', 'bogg': r'\bbog\b',
    'squirrel': r'squirrel', 'weasel': r'weasel', 'stoat': r'\bstoats?\b',
    'toad': r'\btoads?\b', 'newt': r'\bnewts?\b', 'frog': r'\bfrogs?\b',
    'mole': r'\bmoles?\b', 'otter': r'\botters?\b', 'beaver': r'\bbeavers?\b',
}

for name, pat in PATTERNS.items():
    rx = re.compile(pat, re.I)
    hits = [r for r in rows if rx.search(r['supplier_raw'])]
    if hits:
        hits.sort(key=lambda r: -int(r['n']))
        print(f"\n=== {name} ({len(hits)}) ===")
        for h in hits[:25]:
            print(f"  {h['supplier_raw']!r} | {h['publisher']} | n={h['n']} | sum={float(h['total']):.2f}")
        if len(hits) > 25:
            print(f"  ... {len(hits)-25} more")
