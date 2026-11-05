# -*- coding: utf-8 -*-
"""D2 階段三:校準。用『設定與日誌都確定』的期間(日誌第一次成功啟動 → 資料結束),把模擬結果和實盤逐項比對。
設定時間線 = 24 組(2026-10-29 換組前)→ 現行 23 組(換組後);機器人輪詢時間取自日誌(漏輪/斷線自動帶入);起始資金 = 日誌第一輪看到的保證金(當時空手)。"""
import bisect, collections, datetime, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d2_common import *
M, data = load_market(); sigs = load_signals(); EX = exit_params(); meta = d1_meta(); swap_t = meta['swap_t']; starts = meta['starts']
T0 = starts[0][0]; loops = log_loops(); loop_times = [t for t, _ in loops]
T1 = M.h['TRX/USDT'][0][-1] + HOUR
S_ = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
live = [t for t in live_trips() if t['entry_ts'] >= T0 - 3600000]
# 由實盤量測的成交參數(D1 的成交資料;這些是『校準值』,不是假設)
slip_stop = [t['avg_exit'] / t['stop_px'] - 1 for t in live if t.get('stop_px') and t['closed'] and '保護停損' in (t.get('exit_reason') or '')]
init = next(v for t, v in loops if t >= T0)
B = cfg_combos('config.portfolio.json.bak_20251029_before_swap'); C = cfg_combos('config.portfolio.json')
P = S.default_params(EX, slip_entry=0.0003, slip_exit=0.0001, slip_stop=max(0.0, -float(np.mean(slip_stop))) if slip_stop else 0.0005)
res = S.run(M, sigs, [(T0, B), (swap_t, C)], T0, T1, P, init, loop_times=loop_times)
tr = res['trades']; tfms = {'1h': HOUR, '4h': 4 * HOUR}
# ── 逐筆配對 ──
used = set(); pairs = []; sim_only = []
for s in sorted(tr, key=lambda x: x['entry_ts']):
    best = None
    for i, t in enumerate(live):
        if i in used or t['symbol'] != s['sym']: continue
        d = abs(t['entry_ts'] - s['entry_ts'])
        if d <= tfms[s['tf']] and (best is None or d < best[0]): best = (d, i)
    if best: used.add(best[1]); pairs.append((s, live[best[1]]))
    else: sim_only.append(s)
live_only = [t for i, t in enumerate(live) if i not in used]
rm = lambda xs: float(np.median(xs)) if xs else None
exit_d = [abs(s['exit_ts'] - t['exit_ts']) / 3600000 for s, t in pairs if t['closed']]
out = {'window': {'from': S_(T0), 'to': S_(T1), 'init_equity_from_log': init, 'config': 'B(24 組) → C(23 組)@' + S_(swap_t), 'loops_in_log': len(loop_times)},
       'params': {k: v for k, v in P.items() if k not in ('exit', '_fts')}, 'slip_stop_samples': len(slip_stop), 'slip_stop_mean_pct': (float(np.mean(slip_stop)) * 100 if slip_stop else None),
       'counts': {'live_trips': len(live), 'sim_trips': len(tr), 'matched': len(pairs), 'sim_only': len(sim_only), 'live_only': len(live_only)}, 'rejected': res['rejected'], 'notes': res['notes']}
cl = [(s, t) for s, t in pairs if t['closed']]
out['matched_stats'] = {'n_closed_pairs': len(cl), 'entry_time_diff_s_median': rm([abs(s['entry_ts'] - t['entry_ts']) / 1000 for s, t in pairs]),
                        'exit_time_diff_h_median': rm(exit_d), 'exit_within_1h': sum(1 for x in exit_d if x <= 1.01), 'exit_within_4h': sum(1 for x in exit_d if x <= 4.01),
                        'notional_ratio_sim_over_live_median': rm([s['notional'] / t['entry_notional'] for s, t in pairs]), 'notional_ratio_mean': float(np.mean([s['notional'] / t['entry_notional'] for s, t in pairs])) if pairs else None,
                        'fee_ratio_median': rm([s['fees'] / t['commission'] for s, t in cl if t['commission']]), 'net_diff_median_usd': rm([s['net'] - t['net'] for s, t in cl]),
                        'sim_net_sum_matched': round(sum(s['net'] for s, t in cl), 4), 'live_net_sum_matched': round(sum(t['net'] for s, t in cl), 4)}
out['sim_only'] = [{'key': s['key'], 'entry': S_(s['entry_ts']), 'exit': S_(s['exit_ts']), 'net': round(s['net'], 3), 'why': s['why']} for s in sim_only]
out['live_only'] = [{'sym': t['symbol'], 'strategy': t.get('strategy'), 'attr': t['attr'], 'entry': S_(t['entry_ts']), 'exit': S_(t['exit_ts']) if t['closed'] else '持倉中', 'net': round(t['net'], 3), 'reason': t.get('exit_reason')} for t in live_only]
out['totals'] = {'live': {'n_closed': sum(1 for t in live if t['closed']), 'net': round(sum(t['net'] for t in live if t['closed']), 4), 'fees': round(sum(t['commission'] for t in live if t['closed']), 4), 'funding': round(sum(t['funding'] for t in live if t['closed']), 4), 'gross': round(sum(t['realized'] for t in live if t['closed']), 4), 'notional_sum': round(sum(t['entry_notional'] for t in live), 2)},
                 'sim': {'n_closed': len(tr), 'net': round(sum(s['net'] for s in tr), 4), 'fees': round(sum(s['fees'] for s in tr), 4), 'funding': round(sum(s['funding'] for s in tr), 4), 'gross': round(sum(s['gross'] for s in tr), 4), 'notional_sum': round(sum(s['notional'] for s in tr), 2)},
                 'sim_open_end': res['open']}
# ── 權益曲線:實盤 = 日誌每輪看到的保證金(錢包+未實現);模擬 = 小時權益 ──
byh = {}
for t, v in loops: byh[t - t % HOUR + HOUR] = v          # 該小時『最後一輪』看到的保證金,標在小時結束時間(與模擬的整點權益同一時刻)
marks = {h: e for h, e, w, ex_, n in res['marks']}; nmarks = {h: n for h, e, w, ex_, n in res['marks']}
common = sorted(h for h in byh if h in marks)
live_e = np.array([byh[h] for h in common]); sim_e = np.array([marks[h] for h in common])
def mdd(x):
    pk = np.maximum.accumulate(x); return float(((x - pk) / pk).min() * 100)
live_open = [sum(1 for t in live if t['entry_ts'] <= h < (t['exit_ts'] if t['closed'] else 10**15)) for h in common]
out['equity'] = {'hours_compared': len(common), 'live_start': float(live_e[0]), 'live_end': float(live_e[-1]), 'sim_start': float(sim_e[0]), 'sim_end': float(sim_e[-1]),
                 'live_change_usd': float(live_e[-1] - live_e[0]), 'sim_change_usd': float(sim_e[-1] - sim_e[0]), 'live_mdd_pct': mdd(live_e), 'sim_mdd_pct': mdd(sim_e),
                 'hourly_diff_mean_usd': float((sim_e - live_e).mean()), 'hourly_diff_abs_max_usd': float(np.abs(sim_e - live_e).max()), 'corr_hourly_changes': float(np.corrcoef(np.diff(live_e), np.diff(sim_e))[0, 1]),
                 'live_max_dd_usd': float((live_e - np.maximum.accumulate(live_e)).min()), 'sim_max_dd_usd': float((sim_e - np.maximum.accumulate(sim_e)).min())}
out['concurrency'] = {'live_avg': float(np.mean(live_open)), 'sim_avg': float(np.mean([nmarks[h] for h in common])), 'live_max': int(max(live_open)), 'sim_max': int(max(nmarks[h] for h in common)), 'corr': float(np.corrcoef(live_open, [nmarks[h] for h in common])[0, 1])}
out['series'] = {'hours': [S_(h) for h in common[::6]], 'live': [round(float(x), 2) for x in live_e[::6]], 'sim': [round(float(x), 2) for x in sim_e[::6]]}
os.makedirs(os.path.join(HERE, 'results'), exist_ok=True); json.dump(out, open(os.path.join(HERE, 'results', 'calibration.json'), 'w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ('series', 'sim_only', 'live_only')}, ensure_ascii=False, indent=1, default=str))
print('SIM ONLY', len(sim_only), out['sim_only'][:12]); print('LIVE ONLY', len(live_only), out['live_only'][:12])
