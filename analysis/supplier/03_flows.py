# 03_flows.py — Q3: public-body-to-public-body flows.
# Scope: UK CORE public bodies as payees — central departments, local government,
# NHS bodies (incl. state-owned NHS companies), police/fire, national agencies,
# LGPS pension funds, UK NDPBs (British Council, research councils, funding
# councils). DELIBERATELY OUT of scope, stated in the report:
#   - schools, academies, colleges, universities (DfE's academy grants are a
#     known structure; token-matching would catch them only patchily and mislead)
#   - foreign governments (DFID/FCDO grants to overseas ministries)
#   - fee-funded professional regulators (GMC, HCPC, NMC...) — borderline
#   - charities/associations with "council" in the name
# Every included normalised name >= GBP 1M was eyeballed (explore_pubbody.py);
# the tail below 1M is rule-matched only and its aggregate GBP is reported as
# the bounded residual risk.
import sqlite3, os, re, csv, json
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, "agg.db"))

DROP = {"LTD", "LIMITED", "PLC", "AND"}
_punct = re.compile(r"[^A-Z0-9 ]+")
def norm(s):
    s = _punct.sub(" ", s.upper())
    t = [x for x in s.split() if x not in DROP]
    if t and t[0] == "THE":
        t = t[1:]
    return " ".join(t)

TOKENS = re.compile(
    r"\bCOUNCIL\b|\bNHS\b|CONSTABULARY|POLICE|\bHMRC\b|HM REVENUE|INLAND REVENUE|"
    r"HM TREASURY|H M TREASURY|MINISTRY OF|DEPARTMENT FOR|DEPARTMENT OF|DEPT OF|DEPT FOR|"
    r"HOME OFFICE|CABINET OFFICE|FOREIGN COMMONWEALTH|ENVIRONMENT AGENCY|"
    r"FIRE RESCUE|FIRE AUTHORITY|FIRE SERVICE|AMBULANCE SERVICE|PRIMARY CARE TRUST|"
    r"FOUNDATION TRUST|HOSPITALS? TRUST|CLINICAL COMMISSIONING|INTEGRATED CARE BOARD|"
    r"\bICB\b|\bCCG\b|\bPCT\b|BOROUGH OF|CITY OF|CROWN PROSECUTION|"
    r"LEGAL AID AGENCY|\bDVLA\b|\bDVSA\b|DRIVER VEHICLE|HIGHWAYS ENGLAND|HIGHWAYS AGENCY|"
    r"NATIONAL HIGHWAYS|TRANSPORT FOR LONDON|NETWORK RAIL|HEALTH SECURITY AGENCY|"
    r"PUBLIC HEALTH ENGLAND|OFFICE FOR NATIONAL|ORDNANCE SURVEY|MET OFFICE|"
    r"LAND REGISTRY|COMPANIES HOUSE|VALUATION OFFICE|GREATER LONDON AUTHORITY|"
    r"WELSH GOVERNMENT|SCOTTISH GOVERNMENT|SCOTTISH MINISTERS|NORTHERN IRELAND (OFFICE|EXECUTIVE)|"
    r"COMBINED AUTHORITY|PENSION FUND|PARISH COUNCIL|TOWN COUNCIL|"
    r"COURT SERVICE|\bHMCTS\b|HM PRISON|HM COURTS|NATIONAL PROBATION|PROBATION SERVICE|"
    r"\bMBC\b|\bMDC\b|\bLBC\b|^LB |^RB |WEST NORTHAMPTONSHIRE UDC"
)

# Exact normalised names the abbreviation tokens (MBC/MDC/LB/RB) catch that are
# NOT councils — from eyeballing the full 143-name abbreviation-matched list.
EXPLICIT_EXCLUDE = {
    "MBC BUILDING CONTRACTOR NW", "MODEL BOOT CAMP MBC", "MBC PROMOTIONS",
    "MDC LEISURE", "LB HOTINVEST", "LB PROPAGANDA E PRODUC",
    "LB RESTORATION SERVICES", "LB INTERNATIONAL GROUP", "RB CONFECCOES",
    "RB ARCHITECTURAL", "RB EXPORT COMPANY", "RB EQUESTRIAN",
    "RB HEALTH SAFETY SOLUTIONS", "RB SAN DIEGO", "RB PERFORMANCE",
}

# Include-first overrides (checked before any exclusion)
FORCE_INCLUDE = re.compile(
    r"BRITISH COUNCIL|LEARNING SKILLS COUNCIL|SCOTTISH FUNDING COUNCIL|"
    r"HIGHER EDUCATION FUNDING COUNCIL|RESEARCH COUNCIL|UKRI|"
    r"UNIVERSITY HOSPITAL|COUNCIL OF RESERVE FORCES"
)

EXCLUDE = [
    # schools / colleges / academies / HE — out of scope
    (re.compile(r"ACADEM|SCHOOL|COLLEGE|SIXTH FORM|UNIVERSITY"), "education institution (out of scope)"),
    # foreign governments and bodies
    (re.compile(r"ETHIOPIA|MOZAM|VIETNAM|\bSRV\b|ITALY|GREECE|NETHERLANDS|RWANDA|MALAWI|"
                r"TANZANIA|JAMAICA|GHANA|KENYA|UGANDA|AFGHANISTAN|AUSTRIA|SWITZERLAND|"
                r"GIBRALTAR|CYPRUS|SWEDEN|LUXEMBOURG|CHINA|OTTAWA|NEW YORK|EUROPEAN UNION|"
                r"NORWEGIAN|SOMALIA|NIGERIA|\bNIG\b|PARASTATAL|ATLANTIC COUNCIL|ZAMBIA|NEPAL|"
                r"PAKISTAN|BANGLADESH|SIERRA LEONE|LIBERIA|ZIMBABWE|SUDAN|YEMEN|IRAQ|INDIA\b|"
                r"DEVELOPMENT RESEARCH CENTER"), "foreign government/body"),
    (re.compile(r"MINISTRY OF (?!DEFENCE|JUSTICE|HOUSING)"), "non-UK ministry naming (UK has Defence/Justice/Housing)"),
    # charities, associations, church, clubs
    (re.compile(r"VOLUNTARY|REFUGEE COUNCIL|YOUTH COUNCIL|PALLIATIVE|RESTORATIVE JUSTICE|"
                r"FASHION COUNCIL|SPORTS COUNCIL|DIOCES|CATHOLIC|CHURCH|TRAINING COUNCIL|"
                r"FINANCIAL SERVICES SKILLS COUNCIL|COUNCIL FOR DISABLED|CYBER SECURITY COUNCIL|"
                r"CHARIT"), "charity/association/church"),
    # fee-funded professional regulators — borderline, excluded
    (re.compile(r"GENERAL (MEDICAL|DENTAL|OPTICAL|OSTEOPATHIC|CHIROPRACTIC|PHARMACEUTICAL|TEACHING) COUNCIL|"
                r"NURSING MIDWIFERY COUNCIL|HEALTH CARE PROFESSIONS COUNCIL|"
                r"HEALTHCARE REGULATORY|FINANCIAL REPORTING COUNCIL"), "fee-funded regulator (borderline, excluded)"),
    # private ambulance / police-adjacent private
    (re.compile(r"ELITE MEDICAL|MEDI4|F A S T AMBULANCE|KENT CENTRAL AMBULANCE|AIR AMBULANCE|"
                r"AMBULANCE SERVICES? CHARITY"), "private/charity ambulance"),
    (re.compile(r"POLICE (MUTUAL|FEDERATION|TREATMENT|RESOURCES|REHAB)|POLICE ICT"), "police-adjacent non-state body"),
    # private pension funds seen in eyeball
    (re.compile(r"SHELL|SATURNIA"), "private pension fund"),
    # payee-unclear specials (same judgements as Q1)
    (re.compile(r"^PWC LLP HMRC|NATWEST INTERNAL HMRC|^CSR HMRC$|GBSRE ADMIN HMRC|"
                r"GOMA HMRCAZ|^INLAND REVENUE DEPARTMENT$|^SSCL ENVIRONMENT AGENCY$|"
                r"^CITY OF GLASGOW$"), "payee unclear / ambiguous"),
]

def classify(nn):
    if not TOKENS.search(nn):
        return None, None
    if nn in EXPLICIT_EXCLUDE:
        return False, "abbreviation false positive (eyeballed)"
    if FORCE_INCLUDE.search(nn):
        return True, None
    for rex, reason in EXCLUDE:
        if rex.search(nn):
            return False, reason
    return True, None

def main():
    # DHSC mega-transfers (two single payments to HM Treasury) — find exactly
    cor = sqlite3.connect(os.path.join(HERE, "..", "spending", "corpus.db"))
    mega = cor.execute("""
        SELECT publisher, supplier_raw, date, amount FROM transactions
        WHERE is_dup=0 AND publisher LIKE '%Health and Social Care%'
          AND amount > 2e10 ORDER BY amount DESC LIMIT 2""").fetchall()
    mega_total = sum(m[3] for m in mega)
    print("DHSC mega-transfers (reported separately, excluded from shares):")
    for m in mega:
        print(f"  {m[2]}  {m[3]:>20,.2f}  |{m[1]}|  ({m[0]})")
    cor.close()

    flows = defaultdict(lambda: [0, 0.0])       # (publisher, to_norm) -> [txns, gbp]
    pub_total = defaultdict(float)
    pub_pb = defaultdict(float)
    excluded_gbp = defaultdict(float)
    included_names = {}
    for raw, pub, txns, gbp in con.execute("SELECT supplier_raw, publisher, txns, gbp FROM sp"):
        pub_total[pub] += gbp
        nn = norm(raw)
        if not nn:
            continue
        ok, reason = classify(nn)
        if ok:
            f = flows[(pub, nn)]
            f[0] += txns; f[1] += gbp
            pub_pb[pub] += gbp
            included_names[nn] = included_names.get(nn, 0.0) + gbp
        elif ok is False:
            excluded_gbp[reason] += gbp

    # adjust DHSC for the two mega-transfers (they are HM TREASURY rows, included above)
    dhsc = [p for p in pub_total if "Health and Social Care" in p]
    dhsc_name = dhsc[0] if dhsc else None
    if dhsc_name:
        pub_total[dhsc_name] -= mega_total
        pub_pb[dhsc_name] -= mega_total
        for (pub, nn), f in flows.items():
            if pub == dhsc_name and nn.startswith("HM TREASURY"):
                f[1] -= mega_total   # both rows carry supplier 'HM TREASURY (HMT)'
                break

    with open(os.path.join(HERE, "flows.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["from_publisher", "to_body_normalised", "gbp", "transactions", "self_flag"])
        for (pub, nn), (txns, gbp) in sorted(flows.items(), key=lambda kv: -kv[1][1]):
            self_flag = 1 if (norm(pub) and (norm(pub) in nn or nn in norm(pub))) else 0
            w.writerow([pub, nn, round(gbp, 2), txns, self_flag])

    shares = sorted(
        ((p, pub_total[p], pub_pb.get(p, 0.0)) for p in pub_total if pub_total[p] > 0),
        key=lambda x: -(x[2] / x[1] if x[1] else 0))
    print(f"\nflows: {len(flows):,} publisher->body pairs, {len(included_names):,} bodies")
    print(f"total to public bodies (excl. DHSC mega): GBP {sum(pub_pb.values()):,.0f}")
    print(f"\n{'publisher':58} {'share':>6} {'pb_gbp':>16} {'total_gbp':>17}")
    for p, tot, pb in shares:
        if tot >= 1e8:
            print(f"{p[:58]:58} {pb/tot:6.1%} {pb:>16,.0f} {tot:>17,.0f}")
    print("\nexcluded-by-rule GBP:")
    for r, g in sorted(excluded_gbp.items(), key=lambda kv: -kv[1]):
        print(f"  {g:>16,.0f}  {r}")
    small = sum(g for n, g in included_names.items() if g < 1e6)
    print(f"\nresidual risk: included names under GBP 1M each (rule-matched, not eyeballed): "
          f"{sum(1 for n,g in included_names.items() if g<1e6):,} names, GBP {small:,.0f}")

    json.dump({
        "mega_transfers": [{"publisher": m[0], "supplier_raw": m[1], "date": m[2], "amount": m[3]} for m in mega],
        "pairs": len(flows), "bodies": len(included_names),
        "gbp_to_public_bodies_excl_mega": round(sum(pub_pb.values()), 2),
        "publisher_shares": [{"publisher": p, "total_gbp": round(t, 2), "public_body_gbp": round(pb, 2),
                              "share": round(pb / t, 4) if t else None} for p, t, pb in shares],
        "excluded_by_rule_gbp": {k: round(v, 2) for k, v in excluded_gbp.items()},
        "residual_unreviewed_tail_gbp": round(small, 2),
    }, open(os.path.join(HERE, "flows_summary.json"), "w", encoding="utf-8"), indent=2)

if __name__ == "__main__":
    main()
