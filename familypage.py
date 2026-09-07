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


FAMILY_ORDER = ["recycling_centres", "air_quality_annual", "spend_over_500"]
PREVIEW_ROWS = 8
PREVIEW_COLS = 6


def _schema(family: str) -> dict:
    return json.loads((Path(__file__).parent / "families" / "schema" / f"{family}.json").read_text(encoding="utf-8"))


def _headline(s: dict) -> dict:
    """The numbers a page leads with, all from the build summary."""
    by_pub: dict[str, int] = {}
    for e in s.get("sources", []):
        if e.get("ladder") == "published" and e.get("rows"):
            by_pub[e["publisher"]] = by_pub.get(e["publisher"], 0) + e["rows"]
    ladder = s.get("ladder", {})
    return {"total": s.get("published_rows", 0), "by_pub": by_pub, "bodies": len(by_pub),
            "sources": sum(ladder.values()), "built": (s.get("built_at") or "")[:10]}


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


def render_family(family: str, site_url: str) -> str | None:
    s = load(family)
    if s is None:
        return None
    schema = _schema(family)
    rows = published_rows(family)          # capped at 50,000: enough for a preview
    h = _headline(s)
    total, by_pub, n_sources = h["total"], h["by_pub"], h["sources"]

    crumb_html, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Combined data", "/combined"), (s["label"], None)], site_url)

    def _review_note(notes: str) -> str:
        # The reviewer's own sentences, if any, ahead of the proposer's description.
        parts = re.findall(r"Review \d{4}-\d{2}-\d{2}:.*?(?=Review \d{4}-\d{2}-\d{2}:|$)", notes, flags=re.S)
        text = " ".join(x.strip() for x in parts) if parts else notes
        return text[:480] + ("…" if len(text) > 480 else "")

    # What the reviewer recorded about a source travels with it: a publisher
    # whose header labels are mislabelled, a threshold read from the title,
    # a file layout that changed one year.
    notes_by_pub: dict[str, list[str]] = {}
    for e in s.get("sources", []):
        if e.get("ladder") == "published" and e.get("notes"):
            notes_by_pub.setdefault(e["publisher"], []).append(e["notes"])
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
        pending.append(
            f'<li><a href="{esc(dataset_path(e["dataset_key"]))}">{esc(e["publisher"] or "")}</a> '
            f'<span class="note">— {esc(LADDER_TEXT.get(e["ladder"], e["ladder"]))}'
            f'{(": " + esc(why[:120])) if why and e["ladder"] in ("not admitted", "fetch failed", "mapping failed", "rejected") else ""}</span></li>')

    # A preview, not the table: a few rows and the columns that carry the
    # meaning. The download has every row with every receipt.
    cols = [c["name"] for c in schema["columns"]][:PREVIEW_COLS]
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = []
    def _show(v) -> str:
        # 10000.0 is a stored float; a reader sees 10,000
        if isinstance(v, float):
            return f"{v:,.2f}".rstrip("0").rstrip(".")
        return "" if v is None else str(v)

    for r in rows[:PREVIEW_ROWS]:
        body.append("<tr>" + "".join(f"<td>{esc(_show(r.get(c)))}</td>" for c in cols) + "</tr>")
    preview = (f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
               f'<p class="note">{min(PREVIEW_ROWS, len(rows))} of {total:,} rows and {len(cols)} of '
               f'{len(schema["columns"])} columns. The download has all of them, with a receipt on every row: '
               'the publisher, the file and its hash, the source row, and the licence.</p>')

    columns_doc = "".join(
        f'<li><code>{esc(c["name"])}</code> — {esc(c["meaning"])}</li>' for c in schema["columns"])
    rules = "".join(f"<li>{esc(r)}</li>" for r in schema.get("rules", []))
    lic = ", ".join(s.get("licences") or []) or "—"

    body_html = (
        crumb_html
        + f"<h1>{esc(s['label'])}</h1>"
        + f'<p class="lede">One table of {esc(schema["one_row_is"])}, from {len(by_pub)} public bodies&#39; own published files.</p>'
        + '<div class="stat-row">'
          f'<div class="stat"><b>{total:,}</b><span>rows</span></div>'
          f'<div class="stat"><b>{len(by_pub)}</b><span>bodies in the table</span></div>'
          f'<div class="stat"><b>{n_sources}</b><span>bodies that publish it</span></div>'
          f'<div class="stat"><b>{esc(_nice_date(h["built"]))}</b><span>last built</span></div>'
          '</div>'
        + f'<p class="dl-row"><a class="cta" href="/api/family/{esc(family)}.csv">Download CSV</a>'
          f'<a href="/api/family/{esc(family)}">JSON</a>'
          f'<a href="/who-publishes?name={esc(s["label"])}">Who publishes this</a>'
          f'<span class="note">Licence: {esc(lic)}</span></p>'
        + "<h2>Preview</h2>" + preview
        + f"<h2>Bodies in the table</h2><ul class=\"bodies\">{bodies or '<li>none yet</li>'}</ul>"
        + (f'<details class="fold"><summary>Reviewer notes ({len(notes_by_pub)})</summary>'
           "<p class=\"note\">What a person recorded when checking how a body's file was read: a mislabelled header, "
           'a threshold taken from the title, a unit the file does not state.</p>'
           f'<ul class="notes">{review_notes}</ul></details>' if review_notes else "")
        + f'<details class="fold"><summary>Publish it, but not in the table yet ({len(pending)} of {n_sources})</summary>'
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
        f"{s['label']} — one table from {len(by_pub)} UK public bodies",
        f"{total:,} rows of {s['label'].lower()} combined from {len(by_pub)} publishers' own open data, "
        "with the source, licence and row of every entry.",
        f"/family/{family}", site_url, crumb_ld)
    return _page(head_html, body_html, "/combined")
