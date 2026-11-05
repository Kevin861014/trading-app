# -*- coding: utf-8 -*-
"""usage: python rank_compare.py <code_dir> <out.json>   -- runs /api/best_strategy on cached identical data"""
import sys, os, json, warnings
warnings.filterwarnings('ignore')
code_dir, out = sys.argv[1], sys.argv[2]
sys.path.insert(0, code_dir)
SP = os.path.dirname(os.path.abspath(__file__))
import app as A
def cached(sym, tf):
    return json.load(open(os.path.join(SP, 'ba_cache', sym.replace('/', '_') + '_' + tf + '.json')))
A.fetch_data = lambda sym, start, interval='1d': cached(sym, interval)
c = A.app.test_client(); res = {}
for sym, tf in [('BTC/USDT', '4h'), ('SOL/USDT', '4h'), ('2330.TW', '1d'), ('AAPL', '1d'), ('NVDA', '1d')]:
    r = c.get('/api/best_strategy', query_string=dict(symbol=sym, period='2y', timeframe=tf, use_oos='1'))
    j = r.get_json()
    if r.status_code != 200: res[sym] = dict(error=str(j)[:200]); continue
    res[sym] = dict(tested=j['total_tested'], top=[dict(s=x['strat'], pf=x['pf'], total=x['total'], trades=x['trades'], mdd=x['mdd'], oos=x.get('oosPf')) for x in j['results']],
                    n_candidates_passing=len(j['results']))
json.dump(res, open(out, 'w'), indent=1)
print('done', code_dir)
