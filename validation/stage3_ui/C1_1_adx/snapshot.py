# -*- coding: utf-8 -*-
"""C1.1:用網站自己的取得路徑(app.fetch_data,同一個起算日)把實際 OHLC 存成快照,之後的比較/測試都離線重播,不再下載。"""
import json, os, sys, warnings
warnings.filterwarnings('ignore')
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import app as A
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
SYMS = ['BTC/USDT', 'SOL/USDT', '2330.TW', 'AAPL']
for sym in SYMS:
    for tf in ('1w', '1d', '4h', '1h'):
        if A._mtf_unsupported(sym, tf): continue
        yf_tf = {'1w': '1w', '1d': '1d', '4h': '4h', '1h': '1h'}[tf]
        rows = A.fetch_data(sym, A._mtf_start(sym, tf), interval=yf_tf)
        rows = [list(r) for r in rows]
        json.dump({'symbol': sym, 'tf': tf, 'rows': rows}, open(os.path.join(OUT, '%s_%s.json' % (sym.replace('/', '-'), tf)), 'w'))
        print(sym, tf, len(rows), flush=True)
