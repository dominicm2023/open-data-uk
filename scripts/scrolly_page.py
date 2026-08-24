"""Scrollytelling tests — do the figures change as you scroll, and is it good?

Two treatments, both from data already computed and eyeballed elsewhere in
the repo, because a scroll test with made-up numbers would test nothing:

1. The morphing league: every Metropolitan District's spend per head, one
   statutory service at a time, bars re-sorting and re-scaling as the steps
   go by. Ends on the libraries story — 34 of 35 districts cut them in real
   terms since 2013-14 — because a form is only worth keeping if it can
   carry a real finding.
2. The ticking receipt: verbatim ledger lines from the comedy strand,
   printed one by one as the reader scrolls, the total counting up. Every
   line was verified against its source file before it was allowed to be
   funny.

No third-party requests: the scroller is ~30 lines of IntersectionObserver,
the data is inlined, and the styles ride on /site.css tokens with literal
fallbacks. Draft, for the workshop, behind /lab.

Usage:
    python scripts/scrolly_page.py        # write scrolly.html
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "scrolly.html"
RO = ROOT / "analysis" / "ro" / "ro_per_head.csv"
RECEIPTS = ROOT / "analysis" / "strands2" / "comedy" / "receipts.csv"

SITE = "open-data.org.uk"
MEASURED = "24 August 2026"
BYLINE = "Joined Up"

RO_QUERY = ("MHCLG Revenue Outturn 2024-25, gross service expenditure by "
            "statutory category / ONS mid-year population; Metropolitan "
            "Districts only — never compared across council classes")
REAL_QUERY = ("same, 2013-14 vs 2024-25, both deflated to 2024-25 prices "
              "(HMT GDP deflator)")
RECEIPT_QUERY = ("published spending-over-threshold ledgers; every line "
                 "matched to its source file, supplier spelling verbatim")

# service key -> (step heading, unit note)
SERVICES = [
    ("total_service_expenditure", "Everything a council does", "£ per head, 2024-25"),
    ("adult_social_care", "Adult social care", "£ per head, 2024-25"),
    ("children_social_care", "Children's social care", "£ per head, 2024-25"),
    ("street_cleansing", "Street cleansing", "£ per head, 2024-25"),
    ("libraries", "Libraries", "£ per head, 2024-25"),
]

# The receipt lines, picked from the eyeballed strand by (finding, supplier
# fragment, amount) so a CSV re-order can never swap a jester for a camel.
PICKS = [
    ("conwy_jester", None, None),
    ("josephs_amazing_camels", None, None),
    ("real_reindeer", None, None),
    ("panto_expenditure", "Hopkins", 30003.0),
    ("flag_flying", "Flag Consultancy", 56500.0),
    ("wig_and_toupee", None, None),
    ("cosmic_sausages", None, None),
    ("weaseltron", None, None),
    ("silent_disco_king", None, None),
    ("trump_golf_card", None, 2360.0),
]


def load_ro() -> tuple[list[str], list[dict]]:
    rows = list(csv.DictReader(open(RO, encoding="utf-8")))
    md = [r for r in rows if r["cls"] == "MD" and r["measure"] == "gross"]

    def per_head(year: str, service: str, col: str = "gbp_per_head") -> dict:
        return {r["name"]: round(float(r[col]), 1)
                for r in md if r["year"] == year and r["service"] == service
                and float(r[col] or 0) > 0}

    councils = sorted(per_head("2024-25", "total_service_expenditure"))
    steps = []
    for svc, title, unit in SERVICES:
        vals = per_head("2024-25", svc)
        ranked = sorted(vals.items(), key=lambda kv: -kv[1])
        hi_n, hi_v = ranked[0]
        lo_n, lo_v = ranked[-1]
        ratio = hi_v / lo_v if lo_v else 0
        copy = {
            "total_service_expenditure":
                f"Start with the whole bill. {hi_n} spends "
                f"£{hi_v:,.0f} for every resident; {lo_n} spends "
                f"£{lo_v:,.0f}. Same statutory duties, same country — "
                f"a {ratio:.1f}× gap before a single choice about "
                "priorities has been made.",
            "adult_social_care":
                f"The biggest single line almost everywhere. {hi_n} puts "
                f"£{hi_v:,.0f} per head into adult social care — "
                f"{lo_n}, £{lo_v:,.0f}. Need drives this more than choice: "
                "poorer, older places pay more because more is needed.",
            "children_social_care":
                f"Watch the order shuffle. {hi_n} now leads at "
                f"£{hi_v:,.0f} per head; the range runs to {lo_n} at "
                f"£{lo_v:,.0f}. A council's place in this league is a map "
                "of deprivation, not of management.",
            "street_cleansing":
                f"Now a small line, and the bars re-scale with it: "
                f"£{hi_v:,.0f} per head in {hi_n} down to £{lo_v:,.0f} in "
                f"{lo_n}. The gap is {ratio:.0f}× — on the visible, "
                "everyday service people judge a council by.",
            "libraries":
                f"And the line that took the cuts. {hi_n} still finds "
                f"£{hi_v:,.0f} per head for libraries; {lo_n} is down to "
                f"£{lo_v:,.0f} — about the price of a paperback, per "
                "resident, per year.",
        }[svc]
        steps.append({"title": title, "unit": unit, "copy": copy,
                      "values": vals, "diverging": False})

    # The closer: libraries, real change since 2013-14.
    lib = defaultdict(dict)
    for r in md:
        if r["service"] == "libraries" and float(r["real_gbp_per_head"] or 0) > 0:
            lib[r["name"]][r["year"]] = float(r["real_gbp_per_head"])
    change = {n: round(v["2024-25"] - v["2013-14"], 1)
              for n, v in lib.items() if "2013-14" in v and "2024-25" in v}
    falls = sum(1 for c in change.values() if c < 0)
    worst = min(change.items(), key=lambda kv: kv[1])
    steps.append({
        "title": "Libraries, since 2013-14",
        "unit": "change in £ per head, real terms",
        "copy": (f"The same libraries line, held against 2013-14 at "
                 f"2024-25 prices. {falls} of {len(change)} metropolitan "
                 f"districts spend less per head in real terms than they "
                 f"did then. {worst[0]} has lost £{-worst[1]:,.0f} per "
                 "head — the deepest cut in the class. This is what a "
                 "decade of “efficiency savings” looks like when "
                 "you draw it."),
        "values": change, "diverging": True})
    return councils, steps


def load_receipt() -> list[dict]:
    rows = list(csv.DictReader(open(RECEIPTS, encoding="utf-8")))
    out = []
    for finding, frag, amount in PICKS:
        match = None
        for r in rows:
            if r["finding"] != finding:
                continue
            if frag and frag.lower() not in r["supplier_raw"].lower():
                continue
            if amount is not None and abs(float(r["amount"]) - amount) > 0.01:
                continue
            match = r
            break
        if not match:
            print(f"   receipt pick MISSING: {finding}")
            continue
        out.append({
            "supplier": match["supplier_raw"],
            "amount": round(float(match["amount"]), 2),
            "buyer": match["publisher"],
            "what": match["expense_type"],
            "date": (match["date"] or "")[:10],
        })
    return out


RECEIPT_COPY = [
    "Every line that follows is a verbatim row from a public spending "
    "ledger, matched to its source file. Councils and departments must "
    "publish what they spend; mostly nobody reads it. We read it.",
    "Conwy hired a jester. Aberdeenshire hired Joseph's Amazing Camels. "
    "These are line items, with dates.",
    "Kensington & Chelsea's reindeer were real. The pantomime industry, "
    "it turns out, has a supply chain.",
    "The Flag Consultancy Ltd is a real firm, and flag flying is a real "
    "budget line at the department for culture.",
    "The Foreign Office once needed a wig shop, cosmic sausages, and — "
    "on a government charge card — a weasel-themed something called "
    "Weaseltron.",
    "A silent disco king, and £2,360 at Trump International Golf. Your "
    "taxes, gloriously specific. The serious point: the ledgers work. "
    "When the spending is this traceable, so is the £638m that isn't funny.",
]


def build() -> str:
    councils, steps = load_ro()
    receipt = load_receipt()

    bars_steps_html = "".join(
        f'<div class="step" data-step="{i}"><h3>{s["title"]}</h3>'
        f'<p>{s["copy"]}</p></div>'
        for i, s in enumerate(steps))

    lines_per_step = 2
    receipt_steps_html = "".join(
        f'<div class="rstep" data-rstep="{i}"><p>{copy}</p></div>'
        for i, copy in enumerate(RECEIPT_COPY))

    page = TEMPLATE
    page = page.replace("__BARS_DATA__", json.dumps(
        {"councils": councils, "steps": steps}, separators=(",", ":")))
    page = page.replace("__RECEIPT_DATA__", json.dumps(
        {"lines": receipt, "perStep": lines_per_step},
        separators=(",", ":")))
    page = page.replace("__BARS_STEPS__", bars_steps_html)
    page = page.replace("__RECEIPT_STEPS__", receipt_steps_html)
    page = page.replace("__RO_QUERY__", RO_QUERY)
    page = page.replace("__REAL_QUERY__", REAL_QUERY)
    page = page.replace("__RECEIPT_QUERY__", RECEIPT_QUERY)
    page = page.replace("__MEASURED__", MEASURED)
    page = page.replace("__BYLINE__", BYLINE)
    return page


TEMPLATE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Scroll tests — Joined Up workshop</title>
<link rel="stylesheet" href="/site.css">
<style>
  .scrolly-wrap { max-width: 72rem; margin: 0 auto; padding: 1.5rem 1.1rem 4rem; }
  .scrolly { display: grid; grid-template-columns: minmax(16rem, 24rem) minmax(0, 1fr);
             gap: 2.5rem; align-items: start; }
  .steps .step, .steps .rstep { min-height: 65vh; display: flex; flex-direction: column;
             justify-content: center; opacity: .35; transition: opacity .4s; }
  .steps .step.active, .steps .rstep.active { opacity: 1; }
  .steps h3 { margin: 0 0 .4rem; font-size: 1.15rem; }
  .sticky-pane { position: sticky; top: 1rem; background: var(--card, #fff);
             border: 1px solid var(--line, #e3e3de); border-radius: var(--radius, 10px);
             padding: 1rem 1.1rem 1.2rem; }
  .pane-title { font-weight: 620; margin: 0 0 .1rem; }
  .pane-unit { color: var(--muted, #61656d); font-size: .8rem; margin: 0 0 .8rem; }
  .bars { position: relative; --namew: 7.2rem; --valw: 3.2rem;
          --namefs: .66rem; }
  .bar-row { position: absolute; left: 0; right: 0;
             transition: transform .7s cubic-bezier(.4,0,.2,1); }
  .bar-name { position: absolute; left: 0; width: var(--namew);
             font-size: var(--namefs);
             white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; color: var(--muted, #61656d); }
  .bar-track { position: absolute; left: calc(var(--namew) + .4rem);
             right: calc(var(--valw) + .2rem); top: 2px; bottom: 2px; }
  .bar-fill { position: absolute; top: 0; bottom: 0; border-radius: 2px;
             background: var(--ju-accent, #0e6e63);
             transition: width .7s cubic-bezier(.4,0,.2,1), left .7s cubic-bezier(.4,0,.2,1),
                         background-color .4s; }
  .bar-fill.neg { background: var(--warn, #a4192b); }
  .bar-val { position: absolute; right: 0; width: var(--valw); text-align: right;
             font-size: var(--namefs);
             font-variant-numeric: tabular-nums; color: var(--ink, #16181c); }
  .baseline { position: absolute; top: 0; bottom: 0; width: 1px;
             background: var(--line-strong, #cfd0ca); transition: left .7s, opacity .4s; }
  /* Compact mode: every bar still present, rows shrunk to fit the pane.
     Per-row text can't survive 9px rows, so only the extremes are labelled
     and a tap names any bar. Honesty by geometry, names on demand. */
  .bars.compact .bar-name, .bars.compact .bar-val { display: none; }
  .bars.compact .bar-track { left: 0; right: 0; }
  .bars.compact .bar-row.notable .bar-name {
             display: block; z-index: 1; width: auto; max-width: 8rem;
             font-size: .62rem; background: var(--card, #fff);
             padding: 0 .3rem 0 0; }
  .bars.compact .bar-row.notable .bar-val {
             display: block; z-index: 1; font-size: .62rem;
             background: var(--card, #fff); padding-left: .3rem; }
  .pane-tap { color: var(--muted, #61656d); font-size: .72rem;
             margin: .5rem 0 0; min-height: 1em; }
  /* receipt */
  .receipt { font-family: ui-monospace, Menlo, Consolas, monospace;
             font-size: .78rem; line-height: 1.5; }
  .receipt .rline { display: none; }
  .receipt .rline.shown { display: block; animation: rin .45s ease-out; }
  @keyframes rin { from { opacity: 0; transform: translateY(6px); }
                   to { opacity: 1; transform: none; } }
  .receipt .amt { float: right; font-variant-numeric: tabular-nums; }
  .receipt .who { color: var(--muted, #61656d); font-size: .68rem; }
  .receipt hr { border: 0; border-top: 1px dashed var(--line-strong, #cfd0ca); }
  .rtotal { font-weight: 700; font-size: .95rem; }
  .provenance { color: var(--muted, #61656d); font-size: .78rem;
             border-top: 1px solid var(--line, #e3e3de); margin-top: 3rem;
             padding-top: 1rem; }
  @media (max-width: 52rem) {
    .scrolly { display: block; }
    .sticky-pane { top: .5rem; max-height: 66vh; overflow: hidden; z-index: 2;
             padding: .6rem .8rem .7rem; }
    /* One header line, not three: on a phone every pixel of chrome is a
       pixel taken from a bar. */
    .pane-title { display: inline; font-size: .88rem; }
    .pane-unit { display: inline; margin: 0 0 0 .45rem; font-size: .72rem; }
    .bars { margin-top: .5rem; }
    .pane-tap { margin: .3rem 0 0; font-size: .65rem; }
    .steps .step, .steps .rstep { min-height: 55vh; }
    .receipt { font-size: .7rem; line-height: 1.4; }
  }
</style>
</head><body><div class="scrolly-wrap">
<h1>Scroll tests</h1>
<p class="lede">Two treatments of the scrollytelling form, using data already
measured and eyeballed elsewhere in the workshop. The question each one asks:
does the scroll add force, or just motion?</p>

<h2>Test 1 — the morphing league</h2>
<section class="scrolly">
  <div class="steps">__BARS_STEPS__</div>
  <div class="sticky-pane" aria-live="off">
    <p class="pane-title" id="bars-title"></p>
    <p class="pane-unit" id="bars-unit"></p>
    <div class="bars" id="bars"></div>
    <p class="pane-tap" id="bars-tap"></p>
  </div>
</section>

<h2 style="margin-top:4rem">Test 2 — the ticking receipt</h2>
<section class="scrolly">
  <div class="steps">__RECEIPT_STEPS__</div>
  <div class="sticky-pane">
    <p class="pane-title">HER MAJESTY'S TILL RECEIPT</p>
    <p class="pane-unit">every line verbatim from a published ledger</p>
    <div class="receipt" id="receipt"></div>
  </div>
</section>

<footer class="provenance">
  <p>How it was measured — league: __RO_QUERY__. Final step: __REAL_QUERY__.
  Receipt: __RECEIPT_QUERY__.</p>
  <p>__BYLINE__ · draft, not for publication · measured __MEASURED__ ·
  data via open-data.org.uk</p>
</footer>
</div>
<script>
const BARS = __BARS_DATA__;
const RCPT = __RECEIPT_DATA__;

/* ---- test 1: morphing bars ---- */
const bars = document.getElementById('bars');
const pane = bars.closest('.sticky-pane');
let ROW = 15, compact = false, curStep = 0;
const baseline = document.createElement('div');
baseline.className = 'baseline'; baseline.style.opacity = '0';
bars.appendChild(baseline);
const rows = {};
for (const name of BARS.councils) {
  const r = document.createElement('div'); r.className = 'bar-row';
  r.dataset.name = name;
  r.innerHTML = '<span class="bar-name">' + name + '</span>' +
    '<span class="bar-track"><span class="bar-fill"></span></span>' +
    '<span class="bar-val"></span>';
  bars.appendChild(r); rows[name] = r;
}
/* Fit every bar into whatever height the pane actually has: rows shrink
   before bars are allowed to clip, and the name column shrinks with them —
   36 names at 8px beat 2 names at 11px, which is what the first phone test
   taught us. Only below 9px rows does text genuinely stop working; then
   the extremes keep their labels and a tap names the rest. */
function layout() {
  const n = BARS.councils.length;
  const chrome = bars.getBoundingClientRect().top - pane.getBoundingClientRect().top
               + 34;  /* pane padding + the tap line under the bars */
  const maxPane = Math.min(window.innerHeight * 0.66, 640);
  ROW = Math.max(8, Math.min(15, Math.floor((maxPane - chrome) / n)));
  compact = ROW < 9;
  bars.classList.toggle('compact', compact);
  if (ROW >= 12) {
    bars.style.setProperty('--namew', '7.2rem');
    bars.style.setProperty('--valw', '3.2rem');
    bars.style.setProperty('--namefs', '.66rem');
  } else {
    bars.style.setProperty('--namew', '4.9rem');
    bars.style.setProperty('--valw', '2.3rem');
    bars.style.setProperty('--namefs', Math.max(7, ROW - 2) + 'px');
  }
  bars.style.height = (n * ROW) + 'px';
  for (const name of BARS.councils) {
    const r = rows[name];
    r.style.height = (ROW - 1) + 'px';
    r.querySelector('.bar-name').style.lineHeight = (ROW - 1) + 'px';
    r.querySelector('.bar-val').style.lineHeight = (ROW - 1) + 'px';
  }
  baseline.style.left = compact ? '78%'
    : 'calc(var(--namew) + .4rem + (100% - var(--namew) - var(--valw) - .6rem) * .78)';
}
bars.addEventListener('click', e => {
  const r = e.target.closest('.bar-row');
  if (!r) return;
  const s = BARS.steps[curStep], v = s.values[r.dataset.name];
  document.getElementById('bars-tap').textContent =
    v == null ? r.dataset.name + ' — no figure reported'
              : r.dataset.name + ' — ' + fmt(v, s.diverging) + ' per head';
});
window.addEventListener('resize', () => { layout(); showStep(curStep); });
function fmt(v, diverging) {
  const a = Math.abs(v);
  const s = a >= 1000 ? (a/1000).toFixed(1) + 'k' : a >= 100 ? a.toFixed(0) : a.toFixed(0);
  return (diverging && v < 0 ? '−£' : '£') + s;
}
function showStep(i) {
  curStep = i;
  const s = BARS.steps[i];
  document.getElementById('bars-title').textContent = s.title;
  document.getElementById('bars-unit').textContent = s.unit;
  const ranked = BARS.councils
    .map(n => ({n, v: s.values[n]}))
    .sort((a, b) => (b.v ?? -1e9) - (a.v ?? -1e9));
  const max = Math.max(...ranked.map(d => Math.abs(d.v ?? 0)), 1);
  const withVals = ranked.filter(d => d.v != null);
  const notable = new Set([withVals[0]?.n, withVals[withVals.length - 1]?.n]);
  baseline.style.opacity = s.diverging ? '1' : '0';
  ranked.forEach((d, i2) => {
    const r = rows[d.n], fill = r.querySelector('.bar-fill'),
          val = r.querySelector('.bar-val');
    r.style.transform = 'translateY(' + (i2 * ROW) + 'px)';
    r.classList.toggle('notable', notable.has(d.n));
    if (d.v == null) { fill.style.width = '0%'; val.textContent = '–'; return; }
    const w = Math.abs(d.v) / max * (s.diverging ? 78 : 100);
    fill.classList.toggle('neg', s.diverging && d.v < 0);
    if (s.diverging) {
      fill.style.width = w + '%';
      fill.style.left = d.v < 0 ? (78 - w) + '%' : '78%';
    } else {
      fill.style.width = w + '%'; fill.style.left = '0%';
    }
    val.textContent = fmt(d.v, s.diverging);
  });
}
/* ---- test 2: the receipt ---- */
const rc = document.getElementById('receipt');
let html = '';
RCPT.lines.forEach((l, i) => {
  html += '<div class="rline" data-line="' + i + '">' +
    '<span class="amt">£' + l.amount.toLocaleString('en-GB',
        {minimumFractionDigits: 2}) + '</span>' +
    l.what.toUpperCase() +
    '<div class="who">' + l.supplier + ' — ' + l.buyer +
    (l.date ? ' · ' + l.date : '') + '</div></div>';
});
html += '<hr><div class="rtotal">TOTAL <span class="amt" id="rtot">£0.00</span></div>';
rc.innerHTML = html;
const rlines = rc.querySelectorAll('.rline');
let shownTotal = 0, tickFrom = 0, tickTo = 0, tickT0 = 0;
function tick(ts) {
  if (!tickT0) tickT0 = ts;
  const p = Math.min((ts - tickT0) / 500, 1);
  const v = tickFrom + (tickTo - tickFrom) * (1 - Math.pow(1 - p, 3));
  document.getElementById('rtot').textContent =
    '£' + v.toLocaleString('en-GB', {minimumFractionDigits: 2,
                                          maximumFractionDigits: 2});
  if (p < 1) requestAnimationFrame(tick);
}
function showReceiptStep(i) {
  const upto = Math.min((i) * RCPT.perStep, RCPT.lines.length);
  let total = 0;
  rlines.forEach((el, j) => {
    el.classList.toggle('shown', j < upto);
    if (j < upto) total += RCPT.lines[j].amount;
  });
  if (total !== tickTo) {
    tickFrom = tickTo; tickTo = total; tickT0 = 0;
    requestAnimationFrame(tick);
  }
}
/* ---- one observer drives both ---- */
const io = new IntersectionObserver(entries => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    document.querySelectorAll('.step, .rstep')
      .forEach(el => el.classList.remove('active'));
    e.target.classList.add('active');
    if (e.target.dataset.step !== undefined) showStep(+e.target.dataset.step);
    if (e.target.dataset.rstep !== undefined) showReceiptStep(+e.target.dataset.rstep);
  }
}, {rootMargin: '-40% 0px -40% 0px'});
document.querySelectorAll('.step, .rstep').forEach(el => io.observe(el));
layout(); showStep(0); showReceiptStep(0);
if (compact) document.getElementById('bars-tap').textContent =
  'tap any bar for its council';
</script>
</body></html>
"""


def main() -> int:
    page = build()
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.name} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
