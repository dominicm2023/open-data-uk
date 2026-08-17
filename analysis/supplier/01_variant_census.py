# 01_variant_census.py — Q1: the name-variant census.
# Method: per company, a deliberately BROAD regex net over distinct supplier_raw
# strings (agg.db, built by 00_build_agg.py), then an EXPLICIT exclusion list of
# exact strings that the net caught but that are NOT the company. Every matched
# string was eyeballed (explore_variants.py output, 2026-08-17); exclusions and
# the reason for each are recorded below and surfaced in findings.json so the
# judgement calls are auditable. A string the net catches that is in neither the
# include set nor the exclusion list cannot exist by construction (exclusions are
# subtracted from the net), so the census fails loudly if the corpus changes:
# any NEW string the net catches after a rebuild lands in "included" and shows up
# in variants.csv for re-eyeballing.
#
# Grouping rule: a "company" is the corporate group (subsidiaries and divisions
# included: BT Global Services under BT, G4S Kenya under G4S). Joint ventures,
# predecessor-lookalikes we could not verify, and pass-through payment accounts
# are EXCLUDED and listed. Virgin is split: only Virgin Media (incl. Virgin
# Media O2) is censused; every other Virgin company is listed as an ambiguity.
import sqlite3, os, re, csv, json

HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, "agg.db"))

COMPANIES = {
    "BT Group": {
        "net": r"\bB\.?T\b|BRITISH TELECOM",
        "note": "Includes BT plc, Openreach, BT Global Services, Syntegra, Redcare, Engage IT, Business Direct, EE excluded (not matched by net).",
        "exclude": {
            # not BT at all
            "MAKRO MACHELEN BT WINK": "Belgian cash-and-carry card line, BT is a ref fragment",
            "MAKRO MACHELEN BT WIN": "same",
            "B.T.L.-BELMOPAN": "Belize Telemedia, Belmopan",
            "B.T.L. BELMOPAN": "same",
            "B.T.U. (Maintenance) Ltd.": "unrelated maintenance firm",
            "MECHANICAL QUALITY BT.": "unrelated",
            "BT MACFARLANE LTD": "unrelated (initials)",
            "BT PHILIPPE LIQUORS-N": "unrelated card line",
            "BT MARINE PROPELLERS LTD": "unrelated",
            "PAYPAL KOBOL BT": "PayPal line, BT = Hungarian company suffix (Bt.)",
            "BT MAKEDONIJA": "Beogradska?/Balkan card line, not BT plc",
            "BT WAREHOUSE WINES SP": "unrelated card line",
            "BT Academy Riding school": "riding school",
            "BT DONALD": "person's initials",
            # ambiguous / not a supplier name
            "Reverse duplicated transaction - see also BT 10032177 - MHCLG coronavirus hardship fund": "note field pasted into supplier column",
            "BT DISCLOSURE SCOTLAND": "card line, payee is Disclosure Scotland",
            "BT PAY BY PHONE          GATESHEAD NEW": "pay-by-phone parking line, payee unclear",
            "BT CETFW37YW": "card fragment, identity unverifiable",
            # BT Al-Saudia: joint venture, not a BT Group subsidiary
            "BT Al Saudia": "JV, excluded per grouping rule",
            "BRITISH TELECOM AL-SAUDIA LTD.": "JV",
            "British Telecom Al-Saudia Ltd.": "JV",
            "British Telecom Al Saudia Ltd": "JV",
            "British Telecom Al-Saudi Ltd.": "JV",
            "BT AL SAUDIA": "JV",
            "BT AL SUADIA": "JV",
            "BT Al-Saudia": "JV",
            "BT AL-SAUDIA LTD.": "JV",
        },
    },
    "Royal Mail": {
        "net": r"ROYAL\s*MAIL|ROYALMAIL",
        "note": "Royal Mail Group incl. Wholesale, Holdings, Retail, online shop card lines.",
        "exclude": {
            "Royal Mail Courier Services Ltd": "presents as a distinct legal entity we could not verify as Royal Mail Group",
        },
    },
    "EDF Energy": {
        "net": r"\bEDF\b|EDF ENERGY",
        "note": "EDF Energy group incl. Customers, Networks, Trading, R&D, Nuclear Generation.",
        "exclude": {
            "EUROPEAN COMMISSION (EDF)": "EDF = European Development Fund, not the utility (GBP 3.17bn — the acronym trap, reported separately)",
        },
    },
    "British Gas / Centrica": {
        "net": r"BRITISH\s*GAS|CENTRICA",
        "note": "Centrica group incl. British Gas Trading/Services/Business, PH Jones. Corona Energy deliberately NOT in the net: it is Macquarie-owned, not Centrica (an early draft of this census wrongly netted it).",
        "exclude": {
            "SOCIETY OF BRITISH GAS INDUSTRIES (SBGI)": "trade association, not the company",
        },
    },
    "Capita": {
        "net": r"\bCAPITA\b",
        "note": "Capita plc group incl. Business Services, Resourcing, Symonds, Veredus, Pay360, Hartshead, Gwent.",
        "exclude": {
            "CAPITA TP NATWEST": "pass-through: DfE 'funding to pay Teachers' Pensions' routed via Capita's third-party bank account (GBP 35.6bn — reported separately, not payments TO Capita)",
            "CAPITA TP HSBC": "same pass-through, HSBC account (GBP 246.5m)",
            "THE DEANERY CHURCH OF ENGLAND HIGH GOVERNORS CAPITA": "school governors' account administered by Capita; beneficiary is the school",
            "THE DEANERY C OF E HIGH GOVERNORS CAPITA": "same",
            "Capita Consortium Nominees No 1 & No 2 Ltd": "nominee vehicle, beneficial recipient unclear",
        },
    },
    "Serco": {
        "net": r"SERCO",
        "note": "Serco Group plc incl. Assurance, Regional Services, Listening, Leisure, Defence Science.",
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
        "note": "G4S group incl. overseas subsidiaries (Kenya, DRC, Uganda, Ghana, Jordan...) and predecessor Group 4 Securicor.",
        "exclude": {
            "WAYNE LLEWELLYN T/A FRIENDS OF BOXING4SCHOOLS": "'boxing4schools' substring hit",
            "FRIENDS OF BOXING4SCHOOLS": "same",
            "AMAZON.CO.UK 2X58G4SO4": "Amazon order reference containing G4S",
            "Group 4": "bare string, could be anything",
        },
    },
    "Virgin Media": {
        "net": r"VIRGIN\s*MEDIA",
        "note": "Virgin Media only (incl. Payments, Business, O2 merged entity). ALL other Virgin companies are separate businesses and are excluded by construction — see ambiguities.",
        "exclude": {},
    },
    "Microsoft": {
        "net": r"MICROSOFT|MICROSFT|MICOSOFT|MSFT",
        "note": "Microsoft Corp/Ltd/Ireland incl. invoice-suffixed card lines (Microsoft-G0...) and Microsoft Store.",
        "exclude": {
            "DRI MICROSOFT": "merchant of record is Digital River, not Microsoft",
            "DRI MICROSOFT O": "same",
            "SENTILLION/MICROSOFT": "acquired company; payment may predate acquisition, unverifiable",
        },
    },
    "Amazon (incl. AWS)": {
        "net": r"AMAZON|\bAWS\b|AMZN",
        "note": "Amazon group: AWS, retail, Marketplace, Business, Pay, and hundreds of card-statement lines with per-order references.",
        "exclude": {
            "AWS BATHROOM SUPPLIES LTD": "bathroom supplier",
            "Amazon Public Relations": "identity unverifiable (could be a PR firm named Amazon)",
            "Amazon-EcoMedia Ltd": "unrelated company",
            "IN AMAZON LIGHTS INC.": "unrelated",
            "INT*AMAZON LIGHTS INC.": "unrelated",
            "VILLA AMAZONIA": "hotel",
            "WWW.AMAZONMEDICAL.CO.U": "Amazon Medical, unrelated",
        },
    },
    "HMRC (as payee)": {
        "net": r"HMRC|HM REVENUE|H M REVENUE|INLAND REVENUE",
        "note": "HMRC and its predecessor the (UK) Inland Revenue as a PAYEE: PAYE/NI, VAT, CIS remittances by other bodies.",
        "exclude": {
            "PWC LLP (HMRC GRANTS)": "payee is PwC",
            "NATWEST- INTERNAL HMRC USE ONLY": "bank-account label, payee unclear",
            "GOMA HMRCAZ LGISOR VEM": "garbled card line (Goma, DRC)",
            "CSR/HMRC": "compound label, payee unclear",
            "GBSRE ADMIN HMRC": "compound label, payee unclear",
            "Inland Revenue Department": "'Inland Revenue Department' is the naming style of overseas IRDs (NZ/HK), publisher context unverified",
        },
    },
    "Thames Water": {"net": r"THAMES WATER", "note": "", "exclude": {}},
    "Severn Trent": {
        "net": r"SEVERN TRENT",
        "note": "Severn Trent plc incl. Services Defence.",
        "exclude": {
            "SEVERN TRENT COSTAIN WATER LIMITED": "joint venture with Costain",
        },
    },
    "Anglian Water": {
        "net": r"ANGLIAN WATER",
        "note": "Incl. predecessor-named 'ANGLIAN WATER AUTHORITY' (legacy ledger name). Wave (JV) excluded.",
        "exclude": {
            "WAVE ANGLIAN WATER BUSINESS": "Wave is the Anglian/NWG joint venture brand",
        },
    },
    "Yorkshire Water": {"net": r"YORKSHIRE WATER", "note": "", "exclude": {}},
    "South West Water (Pennon)": {"net": r"SOUTH WEST WATER|PENNON", "note": "Pennon group incl. Bristol Water t/a line.", "exclude": {}},
    "NHS Professionals": {"net": r"NHS PROFESSIONALS", "note": "DHSC-owned staffing bank.", "exclude": {}},
    "NHS Supply Chain (SCCL)": {
        "net": r"NHS SUPPLY CHAIN|SUPPLY CHAIN CO(ORDINATION|ORDIN\b| LTD)|Sccl|N\.H\.S\. Bsa \(Supply Chain\)",
        "note": "NHS Supply Chain brand + Supply Chain Coordination Ltd (its legal operator) + the NHS BSA-era account label; one operation across eras.",
        "exclude": {},
    },
}

def main():
    rows_out, summary, ambiguities = [], [], []
    for company, spec in COMPANIES.items():
        pat = re.compile(spec["net"], re.I)
        matched = [r for r in con.execute("SELECT supplier_raw, publishers, txns, gbp FROM s").fetchall() if pat.search(r[0])]
        excl = spec["exclude"]
        # exclusions must actually exist (typo guard)
        matched_names = {m[0] for m in matched}
        for e in excl:
            if e not in matched_names:
                print(f"WARN: exclusion not matched by net for {company}: |{e}|")
        inc = [m for m in matched if m[0] not in excl]
        exc = [m for m in matched if m[0] in excl]
        # distinct publishers across included variants
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

    with open(os.path.join(HERE, "variants.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "variant", "publishers", "txns", "gbp"]); w.writerows(rows_out)
    with open(os.path.join(HERE, "variants_excluded.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["company", "string", "gbp", "reason"]); w.writerows(ambiguities)
    with open(os.path.join(HERE, "census_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"{'company':34} {'variants':>8} {'pubs':>5} {'txns':>9} {'gbp':>20}")
    for s in sorted(summary, key=lambda x: -x["variants"]):
        print(f"{s['company']:34} {s['variants']:>8} {s['publishers']:>5} {s['txns']:>9,} {s['gbp']:>20,.2f}")
    print(f"\ntotals: {sum(s['variants'] for s in summary)} included variant strings, {len(ambiguities)} excluded strings")

if __name__ == "__main__":
    main()
