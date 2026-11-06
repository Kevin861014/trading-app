# -*- coding: utf-8 -*-
"""把 out/*.json 的結果組成 REPORT.md(表格全部由結果檔產生,不手抄)。只讀 out/,只寫 REPORT.md。"""
import collections, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import OUT, BASE, D2P, D3P, U

J = lambda n: json.load(open(os.path.join(OUT, n), encoding='utf-8'))
b1 = J('b1_samples.json')['results']; b3 = J('b3_cross_tf.json'); b4 = J('b4_spot_contract.json'); b5 = J('b5_mismatch_diagnose.json'); b6 = J('b6_local_scan.json'); b7 = J('b7_d2_vs_d3.json'); c = J('c_code_path.json'); a1 = J('a1_local.json') if os.path.exists(os.path.join(OUT, 'a1_local.json')) else None
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
rows = [r for r in b1 if 'api_rows' in r]; bad = lambda r: r['mismatch_rows'] + r['missing_in_local'] + r['extra_in_local'] + r['close_time_mismatch']

# 表 A:固定日期樣本(全部列出)
fx = [r for r in rows if r['kind'] == 'fixed_window']
A = ['| 樣本 | 符號 | 週期 | 比對的本機快取 | 官方 API 時間範圍(UTC) | API 筆數 | 一致 | 不一致 |', '|---|---|---|---|---|---|---|---|']
for r in sorted(fx, key=lambda r: (r['sym'], r['tf'], r['sample'], r['source'])):
    A.append('| %s | %s | %s | %s | %s | %d | %d | %d |' % (r['sample'], r['sym'], r['tf'], {'D2': 'D2 data.pkl', 'D3': 'D3 long.pkl'}[r['source']], r['window_utc'], r['api_rows'], r['matched'], bad(r)))
# 表 B:分頁交界彙總
agg = collections.defaultdict(lambda: [0, 0, 0, 0])
for r in rows:
    if r['kind'].startswith('page_boundary'):
        a = agg[(r['sym'], r['tf'], r['source'])]; a[0] += 1; a[1] += r['api_rows']; a[2] += r['matched']; a[3] += bad(r)
B = ['| 符號 | 週期 | 本機快取(原抓取分頁大小) | 交界窗口數 | API 筆數 | 一致 | 不一致 |', '|---|---|---|---|---|---|---|']
for (s, tf, src), v in sorted(agg.items()): B.append('| %s | %s | %s | %d | %d | %d | %d |' % (s, tf, {'D3': 'D3 long.pkl(limit=1500)', 'D2': 'D2 data.pkl(ccxt limit=1000)'}[src], v[0], v[1], v[2], v[3]))
tot = lambda kind: [sum(1 for r in rows if r['kind'].startswith(kind)), sum(r['api_rows'] for r in rows if r['kind'].startswith(kind)), sum(r['matched'] for r in rows if r['kind'].startswith(kind)), sum(bad(r) for r in rows if r['kind'].startswith(kind))]
tfix, tpg = tot('fixed'), tot('page')
# 表 C:網站與 D4
S = ['| UI 選擇 | 標的 | 送進策略引擎的 K 棒數 | 實際間距(毫秒) | 期望間距 | 首根 → 末根(UTC) | 官方 API 逐欄比對 |', '|---|---|---|---|---|---|---|']
for r in c['site_analyze']:
    o = r['official_compare']; S.append('| %s | %s | %d | %s | %d | %s → %s | %d/%d 一致,不一致 %d |' % (r['ui_timeframe'].upper(), r['symbol'], r['bars_sent_to_engine'], r['spacing_ms'], r['expected_step_ms'], r['first'], r['last'], o['matched'], o['api_rows'], o['mismatch_rows'] + o['missing_in_local'] + o['extra_in_local'] + o['close_time_mismatch']))
D4 = ['| 符號 | 週期 | BinanceFeed 筆數 | 官方 API 筆數 | 一致 | 不一致 | 末根已收盤(UTC) |', '|---|---|---|---|---|---|---|']
for r in c['d4_feed']: D4.append('| %s | %s | %d | %d | %d | %d | %s |' % (r['sym'], r['tf'], r['feed_rows'], r['api_rows'], r['matched'], r['mismatch_rows'] + r['missing'] + r['extra'], r['last_closed']))
X = ['| 符號 | 時間窗 | 官方 4H 棒數 | 可聚合比對 | 不一致 | 不在 UTC 4 小時格線 | 收盤時間≠開盤+4h−1ms |', '|---|---|---|---|---|---|---|']
for r in b3['official']: X.append('| %s | %s 起 7 天 | %d | %d | %d | %d | %d |' % (r['sym'], r['window'], r['api_4h_bars'], r['compared'], r['mismatch'], r['boundary_not_utc_grid'], r['close_time_bad']))
ex = b3['example']
EX = '| 開盤(UTC) | Open | High | Low | Close | Volume |\n|---|---|---|---|---|---|\n' + '\n'.join('| %s | %s | %s | %s | %s | %s |' % (p['open_utc'], p['o'], p['h'], p['l'], p['c'], p['v']) for p in ex['1h_bars'])
m = ex['manual_aggregate']; o4 = ex['official_4h']
EX += '\n| **人工聚合(4 根 1H)** | **%s** | **%s** | **%s** | **%s** | **%s** |\n| **官方直接取得的 4H**(%s) | %s | %s | %s | %s | %s |' % (m['o'], m['h'], m['l'], m['c'], m['v'], ex['4h_open_utc'], o4['o'], o4['h'], o4['l'], o4['c'], o4['v'])
M = ['| 符號 | 4H 開盤(UTC) | 本機哪些欄位與 1H 聚合不同 | 本機 4H = 官方 4H? | 本機 1H(4 根) = 官方 1H? | 官方 1H 聚合 = 官方 4H? | 官方 4H 成交筆數 | 官方 4 根 1H 成交筆數 |', '|---|---|---|---|---|---|---|---|']
for r in b5['details']: M.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (r['sym'], r['bar_open_utc'], '/'.join(r['fields_differ_in_local']), '是' if r['local_4h_equals_official_4h'] else '否', '是' if r['local_1h_equals_official_1h'] else '否', '是' if r.get('official_1h_aggregate_equals_official_4h') else '**否**', r.get('official_4h_trades'), r.get('official_1h_trades')))
magp = b6['max_ohlc_rel_diff_by_time']; magv = b6['max_vol_rel_diff_by_time']
sym_at = collections.defaultdict(list)
for s, r in b6['per_symbol'].items():
    for t in r['times']: sym_at[t].append(s)
T = ['| 4H 開盤(UTC) | 受影響符號數 | OHLC 最大相對差異 | 成交量最大相對差異 |', '|---|---|---|---|']
for t in sorted(sym_at): T.append('| %s | %d | %.3f%% | %.1f%% |' % (t, len(sym_at[t]), magp.get(t, 0) * 100, magv.get(t, 0) * 100))
PS = ['| 符號 | 4H 棒數 | 不一致 4H 棒 | 其中 OHLC 也不同 |', '|---|---|---|---|']
for s, r in b6['per_symbol'].items(): PS.append('| %s | %d | %d | %d |' % (s, r['4h_bars'], r['inconsistent_4h_bars'], r['of_which_ohlc_differs']))
sp = b4['spot_vs_local']; spot_rows = sum(r['spot_rows'] for r in sp); spot_same = sum(r['local_rows_same_ohlc_as_spot'] for r in sp)
CT = ['| 符號 | contractType | quoteAsset | status | onboardDate(UTC) |', '|---|---|---|---|---|'] + ['| %s | %s | %s | %s | %s |' % (r['symbol'], r['contractType'], r['quoteAsset'], r['status'], r['onboardDate']) for r in b4['contract']]
live_hit = b6['live_4h_combos_touched']
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report_template.md'), encoding='utf-8').read()
rep = {'@@FIXED@@': '\n'.join(A), '@@BOUNDARY@@': '\n'.join(B), '@@SITE@@': '\n'.join(S), '@@D4FEED@@': '\n'.join(D4), '@@XTF@@': '\n'.join(X), '@@EXAMPLE@@': EX, '@@MISMATCH16@@': '\n'.join(M), '@@TIMEPOINTS@@': '\n'.join(T), '@@PERSYMBOL@@': '\n'.join(PS), '@@CONTRACT@@': '\n'.join(CT),
       '@@N_FIXED@@': str(tfix[0]), '@@R_FIXED@@': '{:,}'.format(tfix[1]), '@@N_PAGE@@': str(tpg[0]), '@@R_PAGE@@': '{:,}'.format(tpg[1]), '@@BAD_B1@@': str(tfix[3] + tpg[3]), '@@N_B1@@': str(tfix[0] + tpg[0]), '@@R_B1@@': '{:,}'.format(tfix[1] + tpg[1]),
       '@@SPOT_ROWS@@': str(spot_rows), '@@SPOT_SAME@@': str(spot_same), '@@D2D3_OVERLAP@@': '{:,}'.format(b7['total']['overlap']), '@@D2D3_DIFF@@': str(b7['total']['diff']),
       '@@TOT_INCONS@@': str(b6['total']), '@@TOT_4H@@': '{:,}'.format(b6['all_4h_bars']), '@@PCT@@': '%.3f' % (100.0 * b6['total'] / b6['all_4h_bars']), '@@N_LIVE_HIT@@': str(len(live_hit)),
       '@@SHA_D2@@': sha(D2P), '@@SHA_D3@@': sha(D3P), '@@SITE_BARS@@': '{:,}'.format(sum(r['bars_sent_to_engine'] for r in c['site_analyze'])), '@@D4_BARS@@': '{:,}'.format(sum(r['feed_rows'] for r in c['d4_feed'])),
       '@@EXAMPLE_CLOSE@@': str(ex['official_4h']['closeTime']), '@@XTF_N@@': str(sum(r['compared'] for r in b3['official'])), '@@XTF_BAD@@': str(sum(r['mismatch'] for r in b3['official']))}
for k, v in rep.items(): tpl = tpl.replace(k, v)
assert '@@' not in tpl, [x for x in tpl.split('@@')[1::2]][:3]
open(os.path.join(BASE, 'REPORT.md'), 'w', encoding='utf-8').write(tpl); print('REPORT.md written', len(tpl))
