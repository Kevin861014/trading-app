# -*- coding: utf-8 -*-
"""把 results_*.json 整理成 warmup_study.md(只做彙整,不重算)。"""
import collections, json, os
H = os.path.dirname(os.path.abspath(__file__))
L = lambda n: json.load(open(os.path.join(H, 'results_%s.json' % n), encoding='utf-8'))
cz, sd, st, rk, ch = L('causality'), L('startdate'), L('strategies'), L('ranking'), L('chz')
VS = ['B', 'C27', 'C100', 'C200']
md = ['# C1.1 第二部分:策略用 ADX(sim.dmi)暖機研究結果', '', 'A = 現行 sim.dmi;B = 教科書 Wilder 因果版;C(K) = 現行 + 資料最前 K 根的 DI/ADX 一律視為 None。全部離線重播真實 K 線快照(`snapshots.json`),只在記憶體暫時替換 sim.dmi,沒有修改 sim.py。', '']

md += ['## 1. 因果性(任一時間點只用當時及過去的 K 棒)', '', '方法:對前 N 根(N = 20、28、30、35、40、60、100、150、250、400)重算,和「全段算出來再取前 N 根」逐根比對;不同就是用了之後的資料。', '',
       '| 版本 | DI/ADX 函式的違反數(3 條序列 × 10 個長度) | 違反位置 | 六個策略訊號的違反數 |', '|---|---|---|---|']
for V in ['A', 'B', 'C27', 'C50', 'C100', 'C150', 'C200']:
    n = sum(sum(v['violations_by_prefix_len'].values()) for k, v in cz['dmi'].items() if k.endswith(' ' + V))
    pos = sorted({x for k, v in cz['dmi'].items() if k.endswith(' ' + V) for r in v['bad_index_range'].values() for x in r})
    sg = sum(n_ for k, n_ in cz['signals'].items() if k.endswith(' ' + V))
    md.append('| %s | %d | %s | %d |' % (V, n, ('第 %d~%d 根' % (pos[0], pos[-1])) if pos else '無', sg))

md += ['', '## 2. 歷史資料起始日期是否影響正式回測窗口內的訊號', '', '做法:把資料最前面砍掉 k 根(窗口內資料不動),比較窗口內(最近 730 天)的進出場訊號與完整回測交易。6 條序列 × 6 策略 = 36 組。', '',
       '| 版本 | 砍掉前 k 根 | 窗口內訊號有變的組數 | 窗口內進場日不同的組數 | PF 不同的組數 |', '|---|---|---|---|---|']
agg = collections.defaultdict(lambda: [0, 0, 0, 0])
for r in sd:
    a = agg[(r['variant'], r['drop_first_bars'])]; a[0] += 1; a[1] += r['window_signal_flips'] > 0; a[2] += not r['entries_identical']; a[3] += r['pf_base'] != r['pf_k']
for (V, k), a in sorted(agg.items()): md.append('| %s | %d | %d / %d | %d | %d |' % (V, k, a[1], a[0], a[2], a[3]))
only = sorted({(r['symbol'], r['strategy']) for r in sd if r['variant'] == 'A' and r['drop_first_bars'] == 400 and r['window_signal_flips']})
md += ['', '砍掉 400 根時 A 與 B **同樣**只有 %d 組有變(%s),這幾組都是 `ema50_200_adx`:是 EMA200 還沒收斂(日線資料只剩約 45 根窗口前暖機),**不是 ADX**。C100 在這個極端下多出變動,是因為窗口前只剩 45 根、卻要求遮蔽 100 根,把窗口內的前面幾根也遮掉了:**嚴格暖機長度 K 不能大於窗口之前實際可用的歷史**。' % (len(only), '、'.join('%s %s' % x for x in only)), '']

md += ['## 3. 六個使用 DMI 的策略各自受多少影響(正式窗口:最近 730 天;IS/OOS 切分與 app 完全相同)', '', '6 條真實序列(BTC/SOL/CHZ 4H、2330.TW/AAPL/NVDA 日線)× 該策略;「組」= 序列。比較對象是 A。', '',
       '| 策略 | 版本 | 窗口內訊號不同的組數 | 完整交易清單不同的組數 | PF 不同的組數 | IS PF 不同 | OOS 筆數或 PF 不同 | 最大訊號差(根) |', '|---|---|---|---|---|---|---|---|']
for key in ['diadx', 'ema50_200_adx', 'adx_di', 'dmi_cross', 'adx_di_trend', 'holy_grail']:
    rs = [r for r in st if r['strategy'] == key]
    for V in VS:
        md.append('| %s | %s | %d / %d | %d | %d | %d | %d | %d |' % (key, V, sum(r['sigdiff_vs_A_' + V] > 0 for r in rs), len(rs), sum(not r['entries_same_as_A_' + V] for r in rs),
                                                                        sum(1 for r in rs if r['A'] and r[V] and r['A']['pf'] != r[V]['pf']), sum(1 for r in rs if r['A'] and r[V] and r['A']['is_pf'] != r[V]['is_pf']),
                                                                        sum(1 for r in rs if r['A'] and r[V] and (r['A']['oos_trades'], r['A']['oos_pf']) != (r[V]['oos_trades'], r[V]['oos_pf'])), max(r['sigdiff_vs_A_' + V] for r in rs)))

md += ['', '## 4. 暖機長度是否改變策略排名與 OOS(走真正的 best_strategy 流程,176 個策略全跑)', '', '| 序列 | 版本 | 前 8 名(策略代碼順序)相同 | 排名分數/PF/筆數/回撤/勝率/報酬相同 | OOS 狀態/PF/筆數/報酬相同 | 前 8 名中的 ADX 策略 |', '|---|---|---|---|---|---|']
for k, per in rk.items():
    base = per['A']['top']
    for V in ['B', 'C27', 'C100', 'C200']:
        t = per[V]['top']
        md.append('| %s | %s | %s | %s | %s | %s |' % (k, V, '是' if [x[0] for x in base] == [x[0] for x in t] else '否', '是' if [x[:7] for x in base] == [x[:7] for x in t] else '否', '是' if [x[7:] for x in base] == [x[7:] for x in t] else '否',
                                                       '、'.join(x[0] for x in base if x[0] in ('diadx', 'ema50_200_adx', 'adx_di', 'dmi_cross', 'adx_di_trend', 'holy_grail')) or '無'))

c = ch['counts_vs_A']
md += ['', '## 5. 機器人 CHZ/USDT 4H `ema50_200_adx`', '', '機器人每輪用最近 400 根已收盤 4H K 棒(`closed_ohlcv(limit=400)`)呼叫 `build`,看最後一根的進場/出場訊號;機器人與本 app 的 `sim.dmi`、`sig_ema50_200_adx` 原始碼逐字相同(測試確認)。',
       '用 CHZ 4H 全部歷史(%d 個滾動 400 根窗口,每一根當最後一根)比較:' % ch['windows_400'], '', '| 版本(對 A) | 最後一根訊號不同 | 最近 10 根訊號不同 | 窗口末端持倉狀態不同 | 最後一根 ADX 最大差 |', '|---|---|---|---|---|']
for V in ['B', 'C100', 'C200']: md.append('| %s | %d | %d | %d | %.1e |' % (V, c[V]['last_bar_signal_diff'], c[V]['last10_signal_diff'], c[V]['final_pos_diff'], c[V]['adx_last_maxdiff']))
cur = ch['current_window']
md += ['', '目前這一輪(最新的 400 根窗口):' + '; '.join('%s: ADX=%.3f、進場=%s、出場=%s、持倉=%s' % (V, v['adx_last'], v['el_last'], v['xl_last'], v['pos_state']) for V, v in cur.items()) + '。',
       '', '凱利種子(機器人首次用 ~900 天歷史,%d 根)的訊號:A 的第一筆進場在第 %s 根,B 在第 %s 根(只差資料最前面 %s);A/B 的交易數 %d / %d;C100 / C200 因為遮蔽前 100/200 根,交易數 %d / %d(假設性,機器人並沒有這個遮蔽)。' % (
           ch['seed_bars'], ch['seed_900d']['A']['el_idx'][0], ch['seed_900d']['B']['el_idx'][0], '、'.join(map(str, ch['seed_signal_diff_indexes_A_vs_B'])), ch['seed_900d']['A']['trades'], ch['seed_900d']['B']['trades'], ch['seed_900d']['C100']['trades'], ch['seed_900d']['C200']['trades']), '']
open(os.path.join(H, 'warmup_study.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
print('\n'.join(md))
