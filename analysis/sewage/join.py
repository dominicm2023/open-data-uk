"""Join EDM 2025 storm overflow annual returns to IMD 2019 deciles via LSOA 2011.

Pipeline:
  1. Parse the EA 'EDM 2025 Storm Overflow Annual Return' xlsx (All WaSC sheet).
  2. Parse OS National Grid references to easting/northing (metres, EPSG:27700).
  3. Assign each overflow to an LSOA two ways:
       a. point-in-polygon against ONS BSC (super-generalised) LSOA 2011 boundaries
          (fetched in EPSG:27700, so no datum transform is involved in the join);
       b. nearest population-weighted centroid (also EPSG:27700).
     Report the disagreement rate between the methods.
  4. Join IMD 2019 rank/decile (England only, E01*), RUC 2011 urban/rural,
     and a coastal flag (LSOA centroid within 5 km of the simplified coastline).
  5. Write joined.csv and findings.json.

Coordinate conversions (only used for the lon/lat convenience columns and the
coastal flag, never for the LSOA assignment itself): Transverse Mercator per
OS 'A guide to coordinate systems in Great Britain' + 7-parameter Helmert
between OSGB36 and WGS84 (accurate to ~5 m, ample for these purposes).
"""
import csv, io, json, math, os, zipfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')

# ---------------------------------------------------------------- NGR parsing
def ngr_to_en(ngr):
    """OS grid reference (e.g. 'SP6419046470') -> (easting, northing) at square centre."""
    if not ngr or not isinstance(ngr, str):
        return None
    s = ''.join(ngr.split()).upper()
    if len(s) < 4 or not s[:2].isalpha() or not s[2:].isdigit():
        return None
    def idx(c):
        i = ord(c) - ord('A')
        if c > 'I':
            i -= 1  # the grid skips letter I
        return i
    i1, i2 = idx(s[0]), idx(s[1])
    e100 = ((i1 - 2) % 5) * 5 + (i2 % 5)
    n100 = (19 - (i1 // 5) * 5) - (i2 // 5)
    digits = s[2:]
    if len(digits) % 2:
        return None
    h = len(digits) // 2
    cell = 10 ** (5 - h)
    e = e100 * 100000 + int(digits[:h]) * cell + cell / 2
    n = n100 * 100000 + int(digits[h:]) * cell + cell / 2
    if not (0 <= e < 800000 and 0 <= n < 1300000):
        return None
    return e, n

# ------------------------------------------------- OSGB36 <-> WGS84 transforms
_OSGB = (6377563.396, 6356256.909)   # Airy 1830
_WGS = (6378137.0, 6356752.3141)
_F0, _LAT0, _LON0, _E0, _N0 = 0.9996012717, math.radians(49), math.radians(-2), 400000.0, -100000.0

def _merid_arc(phi, a, b):
    n = (a - b) / (a + b)
    n2, n3 = n * n, n * n * n
    p, m = phi - _LAT0, phi + _LAT0
    return b * _F0 * (
        (1 + n + 1.25 * n2 + 1.25 * n3) * p
        - (3 * n + 3 * n2 + 2.625 * n3) * math.sin(p) * math.cos(m)
        + (1.875 * n2 + 1.875 * n3) * math.sin(2 * p) * math.cos(2 * m)
        - (35 / 24) * n3 * math.sin(3 * p) * math.cos(3 * m))

def _tm_inverse(E, N):
    """E/N (EPSG:27700) -> OSGB36 lat/lon (radians)."""
    a, b = _OSGB
    e2 = 1 - (b * b) / (a * a)
    phi = _LAT0 + (N - _N0) / (a * _F0)
    M = _merid_arc(phi, a, b)
    while abs(N - _N0 - M) > 1e-5:
        phi += (N - _N0 - M) / (a * _F0)
        M = _merid_arc(phi, a, b)
    sp, cp, tp = math.sin(phi), math.cos(phi), math.tan(phi)
    nu = a * _F0 / math.sqrt(1 - e2 * sp * sp)
    rho = a * _F0 * (1 - e2) / (1 - e2 * sp * sp) ** 1.5
    eta2 = nu / rho - 1
    VII = tp / (2 * rho * nu)
    VIII = tp / (24 * rho * nu ** 3) * (5 + 3 * tp ** 2 + eta2 - 9 * tp ** 2 * eta2)
    IX = tp / (720 * rho * nu ** 5) * (61 + 90 * tp ** 2 + 45 * tp ** 4)
    X = 1 / (cp * nu)
    XI = (nu / rho + 2 * tp ** 2) / (cp * 6 * nu ** 3)
    XII = (5 + 28 * tp ** 2 + 24 * tp ** 4) / (cp * 120 * nu ** 5)
    dE = E - _E0
    lat = phi - VII * dE ** 2 + VIII * dE ** 4 - IX * dE ** 6
    lon = _LON0 + X * dE - XI * dE ** 3 + XII * dE ** 5
    return lat, lon

def _tm_forward(lat, lon):
    """OSGB36 lat/lon (radians) -> E/N (EPSG:27700)."""
    a, b = _OSGB
    e2 = 1 - (b * b) / (a * a)
    sp, cp, tp = math.sin(lat), math.cos(lat), math.tan(lat)
    nu = a * _F0 / math.sqrt(1 - e2 * sp * sp)
    rho = a * _F0 * (1 - e2) / (1 - e2 * sp * sp) ** 1.5
    eta2 = nu / rho - 1
    M = _merid_arc(lat, a, b)
    I = M + _N0
    II = nu / 2 * sp * cp
    III = nu / 24 * sp * cp ** 3 * (5 - tp ** 2 + 9 * eta2)
    IIIA = nu / 720 * sp * cp ** 5 * (61 - 58 * tp ** 2 + tp ** 4)
    IV = nu * cp
    V = nu / 6 * cp ** 3 * (nu / rho - tp ** 2)
    VI = nu / 120 * cp ** 5 * (5 - 18 * tp ** 2 + tp ** 4 + 14 * eta2 - 58 * tp ** 2 * eta2)
    dl = lon - _LON0
    N = I + II * dl ** 2 + III * dl ** 4 + IIIA * dl ** 6
    E = _E0 + IV * dl + V * dl ** 3 + VI * dl ** 5
    return E, N

def _latlon_to_cart(lat, lon, ab):
    a, b = ab
    e2 = 1 - (b * b) / (a * a)
    nu = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return (nu * math.cos(lat) * math.cos(lon),
            nu * math.cos(lat) * math.sin(lon),
            (1 - e2) * nu * math.sin(lat))

def _cart_to_latlon(x, y, z, ab):
    a, b = ab
    e2 = 1 - (b * b) / (a * a)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(8):
        nu = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * nu * math.sin(lat), p)
    return lat, math.atan2(y, x)

# Helmert WGS84 -> OSGB36 (OS published parameters); invert signs for the reverse.
_H = dict(tx=-446.448, ty=125.157, tz=-542.060, s=20.4894e-6,
          rx=math.radians(-0.1502 / 3600), ry=math.radians(-0.2470 / 3600),
          rz=math.radians(-0.8421 / 3600))

def _helmert(x, y, z, sign):
    tx, ty, tz = sign * _H['tx'], sign * _H['ty'], sign * _H['tz']
    s = sign * _H['s']; rx, ry, rz = sign * _H['rx'], sign * _H['ry'], sign * _H['rz']
    return (tx + (1 + s) * x - rz * y + ry * z,
            ty + rz * x + (1 + s) * y - rx * z,
            tz - ry * x + rx * y + (1 + s) * z)

def bng_to_wgs84(E, N):
    lat, lon = _tm_inverse(E, N)
    x, y, z = _latlon_to_cart(lat, lon, _OSGB)
    x, y, z = _helmert(x, y, z, -1)
    lat, lon = _cart_to_latlon(x, y, z, _WGS)
    return math.degrees(lat), math.degrees(lon)

def wgs84_to_bng(lat_deg, lon_deg):
    x, y, z = _latlon_to_cart(math.radians(lat_deg), math.radians(lon_deg), _WGS)
    x, y, z = _helmert(x, y, z, +1)
    lat, lon = _cart_to_latlon(x, y, z, _OSGB)
    return _tm_forward(lat, lon)

# ------------------------------------------------------------- spatial indexes
CELL = 10000.0  # 10 km grid cells

class PolyIndex:
    def __init__(self, feats):
        self.feats = []
        self.grid = defaultdict(list)
        for f in feats:
            code = f['attributes']['LSOA11CD']
            rings = f['geometry']['rings']
            xs = [p[0] for r in rings for p in r]
            ys = [p[1] for r in rings for p in r]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            i = len(self.feats)
            self.feats.append((code, rings, bbox))
            for cx in range(int(bbox[0] // CELL), int(bbox[2] // CELL) + 1):
                for cy in range(int(bbox[1] // CELL), int(bbox[3] // CELL) + 1):
                    self.grid[(cx, cy)].append(i)

    @staticmethod
    def _pip(x, y, rings):
        """Even-odd ray cast across all rings (handles holes)."""
        inside = False
        for ring in rings:
            n = len(ring)
            j = n - 1
            for i in range(n):
                xi, yi = ring[i]; xj, yj = ring[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
        return inside

    def locate(self, x, y):
        for i in self.grid.get((int(x // CELL), int(y // CELL)), ()):
            code, rings, bb = self.feats[i]
            if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and self._pip(x, y, rings):
                return code
        return None

    @staticmethod
    def _seg_dist2(x, y, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return (x - ax) ** 2 + (y - ay) ** 2
        t = ((x - ax) * dx + (y - ay) * dy) / L2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        px, py = ax + t * dx, ay + t * dy
        return (x - px) ** 2 + (y - py) ** 2

    def ring_dist(self, x, y, rings):
        """Distance from point to polygon outline (metres)."""
        best = float('inf')
        for ring in rings:
            for i in range(len(ring)):
                ax, ay = ring[i - 1]
                bx, by = ring[i]
                d2 = self._seg_dist2(x, y, ax, ay, bx, by)
                if d2 < best:
                    best = d2
        return math.sqrt(best)

    def near(self, x, y, radius):
        """{code: distance} for polygons within radius of the point (0 = contains)."""
        out = {}
        cx, cy = int(x // CELL), int(y // CELL)
        cells = {(cx, cy)}
        # include neighbour cells when the point is within radius of a cell edge
        if x % CELL < radius: cells.add((cx - 1, cy))
        if CELL - x % CELL < radius: cells.add((cx + 1, cy))
        if y % CELL < radius: cells.add((cx, cy - 1))
        if CELL - y % CELL < radius: cells.add((cx, cy + 1))
        seen = set()
        for cell in cells:
            for i in self.grid.get(cell, ()):
                if i in seen:
                    continue
                seen.add(i)
                code, rings, bb = self.feats[i]
                if not (bb[0] - radius <= x <= bb[2] + radius
                        and bb[1] - radius <= y <= bb[3] + radius):
                    continue
                if (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]
                        and self._pip(x, y, rings)):
                    out[code] = 0.0
                    continue
                d = self.ring_dist(x, y, rings)
                if d <= radius:
                    out[code] = d
        return out

class CentroidIndex:
    def __init__(self, pts):  # pts: list of (code, x, y)
        self.grid = defaultdict(list)
        for code, x, y in pts:
            self.grid[(int(x // CELL), int(y // CELL))].append((code, x, y))

    def nearest(self, x, y):
        cx, cy = int(x // CELL), int(y // CELL)
        best, bd = None, float('inf')
        for ring in range(0, 30):
            cand = []
            for gx in range(cx - ring, cx + ring + 1):
                for gy in range(cy - ring, cy + ring + 1):
                    if max(abs(gx - cx), abs(gy - cy)) == ring:
                        cand.extend(self.grid.get((gx, gy), ()))
            for code, px, py in cand:
                d = (px - x) ** 2 + (py - y) ** 2
                if d < bd:
                    bd, best = d, code
            # once we have a hit, one more ring guarantees true nearest
            if best is not None and ring >= 1:
                break
        return best, math.sqrt(bd) if best else None

# --------------------------------------------------------------------- inputs
def load_edm():
    import openpyxl
    z = zipfile.ZipFile(os.path.join(RAW, 'EDM_2025_Storm_Overflow_Annual_Return.zip'))
    name = ('EDM_2025_Storm_Overflow_Annual_Return/'
            'EDM 2025 Storm Overflow Annual Return - all water and sewerage companies.xlsx')
    wb = openpyxl.load_workbook(io.BytesIO(z.read(name)), read_only=True)
    ws = wb['All WaSC']
    rows, skipped = [], defaultdict(int)
    for r in ws.iter_rows(min_row=8, values_only=True):
        uid = r[0]
        if not uid:
            continue
        company, site, ngr = r[1], r[2], r[8]
        dur_raw, spills_raw, op_pct = r[15], r[16], r[19]
        en = ngr_to_en(ngr if isinstance(ngr, str) else None)
        if en is None:
            skipped['bad_ngr'] += 1
            continue
        # duration: openpyxl yields timedelta (>24h), time (<24h) or 'hh:mm:ss' string
        import datetime
        hours = None
        if isinstance(dur_raw, datetime.timedelta):
            hours = dur_raw.total_seconds() / 3600
        elif isinstance(dur_raw, datetime.time):
            hours = dur_raw.hour + dur_raw.minute / 60 + dur_raw.second / 3600
        elif isinstance(dur_raw, str) and dur_raw.count(':') == 2:
            h, m, s = dur_raw.split(':')
            try:
                hours = int(h) + int(m) / 60 + int(s) / 3600
            except ValueError:
                pass
        elif isinstance(dur_raw, (int, float)):
            hours = float(dur_raw) * 24  # excel time serial, days
        if hours is None:
            skipped['bad_duration'] += 1
            continue
        if not isinstance(spills_raw, (int, float)):
            skipped['bad_spill_count'] += 1
            continue
        rows.append(dict(uid=uid, company=company, site=site, ngr=ngr,
                         e=en[0], n=en[1], spills=float(spills_raw),
                         hours=hours,
                         op_pct=float(op_pct) if isinstance(op_pct, (int, float)) else None))
    return rows, dict(skipped)

def main():
    print('loading EDM...')
    edm, skipped = load_edm()
    print(len(edm), 'overflows with usable NGR+counts; skipped:', skipped)

    print('loading geography...')
    pwc = json.load(open(os.path.join(RAW, 'lsoa2011_pwc.json')))
    cents = [(f['attributes']['lsoa11cd'], f['geometry']['x'], f['geometry']['y'])
             for f in pwc['features']]
    cidx = CentroidIndex(cents)
    bsc = json.load(open(os.path.join(RAW, 'lsoa2011_bsc.json')))
    pidx = PolyIndex(bsc['features'])
    bgc_path = os.path.join(RAW, 'lsoa2011_bgc.json')
    bidx = None
    if os.path.exists(bgc_path):
        bgc = json.load(open(bgc_path))
        bidx = PolyIndex(bgc['features'])
        print('BGC (20m generalised) boundaries loaded:', len(bgc['features']))

    imd = {}
    with open(os.path.join(RAW, 'IoD2019_File7_scores_ranks_deciles.csv'),
              encoding='utf-8-sig') as f:
        rd = csv.reader(f)
        hdr = next(rd)
        i_pop = next(i for i, c in enumerate(hdr) if c.startswith('Total population: mid 2015'))
        for row in rd:
            imd[row[0]] = dict(rank=int(row[5]), decile=int(row[6]), pop=float(row[i_pop]))
    print(len(imd), 'English LSOAs with IMD')

    ruc = {f['attributes']['LSOA11CD']: f['attributes']['RUC11CD']
           for f in json.load(open(os.path.join(RAW, 'ruc2011_lsoa.json')))['features']}

    # coastal flag per LSOA: centroid within 5 km of simplified coastline
    coast = json.load(open(os.path.join(HERE, '..', '..', 'coastline.json')))
    cpts = [wgs84_to_bng(p[1], p[0]) for ring in coast['rings'] for p in ring]
    cgrid = defaultdict(list)
    for x, y in cpts:
        cgrid[(int(x // CELL), int(y // CELL))].append((x, y))
    def near_coast(x, y, thresh=5000.0):
        cx, cy = int(x // CELL), int(y // CELL)
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for px, py in cgrid.get((gx, gy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 <= thresh ** 2:
                        return True
        return False
    coastal_lsoa = {code: near_coast(x, y) for code, x, y in cents}

    bfc_path = os.path.join(RAW, 'bfc_point_assignments.json')
    bfc_res = json.load(open(bfc_path)) if os.path.exists(bfc_path) else {}
    if bfc_res:
        print(len(bfc_res), 'points resolved against full-resolution BFC boundaries')

    print('assigning...')
    out, tallies = [], defaultdict(int)
    for r in edm:
        bsc_code = pidx.locate(r['e'], r['n'])
        bgc_code = bidx.locate(r['e'], r['n']) if bidx else None
        nc_code, nc_dist = cidx.nearest(r['e'], r['n'])
        bfc_entry = bfc_res.get(r['uid'])
        bfc_code = bfc_entry['bfc'] if bfc_entry else None
        if bfc_code:
            code, method = bfc_code, 'point_in_polygon_bfc'
            tallies['bfc'] += 1
        elif bgc_code:
            code, method = bgc_code, 'point_in_polygon_bgc'
            tallies['bgc'] += 1
        elif bsc_code:
            code, method = bsc_code, 'point_in_polygon_bsc'
            tallies['bgc_missed_bsc_hit'] += 1
        else:
            code, method = nc_code, 'nearest_centroid_fallback'
            tallies['pip_missed'] += 1
        r.update(lsoa=code, method=method, nc_code=nc_code, nc_dist=nc_dist,
                 bsc_code=bsc_code, bgc_code=bgc_code, bfc_code=bfc_code,
                 bfc_group=bfc_entry['group'] if bfc_entry else None)
        out.append(r)

    # validation: on the random sample of generalisation-agreed points, how often
    # does full resolution confirm the generalised assignment?
    val = [r for r in out if r['bfc_group'] == 'validation' and r['bfc_code']]
    validation = None
    if val:
        ok = sum(1 for r in val if r['bfc_code'] == r['bgc_code'])
        ok_dec = sum(1 for r in val
                     if (r['bfc_code'] in imd) == (r['bgc_code'] in imd)
                     and (r['bfc_code'] not in imd
                          or imd[r['bfc_code']]['decile'] == imd[r['bgc_code']]['decile']))
        validation = dict(n=len(val), lsoa_confirmed=ok,
                          lsoa_confirmed_pct=round(100 * ok / len(val), 2),
                          decile_confirmed=ok_dec,
                          decile_confirmed_pct=round(100 * ok_dec / len(val), 2))
        print('validation sample (BGC=BSC agreed points vs BFC):', validation)

    disp = [r for r in out if r['bfc_group'] == 'disputed' and r['bfc_code']]
    arbitration = None
    if disp:
        arbitration = dict(
            n=len(disp),
            bfc_sides_with_bgc=sum(1 for r in disp if r['bfc_code'] == r['bgc_code']),
            bfc_sides_with_bsc=sum(1 for r in disp if r['bfc_code'] == r['bsc_code']),
            bfc_sides_with_neither=sum(1 for r in disp if r['bfc_code'] not in
                                       (r['bgc_code'], r['bsc_code'])))
        print('BFC arbitration of disputed points:', arbitration)

    # ---- boundary-proximity test: is method disagreement explained by points
    # sitting on LSOA boundary lines (i.e. on watercourses)?
    print('computing distance to LSOA boundary + 100m candidate sets...')
    BUFFER = 100.0
    for r in out:
        idx = bidx if bidx else pidx
        cands = idx.near(r['e'], r['n'], BUFFER)
        if r['lsoa'] and r['lsoa'] not in cands:
            cands[r['lsoa']] = 0.0
        r['cands'] = cands
        # distance to nearest LSOA boundary = distance to own polygon's outline
        r['d_boundary'] = None
        for i in idx.grid.get((int(r['e'] // CELL), int(r['n'] // CELL)), ()):
            code, rings, bb = idx.feats[i]
            if code == (r['bgc_code'] or r['bsc_code']):
                r['d_boundary'] = idx.ring_dist(r['e'], r['n'], rings)
                break

    def dist_stats(rows):
        ds = sorted(r['d_boundary'] for r in rows if r['d_boundary'] is not None)
        if not ds:
            return None
        med = ds[len(ds) // 2]
        return dict(n=len(ds), median_m=round(med, 1),
                    pct_within_25m=round(100 * sum(d <= 25 for d in ds) / len(ds), 1),
                    pct_within_50m=round(100 * sum(d <= 50 for d in ds) / len(ds), 1),
                    pct_within_100m=round(100 * sum(d <= 100 for d in ds) / len(ds), 1))

    agree_rows = [r for r in out if r['bgc_code'] and r['bsc_code']
                  and r['bgc_code'] == r['bsc_code']]
    disagree_rows = [r for r in out if r['bgc_code'] and r['bsc_code']
                     and r['bgc_code'] != r['bsc_code']]
    boundary_proximity = dict(
        buffer_m=BUFFER,
        methods_agree=dist_stats(agree_rows),
        methods_disagree=dist_stats(disagree_rows),
        pct_overflows_with_multiple_candidate_lsoas_100m=round(
            100 * sum(1 for r in out if len(r['cands']) > 1) / len(out), 1),
        pct_overflows_with_multiple_candidate_deciles_100m=round(
            100 * sum(1 for r in out
                      if len({imd[c]['decile'] for c in r['cands'] if c in imd}) > 1)
            / len(out), 1),
    )
    print('boundary proximity:', boundary_proximity)

    def dec(c):
        return imd[c]['decile'] if c in imd else None

    def compare(a_key, b_key):
        both = [r for r in out if r[a_key] and r[b_key]]
        n = len(both)
        dc = sum(1 for r in both if r[a_key] != r[b_key])
        dd = sum(1 for r in both if dec(r[a_key]) != dec(r[b_key]))
        return dict(n=n, lsoa_disagreements=dc,
                    lsoa_disagreement_pct=round(100 * dc / n, 2) if n else None,
                    decile_disagreements=dd,
                    decile_disagreement_pct=round(100 * dd / n, 2) if n else None)

    cmp_bgc_bsc = compare('bgc_code', 'bsc_code') if bidx else None
    cmp_bgc_nc = compare('bgc_code', 'nc_code') if bidx else None
    cmp_bsc_nc = compare('bsc_code', 'nc_code')
    for label, c in [('BGC vs BSC', cmp_bgc_bsc), ('BGC vs centroid', cmp_bgc_nc),
                     ('BSC vs centroid', cmp_bsc_nc)]:
        if c:
            print(f"{label}: n={c['n']} lsoa {c['lsoa_disagreement_pct']}% "
                  f"decile {c['decile_disagreement_pct']}%")

    # England filter: keep rows whose assigned LSOA is in IMD (E01*)
    eng = [r for r in out if r['lsoa'] in imd]
    excluded_nonengland = len(out) - len(eng)
    print(len(eng), 'overflows in English LSOAs;', excluded_nonengland, 'excluded (Wales / unassigned)')

    with open(os.path.join(HERE, 'joined.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['unique_id', 'company', 'site_name', 'spill_count',
                    'total_duration_hours', 'easting', 'northing', 'lon', 'lat',
                    'lsoa_code', 'imd_decile', 'imd_rank', 'assignment_method',
                    'edm_operational_pct', 'urban', 'coastal',
                    'dist_to_lsoa_boundary_m', 'candidate_lsoas_100m',
                    'candidate_imd_deciles_100m'])
        for r in eng:
            lat, lon = bng_to_wgs84(r['e'], r['n'])
            m = imd[r['lsoa']]
            ru = ruc.get(r['lsoa'], '')
            cand_deciles = sorted({imd[c]['decile'] for c in r['cands'] if c in imd})
            w.writerow([r['uid'], r['company'], r['site'], r['spills'],
                        round(r['hours'], 2), round(r['e'], 1), round(r['n'], 1),
                        round(lon, 6), round(lat, 6), r['lsoa'], m['decile'],
                        m['rank'], r['method'], r['op_pct'],
                        1 if ru.startswith(('A', 'B', 'C')) else 0,
                        1 if coastal_lsoa.get(r['lsoa']) else 0,
                        round(r['d_boundary'], 1) if r['d_boundary'] is not None else '',
                        ';'.join(sorted(r['cands'])),
                        ';'.join(str(d) for d in cand_deciles)])

    # ------------------------------------------------------------- analysis
    def decile_table(rows, lsoa_filter=None):
        """Aggregate by decile; denominators are LSOA counts/population in-scope."""
        lsoas = {c: v for c, v in imd.items() if lsoa_filter is None or lsoa_filter(c)}
        agg = {d: dict(overflows=0, spills=0.0, hours=0.0, lsoas=0, pop=0.0,
                       _op_sum=0.0, _op_n=0)
               for d in range(1, 11)}
        for c, v in lsoas.items():
            agg[v['decile']]['lsoas'] += 1
            agg[v['decile']]['pop'] += v['pop']
        for r in rows:
            if r['lsoa'] not in lsoas:
                continue
            d = imd[r['lsoa']]['decile']
            agg[d]['overflows'] += 1
            agg[d]['spills'] += r['spills']
            agg[d]['hours'] += r['hours']
            if r['op_pct'] is not None:
                agg[d]['_op_sum'] += r['op_pct']
                agg[d]['_op_n'] += 1
        for d, a in agg.items():
            op_sum, op_n = a.pop('_op_sum'), a.pop('_op_n')
            a['mean_edm_operational_pct'] = op_sum / op_n if op_n else None
            a['spills_per_lsoa'] = a['spills'] / a['lsoas'] if a['lsoas'] else None
            a['hours_per_lsoa'] = a['hours'] / a['lsoas'] if a['lsoas'] else None
            a['spills_per_100k_pop'] = 1e5 * a['spills'] / a['pop'] if a['pop'] else None
            a['overflows_per_100_lsoas'] = 100 * a['overflows'] / a['lsoas'] if a['lsoas'] else None
            a['spills_per_overflow'] = a['spills'] / a['overflows'] if a['overflows'] else None
        return agg

    def spearman_deciles(agg, key):
        vals = [(d, agg[d][key]) for d in range(1, 11) if agg[d][key] is not None]
        n = len(vals)
        rk = {v: i + 1 for i, (_, v) in enumerate(sorted(vals, key=lambda t: t[1]))}
        num = sum((i + 1 - (n + 1) / 2) * (rk[v] - (n + 1) / 2) for i, (_, v) in enumerate(vals))
        den = math.sqrt(sum((i + 1 - (n + 1) / 2) ** 2 for i in range(n)) *
                        sum((rk[v] - (n + 1) / 2) ** 2 for _, v in vals))
        return num / den if den else None

    def half_ratio(agg, key):
        lo = sum(agg[d][key] for d in range(1, 6) if agg[d][key] is not None)
        hi = sum(agg[d][key] for d in range(6, 11) if agg[d][key] is not None)
        return lo / hi if hi else None

    strata = {
        'all_england': None,
        'urban_only': lambda c: ruc.get(c, '').startswith(('A', 'B', 'C')),
        'rural_only': lambda c: ruc.get(c, '').startswith(('D', 'E')),
        'coastal_only': lambda c: coastal_lsoa.get(c, False),
        'inland_only': lambda c: not coastal_lsoa.get(c, False),
    }
    findings = dict(
        inputs=dict(
            edm=dict(file='EDM_2025_Storm_Overflow_Annual_Return.zip', vintage='calendar year 2025',
                     publisher='Environment Agency (annual return, all English WaSCs)',
                     licence='OGL-UK-3.0',
                     url='https://www.data.gov.uk/dataset/event-duration-monitoring-storm-overflows-annual-returns'),
            imd=dict(file='IoD2019_File7_scores_ranks_deciles.csv', vintage='IMD 2019 (population denominators mid-2015)',
                     publisher='MHCLG', licence='OGL-UK-3.0'),
            lsoa_pwc=dict(file='lsoa2011_pwc.json', vintage='LSOA Dec 2011 population-weighted centroids (ONS, 2022 republication)'),
            lsoa_bsc=dict(file='lsoa2011_bsc.json', vintage='LSOA Dec 2011 boundaries, super-generalised clipped (BSC) V4 (ONS)'),
            ruc=dict(file='ruc2011_lsoa.json', vintage='Rural Urban Classification 2011 of LSOAs (ONS)'),
            coastline=dict(file='../../coastline.json', note='ultra-generalised ONS/OS coastline, ~1 km tolerance; used only for 5 km coastal flag'),
        ),
        parsing=dict(rows_skipped=skipped, overflows_parsed=len(edm),
                     overflows_england=len(eng), excluded_wales_or_unassigned=excluded_nonengland,
                     welsh_water_english_sites=sum(
                         1 for r in eng if 'Welsh Water' in (r['company'] or '')),
                     assignment_method_counts=dict(tallies)),
        method_comparison=dict(
            bgc_vs_bsc=cmp_bgc_bsc, bgc_vs_centroid=cmp_bgc_nc,
            bsc_vs_centroid=cmp_bsc_nc,
            validation_sample_agreed_points_vs_bfc=validation,
            bfc_arbitration_of_disputed=arbitration),
        boundary_proximity=boundary_proximity,
        strata={},
        band={},
    )
    # sensitivity: monitors operating >=90% of the year only (undercount control)
    eng_op90 = [r for r in eng if r['op_pct'] is not None and r['op_pct'] >= 90]
    findings['op90_note'] = (f"{len(eng_op90)} of {len(eng)} overflows had EDM "
                             "operational >=90% of the reporting period")
    row_sets = {name: eng for name in strata}
    strata['all_england_op90plus'] = None
    row_sets['all_england_op90plus'] = eng_op90

    for name, filt in strata.items():
        agg = decile_table(row_sets[name], filt)
        findings['strata'][name] = dict(
            deciles={d: {k: (round(v, 3) if isinstance(v, float) else v)
                         for k, v in a.items()} for d, a in agg.items()},
            spearman_decile_vs_spills_per_lsoa=round(spearman_deciles(agg, 'spills_per_lsoa'), 3),
            spearman_decile_vs_overflow_density=round(spearman_deciles(agg, 'overflows_per_100_lsoas'), 3),
            spearman_decile_vs_spills_per_overflow=round(spearman_deciles(agg, 'spills_per_overflow'), 3),
            deprived_half_over_affluent_half_spills_per_lsoa=round(half_ratio(agg, 'spills_per_lsoa'), 3),
            deprived_half_over_affluent_half_hours_per_lsoa=round(half_ratio(agg, 'hours_per_lsoa'), 3),
        )

    # ---- band analysis: where the assignment is ambiguous (any method
    # disagreement or any other LSOA within 100 m), push every ambiguous
    # overflow to its most-deprived candidate, then to its least-deprived
    # candidate. The truth lies between the two edges.
    def edge_rows(rows, pick):
        res = []
        for r in rows:
            cs = {c for c in r['cands']} | {r['lsoa'], r['bfc_code'],
                                            r['bgc_code'], r['bsc_code']}
            cs = [c for c in cs if c in imd]
            if not cs:
                continue
            r2 = dict(r)
            r2['lsoa'] = pick(cs, key=lambda c: imd[c]['decile'])
            res.append(r2)
        return res

    eng_dep = edge_rows(out, min)
    eng_aff = edge_rows(out, max)
    for name, filt in strata.items():
        if name == 'all_england_op90plus':
            continue
        entry = {}
        for edge, rows in [('deprived_edge', eng_dep), ('affluent_edge', eng_aff)]:
            agg = decile_table(rows, filt)
            entry[edge] = dict(
                spills_per_lsoa=[round(agg[d]['spills_per_lsoa'], 3) for d in range(1, 11)],
                spearman_decile_vs_spills_per_lsoa=round(
                    spearman_deciles(agg, 'spills_per_lsoa'), 3),
                deprived_half_over_affluent_half=round(
                    half_ratio(agg, 'spills_per_lsoa'), 3),
            )
        findings['band'][name] = entry
        print(f"band {name}: dep-edge rho={entry['deprived_edge']['spearman_decile_vs_spills_per_lsoa']} "
              f"ratio={entry['deprived_edge']['deprived_half_over_affluent_half']} | "
              f"aff-edge rho={entry['affluent_edge']['spearman_decile_vs_spills_per_lsoa']} "
              f"ratio={entry['affluent_edge']['deprived_half_over_affluent_half']}")

    with open(os.path.join(HERE, 'findings.json'), 'w', encoding='utf-8') as f:
        json.dump(findings, f, indent=1)
    print('wrote joined.csv and findings.json')

    # quick console summary
    for name in strata:
        s = findings['strata'][name]
        print(f"--- {name}: rho(spills/LSOA)={s['spearman_decile_vs_spills_per_lsoa']}, "
              f"deprived/affluent={s['deprived_half_over_affluent_half_spills_per_lsoa']}")
        print('    spills/LSOA by decile:',
              [s['deciles'][d]['spills_per_lsoa'] for d in range(1, 11)])

if __name__ == '__main__':
    # transform self-test: OS worked example (OSGB36 point) and a sanity roundtrip
    E, N = _tm_forward(math.radians(52 + 39 / 60 + 27.2531 / 3600),
                       math.radians(1 + 43 / 60 + 4.5177 / 3600))
    assert abs(E - 651409.903) < 0.01 and abs(N - 313177.270) < 0.01, (E, N)
    lat, lon = bng_to_wgs84(530000, 180000)
    assert abs(lat - 51.503) < 0.01 and abs(lon + 0.128) < 0.02, (lat, lon)
    e2, n2 = wgs84_to_bng(lat, lon)
    assert abs(e2 - 530000) < 1 and abs(n2 - 180000) < 1
    main()
