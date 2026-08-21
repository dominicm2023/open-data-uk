"""Place-name detection and coverage checking for query-time geography.

Two vocabularies combine:
- a curated list of UK places (so we recognise "brighton" even when we hold
  little or no data for it), and
- place words mined from publisher names in the index (so every council or
  body we do cover is recognised automatically).

search.py uses this to (a) tell the user honestly when a place they asked
about has little or no indexed data, and (b) flag when top results come from
somewhere else entirely.
"""

from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

GAZETTEER_PATH = Path(__file__).parent / "gazetteer.json"


@lru_cache(maxsize=1)
def gazetteer() -> dict[str, tuple[float, float]]:
    """UK place name -> (lon, lat), from ONS Local Authority Districts.

    Built by scripts/build_gazetteer.py. Absent gazetteer just means no
    coordinate-based search — everything else still works.

    Keys are re-normalised through the same tokeniser queries go through:
    "Armagh City, Banbridge and Craigavon" is unreachable as stored, because
    no tokenised query ever contains a comma. Keys that begin with "of " are
    dropped — name-stripping in the build left "of london" and "of
    edinburgh" behind, and "mayor of london" queries were detecting a place
    called "of london".
    """
    try:
        raw = json.loads(GAZETTEER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for k, v in raw.items():
        if not (isinstance(v, list) and len(v) == 2):
            continue
        key = " ".join(_tokens(k))
        if not key or key.startswith("of "):
            continue
        out.setdefault(key, (float(v[0]), float(v[1])))
    return out


def place_point(place: str | None) -> tuple[float, float] | None:
    """Coordinates for a detected place, if we know them."""
    return gazetteer().get((place or "").lower().strip())

# Curated UK places: nations, regions, cities, and well-known towns. Not
# exhaustive — the publisher-mined vocabulary covers every place we actually
# hold data for; this list exists so we can recognise places we DON'T cover.
MAJOR_PLACES = {
    "england", "scotland", "wales", "northern ireland", "cornwall", "devon",
    "dorset", "somerset", "kent", "essex", "sussex", "surrey", "hampshire",
    "norfolk", "suffolk", "cumbria", "yorkshire", "lancashire", "merseyside",
    "london", "birmingham", "manchester", "leeds", "sheffield", "liverpool",
    "bristol", "newcastle", "nottingham", "leicester", "coventry", "bradford",
    "cardiff", "swansea", "newport", "wrexham", "bangor", "aberystwyth",
    "edinburgh", "glasgow", "aberdeen", "dundee", "inverness", "stirling",
    "perth", "falkirk", "paisley", "belfast", "derry", "londonderry", "lisburn",
    "newry", "armagh", "brighton", "hove", "portsmouth", "southampton",
    "plymouth", "exeter", "bath", "gloucester", "cheltenham", "oxford",
    "cambridge", "norwich", "ipswich", "luton", "reading", "slough", "swindon",
    "bournemouth", "poole", "salisbury", "winchester", "guildford", "woking",
    "crawley", "eastbourne", "hastings", "canterbury", "maidstone", "dover",
    "chelmsford", "colchester", "southend", "basildon", "watford", "stevenage",
    "peterborough", "northampton", "milton keynes", "bedford", "derby",
    "stoke", "wolverhampton", "walsall", "dudley", "solihull", "warwick",
    "worcester", "hereford", "shrewsbury", "telford", "chester", "warrington",
    "stockport", "bolton", "oldham", "rochdale", "salford", "wigan", "bury",
    "preston", "blackpool", "blackburn", "burnley", "lancaster", "carlisle",
    "durham", "sunderland", "gateshead", "middlesbrough", "darlington",
    "hartlepool", "york", "hull", "wakefield", "huddersfield", "halifax",
    "harrogate", "doncaster", "rotherham", "barnsley", "grimsby", "lincoln",
    "scunthorpe", "mansfield", "chesterfield", "loughborough", "rugby",
    "nuneaton", "redditch", "kidderminster", "stafford", "crewe", "macclesfield",
    # Ceremonial counties not already covered above: people ask for
    # "derbyshire school places", not for a district they can't name.
    "northumberland", "cheshire", "derbyshire", "nottinghamshire",
    "lincolnshire", "leicestershire", "rutland", "staffordshire",
    "warwickshire", "northamptonshire", "buckinghamshire", "berkshire",
    "oxfordshire", "wiltshire", "gloucestershire", "herefordshire",
    "worcestershire", "shropshire", "hertfordshire", "bedfordshire",
    "cambridgeshire", "tyne and wear", "county durham", "isle of wight",
    "east sussex", "west sussex", "north yorkshire", "south yorkshire",
    "west yorkshire", "east riding",
}

# Welsh-language names, mapped to the English forms the index stores. Only
# the names that differ are listed; "gwynedd" and "powys" are already their
# own English names. Accented forms are listed as people type them without
# the accent ("ynys mon"), because the tokeniser only keeps a-z.
WELSH_ALIASES = {
    "caerdydd": "cardiff", "abertawe": "swansea", "casnewydd": "newport",
    "wrecsam": "wrexham", "ynys mon": "isle of anglesey",
    "anglesey": "isle of anglesey", "sir fynwy": "monmouthshire",
    "sir gaerfyrddin": "carmarthenshire", "sir ddinbych": "denbighshire",
    "sir benfro": "pembrokeshire", "sir y fflint": "flintshire",
    "bro morgannwg": "vale of glamorgan", "caerffili": "caerphilly",
    "merthyr tudful": "merthyr tydfil",
    "castell nedd port talbot": "neath port talbot",
    "pen y bont ar ogwr": "bridgend",
}

# Words in publisher names that are organisational, not geographic
_ORG_WORDS = {
    "council", "city", "of", "and", "the", "borough", "district", "county",
    "metropolitan", "royal", "greater", "national", "park", "authority",
    "combined", "unitary", "shire", "nhs", "trust", "foundation", "ccg",
    "icb", "hospital", "hospitals", "university", "college", "school",
    "government", "department", "ministry", "office", "agency", "executive",
    "assembly", "parliament", "service", "services", "board", "committee",
    "commission", "partnership", "association", "federation", "society",
    "group", "team", "unit", "centre", "center", "institute", "laboratory",
    "survey", "archive", "library", "museum", "gallery", "fund", "scheme",
    "open", "data", "datastore", "dataworks", "observatory", "digital",
    "information", "statistics", "records", "environment", "environmental",
    "natural", "historic", "heritage", "rural", "affairs", "communities",
    "housing", "transport", "health", "social", "care", "education", "police",
    "fire", "rescue", "ambulance", "water", "coast", "coastal", "valley",
    "north", "south", "east", "west", "central", "upon", "under", "on", "in",
    "st", "new", "old", "great", "little", "upper", "lower", "for",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def build_place_vocab(conn: sqlite3.Connection) -> set[str]:
    """Authoritative UK places only: MAJOR_PLACES plus the ONS gazetteer.

    We deliberately do NOT mine publisher names here any more. Doing so let
    ordinary domain nouns into the vocabulary — "Care Quality Commission"
    made "quality" a "place", so "air quality in Paris" detected
    place="quality", which then *suppressed* the "no data for Paris" honesty
    banner. The gazetteer already covers every local authority, so the
    mined set was redundant as well as harmful. (conn kept for call
    compatibility; no longer read.)
    """
    return set(MAJOR_PLACES) | set(gazetteer()) | set(WELSH_ALIASES)


def detect_place(query: str, vocab: set[str]) -> str | None:
    """Return the authoritative UK place named in the query, if any.

    Longer names take precedence — the two-word window used to be the
    ceiling, which made all 62 three-plus-word authorities ("newcastle upon
    tyne", "bath and north east somerset") undetectable even though the
    gazetteer held them. Within a length, the last match wins, since the
    trailing place is usually the constraint ("flood risk in brighton").
    Only real places in `vocab` match — a query that names a place we don't
    hold (or a foreign city) returns None rather than a fabricated place,
    so the caller can be honest about coverage instead of silently
    guessing. A Welsh-language name comes back as the English form the
    index stores.
    """
    toks = _tokens(query)
    for size in range(min(6, len(toks)), 0, -1):
        found: str | None = None
        for i in range(len(toks) - size + 1):
            gram = " ".join(toks[i:i + size])
            if gram in vocab:
                found = gram
        if found:
            return WELSH_ALIASES.get(found, found)
    return None


def place_coverage(place: str, conn: sqlite3.Connection) -> int:
    """How many datasets plausibly relate to this place (publisher or title)."""
    q = " ".join(place.split())  # FTS phrase for multi-word places
    try:
        pub = conn.execute(
            'SELECT COUNT(*) FROM fts WHERE fts MATCH ?', (f'publisher:"{q}"',)
        ).fetchone()[0]
        title = conn.execute(
            'SELECT COUNT(*) FROM fts WHERE fts MATCH ?', (f'title:"{q}"',)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    return pub + title


def mentions_place(result: dict, place: str) -> bool:
    hay = f"{result.get('title', '')} {result.get('publisher', '')} " \
          f"{result.get('description', '')}".lower()
    return place in hay
