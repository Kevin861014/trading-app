# -*- coding: utf-8 -*-
"""D3 異常 4H 棒敏感度測試 步驟 1:列出 D3 快取裡『1H 聚合 ≠ 4H』的 4H 棒,逐根向官方 /fapi/v1/klines(公開 GET)重新核對該 4H 棒與其 4 根 1H。
判定(每根):
  VERIFIED   本機 4H = 官方 4H 且 本機 4 根 1H = 官方 4 根 1H(可以拿官方 1H 聚合出替代棒)
  UNVERIFIED 任何一項對不上或官方查無資料(不替換、列為未驗證)
不修改 long.pkl(只讀)。輸出 results/s1_bars.json。"""
import json, os, sys, time
from decimal import Decimal as Dm
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), 'docs', 'data_audit_20261106', 'scripts'))
from common import get, FAPI, STEP, U, D3P
import pickle
RES = os.path.join(HERE, 'results'); os.makedirs(RES, exist_ok=True)
H = 3600000; H4 = 4 * H; NOW = int(time.time() * 1000)
d3 = pickle.load(open(D3P, 'rb'))['candles']
found = []
for s in sorted({k[0] for k in d3}):
    if (s, '1h') not in d3 or (s, '4h') not in d3: continue
    r1 = {r[0]: r for r in d3[(s, '1h')]}
    for b in d3[(s, '4h')]:
        t = b[0]; parts = [r1.get(t + i * H) for i in range(4)]
        if any(p is None for p in parts): continue
        o = parts[0][1]; h = max(p[2] for p in parts); l = min(p[3] for p in parts); c = parts[-1][4]; v = sum(p[5] for p in parts)
        f = [k for k, x, y in (('o', o, b[1]), ('h', h, b[2]), ('l', l, b[3]), ('c', c, b[4])) if x != y]
        if abs(v - b[5]) / max(abs(b[5]), 1e-12) > 1e-9: f.append('v')
        if f: found.append((s, t, f, parts))
print('abnormal 4H bars in local D3 cache:', len(found), flush=True)
out = []
for s, t, f, parts in found:
    sid = s.replace('/', '')
    r4 = get(FAPI, '/fapi/v1/klines', {'symbol': sid, 'interval': '4h', 'startTime': t, 'limit': 1}); r1 = get(FAPI, '/fapi/v1/klines', {'symbol': sid, 'interval': '1h', 'startTime': t, 'limit': 4})
    b4 = [x for x in d3[(s, '4h')] if x[0] == t][0]
    ok4 = bool(r4) and int(r4[0][0]) == t and all(float(r4[0][i]) == b4[i] for i in range(1, 6))
    ok1 = len(r1) == 4 and all(int(r1[j][0]) == t + j * H for j in range(4)) and all(float(r1[j][i]) == parts[j][i] for j in range(4) for i in range(1, 6))
    agg_ne = None
    if len(r1) == 4 and r4:
        agg = (r1[0][1], max(r1, key=lambda x: Dm(x[2]))[2], min(r1, key=lambda x: Dm(x[3]))[3], r1[3][4], sum((Dm(x[5]) for x in r1), Dm(0)))
        agg_ne = not (Dm(agg[0]) == Dm(r4[0][1]) and Dm(agg[1]) == Dm(r4[0][2]) and Dm(agg[2]) == Dm(r4[0][3]) and Dm(agg[3]) == Dm(r4[0][4]) and agg[4] == Dm(r4[0][5]))
    status = 'VERIFIED' if (ok4 and ok1) else 'UNVERIFIED'
    out.append({'sym': s, 't': t, 'utc': U(t), 'fields': f, 'status': status, 'local4h_eq_official': ok4, 'local1h_eq_official': ok1, 'official_agg_differs_from_official_4h': agg_ne})
print('VERIFIED', sum(1 for x in out if x['status'] == 'VERIFIED'), 'UNVERIFIED', sum(1 for x in out if x['status'] != 'VERIFIED'), '| official 1H-agg differs from official 4H:', sum(1 for x in out if x['official_agg_differs_from_official_4h']))
json.dump({'n': len(out), 'bars': out}, open(os.path.join(RES, 's1_bars.json'), 'w'), ensure_ascii=False, indent=1)
