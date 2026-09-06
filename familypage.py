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


def render_family(family: str, site_url: str) -> str | None:
    s = load(family)
    if s is None:
        return None
    schema = json.loads((Path(__file__).parent / "families" / "schema" / f"{family}.json").read_text(encoding="utf-8"))
    rows = published_rows(family)          # capped at 50,000: enough to show 200
    total = s.get("published_rows", len(rows))
    # Counts come from the build summary, never from the capped JSON: spend
    # over £500 is 588,006 rows and the page said 50,000 for an hour.
    by_pub: dict[str, int] = {}
    for e in s.get("sources", []):
        if e.get("ladder") == "published" and e.get("rows"):
            by_pub[e["publisher"]] = by_pub.get(e["publisher"], 0) + e["rows"]
    ladder = s.get("ladder", {})
    n_sources = sum(ladder.values())

    crumb_html, crumb_ld = breadcrumbs(
        [("Home", "/"), ("Who publishes what", "/who-publishes"), (s["label"], None)], site_url)

    # who is in, and who is not yet, with the reason
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
    contributing = "".join(
        f'<li>{esc(pub)} <span class="note">{n:,} rows</span>'
        + (f'<br><span class="note">{esc(_review_note(" ".join(notes_by_pub[pub])))}</span>' if pub in notes_by_pub else "")
        + "</li>"
        for pub, n in sorted(by_pub.items(), key=lambda kv: (-kv[1], kv[0])))
    pending = []
    for e in s["sources"]:
        if e["ladder"] == "published":
            continue
        why = e.get("why") or e.get("intake_detail") or ""
        pending.append(
            f'<li><a href="{esc(dataset_path(e["dataset_key"]))}">{esc(e["publisher"] or "")}</a> '
            f'<span class="note">— {esc(LADDER_TEXT.get(e["ladder"], e["ladder"]))}'
            f'{(": " + esc(why[:120])) if why and e["ladder"] in ("not admitted", "fetch failed", "mapping failed", "rejected") else ""}</span></li>')

    # the table: first 200 rows on the page, the rest by download
    cols = [c["name"] for c in schema["columns"]]
    head = "".join(f"<th>{esc(c)}</th>" for c in cols) + "<th>publisher</th><th>source</th>"
    body = []
    for r in rows[:200]:
        cells = "".join(f"<td>{esc('' if r.get(c) is None else str(r.get(c)))}</td>" for c in cols)
        body.append(f'<tr>{cells}<td>{esc(r["publisher"])}</td>'
                    f'<td><a href="{esc(r["source_url"])}" rel="noopener">row {r["source_row"]}</a></td></tr>')
    table = (f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
             f'<tbody>{"".join(body)}</tbody></table></div>'
             + (f'<p class="note">Showing 200 of {total:,} rows; the CSV download has all of them.</p>'
                if total > 200 else ""))

    columns_doc = "".join(
        f'<li><code>{esc(c["name"])}</code> — {esc(c["meaning"])}</li>' for c in schema["columns"])
    rules = "".join(f"<li>{esc(r)}</li>" for r in schema.get("rules", []))
    lic = ", ".join(s.get("licences") or []) or "—"

    body_html = (
        crumb_html
        + f"<h1>{esc(s['label'])}: one table</h1>"
        + f'<p class="lede">{total:,} rows from {len(by_pub)} public bodies, combined from their own published files '
          f'into one schema. Every row keeps its receipt: the publisher, the file, its hash, the row it came from, and the licence.</p>'
        + '<p class="note">The original files come first — each contributing body is linked below, and the table is a '
          'convenience built on them, published only where the licence explicitly allows it and a person has reviewed how '
          f'the pieces were joined. Licences in this table: {esc(lic)}. '
          f'<a href="/api/family/{esc(family)}.csv">Download CSV</a> · <a href="/api/family/{esc(family)}">JSON</a> · '
          f'<a href="/who-publishes?name={esc(s["label"])}">Who publishes this</a>.</p>'
        + f"<h2>Contributing bodies ({len(by_pub)})</h2><ul class=\"cols\">{contributing or '<li>none yet</li>'}</ul>"
        + f"<h2>Publish it, but not in the table yet ({len(pending)} of {n_sources} sources)</h2>"
        + '<p class="note">A body appears here when it publishes this dataset but its file has not reached the table: '
          'the licence was not stated explicitly, the file could not be read, or the mapping is still waiting for review. '
          'That is a fact about the file, not a judgement of the body.</p>'
        + f'<ul class="datasets">{"".join(pending) or "<li>none</li>"}</ul>'
        + "<h2>The table</h2>" + table
        + "<h2>What the columns mean</h2><ul>" + columns_doc + "</ul>"
        + ("<h2>Rules this table keeps</h2><ul>" + rules + "</ul>" if rules else "")
        + f'<p class="note">Built {esc(s["built_at"][:10])}. One row is {esc(schema["one_row_is"])}.</p>'
    )
    head_html = simple_head(
        f"{s['label']} — one table from {len(by_pub)} UK public bodies",
        f"{total:,} rows of {s['label'].lower()} combined from {len(by_pub)} publishers' own open data, "
        "with the source, licence and row of every entry.",
        f"/family/{family}", site_url, crumb_ld)
    return _page(head_html, body_html, "/who-publishes")
