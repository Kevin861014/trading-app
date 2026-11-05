# -*- coding: utf-8 -*-
"""D1 步驟 5:把 analysis.json / compare.json / stats.json 組成報告表格(所有數字直接取自分析輸出,不手填)。輸出 results/*.json 與 results/tables.md。"""
import json, os, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); OUT = os.path.join(HERE, 'results'); os.makedirs(OUT, exist_ok=True)
R = json.load(open(os.path.join(RAW, 'analysis.json'))); C = json.load(open(os.path.join(RAW, 'compare.json'))); ST = json.load(open(os.path.join(RAW, 'stats.json')))
for f in ('analysis.json', 'compare.json', 'stats.json'): shutil.copy(os.path.join(RAW, f), os.path.join(OUT, f))
f2 = lambda v, d=2: '—' if v is None else ('%+.*f' % (d, v))
nm = lambda x: x.replace('/USDT', '').replace('|', ' · ')
g2 = lambda v, d=2: '—' if v is None else ('%.*f' % (d, v))
L = R['btc_regime_labels']; md = []


def tier(n): return '樣本不足' if n < 20 else ('初步觀察' if n < 50 else '可進一步評估')


# 月績效
md += ['## T1 每月實際績效（含未實現，逐小時估算；USDT）', '', '| 月份 | 報酬率% | 損益 | 已實現（毛） | 手續費 | 資金費率 | 出場筆數 | 筆數淨損益 |', '|---|---|---|---|---|---|---|---|']
for m in R['monthly']: md.append('| %s | %s | %s | %s | %s | %s | %d | %s |' % (m['month'], f2(m['ret_pct']), f2(m['pnl_usd']), f2(m['realized']), f2(m['fees']), f2(m['funding']), m['trips_closed'], f2(m['net_closed'])))
# 23 組
md += ['', '## T2 目前 23 組（歸屬可靠者；損益 = 已實現 − 手續費 + 資金費率，USDT）', '', '| 組合 | 權重(配置%) | 筆數 | 分級 | 淨損益 | 毛損益 | 手續費 | 勝率% | 淨 PF | 平均/筆 | 未實現 | 同幣無法歸屬的筆數／淨損益 |', '|---|---|---|---|---|---|---|---|---|---|---|---|']
tot = {'n': 0, 'net': 0.0}
for c in sorted(R['combos'], key=lambda c: -c['net']):
    u = c['unknown_trips']; unk = ('%d／%s' % (u['n'], f2(u['net'], 2))) if u['n'] else '—'
    md.append('| %s | %s(%s%%) | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (nm(c['combo']), c['weight'], c['alloc_pct'], c['n'], tier(c['n']), f2(c['net']), f2(c['gross']), g2(c['fees'], 3), '—' if c['win'] is None else c['win'], '—' if c['pf'] is None else c['pf'], f2(c['avg'], 3), f2(c['open_unrealized']), unk))
    tot['n'] += c['n']; tot['net'] += c['net']
unk_n = sum(c['unknown_trips']['n'] for c in R['combos']); unk_net = sum(c['unknown_trips']['net'] for c in R['combos']); old_n = sum(c['old_strategy_trips']['n'] for c in R['combos']); old_net = sum(c['old_strategy_trips']['net'] for c in R['combos'])
ret_n = sum(v['n'] for v in R['retired_combos'].values()); ret_net = sum(v['net'] for v in R['retired_combos'].values())
md += ['', '| 合計 | | %d | | %s | | | | | | | |' % (tot['n'], f2(tot['net'])), '', '| 其他來源 | 筆數 | 淨損益 |', '|---|---|---|',
       '| 同幣「舊策略」且日誌可確認（SOL ema_8_21、PAXG trix_signal、PYTH week_hl、AAVE ppo_cross） | %d | %s |' % (old_n, f2(old_net)), '| 無法可靠歸屬（日誌之前曾換策略：AAVE、BNB、PAXG、PYTH、SOL、XRP） | %d | %s |' % (unk_n, f2(unk_net)),
       '| 已從設定移除的組合（ARB） | %d | %s |' % (ret_n, f2(ret_net)), '| **全部已平倉** | %d | %s |' % (R['overall_closed']['n'], f2(R['overall_closed']['net']))]
# 貢獻
pos = sorted([c for c in R['combos'] if c['net'] > 0], key=lambda c: -c['net']); neg = sorted([c for c in R['combos'] if c['net'] < 0], key=lambda c: c['net'])
gp = sum(c['net'] for c in pos); gl = sum(c['net'] for c in neg)
md += ['', '## T3 對整體的貢獻（只含歸屬可靠的組合；比例 = 該組合淨損益 / 同方向合計）', '', '| 賺錢的組合 | 淨損益 | 占賺錢組合合計 | | 虧錢的組合 | 淨損益 | 占虧錢組合合計 |', '|---|---|---|---|---|---|---|']
for i in range(max(len(pos), len(neg))):
    a = pos[i] if i < len(pos) else None; b = neg[i] if i < len(neg) else None
    md.append('| %s | %s | %s | | %s | %s | %s |' % (nm(a['combo']) if a else '', f2(a['net']) if a else '', ('%.0f%%' % (a['net'] / gp * 100)) if a else '', nm(b['combo']) if b else '', f2(b['net']) if b else '', ('%.0f%%' % (b['net'] / gl * 100)) if b else ''))
# 環境
md += ['', '## T4 BTC 環境（進場決策當下已收盤的 BTC 4H K 棒，C2 規則）× 實盤交易', '', '| BTC 環境 | 期間內佔比 | 筆數 | 分級 | 淨損益 | 勝率% | 淨 PF | 平均淨報酬/筆% | 95% 信賴區間(bootstrap) |', '|---|---|---|---|---|---|---|---|---|']
for k in ('up', 'down', 'range', 'transition'):
    v = R['by_btc_regime'].get(k)
    if not v: continue
    ci = ST['by_regime_net_pct'].get(k, {}).get('ci95')
    md.append('| %s | %s%% | %d | %s | %s | %s | %s | %s | %s |' % (L[k], R['btc_regime_share_of_time'][k]['pct'], v['n'], tier(v['n']), f2(v['net']), v['win'], '—' if v['pf'] is None else v['pf'], f2(v['avg_pct'], 3), ('[%s, %s]' % (f2(ci[0], 2), f2(ci[1], 2))) if ci else '—'))
o = ST['overall_net_pct']; md.append('| 全部 | | %d | | %s | %s | %s | %s | [%s, %s] |' % (o['n'], f2(R['overall_closed']['net']), R['overall_closed']['win'], R['overall_closed']['pf'], f2(o['mean'], 3), f2(o['ci95'][0]), f2(o['ci95'][1])))
md += ['', '## T5 BTC 24 小時急跌（自滾動高點回落 ≥ 4%）當時的持倉與權益', '', '| BTC 高點 → 低點（UTC） | BTC 跌幅 | 高點時持倉數 | 持倉名目 | 槓桿(名目/權益) | 期間權益變動 | 日誌可辨識的停損出場 |', '|---|---|---|---|---|---|---|']
for d in R['btc_drops']: md.append('| %s → %s | %s%% | %d | %s | %s | %s USDT（%s%%） | %d |' % (d['peak'], d['trough'], d['btc_drop_pct'], d['open_positions_at_peak'], d['notional_at_peak'], d['leverage_at_peak'], d['equity_change_usd'], d['equity_change_pct'], d['stops_hit']))
md += ['', '## T6 同日同時虧損（以出場日 UTC 加總）', '', '| 日期 | 淨損益 | 出場筆數 | 虧損筆數 | 虧損的幣 |', '|---|---|---|---|---|']
for d in R['worst_days']: md.append('| %s | %s | %d | %d | %s |' % (d['day'], f2(d['net']), d['exits'], d['losers'], '、'.join(d['symbols'])))
md += ['', '## T7 集中度', '', '| 項目 | 數值 |', '|---|---|']
cc = R['concentration']
for k, v in (('全部已平倉淨損益', cc['total_net']), ('賺錢筆數 / 虧錢筆數', '%d / %d' % (cc['n_win'], cc['n_loss'])), ('毛獲利 / 毛虧損', '%s / %s' % (cc['gross_profit'], cc['gross_loss'])), ('最大 1 筆', cc['top1']), ('最大 3 筆合計', cc['top3']), ('最大 5 筆合計', cc['top5']),
             ('扣掉最大 3 筆後的淨損益', cc['net_without_top3']), ('扣掉最大 5 筆後的淨損益', cc['net_without_top5']), ('最大 5 筆占毛獲利', '%s%%' % cc['top5_share_of_gross_profit_pct']), ('最差 5 筆合計', cc['worst5'])): md.append('| %s | %s |' % (k, v))
md += ['', '最大的幾筆：' + '；'.join('%s %s（%s%%，%s，持倉 %sh，BTC %s）' % (t['symbol'].replace('/USDT', ''), t['net'], t['ret_pct'], t['entry'], t['hold_h'], L.get(t['btc_regime'], '?')) for t in ST['top_trades'][:4])]
md += ['', '## T8 同時持倉、重疊與相關', '', '| 項目 | 數值 |', '|---|---|']
ex = R['exposure']
for k, v in (('最多同時持倉組數', '%d（%s UTC）' % (ex['max_concurrent'], ex['max_conc_time'])), ('平均同時持倉組數', ex['avg_concurrent']), ('空手（無任何持倉）的時間比例', '%s%%' % ex['share_hours_flat']), ('≥ 5 組同時持倉的時間比例', '%s%%' % ex['share_hours_ge5']), ('≥ 10 組', '%s%%' % ex['share_hours_ge10']),
             ('名目槓桿（持倉名目／權益）平均 / 95 百分位 / 最大', '%sx / %sx / %sx' % (ex['avg_leverage_x'], ex['p95_leverage_x'], ex['max_leverage_x'])), ('方向', '全部做多（機器人 long-only；成交紀錄沒有賣空）'),
             ('兩兩持倉時間重疊率（平均）', R['overlap_mean']), ('重疊最高的組', '；'.join('%s×%s %s' % (a.replace('/USDT', ''), b.replace('/USDT', ''), r) for a, b, r, _ in R['overlap_top'][:4])), ('日報酬兩兩相關（23 幣平均）', R['price_corr']['mean_pairwise']), ('相關 ≥ 0.7 的配對比例', '%s%%' % R['price_corr']['share_pairs_ge_0.7'])): md.append('| %s | %s |' % (k, v))
md += ['', '同一個 4H 棒收盤同時進場 ≥ 3 組的紀錄：' + '；'.join('%s UTC %d 組（%s）' % (a, n, '、'.join(x.replace('/USDT', '') for x in s)) for a, n, s in R['entry_clusters'][:4])]
# 成本與執行
co = R['costs']; exq = R['execution']; bt = ST['by_tf']
md += ['', '## T9 成本與執行', '', '| 項目 | 數值 |', '|---|---|', '| 已平倉交易：毛損益 / 手續費 / 資金費率 | %s / %s / %s USDT |' % (co['gross_realized'], co['commission_total'], co['funding_total']), '| 手續費占毛損益 | %s%% |' % co['fees_vs_gross_pct'],
       '| 平均單邊手續費率 / 平均來回成本（占進場名目） | %s%% / %s%%（只含手續費） |' % (co['avg_commission_rate_per_side_pct'], co['avg_roundtrip_cost_pct_of_notional']), '| 平均單筆進場名目 / 每月來回筆數 | %s USDT / %s 筆 |' % (co['avg_notional'], co['trips_per_month']),
       '| 成交方式 | 100%% 吃單（taker）：%s%% |' % exq['taker_share_pct'], '| 進場成交價 vs 日誌訊號價（n=%d） | 平均 %s%%、中位數 %s%%、90 百分位 %s%%（正 = 較貴） |' % (exq['n_slip'], exq['slip_mean_pct'], exq['slip_median_pct'], exq['slip_p90_pct']),
       '| 進場延遲（K 棒收盤後到成交，n=%d） | 中位數 %s 秒、90 百分位 %s 秒 |' % (exq['delay_n'], exq['delay_median_s'], exq['delay_p90_s'])]
md += ['', '| 週期（歸屬可靠者） | 筆數 | 毛損益 | 手續費 | 淨損益 | 勝率% | 持倉中位數(h) |', '|---|---|---|---|---|---|---|']
for k, v in bt.items(): md.append('| %s | %d | %s | %s | %s | %s | %s |' % (k, v['n'], f2(v['gross']), g2(v['fees']), f2(v['net']), v['win'], v['median_hold_h']))
md += ['', '| 手續費最高的幣 | 筆數 | 毛損益 | 手續費 |', '|---|---|---|---|']
for k, v in ST['fee_vs_gross'].items(): md.append('| %s | %d | %s | %s |' % (k.replace('/USDT', ''), v['n'], f2(v['gross']), g2(v['fees'])))
# 與網站回測
cp = C['total']
md += ['', '## T10 實盤 vs 網站回測（逐筆配對；兩者口徑不同，見說明）', '', '| 項目 | 數值 |', '|---|---|', '| 實盤已平倉（歸屬可靠）/ 同窗口網站回測筆數 / 以進場時間配對成功（±1 根） | %d / %d / %d |' % (cp['live_n'], cp['bt_n'], cp['matched']),
       '| 平均每筆淨報酬（實盤 / 網站回測；同窗口） | %s%% / %s%% |' % (f2(cp['live_mean_pct'], 3), f2(cp['bt_mean_pct'], 3)), '| 配對交易：進場價 實盤 vs 回測下一根開盤（加權平均） | %s%%（正 = 實盤較貴） |' % f2(cp['entry_px_diff_pct_wmean'], 3),
       '| 配對交易：出場價 實盤 vs 回測（加權平均） | %s%% |' % f2(cp['exit_px_diff_pct_wmean'], 3), '| 配對交易：每筆淨報酬差（實盤 − 回測） | %s%% |' % f2(cp['pair_ret_diff_pct_wmean'], 3),
       '| 網站回測最近 540 天（23 組，2228 筆）：勝率 / 每筆淨報酬 / PF | %s%% / %s%% / %s |' % (cp['bt540_win'], f2(cp['bt540_mean_pct'], 3), cp['bt540_pf'])]
md += ['', '| 組合 | 實盤筆數 | 回測筆數(同窗口) | 配對 | 實盤勝率 | 回測勝率 | 回測 540 天：筆/月、勝率、每筆% | 窗口起點(依據) |', '|---|---|---|---|---|---|---|---|']
for r in C['combos']:
    if 'error' in r: continue
    md.append('| %s | %d | %d | %d | %s | %s | %s、%s、%s | %s(%s) |' % (nm(r['combo']), r['live_n'], r['bt_n'], r['matched'], r['live_win'] if r['live_win'] is not None else '—', r['bt_win'] if r['bt_win'] is not None else '—', r['bt540_per_month'], r['bt540_win'], f2(r['bt540_mean_pct'], 3), r['window_from'], r['window_basis']))
# 狀態檔對照
md += ['', '## T11 機器人狀態檔 `realized`（毛損益）vs 幣安成交重建（毛損益）', '', '| 狀態檔組合 | 狀態檔筆數 | 狀態檔毛損益 | 重建筆數 | 重建毛損益 | 差 |', '|---|---|---|---|---|---|']
seen = set(); dsum = 0.0; dn = 0
for x in R['state_crosscheck']:
    if x['state_key'] in seen or x['ours_n'] == 0: continue
    seen.add(x['state_key'])
    if x['ours_n'] == x['state_trades']: dsum += x['ours_gross'] - x['state_realized_gross']; dn += 1
    md.append('| %s | %d | %s | %d | %s | %s |' % (nm(x['state_key']), x['state_trades'], f2(x['state_realized_gross'], 3), x['ours_n'], f2(x['ours_gross'], 3), f2(x['ours_gross'] - x['state_realized_gross'], 3)))
md += ['', '筆數完全相同的 %d 組：幣安成交重建的毛損益合計比狀態檔低 %s USDT（狀態檔較樂觀；差距來自成交價與機器人記帳價不同）。' % (dn, g2(-dsum, 2))]
open(os.path.join(OUT, 'tables.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n'); print('\n'.join(md)[:200], '...'); print('tables written', len(md))
