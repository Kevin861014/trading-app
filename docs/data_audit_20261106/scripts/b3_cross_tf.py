# -*- coding: utf-8 -*-
"""稽核 B3:交叉週期檢查。
(1) 官方 API:同一時段,把官方 1H 每 4 根(UTC 0/4/8/12/16/20 起算)依 OHLCV 規則人工聚合(Decimal 精確運算),與官方直接取得的 4H 比對。
(2) 本機快取:D3 long.pkl 的 1H 聚合後 vs 同一份快取的 4H(全部歷史)。
只有公開 GET;不改任何既有檔案。"""
import json, os, sys, time
from decimal import Decimal as Dm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SYMS = ['BTCUSDT', 'TRXUSDT', 'XRPUSDT', 'SOLUSDT']
WIN = [('2022-05-08', MS(2022, 5, 8), MS(2022, 5, 15)), ('2025-06-01', MS(2025, 6, 1), MS(2025, 6, 8)), ('2026-10-20', MS(2026, 10, 20), MS(2026, 10, 27))]
NOW = int(time.time() * 1000); H = 3600000; H4 = 4 * H
res = []; example = None


def agg(four):
    return {'o': four[0][1], 'h': max(four, key=lambda x: Dm(x[2]))[2], 'l': min(four, key=lambda x: Dm(x[3]))[3], 'c': four[-1][4], 'v': sum((Dm(x[5]) for x in four), Dm(0))}


for sym in SYMS:
    for lab, lo, hi in WIN:
        one = {int(x[0]): x for x in klines(sym, '1h', lo, hi, now=NOW)}; four = klines(sym, '4h', lo, hi, now=NOW)
        r = {'sym': sym, 'window': lab, 'api_4h_bars': len(four), 'api_1h_bars': len(one), 'compared': 0, 'mismatch': 0, 'boundary_not_utc_grid': 0, 'close_time_bad': 0, 'incomplete_4h': 0, 'diffs': []}
        for b in four:
            t = int(b[0])
            if t % H4 != 0: r['boundary_not_utc_grid'] += 1
            if int(b[6]) != t + H4 - 1: r['close_time_bad'] += 1
            parts = [one.get(t + i * H) for i in range(4)]
            if any(p is None for p in parts): r['incomplete_4h'] += 1; continue
            a = agg(parts); r['compared'] += 1
            bad = [k for k, v in (('o', Dm(b[1])), ('h', Dm(b[2])), ('l', Dm(b[3])), ('c', Dm(b[4])), ('v', Dm(b[5]))) if Dm(a[k]) != v]
            if bad: r['mismatch'] += 1; r['diffs'].append({'t': U(t), 'fields': bad, 'agg': {k: str(a[k]) for k in a}, 'api4h': b[1:6]})
            if example is None and sym == 'BTCUSDT' and lab == '2025-06-01' and t == MS(2025, 6, 2, 8):
                example = {'4h_open_utc': U(t), '1h_bars': [{'open_utc': U(int(p[0])), 'o': p[1], 'h': p[2], 'l': p[3], 'c': p[4], 'v': p[5]} for p in parts], 'manual_aggregate': {k: str(a[k]) for k in a}, 'official_4h': {'o': b[1], 'h': b[2], 'l': b[3], 'c': b[4], 'v': b[5], 'closeTime': int(b[6])}}
        res.append(r); print(sym, lab, {k: v for k, v in r.items() if k != 'diffs'}, flush=True)

# (2) 本機 D3:1H 聚合 vs 4H(整段歷史)
d3 = pickle.load(open(D3P, 'rb'))['candles']; loc = []
for sym in SYMS:
    u = to_unified(sym); r1 = {r[0]: r for r in d3[(u, '1h')]}; r4 = d3[(u, '4h')]; cmp = mis = inc = vol_rel_max = 0; first_inc = None
    for b in r4:
        t = b[0]; parts = [r1.get(t + i * H) for i in range(4)]
        if any(p is None for p in parts): inc += 1; continue
        cmp += 1
        o = parts[0][1]; h = max(p[2] for p in parts); l = min(p[3] for p in parts); c = parts[-1][4]; v = sum(p[5] for p in parts)
        ok = (o == b[1] and h == b[2] and l == b[3] and c == b[4])
        rel = abs(v - b[5]) / max(abs(b[5]), 1e-12); vol_rel_max = max(vol_rel_max, rel)
        if not ok or rel > 1e-9: mis += 1
    loc.append({'sym': sym, '4h_bars': len(r4), 'compared_full_4h': cmp, 'not_comparable_partial_first_bar': inc, 'mismatch': mis, 'max_volume_rel_diff': vol_rel_max})
    print('LOCAL', loc[-1], flush=True)
json.dump({'official': res, 'local_d3': loc, 'example': example, 'requests': len(REQLOG)}, open(os.path.join(OUT, 'b3_cross_tf.json'), 'w'), ensure_ascii=False, indent=1)
json.dump(REQLOG, open(os.path.join(OUT, 'b3_requests.json'), 'w'), ensure_ascii=False)
print('requests', len(REQLOG))
