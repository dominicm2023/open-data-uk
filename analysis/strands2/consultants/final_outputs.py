"""Assemble final chart-ready CSVs."""
import sqlite3, csv
from collections import defaultdict

OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\consultants"
DB  = r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db"

# 1. category x sector x fy rollup
rows = list(csv.DictReader(open(f"{OUT}\\yearly_firm_sector.csv", encoding="utf-8")))
cat = defaultdict(float)
for r in rows:
    cat[(r["fy"], r["category"], r["sector"])] += float(r["gbp"])
with open(f"{OUT}\\yearly_category_sector.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["fy", "category", "sector", "gbp"])
    for k in sorted(cat): w.writerow([k[0], k[1], k[2], round(cat[k], 2)])

# 2. DHSC same-ledger consulting arc (from classified data: consulting category, DHSC only)
con = sqlite3.connect(DB); cur = con.cursor()
inc = [r["supplier_raw"] for r in csv.DictReader(open(f"{OUT}\\firm_variants_included.csv", encoding="utf-8"))
       if r["category"] == "consulting"]
dhsc = defaultdict(float)
CH = 400
for i in range(0, len(inc), CH):
    chunk = inc[i:i+CH]
    q = f"""select year_month, sum(amount) from transactions
            where is_dup=0 and publisher='Department of Health and Social Care'
            and year_month is not null and supplier_raw in ({','.join('?'*len(chunk))})
            group by year_month"""
    for ym, g in cur.execute(q, chunk):
        y, m = int(ym[:4]), int(ym[5:7]); s = y if m >= 4 else y-1
        dhsc[f"{s}-{str(s+1)[2:]}"] += g or 0
with open(f"{OUT}\\dhsc_consulting_fy.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["fy", "consulting_gbp", "note"])
    for k in sorted(dhsc):
        note = "ledger runs 2010-06 to 2022-11; 2022-23 is a part year" if k == "2022-23" else ""
        w.writerow([k, round(dhsc[k], 2), note])

# 3. Greenwich Manpower by FY (master-vendor agency deal)
gw = defaultdict(float)
for ym, g in cur.execute("""select year_month, sum(amount) from transactions
    where is_dup=0 and publisher='Royal Borough of Greenwich'
    and supplier_raw in ('MANPOWER UK LTD','MANPOWER UK LIMITED') and year_month is not null
    group by year_month"""):
    y, m = int(ym[:4]), int(ym[5:7]); s = y if m >= 4 else y-1
    gw[f"{s}-{str(s+1)[2:]}"] += g or 0
with open(f"{OUT}\\greenwich_manpower_fy.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["fy", "manpower_gbp"])
    for k in sorted(gw): w.writerow([k, round(gw[k], 2)])

# 4. juxtaposition: RO years x (corpus consulting central gov, corpus council agency) + RO real per-head
cons = {k[0]: 0.0 for k in cat}
agc = defaultdict(float); agco = defaultdict(float)
for (fy, c, s), g in cat.items():
    if c == "consulting" and s == "central_gov": cons[fy] = cons.get(fy, 0) + g
    if c == "agency_staff" and s == "councils": agc[fy] += g
ro = defaultdict(dict)
for r in csv.DictReader(open(f"{OUT}\\ro_staffheavy_arc.csv", encoding="utf-8")):
    ro[r["year"]][(r["service"], r["group"])] = float(r["real_gbp_per_head"])
with open(f"{OUT}\\juxtaposition.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["fy", "central_gov_consulting_gbp_m_nominal", "councils_agency_gbp_m_nominal",
                "england_libraries_real_ph", "england_cultural_real_ph",
                "england_planning_dev_real_ph", "england_street_cleansing_real_ph",
                "england_total_service_real_ph"])
    for fy in ["2013-14", "2018-19", "2024-25"]:
        w.writerow([fy, round(cons.get(fy, 0)/1e6, 1), round(agc.get(fy, 0)/1e6, 2),
                    ro[fy][("libraries", "england")], ro[fy][("cultural", "england")],
                    ro[fy][("planning_development", "england")], ro[fy][("street_cleansing", "england")],
                    ro[fy][("total_service_expenditure", "england")]])

# 5. curated top engagements (hand-checked)
top = [
 # amount, firm, category, supplier_raw, payer, date, expense_type, hand_check verdict
 (44014030.69,"Deloitte","consulting","DELOITTE","Department of Health and Social Care","2021-06-28","Consultancy/Professional Advice (expense_area Global Health)","single ledger row, txn 8001907635; COVID-era DHSC (Test-and-Trace period); no duplicate found"),
 (19419273.51,"Deloitte","consulting","DELOITTE","Department of Health and Social Care","2020-07-22","Delivery of NHS Transaction related operational efficiency","one row bundling six invoice numbers (8001284976/978/987/988/990/991); no duplicate"),
 (11959200.00,"Reed","welfare_to_work","REED IN PARTNERSHIP LTD","Department for Work and Pensions","2021-08-13","EP CEP RESTART CPA 5C HOME COUNTIES","Restart scheme contract payment; welfare-to-work, NOT agency staff"),
 (9820144.93,"PA Consulting","consulting","PA CONSULTING SERVICES LIMITED","Ministry of Housing, Communities and Local Government","(file gives no dates)","(none)","source file 16bde454... has no date column for any of its 1,181 rows; amount verified single row"),
 (8444541.00,"Deloitte","consulting","DELOITTE","Department of Health and Social Care","2020-07-23","Delivery of NHS Transaction related operational efficiency","no duplicate"),
 (7855054.20,"Deloitte","consulting","DELOITTE","Department of Health and Social Care","2021-04-09","Contractor/ Staff Substitution","DHSC's own label: consultants substituting for staff"),
 (7812000.00,"Reed","welfare_to_work","REED IN PARTNERSHIP LTD","Department for Work and Pensions","2021-08-13","EP CEP RESTART CPA 2A NORTH EAST & HUMBERSIDE","Restart scheme"),
 (6948928.80,"BCG","consulting","THE BOSTON CONSULTING GROUP UK LLP","Department of Health and Social Care","2021-02-15","Outsourcing Contract (expense_area Global Health)","COVID-era; BCG barely appears in the corpus before 2020-21"),
 (6113775.00,"McKinsey","consulting","McKinsey Development Partners","Foreign, Commonwealth and Development Office (FCDO)","2021-01-29","(none given)","McKinsey development-programmes entity; FCDO ledger gives no expense_type"),
 (5838330.00,"McKinsey","consulting","MCKINSEY AND CO INC UK","Department of Health and Social Care","2021-07-30","Consultancy/Professional Advice","COVID-era DHSC"),
 (5245452.00,"KPMG","consulting","KPMG LLP","Ministry of Defence","2017-11-15","Fees for professional services","largest single KPMG fee row; MOD"),
 (5069988.00,"PwC","consulting","PRICEWATERHOUSECOOPERS LLP","Ministry of Defence","2017-06-26","Fees for professional services","largest single PwC UK fee row; MOD"),
 (3600000.00,"EY","consulting","ERNST & YOUNG","Department for Work and Pensions","2019-11-05","EXP - PURCHASE OF GOODS/SERVICES - SUPPORT","largest single EY row"),
 (2580000.00,"Reed","agency_staff","REED EMPLOYMENT PLC","Ministry of Housing, Communities and Local Government","(file gives no dates)","(none)","largest single Reed agency row; same dateless MHCLG file as the PA row"),
 (1102000.00,"Gartner","consulting","GARTNER UK LTD","HM Revenue and Customs","2023-04-05","SW Lic Sup Off shlf","software licence/research subscription, not advice work — Gartner is mostly research subscriptions"),
 (838000.00,"Manpower","agency_staff","MANPOWER UK LTD","Royal Borough of Greenwich","2015-07-01","Expenditure Payments","one month of Greenwich's master-vendor temp-staff contract (GBP 106.8m total 2012-2017)"),
 (450000.00,"Comensura","agency_staff","Comensura Ltd","Bristol City Council","2024-08-30","Agency Staff","Bristol neutral-vendor agency contract (GBP 35.9m total 2024-2026)"),
 (370000.00,"Matrix SCM","agency_staff","MATRIX SCM LTD","Former council of North Yorkshire","2022-09-21","Temporary & Agency Staff","North Yorkshire neutral-vendor contract"),
]
with open(f"{OUT}\\top_engagements.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["amount_gbp","firm","category","supplier_raw","payer","date","expense_type","hand_check"])
    for t in top: w.writerow(t)

print("final outputs written")
