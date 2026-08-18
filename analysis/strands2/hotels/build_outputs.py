import sqlite3, csv, os
from collections import defaultdict
ROOT = r"C:\Users\domin\Documents\Open Data"
OUT = os.path.join(ROOT, r"analysis\strands2\hotels")
w = sqlite3.connect(os.path.join(OUT, "work.sqlite"))
cur = w.cursor()

def fy_of(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    f = y if m >= 4 else y - 1
    return "%d-%02d" % (f, (f + 1) % 100)

def wcsv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        cw = csv.writer(f); cw.writerow(header); cw.writerows(rows)
    print(name, len(rows), "rows")

# ---------- 1. hotel chain census (eyeballed) ----------
EXCL_SUBSTR = ['IBISWORLD','IBIS WORLD','IBIS TRADING','DANIDA','IBIS DAKAR',
 'ACCORD','ACCORA','ACCOR SERVICES','EDENRED','SPORTACCORD','MACCORMACK','ACCORIE','HIBISCUS',
 'IN ACCORD','TO UNDERTAKE','SAMUEL WHITBREAD']
def chain_of(s):
    if any(e in s for e in EXCL_SUBSTR): return None
    if 'TRAVELODGE' in s: return 'Travelodge'
    if s.startswith('PREMIER INN') or s == 'WHITBREAD PLC': return 'Premier Inn / Whitbread'
    if s in ('BRITANNIA HOTELS LIMITED','BRITANNIA HOTELS LTD T/A DARESBURY PARK HOTEL'): return 'Britannia Hotels'
    if 'BRITANNIA' in s: return None
    if 'HOLIDAY INN' in s or 'INTERCONTINENTAL HOTEL' in s or s == 'IHG RUIJIN': return 'Holiday Inn / IHG'
    if 'IBIS' in s or 'NOVOTEL' in s or 'MERCURE' in s or s.startswith('ACCOR.COM'): return 'Ibis / Novotel / Mercure (Accor)'
    return None
census = defaultdict(lambda: [0, 0.0])
matched_strings = defaultdict(lambda: [0,0.0])
excluded = defaultdict(lambda: [0,0.0])
PATS = ('%TRAVELODGE%','%PREMIER INN%','%WHITBREAD%','%BRITANNIA%','%HOLIDAY INN%','%IHG%',
        '%INTERCONTINENTAL HOTEL%','%IBIS%','%ACCOR%','%NOVOTEL%','%MERCURE%')
q = " OR ".join("s LIKE ?" for _ in PATS)
for s, pub, yr, n, g in cur.execute("SELECT s, publisher, yr, n, gbp FROM sup_year WHERE " + q, PATS):
    c = chain_of(s)
    if c:
        census[(c, pub, yr)][0] += n; census[(c, pub, yr)][1] += g
        matched_strings[(c, s)][0] += n; matched_strings[(c, s)][1] += g
    else:
        excluded[s][0] += n; excluded[s][1] += g
wcsv("hotel_chain_census.csv", ["chain","publisher","year","txns","gbp"],
     [(c,p,y,n,round(g,2)) for (c,p,y),(n,g) in sorted(census.items(), key=lambda x:(x[0][0],x[0][1],x[0][2] or ''))])
wcsv("hotel_census_included_strings.csv", ["chain","supplier_string","txns","gbp"],
     [(c,s,n,round(g,2)) for (c,s),(n,g) in sorted(matched_strings.items(), key=lambda x:(-x[1][1]))])
wcsv("hotel_census_excluded_strings.csv", ["supplier_string","txns","gbp"],
     [(s,n,round(g,2)) for s,(n,g) in sorted(excluded.items(), key=lambda x:-x[1][1])])
tot = defaultdict(lambda: [0,0.0])
for (c,p,y),(n,g) in census.items(): tot[c][0]+=n; tot[c][1]+=g
for c,(n,g) in sorted(tot.items(), key=lambda x:-x[1][1]): print("   %-35s n=%5d %14s" % (c, n, format(g, ",.2f")))

# ---------- 2. Bristol ----------
wcsv("bristol_holiday_inn_monthly.csv", ["year_month","txns","gbp","expense_types"],
 cur.execute("""SELECT year_month, COUNT(*), ROUND(SUM(amount),2), GROUP_CONCAT(DISTINCT expense_type)
    FROM council WHERE publisher='Bristol City Council' AND UPPER(supplier_raw) LIKE '%HOLIDAY INN%'
    GROUP BY 1 ORDER BY 1""").fetchall())
fyb = defaultdict(lambda: [set(),0,0.0])
for ym,n,g in cur.execute("""SELECT year_month, COUNT(*), SUM(amount) FROM council
    WHERE publisher='Bristol City Council' AND UPPER(expense_type)='TPP - B&B PAYMENTS TO LANDLORDS' GROUP BY 1"""):
    k = fy_of(ym); fyb[k][0].add(ym); fyb[k][1]+=n; fyb[k][2]+=g
wcsv("bristol_tpp_bb_fy.csv", ["fy","months_in_ledger","txns","gbp"],
     [(k,len(v[0]),v[1],round(v[2],2)) for k,v in sorted(fyb.items())])
wcsv("bristol_ta_suppliers.csv", ["supplier","txns","gbp","first_month","last_month"],
 cur.execute("""SELECT UPPER(TRIM(supplier_raw)), COUNT(*), ROUND(SUM(amount),2), MIN(year_month), MAX(year_month)
    FROM council WHERE publisher='Bristol City Council' AND UPPER(expense_type)='TPP - B&B PAYMENTS TO LANDLORDS'
    GROUP BY 1 HAVING SUM(amount)>20000 ORDER BY SUM(amount) DESC""").fetchall())

# ---------- 3. Uttlesford ----------
TA_UTT = "('HOMELESSNESS - ACCOMMODATION','TEMPORARY ACCOMMODATION - THIRD PARTY','BED & BREAKFAST THIRD PARTY - TEMP ACCOMM')"
fyu = defaultdict(lambda: [0,0.0])
for ym,n,g in cur.execute("""SELECT year_month, COUNT(*), SUM(amount) FROM council
    WHERE publisher='Uttlesford District Council' AND UPPER(expense_type) IN """ + TA_UTT + " GROUP BY 1"):
    k=fy_of(ym); fyu[k][0]+=n; fyu[k][1]+=g
wcsv("uttlesford_ta_fy.csv", ["fy","txns","gbp"], [(k,v[0],round(v[1],2)) for k,v in sorted(fyu.items())])
wcsv("uttlesford_ta_suppliers.csv", ["supplier","txns","gbp","first_month","last_month"],
 cur.execute("""SELECT UPPER(TRIM(supplier_raw)), COUNT(*), ROUND(SUM(amount),2), MIN(year_month), MAX(year_month)
    FROM council WHERE publisher='Uttlesford District Council' AND UPPER(expense_type) IN """ + TA_UTT + """
    GROUP BY 1 ORDER BY SUM(amount) DESC""").fetchall())

# ---------- 4. Rushmoor ----------
fyr = defaultdict(lambda: [0,0.0])
for ym,n,g in cur.execute("""SELECT year_month, COUNT(*), SUM(amount) FROM council
    WHERE publisher='Rushmoor Borough Council' AND UPPER(expense_type) IN ('BED AND BREAKFAST','HOSTEL ACCOMMODATION') GROUP BY 1"""):
    k=fy_of(ym); fyr[k][0]+=n; fyr[k][1]+=g
wcsv("rushmoor_bb_fy.csv", ["fy","txns","gbp"], [(k,v[0],round(v[1],2)) for k,v in sorted(fyr.items())])
wcsv("rushmoor_bb_suppliers.csv", ["supplier","txns","gbp","first_month","last_month"],
 cur.execute("""SELECT UPPER(TRIM(supplier_raw)), COUNT(*), ROUND(SUM(amount),2), MIN(year_month), MAX(year_month)
    FROM council WHERE publisher='Rushmoor Borough Council'
      AND UPPER(expense_type) IN ('BED AND BREAKFAST','HOSTEL ACCOMMODATION')
    GROUP BY 1 HAVING SUM(amount)>3000 ORDER BY SUM(amount) DESC""").fetchall())

# ---------- 5. council TA lines ----------
LINES = [
 ('Bristol City Council', "UPPER(expense_type)='TPP - B&B PAYMENTS TO LANDLORDS'", "nightly-paid/B&B TA to private landlords"),
 ('Uttlesford District Council', "UPPER(expense_type) IN " + TA_UTT, "homelessness TA incl hotels"),
 ('Rushmoor Borough Council', "UPPER(expense_type) IN ('BED AND BREAKFAST','HOSTEL ACCOMMODATION')", "B&B and hostel placements"),
 ('South Gloucestershire Council', "UPPER(expense_type)='BED & BREAKFAST'", "B&B placements 2010-11 window only"),
 ('Plymouth City Council', "UPPER(expense_type)='B&B COSTS  CLIENT'", "client B&B costs 2015 window only"),
 ('Eden District Council', "UPPER(expense_type) LIKE 'HOMELESS%'", "homelessness incl grants to Eden HA"),
 ('North Yorkshire Council', "expense_type LIKE '321021%' OR expense_type LIKE '321060%'", "homeless support + unsupported TA"),
 ('Former council of North Yorkshire', "expense_type LIKE '321021%' OR expense_type LIKE '321060%'", "homeless support + unsupported TA"),
 ('London Borough of Richmond Upon Thames', "UPPER(expense_type)='RENT REBATES FOR B&B'", "rent rebates for B&B"),
 ('Royal Borough of Greenwich', "UPPER(expense_type)='TEMPORARY ACCOMMODATION'", "only 2 rows labelled TA - coding hides TA"),
]
rows5 = []
for pub, cond, note in LINES:
    r = cur.execute("SELECT COUNT(*), ROUND(SUM(amount),2), MIN(year_month), MAX(year_month) FROM council WHERE publisher=? AND (" + cond + ")", (pub,)).fetchone()
    rows5.append((pub, note, r[2], r[3], r[0], r[1]))
wcsv("council_ta_lines.csv", ["publisher","line","first_month","last_month","txns","gbp"], rows5)

# ---------- 6. Greenwich probe ----------
wcsv("greenwich_lettings_probe.csv", ["supplier","expense_type","expense_area","txns","gbp","first_month","last_month"],
 cur.execute("""SELECT UPPER(TRIM(supplier_raw)), COALESCE(expense_type,''), COALESCE(expense_area,''),
        COUNT(*), ROUND(SUM(amount),2), MIN(year_month), MAX(year_month)
    FROM council WHERE publisher='Royal Borough of Greenwich'
      AND UPPER(TRIM(supplier_raw)) IN ('HOUSE TO HOME LETTINGS LTD','ASSETGROVE LETTINGS LTD',
          'MELBA LODGE','MEADOW CROFT LODGE','MEADOWCROFT LODGE LTD','BETTERCARE KEYS LTD (TUDOR LODGE)',
          'LEIGHAM LODGE LTD','CORNER LODGE LTD','GROVE HOTEL','TRAVELODGE HOTELS LTD')
    GROUP BY 1,2,3 ORDER BY 1, SUM(amount) DESC""").fetchall())

# ---------- 7. Home Office asylum receipt ----------
rows7 = []
GROUPS = [
 ("Clearsprings (asylum accommodation)", "s LIKE '%CLEARSPRING%'"),
 ("Serco (all Home Office work)", "(s='SERCO LTD' OR s='SERCO  LTD' OR s='SERCO' OR s='SERCO JUSTICE')"),
 ("G4S (all Home Office work)", "s LIKE 'G4S%'"),
 ("Direct hotel payments", "(s LIKE '%HOTEL%' OR s LIKE '%HOLIDAY INN%' OR s LIKE '%RADISSON%') AND s NOT LIKE '%CLEARSPRING%'"),
]
for label, cond in GROUPS:
    for yr, n, g in cur.execute("SELECT yr, SUM(n), ROUND(SUM(gbp),2) FROM sup_year WHERE publisher='Home Office' AND (" + cond + ") GROUP BY yr ORDER BY yr"):
        rows7.append((label, yr, n, g))
wcsv("home_office_asylum_receipt.csv", ["supplier_group","year","txns","gbp"], rows7)
w.close()

# ---------- 8. RO housing_gfra ----------
rows = []
with open(os.path.join(ROOT, r"analysis\ro\ro_per_head.csv"), newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f): rows.append(r)
DEF = {'2013-14':70.5952,'2018-19':76.1639,'2024-25':96.6694}
BASE = 96.6694
BILL = {'SD','LB','MD','UA'}
eng_money = defaultdict(float); eng_pop = defaultdict(float)
svc_money = defaultdict(float)
for r in rows:
    y, m, s = r['year'], r['measure'], r['service']
    g = float(r['gbp_thousand'] or 0)
    if s == 'housing_gfra': eng_money[(y,m)] += g
    if m == 'nce': svc_money[(s,y)] += g
    if m=='nce' and s=='total_service_expenditure' and r['cls'] in BILL:
        eng_pop[y] += float(r['population'] or 0)
out7 = []
for (y,m),g in sorted(eng_money.items()):
    nom_ph = g*1000/eng_pop[y]
    out7.append((y, m, round(g/1000,1), round(nom_ph,2), round(nom_ph*BASE/DEF[y],2)))
wcsv("england_housing_gfra.csv", ["year","measure","gbp_million_nominal","gbp_per_head_nominal","real_gbp_per_head_2425"], out7)

NAMES = ['Bristol UA','Uttlesford','Rushmoor','South Gloucestershire UA','Plymouth UA','Eden',
 'Greenwich','Richmond upon Thames','Blaby','Cheltenham','North Yorkshire','North Yorkshire CC','Harrogate']
out8 = [(r['name'], r['year'], r['measure'], r['gbp_thousand'], r['gbp_per_head'], r['real_gbp_per_head'])
        for r in rows if r['service']=='housing_gfra' and r['name'] in NAMES]
wcsv("payers_housing_gfra.csv", ["name","year","measure","gbp_thousand","gbp_per_head_nominal","real_gbp_per_head_2425"],
     sorted(out8))

out9 = []
for s in sorted(set(k[0] for k in svc_money)):
    v = {}
    for y in DEF:
        nom_ph = svc_money[(s,y)]*1000/eng_pop[y]
        v[y] = nom_ph*BASE/DEF[y]
    ch = (v['2024-25']/v['2013-14']-1)*100 if v['2013-14'] else None
    out9.append((s, round(v['2013-14'],2), round(v['2018-19'],2), round(v['2024-25'],2),
                 round(ch,1) if ch is not None else ''))
out9.sort(key=lambda x: -(x[4] if x[4]!='' else -999))
wcsv("england_service_real_growth.csv",
     ["service","real_gbp_per_head_2013_14","real_gbp_per_head_2018_19","real_gbp_per_head_2024_25","real_pct_change_13_to_24"], out9)
print("England billing pop:", dict((k, round(v/1e6,2)) for k,v in eng_pop.items()))
