"""England-wide real per-head arc for staff-heavy services from RO, 2013-14/2018-19/2024-25.
Staff-heavy picks: libraries, cultural, planning_development, street_cleansing, environmental_regulatory.
Measure: nce (net current expenditure), real terms. Aggregate = population-weighted (sum gbp_thousand real? --
we recompute England totals from nominal gbp_thousand * (real_gbp_per_head/gbp_per_head) deflator per row is unsafe
when gbp_per_head=0, so instead: England real total = sum over authorities of real_gbp_per_head*population; per-head
= that / sum population, restricted to rows with population>0.)"""
import csv
from collections import defaultdict

SRC = r"C:\Users\domin\Documents\Open Data\analysis\ro\ro_per_head.csv"
OUT = r"C:\Users\domin\Documents\Open Data\analysis\strands2\consultants\ro_staffheavy_arc.csv"

SERVICES = ["libraries", "cultural", "planning_development", "street_cleansing",
            "environmental_regulatory", "adult_social_care", "children_social_care",
            "total_service_expenditure"]

# corpus councils by RO name (hand-mapped; North Yorkshire appears as county then UA)
CORPUS_COUNCILS = {"Bristol", "Greenwich", "North Yorkshire", "Rushmoor", "South Gloucestershire",
                   "Uttlesford", "Plymouth", "Blaby", "Eden", "Cheltenham", "Richmond upon Thames",
                   "Harrogate"}

num = defaultdict(float)   # (year, service, group) -> sum real_gbp_per_head*pop
den = defaultdict(float)   # (year, service, group) -> sum pop
names_seen = set()
with open(SRC, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["measure"] != "nce" or r["service"] not in SERVICES:
            continue
        try:
            pop = float(r["population"]); real_ph = float(r["real_gbp_per_head"])
        except ValueError:
            continue
        if pop <= 0:
            continue
        key_all = (r["year"], r["service"], "england")
        num[key_all] += real_ph * pop; den[key_all] += pop
        if r["name"] in CORPUS_COUNCILS:
            names_seen.add(r["name"])
            k = (r["year"], r["service"], "corpus_councils")
            num[k] += real_ph * pop; den[k] += pop

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["year", "service", "group", "real_gbp_per_head", "real_total_gbp_m"])
    for k in sorted(num):
        w.writerow([k[0], k[1], k[2], round(num[k]/den[k], 2), round(num[k]/1e6, 1)])
print("corpus councils matched in RO:", sorted(names_seen))
print("written", OUT)
