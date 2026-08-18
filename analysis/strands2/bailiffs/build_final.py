# Final build: firm x payer x year census (gross + net), council per-resident table,
# council-tax-dependence juxtaposition. Every inclusion was eyeballed (see notes.md).
import sqlite3, csv, os

DB = r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db"
OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\bailiffs"
con = sqlite3.connect(DB)

# (firm, tier, flag, supplier_raw, publisher)
INCLUDE = [
    ("Marston", "debt_enforcement", "", "MARSTON GROUP", "Ministry of Justice"),
    ("Marston", "debt_enforcement", "", "MARSTON GROUP LTD", "Department for Work and Pensions"),
    ("Marston", "debt_enforcement", "", "MARSTON GROUP LIMITED", "Royal Borough of Greenwich"),
    ("Marston", "debt_enforcement", "", "Marston (Holdings) Limited", "Bristol City Council"),
    ("Marston", "debt_enforcement", "", "Marston Group Limited", "Bristol City Council"),
    ("Marston", "debt_enforcement", "refund_row", "Marston Group Ltd", "Rushmoor Borough Council"),
    ("Marston", "debt_enforcement", "", "MARSTON GROUP LTD", "North Yorkshire Council"),
    ("Marston", "debt_enforcement", "", "MARSTON GROUP LTD", "Department for Environment, Food and Rural Affairs"),
    ("Bristow & Sutor", "debt_enforcement", "", "Bristow & Sutor", "Bristol City Council"),
    ("Bristow & Sutor", "debt_enforcement", "", "Bristow & Sutor", "South Gloucestershire Council"),
    ("Bristow & Sutor", "debt_enforcement", "", "Bristow & Sutor", "Cheltenham Borough Council"),
    ("Bristow & Sutor", "debt_enforcement", "", "BRISTOW & SUTOR", "North Yorkshire Council"),
    ("Bristow & Sutor", "debt_enforcement", "", "BRISTOW SUTOR", "Blaby District Council"),
    ("Jacobs (enforcement)", "debt_enforcement", "", "JACOBS DEBT RECOVERY", "North Yorkshire Council"),
    ("Equita", "debt_enforcement", "", "EQUITA LTD", "HM Revenue and Customs"),
    ("Equita", "debt_enforcement", "", "EQUITA LTD", "Royal Borough of Greenwich"),
    ("Equita", "debt_enforcement", "", "EQUITA LIMITED", "North Yorkshire Council"),
    ("Rossendales", "debt_enforcement", "", "ROSSENDALES LTD", "HM Revenue and Customs"),
    ("Rossendales", "debt_enforcement", "", "Rossendales Limited", "HM Revenue and Customs"),
    ("Rossendales", "debt_enforcement", "", "Rossendales Ltd", "HM Revenue and Customs"),
    ("Rossendales", "debt_enforcement", "", "ROSSENDALES LTD", "Ministry of Justice"),
    ("Rossendales", "debt_enforcement", "", "ROSSENDALES LTD", "Royal Borough of Greenwich"),
    ("Rossendales", "debt_enforcement", "", "ROSSENDALES", "Blaby District Council"),
    ("Rossendales", "debt_enforcement", "", "Rossendales Ltd", "Bristol City Council"),
    ("CDER Group", "debt_enforcement", "", "CDER Group Limited", "Bristol City Council"),
    ("CDER Group", "debt_enforcement", "", "CDER GROUP LIMITED.", "Department of Health and Social Care"),
    ("Whyte & Co", "debt_enforcement", "", "WHYTE & CO", "Royal Borough of Greenwich"),
    ("Rundles", "debt_enforcement", "", "RUNDLES & CO LTD", "Royal Borough of Greenwich"),
    ("Rundles", "debt_enforcement", "", "Rundle & Co Limited", "South Gloucestershire Council"),
    ("Rundles", "debt_enforcement", "", "Rundle & Co Ltd", "Uttlesford District Council"),
    ("Rundles", "debt_enforcement", "payer_may_be_debtor", "RUNDLE & CO LTD", "Transport for Greater Manchester"),
    ("JBW Group", "debt_enforcement", "", "JBW GROUP LIMITED", "Royal Borough of Greenwich"),
    ("JBW Group", "debt_enforcement", "", "JBW Group", "Plymouth City Council"),
    ("Ross & Roberts", "debt_enforcement", "", "ROSS & ROBERTS LTD", "Royal Borough of Greenwich"),
    ("Ross & Roberts", "debt_enforcement", "", "Ross & Roberts Ltd.", "Bristol City Council"),
    ("Ross & Roberts", "debt_enforcement", "", "Ross & Roberts Limited", "Rushmoor Borough Council"),
    ("Quality Bailiffs (Enforcement Bailiffs Ltd)", "debt_enforcement", "", "Enforcement Bailiffs Ltd t/a Quality Bailiffs", "Cheltenham Borough Council"),
    ("Quality Bailiffs (Enforcement Bailiffs Ltd)", "debt_enforcement", "expense_code_R&M", "Enforcement Bailiffs Ltd", "Rushmoor Borough Council"),
    ("Civil Enforcement Agents Ltd", "debt_enforcement", "", "CIVIL ENFORCEMENT AGENTS LTD", "North Yorkshire Council"),
    ("Civil Enforcement Agents Ltd", "debt_enforcement", "", "CIVIL ENFORCEMENT AGENTS LTD", "Former council of North Yorkshire"),
    ("JTR Collections", "debt_enforcement", "", "JTR COLLECTIONS", "North Yorkshire Council"),
    ("JTR Collections", "debt_enforcement", "", "JTR COLLECTIONS", "Former council of North Yorkshire"),
    ("Capital Resolve", "debt_enforcement", "", "CAPITAL RESOLVE LTD", "North Yorkshire Council"),
    ("CCS Enforcement Services", "debt_enforcement", "", "CCS ENFORCEMENT SERVICES LTD", "Royal Borough of Greenwich"),
    ("Enforcement Services (name as published)", "debt_enforcement", "generic_name_finance_area", "ENFORCEMENT SERVICES", "Blaby District Council"),
    ("Illion Digital Tech (debt software)", "debt_enforcement", "software_not_agent", "ILLION DIGITAL TECH SOLUTIONS UK LTD", "Former council of North Yorkshire"),
    ("Able Investigations (eviction/property)", "property_enforcement", "", "Able Investigations and Enforcement Solutions Limited", "Bristol City Council"),
    ("Bail Enforcement Agency Ltd", "property_enforcement", "trade_unclear", "BAIL ENFORCEMENT AGENCY LTD", "Royal Borough of Greenwich"),
]

with open(os.path.join(OUT, "firm_year_payer.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["firm", "tier", "flag", "payer", "supplier_raw", "year", "txns",
                "gross_outflow_gbp", "gross_inflow_gbp", "net_gbp"])
    for firm, tier, flag, sup, pub in INCLUDE:
        q = """select substr(year_month,1,4) yr, count(*) t,
                      round(sum(case when amount>0 then amount else 0 end),2) pos,
                      round(sum(case when amount<0 then amount else 0 end),2) neg,
                      round(sum(amount),2) net
               from transactions where supplier_raw=? and publisher=?
               group by yr order by yr"""
        for yr, t, pos, neg, net in con.execute(q, (sup, pub)):
            w.writerow([firm, tier, flag, pub, sup, yr, t, pos, neg, net])

# Council-level rollup (debt_enforcement tier only, council payers only)
COUNCILS = {
    "Bristol City Council": ("Bristol", "UA", 494225, "2024-25", 60.5, 60.7),
    "Royal Borough of Greenwich": ("Greenwich", "LB", 264008, "2013-14", 45.6, 42.9),
    "North Yorkshire Council": ("North Yorkshire", "UA", 633692, "2024-25", 76.0, 81.0),
    "Former council of North Yorkshire": ("North Yorkshire", "UA", 633692, "2024-25", 76.0, 81.0),
    "South Gloucestershire Council": ("South Gloucestershire", "UA", 269107, "2013-14", 74.3, 74.7),
    "Uttlesford District Council": ("Uttlesford", "SD", 94953, "2024-25", 59.2, 65.4),
    "Plymouth City Council": ("Plymouth", "UA", 259175, "2013-14", 58.4, 54.0),
    "Blaby District Council": ("Blaby", "SD", 100421, "2018-19", 58.0, 66.9),
    "Cheltenham Borough Council": ("Cheltenham", "SD", 117090, "2018-19", 64.3, 66.8),
    "Rushmoor Borough Council": ("Rushmoor", "SD", 95142, "2018-19", 64.2, 72.4),
}
agg = {}
for firm, tier, flag, sup, pub in INCLUDE:
    if pub not in COUNCILS or tier != "debt_enforcement":
        continue
    q = """select count(*),
                  round(sum(case when amount>0 then amount else 0 end),2),
                  round(sum(amount),2), min(year_month), max(year_month)
           from transactions where supplier_raw=? and publisher=?"""
    t, pos, net, a, b = con.execute(q, (sup, pub)).fetchone()
    name = COUNCILS[pub][0]
    d = agg.setdefault(name, {"txns": 0, "gross": 0.0, "net": 0.0, "firms": set(), "first": a, "last": b})
    d["txns"] += t; d["gross"] += pos or 0; d["net"] += net or 0; d["firms"].add(firm)
    d["first"] = min(d["first"], a); d["last"] = max(d["last"], b)

with open(os.path.join(OUT, "council_enforcement_vs_ct_dependence.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["council", "cls", "n_enforcement_firms", "firms", "window_first", "window_last",
                "txns", "gross_paid_to_firms_gbp", "net_cost_gbp",
                "population", "pop_vintage", "gross_per_1000_residents_gbp", "net_per_1000_residents_gbp",
                "ct_share_financing_pct_2024_25", "ct_share_nre_pct_2024_25"])
    byname = {v[0]: (k, v) for k, v in COUNCILS.items() if not k.startswith("Former")}
    for name, d in sorted(agg.items(), key=lambda kv: -kv[1]["gross"]):
        _, (nm, cls, pop, vint, fin, nre) = byname[name][0], byname[name][1]
        w.writerow([name, cls, len(d["firms"]), "; ".join(sorted(d["firms"])), d["first"], d["last"],
                    d["txns"], round(d["gross"], 2), round(d["net"], 2),
                    pop, vint, round(1000 * d["gross"] / pop, 2), round(1000 * d["net"] / pop, 2),
                    fin, nre])

# Firm totals across all payers
with open(os.path.join(OUT, "firm_totals.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["firm", "tier", "payers", "txns", "gross_outflow_gbp", "net_gbp", "first", "last"])
    ft = {}
    for firm, tier, flag, sup, pub in INCLUDE:
        q = """select count(*),
                      round(sum(case when amount>0 then amount else 0 end),2),
                      round(sum(amount),2), min(year_month), max(year_month)
               from transactions where supplier_raw=? and publisher=?"""
        t, pos, net, a, b = con.execute(q, (sup, pub)).fetchone()
        d = ft.setdefault(firm, {"tier": tier, "payers": set(), "t": 0, "pos": 0.0, "net": 0.0,
                                 "a": a, "b": b})
        d["payers"].add(pub); d["t"] += t; d["pos"] += pos or 0; d["net"] += net or 0
        if a: d["a"] = min(d["a"] or a, a)
        if b: d["b"] = max(d["b"] or b, b)
    for firm, d in sorted(ft.items(), key=lambda kv: -kv[1]["pos"]):
        w.writerow([firm, d["tier"], "; ".join(sorted(d["payers"])), d["t"],
                    round(d["pos"], 2), round(d["net"], 2), d["a"], d["b"]])

print("final build done")
