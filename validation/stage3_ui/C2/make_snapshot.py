# -*- coding: utf-8 -*-
"""C2:把研究要用的真實 K 線(與 /api/regime_study 同一個取得路徑與起算日)存成離線快照,測試與驗證都離線重播。"""
import datetime, json, os, sys, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
A.CCXT_AVAILABLE = True
now = datetime.datetime.now()
def st(days): return (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
jobs = [('BTC/USDT', '4h', 730 + 300), ('SOL/USDT', '4h', 730 + 300), ('BTC/USDT', '1d', 730 + 700), ('SOL/USDT', '1d', 730 + 700),
        ('2330.TW', '1d', 730 + 700), ('AAPL', '1d', 730 + 700), ('^TWII', '1d', 730 + 700), ('^GSPC', '1d', 730 + 700), ('^IXIC', '1d', 730 + 700)]
out = {}
for sym, tf, d in jobs:
    out['%s|%s' % (sym, tf)] = [list(r) for r in A.fetch_data(sym, st(d), interval=tf)]
    print(sym, tf, len(out['%s|%s' % (sym, tf)]), flush=True)
json.dump({'__now__': now.isoformat(), 'rows': out}, open(os.path.join(HERE, 'snapshot.json'), 'w'))
