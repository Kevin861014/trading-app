# -*- coding: utf-8 -*-
"""稽核 B1:固定日期樣本 + 資料分頁交界,逐欄比對『幣安官方 /fapi/v1/klines 原始 JSON』與本機快取(D2 data.pkl、D3 long.pkl)。
只有公開 GET。原始 API 回應存在 raw_api/ 供重現。不改任何既有檔案。"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SYMS = ['BTCUSDT', 'TRXUSDT', 'XRPUSDT', 'SOLUSDT']
WINDOWS = [('W1_2020-09-20', MS(2020, 9, 20), MS(2020, 9, 27)), ('W2_2022-05-08', MS(2022, 5, 8), MS(2022, 5, 15)), ('W3_2024-03-10', MS(2024, 3, 10), MS(2024, 3, 17)),
           ('W4_2025-06-01', MS(2025, 6, 1), MS(2025, 6, 8)), ('W5_2026-10-20', MS(2026, 10, 20), MS(2026, 10, 27)), ('W6_latest', MS(2026, 10, 31), None)]
NOW = int(time.time() * 1000)
LOC, RAWD = load_local()
rows_out = []


def run(label, sym, tf, lo, hi, kind):
    u = to_unified(sym); step = STEP[tf]
    api = klines(sym, tf, lo, hi, now=NOW)
    if not api: rows_out.append({'sample': label, 'sym': sym, 'tf': tf, 'note': 'API returned 0 rows'}); return
    json.dump(api, open(os.path.join(RAW_API, '%s_%s_%s.json' % (sym, tf, label)), 'w'), separators=(',', ':'))
    a_lo, a_hi = int(api[0][0]), int(api[-1][0])
    for src in ('D3', 'D2'):
        loc = LOC[src].get((u, tf))
        if not loc: continue
        l_first, l_last = min(loc), max(loc)
        if src == 'D2' and a_lo < l_first: continue                          # D2 只有 2025-03 之後(1H)/2024-11 之後(4H),樣本早於此就不比
        beyond = [x for x in api if int(x[0]) > l_last]; api_c = [x for x in api if int(x[0]) <= l_last]
        if not api_c: continue
        r = compare(api_c, loc, tf, int(api_c[0][0]), int(api_c[-1][0]))
        r.update({'sample': label, 'kind': kind, 'sym': sym, 'tf': tf, 'source': src, 'window_utc': '%s -> %s' % (U(a_lo), U(a_hi)), 'api_beyond_local_end': len(beyond),
                  'api_url': '%s/fapi/v1/klines?symbol=%s&interval=%s&startTime=%d%s&limit=1500' % (FAPI, sym, tf, lo, ('&endTime=%d' % hi) if hi else '')})
        rows_out.append(r)
        print('%-16s %-8s %-3s %-3s api=%4d matched=%4d fieldMis=%s rowMis=%d missLocal=%d extraLocal=%d closeTimeMis=%d beyond=%d' % (label, sym, tf, src, r['api_rows'], r['matched'], r['field_mismatch'], r['mismatch_rows'], r['missing_in_local'], r['extra_in_local'], r['close_time_mismatch'], len(beyond)), flush=True)


# 1) 固定日期樣本
for sym in SYMS:
    for tf in ('1h', '4h'):
        for lab, lo, hi in WINDOWS:
            run(lab, sym, tf, lo, hi, 'fixed_window')

# 2) 分頁交界:D3 用 limit=1500(fapi 直接),D2 用 limit=1000(ccxt)。取本機每個交界前後各 5 根,向官方 API 重新要同一段
for src, per in (('D3', 1500), ('D2', 1000)):
    for sym in SYMS:
        u = to_unified(sym)
        for tf in ('1h', '4h'):
            loc = LOC[src].get((u, tf))
            if not loc: continue
            ts = sorted(loc); n = len(ts)
            for k in range(1, (n - 1) // per + 1):
                i = k * per
                lo, hi = ts[i - 5], ts[min(i + 4, n - 1)]
                run('PAGE_%s_k%d_idx%d' % (src, k, i), sym, tf, lo, hi, 'page_boundary_' + src)

json.dump({'now_utc': U(NOW), 'results': rows_out, 'requests': len(REQLOG), 'req_log_head': REQLOG[:5]}, open(os.path.join(OUT, 'b1_samples.json'), 'w'), ensure_ascii=False, indent=1)
json.dump(REQLOG, open(os.path.join(OUT, 'b1_requests.json'), 'w'), ensure_ascii=False)
tot = lambda key: sum(r.get(key, 0) for r in rows_out if 'api_rows' in r)
print('\nSUMMARY samples=%d api_rows=%d matched=%d rowMismatch=%d missing_in_local=%d extra_in_local=%d closeTimeMis=%d requests=%d' % (len([r for r in rows_out if 'api_rows' in r]), tot('api_rows'), tot('matched'), tot('mismatch_rows'), tot('missing_in_local'), tot('extra_in_local'), tot('close_time_mismatch'), len(REQLOG)))
