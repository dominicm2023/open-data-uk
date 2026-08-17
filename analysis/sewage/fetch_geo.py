"""Fetch IMD 2019, LSOA 2011 PWC centroids, LSOA 2011 BSC boundaries, RUC 2011 lookup.

Sources (all recorded in REPORT.md):
- IMD 2019 File 7 (MHCLG, English Indices of Deprivation 2019), gov.uk assets.
- ONS Open Geography: LSOA Dec 2011 population-weighted centroids (2022 republication).
- ONS Open Geography: LSOA Dec 2011 boundaries, super-generalised clipped (BSC) V4.
- ONS: Rural Urban Classification (2011) of LSOAs in England and Wales.

Everything geographic is requested in EPSG:27700 (British National Grid) so the
EDM NGR coordinates join with no datum transform at all.
"""
import sys, os, json, time, urllib.request, urllib.parse

sys.path.insert(0, r'C:\Users\domin\Documents\Open Data')
from agent import HEADERS

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'raw')
os.makedirs(RAW, exist_ok=True)

_last = {}
def polite_get(url, host_delay=0.5):
    host = urllib.parse.urlparse(url).netloc
    dt = time.time() - _last.get(host, 0)
    if dt < host_delay:
        time.sleep(host_delay - dt)
    req = urllib.request.Request(url, headers=HEADERS)
    data = urllib.request.urlopen(req, timeout=60).read()
    _last[host] = time.time()
    return data

def fetch_imd():
    dest = os.path.join(RAW, 'IoD2019_File7_scores_ranks_deciles.csv')
    if os.path.exists(dest):
        print('imd: cached'); return
    candidates = [
        'https://assets.publishing.service.gov.uk/media/5d8b3b17ed915d0373d3540f/File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv',
        'https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/845345/File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv',
    ]
    for u in candidates:
        try:
            data = polite_get(u)
            if data[:20].lstrip().startswith(b'LSOA') or b'lsoa' in data[:200].lower():
                with open(dest, 'wb') as f: f.write(data)
                print('imd:', u, len(data), 'bytes'); return
        except Exception as e:
            print('imd candidate failed:', u, e)
    raise SystemExit('IMD File 7 not fetched')

def fetch_layer(base, out_name, out_fields='*', geometry=True, precision=None):
    dest = os.path.join(RAW, out_name)
    if os.path.exists(dest):
        print(out_name, ': cached'); return
    meta = json.loads(polite_get(base + '/0?f=json'))
    maxrec = meta.get('maxRecordCount', 1000)
    maxrec = min(maxrec, 2000)
    feats = []
    offset = 0
    while True:
        params = {
            'where': '1=1', 'outFields': out_fields, 'f': 'json',
            'resultOffset': offset, 'resultRecordCount': maxrec,
            'returnGeometry': 'true' if geometry else 'false',
            'orderByFields': meta.get('objectIdField', 'FID'),
        }
        if geometry:
            params['outSR'] = 27700
            if precision is not None:
                params['geometryPrecision'] = precision
        u = base + '/0/query?' + urllib.parse.urlencode(params)
        d = json.loads(polite_get(u))
        if 'error' in d:
            raise SystemExit(f'{out_name}: {d["error"]}')
        got = d.get('features', [])
        feats.extend(got)
        print(f'{out_name}: offset {offset} +{len(got)} (total {len(feats)})')
        if not d.get('exceededTransferLimit') and len(got) < maxrec:
            break
        offset += len(got)
        if not got:
            break
    with open(dest, 'w', encoding='utf-8') as f:
        json.dump({'fields': meta.get('fields'), 'features': feats}, f)
    print(out_name, ':', len(feats), 'features,', os.path.getsize(dest), 'bytes')

if __name__ == '__main__':
    fetch_imd()
    fetch_layer(
        'https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LSOA_Dec_2011_PWC_in_England_and_Wales_2022/FeatureServer',
        'lsoa2011_pwc.json', out_fields='LSOA11CD,LSOA11NM')
    fetch_layer(
        'https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Rural%20Urban%20Classification%20(2011)%20of%20Lower%20Layer%20Super%20Output%20Areas%20in%20England%20and%20Wales_new/FeatureServer',
        'ruc2011_lsoa.json', out_fields='*', geometry=False)
    fetch_layer(
        'https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LSOA_2011_Boundaries_Super_Generalised_Clipped_BSC_EW_V4/FeatureServer',
        'lsoa2011_bsc.json', out_fields='LSOA11CD', precision=1)
