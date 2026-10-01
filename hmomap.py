"""The HMO map: licensed houses in multiple occupation, by postcode district.

  /family/hmo_registers/map      the page
  /api/family/hmo_registers/districts.geojson, areas.geojson   what it draws

Districts, not doors. The family table carries a postcode district on every
row and nothing finer, so this map cannot show a property and does not try:
at every scale each district is a shape filled by its count, and a click
says how many licences, under which council's register, of what kind.

The page is server-rendered and complete without its script: every number
the map shows is in the table beneath it. The script (web/hmomap.js) draws
with MapLibre GL JS, served from this site with the shapes; nothing is
asked of any other host.
"""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path

from pagerender import _page, breadcrumbs, esc, simple_head
from paths import DATA_DIR

FAMILY = "hmo_registers"
OUT = DATA_DIR / "families" / "out" / FAMILY
WEB = Path(__file__).parent / "web"
PATH = f"/family/{FAMILY}/map"


def geo_file(name: str) -> Path | None:
    p = OUT / name
    return p if name in ("districts.geojson", "areas.geojson") and p.is_file() else None


@functools.lru_cache(maxsize=2)
def _load(stamp: float) -> dict | None:
    try:
        doc = json.loads((OUT / "districts.geojson").read_text(encoding="utf-8"))
        summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = []
    for f in doc["features"]:
        p = f["properties"]
        if p.get("licences"):
            rows.append({"district": p["district"], "licences": p["licences"], "occupants": p.get("occupants") or 0,
                         "occupants_of": p.get("occupants_of") or 0,
                         "councils": json.loads(p["councils"]), "types": json.loads(p["types"])})
    rows.sort(key=lambda r: -r["licences"])
    councils: dict[str, dict] = {}
    for r in rows:
        for c in r["councils"]:
            e = councils.setdefault(c["council"], {"licences": 0, "districts": 0, "worked_out": 0, "as_of": c.get("as_of"),
                                                   "source_url": c.get("source_url")})
            e["licences"] += c["licences"]
            e["worked_out"] += c.get("worked_out", 0)
            e["districts"] += 1
    absent = [s for s in summary.get("sources", []) if s.get("ladder") in ("not admitted", "fetch failed", "extracted")]
    return {"rows": rows, "councils": councils, "absent": absent, "attribution": doc.get("attribution", ""),
            "no_shape": doc.get("districts_without_a_shape", []), "built_at": summary.get("built_at", "")}


COVERAGE = Path(__file__).parent / "families" / "registry" / f"{FAMILY}.coverage.json"
# Every housing authority, and where its register stands. The order is the
# order of usefulness to a reader: in the table, then open data we could
# read, then published in a form we cannot read, then not published.
STATUS = [
    ("in_table", "In this table"),
    ("open_file", "Published as open data, not yet in this table"),
    ("file_no_licence", "Published as a data file we could not use: the reason is beside each"),
    ("held", "Published, but the council's website says ‘All rights reserved’"),
    ("document", "Published as a PDF or web page we could not use: the reason is beside each"),
    ("search_only", "Published only as a search box on the council's website"),
    ("on_request", "Available only on request or for inspection"),
    ("not_found", "No register found online"),
    ("unsearched", "Not yet confirmed: the council's website refused our reader, or its register page could not be found"),
]


@functools.lru_cache(maxsize=2)
def _coverage(stamp: float) -> dict | None:
    try:
        return json.loads(COVERAGE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def coverage() -> dict | None:
    try:
        return _coverage(COVERAGE.stat().st_mtime)
    except OSError:
        return None


def _council_li(c: dict) -> str:
    name = esc(c["name"])
    if c.get("register_page"):
        name = f'<a href="{esc(c["register_page"])}">{name}</a>'
    note = f' <span class="org-meta">{esc(c["note"])}</span>' if c.get("note") else ""
    return f"<li>{name}{note}</li>"


def _worked_out_note(c: dict) -> str:
    """Beside a council whose register gives no postcode for some or all of
    its licences: how many were placed from their street or point instead."""
    n, total = c.get("worked_out", 0), c["licences"]
    if not n:
        return ""
    if n == total:
        return " · all placed from their street address or point: the register gives no postcodes"
    return f" · {n:,} placed from their street address or point, the register giving no postcode for them"


def _coverage_html() -> str:
    cov = coverage()
    if not cov:
        return ""
    by: dict[str, list] = {k: [] for k, _ in STATUS}
    for c in cov["councils"]:
        by.setdefault(c["status"], []).append(c)
    n = len(cov["councils"])
    parts = []
    for key, label in STATUS:
        rows = sorted(by.get(key, []), key=lambda c: c["name"])
        if not rows:
            continue
        items = "".join(_council_li(c) for c in rows)
        parts.append(f'<details class="hmo-cov"{" open" if key in ("in_table", "open_file") else ""}><summary>'
                     f'<b>{len(rows)}</b> {esc(label)}</summary><ul class="org-list">{items}</ul></details>')
    return ("<h2>Every council&#39;s register</h2>"
            f'<p class="note">Every one of the UK&#39;s {n} housing authorities must keep a public register of the HMOs it '
            'licenses. This is where each one publishes it, as far as a search of its website and the open data '
            f'catalogues found on {esc(cov.get("checked", ""))}. A link goes to the council&#39;s own page for its register.</p>'
            + "".join(parts))


def data() -> dict | None:
    try:
        return _load((OUT / "districts.geojson").stat().st_mtime)
    except OSError:
        return None


def _version(name: str) -> str:
    try:
        return hashlib.sha1((WEB / name).read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


_WHY = {
    "not admitted": "its licence does not let us",
    "fetch failed": "its file could not be fetched",
    "extracted": "it is published in a form we cannot read yet",
}


def render_map(site_url: str) -> str | None:
    d = data()
    if not d or not d["rows"]:
        return None
    total = sum(r["licences"] for r in d["rows"])
    crumb_html, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Combined data", "/combined"), ("HMO licence registers", f"/family/{FAMILY}"), ("Map", None)], site_url)
    title = "Map of licensed HMOs by postcode district"
    desc = (f"{total:,} licensed houses in multiple occupation on {len(d['councils'])} councils' public registers, "
            f"counted by postcode district across {len(d['rows'])} districts. Districts, not addresses.")
    councils = "".join(
        f'<li><a href="{esc(c["source_url"])}">{esc(name)}</a> <span class="org-meta">{c["licences"]:,} licences in '
        f'{c["districts"]} district{"" if c["districts"] == 1 else "s"}'
        + _worked_out_note(c)
        + (f' · register dated {esc(c["as_of"])}' if c.get("as_of") else " · the register states no date") + "</span></li>"
        for name, c in sorted(d["councils"].items(), key=lambda kv: -kv[1]["licences"]))
    seen, absent = set(), []
    for s in d["absent"]:
        key = (s["publisher"], s["ladder"])
        if key in seen:
            continue
        seen.add(key)
        absent.append(f'<li><a href="{esc(s.get("landing_url") or s.get("resource_url") or "#")}">{esc(s["publisher"])}</a> '
                      f'<span class="org-meta">{esc(_WHY.get(s["ladder"], s["ladder"]))}: {esc(str(s.get("intake_detail") or "")[:160])}</span></li>')
    trs = "".join(
        f'<tr data-district="{esc(r["district"])}"><th scope="row"><button type="button" class="hmo-go">{esc(r["district"])}</button></th>'
        f'<td class="num">{r["licences"]:,}</td>'
        f'<td>{esc(", ".join(c["council"] for c in r["councils"]))}</td>'
        f'<td>{esc("; ".join(f"{t}: {n:,}" for t, n in r["types"]))}</td>'
        f'<td class="num">{(format(r["occupants"], ",") if r["occupants_of"] else "—")}</td></tr>'
        for r in d["rows"])
    body_html = (
        crumb_html
        + "<h1>Licensed HMOs by postcode district</h1>"
        + f'<p class="lede">{total:,} licensed houses in multiple occupation, from the public registers of '
          f'{len(d["councils"])} councils, counted by postcode district. Each district is filled by how many it has; '
          'zoom in for its edges and click one to open it. It shows districts, never addresses: the table behind it holds '
          'no address, no full postcode and nobody&#39;s name.</p>'
        + '<div class="hmo-wrap"><div id="hmo-map" class="hmo-map" role="application" '
          'aria-label="Map of licensed HMOs by postcode district. The table below holds the same figures."></div>'
          '<aside id="hmo-panel" class="hmo-panel" aria-live="polite"><h2>Open a district</h2>'
          '<p class="note">Click a district on the map, or a district in the table below.</p></aside></div>'
        + '<p class="hmo-legend" id="hmo-legend" aria-hidden="true"></p>'
        + '<p id="hmo-nogl" class="note" hidden>The map needs WebGL, which this browser has turned off. '
          'Every figure it would show is in the table below.</p>'
        + f'<p class="dl-row"><a class="cta" href="/family/{FAMILY}">The table and downloads</a></p>'
        + "<h2>Whose registers these are</h2>"
        + f'<ul class="org-list">{councils}</ul>'
        + '<p class="note">A count is the licences on a council&#39;s register as it published it, not every HMO: smaller HMOs '
          'need a licence only where the council runs an additional scheme, and an unlicensed one is on no register. '
          'A district with no count is one these registers say nothing about, which is not the same as none.</p>'
        + _coverage_html()
        + "<h2>Every district</h2>"
        + '<div class="table-wrap"><table class="hmo-table"><thead><tr><th scope="col">District</th><th scope="col" class="num">Licences</th>'
          '<th scope="col">Council</th><th scope="col">Kind of licence, in the council&#39;s words</th>'
          '<th scope="col" class="num">People permitted</th></tr></thead>'
        + f"<tbody>{trs}</tbody></table></div>"
        + '<p class="note">People permitted is the sum of the most occupants each licence allows, where the register gives it.</p>'
        + f'<p class="note">{esc(d["attribution"])} The boundaries are approximate by their maker&#39;s own account. '
          'Drawn with MapLibre GL JS (BSD 3-Clause), served from this site.</p>'
        + f'<link rel="stylesheet" href="/maplibre-gl.css?v={_version("maplibre-gl.css")}">'
        + f'<script type="module" src="/hmomap.js?v={_version("hmomap.js")}"></script>')
    head_html = simple_head(title, desc, PATH, site_url, extra=crumb_ld)
    return _page(head_html, body_html, "/combined")
