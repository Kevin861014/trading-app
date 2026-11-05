# -*- coding: utf-8 -*-
"""把研究要用的真實 K 線存成離線快照:C1 回歸快照的 5 條 + 機器人組合 CHZ/USDT 4H(公開行情,免費,與 app.fetch_data 同路徑)。"""
import datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from warmup_common import *

C1 = r'C:/Users/User/AppData/Local/Temp/claude/be6f13411faa902a/44ad17db-b09f-4293-a234-571d9c4e1595/scratchpad/c1/snapshot.json'
src = json.load(open(C1, encoding='utf-8'))['rows']
pick = {'BTC/USDT|4h': 'BTC/USDT|2024-01-10|4h', 'SOL/USDT|4h': 'SOL/USDT|2024-01-10|4h', '2330.TW|1d': '2330.TW|2022-12-06|1d',
        'AAPL|1d': 'AAPL|2022-12-06|1d', 'NVDA|1d': 'NVDA|2022-12-06|1d'}
out = {k: src[v] for k, v in pick.items()}
start = (datetime.datetime.now() - datetime.timedelta(days=730 + 300)).strftime('%Y-%m-%d')      # 與 best_strategy 對 ccxt 4H 的取法相同
out['CHZ/USDT|4h'] = [list(r) for r in A.fetch_data('CHZ/USDT', start, interval='4h')]
# 機器人的凱利種子用 ~900 天歷史
out['CHZ/USDT|4h|900d'] = [list(r) for r in A.fetch_data('CHZ/USDT', (datetime.datetime.now() - datetime.timedelta(days=900)).strftime('%Y-%m-%d'), interval='4h')]
json.dump({'__fixed_now__': FIXED_NOW.isoformat(), 'rows': out}, open(SNAP, 'w'))
for k, v in out.items(): print(k, len(v), datetime.datetime.utcfromtimestamp(v[0][0] / 1000), datetime.datetime.utcfromtimestamp(v[-1][0] / 1000))
