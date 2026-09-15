"""The organisation chart drawn from the organograms family.

Every senior row carries the reference of the post it reports to, and every
junior row the senior post its group hangs off, so a body's chart is a tree
walk over its own published rows — nothing is inferred. Two views:

  /family/organograms/chart            every body, grouped by the parent
                                       department its file names, with the
                                       post at the top of each
  /family/organograms/chart?body=...   one body's tree: senior posts nested
                                       by reporting line, junior groups
                                       under the post they report to

Rendered on the server as nested <details>, so the page is one self-
contained document: no script, nothing fetched, and every node crawlable.
The table is posts, not people (FAMILIES.md), and so is the chart.
"""

from __future__ import annotations

import collections
import functools
import sqlite3
from pathlib import Path

from pagerender import _page, breadcrumbs, esc, simple_head
from paths import DATA_DIR

STORE = DATA_DIR / "families" / "out"
FAMILY = "organograms"
HEAD_REFS = {"", "xx", "n/a", "none", "-"}
GRADE_ORDER = {"scs4": 0, "scs3": 1, "scs2": 2, "scs1a": 3, "scs1": 4}


def _db() -> Path:
    return STORE / FAMILY / f"{FAMILY}.sqlite"


def _grade_rank(g: str | None) -> int:
    return GRADE_ORDER.get((g or "").replace(" ", "").lower(), 9)


def _pay(r: dict) -> str:
    lo, hi = r.get("pay_floor_gbp"), r.get("pay_ceiling_gbp")
    if lo is None and hi is None:
        return r.get("pay_band") or ""
    if lo is not None and hi is not None:
        return f"£{lo:,.0f}–£{hi:,.0f}"
    return f"£{(lo if lo is not None else hi):,.0f}"


def _fte(v) -> str:
    if v is None:
        return ""
    return f"{v:,.2f}".rstrip("0").rstrip(".")


# --- the tree, from rows ---------------------------------------------------

def trees_from_rows(rows: list[dict]) -> list[dict]:
    """One tree per dataset the body's rows came from (a body may publish
    two organograms, an old and a current), newest snapshot first.

    A node is a senior post; its children are the senior posts whose
    reports_to is its reference and the junior groups that report to it.
    A post whose reports_to is 'XX', blank, or a reference no row carries
    is a root: the head of the body, or a post whose line is not stated —
    the chart says which.
    """
    by_ds: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_ds[r.get("dataset_key") or ""].append(r)
    out = []
    for key, rs in by_ds.items():
        seniors = [r for r in rs if (r.get("level") or "").lower() == "senior"]
        juniors = [r for r in rs if (r.get("level") or "").lower() != "senior"]
        nodes: dict[str, dict] = {}
        for r in seniors:
            ref = str(r.get("post_reference") or "").strip()
            node = {"ref": ref, "title": r.get("job_title") or "", "grade": r.get("grade") or "",
                    "unit": r.get("unit") or "", "pay": _pay(r), "fte": r.get("fte"),
                    "function": r.get("job_function") or "", "reports_to": str(r.get("reports_to") or "").strip(),
                    "children": [], "juniors": [], "source_url": r.get("source_url") or ""}
            # a reference used twice keeps both posts, the second under a suffixed key
            k = ref or f"_{len(nodes)}"
            while k in nodes:
                k += "'"
            nodes[k] = node
        roots, orphans = [], []
        for k, node in nodes.items():
            parent = node["reports_to"]
            if parent.lower() in HEAD_REFS:
                roots.append(node)
            elif parent in nodes and nodes[parent] is not node:
                nodes[parent]["children"].append(node)
            else:
                orphans.append(node)
        for r in juniors:
            g = {"title": r.get("job_title") or "", "grade": r.get("grade") or "", "pay": _pay(r),
                 "fte": r.get("fte"), "unit": r.get("unit") or ""}
            parent = str(r.get("reports_to") or "").strip()
            if parent in nodes:
                nodes[parent]["juniors"].append(g)
            else:
                orphans.append({"ref": "", "title": g["title"], "grade": g["grade"], "unit": g["unit"], "pay": g["pay"],
                                "fte": g["fte"], "function": "", "reports_to": parent, "children": [], "juniors": [],
                                "source_url": r.get("source_url") or "", "junior_group": True})

        def rollup(n: dict) -> tuple[float, int]:
            fte = n["fte"] or 0.0
            senior = 0 if n.get("junior_group") else 1
            for j in n["juniors"]:
                fte += j["fte"] or 0.0
            for c in n["children"]:
                f2, s2 = rollup(c)
                fte += f2
                senior += s2
            n["below_fte"], n["below_senior"] = fte, senior
            return fte, senior

        def sort(n: dict) -> None:
            n["children"].sort(key=lambda c: (_grade_rank(c["grade"]), -(c.get("below_fte") or 0), c["title"]))
            n["juniors"].sort(key=lambda j: (_grade_rank(j["grade"]), j["grade"], -(j["fte"] or 0)))
            for c in n["children"]:
                sort(c)
        for n in roots + orphans:
            rollup(n)
            sort(n)
        roots.sort(key=lambda n: (_grade_rank(n["grade"]), -(n.get("below_fte") or 0)))
        orphans.sort(key=lambda n: (_grade_rank(n["grade"]), -(n.get("below_fte") or 0)))
        as_of = max((r.get("as_of") or "" for r in rs), default="")
        out.append({"dataset_key": key, "as_of": as_of, "roots": roots, "orphans": orphans,
                    "senior": len(seniors), "junior_groups": len(juniors),
                    "fte": sum((r.get("fte") or 0.0) for r in rs),
                    "source_url": next((r.get("source_url") for r in seniors + juniors if r.get("source_url")), ""),
                    "parent_department": _mode(r.get("parent_department") for r in rs),
                    "organisation": _mode(r.get("organisation") for r in rs)})
    out.sort(key=lambda t: t["as_of"], reverse=True)
    return out


def _mode(values) -> str:
    c = collections.Counter(v for v in values if v)
    return c.most_common(1)[0][0] if c else ""


# --- reading the family ------------------------------------------------------

def rows_for(body: str) -> list[dict]:
    db = _db()
    if not db.exists():
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute('SELECT * FROM rows WHERE "body" = ?', (body,))]
    finally:
        conn.close()


@functools.lru_cache(maxsize=4)
def _overview_cached(stamp: float) -> list[dict]:
    db = _db()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        bodies = collections.defaultdict(lambda: {"senior": 0, "junior_groups": 0, "fte": 0.0, "as_of": "",
                                                  "heads": [], "parent": collections.Counter(), "datasets": set()})
        for r in conn.execute('SELECT "body", "level", "fte", "as_of", "reports_to", "job_title", "grade", '
                              '"parent_department", "dataset_key" FROM rows'):
            b = bodies[r["body"]]
            b["datasets"].add(r["dataset_key"])
            if (r["level"] or "").lower() == "senior":
                b["senior"] += 1
                if str(r["reports_to"] or "").strip().lower() in HEAD_REFS:
                    b["heads"].append((r["as_of"] or "", _grade_rank(r["grade"]), r["job_title"] or "", r["grade"] or ""))
            else:
                b["junior_groups"] += 1
            b["fte"] += r["fte"] or 0.0
            b["as_of"] = max(b["as_of"], r["as_of"] or "")
            if r["parent_department"]:
                b["parent"][r["parent_department"]] += 1
    finally:
        conn.close()
    out = []
    for name, b in bodies.items():
        heads = sorted(b["heads"], key=lambda h: (h[0] != b["as_of"], h[1], h[2]))
        out.append({"body": name, "senior": b["senior"], "junior_groups": b["junior_groups"], "fte": b["fte"],
                    "as_of": b["as_of"], "datasets": len(b["datasets"]),
                    "head": (heads[0][2], heads[0][3]) if heads else None,
                    "parent": b["parent"].most_common(1)[0][0] if b["parent"] else ""})
    out.sort(key=lambda x: -x["fte"])
    return out


def overview() -> list[dict]:
    """Every body in the table: its FTE, senior posts, the post at its top
    and the parent department its file names. Cached per build."""
    db = _db()
    if not db.exists():
        return []
    return _overview_cached(db.stat().st_mtime)


# --- rendering ------------------------------------------------------------------

def _node_html(n: dict, depth: int) -> str:
    kids = n["children"]
    juniors = n["juniors"]
    meta = " · ".join(x for x in (esc(n["grade"]), esc(n["pay"]), f"FTE {esc(_fte(n['fte']))}" if n["fte"] is not None else "") if x)
    below = ""
    if n.get("below_fte") and (kids or juniors):
        below = (f'<span class="org-below">{n["below_fte"]:,.0f} FTE beneath'
                 + (f", {n['below_senior'] - 1:,} senior posts" if n["below_senior"] > 1 else "") + "</span>")
    summary = (f'<summary><span class="org-title">{esc(n["title"]) or "(untitled post)"}</span>'
               f'<span class="org-meta">{meta}</span>{below}'
               + (f'<span class="org-unit">{esc(n["unit"])}</span>' if n["unit"] else "") + "</summary>")
    inner = ""
    if n.get("function"):
        inner += f'<p class="org-fn">{esc(n["function"][:400])}</p>'
    if juniors:
        inner += ('<table class="org-juniors"><thead><tr><th>Grade</th><th>Posts (generic title)</th>'
                  '<th class="num">FTE</th><th>Pay scale</th></tr></thead><tbody>'
                  + "".join(f'<tr><td>{esc(j["grade"])}</td><td>{esc(j["title"])}</td>'
                            f'<td class="num">{esc(_fte(j["fte"]))}</td><td>{esc(j["pay"])}</td></tr>' for j in juniors)
                  + "</tbody></table>")
    if kids:
        inner += "".join(_node_html(c, depth + 1) for c in kids)
    if not inner:
        return f'<div class="org-node org-leaf">{summary.replace("<summary>", "<div class=\"org-sum\">").replace("</summary>", "</div>")}</div>'
    open_attr = " open" if depth < 1 else ""
    return f'<details class="org-node"{open_attr}>{summary}{inner}</details>'


def render_chart(site_url: str, body: str | None) -> str | None:
    """The chart page: one body's tree, or every body by parent department."""
    if body:
        rows = rows_for(body)
        if not rows:
            return None
        trees = trees_from_rows(rows)
        crumb_html, crumb_ld = breadcrumbs(
            [("Home", "/"), ("Combined data", "/combined"), ("Organograms", "/family/organograms"),
             ("Organisation chart", "/family/organograms/chart"), (body, None)], site_url)
        parts = []
        for t in trees:
            head_note = ""
            if not t["roots"] and t["orphans"]:
                head_note = "<p class=\"note\">No post in this file reports to 'XX', so the file does not say which post is at the top; the posts below are listed with the reporting line as published.</p>"
            parts.append(
                f'<section class="org-file"><h2>{esc(t["organisation"] or body)}'
                + (f' <span class="org-asof">as of {esc(_nice(t["as_of"]))}</span>' if t["as_of"] else "") + "</h2>"
                + f'<p class="stats">{t["senior"]:,} senior posts, {t["junior_groups"]:,} junior groups, {t["fte"]:,.0f} FTE in all'
                + (f' · parent department: {esc(t["parent_department"])}' if t["parent_department"] and t["parent_department"] != body else "")
                + (f' · <a href="{esc(t["source_url"])}">the body\'s own file</a>' if t["source_url"] else "") + "</p>"
                + head_note
                + "".join(_node_html(n, 0) for n in t["roots"])
                + (('<h3>Posts whose reporting line is not in the file</h3>' + "".join(_node_html(n, 0) for n in t["orphans"])) if t["orphans"] else "")
                + "</section>")
        title = f"{body}: organisation chart"
        desc = (f"The posts, grades and pay bands of {body}, nested by reporting line as the body published them "
                "in its organogram. Posts, not people.")
        body_html = (
            crumb_html
            + f"<h1>{esc(body)}</h1>"
            + '<p class="lede">The organisation chart as the body published it: senior posts nested by the post they '
              'report to, junior groups under the senior post they report to. Posts, not people — no names are shown.</p>'
            + f'<p class="dl-row"><a href="/family/organograms/chart">All bodies</a> '
              f'<a href="/api/family/organograms.csv?body={esc(body)}">Download this body\'s rows (CSV)</a> '
              f'<a href="/family/organograms">The family table</a></p>'
            + "".join(parts)
            + '<p class="note">Open a post to see the posts and groups beneath it. Pay is the band the body published: '
              'senior posts in £5,000 bands, junior groups as the grade\'s scale. FTE is the body\'s own figure.</p>')
        head_html = simple_head(title, desc, f"/family/organograms/chart?body={esc(body)}", site_url,
                                extra=crumb_ld + '<meta name="robots" content="noindex,follow">')
        return _page(head_html, body_html, "/combined")

    ov = overview()
    if not ov:
        return None
    crumb_html, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Combined data", "/combined"), ("Organograms", "/family/organograms"),
         ("Organisation chart", None)], site_url)
    by_parent: dict[str, list[dict]] = collections.defaultdict(list)
    for b in ov:
        by_parent[b["parent"] or b["body"]].append(b)
    groups = sorted(by_parent.items(), key=lambda kv: -sum(x["fte"] for x in kv[1]))
    sections = []
    for parent, bodies in groups:
        bodies.sort(key=lambda x: (x["body"] != parent, -x["fte"]))
        items = "".join(
            f'<li><a href="/family/organograms/chart?body={esc(b["body"])}">{esc(b["body"])}</a>'
            + (f' <span class="org-head">— {esc(b["head"][0])}' + (f' ({esc(b["head"][1])})' if b["head"][1] else "") + "</span>" if b["head"] else "")
            + f'<span class="org-meta">{b["fte"]:,.0f} FTE · {b["senior"]:,} senior posts'
            + (f' · as of {esc(_nice(b["as_of"]))}' if b["as_of"] else "") + "</span></li>"
            for b in bodies)
        total = sum(b["fte"] for b in bodies)
        sections.append(f'<section class="org-dept"><h2>{esc(parent)} <span class="org-asof">{total:,.0f} FTE across {len(bodies)} bod{"y" if len(bodies) == 1 else "ies"}</span></h2><ul class="org-list">{items}</ul></section>')
    n_bodies, fte = len(ov), sum(b["fte"] for b in ov)
    title = "UK government organisation chart"
    desc = (f"{n_bodies} public bodies by parent department, each with the post at its top and its FTE, "
            "from the organograms they publish. Open a body for its full chart.")
    body_html = (
        crumb_html
        + "<h1>Organisation chart</h1>"
        + f'<p class="lede">{n_bodies} public bodies, {fte:,.0f} full-time-equivalent posts, grouped by the parent department '
          'each body names in its own organogram. Open a body for every senior post nested by reporting line, with the '
          'junior groups beneath. Posts, not people — no names are shown.</p>'
        + '<p class="dl-row"><a href="/family/organograms">The family table</a> '
          '<a href="/api/family/organograms.csv">Download every row (CSV)</a></p>'
        + "".join(sections)
        + '<p class="note">A body appears under the parent department its file names; a department appears under itself. '
          'The post at the top is the senior post whose reporting line is "XX" in the newest file; where none is, none is shown. '
          'Bodies whose organogram is old are shown as old, not refreshed by us.</p>')
    head_html = simple_head(title, desc, "/family/organograms/chart", site_url, extra=crumb_ld)
    return _page(head_html, body_html, "/combined")


def _nice(iso: str) -> str:
    try:
        from datetime import date
        d = date.fromisoformat(iso[:10])
        return f"{d.day} {d:%B %Y}"
    except ValueError:
        return iso
