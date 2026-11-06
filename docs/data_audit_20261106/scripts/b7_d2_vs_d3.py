# -*- coding: utf-8 -*-
"""稽核 B7(只讀本機、不連網):D2 data.pkl(經網站 fetch_data → ccxt)與 D3 long.pkl(直接 fapi klines)是兩次獨立、程式路徑不同的抓取。
比對兩者重疊期間所有符號、1H/4H 的逐根 OHLCV;若 D2 任何一段曾靜默退回 yfinance/現貨,兩者就會不同。另列 BTC 零成交量的 1H 棒。"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
LOC, RAWD = load_local(); rows = []; tot = {'overlap': 0, 'equal': 0, 'diff': 0, 'only_d2': 0, 'only_d3_in_range': 0}
for (s, tf), a in sorted(LOC['D2'].items()):
    b = LOC['D3'].get((s, tf))
    if not b: rows.append({'sym': s, 'tf': tf, 'note': 'not in D3 (D2-only symbol)', 'bars_d2': len(a)}); continue
    lo, hi = max(min(a), min(b)), min(max(a), max(b)); ov = [t for t in a if lo <= t <= hi]
    eq = sum(1 for t in ov if t in b and a[t][1:6] == b[t][1:6]); diff = [t for t in ov if t in b and a[t][1:6] != b[t][1:6]]; only2 = [t for t in ov if t not in b]; only3 = [t for t in b if lo <= t <= hi and t not in a]
    rows.append({'sym': s, 'tf': tf, 'overlap_bars': len(ov), 'equal': eq, 'diff': len(diff), 'only_in_d2': len(only2), 'only_in_d3_within_overlap': len(only3), 'range': '%s -> %s' % (U(lo), U(hi)), 'diff_examples': [U(t) for t in diff[:3]]})
    tot['overlap'] += len(ov); tot['equal'] += eq; tot['diff'] += len(diff); tot['only_d2'] += len(only2); tot['only_d3_in_range'] += len(only3)
for r in rows:
    if 'overlap_bars' in r and (r['diff'] or r['only_in_d2'] or r['only_in_d3_within_overlap']): print('DIFF', r)
print('symbols/tf compared:', sum(1 for r in rows if 'overlap_bars' in r), '| D2-only:', [r['sym'] + '/' + r['tf'] for r in rows if 'note' in r]); print('TOTAL', tot)
zv = [(s, tf, U(t)) for (s, tf), m in LOC['D3'].items() for t, r in m.items() if r[5] == 0]
print('zero-volume bars in D3:', zv)
json.dump({'rows': rows, 'total': tot, 'zero_volume_bars_d3': zv}, open(os.path.join(OUT, 'b7_d2_vs_d3.json'), 'w'), ensure_ascii=False, indent=1)
