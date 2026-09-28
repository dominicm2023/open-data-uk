"""A postcode district for a register row that gives no postcode, from what
it does give: a street address, or a point.

Some councils publish their HMO register with each property's street
address and no postcode (Milton Keynes, Basingstoke, Chorley...), or as map
layers with coordinates (Bristol). The family still publishes nothing finer
than a postcode district; this module works that district out, and the
address or point it was worked out from is dropped as soon as it has.

The source is OS Open Names (Ordnance Survey, Open Government Licence v3):
every named road in Great Britain with the postcode district, the settlement
and the council it lies in, and every postcode unit with its centre.

  Contains OS data (c) Crown copyright and database right 2026
  Contains Royal Mail data (c) Royal Mail copyright and database right 2026
  Contains National Statistics data (c) Crown copyright and database right 2026

A street address gives a district only when it can be read without a guess:
the street is found among the named roads of the council's own area, and
all of that street's entries lie in one district, or the settlement the
address names settles which. A street name the council has twice, in two
districts, with nothing in the address to choose between them, gives no
district. A point gives the district of the nearest postcode unit's centre.

The download (100 MB) is not in the repository: it is unpacked once on the
box under DATA_DIR/geo/opennames, and `python families/place.py index`
builds DATA_DIR/geo/opennames/names.sqlite from it.
"""
from __future__ import annotations

import csv
import functools
import math
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import DATA_DIR  # noqa: E402

HERE = DATA_DIR / "geo" / "opennames"
INDEX = HERE / "names.sqlite"
ATTRIBUTION = ("Districts worked out from street addresses and points: contains OS data (c) Crown copyright and "
               "database right 2026; contains Royal Mail data (c) Royal Mail copyright and database right 2026; "
               "contains National Statistics data (c) Crown copyright and database right 2026.")

# Written forms of the same street: 'Rd' and 'Road', 'St' and 'Street' and
# 'Saint'. Both sides are brought to the short form before comparing.
_SHORT = {"road": "rd", "street": "st", "saint": "st", "avenue": "ave", "lane": "ln", "close": "cl", "drive": "dr",
          "crescent": "cres", "court": "ct", "place": "pl", "square": "sq", "terrace": "ter", "gardens": "gdns",
          "grove": "gr", "park": "pk", "parade": "pde", "mount": "mt", "north": "n", "south": "s", "east": "e",
          "west": "w", "upper": "upr", "lower": "lwr", "the": ""}
_PC = re.compile(r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s*[0-9][A-Z]{2}\b", re.I)


def norm(text: str) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"['’`]", "", str(text).lower())).split()
    return " ".join(w for w in (_SHORT.get(w, w) for w in words) if w)


def build_index() -> int:
    """names.sqlite from the Open Names CSVs: named roads, settlements and
    postcode units, with the columns this module reads."""
    header = next(csv.reader(open(HERE / "Doc" / "OS_Open_Names_Header.csv", encoding="utf-8-sig")))
    col = {n: i for i, n in enumerate(header)}
    tmp = INDEX.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("""
        CREATE TABLE road (name TEXT, district TEXT, place TEXT, authority TEXT);
        CREATE TABLE settlement (name TEXT, authority TEXT);
        CREATE TABLE unit (district TEXT, x REAL, y REAL, gx INTEGER, gy INTEGER);
    """)
    n = 0
    for f in sorted((HERE / "Data").glob("*.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.reader(fh):
                kind, local = r[col["TYPE"]], r[col["LOCAL_TYPE"]]
                authority = r[col["DISTRICT_BOROUGH"]] or r[col["COUNTY_UNITARY"]]
                if local in ("Named Road", "Section Of Named Road"):
                    for name in {r[col["NAME1"]], r[col["NAME2"]]} - {""}:
                        db.execute("INSERT INTO road VALUES (?,?,?,?)", (norm(name), r[col["POSTCODE_DISTRICT"]],
                                   norm(r[col["POPULATED_PLACE"]]), authority))
                elif kind == "populatedPlace":
                    for name in {r[col["NAME1"]], r[col["NAME2"]]} - {""}:
                        db.execute("INSERT INTO settlement VALUES (?,?)", (norm(name), authority))
                elif local == "Postcode":
                    x, y = float(r[col["GEOMETRY_X"]]), float(r[col["GEOMETRY_Y"]])
                    district = r[col["NAME1"]].split()[0]
                    db.execute("INSERT INTO unit VALUES (?,?,?,?,?)", (district, x, y, int(x // 1000), int(y // 1000)))
                n += 1
    db.executescript("""
        CREATE INDEX road_authority ON road(authority);
        CREATE INDEX settlement_authority ON settlement(authority);
        CREATE INDEX unit_grid ON unit(gx, gy);
    """)
    db.commit()
    db.close()
    tmp.replace(INDEX)
    return n


@functools.lru_cache(maxsize=1)
def _db() -> sqlite3.Connection | None:
    """The index, or None where it has not been built (a fresh box, CI):
    then nothing is worked out, and rows without a postcode are set aside."""
    if not INDEX.is_file():
        return None
    return sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True, check_same_thread=False)


def authorities() -> list[str]:
    return [a for (a,) in _db().execute("SELECT DISTINCT authority FROM road ORDER BY 1")]


@functools.lru_cache(maxsize=64)
def _area(authorities: tuple[str, ...]) -> tuple[dict, set]:
    """The named roads of the council's area, name to {district: [places]},
    and the names of its settlements."""
    q = ",".join("?" * len(authorities))
    roads: dict[str, dict[str, set]] = {}
    for name, district, place in _db().execute(f"SELECT name, district, place FROM road WHERE authority IN ({q})", authorities):
        if district:
            roads.setdefault(name, {}).setdefault(district, set()).add(place)
    places = {p for (p,) in _db().execute(f"SELECT name FROM settlement WHERE authority IN ({q})", authorities)}
    return roads, places


def district_from_street(address: str, authorities: tuple[str, ...]) -> str | None:
    """The postcode district of the street an address names, within the
    council's area, or None where that cannot be read without a guess."""
    if not address or not authorities or _db() is None:
        return None
    roads, places = _area(tuple(authorities))
    words = norm(_PC.sub(" ", str(address))).split()
    # The street is the longest run of the address's words that is a named
    # road of the area ('high st' inside '14 high st wolverton'); where two
    # runs are equally long the address names two roads, and it is not read.
    found: list[str] = []
    for size in range(min(8, len(words)), 0, -1):
        found = [" ".join(words[i:i + size]) for i in range(len(words) - size + 1)
                 if " ".join(words[i:i + size]) in roads]
        if found:
            break
    found = list(dict.fromkeys(found))
    if len(found) != 1 or len(found[0].split()) == 1 and found[0] in places:
        return None
    districts = roads[found[0]]
    if len(districts) == 1:
        return next(iter(districts))
    # A street in more than one district: the settlement the address names
    # (after the street) settles it, if it points to exactly one.
    text = " " + " ".join(words) + " "
    named = {p for p in places if p and f" {p} " in text and p != found[0]}
    hits = {d for d, ps in districts.items() if ps & named}
    return next(iter(hits)) if len(hits) == 1 else None


def lonlat_to_osgb(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 longitude and latitude to British National Grid easting and
    northing, by the Ordnance Survey's Helmert transformation (a few metres
    out at most: far inside any postcode unit's reach)."""
    a, b = 6378137.000, 6356752.3142                                    # WGS84
    phi, lam = math.radians(lat), math.radians(lon)
    e2 = 1 - b * b / (a * a)
    nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    x, y, z = (nu * math.cos(phi) * math.cos(lam), nu * math.cos(phi) * math.sin(lam), nu * (1 - e2) * math.sin(phi))
    tx, ty, tz, s = -446.448, 125.157, -542.060, 20.4894e-6          # WGS84 to OSGB36
    rx, ry, rz = (math.radians(v / 3600) for v in (-0.1502, -0.2470, -0.8421))
    x2 = tx + (1 + s) * x - rz * y + ry * z
    y2 = ty + rz * x + (1 + s) * y - rx * z
    z2 = tz - ry * x + rx * y + (1 + s) * z
    a, b = 6377563.396, 6356256.909                                     # Airy 1830
    e2 = 1 - b * b / (a * a)
    p = math.hypot(x2, y2)
    phi = math.atan2(z2, p * (1 - e2))
    for _ in range(10):
        nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(z2 + e2 * nu * math.sin(phi), p)
    lam = math.atan2(y2, x2)
    F0, phi0, lam0, N0, E0 = 0.9996012717, math.radians(49), math.radians(-2), -100000, 400000
    n = (a - b) / (a + b)
    nu = a * F0 / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    rho = a * F0 * (1 - e2) / (1 - e2 * math.sin(phi) ** 2) ** 1.5
    eta2 = nu / rho - 1
    dp, sp = phi - phi0, phi + phi0
    M = b * F0 * ((1 + n + 1.25 * n * n + 1.25 * n ** 3) * dp - (3 * n + 3 * n * n + 2.625 * n ** 3) * math.sin(dp) * math.cos(sp)
                  + (1.875 * n * n + 1.875 * n ** 3) * math.sin(2 * dp) * math.cos(2 * sp) - (35 / 24) * n ** 3 * math.sin(3 * dp) * math.cos(3 * sp))
    c, sn, t = math.cos(phi), math.sin(phi), math.tan(phi)
    I, II = M + N0, nu / 2 * sn * c
    III = nu / 24 * sn * c ** 3 * (5 - t * t + 9 * eta2)
    IIIA = nu / 720 * sn * c ** 5 * (61 - 58 * t * t + t ** 4)
    IV = nu * c
    V = nu / 6 * c ** 3 * (nu / rho - t * t)
    VI = nu / 120 * c ** 5 * (5 - 18 * t * t + t ** 4 + 14 * eta2 - 58 * t * t * eta2)
    dl = lam - lam0
    return E0 + IV * dl + V * dl ** 3 + VI * dl ** 5, I + II * dl ** 2 + III * dl ** 4 + IIIA * dl ** 6


def district_from_point(x: float, y: float, lonlat: bool = False, reach_m: float = 400) -> str | None:
    """The district of the postcode unit whose centre is nearest the point,
    if one lies within reach (a point in open country, or off by a
    transposition, gives none)."""
    if _db() is None:
        return None
    if lonlat:
        x, y = lonlat_to_osgb(x, y)
    gx, gy = int(x // 1000), int(y // 1000)
    best, best_d = None, reach_m
    for d, ux, uy in _db().execute("SELECT district, x, y FROM unit WHERE gx BETWEEN ? AND ? AND gy BETWEEN ? AND ?",
                                   (gx - 1, gx + 1, gy - 1, gy + 1)):
        dist = math.hypot(ux - x, uy - y)
        if dist < best_d:
            best, best_d = d, dist
    return best


if __name__ == "__main__":
    if sys.argv[1:2] == ["index"]:
        print(f"{build_index():,} Open Names entries read -> {INDEX}")
    elif sys.argv[1:2] == ["authorities"]:
        print("\n".join(authorities()))
