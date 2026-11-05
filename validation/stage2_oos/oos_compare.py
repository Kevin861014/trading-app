# -*- coding: utf-8 -*-
"""usage: python oos_compare.py <code_dir> <out.json>
Runs /api/best_strategy and /api/deep_analysis on cached identical data and records the OOS-related fields."""
import sys, os, json, warnings
warnings.filterwarnings('ignore')
code_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, code_dir)
SP = os.path.dirname(os.path.abspath(__file__))
import app as A
def cached(sym, tf): return json.load(open(os.path.join(SP, 'ba_cache', sym.replace('/', '_') + '_' + tf + '.json')))
A.fetch_data = lambda sym, start, interval='1d': cached(sym, interval)
A.IS_RENDER = False
c = A.app.test_client(); res = {}
def pick(x):
    return dict(s=x['strat'], pf=x['pf'], trades=x['trades'], total=x['total'], oosPf=x.get('oosPf'), oosTrades=x.get('oosTrades'),
                oosPass=x.get('oosPass'), status=x.get('oosStatus'), trust=x.get('trust'), full=(x.get('full') or {}).get('total'), oos=(x.get('oos') or {}).get('total'))
for kind, targets in (('best', [('BTC/USDT', '4h'), ('SOL/USDT', '4h'), ('2330.TW', '1d'), ('AAPL', '1d'), ('NVDA', '1d')]),
                      ('deep', [('BTC/USDT', '4h'), ('2330.TW', '1d')])):
    for sym, tf in targets:
        path = '/api/best_strategy' if kind == 'best' else '/api/deep_analysis'
        qs = dict(symbol=sym, timeframe=tf, use_oos='1')
        if kind == 'best': qs['period'] = '2y'
        r = c.get(path, query_string=qs); j = r.get_json()
        res['%s|%s|%s' % (kind, sym, tf)] = dict(error=str(j)[:150]) if r.status_code != 200 else dict(split=j.get('split'), top=[pick(x) for x in j['results']])
json.dump(res, open(out, 'w'), indent=1)
print('done', code_dir)
