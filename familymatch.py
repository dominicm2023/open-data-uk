"""The site's own combined tables, offered above the search results when a
search is about one of them.

A visitor on 8 October 2026 searched "HMO license" eight ways, with "Leeds"
and an LS4 postcode, and was shown single councils' datasets: never the
table of 88 councils' registers this site builds, nor its map, nor the
plain answer to their question (Leeds publishes its register only on
request). Search ranks the catalogue; it does not know the families. This
does, from their built outputs, and says:

  - what the table is and how much of it there is (its own summary.json);
  - for a place the search named, whether that place's council is in it
    (the table's publishers) and, for the HMO family, what the council's
    register is if it is not (the coverage file, one entry per council);
  - for a postcode district in an HMO search, how many licences the
    registers we hold list there.

Nothing is ranked or hidden by it; the results below are the search's own.
A card's link carries data-role="family" so the click beacon can count it.
"""
from __future__ import annotations

import functools
import json
import re
import sqlite3
from pathlib import Path

from paths import DATA_DIR

ROOT = Path(__file__).resolve().parent
OUT = DATA_DIR / "families" / "out"
COVERAGE = ROOT / "families" / "registry" / "hmo_registers.coverage.json"
MAPIT = DATA_DIR / "geo" / "mapit" / "gb-postcodes-v5" / "districts"

# What a search says when it is about a family. Written for what people type,
# not for dataset titles (families/registry.py has those): "council spending",
# "HMO license", "air pollution".
WORDS = {
    "hmo_registers": r"\bhmos?\b|multiple\s+occupa|multi[\s-]?occupancy|bedsits?\b",
    "air_quality_annual": r"air\s+(quality|pollution)|\bno2\b|nitrogen\s+dioxide|\bpm\s?(2\.?5|10)\b|diffusion\s+tubes?",
    "brownfield_land": r"brownfield",
    "spend_over_500": r"\bspend(ing)?\b|expenditure|payments?\s+to\s+suppliers|supplier\s+payments|over\s+£?\s?500\b",
    "organograms": r"organogram|senior\s+(salar|pay|staff|civil\s+servant)|staff\s+(roles|structure)|civil\s+serv\w*\s+(pay|salar|grade)|org(ani[sz]ation(al)?)?\s+charts?",
    "recycling_centres": r"recycling\s+(cent|site|point)|\bhwrcs?\b|household\s+waste|civic\s+amenit|\btip\b",
}
# What one row of each table is, for the card's sentence.
WHAT = {
    "hmo_registers": ("licensed HMOs", "councils' public registers"),
    "air_quality_annual": ("annual mean readings", "monitoring networks and councils"),
    "brownfield_land": ("brownfield sites", "councils' registers"),
    "spend_over_500": ("payments", "public bodies' transparency returns"),
    "organograms": ("posts", "public bodies' organograms"),
    "recycling_centres": ("recycling centres", "councils"),
}
EXTRA = {
    "hmo_registers": [("Map by postcode district", "/family/hmo_registers/map")],
    "organograms": [("Explore a body's chart", "/family/organograms/chart")],
}
_COUNCIL_WORDS = re.compile(r"\b(london borough of|royal borough of|borough of|city of|county of|the|council|city|borough|district|"
                            r"county|metropolitan|unitary|authority|arcgis online|former( council| district)? of)\b|[,.()&]", re.I)
_OUTWARD = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?)(?:\s*[0-9][A-Z]{2})?\b", re.I)


def _core(name: str) -> str:
    return " ".join(_COUNCIL_WORDS.sub(" ", name.lower()).split())


# Places a search names that are not one council: a region or a nation has
# many councils in it, and no single council's status answers for it.
REGIONS = {"london", "greater london", "england", "wales", "scotland", "northern ireland", "uk", "united kingdom",
           "great britain", "britain", "yorkshire", "west yorkshire", "south yorkshire", "north west", "north east",
           "south west", "south east", "east midlands", "west midlands", "east of england", "east anglia",
           "greater manchester", "merseyside", "midlands", "the north", "highlands"}


def _same_place(place: str, name: str) -> bool:
    """'leeds' and 'Leeds City Council'; 'newcastle upon tyne' and
    'Newcastle City Council'; 'bristol' and 'Bristol, City of'."""
    core = _core(name)
    if not core or not place:
        return False
    if core == place:
        return True
    short, long = sorted((core, place), key=len)
    return len(short) > 3 and re.search(rf"\b{re.escape(short)}\b", long) is not None


def _stamp(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


@functools.lru_cache(maxsize=16)
def _summary(family: str, stamp: float) -> dict | None:
    try:
        return json.loads((OUT / family / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@functools.lru_cache(maxsize=4)
def _coverage(stamp: float) -> list:
    try:
        return json.loads(COVERAGE.read_text(encoding="utf-8"))["councils"]
    except (OSError, ValueError, KeyError):
        return []


@functools.lru_cache(maxsize=4)
def _hmo_counts(stamp: float) -> tuple[float, dict, int]:
    """Licences in the HMO table, per postcode district, and its councils
    (a council can publish more than one register: Bristol's layers)."""
    db = OUT / "hmo_registers" / "hmo_registers.sqlite"
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            by = dict(c.execute("SELECT postcode_district, SUM(licences) FROM rows GROUP BY 1").fetchall())
            councils = c.execute("SELECT COUNT(DISTINCT council) FROM rows").fetchone()[0]
        finally:
            c.close()
    except sqlite3.Error:
        return 0.0, {}, 0
    return float(sum(v or 0 for v in by.values())), by, councils


@functools.lru_cache(maxsize=1)
def _districts() -> frozenset:
    try:
        return frozenset(p.stem for p in MAPIT.glob("*.geojson"))
    except OSError:
        return frozenset()


# What a council not in the HMO table publishes, as the rest of a sentence
# beginning "<Council> is not in this table: ".
NOT_IN = {
    "open_file": "its register is open data we have not added yet",
    "file_no_licence": "its register is published as a file we could not use",
    "held": "its register is published, and the terms on its website are awaiting a decision",
    "document": "its register is published as a PDF or web page we cannot read",
    "search_only": "the council publishes its register only as a search box on its own website",
    "on_request": "its register is available only on request or for inspection",
    "not_found": "we found no register of its online",
    "unsearched": "we have not yet been able to confirm what it publishes",
}


def _title(place: str) -> str:
    small = {"upon", "and", "of", "on", "the", "in", "le", "under"}
    return " ".join(w if i and w in small else w[:1].upper() + w[1:] for i, w in enumerate(place.split()))


def _hmo_place(place: str) -> dict | None:
    for c in _coverage(_stamp(COVERAGE)):
        if not _same_place(place, c["name"]):
            continue
        name = c["name"].split(",")[0]
        if c["status"] == "in_table":
            return {"name": name, "in_table": True, "text": f"{name}: {c.get('note') or 'in this table'}.",
                    "link": {"text": "See it on the map", "url": "/family/hmo_registers/map"}}
        text = f"{name} is not in this table: {NOT_IN.get(c['status'], 'it is not among the registers we hold')}."
        if c.get("note") and c["status"] in ("document", "file_no_licence", "held"):
            text += f" {c['note'][0].upper()}{c['note'][1:]}" + ("" if c["note"].endswith(".") else ".")
        link = c.get("register_page") or c.get("register_url")
        return {"name": name, "in_table": False, "text": text,
                "link": {"text": f"{name}'s own HMO page", "url": link} if link and link.startswith("http") else None}
    return None


def cards(query: str, geo: dict | None) -> list[dict]:
    """The family cards for a search, most specific first; usually none."""
    q = query or ""
    place = ((geo or {}).get("place") or "").lower().strip()
    out = []
    for family, pattern in WORDS.items():
        if not re.search(pattern, q, re.I):
            continue
        s = _summary(family, _stamp(OUT / family / "summary.json"))
        if not s or not s.get("published_rows"):
            continue
        pubs = s.get("publishers_published") or []
        row, whose = WHAT[family]
        n, bodies = s["published_rows"], len(pubs)
        if family == "hmo_registers":
            total, _, councils = _hmo_counts(_stamp(OUT / family / "hmo_registers.sqlite"))
            n, bodies = total or n, councils or bodies
        card = {"family": family, "label": s.get("label") or family, "url": f"/family/{family}",
                "summary": f"A table this site builds from {bodies} {whose}: {n:,.0f} {row}, in one form, with each "
                           f"row linked to its source.",
                "links": [{"text": t, "url": u} for t, u in EXTRA.get(family, [])], "place": None, "district": None}
        if place and place not in REGIONS:
            if family == "hmo_registers":
                card["place"] = _hmo_place(place)
            if not card["place"]:
                hits = [p for p in pubs if _same_place(place, p)]
                pname = _title(place)
                card["place"] = ({"name": pname, "in_table": True, "text": f"{pname} is in this table: {', '.join(hits[:3])}."}
                                 if hits else {"name": pname, "in_table": False,
                                               "text": f"{pname} is not among this table's {len(pubs)} publishers yet."})
        if family == "hmo_registers":
            known = _districts()
            _, by, _ = _hmo_counts(_stamp(OUT / family / "hmo_registers.sqlite"))
            for m in _OUTWARD.finditer(q):
                d = m.group(1).upper()
                if d in known or d in by:
                    k = int(by.get(d) or 0)
                    card["district"] = {"district": d, "licences": k,
                                        "text": (f"{d}: {k:,} licensed HMO{'' if k == 1 else 's'} on the registers this table holds."
                                                 if k else f"{d}: no licensed HMOs on the registers this table holds. That is not the "
                                                           f"same as none: the council's register may not be among them."),
                                        "url": f"/family/hmo_registers/map?district={d}"}
                    break
        out.append(card)
    return out
