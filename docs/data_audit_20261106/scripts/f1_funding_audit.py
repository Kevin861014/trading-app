# -*- coding: utf-8 -*-
"""資金費率稽核(只有公開 GET,不帶金鑰;不改任何既有檔案)。
F1 本機 D2/D3 快取的結構:筆數、排序/重複、結算間隔、缺口、時間戳落在 UTC 結算格線的偏移。
F2 深度抽樣(BTC、TRX、XRP、SOL):固定日期窗口 + 分頁交界(limit=1000),逐筆比對官方 /fapi/v1/fundingRate(fundingTime、fundingRate)與 D2/D3 本機快取。
F3 輕量抽樣(全部 24 個符號):2025-06 與最新窗口。
F4 D4 BinanceFeed.funding() 與官方原始回應逐筆比對。
F5 D2 與 D3 兩份獨立快取在重疊期間逐筆比對(只用本機)。"""
import collections, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
sys.path.insert(0, r'C:\Users\User\發大財\trading-app\paper_trading')
H = 3600000; NOW = int(time.time() * 1000)
d2 = pickle.load(open(D2P, 'rb'))['funding']; d3 = pickle.load(open(D3P, 'rb'))['funding']
out = {'now_utc': U(NOW)}


def frange(sid, lo, hi=None):
    rows = []; cur = lo
    while True:
        p = {'symbol': sid, 'startTime': cur, 'limit': 1000}
        if hi: p['endTime'] = hi
        r = get(FAPI, '/fapi/v1/fundingRate', p)
        if not r: break
        rows += r
        if len(r) < 1000: break
        cur = int(r[-1]['fundingTime']) + 1
    return rows


def cmp(api, local_by_t, lo, hi):
    res = {'api_rows': len(api), 'matched': 0, 'time_missing_in_local': 0, 'rate_mismatch': 0, 'extra_in_local': 0, 'examples': []}
    seen = set()
    for x in api:
        t = int(x['fundingTime']); seen.add(t); l = local_by_t.get(t)
        if l is None: res['time_missing_in_local'] += 1; continue
        if float(x['fundingRate']) != l: res['rate_mismatch'] += 1; len(res['examples']) < 3 and res['examples'].append((U(t), x['fundingRate'], l))
        else: res['matched'] += 1
    res['extra_in_local'] = sum(1 for t in local_by_t if lo <= t <= hi and t not in seen); return res


# ---- F1 本機結構 ----
f1 = {}
for name, d in (('D2', d2), ('D3', d3)):
    for s, rows in sorted(d.items()):
        if not rows: f1['%s|%s' % (name, s)] = {'n': 0}; continue
        ts = [r[0] for r in rows]; dif = collections.Counter(round((b - a) / H) for a, b in zip(ts, ts[1:]))
        off = collections.Counter(t % H for t in ts); gaps = [(U(a), round((b - a) / H)) for a, b in zip(ts, ts[1:]) if b - a > 8 * H + 60000]
        f1['%s|%s' % (name, s)] = {'n': len(rows), 'first': U(ts[0]), 'last': U(ts[-1]), 'dup': len(ts) - len(set(ts)), 'unsorted': sum(1 for a, b in zip(ts, ts[1:]) if b <= a), 'spacing_hours': dict(dif.most_common(4)), 'gaps_over_8h': len(gaps), 'gaps_example': gaps[:3],
                                  'max_offset_ms_after_hour': max(off), 'offset_ms_set': sorted(off)[:6], 'nan_or_inf': sum(1 for r in rows if r[1] != r[1] or abs(r[1]) == float('inf')), 'rate_min': min(r[1] for r in rows), 'rate_max': max(r[1] for r in rows)}
out['F1_local_structure'] = f1
print('F1 series:', len(f1), '| with duplicates/unsorted/NaN:', sum(1 for v in f1.values() if v.get('n') and (v['dup'] or v['unsorted'] or v['nan_or_inf'])), '| with gaps>8h:', [(k, v['gaps_over_8h'], v['gaps_example']) for k, v in f1.items() if v.get('gaps_over_8h')], flush=True)
print('   spacing_hours seen:', sorted({h for v in f1.values() if v.get('n') for h in v['spacing_hours']}), '| max ms after the hour:', max(v['max_offset_ms_after_hour'] for v in f1.values() if v.get('n')), flush=True)

# ---- F2 深度抽樣 ----
SY4 = ['BTCUSDT', 'TRXUSDT', 'XRPUSDT', 'SOLUSDT']
WIN = [('W2_2022-05-08', MS(2022, 5, 8), MS(2022, 5, 15)), ('W3_2024-03-10', MS(2024, 3, 10), MS(2024, 3, 17)), ('W4_2025-06-01', MS(2025, 6, 1), MS(2025, 6, 8)), ('W5_2026-10-20', MS(2026, 10, 20), MS(2026, 10, 27)), ('W6_latest', MS(2026, 10, 30), None)]
f2 = []; grid_off = []
def run(label, sid, lo, hi, kind):
    u = to_unified(sid); api = frange(sid, lo, hi)
    if not api: f2.append({'sample': label, 'sym': sid, 'note': 'API 0 rows'}); return
    json.dump(api, open(os.path.join(RAW_API, 'funding_%s_%s.json' % (sid, label)), 'w'), separators=(',', ':'))
    a_lo, a_hi = int(api[0]['fundingTime']), int(api[-1]['fundingTime'])
    for t in (int(x['fundingTime']) for x in api): grid_off.append(t % (8 * H))
    for src, d in (('D3', d3), ('D2', d2)):
        rows = d.get(u)
        if not rows: continue
        if src == 'D2' and a_lo < rows[0][0]: continue
        last = rows[-1][0]; api_c = [x for x in api if int(x['fundingTime']) <= last]
        if not api_c: continue
        r = cmp(api_c, dict(rows), int(api_c[0]['fundingTime']), int(api_c[-1]['fundingTime'])); r.update({'sample': label, 'kind': kind, 'sym': sid, 'source': src, 'window_utc': '%s -> %s' % (U(a_lo), U(a_hi)), 'beyond_local_end': len(api) - len(api_c)}); f2.append(r)
for sid in SY4:
    for lab, lo, hi in WIN: run(lab, sid, lo, hi, 'fixed_window')
    for src, d in (('D3', d3), ('D2', d2)):
        rows = d.get(to_unified(sid))
        if not rows: continue
        for k in range(1, (len(rows) - 1) // 1000 + 1):
            i = k * 1000; run('PAGE_%s_k%d_idx%d' % (src, k, i), sid, rows[i - 5][0], rows[min(i + 4, len(rows) - 1)][0], 'page_boundary_' + src)
bad = lambda r: r.get('time_missing_in_local', 0) + r.get('rate_mismatch', 0) + r.get('extra_in_local', 0)
rows2 = [r for r in f2 if 'api_rows' in r]
for k in ('fixed_window', 'page_boundary'):
    sel = [r for r in rows2 if r['kind'].startswith(k)]; print('F2 %-14s comparisons=%d api_rows=%d matched=%d inconsistent=%d' % (k, len(sel), sum(r['api_rows'] for r in sel), sum(r['matched'] for r in sel), sum(bad(r) for r in sel)), flush=True)
out['F2_deep'] = f2
off = collections.Counter(grid_off); out['F2_settlement_offset_ms_from_8h_grid'] = {'max': max(grid_off), 'distribution_top': off.most_common(5), 'n': len(grid_off)}
print('F2 settlement offset from 00/08/16 UTC grid (ms): max', max(grid_off), 'top', off.most_common(4), flush=True)

# ---- F3 輕量抽樣:全部符號 ----
f3 = []; syms = sorted(set(d3) | set(d2))
for u in syms:
    sid = u.replace('/', '')
    for lab, lo, hi in (('light_2025-06-01', MS(2025, 6, 1), MS(2025, 6, 8)), ('light_latest', MS(2026, 10, 30), None)):
        api = frange(sid, lo, hi)
        if not api: f3.append({'sym': sid, 'sample': lab, 'note': 'API 0 rows'}); continue
        for src, d in (('D3', d3), ('D2', d2)):
            rows = d.get(u)
            if not rows or (src == 'D2' and int(api[0]['fundingTime']) < rows[0][0]): continue
            last = rows[-1][0]; api_c = [x for x in api if int(x['fundingTime']) <= last]
            if api_c: r = cmp(api_c, dict(rows), int(api_c[0]['fundingTime']), int(api_c[-1]['fundingTime'])); r.update({'sym': sid, 'sample': lab, 'source': src}); f3.append(r)
r3 = [r for r in f3 if 'api_rows' in r]
print('F3 light: symbols=%d comparisons=%d api_rows=%d matched=%d inconsistent=%d no-data=%s' % (len(syms), len(r3), sum(r['api_rows'] for r in r3), sum(r['matched'] for r in r3), sum(bad(r) for r in r3), [r['sym'] for r in f3 if 'note' in r]), flush=True)
out['F3_light_all_symbols'] = f3

# ---- F4 D4 feed ----
from d4_feed import BinanceFeed
feed = BinanceFeed(); f4 = []
for sid in SY4:
    lo = MS(2026, 10, 1); fr = feed.funding(sid, lo); api = frange(sid, lo)
    same = [(int(x['fundingTime']), float(x['fundingRate'])) for x in api] == fr
    f4.append({'sym': sid, 'feed_rows': len(fr), 'api_rows': len(api), 'identical': same, 'last': U(fr[-1][0])})
    print('F4', f4[-1], flush=True)
out['F4_d4_feed'] = f4

# ---- F5 D2 vs D3 ----
f5 = {'compared': 0, 'equal': 0, 'diff': 0, 'only_d2': 0, 'only_d3_in_range': 0, 'symbols': 0}
for u, a in d2.items():
    b = d3.get(u)
    if not b: continue
    da, db = dict(a), dict(b); lo, hi = max(a[0][0], b[0][0]), min(a[-1][0], b[-1][0]); f5['symbols'] += 1
    for t, v in da.items():
        if lo <= t <= hi:
            f5['compared'] += 1
            if t not in db: f5['only_d2'] += 1
            elif db[t] == v: f5['equal'] += 1
            else: f5['diff'] += 1
    f5['only_d3_in_range'] += sum(1 for t in db if lo <= t <= hi and t not in da)
out['F5_d2_vs_d3'] = f5; print('F5', f5)
json.dump(out, open(os.path.join(OUT, 'f1_funding_audit.json'), 'w'), ensure_ascii=False, indent=1, default=str); json.dump(REQLOG, open(os.path.join(OUT, 'f1_requests.json'), 'w'), ensure_ascii=False); print('requests', len(REQLOG))
