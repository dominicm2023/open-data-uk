"""Resolve ambiguous LSOA assignments against full-resolution (BFC) boundaries.

For every overflow where the BGC (20m) and BSC (200m) generalised boundaries
disagree — or where either misses (coastal clipping) — query the ONS BFC V3
FeatureServer for a server-side full-resolution point-in-polygon. Also queries
a fixed random sample of 300 'agreed' points to estimate residual error where
the two generalisations agree.

Output: raw/bfc_point_assignments.json  {uid: {"bfc": lsoa_or_null, "group": "disputed"|"validation"}}
"""
import json, os, random, sys, time, urllib.parse, urllib.request

sys.path.insert(0, r'C:\Users\domin\Documents\Open Data')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import HEADERS
import join as J

BFC = ('https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/'
       'Lower_layer_Super_Output_Areas_Dec_2011_Boundaries_Full_Clipped_BFC_EW_V3_2022/'
       'FeatureServer/0/query')
OUT = os.path.join(J.RAW, 'bfc_point_assignments.json')

def bfc_locate(e, n, retried=False):
    p = {'geometry': f'{e},{n}', 'geometryType': 'esriGeometryPoint', 'inSR': 27700,
         'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'LSOA11CD',
         'returnGeometry': 'false', 'f': 'json', 'where': '1=1'}
    u = BFC + '?' + urllib.parse.urlencode(p)
    try:
        d = json.loads(urllib.request.urlopen(
            urllib.request.Request(u, headers=HEADERS), timeout=60).read())
    except Exception as exc:
        if retried:
            print('  giving up:', exc)
            return '__error__'
        time.sleep(5)
        return bfc_locate(e, n, retried=True)
    feats = d.get('features', [])
    return feats[0]['attributes']['LSOA11CD'] if feats else None

def main():
    edm, _ = J.load_edm()
    pwc = json.load(open(os.path.join(J.RAW, 'lsoa2011_pwc.json')))
    bsc = json.load(open(os.path.join(J.RAW, 'lsoa2011_bsc.json')))
    bgc = json.load(open(os.path.join(J.RAW, 'lsoa2011_bgc.json')))
    pidx = J.PolyIndex(bsc['features'])
    bidx = J.PolyIndex(bgc['features'])

    disputed, agreed = [], []
    for r in edm:
        a = bidx.locate(r['e'], r['n'])
        b = pidx.locate(r['e'], r['n'])
        if a and b and a == b:
            agreed.append(r)
        else:
            disputed.append(r)
    print(len(disputed), 'disputed;', len(agreed), 'agreed')

    rng = random.Random(20260817)
    sample = rng.sample(agreed, 300)

    done = {}
    if os.path.exists(OUT):
        done = json.load(open(OUT))
        print('resuming with', len(done), 'already resolved')

    todo = [(r, 'disputed') for r in disputed] + [(r, 'validation') for r in sample]
    for i, (r, grp) in enumerate(todo):
        if r['uid'] in done:
            continue
        code = bfc_locate(r['e'], r['n'])
        if code == '__error__':
            continue
        done[r['uid']] = {'bfc': code, 'group': grp}
        if i % 100 == 0:
            print(i, '/', len(todo))
            with open(OUT, 'w') as f:
                json.dump(done, f)
        time.sleep(0.5)
    with open(OUT, 'w') as f:
        json.dump(done, f)
    print('done:', len(done), 'resolved ->', OUT)

if __name__ == '__main__':
    main()
