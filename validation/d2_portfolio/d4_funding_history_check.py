# -*- coding: utf-8 -*-
"""把 D4 的資金費率完整性檢查(paper_trading/d4_funding.py)套在本機真實歷史上(D3 long.pkl、D2 data.pkl):只讀、不連網、不寫檔。
目的:驗證『結算間隔 1/2/4/8 小時且落在格線上』這個規則沒有誤傷真實資料,並列出它會在哪裡停止。"""
import os, pickle, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, os.path.join(ROOT, 'paper_trading'))
import d4_funding as F
tot = collections.Counter(); flagged = []
for name, p in (('D3 long.pkl', os.path.join(ROOT, 'validation', 'd3_walkforward', 'raw', 'long.pkl')), ('D2 data.pkl', os.path.join(HERE, 'raw', 'data.pkl'))):
    d = pickle.load(open(p, 'rb'))['funding']
    for s, rows in sorted(d.items()):
        ts = sorted(t for t, _ in rows)
        iss = F.check(rows, ts[0], ts[-1] - 1)          # 處理範圍 = 整段歷史(T1 取最後一筆之前,避免『尚未結算』的覆蓋判斷)
        tot['series'] += 1; tot['pairs'] += len(ts) - 1; tot['issues'] += len(iss)
        for i in iss: flagged.append((name, s, i['kind'], i['from_utc'], i['to_utc']))
print(dict(tot))
for f in flagged: print(f)
