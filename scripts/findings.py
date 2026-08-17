"""Find things in the index worth saying out loud, with the receipts attached.

The index knows things nobody else can check: which councils publish nothing,
who states no licence, whose links have rotted, and where two public bodies
publish the same dataset under different terms. This turns those into
*claims* — each one carrying the exact query that produced it, the numbers,
and a draft post.

Every finding is tiered by how much a human needs to be involved before it
goes anywhere:

  1  a fact about our own index          publish automatically
  2  a coverage or quality comparison    publish automatically
  3  a measurement about a named body    a human checks it first
  4  a cross-source join                 a human checks the join, always
  5  framing and argument                a human writes it

Tier 3 was meant to auto-publish, on the reasoning that a measurement is not
an accusation. Building this disproved that. Every single-publisher claim the
first runs produced had a confounder that changed what it meant:

  * a council with 100% dead links had been abolished in 2023
  * a department with 100% dead links was an artefact of a stale local copy
  * a council "letting its links rot" had decommissioned its portal, and the
    national catalogue had never pruned the records
  * a body whose links 404 turned out to be hosting on another agency's
    platform, which is who removed the files

All four were true as measurements and misleading as sentences. Four out of
four is not a run of bad luck, it is the base rate: naming one organisation
means implying a cause, and the cause lives outside our data. So tier 3 goes
in the review queue with the rest.

Nothing above tier 3 is generated here. A join across publishers can be
wrong in ways that look right — mismatched geographies, different reporting
periods — and a confident wrong claim about a named organisation is the one
failure mode that matters. Tiers 4 and 5 get a prompt in the queue and a
human, not a generator.

Each finding records the SQL that produced it so anyone, including someone
who disagrees with the conclusion, can re-run it and check. That is the
whole point: an argument from open data should be as checkable as the data.

Usage:
    python scripts/findings.py                 # write FINDINGS.md + findings.json
    python scripts/findings.py --tier 1,2      # only auto-publishable tiers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from paths import connect as db_connect  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT_MD = ROOT / "FINDINGS.md"
OUT_JSON = ROOT / "findings.json"
SITE = "https://open-data.org.uk"

# Only findable datasets: duplicates collapsed, withdrawn records excluded.
FINDABLE = ("FROM datasets d WHERE "
            "NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key) AND "
            "NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)")


def finding(tier: int, kind: str, headline: str, detail: str, numbers: dict,
            sql: str, post: str, link: str = SITE) -> dict:
    return {"tier": tier, "kind": kind, "headline": headline, "detail": detail,
            "numbers": numbers, "sql": " ".join(sql.split()), "post": post,
            "link": link}


# --- Tier 2: coverage ----------------------------------------------------

def coverage_gaps(conn) -> list[dict]:
    """Councils publishing nothing we can find, by nation."""
    path = ROOT / "council_coverage.json"
    if not path.exists():
        return []
    councils = json.loads(path.read_text(encoding="utf-8"))
    out = []
    by_nation: dict[str, list[str]] = {}
    for c in councils:
        if c["state"] == "none":
            by_nation.setdefault(c["nation"], []).append(c["name"])
    for nation, names in sorted(by_nation.items()):
        total = sum(1 for c in councils if c["nation"] == nation)
        out.append(finding(
            2, "coverage",
            f"{len(names)} of {total} councils in {nation} publish no open data we can find",
            "Checked against the ONS register of local authorities. 'None' means "
            "we hold nothing under that council's name from any of our sources, "
            "including data.gov.uk, and no portal answered at any address we "
            "could find. Councils: " + ", ".join(sorted(names)),
            {"nation": nation, "without_data": len(names), "councils": total},
            "council_coverage.json, state == 'none'",
            f"{len(names)} of {total} councils in {nation} publish no open data "
            f"that we can find anywhere — not on their own site, not on "
            f"data.gov.uk. Full list and method: {SITE}/about",
            f"{SITE}/publishers"))
    return out


# --- Tier 2: licensing ---------------------------------------------------

def licence_gap(conn) -> list[dict]:
    """How much of the catalogue you legally cannot reuse."""
    total, nolic = conn.execute(
        f"SELECT COUNT(*), SUM(CASE WHEN d.license_norm IS NULL THEN 1 ELSE 0 END) "
        f"{FINDABLE}").fetchone()
    pct = round(100 * nolic / total)
    out = [finding(
        1, "licensing",
        f"{pct}% of UK open data states no licence at all",
        "Without a stated licence you cannot know whether you may republish, "
        "build on, or sell work using the data. We count a licence recorded "
        "anywhere the publisher put it, including the non-standard fields "
        "data.gov.uk uses — this is after that recovery, not before it.",
        {"datasets": total, "no_licence": nolic, "percent": pct},
        f"SELECT COUNT(*) {FINDABLE} AND d.license_norm IS NULL",
        f"{pct}% of the UK's open data doesn't say what licence it's under. "
        f"Not 'restrictive' — unstated. You cannot legally know whether you "
        f"may reuse {nolic:,} datasets. {SITE}")]

    rows = conn.execute(f"""
        SELECT d.publisher, COUNT(*) n,
               SUM(CASE WHEN d.license_norm IS NULL THEN 1 ELSE 0 END) missing
        {FINDABLE} AND d.publisher IS NOT NULL
        GROUP BY d.publisher HAVING n >= 100
        ORDER BY (missing * 1.0 / n) DESC, n DESC LIMIT 10""").fetchall()
    worst = [(p, n, m) for p, n, m in rows if m > 0]
    if worst:
        p, n, m = worst[0]
        out.append(finding(
            3, "licensing",
            f"{p} states no licence on {round(100*m/n)}% of its datasets",
            "Measured across publishers holding at least 100 datasets. This "
            "states what the catalogue records, not whether the data is in "
            "fact reusable — the publisher may intend it to be.",
            {"publisher": p, "datasets": n, "missing": m,
             "others": [{"publisher": x, "datasets": y, "missing": z} for x, y, z in worst[:10]]},
            "publisher licence coverage, min 100 datasets",
            f"{p} publishes {n:,} datasets and states no licence on {m:,} of "
            f"them ({round(100*m/n)}%). Nobody can legally reuse what they "
            f"can't identify the terms of. {SITE}"))
    return out


# --- Tier 2: the data that died with the council -------------------------

# English councils abolished in the 2019-2023 reorganisations. Not exhaustive
# — it stops at 2019, so the figures below are a floor, not a ceiling.
ABOLISHED = [
    "Allerdale", "Copeland", "Carlisle", "Barrow", "Eden", "South Lakeland",
    "Craven", "Hambleton", "Harrogate", "Richmondshire", "Ryedale",
    "Scarborough", "Selby", "Mendip", "Sedgemoor", "South Somerset",
    "Somerset West", "Taunton Deane", "West Somerset", "Aylesbury Vale",
    "Chiltern", "South Bucks", "Wycombe", "Corby", "Kettering",
    "Wellingborough", "East Northamptonshire", "Daventry",
    "South Northamptonshire", "Northampton", "Bournemouth", "Poole",
    "Christchurch", "East Dorset", "North Dorset", "Purbeck", "West Dorset",
    "Weymouth", "Forest Heath", "St Edmundsbury", "Suffolk Coastal",
    "Waveney", "Shepway",
]


def abolished_councils(conn) -> list[dict]:
    """What happens to a council's published data when the council ends.

    This is the kind of thing only a cross-portal index can see. data.gov.uk
    keeps the catalogue entry; the council's own server went when the council
    did. Each portal sees a working record of its own.
    """
    total = checked = dead = 0
    worst = []
    for name in ABOLISHED:
        n, d, ck = conn.execute(
            f"SELECT COUNT(*), SUM(CASE WHEN d.availability='dead' THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN d.availability IS NOT NULL THEN 1 ELSE 0 END) "
            f"{FINDABLE} AND d.publisher LIKE ?", (name + "%",)).fetchone()
        if not n:
            continue
        total += n
        checked += ck or 0
        dead += d or 0
        if ck and d:
            worst.append({"council": name, "datasets": n, "checked": ck, "dead": d})
    if not checked:
        return []
    pct = round(100 * dead / checked)
    worst.sort(key=lambda w: -w["dead"])
    return [finding(
        2, "abolished",
        f"{dead:,} datasets published by councils that no longer exist now lead nowhere",
        f"{len(ABOLISHED)} English councils were abolished in the 2019-2023 "
        f"reorganisations. We hold {total:,} datasets published in their names. "
        f"Of the {checked:,} whose links we have followed, {dead:,} ({pct}%) are "
        f"dead — the catalogue entry survived the council, the server didn't. "
        f"Nobody inherited the duty to move the data. The list stops at 2019, "
        f"so this is a floor.",
        {"councils": len(ABOLISHED), "datasets": total, "checked": checked,
         "dead": dead, "percent": pct, "worst": worst[:10]},
        "publisher matching abolished-council names, availability = 'dead'",
        f"When a council is abolished its data dies with it. We hold {total:,} "
        f"datasets from {len(ABOLISHED)} councils abolished since 2019 — {pct}% "
        f"of the links we've followed are dead. The records are still listed. "
        f"They just don't go anywhere. {SITE}")]


# --- Tier 2: servers the catalogues still point at ----------------------

def _dead_host_publishers() -> set[str]:
    """Publishers whose broken links are explained by a host that is simply gone.

    They belong in the dead-hosts finding, not the link-rot one. "96% of this
    council's links are broken" reads as neglect; the truth was that they
    switched a portal off and the national catalogue kept listing it. Both are
    failures, but only one of them is theirs, and the honest version is also
    the more interesting one.
    """
    path = ROOT / "dead_hosts.json"
    if not path.exists():
        return set()
    return {p for h in json.loads(path.read_text(encoding="utf-8"))
            for p in h["publishers"]}


def dead_hosts(_conn) -> list[dict]:
    """Hostnames proven unreachable from two vantage points.

    Reads what scripts/dead_hosts.py measured rather than re-probing, so a
    claim here always corresponds to a probe someone can repeat.

    The claim is deliberately about a *hostname*, never an organisation. When
    we checked the largest of these, the company running it was alive and
    trading — it was the shared endpoint that had stopped answering. "Their
    server is gone" and "the company failed" are one careless sentence apart,
    and only one of them is true.
    """
    path = ROOT / "dead_hosts.json"
    if not path.exists():
        return []
    hosts = json.loads(path.read_text(encoding="utf-8"))
    if not hosts:
        return []
    total = sum(h["resources"] for h in hosts)
    pubs = {p for h in hosts for p in h["publishers"]}
    out = [finding(
        2, "dead-hosts",
        f"{total:,} dataset links point at {len(hosts)} servers that no longer answer",
        f"Across {len(pubs)} publishers. Each hostname was tried from two "
        f"separate networks and failed from both — either it no longer "
        f"resolves at all, or it resolves and nothing is listening. Hosts "
        f"that merely refused our checker are excluded, as are 22 that turned "
        f"out to answer perfectly well, which were our own error rather than "
        f"anyone's dead server. The catalogue entries are all still listed.",
        {"hosts": len(hosts), "resources": total, "publishers": len(pubs),
         "detail": [{"host": h["host"], "state": h["state"],
                     "resources": h["resources"],
                     "publishers": len(h["publishers"])} for h in hosts]},
        "scripts/dead_hosts.py — connection failures grouped by host, re-probed",
        f"{total:,} links in the UK's open data catalogues point at servers "
        f"that don't answer any more — {len(hosts)} hostnames across "
        f"{len(pubs)} public bodies. Every record still sits there looking "
        f"perfectly healthy. {SITE}")]

    shared = max(hosts, key=lambda h: len(h["publishers"]))
    if len(shared["publishers"]) >= 10:
        out.append(finding(
            2, "dead-hosts",
            f"{len(shared['publishers'])} councils published their INSPIRE data "
            f"through one address, and that address stopped answering",
            f"{shared['resources']} datasets from {len(shared['publishers'])} "
            f"different councils all resolve to {shared['host']}, which does "
            f"not respond from any network we tried. The parent domain is "
            f"alive and the supplier is still trading — it is this endpoint "
            f"that went. Councils met a statutory publishing duty by pointing "
            f"at a shared service, and when the address changed nobody went "
            f"back to update {len(shared['publishers'])} catalogues. No single "
            f"portal could notice this: each one holds a handful of records "
            f"that look fine.",
            {"host": shared["host"], "state": shared["state"],
             "resources": shared["resources"],
             "councils": sorted(shared["publishers"])},
            "dead_hosts.json — the host serving the most distinct publishers",
            f"{len(shared['publishers'])} UK councils published their INSPIRE "
            f"data through a single shared address. It stopped answering. "
            f"{shared['resources']} datasets now lead nowhere and every "
            f"catalogue still lists them as available. {SITE}"))
    return out


# --- Tier 3: link rot (a measurement, not a judgement) -------------------

def link_rot(conn) -> list[dict]:
    """Publishers whose links we followed and found broken.

    Abolished councils are excluded: 100% dead is a true measurement there and
    a meaningless accusation, because there is no longer anybody to accuse.
    They get their own finding above.
    """
    rows = conn.execute(f"""
        SELECT d.publisher, COUNT(*) checked,
               SUM(CASE WHEN d.availability = 'dead' THEN 1 ELSE 0 END) dead
        {FINDABLE} AND d.publisher IS NOT NULL AND d.availability IS NOT NULL
        GROUP BY d.publisher HAVING checked >= 50 AND dead > 0
        ORDER BY (dead * 1.0 / checked) DESC LIMIT 20""").fetchall()
    gone_host = _dead_host_publishers()
    live = [(p, c, d) for p, c, d in rows
            if not any(p.startswith(a) for a in ABOLISHED) and p not in gone_host]
    if not live:
        return []
    p, checked, dead = live[0]
    return [finding(
        3, "link-rot",
        f"{round(100*dead/checked)}% of {p}'s dataset links are broken",
        "We follow every resource link and record the response. 'Broken' "
        "means a 404, a server error, or a connection that failed — never a "
        "server that merely refused our checker, which we record separately "
        "as unverified. Two groups are excluded and counted separately: "
        "councils abolished since 2019, because a defunct body can't fix its "
        "links, and publishers whose whole hosting domain has gone, because "
        "that is a decommissioned portal rather than rot.",
        {"publisher": p, "checked": checked, "dead": dead,
         "others": [{"publisher": x, "checked": y, "dead": z} for x, y, z in live[:10]]},
        "availability = 'dead', min 50 checked per publisher, still-existing bodies",
        f"We followed {checked:,} of {p}'s dataset links. {dead:,} are dead — "
        f"404s and server errors, not blocks. {round(100*dead/checked)}% of "
        f"what they publish leads nowhere. {SITE}")]


# --- Tier 2: data locked inside documents --------------------------------

# What a machine can read without a human retyping it. Deliberately generous:
# an over-broad list understates the problem, an under-broad one accuses a
# publisher of something they didn't do. XML, WMS and Esri REST are all
# perfectly machine-readable, and leaving them out once cost Basildon — 101
# XML datasets — a headline saying it published nothing usable.
MACHINE = {"CSV", "TSV", "JSON", "GEOJSON", "JSON-LD", "XML", "RDF", "TURTLE",
           "N3", "SPARQL", "XLS", "XLSX", "ODS", "SHP", "GPKG", "GDB", "KML",
           "KMZ", "GML", "WMS", "WFS", "WCS", "WMTS", "REST", "ESRI-REST",
           "API", "PARQUET", "NETCDF", "ZIP", "TXT", "SQL", "DB", "ATOM", "RSS"}
DOCUMENT = {"PDF", "DOC", "DOCX", "PPT", "PPTX"}


def document_only(conn) -> list[dict]:
    """Publishers whose entire catalogue is documents, not data."""
    rows = conn.execute(f"""
        SELECT d.publisher, d.formats_norm {FINDABLE}
        AND d.publisher IS NOT NULL AND d.formats_norm NOT IN ('[]', '')
        AND d.formats_norm IS NOT NULL""").fetchall()
    tally: dict[str, list[int]] = {}
    for pub, raw in rows:
        try:
            fmts = {str(f).upper() for f in json.loads(raw)}
        except (ValueError, TypeError):
            continue
        if not fmts:
            continue
        t = tally.setdefault(pub, [0, 0, 0])   # rows, machine-readable, document
        t[0] += 1
        t[1] += 1 if fmts & MACHINE else 0
        t[2] += 1 if fmts & DOCUMENT else 0
    hits = [(p, n, doc) for p, (n, mac, doc) in tally.items()
            if n >= 30 and mac == 0 and doc >= n * 0.8]
    if not hits:
        return []
    hits.sort(key=lambda h: -h[1])
    p, n, doc = hits[0]
    return [finding(
        2, "formats",
        f"{p} publishes {n:,} datasets, none of them machine-readable",
        "Every record is a PDF or a Word document — no CSV, spreadsheet, "
        "JSON, XML, geospatial file or API anywhere in the catalogue. The "
        "numbers are public and using them means retyping them. Counted only "
        "across publishers with at least 30 datasets that state a format.",
        {"publisher": p, "datasets": n, "documents": doc,
         "others": [{"publisher": x, "datasets": y, "documents": z} for x, y, z in hits[:10]]},
        "no format in the machine-readable vocabulary, >=80% documents, min 30 datasets",
        f"{p} publishes {n:,} datasets. Not one is machine-readable — every "
        f"record is a PDF or a Word document. Public, and unusable without "
        f"retyping it. {SITE}")]


# --- Tier 2: the same dataset, different terms ---------------------------

def licence_disagreement(conn) -> list[dict]:
    """One dataset type, published by many bodies under different licences."""
    rows = conn.execute(f"""
        SELECT LOWER(TRIM(d.title)) t,
               COUNT(DISTINCT d.publisher) pubs,
               COUNT(DISTINCT d.license_norm) lics,
               SUM(CASE WHEN d.license_norm IS NULL THEN 1 ELSE 0 END) unlicensed,
               COUNT(*) n
        {FINDABLE} AND d.title IS NOT NULL AND d.publisher IS NOT NULL
        GROUP BY t HAVING pubs >= 10 AND lics >= 3
        ORDER BY pubs DESC LIMIT 10""").fetchall()
    if not rows:
        return []
    t, pubs, lics, unlic, n = rows[0]
    return [finding(
        2, "licensing",
        f'"{t.title()}" is published by {pubs} bodies under {lics} different licences',
        "The same kind of dataset, produced for the same statutory reason, "
        "released on terms that differ by council — and some on no stated "
        "terms at all. Anyone wanting a national picture has to reconcile "
        f"{lics} licences first; {unlic} of the {n} copies state none.",
        {"title": t, "publishers": pubs, "licences": lics,
         "unlicensed": unlic, "copies": n,
         "others": [{"title": a, "publishers": b, "licences": c} for a, b, c, _d, _e in rows]},
        "same normalised title, >= 10 publishers, >= 3 distinct licences",
        f'{pubs} public bodies publish "{t}". Between them they use {lics} '
        f"different licences and {unlic} state none at all. Same data, same "
        f"duty, {lics} sets of rules. {SITE}/who-publishes")]


# --- Tier 4/5: prompts for a human, never generated ---------------------

def human_prompts(conn) -> list[dict]:
    """Questions the index can pose but must not answer on its own."""
    return [
        {"tier": 4, "kind": "prompt",
         "headline": "Storm overflow activity against deprivation",
         "detail": "We hold water company discharge data (Stream) and council "
                   "deprivation indices. Joining them would say something real "
                   "about who lives with sewage — and the join is exactly the "
                   "kind that goes wrong: different geography levels, different "
                   "reporting periods, spill *events* not volumes. Needs someone "
                   "who checks the join before a word is published.",
         "numbers": {}, "sql": "", "post": "", "link": SITE},
        {"tier": 5, "kind": "prompt",
         "headline": "What the licence gap is actually for",
         "detail": "A third of public data states no licence. That is a fact "
                   "(tier 1). Whether it reflects neglect, caution, or a "
                   "deliberate brake on reuse is an argument, and arguments "
                   "need a person making them in their own name.",
         "numbers": {}, "sql": "", "post": "", "link": SITE},
    ]


ANALYSES = [coverage_gaps, licence_gap, abolished_councils, dead_hosts,
            link_rot, document_only, licence_disagreement, human_prompts]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", help="only these tiers, e.g. 1,2")
    args = ap.parse_args()
    wanted = {int(t) for t in args.tier.split(",")} if args.tier else None

    conn = db_connect()
    findings: list[dict] = []
    for fn in ANALYSES:
        try:
            findings += fn(conn)
        except Exception as exc:  # noqa: BLE001 - one bad analysis shouldn't stop the rest
            print(f"  {fn.__name__} failed: {type(exc).__name__}: {exc}")
    conn.close()
    if wanted:
        findings = [f for f in findings if f["tier"] in wanted]
    findings.sort(key=lambda f: (f["tier"], f["kind"]))

    auto = [f for f in findings if f["tier"] <= 2]
    review = [f for f in findings if f["tier"] > 2]

    lines = [
        "# Findings", "",
        "Generated by [`scripts/findings.py`](scripts/findings.py) from the "
        "index. Every claim carries the query that produced it, so anyone — "
        "including someone who disagrees with it — can re-run it.", "",
        f"**{len(auto)} ready to publish** (tiers 1-2) · "
        f"**{len(review)} need a person** (tiers 3-5)", "",
        "Tier 1 is a fact about our own index. Tier 2 is a coverage or quality "
        "comparison — a claim about a pattern, not about one organisation. "
        "Tier 3 names a body, and every tier-3 claim this engine has produced "
        "so far turned out to have a cause outside our data that changed what "
        "it meant, so they wait for a person. Tiers 4 and 5 are a join or an "
        "argument, and this script deliberately doesn't write them.", "",
    ]
    for f in findings:
        lines += [f"## [Tier {f['tier']}] {f['headline']}", "",
                  f["detail"], ""]
        if f.get("post"):
            lines += ["**Draft post**", "", "> " + f["post"].replace("\n", " "), ""]
        if f.get("sql"):
            lines += ["<details><summary>How it was measured</summary>", "",
                      "```sql", f["sql"], "```", "",
                      "```json", json.dumps(f["numbers"], indent=1)[:1200], "```",
                      "", "</details>", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(findings, indent=1), encoding="utf-8")

    for f in findings:
        print(f"  [{f['tier']}] {f['kind']:14} {f['headline'][:74]}")
    print(f"\n{len(auto)} publishable, {len(review)} for review — "
          f"wrote {OUT_MD.name} and {OUT_JSON.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
