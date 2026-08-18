# Independent replication pass (2026-08-18) extras kept alongside build_outputs.py:
#  - uttlesford_ta_by_fy.csv : Uttlesford TA arc with the Ukraine emergency line broken out
#  - home_office_asylum_by_fy.csv : asylum-LABELED Home Office lines per FY (the label series)
import sqlite3, csv, os
from collections import defaultdict
os.chdir(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(r"C:\Users\domin\Documents\Open Data\analysis\spending\corpus.db")
cur = con.cursor()

def fy(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    f = y if m >= 4 else y - 1
    return f"{f}-{str(f+1)[-2:]}"

LINES = {
 "Homelessness - Accommodation": "homelessness_accommodation",
 "Temporary Accommodation - Third Party": "ta_third_party",
 "Emerg Accommodation - Ukrainian Refugees": "ukraine_emergency_accommodation",
}
HOTELS = ("De Salis Hotel", "Oasis Hotel Harlow Limited", "Skyline Hotel",
          "George (Bishop Stortford) Hotel LTD", "Stansted Airport Lodge",
          "Malvern Lodge Guest House", "Olivers Lodge")
agg = defaultdict(lambda: defaultdict(float))
for ym, a, et, sup in cur.execute("""SELECT year_month, amount, expense_type, supplier_raw
        FROM transactions WHERE is_dup=0 AND publisher='Uttlesford District Council'"""):
    if et in LINES:
        k = fy(ym)
        agg[k][LINES[et]] += a or 0
        agg[k]["ta_lines_total"] += a or 0
        if sup in HOTELS: agg[k]["of_which_named_hotels"] += a or 0
with open("uttlesford_ta_by_fy.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    cols = ["fiscal_year", "homelessness_accommodation", "ta_third_party",
            "ukraine_emergency_accommodation", "ta_lines_total", "of_which_named_hotels"]
    w.writerow(cols + ["note"])
    for k in sorted(agg):
        note = {"2019-20": "first full FY in holdings",
                "2025-26": "complete FY (holdings run to 2026-03)"}.get(k, "")
        w.writerow([k] + [round(agg[k][c]) for c in cols[1:]] + [note])

agg2 = defaultdict(lambda: [0, 0.0])
for ym, a in cur.execute("""SELECT year_month, amount FROM transactions
        WHERE is_dup=0 AND publisher='Home Office'
        AND (expense_type LIKE '%asylum%' OR expense_type LIKE '%refugee%')"""):
    k = fy(ym); agg2[k][0] += 1; agg2[k][1] += a or 0
NOTES = {
 "2016-17": "asylum-labeled lines fade after 2016-10: spend relabeled to Business Process Outsourcing / Detention Centres etc.",
 "2017-18": "label collapse, not a spending collapse: contractors still paid under generic labels",
 "2018-19": "Apr-Jun 2018 only; Home Office ledger in our holdings stops 2018-06",
}
with open("home_office_asylum_by_fy.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["fiscal_year", "n_payments", "amount_gbp", "note"])
    for k in sorted(agg2):
        w.writerow([k, agg2[k][0], round(agg2[k][1]), NOTES.get(k, "")])
print("done")
