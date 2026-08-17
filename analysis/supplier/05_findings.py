# 05_findings.py — assemble findings.json from the outputs of 01/02/03/04.
# Every number in REPORT.md traces here, and from here to the script that made it.
import json, os, csv

HERE = os.path.dirname(os.path.abspath(__file__))
def load(p): return json.load(open(os.path.join(HERE, p), encoding="utf-8"))

census = load("census_summary.json")
cross = load("cross_body.json")
flows = load("flows_summary.json")

variants_rows = list(csv.DictReader(open(os.path.join(HERE, "variants.csv"), encoding="utf-8")))
flows_rows = list(csv.DictReader(open(os.path.join(HERE, "flows.csv"), encoding="utf-8")))

findings = {
    "_meta": {
        "analysis": "supplier identity across public bodies (analysis #9)",
        "corpus": "../spending/corpus.db, clean set is_dup=0 AND supplier_raw<>'' "
                  "(11,806,377 txns, GBP 3,269,164,975,567.92, 77 publishers, "
                  "241,495 distinct supplier_raw strings — verified by 00_build_agg.py)",
        "blindness": "9 councils + 68 central bodies/NHS/ALBs. This is 'the bodies "
                     "that publish, parsed', never 'the UK'. Never sum across publishers.",
        "scripts": {
            "00_build_agg.py": "corpus -> agg.db (per supplier x publisher rollup)",
            "01_variant_census.py": "Q1 name-variant census -> variants.csv, variants_excluded.csv, census_summary.json",
            "02_cross_body.py": "Q2 cross-body presence -> cross_body.json, cross_body_gainers.csv",
            "03_flows.py": "Q3 public-body flows -> flows.csv, flows_summary.json",
            "04_prices.py": "Q4 recurring-amount test -> recurring_candidates.csv (NOT SUPPORTED)",
        },
    },
    "q1_variant_census": {
        "method": "broad regex net per company over 241,495 distinct supplier strings, "
                  "then every matched string eyeballed; exclusions are exact strings with "
                  "reasons (variants_excluded.csv). Company = corporate group; JVs, "
                  "unverifiable lookalikes and pass-through accounts excluded.",
        "headline": {
            "companies_censused": len(census),
            "included_variant_strings": len(variants_rows),
            "excluded_ambiguous_strings": sum(len(c["excluded"]) for c in census),
        },
        "per_company": [
            {k: c[k] for k in ("company", "variants", "publishers", "txns", "gbp", "note")}
            for c in sorted(census, key=lambda c: -c["variants"])
        ],
        "exhibits": {
            "capita_pass_through": "CAPITA TP NATWEST (GBP 35.61bn, 1,042 txns) + CAPITA TP "
                "HSBC (GBP 246.5m) are DfE 'Funding to pay Teachers' Pensions' routed through "
                "Capita's third-party bank accounts, 2010-04..2014-07. Pension money under a "
                "contractor's bank-account label; excluded from Capita's census total.",
            "edf_acronym_trap": "EUROPEAN COMMISSION (EDF) = European Development Fund, "
                "GBP 3.17bn across 2 publishers. A naive 'EDF' match hands the electricity "
                "company three billion pounds of aid money.",
            "card_statement_explosion": "Amazon's 566 strings are mostly one-off card-statement "
                "lines with per-order references (AMAZON.CO.UK MU5VK08U4...); Microsoft has 18+ "
                "invoice-suffixed 'Microsoft-G0...' strings. Purchase-card exports multiply "
                "variants without limit.",
            "corona_energy_near_miss": "An early draft of this census netted Corona Energy under "
                "British Gas/Centrica. Corona Energy is Macquarie-owned. Kept as a documented "
                "near-miss: eyeballing is the control that caught it.",
        },
        "excluded_by_company": {c["company"]: c["excluded"] for c in census if c["excluded"]},
    },
    "q2_cross_body_presence": cross | {
        "gap_reading": {
            "exact_strings_in_2plus_publishers": cross["exact_match_publishers"]["2+"],
            "normalised_names_in_2plus_publishers": cross["normalised_publishers"]["2+"],
            "exact_10plus": cross["exact_match_publishers"]["10+"],
            "normalised_10plus": cross["normalised_publishers"]["10+"],
            "exact_20plus": cross["exact_match_publishers"]["20+"],
            "normalised_20plus": cross["normalised_publishers"]["20+"],
            "note": "even a trivially conservative normalisation (case/punct/LTD/PLC/THE) "
                    "grows the 10+-publisher set 2.7x and the 20+-publisher set 5.5x; "
                    "fuzzier truth is larger, this is the floor.",
        },
        "example_gainer": "SOFTCAT: one normalised name, 11 exact strings, best single "
                          "string seen in 18 publishers, the name in 41 (cross_body_gainers.csv).",
    },
    "q3_public_body_flows": {
        "supported": True,
        "scope": "UK core public bodies as payees (central gov, local gov incl. MBC/LBC "
                 "abbreviations, NHS, police/fire, agencies, LGPS funds, NDPBs). Excluded and "
                 "quantified: education institutions, foreign governments, charities with "
                 "'council' in the name, fee-funded regulators, private ambulance, "
                 "payee-unclear labels (flows_summary.json.excluded_by_rule_gbp).",
        "eyeballing": "every included normalised name >= GBP 1M eyeballed; unreviewed tail is "
                      f"{flows['residual_unreviewed_tail_gbp']:,.0f} GBP across rule-matched names < 1M each.",
        "pairs": flows["pairs"],
        "bodies": flows["bodies"],
        "gbp_to_public_bodies_excl_mega": flows["gbp_to_public_bodies_excl_mega"],
        "mega_transfers_reported_separately": flows["mega_transfers"],
        "publisher_shares_top": [s for s in flows["publisher_shares"] if s["total_gbp"] >= 1e8][:25],
        "excluded_by_rule_gbp": flows["excluded_by_rule_gbp"],
        "headline_flows": sorted(
            ({"from": r["from_publisher"], "to": r["to_body_normalised"],
              "gbp": float(r["gbp"]), "txns": int(r["transactions"])} for r in flows_rows),
            key=lambda x: -x["gbp"])[:15],
    },
    "q4_same_thing_different_prices": {
        "supported": False,
        "verdict": "NOT SUPPORTED",
        "evidence": "334,200 (supplier, publisher, amount) triples recur >=3 months; 1,034 "
                    "(normalised supplier, amount) pairs recur in >=2 publishers. Inspected: "
                    "they are round-number grants (WFP/ICRC/UNDP contributions), statutory "
                    "fixed fees (ICO GBP 500 registration), franking-machine top-ups (Neopost "
                    "GBP 2,000/4,000), redaction labels (REDACTED, SUPPLIER NAME WITHHELD), and "
                    "NHS pharmacy stock at national list prices (identical Janssen GBP 32,450.52 "
                    "lines across 4 trusts). None is a unit price.",
    },
}

json.dump(findings, open(os.path.join(HERE, "findings.json"), "w", encoding="utf-8"), indent=2)
print("findings.json written")
print(f"census companies {len(census)}, variant rows {len(variants_rows)}, flow rows {len(flows_rows):,}")
