"""Classify eyeballed supplier strings, aggregate by FY/firm/category/sector.
Every string from candidates_raw.csv gets a decision: include (with category+scope) or exclude (with reason).
Row-level reclassification: fund-management/grant expense types -> routed_fund category.
"""
import sqlite3, csv, re
from collections import defaultdict

DB  = r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db"
OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\consultants"

CONSULTING = "consulting"
AGENCY     = "agency_staff"
W2W        = "welfare_to_work"
ROUTED     = "routed_fund"

# ---------- string-level decisions ----------
# exclude: exact supplier_raw -> reason  (matched by generous pattern but NOT the firm / not fees)
EXCLUDE = {
 # Deloitte
 "Rank Group PLC c/o Deloittes": "payment to Rank Group via Deloitte as agent (c/o)",
 "Wm Morrisons Supermarkets PLC c/o Deloitte LLP": "payment to Morrisons via Deloitte as agent (c/o)",
 "WGIS c/o Deloitte Legal": "payment to WGIS via Deloitte Legal as agent (c/o)",
 "Deloitte Real Estate (LLP No 3 a/c)": "client-money account, likely routed payment",
 "DELOITTE LLP NO 2 ACCOUNT": "client-money account, likely routed payment",
 # PwC c/o + artifacts
 "Phoenix Group Holdings Ltd c/o PWC": "payment to Phoenix Group via PwC as agent (c/o)",
 "St. George's University  c/o PWC": "payment to St George's University via PwC (c/o)",
 "RPM Ltd c/o PWC LLP": "payment to RPM Ltd via PwC (c/o)",
 "Worldpay (UK) c/o PWC LLP": "payment to Worldpay via PwC (c/o)",
 "Baring Asset Management Ltd c/o PWC": "payment to Barings via PwC (c/o)",
 "Hippodrome Casino Ltd c/o PWC": "payment to Hippodrome via PwC (c/o)",
 "Sojourn Hotels Ltd c/o PwC": "payment to Sojourn Hotels via PwC (c/o)",
 "PricewaterhouseCoopers LLP Total": "ledger 'Total' artifact row, double-count risk",
 # EY false matches (ERNST inside bERNSTein etc.)
 "Levitt Bernstein Associates Ltd": "architects; 'ERNST' substring inside 'Bernstein'",
 "HOWARD BERNSTEIN SOLICITORS": "solicitors; Bernstein false match",
 "HOWARD BERNSTEIN SOLICITORS [ADVOCATE]": "solicitors; Bernstein false match",
 "BERNSTOCK SPEIRS": "hat maker; Bernstock false match",
 "ERNST HEINE": "individual/unrelated; not EY",
 "SAL BEL EY L LASH P VI": "garbled purchase-card string; not EY",
 "Vale Europe Ltd c/o Ernst & Young LLP": "payment to Vale Europe via EY (c/o)",
 "Dolphin Drilling Ltd c/o Ernst & Young LLP": "payment to Dolphin Drilling via EY (c/o)",
 # KPMG
 "Hiscox PLC c/o KPMG LLP": "payment to Hiscox via KPMG (c/o)",
 "Delinian Ltd c/o KPMG Law": "payment to Delinian via KPMG Law (c/o)",
 "Delinian Ltd. c/o KPMG Law": "payment to Delinian via KPMG Law (c/o)",
 "Poundland Ltd. c/o KPMG Law": "payment to Poundland via KPMG Law (c/o)",
 "HBOS PLC & Lloyds Bank c/o KPMG LLP": "payment to HBOS/Lloyds via KPMG (c/o)",
 "Associated Newspapers Ltd c/o KPMG": "payment to Associated Newspapers via KPMG (c/o)",
 "CITY OF LONDON KPMG ACADEMY HACKNEY": "academy school (KPMG-sponsored), not KPMG",
 # Bain false matches
 "MCBAINS LTD": "McBains, construction consultancy, unrelated",
 "McBains Ltd": "McBains, construction consultancy, unrelated",
 "Baines' Endowed Primary School & Children's Centre": "school",
 "Baines' Endowed Primary School": "school",
 "Baines School": "school",
 "THE GOVERNORS OF BAINES SCHOOL GRANT ACCOUNT": "school grant account",
 "THE GOVERNORS OF BAINES SCHOOL GRANT ACC": "school grant account",
 "BAINES SIMMONS LIMITED": "aviation safety consultancy, unrelated",
 "NORBAIN SD LTD (CO REG 06248590)": "CCTV distributor",
 "NORBAIN SD LTD": "CCTV distributor",
 "NORBAIN DUNASFERN": "CCTV distributor",
 "COBAINS SOLICITORS": "solicitors",
 "BAINS SOLICITORS": "solicitors",
 "SYMES BAINS BROOMER SOLICITORS": "solicitors",
 "BAINES WILSON": "solicitors",
 "Bell & Bain Ltd": "printers, Glasgow",
 "GILES D BAIN": "individual",
 "GILES BAIN": "individual",
 "MR GILES BAIN": "individual",
 "WILLIAM BAIN CO": "unrelated company",
 "BAINBRIDGE BUILDING CONTRACT": "builder",
 "Bainbridge Building Contractors": "builder",
 "BIRCH BAINBRIDGE BUILDING & INTERIORS": "builder",
 "S C BAINBRIDGE FUNERAL DIRECTORS": "funeral directors",
 "BAINBRIDGE PARISH COUNCIL": "parish council",
 "BAINBRIDGE VILLAGE HALL": "village hall",
 "BAINBRIDGE CHRISTMAS LIGHTS": "village event",
 "SDAD BILBAINA DE RECRE": "Bilbao club, purchase card",
 "SOCIEDAD BILBAINA RECR": "Bilbao club, purchase card",
 "SQ  SEMIS URBAINS / UR": "French urban seeds, purchase card",
 "PESAPAL-ALBAININSTIT": "purchase card, unrelated",
 "C O H BAINES LTD": "unrelated company",
 # BCG false matches
 "BCG DIRECT LIMITED": "direct mail company, not Boston Consulting",
 "MERPAGO ABCGARDEN": "purchase card, unrelated",
 "BCG OXFORD": "purchase card, ambiguous (possibly BCG vaccine clinic)",
 # PA Consulting false matches
 "FPA CONSULTING": "FPA Consulting, unrelated",
 "PPA CONSULTING LTD": "PPA Consulting, unrelated",
 # Hays false matches
 "HAYS TRAVEL LIMITED": "Hays Travel (Sunderland travel agent), different company",
 "HAYS TRAVEL": "Hays Travel, different company",
 "HAYSFIELD GIRLS SCHOOL": "school",
 "Chaysestar Entertainment CIC": "unrelated CIC",
 "HAYSAM ABOU-DOMA": "individual",
 "HAYSDEN TRAINING": "unrelated trainer",
 # Michael Page: none excluded
 # Matrix: everything except Matrix SCM
 # Manpower
 "Manpower Direct UK Ltd": "ManpowerDirect UK, security guarding firm, not ManpowerGroup",
 "MANPOWER DIRECT (UK) LTD": "ManpowerDirect UK, security guarding firm, not ManpowerGroup",
 "Quantum Manpower Services Limited": "unrelated",
 "MANPOWER DEVELOPMENT INSTITUTE": "unrelated institute",
 "MANPOWER & MAINTENANCE": "unrelated",
 # Reed: schools, RELX publishing/exhibitions, law firms, Freedom/Breed/Creed etc.
 "Alec Reed Academy": "academy school (named after Reed founder), DfE grant funding",
 "The Alec Reed Academy": "academy school, DfE grant funding",
 "Reedswood E-ACT Academy": "school",
 "Reedswood E-ACT Primary School": "school",
 "GRAMPOUND-WITH-CREED COFE SCHOOL": "school",
 "GRAMPOUND WITH CREED C OF E PRIMARY SCHOOL": "school",
 "Reed Business School Ltd": "Reed family business school; DfE rows are grant funding, not services",
 "REED BUSINESS SCHOOL": "Reed family business school, training course purchase",
 "REED LOCATION": "Greenwich housing disturbance/relocation payments, not the recruiter",
 "REED EXHIBITIONS LTD": "RELX (Reed Elsevier) exhibitions, different company",
 "Reed Exhibitions Ltd": "RELX exhibitions",
 "REED EXHIBITIONS FZ-LLC": "RELX exhibitions",
 "REED EXHIBITIONS LT": "RELX exhibitions",
 "REED EXHIBITIONS": "RELX exhibitions",
 "REED EXPOSITIONS FRANCE": "RELX exhibitions",
 "REED EXPO FRANCE": "RELX exhibitions",
 "REEDMIDEM.COM": "RELX (Reed MIDEM)",
 "REED MIDEM": "RELX (Reed MIDEM)",
 "REED MIDEM LTD": "RELX (Reed MIDEM)",
 "REED BUSINESS INFORMATION LTD": "RELX publishing",
 "REED BUSINESS INFORMATION": "RELX publishing",
 "REED BUSINESS INFORMATION (EAST GRIN": "RELX publishing",
 "Reed Business Information Ltd.": "RELX publishing",
 "Reed Business Information Ltd": "RELX publishing",
 "Reed Business Information": "RELX publishing",
 "Reed Business Informations Ltd": "RELX publishing",
 "REED BUSINESS INFORM": "RELX publishing",
 "REED BUSINESS INFORMAT": "RELX publishing",
 "REED BUSINESS INFORMATION LIMITED": "RELX publishing",
 "*REED BUSINESS INFORMATION LTD": "RELX publishing",
 "REED BUS INFORMATION": "RELX publishing",
 "Reed Business": "RELX publishing",
 "SUBSCRIPTION/REED": "RELX subscription",
 "SUBSCRIPTION/REED        BUS.INFO": "RELX subscription",
 "Lexis Nexis Reed Elsevier (Uk) Ltd T/A": "RELX / LexisNexis",
 "Reed Elsevier (UK) Ltd": "RELX",
 "Reed Elsevier (UK) Ltd T/A LN": "RELX / LexisNexis",
 "WILLIAM REED BUSINESS MEDIA LTD": "William Reed, trade publisher, unrelated",
 "REEDS SOLICITORS LTD": "solicitors",
 "Reeds Solicitors LLP": "solicitors",
 "STERNBERG REED SOLICITORS": "solicitors",
 "STERNBERG REED": "solicitors",
 "STERNBERG REED SOLICITORS-ADVOCATE": "solicitors",
 "CREED LANE LAW GROUP": "law firm",
 "MESSRS CREED LANE LAW GROUP#EC4V 5BR": "law firm",
 "CREED LANE LAW GROUP-ADVOCATE": "law firm",
 "REED SMITH LLP": "Reed Smith, US law firm, unrelated",
 "MICHAEL J REED LTD": "unrelated",
 "Fiona Reed Associates Ltd": "unrelated consultancy (individual)",
 "SABINA BOWLER-REED": "individual",
 "Emma Reed": "individual",
 "MARK REED": "individual",
 "ALAN REED ART LTD": "artist",
 "KIERAN SCRAGG & NEIL REED T/A IKO": "individuals t/a",
 "LEWIS REED (WAV) LTD": "wheelchair vehicles",
 "H&H REEDS PRINTERS LTD": "printers",
 "REEDMAN SERVICES LTD": "unrelated",
 "REED CHILL CHEATER": "canoe/outdoor gear maker",
 "REED-CHILL CHEATER LTD": "canoe/outdoor gear maker",
 "REED CHILL CHEATER       BRAUNTON": "canoe/outdoor gear maker",
 "Reed Engineering Building Services L": "building services",
 "Reed Building Services": "building services",
 "W Reed (Builders) Limited": "builder",
 "REEDY SUPPLIES LTD": "unrelated",
 "REED HALL": "venue",
 "WHISPERING REEDS BOATS": "boats",
 "DUNCAN REEDS LTD": "unrelated",
 "REEDERJ VLAUN HOLDING B.V. /V&S CHARTERS": "Dutch charter firm",
 "YOCO HARLEY REED SA": "unrelated",
 "ALFAHMAWI FOR REED.": "unrelated",
 "SHREEDAR MOTORS LIMITED": "motors, SHREEDar false match",
 "Creedy Court": "care home/venue",
 "Peter Creed": "individual",
 "Creed Food Services  Ltd": "food services",
 "ACRA SCREED LTD": "flooring screed",
 "PERCY & REED PRODUCT LTD": "haircare brand",
 "GMF FREEDIO LTD": "unrelated",
 "Genus Breeding Ltd.": "cattle breeding",
 "Rare Breeds Survival Trust": "charity",
 "RARE BREEDS SURVIVAL TRUST": "charity",
 "BLONDE D'AQUITAINE BREEDERS SOCIETY OF GB LTD T/A BRITISH BLONDE SOCIETY": "cattle breeders",
 "Breedon Southern Ltd": "aggregates",
 "Breedon Cement Ltd": "aggregates",
 "BREEDON NORTHERN LTD": "aggregates",
}
# Freedom*/Freedman* etc: catch by regex below.
EXCLUDE_RE = [
 (re.compile(r"FREED", re.I), "'REED' inside Freedom/Freedman/etc, unrelated"),
 (re.compile(r"^MATRIX (?!SCM)", re.I), "Matrix-named firm, not Matrix SCM"),
]

# Reed group agency strings (default for REED-matched strings is exclude)
REED_AGENCY = {
 "REED SPECIALIST RECRUITMENT LTD","Hays!never","REED SPECIALIST RECRUITMENT LIMITED",
 "Reed Specialist Recruitment Ltd","REED SPECIALIST RECRUITMENT","Reed Specialist Recruitment",
 "Reed Specialist Recruitment Limited","REED SPECIALIST",
 "REED EMPLOYMENT PLC","REED EMPLOYMENT","Reed Employment plc","Reed Employment",
 "REED EMPLOYMENT SERVICES","Reed Personnel Services Plc","REED","Reed",
 "REED TALENT SOLUTIONS LTD","REED TALENT SOLUTIONS LIMITED TA CONSULTANCY PLUS",
 "Reed Talent Solutions t/a Consultancyplus","REED TALENT SOLUTIONS T/A CONSULTAN",
 "REED TECHNOLOGY","Reed Solutions",
 "REED ONLINE LIMITED","REED ONLINE LIMITED (E",
 "REED LEARNING LTD","REED LEARNING PLC","Reed Learning PLC","REED LEARNING",
 "REEDLEARNING.CO.UK","WWW.REEDLEARNING.C","REEDLEARNING","REED LEARNING BACS 22/2",
 "REED LEARNING BACS 21/12","WWW.REEDLEARNING.C       0207 5205100","REED TRAINING",
}
REED_AGENCY.discard("Hays!never")
REED_W2W = {
 "REED IN PARTNERSHIP LTD","REED IN PARTNERSHIP HACKNEY LTD","REED IN PARTNERSHIP",
 "Reed in Partnership Limited","REED IN PARTNERSHIP LIMITED","Reed in Partnership Skills (UK) Ltd",
}
MATRIX_OK = {"MATRIX SCM LTD","Matrix SCM Ltd"}
BAIN_OK   = {"BAIN & COMPANCY INC UNITED KINGDOM","BAIN & COMPANY","Bain & Company"}

PWC_CLIENT_ACCT = {
 "PWC GEC Client Account","PWC Gec Client Account",
 "PRICEWATERHOUSECOOPER LLP - SPF CLIENT MONEY","PWC LLP (HMRC GRANTS)",
}

CONSULT_FIRMS = {"Deloitte","PwC","EY","KPMG","McKinsey","Bain","BCG","PA Consulting","Gartner"}
AGENCY_FIRMS  = {"Hays","Reed","Michael Page","Matrix SCM","Comensura","Adecco","Manpower"}

OVERSEAS_RE = re.compile(
 r"INDIA|UGANDA|KENYA|MALAWI|KOSOVA|ZAMBIA|MOCAMBIQUE|INDONESIA|YOUSUF ADIL|AKINTOLA|"
 r"PTY|TOHMATSU|DTTIPL|GHANA|RWANDA|TANZANIA|VIETNAM|POLAND|SHANGHAI|SHENZHEN|CHINA|DUBAI|"
 r"DRC|RDC|BEOGRAD|CONSULTORES|LIMITADA|HRLINGS|AFRIQUE|AFRICA|NGN|\bINC\b|INCORPORATED|"
 r"KAZAKHSTAN|KURUMSAL|FORD RHODES|SIDAT|TASEER|SIERRA LEONE|HONG KONG|ANGOLA|FIDUCIAIRE|"
 r"SOUTH SUDAN|NIGERIA|ISRAEL|SRL|S R L|RRHH|ACADEMY LLC|IDAS|EAST AFRICA|ZMW|KASPL|"
 r"DEVELOPMENT SERVICE|DEVELOPMENT PARTNERS|GLOBAL SERVICES|AUDITORES|DANISMANLIGI|"
 r"N\.V\.|\(SA\)|PT DELOITTE|SAS$|FAS CO|AUSTRALIA|PRETORIA", re.I)

ROUTED_ET_RE = re.compile(r"FUND MONIES|ACCOUNTABLE GRANT|AID TO CIVIL SOCIETY|GRANTS? EXPENDITURE", re.I)

COUNCILS = {
 "Bristol City Council","Royal Borough of Greenwich","North Yorkshire Council",
 "Former council of North Yorkshire","Former district of Harrogate","Rushmoor Borough Council",
 "South Gloucestershire Council","Uttlesford District Council","Plymouth City Council",
 "Blaby District Council","Eden District Council","Cheltenham Borough Council",
 "London Borough of Richmond Upon Thames",
}
def sector(pub):
    if pub in COUNCILS: return "councils"
    if pub == "Transport for Greater Manchester": return "other_local"
    if ("NHS" in pub or "Hospital" in pub or "CCG" in pub or "ICB" in pub
        or "Healthcare" in pub or "Ambulance" in pub or "Pennine" in pub):
        return "nhs"
    return "central_gov"

def fy(ym):
    if not ym or len(ym) < 7: return "unknown"
    y, m = int(ym[:4]), int(ym[5:7])
    s = y if m >= 4 else y - 1
    return f"{s}-{str(s+1)[2:].zfill(2)}"

# ---------- load candidate strings ----------
cands = []
with open(f"{OUT}\\candidates_raw.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        cands.append((r["firm"], r["supplier_raw"], int(r["txns"]), float(r["gbp"])))

decisions = {}   # supplier_raw -> (firm, category|None, reason)
excl_rows = []
for firm, s, txns, gbp in cands:
    if s in decisions:   # a string can match two firms' patterns; first firm wins, note it
        continue
    reason = EXCLUDE.get(s)
    if reason is None:
        for rx, rr in EXCLUDE_RE:
            if rx.search(s) and s not in MATRIX_OK:
                reason = rr; break
    if firm == "Reed" and reason is None:
        if s in REED_AGENCY: decisions[s] = (firm, AGENCY, "")
        elif s in REED_W2W:  decisions[s] = (firm, W2W, "")
        else: reason = "Reed-matched string not identifiable as Reed group"
    elif firm == "Bain" and reason is None:
        if s in BAIN_OK: decisions[s] = (firm, CONSULTING, "")
        else: reason = "Bain-matched string not Bain & Company"
    elif firm == "Matrix SCM" and reason is None:
        if s in MATRIX_OK: decisions[s] = (firm, AGENCY, "")
        else: reason = "Matrix-named firm, not Matrix SCM"
    elif reason is None:
        if s in PWC_CLIENT_ACCT:
            decisions[s] = (firm, ROUTED, "client account / grant-routing string")
        else:
            decisions[s] = (firm, CONSULTING if firm in CONSULT_FIRMS else AGENCY, "")
    if reason is not None and s not in decisions:
        excl_rows.append([firm, s, txns, round(gbp,2), reason])

with open(f"{OUT}\\variants_excluded.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["firm_matched","supplier_raw","txns","gbp","reason"])
    w.writerows(sorted(excl_rows, key=lambda r: -r[3]))

# ---------- pull rows for included strings ----------
con = sqlite3.connect(DB); cur = con.cursor()
inc_strings = list(decisions.keys())
agg   = defaultdict(lambda: [0.0, 0])       # (fy, firm, cat, sector) -> [gbp, txns]
vagg  = defaultdict(lambda: [0.0, 0])       # (firm, s, cat, scope) -> variant totals
month = defaultdict(float)                  # (ym, cat, sector) -> gbp (for covid monthly)
top   = []                                  # single rows for engagement check

CH = 400
for i in range(0, len(inc_strings), CH):
    chunk = inc_strings[i:i+CH]
    q = f"""SELECT supplier_raw, publisher, year_month, amount, expense_type, expense_area, date, source_file
            FROM transactions WHERE is_dup=0 AND supplier_raw IN ({','.join('?'*len(chunk))})"""
    for s, pub, ym, amt, et, ea, dt, sf in cur.execute(q, chunk):
        firm, cat, note = decisions[s]
        # row-level reclassification
        rcat = cat
        if cat in (CONSULTING, AGENCY):
            if et and ROUTED_ET_RE.search(et):
                rcat = ROUTED
            elif firm == "Reed" and pub == "Department for Work and Pensions" and et and \
                 re.search(r"NDDP|NEW DEAL|JSA|FSF|WORK PROG|RESTART|EMPLOYMENT PROG", et, re.I):
                rcat = W2W
        sec = sector(pub)
        f_y = fy(ym)
        a = agg[(f_y, firm, rcat, sec)]; a[0] += amt or 0; a[1] += 1
        scope = "overseas_member" if OVERSEAS_RE.search(s) else "uk"
        v = vagg[(firm, s, rcat, scope)]; v[0] += amt or 0; v[1] += 1
        if ym: month[(ym, rcat, sec)] += amt or 0
        if amt and amt >= 1_000_000:
            top.append((amt, firm, rcat, s, pub, dt or ym, et, ea, sf))

with open(f"{OUT}\\firm_variants_included.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["firm","supplier_raw","category","scope","txns","gbp"])
    for (firm, s, cat, scope), (g, n) in sorted(vagg.items(), key=lambda kv: -kv[1][0]):
        w.writerow([firm, s, cat, scope, n, round(g,2)])

with open(f"{OUT}\\yearly_firm_sector.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["fy","firm","category","sector","gbp","txns"])
    for (f_y, firm, cat, sec), (g, n) in sorted(agg.items()):
        w.writerow([f_y, firm, cat, sec, round(g,2), n])

with open(f"{OUT}\\monthly_category_sector.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["year_month","category","sector","gbp"])
    for (ym, cat, sec), g in sorted(month.items()):
        w.writerow([ym, cat, sec, round(g,2)])

top.sort(reverse=True)
with open(f"{OUT}\\top_payments_raw.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["amount","firm","category","supplier_raw","publisher","date","expense_type","expense_area","source_file"])
    for t in top[:80]:
        w.writerow([round(t[0],2)] + [str(x) for x in t[1:]])

print("included strings:", len(decisions), " excluded:", len(excl_rows))
print("rows written. top>=1m rows:", len(top))
