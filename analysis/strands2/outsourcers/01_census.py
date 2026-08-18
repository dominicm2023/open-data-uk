# 01_census.py — THE OUTSOURCED STATE: name-variant census of the big outsourcing firms.
# Method inherited from ../../supplier/01_variant_census.py: a deliberately BROAD
# regex net per firm over distinct supplier_raw strings (agg.db), then an EXPLICIT
# exclusion list of exact strings the net caught that are NOT the firm. Every
# matched string was eyeballed (00_eyeball_dump.py output, 2026-08-18). Exclusions
# are subtracted from the net, so any NEW string after a corpus rebuild lands in
# "included" and shows up for re-eyeballing.
#
# Grouping rule (inherited): a "firm" is the corporate group — subsidiaries and
# divisions in, joint ventures OUT (excluded and listed). Two JVs are so large
# and so central to this story that they are censused as their OWN flagged lines
# rather than silently dropped: CarillionAmey (the MoD housing-maintenance JV,
# GBP 1.2bn) and CarillionEnterprise (the earlier MoD prime-contract JV). SSCL
# (Sopra Steria's shared-services JV with the Cabinet Office) likewise.
# Capita/Serco/G4S nets and exclusions are inherited verbatim from the supplier
# census (already eyeballed there); the TP NATWEST/HSBC teachers'-pension
# pass-through stays OUT of Capita.
import sqlite3, os, re, csv, json

HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, "..", "..", "supplier", "agg.db"))

COMPANIES = {
    "Capita": {
        "net": r"\bCAPITA\b",
        "note": "Capita plc group: Business Services, Resourcing/Veredus, Symonds, IB Solutions, Secure Information, IT Services, Pay360, Hartshead, Gwent, Health, Travel & Events, Employee Benefits, Life & Pensions, Pension Solutions, Treasury Solutions, Translation & Interpreting. Excludes the teachers'-pension pass-through accounts (GBP 35.86bn) per the known trap.",
        "exclude": {
            "CAPITA TP NATWEST": "pass-through: DfE 'funding to pay Teachers' Pensions' routed via Capita's third-party bank account (GBP 35.6bn — not payments TO Capita)",
            "CAPITA TP HSBC": "same pass-through, HSBC account (GBP 246.5m)",
            "THE DEANERY CHURCH OF ENGLAND HIGH GOVERNORS CAPITA": "school governors' account administered by Capita; beneficiary is the school",
            "THE DEANERY C OF E HIGH GOVERNORS CAPITA": "same",
            "Capita Consortium Nominees No 1 & No 2 Ltd": "nominee vehicle, beneficial recipient unclear",
        },
    },
    "Serco": {
        "net": r"SERCO",
        "note": "Serco Group plc: Ltd/Limited, Public Services, Assurance, Justice, Regional Services, Listening, Holdings, Leisure, Defence Science, Consulting, Integrated Services, Shared Service Centre.",
        "exclude": {
            "Hanoi Toserco": "Hanoi Tourist Service Company, Vietnam",
            "PHONG VE HANOI TOSERCO": "same",
            "HANOI TOSERCO": "same",
            "HANOI TOSERCO 1": "same",
            "HANOI TOSERCO-MOTO": "same",
            "CORPORACION SERCOPLUS": "Peruvian IT retailer",
            "SERCORIEGO": "unrelated card line",
            "SERCO PROJECTS LLC": "presents as a distinct LLC we could not verify as Serco Group",
        },
    },
    "G4S": {
        "net": r"G4S|GROUP 4",
        "note": "G4S group incl. overseas subsidiaries (Kenya, DRC, Uganda, Ghana, Jordan, Botswana...) and predecessor Group 4 Securicor.",
        "exclude": {
            "WAYNE LLEWELLYN T/A FRIENDS OF BOXING4SCHOOLS": "'boxing4schools' substring hit",
            "FRIENDS OF BOXING4SCHOOLS": "same",
            "AMAZON.CO.UK 2X58G4SO4": "Amazon order reference containing G4S",
            "Group 4": "bare string, could be anything",
        },
    },
    "Mitie": {
        "net": r"MITIE",
        "note": "Mitie Group plc: FM, Security, Care & Custody, Justice, Technical FM, Managed Services, Catering, Cleaning & Environmental, Property Services, Tilley Roofing, Pest Control, Engineering, Landscapes, Utilyx t/a Mitie Energy. No exclusions needed — every netted string is the company.",
        "exclude": {},
    },
    "Sodexo": {
        "net": r"SODEXH?O",
        "note": "Sodexo group incl. pre-2008 spelling Sodexho: Ltd, Pass (voucher arm), Motivation Solutions, Prestige, Defence Services, Property Solutions, Education Services, Cyprus/Norway/embassy card lines. No exclusions needed.",
        "exclude": {},
    },
    "Amey": {
        "net": r"AMEY",
        "note": "Amey plc (Ferrovial-owned to 2022): Community, LG, Defence Services (the post-CarillionAmey MoD contracts), Rail, OW, Metering, MAP Services, plc. JVs excluded and listed: Keolis Amey (Metrolink/DLR, Keolis-led), GEOAmey (prisoner escort), CarillionAmey (censused as its own line).",
        "exclude": {
            "KEOLIS AMEY METROLINK LTD": "JV, Keolis-led (70:30), Manchester Metrolink operator — GBP 693.8m, listed not censused",
            "Keolis Amey Metrolink Ltd": "same JV",
            "KEOLIS AMEY DOCKLANDS LIMITED": "JV, Keolis-led, DLR operator",
            "GEO AMEY PECS LTD": "GEOAmey: 50:50 JV with GEO Group (prisoner escort & custody) — GBP 93.2m, listed not censused",
            "CARILLIONAMEY LIMITED": "censused separately as CarillionAmey (JV)",
            "CARILLIONAMEY (HOUSING PRIME) LIMITED": "censused separately as CarillionAmey (JV)",
            "AMEYZOO": "exotic-pet zoo in Bovingdon, not Amey plc",
        },
    },
    "Interserve": {
        "net": r"INTERSERVE",
        "note": "Interserve group: (Defence), FM/Facilities Management, Construction, Project Services, Working Futures, Learning & Employment, FS (UK), Site Services, Healthcare, Engineering Services.",
        "exclude": {
            "Interserve Academies Trust": "academy trust sponsored by the firm; beneficiary is schools, not the company",
            "INTERSERVE ACADEMIES TRUST": "same",
        },
    },
    "Kier": {
        "net": r"\bKIER\b",
        "note": "Kier Group plc: Regional, Construction (all regions), Services/Maintenance, Facilities Services, Building Services/Maintenance, Highways, Transportation, Integrated Services, Infrastructure & Overseas, Business Services, Property Developments, MG (ex May Gurney), Living, Wallis (Kier Group subsidiary).",
        "exclude": {
            "Kier Graham Defence Limited": "JV with John Graham Construction (DIO estate works) — GBP 52.2m, listed not censused",
            "KIER FOUNDATION": "the firm's charity, not the trading company",
            "Kier Charles Property Services Ltd": "presents as a person-named local firm we could not verify as Kier Group",
        },
    },
    "Sopra Steria": {
        "net": r"SOPRA|STERIA",
        "note": "Sopra Steria group incl. predecessors Steria (merged 2014) and Sopra Group, plus Sopra Steria Recruitment. SSCL, its majority-owned shared-services JV with the Cabinet Office, is censused as its own flagged line.",
        "exclude": {
            "Wisteria House Dementia Care Ltd": "'Wisteria' substring hit — care home",
            "Wisteria House": "same",
            "CATCAKES REPOSTERIA CR": "Spanish 'reposteria' (bakery) card line",
            "FLORISTERIA SIEMPRE VE": "Spanish florist card line",
            "FLORISTERIA DON ELOY": "same",
            "FLORISTERIA INES-28, C": "same",
            "OSTERIA PANEVINO": "Italian restaurant card line",
            "OSTERIA A LE DUE SPADE": "same",
            "PAYPAL  SOPRANO": "'Soprano' substring hit on a PayPal card line",
            "National Offender Management Services (Steria)": "compound label, payee unclear (NOMS' Steria-run shared services)",
        },
    },
    "SSCL (Sopra Steria JV)": {
        "net": r"SSCL|SHARED SERVICES CONNECTED",
        "note": "Shared Services Connected Ltd: Sopra Steria's majority-owned JV with the Cabinet Office, running back-office for DWP/Home Office/MoJ etc. Flagged as a JV line, not merged into Sopra Steria proper. Accounts-receivable and on-behalf labels excluded: money through those lines is owed to the client department, not SSCL.",
        "exclude": {
            "SSCL - ACCOUNTS RECEIVABLE": "AR account label: paying an invoice SSCL raised on behalf of a client department; beneficiary is the department",
            "SSCL ACCOUNTS RECEIVABLE TEAM": "same",
            "CABINET OFFICE SSCL ACCOUNTS RECEIVABLE": "same",
            "SSCL - Accounts Receivable": "same",
            "SSCL on behalf of Cabinet Office": "explicit on-behalf label; beneficiary is the Cabinet Office",
            "HOME OFFICE SSCL": "compound label, payee unclear",
            "SSCL (ENVIRONMENT AGENCY)": "compound label, payee unclear",
        },
    },
    "Liberata": {
        "net": r"LIBERATA",
        "note": "Liberata UK Ltd incl. t/a Trinity Services and t/a CapacityGrid.",
        "exclude": {
            "MOJ LIBERATA": "compound label (TNA paying the MoJ's Liberata-run service), payee unclear",
            "HM Courts Service (Liberata UK Ltd)": "payee presents as HM Courts Service; Liberata is only the operator",
            "HM COURTS SERVICE (LIBERATA UK LTD)": "same",
        },
    },
    "Veolia": {
        "net": r"VEOLIA|\bONYX\b",
        "note": "Veolia group: ES (UK)/Environmental Services, Energy & Utility Services, CHP, Resource Efficiency, Water (incl. Nevis and Outsourcing SPVs for MoD's Project Aquatrine), Water Technologies/VWS, overseas lines. Predecessor brand Onyx netted, zero strings found (null). No exclusions needed.",
        "exclude": {},
    },
    "Biffa": {
        "net": r"BIFFA",
        "note": "Biffa Waste Services. No exclusions needed.",
        "exclude": {},
    },
    "Suez": {
        "net": r"\bSUEZ\b|\bSITA\b",
        "note": "Suez recycling & recovery UK incl. predecessor SITA UK (renamed 2016) and SITA Holdings UK. NOT GDF Suez: the energy group (now Engie) has been a separate listed company from Suez's waste business since 2008 — all GDF Suez strings excluded. SITA the airline-IT firm is the other trap: the bare string 'SITA' is excluded as unverifiable.",
        "exclude": {
            "Cofely GDF Suez": "GDF Suez = energy group (now Engie), separate from the Suez waste company since 2008",
            "GDF SUEZ SALES LTD (GAS)": "same — gas supply",
            "ELECTRABEL GDF SUEZ": "same — Belgian energy arm",
            "GDF SUEZ MARKETING LIMITED": "same",
            "GDF SUEZ": "same",
            "Suez Canal Authority": "the Egyptian state canal authority",
            "Sita Trust": "landfill communities fund charity, not the operating company",
            "SITA": "bare string: could be SITA the airline-IT company; unverifiable",
        },
    },
    "Carillion": {
        "net": r"CARILLION|\bEAGA\b|PLANNED MAINTENANCE ENGINEERING",
        "note": "Carillion plc group: Construction (incl. 'in liquidation' tail lines), plc, AMBS t/a CPM, JM (ex Mowlem), Services/Services 2006, Planned Maintenance (incl. legal entity Planned Maintenance Engineering Ltd, Carillion-owned since the 2006 Mowlem acquisition), Maple Oak, Regeneration, Advice Services, Highway Maintenance, Rail. JVs censused separately or listed: CarillionAmey, CarillionEnterprise, CarillionAramark, Carillion Alawi, Al Futtaim Carillion.",
        "exclude": {
            "CARILLIONAMEY LIMITED": "censused separately as CarillionAmey (JV)",
            "CARILLIONAMEY (HOUSING PRIME) LIMITED": "censused separately as CarillionAmey (JV)",
            "CARILLIONENTERPRISE LIMITED": "censused separately as CarillionEnterprise (JV)",
            "CARILLION ENTERPRISE LIMITED": "censused separately as CarillionEnterprise (JV)",
            "CARILLION ENTERPRISE LTD": "censused separately as CarillionEnterprise (JV)",
            "Carillion Enterprise Ltd": "censused separately as CarillionEnterprise (JV)",
            "CARILLIONARAMARK LIMITED": "JV with Aramark (defence catering) — GBP 5.2m, listed not censused",
            "CARILLION ALAWI LLC": "Oman JV",
            "AL FUTTAIM CARILLION LLC": "Dubai JV",
            "CARILLION AS AGENT FOR STOCKPORT MB": "agent label: beneficiary is Stockport MBC works, payee role unclear",
            "CARILLION ACADEMIES TRUST": "academy trust sponsored by the firm; beneficiary is schools",
            "eaga plc Switchover Help Scheme": "eaga: payment at/before Carillion's April 2011 acquisition completed; ownership at payment date unverifiable",
            "Eaga Heating Services Limited": "same — payments start Dec 2010, pre-acquisition",
        },
    },
    "CarillionAmey (JV)": {
        "net": r"CARILLIONAMEY",
        "note": "CarillionAmey Ltd: the 50:50 Carillion/Amey JV holding the MoD National Housing Prime and regional FM contracts 2014-2018. Censused as its own flagged line — its GBP 1.2bn belongs to neither parent alone, and its curve IS the Carillion collapse story in this corpus.",
        "exclude": {},
    },
    "CarillionEnterprise (JV)": {
        "net": r"CARILLION\s*ENTERPRISE",
        "note": "CarillionEnterprise Ltd: Carillion/Enterprise plc JV holding MoD Regional Prime contracts to 2014, predecessor of the CarillionAmey arrangement.",
        "exclude": {},
    },
}

def main():
    rows_out, summary, ambiguities = [], [], []
    included_by_company = {}
    for company, spec in COMPANIES.items():
        pat = re.compile(spec["net"], re.I)
        matched = [r for r in con.execute("SELECT supplier_raw, publishers, txns, gbp FROM s").fetchall() if pat.search(r[0])]
        excl = spec["exclude"]
        matched_names = {m[0] for m in matched}
        for e in excl:
            if e not in matched_names:
                print(f"WARN: exclusion not matched by net for {company}: |{e}|")
        inc = [m for m in matched if m[0] not in excl]
        exc = [m for m in matched if m[0] in excl]
        included_by_company[company] = {m[0] for m in inc}
        names = [m[0] for m in inc]
        pubs = set()
        for i in range(0, len(names), 500):
            chunk = names[i:i+500]
            q = ",".join("?" * len(chunk))
            pubs |= {r[0] for r in con.execute(f"SELECT DISTINCT publisher FROM sp WHERE supplier_raw IN ({q})", chunk)}
        gbp = sum(m[3] for m in inc); txns = sum(m[2] for m in inc)
        summary.append({
            "company": company, "variants": len(inc), "publishers": len(pubs),
            "txns": txns, "gbp": round(gbp, 2), "note": spec["note"],
            "excluded": [{"string": m[0], "gbp": round(m[3], 2), "reason": excl[m[0]]} for m in sorted(exc, key=lambda x: -x[3])],
        })
        for m in sorted(inc, key=lambda x: -x[3]):
            rows_out.append([company, m[0], m[1], m[2], round(m[3], 2)])
        for m in exc:
            ambiguities.append([company, m[0], round(m[3], 2), excl[m[0]]])

    # overlap guard: no string may be INCLUDED under two companies
    seen = {}
    for c, names in included_by_company.items():
        for n in names:
            if n in seen:
                print(f"OVERLAP: |{n}| included under both {seen[n]} and {c}")
            seen[n] = c

    with open(os.path.join(HERE, "variants.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "variant", "publishers", "txns", "gbp"]); w.writerows(rows_out)
    with open(os.path.join(HERE, "variants_excluded.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "string", "gbp", "reason"]); w.writerows(ambiguities)
    with open(os.path.join(HERE, "census_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"{'company':28} {'variants':>8} {'pubs':>5} {'txns':>9} {'gbp':>20}")
    for s in sorted(summary, key=lambda x: -x["gbp"]):
        print(f"{s['company']:28} {s['variants']:>8} {s['publishers']:>5} {s['txns']:>9,} {s['gbp']:>20,.2f}")
    print(f"\ntotals: {sum(s['variants'] for s in summary)} included variant strings, {len(ambiguities)} excluded strings")

if __name__ == "__main__":
    main()
