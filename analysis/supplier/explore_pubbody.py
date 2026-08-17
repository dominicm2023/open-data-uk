# explore_pubbody.py — throwaway eyeballing tool for Q3.
# Token-net over normalised supplier names for public-body-shaped payees;
# prints top N by GBP for hand-review before 03_flows.py fixes the rules.
import sqlite3, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, "agg.db"))

DROP = {"LTD", "LIMITED", "PLC", "AND"}
_punct = re.compile(r"[^A-Z0-9 ]+")
def norm(s):
    s = _punct.sub(" ", s.upper())
    toks = [t for t in s.split() if t not in DROP]
    if toks and toks[0] == "THE":
        toks = toks[1:]
    return " ".join(toks)

TOKENS = re.compile(
    r"\bCOUNCIL\b|\bNHS\b|CONSTABULARY|POLICE|\bHMRC\b|HM REVENUE|INLAND REVENUE|"
    r"HM TREASURY|H M TREASURY|MINISTRY OF|DEPARTMENT FOR|DEPARTMENT OF|DEPT OF|DEPT FOR|"
    r"HOME OFFICE|CABINET OFFICE|FOREIGN COMMONWEALTH|ENVIRONMENT AGENCY|"
    r"FIRE RESCUE|FIRE AUTHORITY|FIRE SERVICE|AMBULANCE SERVICE|PRIMARY CARE TRUST|"
    r"FOUNDATION TRUST|HOSPITALS? TRUST|CLINICAL COMMISSIONING|INTEGRATED CARE BOARD|"
    r"\bICB\b|\bCCG\b|\bPCT\b|BOROUGH OF|CITY OF|COUNTY OF|CROWN PROSECUTION|"
    r"LEGAL AID AGENCY|DVLA|DVSA|DRIVER VEHICLE|HIGHWAYS ENGLAND|HIGHWAYS AGENCY|"
    r"NATIONAL HIGHWAYS|TRANSPORT FOR LONDON|NETWORK RAIL|HEALTH SECURITY AGENCY|"
    r"PUBLIC HEALTH ENGLAND|UK HEALTH|OFFICE FOR NATIONAL|ORDNANCE SURVEY|MET OFFICE|"
    r"LAND REGISTRY|COMPANIES HOUSE|VALUATION OFFICE|GREATER LONDON AUTHORITY|"
    r"WELSH GOVERNMENT|SCOTTISH GOVERNMENT|SCOTTISH MINISTERS|NORTHERN IRELAND (OFFICE|EXECUTIVE)|"
    r"COMBINED AUTHORITY|PENSION FUND|PARISH COUNCIL|TOWN COUNCIL|"
    r"COURT SERVICE|HMCTS|HM PRISON|HM COURTS|NATIONAL PROBATION|PROBATION SERVICE"
)

agg = defaultdict(lambda: [0, 0.0, set()])
for raw, pub, txns, gbp in con.execute("SELECT supplier_raw, publisher, txns, gbp FROM sp"):
    nn = norm(raw)
    if nn and TOKENS.search(nn):
        a = agg[nn]
        a[0] += txns; a[1] += gbp; a[2].add(pub)

rows = sorted(agg.items(), key=lambda kv: -kv[1][1])
print(f"{len(rows)} normalised public-body-shaped names, GBP {sum(v[1] for _,v in rows):,.0f}")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 250
for nn, (txns, gbp, pubs) in rows[:n]:
    print(f"  {len(pubs):>2}pub {txns:>8}tx {gbp:>18,.0f}  {nn[:90]}")
