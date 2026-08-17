"""Which UK councils do we actually hold data from, and which are missing?

Every council is a potential source, and until now "find more sources" meant
guessing. This turns it into a checklist: all 361 UK local authorities from
the ONS register, each marked with what we hold for it.

Four states, and the distinctions matter:

  own         we harvest that council's own data portal
  hub         we hold their data through a regional hub someone else runs —
              the London Datastore, Scotland's Spatial Hub, OpenDataNI
  aggregator  we hold it only through data.gov.uk's copy
  none        we hold nothing at all under that council's name

None of the middle states is a failure: a council publishing through its
regional hub or through data.gov.uk is doing the right thing, and for a small
district it is the sensible thing. They are search signals, not scores.

The first cut of this collapsed "own" and "hub" into one state, which quietly
credited Brent for appearing in the London Datastore and Norfolk's three
districts for their county's portal — and hid the only question worth asking:
does this council publish somewhere we don't look?

Matching is deliberately strict: a publisher name must reduce to the council's
own words and add none of its own, so "Durham County Council" matches County
Durham while "Durham University" does not. It will undercount rather than
claim coverage we can't demonstrate.

Usage:
    python scripts/council_coverage.py                 # refresh + report
    python scripts/council_coverage.py --offline       # use the cached list
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from dedupe import norm, who  # noqa: E402  (same "strip the admin wrapper" rule)
from agent import HEADERS  # noqa: E402
from paths import connect as db_connect  # noqa: E402

ROOT = Path(__file__).parent.parent
CACHE = ROOT / "councils.json"
OUT = ROOT / "COUNCIL_COVERAGE.md"
# Machine-readable twin of the markdown, so source discovery can be
# pointed straight at the gaps instead of guessing at all 361.
OUT_JSON = ROOT / "council_coverage.json"
AGGREGATOR = "data_gov_uk"

UA = HEADERS
# Local Authority Districts (December 2025) — the same ONS table the gazetteer
# is built from, so the two can never disagree about what a council is called.
LAD_CSV = ("https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/"
           "items/92150c7aa60540c5814abe3b26bce6d0/csv?layers=0")

NATIONS = {"E": "England", "N": "Northern Ireland",
           "S": "Scotland", "W": "Wales"}

# Platform noise, on top of the administrative wrapper dedupe.who() strips.
# Councils name their portals after the software: "Aberdeen City Council
# ArcGIS Online" is Aberdeen, and treating "arcgis" as part of its identity
# would have us report Aberdeen as uncovered while we harvest it nightly.
# Kept here rather than in dedupe.py — merging two datasets is a stricter
# judgement than recognising a council, and should stay stricter.
_PLATFORM_WORDS = {
    "arcgis", "agol", "online", "hub", "portal", "geoportal", "gis", "maps", "map",
    "open", "opendata", "data", "datastore", "dataworks", "datashare",
    "insight", "insights", "observatory", "spatial", "statistics", "stats",
    "digital", "web", "site", "team", "team's", "publisher", "account",
}


def identity(name: str) -> frozenset[str]:
    """The words that say which council this is, ignoring platform branding.

    The fallback exists for City of London, whose every word — "city", "of",
    "london" — is on a noise list, so it reduced to the empty set and could
    never match any publisher. It was recorded as publishing nothing while
    the index held 195 of its datasets, and that false negative was on the
    published coverage page. When stripping noise leaves nothing, keep the
    name's own words instead: a name made entirely of common words still
    identifies one council, and matching is exact-set equality, so a wider
    set cannot collide with a narrower one.
    """
    words = frozenset(who(name)) - _PLATFORM_WORDS
    if words:
        return words
    return frozenset(norm(name).split()) - _PLATFORM_WORDS


def fetch_councils() -> list[dict]:
    r = requests.get(LAD_CSV, headers=UA, timeout=180)
    r.raise_for_status()
    rows = list(csv.DictReader(
        io.StringIO(r.content.decode("utf-8-sig", errors="replace"))))
    if not rows:
        raise SystemExit("ONS returned an empty table")
    name_col = next(c for c in rows[0] if c.upper().startswith("LAD")
                    and c.upper().endswith("NM") and not c.upper().endswith("NMW"))
    code_col = next(c for c in rows[0] if c.upper().startswith("LAD")
                    and c.upper().endswith("CD"))
    out = [{"code": r[code_col], "name": r[name_col],
            "nation": NATIONS.get(r[code_col][:1], "?")}
           for r in rows if r.get(code_col) and r.get(name_col)]
    out.sort(key=lambda c: (c["nation"], c["name"]))
    CACHE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load_councils(offline: bool) -> list[dict]:
    if offline and CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return fetch_councils()


def source_identities() -> dict[str, frozenset]:
    """Which council, if any, each source in the registry belongs to.

    A source is a council's own when its name reduces to that council's own
    words. "Stirling Council Open Data" -> {stirling}. "London Datastore"
    -> {london}, which is no single borough's.
    """
    src = yaml.safe_load(open(ROOT / "sources.yaml", encoding="utf-8"))["sources"]
    # From the name only. Folding the id in poisoned 33 of 199 sources:
    # generated ids are truncated to a fixed length, so
    # "agol_northumberland_county_counci" contributed the fragment "counci",
    # which who() does not recognise as an administrative wrapper and so could
    # not strip. The identity then failed to equal the council's, and eight
    # councils that do run their own portal — Northumberland, East Riding,
    # North Northamptonshire, Three Rivers, West Oxfordshire and three
    # Northern Irish boroughs — were filed as publishing through someone
    # else's.
    return {s["id"]: identity(s["name"]) for s in src}


def publisher_index(conn) -> dict[frozenset, dict]:
    """Every publisher we hold, keyed by its distinctive words."""
    index: dict[frozenset, dict] = {}
    rows = conn.execute(
        "SELECT publisher, source_id, COUNT(*) FROM datasets "
        "WHERE publisher IS NOT NULL AND TRIM(publisher) <> '' "
        "GROUP BY publisher, source_id")
    for publisher, source_id, n in rows:
        words = identity(publisher)
        if not words:
            continue
        entry = index.setdefault(words, {"names": set(), "direct": 0,
                                         "aggregated": 0, "sources": set()})
        entry["names"].add(publisher)
        entry["sources"].add(source_id)
        if source_id == AGGREGATOR:
            entry["aggregated"] += n
        else:
            entry["direct"] += n
    return index


# Councils whose ordinary name differs from the ONS register's spelling. Only
# for the same body under another name — never a different tier of government.
# Kept explicit rather than inferred: every heuristic tried here credited some
# district with its county's portal, and a short list of real aliases is both
# more honest and easier to check than a cleverer rule.
_ALIASES = {
    "Kingston upon Hull, City of": frozenset({"hull"}),
    "Newcastle upon Tyne": frozenset({"newcastle"}),
}


def match(council_words: frozenset, index: dict,
          council_name: str = "") -> list[dict]:
    """Publishers that ARE this council — exact identity, plus known aliases.

    This used to accept any publisher whose words were a subset of the
    council's, to stop "Durham University" satisfying County Durham. It let
    the leak in from the other end instead: {devon} is a subset of
    {mid, devon}, so Devon County Council's 61 datasets were credited to Mid
    Devon, Hertfordshire's 267 to East Hertfordshire, Lancashire's 216 to West
    Lancashire, and — sharing only the word "port" — the Port of London
    Authority's to Neath Port Talbot. Six councils were recorded as covered on
    the strength of a different organisation's publishing.

    Bournemouth, Christchurch and Poole was the subtlest of them: it matched
    its own three predecessor councils, all abolished in 2019. That is not BCP
    publishing, it is the data of dead councils, which we count separately and
    for the opposite reason.
    """
    wanted = _ALIASES.get(council_name, council_words)
    return [entry for words, entry in index.items() if words == wanted]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true",
                    help="use the cached council list instead of fetching")
    args = ap.parse_args()

    councils = load_councils(args.offline)
    conn = db_connect()
    index = publisher_index(conn)
    conn.close()
    src_ids = source_identities()

    rows, by_nation = [], defaultdict(
        lambda: {"own": 0, "hub": 0, "aggregator": 0, "none": 0})
    for c in councils:
        words = identity(c["name"])
        hits = match(words, index, c["name"]) if words else []
        direct = sum(h["direct"] for h in hits)
        aggregated = sum(h["aggregated"] for h in hits)
        names = sorted({n for h in hits for n in h["names"]})
        sources = sorted({s for h in hits for s in h["sources"] if s != AGGREGATOR})
        # Exact identity, not a subset. Norfolk County Council's portal is
        # not North Norfolk District Council's own portal, and subset
        # matching credited it to all three Norfolk districts — the county
        # is a hub for them, which is a different and less interesting fact.
        own = sorted(s for s in sources if src_ids.get(s) == words)
        state = ("own" if own else "hub" if sources
                 else "aggregator" if aggregated else "none")
        rows.append({**c, "state": state, "direct": direct,
                     "aggregated": aggregated, "publishers": names,
                     "sources": sources, "own_sources": own})
        by_nation[c["nation"]][state] += 1

    total = len(rows)
    have = sum(1 for r in rows if r["state"] != "none")
    portals = sum(1 for r in rows if r["state"] == "own")

    lines = [
        "# UK council coverage",
        "",
        "Every UK local authority, from the ONS Local Authority Districts "
        "register, against what this index actually holds. Generated by "
        "[`scripts/council_coverage.py`](scripts/council_coverage.py) — don't "
        "edit by hand.",
        "",
        f"**{have} of {total} councils** ({100*have/total:.0f}%) have data in "
        f"the index. Only **{portals}** ({100*portals/total:.0f}%) run a data "
        "portal of their own that we harvest.",
        "",
        "| | ✅ own portal | 🔵 regional hub | 🟡 data.gov.uk only "
        "| ⬜ nothing |",
        "|---|---:|---:|---:|---:|",
    ]
    for nation in sorted(by_nation):
        s = by_nation[nation]
        lines.append(f"| {nation} | {s['own']} | {s['hub']} | "
                     f"{s['aggregator']} | {s['none']} |")
    lines += [
        "",
        "A council reached through a hub or through data.gov.uk isn't failing "
        "at anything — for a small district that is the sensible way to "
        "publish. The column is a search signal, not a score: it says where "
        "to look next with `scripts/discover_sources.py --from-councils`, "
        "which probes the council register rather than only the publishers we "
        "already hold.",
        "",
    ]

    for nation in sorted({r["nation"] for r in rows}):
        lines += [f"## {nation}", "",
                  "| Council | Data | Datasets | Held as |", "|---|---|---:|---|"]
        for r in [x for x in rows if x["nation"] == nation]:
            mark = {"own": "✅", "hub": "🔵",
                    "aggregator": "🟡", "none": "⬜"}[r["state"]]
            n = r["direct"] + r["aggregated"]
            held = (", ".join(r["own_sources"] or r["sources"]) if r["sources"]
                    else "data.gov.uk" if r["aggregated"] else "—")
            lines.append(f"| {r['name']} | {mark} | {n or ''} | {held} |")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(
        [{k: r[k] for k in ("code", "name", "nation", "state", "direct",
                            "aggregated", "sources", "own_sources")}
         for r in rows],
        indent=1), encoding="utf-8")

    print(f"{total} councils | {have} with data ({100*have/total:.0f}%) | "
          f"{portals} with their own portal ({100*portals/total:.0f}%)")
    for nation in sorted(by_nation):
        s = by_nation[nation]
        print(f"  {nation:18} own {s['own']:>3}  hub {s['hub']:>3}  "
              f"data.gov.uk {s['aggregator']:>3}  none {s['none']:>3}")
    print(f"\nwrote {OUT.name} and {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
