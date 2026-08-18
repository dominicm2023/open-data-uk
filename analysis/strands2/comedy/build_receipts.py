import sqlite3, csv, json

db = sqlite3.connect(r'C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db')
db.row_factory = sqlite3.Row
manifest = json.load(open(r'C:\Users\domin\Documents\Open Data\analysis\spending\manifest.json', encoding='utf-8'))
f2meta = {}
for url, meta in manifest.items():
    if meta.get('file'):
        f2meta[meta['file']] = (meta.get('title', ''), url)

print("=== dedupe-safe aggregates (is_dup=0) ===")
CHECKS = [
    ("Panto Expenditure", "expense_type='Panto Expenditure'"),
    ("Flag Flying", "expense_type='Flag Flying'"),
    ("Alpacas", "supplier_raw LIKE 'Alpacas Peopleton%'"),
    ("Ukulele", "supplier_raw='The Ukulele Orchestra Of Great Britain'"),
    ("Oyster fishery", "supplier_raw LIKE '%COLCHESTER OYSTER%'"),
    ("Superslam", "supplier_raw='All Star Superslam Wrestling'"),
    ("Sodexo 1M", "supplier_raw LIKE '%SODEXO MOTIVATION%' AND amount=1000000"),
    ("Mayoral Dinner Dance", "expense_type='Mayoral Charity Dinner Dance'"),
    ("Trump", "supplier_raw LIKE 'TRUMP INTERNATIONAL%'"),
]
for label, w in CHECKS:
    r = db.execute(f"SELECT count(*) c, sum(amount) s, min(date) a, max(date) b FROM transactions WHERE {w} AND is_dup=0").fetchone()
    r2 = db.execute(f"SELECT count(*) c, sum(amount) s FROM transactions WHERE {w}").fetchone()
    print(f"  {label}: dedup n={r['c']} sum={r['s']:.2f} ({r['a']}..{r['b']}) | raw n={r2['c']} sum={r2['s']:.2f}")

FINDINGS = [
    # (finding_id, where clause, optional limit)
    ("panto_expenditure",      "expense_type='Panto Expenditure' AND is_dup=0 ORDER BY amount DESC LIMIT 3", None),
    ("flag_flying",            "expense_type='Flag Flying' AND is_dup=0", None),
    ("trump_golf_card",        "supplier_raw LIKE 'TRUMP INTERNATIONAL%' AND is_dup=0", None),
    ("wig_and_toupee",         "expense_type='WIG AND TOUPEE SHOPS' AND is_dup=0", None),
    ("fortune_tellers_tivoli", "expense_type='AMUSEMENT PARKS,CARNIVALS,CIRCUS,FORTUNE TELLERS' AND is_dup=0", None),
    ("pawn_shop",              "expense_type='PAWN SHOPS' AND is_dup=0", None),
    ("ikea_furrier",           "expense_type='FURRIERS AND FUR SHOPS' AND is_dup=0", None),
    ("mod_circus_card",        "publisher='Ministry of Defence' AND supplier_raw IN ('Amusement Parks/Circus','Health & Beauty Spas') AND is_dup=0", None),
    ("dog_in_a_doublet",       "expense_type='Lifting arm for dog doublet'", None),
    ("bumble_bee_colonies",    "expense_type LIKE 'Bumble Bee Colonies%'", None),
    ("exercise_exotic_pest",   "expense_type LIKE '%Exercise Incursion of Exotic Pest%'", None),
    ("real_reindeer",          "supplier_raw LIKE '%REINDEER%' AND publisher='Royal Borough of Greenwich' AND is_dup=0", None),
    ("josephs_amazing_camels", "supplier_raw LIKE '%AMAZING CAMELS%' AND is_dup=0", None),
    ("conwy_jester",           "supplier_raw LIKE '%CONWY JESTER%' AND is_dup=0", None),
    ("portsmouth_shantymen",   "supplier_raw='THE PORTSMOUTH SHANTYMEN' AND is_dup=0", None),
    ("ukulele_orchestra",      "supplier_raw='The Ukulele Orchestra Of Great Britain' AND is_dup=0", None),
    ("superslam_wrestling",    "supplier_raw='All Star Superslam Wrestling' AND is_dup=0 ORDER BY amount DESC LIMIT 3", None),
    ("dinosaur_adventure",     "supplier_raw='Dinosaur Adventure Live Ltd' AND is_dup=0", None),
    ("rival_donkeys",          "supplier_raw IN ('Kelly''S Donkeys','South East Donkeys') AND is_dup=0", None),
    ("giant_cheese_climate",   "supplier_raw='Giant Cheese Ltd' AND is_dup=0", None),
    ("petting_farm",           "supplier_raw='2Nd Chance Petting Farm' AND is_dup=0", None),
    ("cosmic_sausages",        "supplier_raw='THE COSMIC SAUSAGES' AND is_dup=0", None),
    ("falconry_pest_control",  "supplier_raw LIKE '%COUNTRYWIDE FALCONRY%' AND is_dup=0", None),
    ("bellringers_public_health", "supplier_raw LIKE '%BELL RINGERS%' AND is_dup=0", None),
    ("hawes_quoits",           "supplier_raw='HAWES QUOITS CLUB' AND is_dup=0", None),
    ("darts_performing_arts",  "supplier_raw='DARTS WORLD LTD' AND is_dup=0", None),
    ("brass_bands",            "supplier_raw IN ('KIRKBYMOORSIDE BRASS BAND','HUNMNABY BRASS BAND') AND is_dup=0", None),
    ("mod_oyster_rent",        "supplier_raw LIKE '%COLCHESTER OYSTER%' AND is_dup=0", None),
    ("fcdo_bagpipes",          "supplier_raw='MCCALLUM BAGPIPES' AND is_dup=0", None),
    ("stallion_and_unicorn",   "supplier_raw='STALLION AND UNICORN LIMITED' AND is_dup=0", None),
    ("text_santa",             "supplier_raw='ITV TEXT SANTA LTD' AND is_dup=0", None),
    ("sodexo_round_millions",  "supplier_raw LIKE '%SODEXO MOTIVATION%' AND amount=1000000 AND is_dup=0", None),
    ("penny_over25k_salisbury","publisher='Salisbury NHS Foundation Trust' AND amount=0.01 AND is_dup=0 LIMIT 3", None),
    ("penny_over25k_norfolk",  "publisher LIKE 'NHS Norfolk%' AND amount=0.01 AND is_dup=0 LIMIT 3", None),
    ("oracle_penny_licence",   "supplier_raw='Oracle Corporation UK Ltd' AND amount<=0.02 AND amount>0 AND is_dup=0", None),
    ("supplier_named_X",       "supplier_raw='X' AND amount=0.01 AND is_dup=0", None),
    ("civic_regalia",          "expense_type='Civic Regalia' AND is_dup=0", None),
    ("mayor_making_binlorry",  "expense_type='Mayor-making' AND supplier_raw='Veolia Environmental Services' AND is_dup=0", None),
    ("alpaca_professional_fees","supplier_raw LIKE 'Alpacas Peopleton%' AND is_dup=0 ORDER BY amount DESC LIMIT 3", None),
    ("curious_hedgehogs",      "supplier_raw='Curious Hedgehogs' AND is_dup=0 ORDER BY amount DESC LIMIT 2", None),
    ("hms_dragon_catering",    "supplier_raw='HMS DRAGON' AND is_dup=0", None),
    ("free_ice_cream",         "supplier_raw='Free Ice Cream Limited' AND is_dup=0", None),
    ("silent_disco_king",      "supplier_raw LIKE '%Silent Disco King%' AND is_dup=0", None),
    ("hungry_yeti",            "supplier_raw='HUNGRY YETI' AND is_dup=0", None),
    ("weaseltron",             "supplier_raw='WEASELTRON ENTERTAINMENT LIMITED' AND is_dup=0", None),
    ("teapottery",             "supplier_raw='THE TEAPOTTERY LTD' AND is_dup=0", None),
    ("marmalade_on_toast",     "supplier_raw='Marmalade On Toast' AND is_dup=0 LIMIT 2", None),
    ("appleby_horse_ramp",     "expense_type='APPLEBY HORSE RAMP' AND is_dup=0", None),
    ("victoria_day_fools_paradise", "expense_type='Victoria Day' AND supplier_raw='Fools Paradise Limited' AND is_dup=0", None),
    ("grazing_goat_dsit",      "supplier_raw LIKE '%Grazing Goat%' AND is_dup=0", None),
    ("wombleton_parish",       "supplier_raw='WOMBLETON PARISH COUNCIL' AND is_dup=0", None),
    ("kennel_feed_stray_dogs", "expense_type='Kennel Feed Stray Dogs' AND is_dup=0 LIMIT 2", None),
]

outpath = r'C:\Users\domin\Documents\Open Data\analysis\strands2\comedy\receipts.csv'
n = 0
with open(outpath, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['finding', 'publisher', 'supplier_raw', 'amount', 'date', 'expense_type',
                'expense_area', 'source_file', 'dataset_title', 'source_url'])
    for fid, where, _ in FINDINGS:
        rows = db.execute(
            "SELECT publisher, supplier_raw, amount, date, expense_type, expense_area, source_file "
            f"FROM transactions WHERE {where}").fetchall()
        for r in rows:
            title, url = f2meta.get(r['source_file'], ('', ''))
            w.writerow([fid, r['publisher'], r['supplier_raw'], r['amount'], r['date'],
                        r['expense_type'], r['expense_area'], r['source_file'], title, url])
            n += 1
    # RO finding appended by hand
    w.writerow(['city_of_london_culture', 'City of London (RO 2024-25)', 'n/a (RO return, gross cultural spend)',
                92046200, '2024-25', 'cultural & related services (gross)', 'RO/RS 2024-25',
                'analysis/ro/ro_per_head.csv', 'Revenue Outturn per-head dataset',
                'gbp_per_head=5939.6 vs London-borough positive median 58.3; population 15497'])
    n += 1
print(f"wrote {n} rows to receipts.csv")
