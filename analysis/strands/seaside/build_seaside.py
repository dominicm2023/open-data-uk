"""THE SEASIDE SEWAGE LEAGUE - build script.

Inputs (all local, no network):
  analysis/sewage/joined.csv   - 14,180 English storm overflows, EDM annual return, calendar 2025
  gazetteer.json               - place name -> [lon, lat] (441 UK local-authority districts + aliases)
  coastline.json               - ultra-generalised UK countries boundary rings (ONS/OS, OGL v3)
  analysis/ro/ro_per_head.csv  - used ONLY as the England local-authority name/class register (2024-25 rows)

Method (stated on every output):
  1. Universe = gazetteer entries that match an English local authority in the RO 2024-25
     register (names normalised; aliases deduped by register name). England only.
  2. Coastal candidates = LAD centroid within 12 km of the generalised coastline
     (10 km search radius + 2 km slack for the ~1.3 km generalisation tolerance,
     i.e. the search circle must plausibly reach the sea).
  3. Curated exclusions, every one named with a reason: London boroughs (the generalised
     boundary treats the tidal Thames as coast) and estuary/river-frontage districts with
     no recognised seaside resort (ports, upstream tidal reaches).
  4. League metric = total monitored spill events and spill-hours in calendar 2025 at
     overflows within 10 km (haversine) of the district centroid. Circles overlap:
     rows are NOT additive. Company coastal totals therefore use the UNION of sites.

Outputs -> analysis/strands/seaside/
  seaside_league.csv, town_cards.csv, company_totals.csv, map_points.csv, top20_sites.csv
"""
import csv
import json
import math
import re
from pathlib import Path

BASE = Path(r"C:\Users\domin\Documents\Open Data")
OUT = BASE / "analysis" / "strands" / "seaside"
OUT.mkdir(parents=True, exist_ok=True)

RADIUS_KM = 10.0
COAST_THRESHOLD_KM = 12.0

# ---------------------------------------------------------------- name matching
def norm(s: str) -> str:
    s = s.casefold().strip()
    s = re.sub(r"\s+(ua|dc|bc|mbc|cc)$", "", s)          # RO suffixes: 'Tendring DC', 'Boston BC', 'Torbay UA'
    s = s.replace(" & ", " and ").replace(chr(8217), "'")
    s = re.sub(r"[.']", "", s)
    s = re.sub(r"[,\-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

# RO register name -> gazetteer name, where they genuinely differ
RO_ALIASES = {
    "medway towns": "medway",
    "the medway towns": "medway",
    "durham": "county durham",
    "newcastle": "newcastle upon tyne",   # RO 2024-25 calls Newcastle upon Tyne 'Newcastle'
}

# ------------------------------------------------- curated exclusions (rule 3)
# norm-key -> reason. Every candidate the distance rule admits but the league drops.
EXCLUDE = {
    "halton": "upstream Mersey tidal river, no seaside frontage",
    "knowsley": "inland; admitted only via the generalised Mersey estuary",
    "warrington": "upstream Mersey tidal river",
    "liverpool": "Mersey estuary port city; nearest beaches are in Sefton",
    "cheshire west and chester": "Dee estuary, no recognised seaside resort",
    "west lancashire": "Ribble estuary marsh, no seaside resort",
    "preston": "Ribble tidal river",
    "south ribble": "Ribble tidal river",
    "gateshead": "Tyne tidal river",
    "newcastle upon tyne": "Tyne tidal river; coast belongs to North Tyneside",
    "middlesbrough": "Tees estuary",
    "stockton on tees": "Tees estuary",
    "kingston upon hull": "Humber estuary port, no seaside resort",
    "north lincolnshire": "Humber estuary, no seaside resort",
    "bristol": "Avon/Severn estuary port",
    "south gloucestershire": "Severn estuary, no seaside resort",
    "forest of dean": "Severn tidal river",
    "exeter": "Exe estuary city; the seaside is East Devon/Teignbridge",
    "ipswich": "Orwell estuary port",
    "colchester": "Colne estuary; centroid circle sits on the city, not West Mersea",
    "maldon": "Blackwater estuary",
    "chelmsford": "inland; admitted only via generalised Essex estuaries",
    "basildon": "Thames estuary industrial frontage",
    "thurrock": "Thames estuary industrial frontage",
    "dartford": "tidal Thames",
    "gravesham": "tidal Thames",
    "rochford": "Crouch/Roach estuary, no seaside resort",
    "medway": "Medway estuary towns, no seaside resort (Sheppey's resorts are Swale)",
    "eastleigh": "Southampton Water, no seaside resort",
    "southampton": "estuary port city, no seaside resort",
    "fareham": "Portsmouth Harbour frontage, no seaside resort",
    "boston": "the Wash, no seaside resort (Skegness is East Lindsey)",
    "south holland": "the Wash marshes, no seaside resort",
    "st helens": "inland; admitted only via the generalised Mersey estuary",
}

# ---------------------------------------------------------------- geometry
def hav_km(lon1, lat1, lon2, lat2):
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def seg_dist_m(lon, lat, ax, ay, bx, by):
    k = math.cos(math.radians(lat)) * 111320.0
    ky = 110574.0
    ax, ay = (ax - lon) * k, (ay - lat) * ky
    bx, by = (bx - lon) * k, (by - lat) * ky
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)

def coast_dist_km(rings, lon, lat):
    best = 1e12
    for ring in rings:
        for i in range(len(ring) - 1):
            (ax, ay), (bx, by) = ring[i], ring[i + 1]
            if min(ax, bx) - 0.8 > lon or max(ax, bx) + 0.8 < lon:
                continue
            if min(ay, by) - 0.5 > lat or max(ay, by) + 0.5 < lat:
                continue
            d = seg_dist_m(lon, lat, ax, ay, bx, by)
            if d < best:
                best = d
    return best / 1000.0

# ---------------------------------------------------------------- load
gaz = json.load(open(BASE / "gazetteer.json"))
rings = json.load(open(BASE / "coastline.json"))["rings"]

register = {}  # norm gazetteer key -> (display name, cls)
with open(BASE / "analysis" / "ro" / "ro_per_head.csv", newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        if row["year"] != "2024-25":
            continue
        display = re.sub(r"\s+(UA|DC|BC|MBC)$", "", row["name"].strip())
        key = norm(row["name"])
        key = RO_ALIASES.get(key, key)
        register.setdefault(key, (display, row["cls"]))

sites = []
with open(BASE / "analysis" / "sewage" / "joined.csv", newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        sites.append({
            "unique_id": row["unique_id"],
            "company": row["company"],
            "site_name": row["site_name"],
            "lon": float(row["lon"]),
            "lat": float(row["lat"]),
            "spills": float(row["spill_count"] or 0),
            "hours": float(row["total_duration_hours"] or 0),
            "coastal_flag": row["coastal"] == "1",   # LSOA centroid within 5 km of coastline (join.py)
        })
assert len(sites) == 14180, f"expected 14,180 overflows, got {len(sites)}"

# ---------------------------------------------------------------- rules 1-3: the town list
towns = []        # kept
dropped = []      # curated exclusions actually applied (for notes)
seen_display = set()
for gname, (lon, lat) in gaz.items():
    key = norm(gname)
    if key not in register:
        continue                       # not an English LA -> out (England only)
    display, cls = register[key]
    if display in seen_display:
        continue                       # alias dedupe
    d = coast_dist_km(rings, lon, lat)
    if d > COAST_THRESHOLD_KM:
        continue                       # centroid circle cannot plausibly reach the sea
    seen_display.add(display)
    if cls == "LB":
        dropped.append((display, cls, round(d, 2), "London borough - tidal Thames, not seaside"))
        continue
    if key in EXCLUDE:
        dropped.append((display, cls, round(d, 2), EXCLUDE[key]))
        continue
    towns.append({"town": display, "gaz_key": gname, "cls": cls,
                  "lon": lon, "lat": lat, "coast_km": round(d, 2)})

towns.sort(key=lambda t: t["town"])
print(f"league towns: {len(towns)}   curated exclusions applied: {len(dropped)}")

# ---------------------------------------------------------------- rule 4: the league
for t in towns:
    near = []
    for s in sites:
        d = hav_km(t["lon"], t["lat"], s["lon"], s["lat"])
        if d <= RADIUS_KM:
            near.append((d, s))
    t["n_overflows"] = len(near)
    t["n_spilled"] = sum(1 for _, s in near if s["spills"] > 0)
    t["spills"] = sum(s["spills"] for _, s in near)
    t["hours"] = sum(s["hours"] for _, s in near)
    t["site_ids"] = {s["unique_id"] for _, s in near}
    if near:
        wd, ws = max(near, key=lambda p: p[1]["hours"])
        t["worst"] = (ws["site_name"], ws["company"], ws["spills"], ws["hours"], wd)
    else:
        t["worst"] = ("", "", 0, 0.0, 0.0)

league = sorted(towns, key=lambda t: -t["hours"])

with open(OUT / "seaside_league.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["rank", "town", "council_class", "lon", "lat", "centroid_to_coast_km",
                "overflows_within_10km", "overflows_that_spilled", "spills_2025", "hours_2025"])
    for i, t in enumerate(league, 1):
        w.writerow([i, t["town"], t["cls"], t["lon"], t["lat"], t["coast_km"],
                    t["n_overflows"], t["n_spilled"], int(t["spills"]), round(t["hours"], 1)])

CAVEATS = {
    "Sefton": ("10 km circle crosses the Mersey: includes Birkenhead WWTW (Wirral bank), "
               "~9.4 km from the Sefton centroid - centroid-radius crudeness, disclosed"),
    "Cornwall": ("one vast unitary; centroid sits mid-county - this row measures the centroid "
                 "circle, not Newquay/St Ives/Penzance"),
    "Somerset": ("unitary centroid sits near Taunton, inland; this row mostly counts inland "
                 "overflows, not Minehead/Burnham-on-Sea"),
    "Cumberland": ("large unitary; centroid circle covers the Workington/Maryport coast, "
                   "not St Bees or Silloth"),
    "East Suffolk": ("large district; centroid sits inland near Saxmundham - Lowestoft, "
                     "Felixstowe and Southwold are outside or at the edge of the circle"),
}
with open(OUT / "town_cards.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["town", "council_class", "overflows_within_10km", "overflows_that_spilled",
                "spills_2025", "hours_2025", "worst_site_name", "worst_site_company",
                "worst_site_spills", "worst_site_hours", "worst_site_km_from_centroid", "caveat"])
    for t in league:
        name, comp, sp, hr, dist = t["worst"]
        w.writerow([t["town"], t["cls"], t["n_overflows"], t["n_spilled"],
                    int(t["spills"]), round(t["hours"], 1),
                    name, comp, int(sp), round(hr, 1), round(dist, 2),
                    CAVEATS.get(t["town"], "")])

# ---------------------------------------------------------------- companies
coastal_ids = set()
for t in towns:
    coastal_ids |= t["site_ids"]

comp = {}
for s in sites:
    d = comp.setdefault(s["company"], {"n": 0, "sp": 0.0, "hr": 0.0,
                                       "cn": 0, "csp": 0.0, "chr": 0.0,
                                       "fn": 0, "fsp": 0.0, "fhr": 0.0})
    d["n"] += 1; d["sp"] += s["spills"]; d["hr"] += s["hours"]
    if s["unique_id"] in coastal_ids:
        d["cn"] += 1; d["csp"] += s["spills"]; d["chr"] += s["hours"]
    if s["coastal_flag"]:
        d["fn"] += 1; d["fsp"] += s["spills"]; d["fhr"] += s["hours"]

tot_hr = sum(d["hr"] for d in comp.values())
tot_chr = sum(d["chr"] for d in comp.values())
tot_fhr = sum(d["fhr"] for d in comp.values())
with open(OUT / "company_totals.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["company", "overflows_england", "spills_england_2025", "hours_england_2025",
                "share_of_england_hours_pct",
                "overflows_seaside_league", "spills_seaside_league", "hours_seaside_league",
                "share_of_seaside_hours_pct",
                "overflows_coastal_5km_lsoa", "spills_coastal_5km_lsoa", "hours_coastal_5km_lsoa",
                "share_of_coastal_5km_hours_pct"])
    for c, d in sorted(comp.items(), key=lambda kv: -kv[1]["hr"]):
        w.writerow([c, d["n"], int(d["sp"]), round(d["hr"], 1),
                    round(100 * d["hr"] / tot_hr, 1),
                    d["cn"], int(d["csp"]), round(d["chr"], 1),
                    round(100 * d["chr"] / tot_chr, 1) if tot_chr else 0,
                    d["fn"], int(d["fsp"]), round(d["fhr"], 1),
                    round(100 * d["fhr"] / tot_fhr, 1) if tot_fhr else 0])

# ---------------------------------------------------------------- map points + top 20
def nearest_town(s):
    best, bt = 1e12, ""
    for t in towns:
        d = hav_km(t["lon"], t["lat"], s["lon"], s["lat"])
        if d < best:
            best, bt = d, t["town"]
    return bt, best

with open(OUT / "map_points.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["unique_id", "company", "site_name", "lon", "lat", "spills_2025", "hours_2025",
                "in_seaside_league_10km", "nearest_league_town", "nearest_league_town_km"])
    for s in sites:
        nt, nd = nearest_town(s)
        w.writerow([s["unique_id"], s["company"], s["site_name"], s["lon"], s["lat"],
                    int(s["spills"]), round(s["hours"], 1),
                    1 if s["unique_id"] in coastal_ids else 0, nt, round(nd, 2)])

with open(OUT / "top20_sites.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["scope", "rank", "site_name", "company", "spills_2025", "hours_2025",
                "lon", "lat", "nearest_league_town", "nearest_league_town_km"])
    for scope, pool in [("england", sites),
                        ("seaside_league", [s for s in sites if s["unique_id"] in coastal_ids])]:
        for i, s in enumerate(sorted(pool, key=lambda x: -x["hours"])[:20], 1):
            nt, nd = nearest_town(s)
            w.writerow([scope, i, s["site_name"], s["company"], int(s["spills"]),
                        round(s["hours"], 1), s["lon"], s["lat"], nt, round(nd, 2)])

# ---------------------------------------------------------------- verification prints
print("\n== league top 15 (hours) ==")
for i, t in enumerate(league[:15], 1):
    print(f"{i:2d}. {t['town']:35s} {t['cls']:2s} sites={t['n_overflows']:4d} "
          f"spills={int(t['spills']):6d} hours={t['hours']:10.1f}")
print("\n== league bottom 5 ==")
for t in league[-5:]:
    print(f"    {t['town']:35s} {t['cls']:2s} sites={t['n_overflows']:4d} "
          f"spills={int(t['spills']):6d} hours={t['hours']:10.1f}")
print("\n== slate cross-checks ==")
for probe in ["East Devon", "Torbay", "Sefton", "Blackpool", "Thanet"]:
    m = [t for t in league if t["town"] == probe]
    if m:
        print(f"  {probe}: hours={m[0]['hours']:.1f} spills={int(m[0]['spills'])}")
    else:
        print(f"  {probe}: NOT IN LEAGUE")
sww = comp.get("South West Water")
print(f"  South West Water total hours: {sww['hr']:.1f} | seaside-league hours: {sww['chr']:.1f} "
      f"| coastal-5km-flag hours: {sww['fhr']:.1f}")
for key, label in [("chr", "league-union"), ("fhr", "coastal-flag")]:
    ranked = sorted(comp.items(), key=lambda kv: -kv[1][key])
    if len(ranked) > 1 and ranked[1][1][key]:
        print(f"  {label} leader ratio: {ranked[0][0]} = "
              f"{ranked[0][1][key]/ranked[1][1][key]:.2f}x {ranked[1][0]}")
print(f"  coastal union: {len(coastal_ids)} overflows within 10 km of a league town")
print("\n== curated exclusions applied ==")
for name, cls, d, reason in sorted(dropped):
    print(f"  {name:32s} {cls:2s} {d:6.2f} km  {reason}")
print("\n== league towns ==")
print(", ".join(t["town"] for t in sorted(towns, key=lambda x: x["town"])))
