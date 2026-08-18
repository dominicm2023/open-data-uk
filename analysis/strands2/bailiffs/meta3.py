import csv
from collections import defaultdict
d = defaultdict(lambda: [0, 0.0, "9999", "0000"])
with open(r"C:\Users\domin\Documents\Open Data\analysis\strands2\bailiffs\central_debt_context.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["publisher"] in ("HM Revenue and Customs", "Department for Work and Pensions",
                              "Ministry of Justice", "Department of Health and Social Care"):
            k = (r["group"], r["publisher"])
            d[k][0] += int(r["txns"]); d[k][1] += float(r["gbp"])
            d[k][2] = min(d[k][2], r["year"] or "9999"); d[k][3] = max(d[k][3], r["year"] or "0000")
for (g, p), (t, s, a, b) in sorted(d.items(), key=lambda kv: -kv[1][1]):
    print(f"{g:35s} {p:45s} {t:5d} txns  £{s:>15,.2f}  {a}-{b}")
