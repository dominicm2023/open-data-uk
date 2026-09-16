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
    by_ds: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_ds[(r.get("dataset_key") or "", r.get("as_of") or "")].append(r)
    out = []
    for (key, _snap), rs in by_ds.items():
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


def dept_key(name: str) -> str:
    """'Department for Environment, Food and Rural Affairs' and 'Department for
    Environment Food & Rural Affairs' are one department: bodies spell their
    parent in their own way. Lower-case, '&' as 'and', 'Her Majesty's' as
    'HM', punctuation gone."""
    n = (name or "").lower().replace("&", " and ")
    n = n.replace("her majesty's", "hm").replace("her majestys", "hm").replace("his majesty's", "hm").replace("his majestys", "hm")
    n = "".join(ch if ch.isalnum() or ch == " " else " " for ch in n)
    return " ".join(n.split())


def fold_departments(names) -> dict[str, str]:
    """Each spelling -> the most common spelling of the same department."""
    by_key: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for n in names:
        if n:
            by_key[dept_key(n)][n] += 1
    return {n: c.most_common(1)[0][0] for c in by_key.values() for n in c}


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
    fold = fold_departments(x["parent"] for x in out)
    for x in out:
        x["parent"] = fold.get(x["parent"], x["parent"])
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
        newest_of = {}
        for t in trees:
            newest_of[t["dataset_key"]] = max(newest_of.get(t["dataset_key"], ""), t["as_of"])
        n_all = len(trees)
        trees = [t for t in trees if t["as_of"] == newest_of[t["dataset_key"]]]
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
            + (f'<p class="note">{n_all - len(trees)} earlier snapshots of this body are in the table too (the 3D view can scrub through them); this page shows the newest.</p>' if n_all > len(trees) else "")
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
        + '<p class="dl-row"><a class="cta" href="/family/organograms/chart/3d">See it as one figure (3D)</a> '
          '<a href="/family/organograms">The family table</a> '
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


# --- the whole of government as one graph, for the 3D view ----------------------

def graph_from_rows(rows: list[dict], at: str | None = None) -> dict:
    """Every body's tree, flattened into parallel arrays the WebGL page can
    upload straight to the GPU: for each senior post its body, its parent's
    index (or -1), title, grade, pay floor, FTE, the FTE and senior posts
    beneath it, and the FTE of the junior groups that report to it. A body
    with two datasets contributes its newest snapshot only. Parents always
    precede children. No name, no contact detail: the columns are never
    read here."""
    by_body: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_body[r.get("body") or ""].append(r)
    depts: dict[str, dict] = {}
    bodies: list[dict] = []
    cols = {k: [] for k in ("body", "parent", "ref", "title", "grade", "pay", "fte", "below_fte", "below_senior", "junior_fte")}

    def add(node: dict, bi: int, parent: int) -> None:
        i = len(cols["title"])
        cols["body"].append(bi)
        cols["parent"].append(parent)
        cols["ref"].append(node["ref"] or "")
        cols["title"].append((node["title"] or "")[:90])
        cols["grade"].append(node["grade"] or "")
        lo = node.get("_pay_floor")
        cols["pay"].append(lo)
        cols["fte"].append(round(node["fte"] or 0, 2))
        cols["below_fte"].append(round(node.get("below_fte") or 0, 1))
        cols["below_senior"].append(node.get("below_senior") or 0)
        cols["junior_fte"].append(round(sum((j["fte"] or 0) for j in node["juniors"]), 1))
        for c in node["children"]:
            add(c, bi, i)

    newest: list[tuple[str, list[dict], dict]] = []
    for name in sorted(by_body):
        trees = trees_from_rows(by_body[name])
        if at:
            # the snapshot in force at that date: the newest one on or before it
            trees = [t for t in trees if t["as_of"] and t["as_of"] <= at]
        if not trees:
            continue
        # The newest snapshot — every dataset that carries it. The Ministry
        # of Defence publishes one organogram per top-level budget (Head
        # Office, Navy, Army, Air, Strategic Command…), all dated the same
        # day; the figure needs all of them, not the first.
        top = trees[0]["as_of"]
        same = [t for t in trees if t["as_of"] == top]
        merged = dict(same[0])
        merged["roots"] = [r for t in same for r in t["roots"]]
        merged["orphans"] = [r for t in same for r in t["orphans"]]
        merged["senior"] = sum(t["senior"] for t in same)
        merged["fte"] = sum(t["fte"] for t in same)
        merged["parent_department"] = _mode(t["parent_department"] for t in same)
        newest.append((name, by_body[name], merged))
    fold = fold_departments(t["parent_department"] or name for name, _, t in newest)
    for name, rs, t in newest:
        # the pay floor travels on the row, not the rendered band
        floors = {}
        for r in rs:
            if (r.get("level") or "").lower() == "senior":
                floors[str(r.get("post_reference") or "").strip()] = r.get("pay_floor_gbp")

        def stamp(n: dict) -> None:
            n["_pay_floor"] = floors.get(n["ref"])
            for c in n["children"]:
                stamp(c)
        dept = fold.get(t["parent_department"] or name, t["parent_department"] or name)
        di = depts.setdefault(dept, {"name": dept, "bodies": [], "i": len(depts)})["i"]
        bi = len(bodies)
        heads = t["roots"] or t["orphans"]
        bodies.append({"name": name, "dept": di, "fte": round(t["fte"], 1), "senior": t["senior"],
                       "as_of": t["as_of"], "head": (heads[0]["title"] if heads else "")})
        depts[dept]["bodies"].append(bi)
        for n in t["roots"] + t["orphans"]:
            stamp(n)
            add(n, bi, -1)
    return {"departments": [{"name": d["name"], "bodies": d["bodies"]} for d in sorted(depts.values(), key=lambda d: d["i"])],
            "bodies": bodies, "nodes": cols,
            "as_of": max((b["as_of"] for b in bodies), default=""), "at": at,
            "note": "Posts, not people. Pay is the floor of the published band; FTE figures are the bodies' own."}


_COLS = ('"body", "level", "post_reference", "job_title", "grade", "unit", "reports_to", "pay_floor_gbp", '
         '"pay_ceiling_gbp", "pay_band", "fte", "job_function", "as_of", "parent_department", "organisation", '
         '"dataset_key", "source_url"')


@functools.lru_cache(maxsize=64)
def _graph_cached(stamp: float, at: str | None = None) -> str:
    """The graph at a date, from each body's newest snapshot on or before it
    — read as those rows only (about 15,000 of 343,000), not the whole
    series — and kept on disk beside the family, so the four workers share
    one build per date rather than each spending six seconds."""
    import json
    cache = STORE / FAMILY / "graphs"
    cache.mkdir(exist_ok=True)
    f = cache / f"{int(stamp)}-{at or 'newest'}.json"
    if f.exists():
        return f.read_text(encoding="utf-8")
    db = _db()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if at:
            pairs = conn.execute("SELECT body, MAX(as_of) FROM rows WHERE as_of IS NOT NULL AND as_of != '' AND as_of <= ? GROUP BY body", (at,)).fetchall()
        else:
            pairs = conn.execute("SELECT body, MAX(as_of) FROM rows GROUP BY body").fetchall()
        rows = []
        for body, snap in pairs:
            if snap is None:
                rows += [dict(r) for r in conn.execute(f"SELECT {_COLS} FROM rows WHERE body = ? AND as_of IS NULL", (body,))]
            else:
                rows += [dict(r) for r in conn.execute(f"SELECT {_COLS} FROM rows WHERE body = ? AND as_of = ?", (body, snap))]
    finally:
        conn.close()
    out = json.dumps(graph_from_rows(rows, at), ensure_ascii=False, separators=(",", ":"))
    for old in cache.glob("*.json"):                    # a new build makes every older graph stale
        if not old.name.startswith(f"{int(stamp)}-"):
            old.unlink(missing_ok=True)
    f.write_text(out, encoding="utf-8")
    return out


def warm_graphs() -> int:
    """Build the graph for every half-year tick the scrubber offers, so the
    first visitor after a build waits for none of them. Run after the
    family builds (refresh.sh) and safe to run any time."""
    import json
    tl = timeline_json()
    if not tl:
        return 0
    dates = [d["date"] for d in json.loads(tl)["dates"] if d["bodies"] >= 3]
    if not dates:
        return 0
    ticks = []
    for y in range(int(dates[0][:4]), int(dates[-1][:4]) + 1):
        for md in ("-03-31", "-09-30"):
            d = f"{y}{md}"
            if dates[0] <= d <= dates[-1]:
                ticks.append(d)
    if not ticks or ticks[-1] != dates[-1]:
        ticks.append(dates[-1])
    graph_json(None)
    for d in ticks:
        graph_json(d)
    return len(ticks) + 1


def graph_json(at: str | None = None) -> str | None:
    db = _db()
    if not db.exists():
        return None
    return _graph_cached(db.stat().st_mtime, at or None)


@functools.lru_cache(maxsize=2)
def _timeline_cached(stamp: float) -> str:
    """Every snapshot date the family holds, with what stood at it: the
    scrubber's ticks. A date carried by fewer than three bodies is a
    body's own odd reporting day, not a government-wide snapshot."""
    import json
    db = _db()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT as_of, COUNT(DISTINCT body), COUNT(*), SUM(fte) FROM rows "
                            "WHERE level = ? AND as_of IS NOT NULL AND as_of != ? GROUP BY as_of ORDER BY as_of",
                            ("senior", "")).fetchall()
    finally:
        conn.close()
    dates = [{"date": d, "bodies": b, "senior": n, "fte": round(f or 0)} for d, b, n, f in rows if b >= 3]
    return json.dumps({"dates": dates, "note": "Senior posts only for earlier snapshots; junior groups are held for the newest."},
                      ensure_ascii=False, separators=(",", ":"))


def timeline_json() -> str | None:
    db = _db()
    if not db.exists():
        return None
    return _timeline_cached(db.stat().st_mtime)


def render_3d(site_url: str) -> str:
    """The full-screen WebGL view: one canvas, a small panel, our own script."""
    import hashlib
    js = Path(__file__).resolve().parent / "web" / "orgchart3d.js"
    ver = hashlib.sha1(js.read_bytes()).hexdigest()[:8] if js.exists() else "0"
    title = "The shape of the state"
    desc = ("Every senior post in UK central government as one 3D figure: bodies around their departments, "
            "posts by reporting line, height by pay band, size by the staff beneath. Drawn from the organograms "
            "the bodies publish.")
    body_html = (
        '<div id="stage" class="org3d">'
        '<canvas id="c" aria-label="Every senior post in UK central government, drawn as a three-dimensional figure"></canvas>'
        '<div id="labels" aria-hidden="true"></div>'
        '<div id="tip" class="org3d-tip" hidden></div>'
        '<nav id="crumbs" class="org3d-crumbs" aria-label="Where you are"></nav>'
        '<section id="panel" class="org3d-panel">'
        '<h1>The shape of the state</h1>'
        '<p id="sub" class="org3d-sub">Loading the organograms…</p>'
        '<p class="org3d-search"><input id="search" type="search" placeholder="Find a body or a post (press /)" autocomplete="off" '
        'aria-label="Find a body or a post"><ul id="hits" class="org3d-hits" hidden></ul></p>'
        '<div id="navhead" class="org3d-navhead"></div>'
        '<p class="org3d-ctl"><button id="upbtn" type="button" hidden>← Up one level (Esc)</button></p>'
        '<ul id="navlist" class="org3d-nav"></ul>'
        '<p class="org3d-legend"><span><i class="k-h"></i>height: pay band</span> <span><i class="k-s"></i>size: staff beneath</span> '
        '<span><i class="k-c"></i>colour: department</span></p>'
        '<p class="org3d-ctl">'
        '<button id="orbit" type="button" aria-pressed="true">Orbit: on</button> '
        '<button id="tour" type="button">Fly-through (F)</button> '
        '<button id="pillars" type="button" aria-pressed="true">Traffic: on</button> '
        '<button id="full" type="button">Full screen</button> '
        '<button id="rec" type="button">Record fly-through</button> '
        '<a id="dl" hidden download="shape-of-the-state.webm">Save video</a> '
        '<button id="reset" type="button">Start again</button> '
        '<button id="helpbtn" type="button" aria-label="Help">?</button></p>'
        '<div id="when-wrap" class="org3d-when" hidden><button id="play" type="button" aria-label="Play through the years">▶</button>'
        '<input id="when" type="range" min="0" max="0" value="0" aria-label="Snapshot date"><span id="whenlabel"></span></div>'
        '<p class="org3d-foot"><a href="/family/organograms/chart">Chart as a list</a> · <a href="/family/organograms">The table</a> '
        '· <span id="asof"></span></p>'
        '</section>'
        '<aside id="detail" class="org3d-detail" hidden><button id="closedetail" type="button" aria-label="Close">×</button><div id="detailbody"></div></aside>'
        '<aside id="help" class="org3d-help" hidden><button id="closehelp" type="button" aria-label="Close">×</button>'
        '<h2>How to move around the city</h2>'
        '<ul><li>Every building is a senior post: its footprint the staff beneath it, its height the pay band. Every department is an island, its area the staff it employs; every body a block on it.</li>'
        '<li>Islands of a kind lie together: the same ministry under its earlier names, the departments of one field, with ferry lanes between them. That grouping is ours, by name; the data says only which body sits under which department.</li>'
        '<li><b>Click</b> a building, a label, or a name in the list to open it: a department, then a body (its buildings re-form as an organisation chart), then the posts beneath a post.</li>'
        '<li><b>Click empty space</b>, press <b>Esc</b>, or use the trail at the top to go back up. The browser&#39;s back button works too.</li>'
        '<li><b>Drag</b> to turn, <b>wheel</b> or <b>+</b>/<b>−</b> to zoom right down into the streets, arrow keys to turn and tilt. <b>F</b> or Fly-through glides you down and round; Record captures that to a video.</li>'
        '<li><b>/</b> jumps to search: any body or post title.</li>'
        '<li>The slider at the foot of the panel scrubs through every snapshot since 2010 (<b>[</b> and <b>]</b> step it, ▶ plays): buildings that stood then keep their place, new ones rise, gone ones vanish. Earlier snapshots hold senior posts only.</li>'
        '<li>Height is the post&#39;s pay band, size is the staff beneath it, colour is the department. Posts, not people: no names are shown.</li></ul></aside>'
        '<p id="nogl" class="org3d-nogl" hidden>This view needs WebGL, which your browser has turned off. '
        '<a href="/family/organograms/chart">The chart as a list</a> has every post.</p>'
        '</div>'
        f'<script src="/orgchart3d.js?v={ver}" defer></script>')
    head_html = simple_head(title, desc, "/family/organograms/chart/3d", site_url)
    return _page(head_html, body_html, "/combined")


if __name__ == "__main__":
    import sys
    print(f"organograms: {warm_graphs()} graphs warm", file=sys.stderr)
