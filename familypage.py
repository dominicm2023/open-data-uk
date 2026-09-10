"""The page for a dataset family: one table for a thing many bodies publish.

Rendered from what families/build.py wrote — the summary with every source's
place on the ladder, and the published rows — so the page can never claim a
row the build did not produce. Everything a reader needs to check us is on
the page: which bodies contributed and under which licence, which bodies
publish the thing but are not in the table yet and why, and a download of
the whole table with a receipt on every row.

The original links come first. A family table is a convenience built on the
publishers' files; the page says so and links each one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pagerender import _page, breadcrumbs, esc, simple_head, dataset_path
from paths import DATA_DIR

STORE = DATA_DIR / "families" / "out"
LADDER_ORDER = ["published", "mapped (proposed)", "extracted", "mapping failed", "rejected",
                "fetch failed", "not admitted"]
LADDER_TEXT = {
    "published": "in the table",
    "mapped (proposed)": "mapped, awaiting a person's review",
    "extracted": "fetched and extracted; not yet mapped to the schema",
    "mapping failed": "the mapping no longer fits the file",
    "rejected": "looked at and found not to be this family",
    "fetch failed": "could not be fetched or read this run",
    "not admitted": "no explicit open licence, so not fetched",
}


def family_for_title(title: str) -> str | None:
    """Which built family a who-publishes title belongs to, by the same
    include/exclude rule the registry uses — so the link and the table can
    never disagree about what counts."""
    import re
    from families.registry import FAMILIES
    for name, spec in FAMILIES.items():
        if re.search(spec["include"], title or "", re.I) and not re.search(spec["exclude"], title or "", re.I):
            return name if load(name) else None
    return None


def load(family: str) -> dict | None:
    p = STORE / family / "summary.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def published_rows(family: str) -> list[dict]:
    p = STORE / family / f"{family}.published.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


FAMILY_ORDER = ["recycling_centres", "air_quality_annual", "spend_over_500", "brownfield_land"]
PREVIEW_ROWS = 8
PREVIEW_COLS = 6


def _schema(family: str) -> dict:
    return json.loads((Path(__file__).parent / "families" / "schema" / f"{family}.json").read_text(encoding="utf-8"))


def _headline(s: dict) -> dict:
    """The numbers a page leads with, all from the build summary."""
    by_pub: dict[str, int] = {}
    # a national collection is one entry that stands for many bodies
    via_platform = 0
    for e in s.get("sources", []):
        if e.get("ladder") == "published" and e.get("rows"):
            b = e.get("body") or e["publisher"]
            if e.get("portal") in ("platform", "dashboard") and e.get("bodies"):
                b = f"{b} — {e['bodies']} authorities"
                via_platform += e["bodies"] - 1
            by_pub[b] = by_pub.get(b, 0) + e["rows"]
    ladder = s.get("ladder", {})
    # the registry's sources are datasets found in the catalogues we index;
    # a national network or collection is a route, not a catalogued dataset
    srcs = s.get("sources", [])
    catalogued = [e for e in srcs if e.get("portal") not in ("networks", "platform")]
    return {"total": s.get("published_rows", 0), "by_pub": by_pub, "bodies": len(by_pub) + via_platform,
            "sources": len(catalogued), "sources_published": sum(1 for e in catalogued if e.get("ladder") == "published"),
            "via_platform": via_platform + (1 if via_platform else 0),
            "via_networks": sum(1 for e in srcs if e.get("portal") == "networks" and e.get("ladder") == "published"),
            "built": (s.get("built_at") or "")[:10]}


def _size_note(family: str) -> str:
    """", 2.1 GB" when the whole table is a download worth warning about."""
    p = STORE / family / f"{family}.published.csv"
    try:
        n = p.stat().st_size
    except OSError:
        return ""
    if n >= 1e9:
        return f", {n / 1e9:.1f} GB"
    if n >= 50e6:
        return f", {n / 1e6:.0f} MB"
    return ""


def _nice_date(iso: str) -> str:
    try:
        from datetime import date
        d = date.fromisoformat(iso)
        return f"{d.day} {d.strftime('%B %Y')}"
    except ValueError:
        return iso


def render_combined(site_url: str) -> str:
    """The hub: every family that has a built table, with its headline numbers."""
    crumb_html, crumb_ld = breadcrumbs([("Home", "/"), ("Combined data", None)], site_url)
    cards = []
    for fam in FAMILY_ORDER:
        s = load(fam)
        if s is None:
            continue
        h = _headline(s)
        schema = _schema(fam)
        cards.append(
            f'<article class="fam-card"><h2><a href="/family/{esc(fam)}">{esc(s["label"])}</a></h2>'
            f'<p class="stats"><b>{h["total"]:,}</b> rows · <b>{h["bodies"]}</b> public bodies · built {esc(_nice_date(h["built"]))}</p>'
            f'<p class="note">One row is {esc(schema["one_row_is"])}.</p>'
            f'<p class="note"><a href="/api/family/{esc(fam)}.csv">CSV</a> · <a href="/api/family/{esc(fam)}">JSON</a> · '
            f'<a href="/who-publishes?name={esc(s["label"])}">who publishes it</a></p></article>')
    body_html = (
        crumb_html
        + "<h1>Combined data</h1>"
        + '<p class="lede">For the things many public bodies publish separately — where the recycling centres are, '
          "what the air monitors read, what was paid to whom — one table each, in one schema, built from the bodies' own files.</p>"
        + f'<div class="fam-grid">{"".join(cards)}</div>'
        + '<h2>How a table is made</h2>'
        + '<p class="note">A file is fetched only where its licence says explicitly that it may be reused. A person reviews '
          "how each body's columns map to the shared schema before its rows publish. Every row keeps its receipt — the "
          'publisher, the file and its hash, the row it came from, and the licence — so anything here can be checked '
          'against the original. Bodies that publish the thing but are not yet in a table are listed on each page, with '
          'the reason.</p>'
        + '<p class="note">The original files come first. A combined table is a convenience built on them; the '
          '<a href="/who-publishes">who-publishes pages</a> link every one.</p>'
    )
    head_html = simple_head(
        "Combined data — one table for the things many UK public bodies publish",
        "Recycling centres, air quality annual means and spend over £500, combined from public bodies' own open data "
        "into one table each, with the source and licence of every row.",
        "/combined", site_url, crumb_ld)
    return _page(head_html, body_html, "/combined")


def _map_svg(facets: dict, total: int) -> str:
    """Every distinct site with coordinates as a dot on the UK outline. No
    tiles, no library: the outline is ours and the dots are the table's."""
    from families import ukmap
    sites = facets.get("sites") or []
    if not sites:
        return ""
    r = 2.6 if len(sites) < 300 else 1.7 if len(sites) < 1500 else 1.2
    dots = []
    for st in sites:
        pt = ukmap.project(st["lon"], st["lat"])
        if pt is None:
            continue
        label = f'{st["name"] or "site"} — {st["body"] or ""}' + (f' ({st["n"]} rows)' if st["n"] > 1 else "")
        dots.append(f'<circle cx="{pt[0]}" cy="{pt[1]}" r="{r}"><title>{esc(label)}</title></circle>')
    n_coords = facets.get("sites_total", len(sites))
    without = total - (facets.get("filled") or {}).get("lon", 0)
    return (
        f'<figure class="map"><svg viewBox="0 0 {ukmap.W} {ukmap.H}" role="img" '
        f'aria-label="{n_coords} sites on a map of the UK">'
        f'<path class="ie" d="{ukmap.IRELAND}"/><path class="uk" d="{ukmap.UK}"/>'
        f'<g class="dots">{"".join(dots)}</g></svg>'
        f'<figcaption class="note">{n_coords:,} distinct sites with coordinates'
        + (f'; {without:,} rows carry none' if without > 0 else '')
        + '. Hover a dot for its name and body.</figcaption></figure>')


def _strip_svg(facets: dict, by_pub: dict) -> str:
    """Which body covers which years: a cell per body and year, shaded by
    how many rows fall there. The gaps are the point."""
    years = sorted(facets.get("years") or {})
    body_years = facets.get("body_years") or {}
    if len(years) < 2 or not body_years:
        return ""
    bodies = [b for b, _ in sorted(by_pub.items(), key=lambda kv: (-kv[1], kv[0])) if b in body_years]
    if not bodies:
        return ""
    lw, cw, ch, top = 200, 30, 18, 22
    w = lw + cw * len(years) + 6
    h = top + ch * len(bodies) + 4
    peak = max(n for by in body_years.values() for n in by.values()) or 1
    import math
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Years covered by each body">']
    for j, y in enumerate(years):
        out.append(f'<text class="yr" x="{lw + j * cw + cw / 2:.0f}" y="{top - 8}" text-anchor="middle">{esc(y)}</text>')
    for i, b in enumerate(bodies):
        y0 = top + i * ch
        short = b if len(b) <= 30 else b[:29] + "…"
        out.append(f'<text class="bd" x="{lw - 8}" y="{y0 + ch - 5}" text-anchor="end"><title>{esc(b)}</title>{esc(short)}</text>')
        for j, y in enumerate(years):
            n = body_years[b].get(y, 0)
            if not n:
                out.append(f'<rect class="empty" x="{lw + j * cw + 1}" y="{y0 + 1}" width="{cw - 2}" height="{ch - 2}"/>')
                continue
            a = 0.18 + 0.82 * (math.log1p(n) / math.log1p(peak))
            out.append(f'<rect x="{lw + j * cw + 1}" y="{y0 + 1}" width="{cw - 2}" height="{ch - 2}" fill-opacity="{a:.2f}">'
                       f'<title>{esc(b)}, {esc(y)}: {n:,} rows</title></rect>')
    out.append("</svg>")
    return (f'<figure class="strip"><div class="table-wrap">{"".join(out)}</div>'
            '<figcaption class="note">Darker is more rows; an outlined cell is a year with none in the table. '
            'Hover a cell for the count.</figcaption></figure>')


def _gbp(v: float) -> str:
    if abs(v) >= 1e9:
        return f"£{v / 1e9:,.2f} billion"
    if abs(v) >= 1e6:
        return f"£{v / 1e6:,.1f} million"
    return f"£{v:,.0f}"


def _headline_tiles(facets: dict) -> str:
    """The figures a family's schema asks the page to lead with."""
    tiles = []
    for t in facets.get("headline") or []:
        v = t.get("value")
        if v is None:
            continue
        if t.get("format") == "percent":
            shown = f"{v * 100:.0f}%"
        elif t.get("format") == "integer":
            shown = f"{int(round(v)):,}"
        else:
            shown = f"{v:,.0f}"
        tiles.append(f'<div class="stat"><b>{esc(shown)}</b><span>{esc(t["label"])}</span></div>')
    return f'<div class="stat-row">{"".join(tiles)}</div>' if tiles else ""


def _qa(family: str, s: dict, schema: dict, h: dict) -> list[tuple[str, str]]:
    """Questions the table can answer, each answered from the build's own
    facets. Every answer is a fact about this table, and says so when the
    obvious next question is one it cannot answer."""
    f = s.get("facets") or {}
    total, by_pub, n_sources = h["total"], h["by_pub"], h["sources"]
    filled = f.get("filled") or {}
    years = f.get("years") or {}
    qa: list[tuple[str, str]] = []
    missing = n_sources - h["sources_published"]
    how_much = (f"{total:,} rows from {h['bodies']} public bodies. The catalogues we index list {n_sources} datasets of "
                f"this kind; {h['sources_published']} are in the table and {missing} are not yet — the list below the "
                "preview says why for each.")
    if h.get("via_platform"):
        how_much += (f" A further {h['via_platform']} authorities are here through MHCLG's national collection rather "
                     "than a file of their own.")
    if h.get("via_networks"):
        how_much += f" {h['via_networks']} national monitoring networks are read from their own sites."
    qa.append(("How much is here?", how_much))
    if years:
        ys = sorted(years)
        peak = max(years.items(), key=lambda kv: kv[1])
        qa.append(("Which years does it cover?",
                   f"{ys[0]} to {ys[-1]}, unevenly: {peak[1]:,} rows fall in {peak[0]}, and not every body "
                   f"covers every year — the grid shows the gaps."))
    if family == "recycling_centres":
        n_coords = f.get("sites_total", 0)
        qa.append(("Where are the centres?",
                   f"{n_coords:,} distinct sites have coordinates and are on the map; "
                   f"{total - filled.get('lon', 0):,} rows have a postcode or an address only."))
        qa.append(("Does it say when they open and what they take?",
                   f"Opening hours are given on {filled.get('opening_hours', 0):,} of {total:,} rows and accepted materials "
                   f"on {filled.get('materials', 0):,}, exactly as each body wrote them — not normalised, so the same "
                   "material can appear under several names."))
    if family == "air_quality_annual":
        means = f.get("annual_mean") or {}
        for pol, m in sorted(means.items(), key=lambda kv: -kv[1]["n"]):
            mx = m.get("max") or {}
            unit = m.get("unit") or mx.get("unit") or ""
            site = mx.get("site_name") or mx.get("site_id") or "an unnamed site"
            qa.append((f"What is the highest {pol} annual mean in the table?",
                       f"{mx.get('annual_mean')} {unit} at {site} ({mx.get('publisher')}, {mx.get('year')}), from "
                       f"{m['n']:,} {pol} readings across {m['sites']:,} sites. That is the figure as the body published it; "
                       "the table does not verify readings against the body's own report."))
        qa.append(("Can I compare a site against the legal limit?",
                   "Only with care. The UK annual mean objective for NO₂ is 40 µg/m³, but a diffusion-tube figure is "
                   "usually bias-adjusted in the body's own report and this table carries the value as published, "
                   "with the method where the body stated it."))
    if family == "brownfield_land":
        hl = {t["column"]: t for t in (f.get("headline") or [])}
        ha, dw, pm = hl.get("hectares"), hl.get("min_net_dwellings"), hl.get("planning_status")
        if ha and ha.get("value") is not None:
            qa.append(("How much land is on the registers?",
                       f"{ha['value']:,.0f} hectares across {ha['n']:,} sites that give an area, as the authorities "
                       f"measured it; {total - ha['n']:,} sites give no area."))
        if dw and dw.get("value") is not None:
            qa.append(("How many homes could it take?",
                       f"At least {int(dw['value']):,}, adding up each authority's own minimum estimate on {dw['n']:,} sites. "
                       "That is a sum of estimates made at different times to different rules, not a forecast."))
        if pm and pm.get("value") is not None:
            qa.append(("How much of it already has permission?",
                       f"{pm['value'] * 100:.0f}% of the {pm['n']:,} sites with a stated planning status are permissioned; "
                       "the rest are pending or not yet applied for. A register lists land suitable for housing, not land "
                       "being built on."))
        n_coords = f.get("sites_total", 0)
        qa.append(("Where are the sites?",
                   f"{n_coords:,} sites have coordinates and are on the map. Rows marked 'via MHCLG's planning data platform' "
                   "come from the national collection because the authority's own file was not available; the rest come "
                   "from the authorities' own registers."))
    if family == "spend_over_500":
        am = f.get("amount") or {}
        if am.get("total"):
            qa.append(("How much spend is in the table?",
                       f"{_gbp(am['total'])} across {filled.get('amount_gbp', total):,} payment lines. Thresholds differ "
                       "between bodies (the threshold_gbp column says which), so this is a sum of what was published, "
                       "not of what was spent."))
        mx = am.get("max")
        if mx:
            qa.append(("What is the largest single line?",
                       f"{_gbp(mx['amount_gbp'])} to {mx.get('supplier')} from {mx.get('body')}"
                       + (f" on {mx['payment_date']}" if mx.get("payment_date") else "")
                       + (f" — {str(mx['description'])[:80]}" if mx.get("description") else "") + "."))
        qa.append(("Can I add up a supplier across bodies?",
                   "Not from this table alone. Supplier names are exactly as each body published them, and two spellings "
                   "of one company are not matched here — that is an eyeballed decision made elsewhere, never by this "
                   "family."))
        if am.get("negative"):
            qa.append(("Why are some amounts negative?",
                       f"{am['negative']:,} lines are credits or refunds; the sign is kept as published."))
    return qa


def _completeness(schema: dict, facets: dict, total: int) -> str:
    filled = facets.get("filled") or {}
    if not total or not filled:
        return ""
    items = []
    for c in schema["columns"]:
        n = filled.get(c["name"], 0)
        pct = 100 * n / total
        items.append(f'<li><span class="lbl"><code>{esc(c["name"])}</code></span>'
                     f'<span class="bar"><i style="width:{pct:.1f}%"></i></span>'
                     f'<span class="pct">{pct:.0f}%</span></li>')
    return ('<ul class="fill">' + "".join(items) + "</ul>"
            '<p class="note">The share of rows with a value in each column. A low bar is not an error: it is a '
            'thing most bodies do not publish.</p>')


_FILTER_SCRIPT = """<script>
(function () {
  var f = document.getElementById("ff"), tb = document.getElementById("frows"),
      st = document.getElementById("fstat"), dl = document.getElementById("fdl"), more = document.getElementById("fmore");
  if (!f || !window.fetch) return;
  var cols = JSON.parse(f.getAttribute("data-cols")), t = null, seq = 0;
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); };
  var show = function (v) { if (v === null || v === undefined) return ""; if (typeof v === "number") return v.toLocaleString("en-GB", {maximumFractionDigits: 2}); return esc(v); };
  var query = function () {
    var p = [];
    ["body", "year", "pollutant", "q"].forEach(function (k) { var el = f.elements[k]; if (el && el.value) p.push(k + "=" + encodeURIComponent(el.value)); });
    return p.join("&");
  };
  var run = function () {
    var qs = query(), id = ++seq;
    if (!qs) { location.reload(); return; }
    st.textContent = "Filtering…";
    fetch("/api/family/__FAM__?" + qs + "&limit=25").then(function (r) { return r.json(); }).then(function (d) {
      if (id !== seq) return;
      tb.innerHTML = d.rows.map(function (r) { return "<tr>" + cols.map(function (c) { return "<td>" + show(r[c]) + "</td>"; }).join("") + "</tr>"; }).join("") || '<tr><td colspan="' + cols.length + '">No rows match.</td></tr>';
      st.textContent = Math.min(d.rows_in_this_response, d.rows_matching).toLocaleString("en-GB") + " of " + d.rows_matching.toLocaleString("en-GB") + " matching rows shown.";
      dl.href = d.download_csv; dl.textContent = "Download these " + d.rows_matching.toLocaleString("en-GB") + " rows (CSV)";
      more.textContent = "Every column and receipt, for exactly the rows that match.";
    }).catch(function () { st.textContent = "The filter could not run; the download link still works."; });
  };
  f.addEventListener("submit", function (e) { e.preventDefault(); run(); });
  f.addEventListener("change", function (e) { if (e.target.tagName === "SELECT") run(); });
  f.elements.q.addEventListener("input", function () { clearTimeout(t); t = setTimeout(run, 350); });
})();
</script>"""


def render_family(family: str, site_url: str) -> str | None:
    s = load(family)
    if s is None:
        return None
    schema = _schema(family)
    rows = published_rows(family)          # capped at 50,000: enough for a preview
    h = _headline(s)
    total, by_pub, n_sources = h["total"], h["by_pub"], h["sources"]
    facets = s.get("facets") or {}

    crumb_html, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Combined data", "/combined"), (s["label"], None)], site_url)

    def _review_note(notes: str) -> str:
        # The reviewer's own sentences, if any, ahead of the proposer's description.
        parts = re.findall(r"Review (?:\d{4}-\d{2}-\d{2}|licence):.*?(?=Review (?:\d{4}-\d{2}-\d{2}|licence):|$)", notes, flags=re.S)
        text = " ".join(x.strip() for x in parts) if parts else notes
        return text[:480] + ("…" if len(text) > 480 else "")

    # What the reviewer recorded about a source travels with it: a publisher
    # whose header labels are mislabelled, a threshold read from the title,
    # a file layout that changed one year.
    notes_by_pub: dict[str, list[str]] = {}
    for e in s.get("sources", []):
        if e.get("ladder") != "published":
            continue
        who = e.get("body") or e["publisher"]
        if e.get("notes"):
            notes_by_pub.setdefault(who, []).append(e["notes"])
        if e.get("licence_note") or e.get("os_acknowledgement"):
            lic = "Review licence: " + (e.get("licence_note") or "")
            if e.get("os_acknowledgement"):
                lic += f" Carries the acknowledgement: {e['os_acknowledgement']}."
            notes_by_pub.setdefault(who, []).append(lic)
    bodies = "".join(
        f'<li>{esc(pub)} <b>{n:,}</b></li>'
        for pub, n in sorted(by_pub.items(), key=lambda kv: (-kv[1], kv[0])))
    review_notes = "".join(
        f'<li><b>{esc(pub)}</b> — {esc(_review_note(" ".join(notes)))}</li>'
        for pub, notes in sorted(notes_by_pub.items()))
    pending = []
    for e in s["sources"]:
        if e["ladder"] == "published":
            continue
        why = e.get("why") or e.get("intake_detail") or ""
        # a national network is not an index record: link its own site
        href = e.get("landing_url") if str(e.get("dataset_key", "")).startswith("network:") else dataset_path(e["dataset_key"])
        pending.append(
            f'<li><a href="{esc(href or "#")}">{esc(e["publisher"] or "")}</a> '
            f'<span class="note">— {esc(LADDER_TEXT.get(e["ladder"], e["ladder"]))}'
            f'{(": " + esc(why[:120])) if why and e["ladder"] in ("not admitted", "fetch failed", "mapping failed", "rejected") else ""}</span></li>')

    # A preview, not the table: a few rows and the columns that carry the
    # meaning. The download has every row with every receipt.
    cols = [c["name"] for c in schema["columns"]][:PREVIEW_COLS]
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)

    def _show(v) -> str:
        # 10000.0 is a stored float; a reader sees 10,000
        if isinstance(v, float):
            return f"{v:,.2f}".rstrip("0").rstrip(".")
        return "" if v is None else str(v)

    body = []
    for r in rows[:PREVIEW_ROWS]:
        body.append("<tr>" + "".join(f"<td>{esc(_show(r.get(c)))}</td>" for c in cols) + "</tr>")
    # Filters: a body, a year, a pollutant where there is one, a word. The
    # form's own action is the filtered CSV, so it works with no script;
    # the script turns the same form into a live preview and a download
    # link for exactly the rows shown.
    years = sorted((facets.get("years") or {}).keys(), reverse=True)
    pols = sorted(((facets.get("annual_mean") or {}).keys()))
    opts = lambda vals: "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in vals)
    filters = (
        f'<form class="filters" id="ff" method="get" action="/api/family/{esc(family)}.csv" data-cols="{esc(json.dumps(cols))}">'
        f'<label>Body<select name="body"><option value="">All {len(by_pub)} bodies</option>'
        f'{opts([p for p, _ in sorted(by_pub.items(), key=lambda kv: (-kv[1], kv[0]))])}</select></label>'
        + (f'<label>Year<select name="year"><option value="">All years</option>{opts(years)}</select></label>' if years else "")
        + (f'<label>Pollutant<select name="pollutant"><option value="">All</option>{opts(pols)}</select></label>' if len(pols) > 1 else "")
        + '<label>Contains<input name="q" type="search" placeholder="a supplier, a site, a street…" maxlength="80"></label>'
        + '<button type="submit">Filter</button></form>')
    preview = (filters
               + f'<p class="note" id="fstat">{min(PREVIEW_ROWS, len(rows))} of {total:,} rows and {len(cols)} of '
               f'{len(schema["columns"])} columns. The download has every column, with a receipt on each row: '
               'the publisher, the file and its hash, the source row, and the licence.</p>'
               f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody id="frows">{"".join(body)}</tbody></table></div>'
               f'<p class="dl-row"><a class="cta" id="fdl" href="/api/family/{esc(family)}.csv">Download all {total:,} rows (CSV{_size_note(family)})</a>'
               '<span class="note" id="fmore"></span></p>'
               + _FILTER_SCRIPT.replace("__FAM__", family))

    # The picture: a map where the rows have coordinates, else the years grid.
    figure = _map_svg(facets, total)
    strip = _strip_svg(facets, by_pub)
    if not figure:
        figure, strip = strip, ""
    qa = "".join(f"<dt>{esc(q)}</dt><dd>{esc(a)}</dd>" for q, a in _qa(family, s, schema, h))
    viz = (f'<section class="viz">{figure}'
           f'<div class="qa-wrap"><h2>What this table can tell you</h2><dl class="qa">{qa}</dl>'
           f'<p class="note">Every answer is computed from this table when it is built, and from nothing else.</p></div>'
           '</section>' if figure or qa else "")

    columns_doc = "".join(
        f'<li><code>{esc(c["name"])}</code> — {esc(c["meaning"])}</li>' for c in schema["columns"])
    rules = "".join(f"<li>{esc(r)}</li>" for r in schema.get("rules", []))
    lic = ", ".join(s.get("licences") or []) or "—"

    body_html = (
        crumb_html
        + f"<h1>{esc(s['label'])}</h1>"
        + f'<p class="lede">One table of {esc(schema["one_row_is"])}, from {h["bodies"]} public bodies&#39; published files.</p>'
        + '<div class="stat-row">'
          f'<div class="stat"><b>{total:,}</b><span>rows</span></div>'
          f'<div class="stat"><b>{h["bodies"]}</b><span>bodies in the table</span></div>'
          f'<div class="stat"><b>{n_sources}</b><span>datasets found in the catalogues</span></div>'
          f'<div class="stat"><b>{esc(_nice_date(h["built"]))}</b><span>last built</span></div>'
          '</div>'
        + _headline_tiles(facets)
        + f'<p class="dl-row"><a class="cta" href="/api/family/{esc(family)}.csv">Download CSV</a>'
          f'<a href="/api/family/{esc(family)}">JSON</a>'
          f'<a href="/who-publishes?name={esc(s["label"])}">Who publishes this</a>'
          f'<span class="note">Licence: {esc(lic)}</span></p>'
        + viz
        + (f"<h2>Years covered, by body</h2>{strip}" if strip else "")
        + "<h2>Preview</h2>" + preview
        + f"<h2>Bodies in the table</h2><ul class=\"bodies\">{bodies or '<li>none yet</li>'}</ul>"
        + (f"<h2>How complete each column is</h2>{_completeness(schema, facets, total)}" if facets else "")
        + (f'<details class="fold"><summary>Reviewer notes ({len(notes_by_pub)})</summary>'
           "<p class=\"note\">What a person recorded when checking how a body's file was read: a mislabelled header, "
           'a threshold taken from the title, a unit the file does not state.</p>'
           f'<ul class="notes">{review_notes}</ul></details>' if review_notes else "")
        + f'<details class="fold"><summary>Found in the catalogues but not in the table ({len(pending)} of {n_sources} datasets)</summary>'
          '<p class="note">A body appears here when it publishes this dataset but its file has not reached the table: '
          'the licence was not stated explicitly, the file could not be read, or the mapping is still waiting for review. '
          'That is a fact about the file, not a judgement of the body.</p>'
          f'<ul class="datasets">{"".join(pending) or "<li>none</li>"}</ul></details>'
        + '<details class="fold"><summary>Columns and rules</summary>'
          "<ul>" + columns_doc + "</ul>"
        + ("<h3>Rules this table keeps</h3><ul>" + rules + "</ul>" if rules else "")
        + "</details>"
        + '<p class="note">The original files come first: a combined table is a convenience built on them, published '
          'only where the licence explicitly allows it and a person has reviewed how the pieces were joined.</p>'
    )
    head_html = simple_head(
        f"{s['label']} — one table from {h['bodies']} UK public bodies",
        f"{total:,} rows of {s['label'].lower()} combined from {h['bodies']} public bodies' open data, "
        "with the source, licence and row of every entry.",
        f"/family/{family}", site_url, crumb_ld)
    return _page(head_html, body_html, "/combined")
