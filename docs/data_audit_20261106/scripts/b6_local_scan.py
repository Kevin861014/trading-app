# -*- coding: utf-8 -*-
"""稽核 B6(只讀本機、不連網):D3 long.pkl 所有符號,找『本機 1H 聚合 ≠ 本機 4H』的 4H 棒,列出時間,並對照現行 23 組與 D2/D3/D4 的資料範圍,估計可能受影響的範圍。
B5 已證明:4 檔抽查中這些棒的本機 1H、4H 都與官方 API 完全相同,不一致來自官方資料本身。其他符號沒有逐根對官方查證(只由本機資料推論)。"""
import collections, glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

H = 3600000; H4 = 4 * H
d3 = pickle.load(open(D3P, 'rb'))['candles']; syms = sorted({k[0] for k in d3})
res = {}; bytime = collections.defaultdict(list)
for s in syms:
    if (s, '1h') not in d3 or (s, '4h') not in d3: continue
    r1 = {r[0]: r for r in d3[(s, '1h')]}; bad = []; kinds = collections.Counter()
    for b in d3[(s, '4h')]:
        t = b[0]; parts = [r1.get(t + i * H) for i in range(4)]
        if any(p is None for p in parts): continue
        o = parts[0][1]; h = max(p[2] for p in parts); l = min(p[3] for p in parts); c = parts[-1][4]; v = sum(p[5] for p in parts)
        f = [k for k, x, y in (('o', o, b[1]), ('h', h, b[2]), ('l', l, b[3]), ('c', c, b[4])) if x != y]
        if abs(v - b[5]) / max(abs(b[5]), 1e-12) > 1e-9: f.append('v')
        if f: bad.append((t, f)); bytime[t].append(s); kinds[tuple(f)] += 1
    ohlc_bad = [x for x in bad if set(x[1]) - {'v'}]
    res[s] = {'4h_bars': len(d3[(s, '4h')]), 'inconsistent_4h_bars': len(bad), 'of_which_ohlc_differs': len(ohlc_bad), 'times': [U(t) for t, _ in bad]}
print('%-14s %8s %6s %6s  times' % ('symbol', '4h_bars', 'incons', 'ohlc'))
for s, r in res.items(): print('%-14s %8d %6d %6d  %s' % (s, r['4h_bars'], r['inconsistent_4h_bars'], r['of_which_ohlc_differs'], ', '.join(r['times'][:12])))
tot = sum(r['inconsistent_4h_bars'] for r in res.values()); allbars = sum(r['4h_bars'] for r in res.values())
print('\nTOTAL inconsistent 4h bars %d of %d (%.4f%%)' % (tot, allbars, 100.0 * tot / allbars))
print('\nTimestamps shared by >=2 symbols (platform-wide, not one symbol):')
for t, ss in sorted(bytime.items()):
    if len(ss) >= 2: print('  ', U(t), len(ss), 'symbols')
bk = sorted(glob.glob(r'C:\Users\User\發大財\研究備份_D2\2*'))[-1]
combos = json.load(open(os.path.join(bk, 'config.portfolio.json.REDACTED.json'), encoding='utf-8'))['combos']
hit = []
for c in combos:
    if c['timeframe'] == '4h':
        r = res.get(c['symbol'])
        if r and r['inconsistent_4h_bars']: hit.append((c['symbol'], c['strategy'], r['inconsistent_4h_bars'], r['times']))
print('\n現行 23 組中,4H 組合且所用符號在歷史上出現不一致 4H 棒的:')
for h in hit: print('  ', h[0], h[1], h[2], h[3])
d2first = {'1h': U(min(r[0] for r in pickle.load(open(D2P, 'rb'))['candles'][('SOL/USDT', '1h')])), '4h': U(min(r[0] for r in pickle.load(open(D2P, 'rb'))['candles'][('SOL/USDT', '4h')]))}
latest = max((t for t, _ in [(0, 0)]), default=0)
alltimes = sorted(bytime); print('\nlatest inconsistent 4h bar in any symbol:', U(alltimes[-1]), '| D2 data starts (1h/4h):', d2first)
# 差異大小:每個時間點,各符號 OHLC 與『1H 聚合』相差的最大相對幅度(不含成交量)
mag = collections.defaultdict(float); magv = collections.defaultdict(float)
for s in syms:
    if (s, '1h') not in d3 or (s, '4h') not in d3: continue
    r1 = {r[0]: r for r in d3[(s, '1h')]}
    for b in d3[(s, '4h')]:
        t = b[0]; parts = [r1.get(t + i * H) for i in range(4)]
        if any(p is None for p in parts) or t not in bytime or s not in bytime[t]: continue
        agg = [parts[0][1], max(p[2] for p in parts), min(p[3] for p in parts), parts[-1][4]]
        mag[t] = max(mag[t], max(abs(a - x) / x for a, x in zip(agg, b[1:5]))); magv[t] = max(magv[t], abs(sum(p[5] for p in parts) - b[5]) / max(b[5], 1e-12))
print('\n每個時間點:OHLC 最大相對差異 / 成交量最大相對差異(各符號中最大者)')
for t in sorted(mag): print('  %s  price %.3f%%  volume %.1f%%' % (U(t), mag[t] * 100, magv[t] * 100))
json.dump({'per_symbol': res, 'max_ohlc_rel_diff_by_time': {U(t): mag[t] for t in mag}, 'max_vol_rel_diff_by_time': {U(t): magv[t] for t in magv}, 'total': tot, 'all_4h_bars': allbars, 'platform_wide_times': [U(t) for t, ss in sorted(bytime.items()) if len(ss) >= 2], 'live_4h_combos_touched': hit}, open(os.path.join(OUT, 'b6_local_scan.json'), 'w'), ensure_ascii=False, indent=1)
