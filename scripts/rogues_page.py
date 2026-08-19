"""Draw the rogue-joins investigations — the capitalism strand, and the receipts.

Seven panels from analysis/strands2/: the austerity-postcode scatter and its
quintile bar, the compounding quadrant, the DHSC consulting spike, the
Carillion relay (one bar per month, coloured by which corporate vehicle the
same MoD housing money flowed through), the bailiff gross-vs-net pairs, and
the till receipt — verbatim ledger lines drawn as the thing they are.

The receipt is the one panel whose form is decorative, and the decoration
carries no value: every number on it is printed text pulled row-by-row from
receipts.csv, which carries a source file per line. Comedy dies if one
example is wrong, so nothing appears that was not verified.

Joined Up livery throughout, signed, drafts for the workshop.

Usage:
    python scripts/rogues_page.py          # write rogues.html
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import charts  # noqa: E402
from charts import PAD, W, _para, esc  # noqa: E402

ROOT = Path(__file__).parent.parent
S2 = ROOT / "analysis" / "strands2"
OUT = ROOT / "rogues.html"
SITE = "open-data.org.uk"
MEASURED = "19 August 2026"
BYLINE = "Joined Up"


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(open(path, encoding="utf-8")))


def num(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) or default)
    except ValueError:
        return default


def panel(title: str, body: str, height: float, query: str) -> str:
    band, band_h = charts._provenance(int(height), query,
                                      f"{SITE} · measured {MEASURED}",
                                      byline=BYLINE)
    svg = charts._with_fallbacks(charts._frame(
        body + band, int(height) + band_h, title, query))
    return (f'<article class="finding joined-up"><h2>{esc(title)}</h2>'
            f"<figure>{svg}</figure></article>")


# --- panels ----------------------------------------------------------------

def postcode_scatter() -> str:
    sc = [r for r in rows(S2 / "regressive" / "scatter_settlement_loss_vs_imd.csv")
          if r.get("clean") == "True" and r["cls"] in ("LB", "MD", "UA", "SC")]
    fills = {"LB": "var(--cat-1)", "MD": "var(--cat-5)",
             "UA": "var(--cat-3)", "SC": "var(--cat-2)"}
    name_these = {"Lewisham", "Blackpool UA", "Surrey CC", "Lancashire CC",
                  "South Tyneside", "Windsor & Maidenhead UA"}
    pts = [{"x": num(r, "imd_avg_score"), "y": num(r, "loss_ph"),
            "fill": fills[r["cls"]],
            "label": r["name"] if r["name"] in name_these else None}
           for r in sc]
    rho = next((num(r, "rho_loss_ph_vs_imd")
                for r in rows(S2 / "regressive" / "spearman_by_class.csv")
                if r["cls"] == "UA" and r.get("subset") == "clean"), None)
    body, h = charts.scatter(
        pts, "IMD 2019 average score (higher = more deprived)",
        "real government settlement lost, £ per resident, 2013-14 to 2024-25",
        "Every upper-tier English council, coloured by class. The more "
        "deprived the place, the more grant it lost per resident — Spearman "
        "runs +0.52 to +0.77 within every class, all p<0.001. On percentage "
        "change this gradient vanishes, because deprived areas started on "
        "grants 2.3x larger: percent leagues launder it, pounds reveal it.",
        rho=rho)
    return panel("Austerity was a postcode policy", body, h,
                 "analysis/strands2/regressive/scatter_settlement_loss_vs_imd"
                 ".csv — RSG + rates retention, real 2024-25 prices, "
                 "hand-check flags honoured")


def quintile_bar() -> str:
    sc = [r for r in rows(S2 / "regressive" / "scatter_settlement_loss_vs_imd.csv")
          if r.get("clean") == "True" and r["cls"] in ("LB", "MD", "UA", "SC")]
    # Quintile by deprivation rank WITHIN class, then pooled: the same
    # within-class discipline as everything else in this project, so a
    # county is never quintiled against a met borough.
    buckets: dict[int, list[float]] = defaultdict(list)
    for r in sc:
        rank, n = num(r, "imd_rank_in_class"), num(r, "class_n")
        if not n:
            continue
        q = min(4, int((rank - 1) / n * 5))
        buckets[q].append(num(r, "loss_ph"))
    labels = ["most deprived fifth", "second", "middle", "fourth",
              "least deprived fifth"]
    data = [(labels[q], sum(v) / len(v)) for q, v in sorted(buckets.items())]
    body, h = charts.hbar(
        data,
        "Mean real settlement lost per resident, 2013-14 to 2024-25, "
        "upper-tier councils quintiled by deprivation within their own class. "
        "The most deprived fifth lost roughly twice the pounds per resident "
        "of the least deprived fifth — and the same councils raise less from "
        "council tax, because poverty is also a weak tax base. The cut "
        "compounded.")
    return panel("Twice the money, taken from the poorest fifth", body, h,
                 "same file, quintiled by imd_rank_in_class within class, "
                 "clean rows only")


def compound_quadrant() -> str:
    cj = [r for r in rows(S2 / "regressive" / "compound_join.csv")
          if r.get("clean") == "True" and r.get("ct_clean") == "True"
          and r["cls"] in ("MD", "UA", "SC")]
    name_these = {"Middlesbrough UA", "Blackpool UA",
                  "Kingston upon Hull UA", "Surrey CC", "Rutland UA",
                  "South Tyneside"}
    pts = [{"x": num(r, "loss_ph"), "y": num(r, "ctr_per_head"),
            "fill": "var(--cat-4)" if num(r, "imd_avg_score") > 27
            else "var(--cat-1)",
            "label": r["name"] if r["name"] in name_these else None}
           for r in cj]
    body, h = charts.scatter(
        pts, "real settlement lost, £ per resident",
        "council tax raised, £ per resident, 2024-25",
        "Upper-tier councils outside London (London's low council tax is a "
        "rate choice, not a weak base — its own note in the working). Red "
        "marks the most deprived third. They cluster bottom-right: the "
        "biggest grant losses AND the least council tax raised to replace "
        "them. Middlesbrough, Blackpool and Hull are doubly hit; Surrey and "
        "Rutland doubly spared.")
    return panel("The compounding: lose the grant, lack the base", body, h,
                 "analysis/strands2/regressive/compound_join.csv — clean and "
                 "ct_clean rows, London excluded for the rate-choice caveat")


def dhsc_spike() -> str:
    fy = rows(S2 / "consultants" / "dhsc_consulting_fy.csv")
    series = [(r["fy"][:4], num(r, "consulting_gbp") / 1e6) for r in fy]
    peak = max(series, key=lambda s: s[1])[0]
    body, h = charts.timeline(
        series,
        "Consulting firms in the Department of Health's published ledger, £m "
        "per financial year. £8.1m in 2019-20 became £204.6m in 2021-22 — "
        "nineteen times over, the Test-and-Trace era — before falling back. "
        "One Deloitte invoice alone was £44m, and £7.9m of Deloitte's work "
        "was booked under a code the ledger calls Contractor/Staff "
        "Substitution: the austerity two-step, written in the state's own "
        "vocabulary.",
        highlight={peak: "var(--cat-4)"})
    return panel("Cut staff, hire consultants", body, h,
                 "analysis/strands2/consultants/dhsc_consulting_fy.csv — "
                 "censused variants, PwC's routed fund money excluded before "
                 "it lied")


def carillion_relay() -> str:
    arcs = rows(S2 / "outsourcers" / "collapse_arcs_monthly.csv")
    relay = ["CarillionEnterprise (JV)", "CarillionAmey (JV)", "Amey"]
    colours = {"CarillionEnterprise (JV)": "var(--seq-3)",
               "CarillionAmey (JV)": "var(--cat-1)",
               "Amey": "var(--cat-5)"}
    monthly: dict[str, dict[str, float]] = defaultdict(dict)
    for r in arcs:
        if r["company"] in relay and r["year_month"] >= "2010-01" \
                and r["year_month"] <= "2020-12":
            monthly[r["year_month"]][r["company"]] = num(r, "gbp")
    months = sorted(monthly)
    series, highlight = [], {}
    for m in months:
        total = sum(monthly[m].values())
        series.append((m, total / 1e6))
        dominant = max(monthly[m], key=monthly[m].get)
        highlight[m] = colours[dominant]
    body, h = charts.timeline(
        series,
        "The same MoD housing money, month by month, coloured by the vehicle "
        "it flowed through: CarillionEnterprise (pale blue) hands to "
        "CarillionAmey (dark blue) in June 2014; CarillionAmey dies in "
        "October 2018 and Amey Defence Services (teal) appears the same "
        "month at £53.2m. Carillion the company was liquidated in January "
        "2018 — its ledger tail is literally titled IN LIQUIDATION — and the "
        "money never paused. The firm collapsed; the flow was immortal.",
        highlight=highlight)
    return panel("The Carillion relay", body, h,
                 "analysis/strands2/outsourcers/collapse_arcs_monthly.csv — "
                 "monthly £ by corporate vehicle, MoD-relay entities, "
                 "2010-2020")


def bailiff_passthrough() -> str:
    ft = rows(S2 / "bailiffs" / "firm_totals.csv")
    ft = [r for r in ft if num(r, "gross_outflow_gbp") > 400_000]
    ft.sort(key=lambda r: -num(r, "gross_outflow_gbp"))
    data = []
    for r in ft[:5]:
        data.append((f"{r['firm']} — gross", num(r, "gross_outflow_gbp") / 1e6))
        data.append((f"{r['firm']} — net", max(0.0, num(r, "net_gbp")) / 1e6))
    body, h = charts.hbar(
        data,
        "£m through enforcement firms in the ledgers we hold: the gross legs "
        "against what actually stayed spent. North Yorkshire's bailiff lines "
        "net to £403.84 across £228,000 of gross churn, and Bristol's "
        "residuals are the statutory £75 and £235 fees the 2014 regulations "
        "charge to the debtor. Councils barely pay for enforcement — the "
        "people being enforced against do. The machine runs on its own "
        "targets.")
    return panel("The debt machine pays for itself", body, h,
                 "analysis/strands2/bailiffs/firm_totals.csv — gross legs vs "
                 "net after same-day contra reversals, per firm")


def the_receipt() -> str:
    """Verbatim ledger lines drawn as a till receipt.

    Every amount is read from receipts.csv rows, never typed in — except the
    panto total, which is the sum of that finding's published series and is
    labelled as a total. The form is a joke; the contents are audit-grade.
    """
    rc = rows(S2 / "comedy" / "receipts.csv")
    by_finding: dict[str, list[dict]] = defaultdict(list)
    for r in rc:
        by_finding[r["finding"]].append(r)

    def exact(finding: str, supplier: str, amount: float) -> dict | None:
        """One row, matched on finding AND supplier AND amount.

        The first version fell back to 'any row in a nearby finding' and put
        the jester's fee on the camels' line. In comedy one wrong number
        kills the format, so a pick either matches all three or the line is
        dropped.
        """
        for r in by_finding.get(finding, []):
            if supplier.lower() in r["supplier_raw"].lower()                     and abs(num(r, "amount") - amount) < 0.005:
                return r
        return None

    items: list[tuple[str, str, float]] = []
    panto = by_finding.get("panto_expenditure", [])
    if panto:
        items.append(("PANTO EXPENDITURE — RUSHMOOR BC",
                      f"{len(panto)} lines held of a 508-payment ledger code",
                      sum(num(r, "amount") for r in panto)))
    picks = [
        ("flag_flying", "FLAG CONSULTANCY", 56500.00,
         "THE FLAG CONSULTANCY LTD — DCMS, 'FLAG FLYING'", ""),
        ("trump_golf_card", "TRUMP", 4545.00,
         "TRUMP INTERNATIONAL GOLF — FCO CARD, AUG 2013",
         "refunded the following month"),
        ("mod_oyster_rent", "OYSTER", 26500.00,
         "COLCHESTER OYSTER FISHERY — MOD, RENT AND RATES",
         "twice yearly"),
        ("bellringers_public_health", "BELL", 1000.00,
         "KIRKBYMOORSIDE BELL RINGERS — N YORKS, 'PUBLIC HEALTH'", ""),
        ("darts_performing_arts", "DARTS WORLD", 28814.05,
         "DARTS WORLD LTD — N YORKS, 'PERFORMING ARTS', 24 DEC", ""),
        ("josephs_amazing_camels", "CAMELS", 2385.00,
         "JOSEPH`S AMAZING CAMELS — GREENWICH", ""),
        ("conwy_jester", "JESTER", 1950.00,
         "RUSS ERWYD T/AS CONWY JESTER — GREENWICH, PARKS", ""),
        ("dog_in_a_doublet", "VP FABRICATION", 780.00,
         "LIFTING ARM FOR DOG DOUBLET — ENVIRONMENT AGENCY", ""),
    ]
    for finding, supplier, amount, label, sub in picks:
        row = exact(finding, supplier, amount)
        if row:
            items.append((label, sub, num(row, "amount")))
    oracle = [r for r in by_finding.get("oracle_penny_licence", [])
              if "oracle" in r["supplier_raw"].lower()]
    if oracle:
        items.append((f"ORACLE — 'SOFTWARE LICENCES', {len(oracle)} INVOICES",
                      "", sum(num(r, "amount") for r in oracle)))

    x, width = 300, 600
    y = 40
    out = [f'<rect x="{x}" y="{y - 18}" width="{width}" height="10" '
           f'fill="var(--accent-soft)"/>']
    out.append(f'<text x="{x + width / 2}" y="{y + 16}" class="t-value" '
               f'text-anchor="middle">THE PUBLIC LEDGER — SELECTED ITEMS</text>')
    out.append(f'<text x="{x + width / 2}" y="{y + 36}" class="p-key" '
               f'text-anchor="middle">EVERY LINE VERBATIM FROM A PUBLISHED '
               f'SPENDING FILE</text>')
    y += 58
    for label, sub, amount in items:
        amt = f"£{amount:,.2f}"
        out.append(f'<text x="{x + 14}" y="{y}" class="p-mono">'
                   f'{esc(charts._fit(label, 11, width - 150, "p-mono"))}</text>')
        out.append(f'<text x="{x + width - 14}" y="{y}" class="p-mono" '
                   f'text-anchor="end">{esc(amt)}</text>')
        y += 18
        if sub:
            out.append(f'<text x="{x + 14}" y="{y}" class="p-key">'
                       f'{esc(sub.upper())}</text>')
            y += 16
        y += 4
    out.append(f'<line x1="{x + 14}" y1="{y}" x2="{x + width - 14}" y2="{y}" '
               f'stroke="var(--line-strong)" stroke-width="1" '
               f'stroke-dasharray="4 4"/>')
    y += 24
    out.append(f'<text x="{x + 14}" y="{y}" class="p-mono">TOTAL</text>')
    out.append(f'<text x="{x + width - 14}" y="{y}" class="p-mono" '
               f'text-anchor="end">A COUNTRY</text>')
    y += 30
    note, note_h = _para(
        "None of this is waste, exactly — Rushmoor runs a theatre, the sluice "
        "is really called the Dog-in-a-Doublet, and someone has to fly the "
        "flags. That is the point: the ledgers are full of true, checkable, "
        "gloriously specific life, and the same provenance that makes the "
        "jokes safe makes the serious claims stick.",
        PAD, 78, "h-note" if "h-note" in charts.SIZE_BY_CLASS else "t-label",
        13, 240, 19)
    out.append(note)
    return panel("The receipt", "".join(out), max(y + 10, 78 + note_h + 10),
                 "analysis/strands2/comedy/receipts.csv — one source file per "
                 "line, amounts read from the rows, never retyped")


PAGE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Rogues — UK Open Data Index</title>
<link rel="stylesheet" href="/site.css">
</head><body><div class="wrap">
<h1>The rogue joins</h1>
<p>The investigations that joined the council accounts to the spending
ledgers and went looking for the failures — and the fun. Every named firm
was matched by eyeballed variants, every claim carries its verdict, and two
of the best findings here are ones the honesty checks produced.</p>
{panels}
</div></body></html>
"""


def main() -> int:
    panels = []
    for name, fn in [("postcode_scatter", postcode_scatter),
                     ("quintile_bar", quintile_bar),
                     ("compound_quadrant", compound_quadrant),
                     ("dhsc_spike", dhsc_spike),
                     ("carillion_relay", carillion_relay),
                     ("bailiff_passthrough", bailiff_passthrough),
                     ("the_receipt", the_receipt)]:
        try:
            panels.append(fn())
            print(f"   drew {name}")
        except Exception as exc:  # noqa: BLE001 — one panel must not sink the page
            print(f"   {name} FAILED: {type(exc).__name__}: {exc}")
    OUT.write_text(PAGE.replace("{panels}", "".join(panels)),
                   encoding="utf-8")
    print(f"\n{len(panels)} panels — wrote {OUT.name} "
          f"({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
