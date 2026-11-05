# -*- coding: utf-8 -*-
"""D2:取得模擬需要的公開資料並存到 raw/data.pkl(不進版控):1H 與 4H 的已收盤 K 線、資金費率歷史、合約規格(數量步長/最小名目)。全部是公開 GET,免金鑰。"""
import datetime, json, os, pickle, sys, time, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); os.makedirs(RAW, exist_ok=True); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import ccxt
import app as A
A.CCXT_AVAILABLE = True
CUR = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']
EXTRA = ['IMX/USDT', 'ARB/USDT', 'UNI/USDT']
SYMS = sorted({c['symbol'] for c in CUR} | set(EXTRA))
start1h = '2025-04-01'; start4h = '2024-12-15'
out = {'candles': {}, 'funding': {}, 'markets': {}, 'fetched_at': int(time.time() * 1000)}
for s in SYMS:
    t0 = time.time()
    for tf, st in (('1h', start1h), ('4h', start4h)):
        try:
            rows = A.fetch_data(s, st, interval=tf); out['candles'][(s, tf)] = [list(r) for r in rows]
        except Exception as e:
            out['candles'][(s, tf)] = []; print('fail', s, tf, str(e)[:80])
    print(s, {tf: len(out['candles'][(s, tf)]) for tf in ('1h', '4h')}, '%.0fs' % (time.time() - t0), flush=True)
pub = ccxt.binanceusdm({'enableRateLimit': True})                       # 沒有金鑰:只能打公開端點
mk = pub.load_markets()
for s in SYMS:
    m = mk.get(s + ':USDT') or mk.get(s)
    if m: out['markets'][s] = {'step': (m.get('precision') or {}).get('amount'), 'min_amount': ((m.get('limits') or {}).get('amount') or {}).get('min'), 'min_cost': ((m.get('limits') or {}).get('cost') or {}).get('min'), 'id': m['id']}
for s in SYMS:
    mid = out['markets'].get(s, {}).get('id')
    if not mid: continue
    rows = []; since = int(datetime.datetime(2025, 4, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    while True:
        r = pub.fapiPublicGetFundingRate({'symbol': mid, 'startTime': since, 'limit': 1000})
        if not r: break
        rows += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
        if len(r) < 1000: break
        since = int(r[-1]['fundingTime']) + 1
    out['funding'][s] = sorted(set(rows))
    print('funding', s, len(rows), flush=True)
pickle.dump(out, open(os.path.join(RAW, 'data.pkl'), 'wb'))
print('saved')
