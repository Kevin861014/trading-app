# -*- coding: utf-8 -*-
"""D2 階段三(延伸):與 D1 相同的完整期間(2026-06-22 → 11-05)重播,對照實盤。
設定時間線只能『推測』:20 組(備份檔 ≈10/10 前)→ 24 組(≈10/10 起)→ 23 組(2026-10-29 重啟)。更早(2026-10-10 之前)BNB cmf、XRP cci、SOL force、PAXG supertrend 等舊策略的時間無紀錄,
所以對照只針對『歸屬可靠(log/single)』且『該幣策略整段沒變』的交易;日誌之前假設機器人一直在線(實際有 16 次看門狗啟動)。資金 = 2026-06-12 入金 152.49 + 2026-08-24 入金 156.39。"""
import collections, datetime, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d2_common import *
M, data = load_market(); sigs = load_signals(); EX = exit_params(); meta = d1_meta(); swap_t = meta['swap_t']; starts = meta['starts']; loops = log_loops(); loop_times = [t for t, _ in loops]
S_ = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
T0 = int(datetime.datetime(2026, 6, 22, 12, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000); T1 = M.h['TRX/USDT'][0][-1] + HOUR
A_ = cfg_combos('config.portfolio.json.bak_20251010'); B_ = cfg_combos('config.portfolio.json.bak_20251029_before_swap'); C_ = cfg_combos('config.portfolio.json')
eraB_start = int(datetime.datetime(2026, 10, 10, 7, 29, tzinfo=datetime.timezone.utc).timestamp() * 1000)         # 備份檔時間(台北 15:29)= 推測的換組時間
dep = [(int(datetime.datetime(2026, 8, 24, 1, 27, tzinfo=datetime.timezone.utc).timestamp() * 1000), 156.389344)]
P = S.default_params(EX, slip_entry=0.0003, slip_exit=0.0001, slip_stop=0.00042)
res = S.run(M, sigs, [(T0, A_), (eraB_start, B_), (swap_t, C_)], T0, T1, P, 152.491324, deposits=dep, loop_times=loop_times)
# 只比『該幣策略整段沒換、歸屬可靠』的實盤交易
changed = {'AAVE/USDT', 'BNB/USDT', 'PAXG/USDT', 'PYTH/USDT', 'SOL/USDT', 'XRP/USDT'}
live = [t for t in live_trips() if t['attr'] in ('log', 'single') and t['symbol'] not in changed]
tfms = {'1h': HOUR, '4h': 4 * HOUR}; used = set(); pairs = []; sim_only = []
sim = [s for s in res['trades'] if s['sym'] not in changed]
for s in sorted(sim, key=lambda x: x['entry_ts']):
    best = None
    for i, t in enumerate(live):
        if i in used or t['symbol'] != s['sym']: continue
        d = abs(t['entry_ts'] - s['entry_ts'])
        if d <= tfms[s['tf']] and (best is None or d < best[0]): best = (d, i)
    if best: used.add(best[1]); pairs.append((s, live[best[1]]))
    else: sim_only.append(s)
live_only = [t for i, t in enumerate(live) if i not in used]
cl = [(s, t) for s, t in pairs if t['closed']]
bysym = collections.defaultdict(lambda: [0, 0, 0])
for s, t in pairs: bysym[s['sym']][0] += 1
for s in sim_only: bysym[s['sym']][1] += 1
for t in live_only: bysym[t['symbol']][2] += 1
ex = [abs(s['exit_ts'] - t['exit_ts']) / 3600000 for s, t in cl]; nr = [s['notional'] / t['entry_notional'] for s, t in pairs]
out = {'window': {'from': S_(T0), 'to': S_(T1)}, 'assumption': '設定時間線與機器人在線時間為推測(見檔頭);只比 {AAVE,BNB,PAXG,PYTH,SOL,XRP} 以外、歸屬可靠的實盤交易',
       'counts': {'live_comparable': len(live), 'sim': len(sim), 'matched_entry_pm1bar': len(pairs), 'sim_only': len(sim_only), 'live_only': len(live_only), 'match_rate_of_live_pct': round(100 * len(pairs) / len(live), 1)},
       'exit_within_1h': sum(1 for x in ex if x <= 1.01), 'exit_within_4h': sum(1 for x in ex if x <= 4.01), 'closed_pairs': len(cl),
       'notional_ratio_sim_over_live': {'median': float(np.median(nr)), 'p10': float(np.percentile(nr, 10)), 'p90': float(np.percentile(nr, 90))},
       'net_matched': {'sim': round(sum(s['net'] for s, t in cl), 3), 'live': round(sum(t['net'] for s, t in cl), 3)}, 'by_symbol_matched_simonly_liveonly': {k: v for k, v in sorted(bysym.items())},
       'sim_only_sample': [{'key': s['key'], 'entry': S_(s['entry_ts']), 'exit': S_(s['exit_ts']), 'net': round(s['net'], 3)} for s in sim_only[:15]],
       'live_only_sample': [{'sym': t['symbol'], 'strategy': t.get('strategy'), 'entry': S_(t['entry_ts']), 'net': round(t['net'], 3)} for t in live_only[:15]],
       'sim_final': {'equity': round(res['equity_end'], 2), 'trades': len(res['trades']), 'rejected': res['rejected']}}
json.dump(out, open(os.path.join(HERE, 'results', 'replay_full_period.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))

# ── sim-only 的歸類:該幣第一筆實盤交易之前(組合很可能還沒上線)/ 之後(真正的差異:停機、斷路、被擋、手動等)──
first_live = {}
for t in live_trips():
    if t['attr'] in ('log', 'single'): first_live[t['symbol']] = min(first_live.get(t['symbol'], 10**15), t['entry_ts'])
before = [s for s in sim_only if s['sym'] in first_live and s['entry_ts'] < first_live[s['sym']] - 4 * HOUR]; after = [s for s in sim_only if s not in before]
out['sim_only_split'] = {'before_first_live_trade_of_that_symbol': len(before), 'after_first_live_trade': len(after), 'after_list': [{'key': s['key'], 'entry': S_(s['entry_ts']), 'exit': S_(s['exit_ts']), 'net': round(s['net'], 3)} for s in after]}
out['first_live_trade'] = {k: S_(v) for k, v in sorted(first_live.items())}
json.dump(out, open(os.path.join(HERE, 'results', 'replay_full_period.json'), 'w'), ensure_ascii=False, indent=1)
print('SPLIT', json.dumps(out['sim_only_split'], ensure_ascii=False)[:1800])
