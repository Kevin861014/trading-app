# -*- coding: utf-8 -*-
"""稽核 B5:針對 B3 在『本機 D3 1H 聚合 vs 本機 4H』找到的不一致,逐根列出差異,並向官方 API 取同一根 4H 與其 4 根 1H 重新核對,
判斷不一致是『本機快取壞掉』還是『官方資料本身就這樣』。只診斷這幾根,不延伸。只有公開 GET。"""
import json, os, sys, time
from decimal import Decimal as Dm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

H = 3600000; H4 = 4 * H; NOW = int(time.time() * 1000)
d3 = pickle.load(open(D3P, 'rb'))['candles']; d2 = pickle.load(open(D2P, 'rb'))['candles']
SYMS = ['BTCUSDT', 'TRXUSDT', 'XRPUSDT', 'SOLUSDT']; found = []
for sym in SYMS:
    u = to_unified(sym); r1 = {r[0]: r for r in d3[(u, '1h')]}
    for b in d3[(u, '4h')]:
        t = b[0]; parts = [r1.get(t + i * H) for i in range(4)]
        if any(p is None for p in parts): continue
        o = parts[0][1]; h = max(p[2] for p in parts); l = min(p[3] for p in parts); c = parts[-1][4]; v = sum(p[5] for p in parts)
        fields = [k for k, x, y in (('o', o, b[1]), ('h', h, b[2]), ('l', l, b[3]), ('c', c, b[4])) if x != y]
        if abs(v - b[5]) / max(abs(b[5]), 1e-12) > 1e-9: fields.append('v')
        if fields: found.append({'sym': sym, 't': t, 'fields': fields, 'local_4h': b[1:6], 'agg_local_1h': [o, h, l, c, v], 'local_1h': [p[1:6] for p in parts]})
print('local mismatches found:', len(found))
out = []
for f in found:
    sym, t = f['sym'], f['t']
    off4 = klines(sym, '4h', t, t + H4 - 1, now=NOW); off1 = klines(sym, '1h', t, t + H4 - 1, now=NOW)
    o4 = off4[0] if off4 else None; parts = off1
    rec = {'sym': sym, 'bar_open_utc': U(t), 'fields_differ_in_local': f['fields']}
    # 本機 4H vs 官方 4H;本機 1H(4 根) vs 官方 1H(4 根)
    rec['local_4h_equals_official_4h'] = bool(o4) and all(float(o4[i]) == f['local_4h'][i - 1] for i in range(1, 6))
    rec['local_1h_equals_official_1h'] = len(parts) == 4 and all(float(parts[j][i]) == f['local_1h'][j][i - 1] for j in range(4) for i in range(1, 6))
    if len(parts) == 4 and o4:
        aggv = sum(Dm(p[5]) for p in parts); aggo = parts[0][1]; aggh = max(parts, key=lambda x: Dm(x[2]))[2]; aggl = min(parts, key=lambda x: Dm(x[3]))[3]; aggc = parts[-1][4]
        rec['official_1h_aggregate_equals_official_4h'] = (Dm(aggo) == Dm(o4[1]) and Dm(aggh) == Dm(o4[2]) and Dm(aggl) == Dm(o4[3]) and Dm(aggc) == Dm(o4[4]) and aggv == Dm(o4[5]))
        rec['official_4h'] = o4[1:6]; rec['official_1h_volumes'] = [p[5] for p in parts]; rec['official_1h_agg_volume'] = str(aggv)
        rec['official_1h_trades'] = [int(p[8]) for p in parts]; rec['official_4h_trades'] = int(o4[8])
    out.append(rec); print(json.dumps(rec, ensure_ascii=False), flush=True)
json.dump({'n_local_mismatch': len(found), 'details': out, 'local_details': found}, open(os.path.join(OUT, 'b5_mismatch_diagnose.json'), 'w'), ensure_ascii=False, indent=1)
json.dump(REQLOG, open(os.path.join(OUT, 'b5_requests.json'), 'w'), ensure_ascii=False)
