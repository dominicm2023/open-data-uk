# Step 2: catch-alls + row-level honesty checks + central debt context.
import sqlite3, csv, os
from collections import Counter

DB = r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db"
OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\bailiffs"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# A) catch-all: enforcement/bailiff/collections in the SUPPLIER name itself
with open(os.path.join(OUT, "eyeball_supplier_catchall.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["pattern", "supplier_raw", "publisher", "txns", "gbp", "first", "last", "ets"])
    for name, pat in {
        "ENFORC_IN_NAME": "%ENFORC%",
        "BAILIFF_IN_NAME": "%BAILIFF%",
        "SUTOR": "%SUTOR%",
        "DEBT_IN_NAME": "%DEBT%",
        "COLLECTIONS_IN_NAME": "%COLLECTIONS%",
    }.items():
        q = """select supplier_raw, publisher, count(*) t, round(sum(amount),2) g,
                      min(year_month) a, max(year_month) b,
                      group_concat(distinct expense_type) ets
               from transactions where upper(supplier_raw) like ?
               group by supplier_raw, publisher order by g desc"""
        for r in con.execute(q, (pat,)):
            w.writerow([name, r["supplier_raw"], r["publisher"], r["t"], r["g"], r["a"], r["b"], (r["ets"] or "")[:200]])

# B) honesty check: row-level detail for the eyeballed-in firm x payer pairs
PAIRS = [
    # (canonical firm, supplier_raw exact, publisher)
    ("Marston", "MARSTON GROUP", "Ministry of Justice"),
    ("Marston", "MARSTON GROUP LTD", "Department for Work and Pensions"),
    ("Marston", "MARSTON GROUP LIMITED", "Royal Borough of Greenwich"),
    ("Marston", "Marston (Holdings) Limited", "Bristol City Council"),
    ("Marston", "Marston Group Limited", "Bristol City Council"),
    ("Marston", "Marston Group Ltd", "Rushmoor Borough Council"),
    ("Marston", "MARSTON GROUP LTD", "North Yorkshire Council"),
    ("Marston", "MARSTON GROUP LTD", "Department for Environment, Food and Rural Affairs"),
    ("Bristow & Sutor", "Bristow & Sutor", "Bristol City Council"),
    ("Bristow & Sutor", "Bristow & Sutor", "South Gloucestershire Council"),
    ("Bristow & Sutor", "Bristow & Sutor", "Cheltenham Borough Council"),
    ("Bristow & Sutor", "BRISTOW & SUTOR", "North Yorkshire Council"),
    ("Bristow & Sutor", "BRISTOW SUTOR", "Blaby District Council"),
    ("Jacobs (enforcement)", "JACOBS DEBT RECOVERY", "North Yorkshire Council"),
    ("Equita", "EQUITA LTD", "HM Revenue and Customs"),
    ("Equita", "EQUITA LTD", "Royal Borough of Greenwich"),
    ("Equita", "EQUITA LIMITED", "North Yorkshire Council"),
    ("Rossendales", "ROSSENDALES LTD", "HM Revenue and Customs"),
    ("Rossendales", "Rossendales Limited", "HM Revenue and Customs"),
    ("Rossendales", "Rossendales Ltd", "HM Revenue and Customs"),
    ("Rossendales", "ROSSENDALES LTD", "Ministry of Justice"),
    ("Rossendales", "ROSSENDALES LTD", "Royal Borough of Greenwich"),
    ("Rossendales", "ROSSENDALES", "Blaby District Council"),
    ("Rossendales", "Rossendales Ltd", "Bristol City Council"),
    ("CDER", "CDER Group Limited", "Bristol City Council"),
    ("CDER", "CDER GROUP LIMITED.", "Department of Health and Social Care"),
    ("Whyte & Co", "WHYTE & CO", "Royal Borough of Greenwich"),
    ("Rundles", "RUNDLES & CO LTD", "Royal Borough of Greenwich"),
    ("Rundles", "Rundle & Co Limited", "South Gloucestershire Council"),
    ("Rundles", "Rundle & Co Ltd", "Uttlesford District Council"),
    ("Rundles", "RUNDLE & CO LTD", "Transport for Greater Manchester"),
    ("JBW", "JBW GROUP LIMITED", "Royal Borough of Greenwich"),
    ("JBW", "JBW Group", "Plymouth City Council"),
    ("Ross & Roberts", "ROSS & ROBERTS LTD", "Royal Borough of Greenwich"),
    ("Ross & Roberts", "Ross & Roberts Ltd.", "Bristol City Council"),
    ("Ross & Roberts", "Ross & Roberts Limited", "Rushmoor Borough Council"),
]

# B1: per pair x expense_type x year summary + amount stats
with open(os.path.join(OUT, "firm_payer_expense_detail.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["firm", "supplier_raw", "publisher", "expense_type", "year", "txns", "gbp",
                "n_negative", "gbp_negative", "min_amt", "max_amt"])
    for firm, sup, pub in PAIRS:
        q = """select expense_type, substr(year_month,1,4) yr, count(*) t, round(sum(amount),2) g,
                      sum(amount<0) nneg, round(sum(case when amount<0 then amount else 0 end),2) gneg,
                      round(min(amount),2) mn, round(max(amount),2) mx
               from transactions where supplier_raw = ? and publisher = ?
               group by expense_type, yr order by yr, g desc"""
        for r in con.execute(q, (sup, pub)):
            w.writerow([firm, sup, pub, r["expense_type"], r["yr"], r["t"], r["g"],
                        r["nneg"], r["gneg"], r["mn"], r["mx"]])

# B2: modal amounts (fee-structure fingerprint) per firm x publisher
with open(os.path.join(OUT, "amount_fingerprint.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["firm", "publisher", "txns", "top_amounts (amount xcount)"])
    agg = {}
    for firm, sup, pub in PAIRS:
        key = (firm, pub)
        amts = [r[0] for r in con.execute(
            "select amount from transactions where supplier_raw=? and publisher=?", (sup, pub))]
        agg.setdefault(key, []).extend(amts)
    for (firm, pub), amts in agg.items():
        c = Counter(round(a, 2) for a in amts)
        top = "; ".join(f"{amt}x{n}" for amt, n in c.most_common(8))
        w.writerow([firm, pub, len(amts), top])

# B3: North Yorkshire zero-amount rows in full
with open(os.path.join(OUT, "nyc_zero_rows.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["publisher", "supplier_raw", "date", "year_month", "amount", "expense_type", "expense_area", "source_file"])
    q = """select publisher, supplier_raw, date, year_month, amount, expense_type, expense_area, source_file
           from transactions
           where publisher like '%North Yorkshire%'
             and (supplier_raw in ('MARSTON GROUP LTD','JACOBS DEBT RECOVERY','EQUITA LIMITED','BRISTOW & SUTOR'))
           order by supplier_raw, date"""
    for r in con.execute(q):
        w.writerow(list(r))

# C) central government debt-collection context (unambiguous debt-collection contractors)
CENTRAL = {
    "Indesser/iDS": ["INDESSER", "INTEGRATED DEBT SERVICES LTD", "INTEGRATED DEBT SERVICES LTD T/AS"],
    "TDX Group": ["TDX GROUP LTD"],
    "iQor": ["iQor holdings Limited", "IQOR HOLDINGS LTD"],
    "Advantis Credit": ["ADVANTIS CREDIT LTD"],
    "Akinika": ["AKINIKA", "AKINIKA HOLDINGS (UK) LIMITED"],
    "Bluestone Credit Mgmt": ["BLUESTONE CREDIT MANAGEMENT LTD"],
    "Commercial Collection Services": ["COMMERCIAL COLLECTION SERVICES", "Commercial Collection Services"],
    "Credit Solutions": ["Credit Solutions"],
    "Drydens/drydensfairfax": ["DRYDENS LTD", "DRYDENS FAIRFAX SOLICITORS", "DRYDENSFAIRFAX SOLICITORS"],
    "Qualco": ["QUALCO UK LTD"],
    "Capital Resolve": ["CAPITAL RESOLVE LTD"],
    "CCI Credit Management": ["CCI CREDIT MANAGEMENT LTD", "CCI LEGAL SERVICES LTD"],
    "JTR Collections": ["JTR COLLECTIONS"],
    "Marston": ["MARSTON GROUP", "MARSTON GROUP LTD"],
    "Equita": ["EQUITA LTD"],
    "Rossendales": ["ROSSENDALES LTD", "Rossendales Limited", "Rossendales Ltd"],
}
with open(os.path.join(OUT, "central_debt_context.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["group", "supplier_raw", "publisher", "expense_type_class", "year", "txns", "gbp"])
    for grp, sups in CENTRAL.items():
        ph = ",".join("?" * len(sups))
        q = f"""select supplier_raw, publisher, expense_type, substr(year_month,1,4) yr,
                       count(*) t, round(sum(amount),2) g
                from transactions where supplier_raw in ({ph})
                group by supplier_raw, publisher, expense_type, yr order by publisher, yr"""
        for r in con.execute(q, sups):
            w.writerow([grp, r["supplier_raw"], r["publisher"], r["expense_type"], r["yr"], r["t"], r["g"]])

# D) court-side costs of collection (summons/liability-order fees paid to courts)
with open(os.path.join(OUT, "court_collection_costs.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["publisher", "supplier_raw", "expense_type", "year", "txns", "gbp"])
    q = """select publisher, supplier_raw, expense_type, substr(year_month,1,4) yr,
                  count(*) t, round(sum(amount),2) g
           from transactions
           where (expense_type = 'Court Costs Summons Fees')
              or (expense_type in ('Council Tax Collection','Cost of NNDR Collection') and publisher='Rushmoor Borough Council')
              or (supplier_raw = 'TRAFFIC ENFORCEMENT CENTRE')
           group by publisher, supplier_raw, expense_type, yr order by publisher, yr"""
    for r in con.execute(q):
        w.writerow(list(r))

print("step2 done")
