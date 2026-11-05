# -*- coding: utf-8 -*-
"""D1 步驟 3:實盤 vs 網站回測(逐組合、逐筆配對)。兩者口徑不同,所以輸出的是『對照』與差異來源,不是『誤差』。
網站回測 = 既有 run_backtest(同策略程式、同停損規則、下一根開盤進場、網站的加密成本 0.14% 來回、起始 10,000、1.5% 風險);
實盤 = 幣安成交(市價單、實際手續費、資金費率、4.03% 風險、最小數量進位、保證金、斷路器、重啟/漏輪)。"""
import bisect, collections, datetime, json, math, os, sys, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import app as A, sim
A.CCXT_AVAILABLE = True
T = json.load(open(os.path.join(RAW, 'trips_enriched.json')))['trips']
cfg = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']
swap_t = json.load(open(os.path.join(RAW, 'trips.json')))['swap_t']
STEP = {'1h': 3600000, '4h': 14400000}
ERA_B_START = int(datetime.datetime(2026, 10, 10, tzinfo=datetime.timezone.utc).timestamp() * 1000)     # 設定備份檔的日期(推測的 24 組版本起點;只用於沒有任何實盤交易的組合)
now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
out = []; allbt = []; alllive = []; allfull = []
for c in cfg:
    sym, tf, st = c['symbol'], c['timeframe'], c['strategy']; step = STEP[tf]
    live = [t for t in T if t['symbol'] == sym and t.get('strategy') == st and t['attr'] in ('log', 'single')]
    swapped = any(t['symbol'] == sym and t.get('strategy') not in (None, st) and t['attr'] == 'log' for t in T) or sym in ('SOL/USDT', 'PAXG/USDT', 'PYTH/USDT', 'AAVE/USDT')
    W = min((t['entry_ts'] for t in live), default=(swap_t if swapped else ERA_B_START))
    if swapped: W = max(W, swap_t) if not live else min(t['entry_ts'] for t in live)
    start = (datetime.datetime.now() - datetime.timedelta(days=900 if tf == '4h' else 580)).strftime('%Y-%m-%d')
    rows = A.fetch_data(sym, start, interval=tf)
    res = A.run_backtest(rows, strategy=st, risk_pct=0.015, timeframe=tf, **sim.cost_kwargs(sym, st))
    if not res: out.append({'combo': '%s|%s|%s' % (sym, tf, st), 'error': 'backtest unavailable'}); continue
    bt = [x for x in res[2]['trade_log'] if not x.get('open') and int(x['entry_date'].replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) >= W - step]
    btm = [(int(x['entry_date'].replace(tzinfo=datetime.timezone.utc).timestamp() * 1000), x) for x in bt]
    pairs = []; used = set()
    for t in live:
        if not t['closed']: continue
        best = None
        for i, (e, x) in enumerate(btm):
            if i in used: continue
            d = abs(e - t['entry_ts'])
            if d <= step and (best is None or d < best[0]): best = (d, i)
        if best: used.add(best[1]); pairs.append((t, btm[best[1]][1]))
    cut540 = now - 540 * 86400000
    full = [x for x in res[2]['trade_log'] if not x.get('open') and int(x['entry_date'].replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) >= cut540]
    fw = sum(x['ret'] for x in full if x['ret'] > 0); fl = -sum(x['ret'] for x in full if x['ret'] < 0)
    live_closed = [t for t in live if t['closed']]
    r = {'combo': '%s|%s|%s' % (sym, tf, st), 'window_from': datetime.datetime.fromtimestamp(W / 1000, datetime.timezone.utc).strftime('%Y-%m-%d'), 'window_basis': 'first live trade' if live else ('swap time' if swapped else 'ERA_B_START(推測)'),
         'live_n': len(live_closed), 'bt_n': len(bt), 'matched': len(pairs), 'live_only': len(live_closed) - len(pairs), 'bt_only': len(bt) - len(pairs),
         'bt_net_pct_sum': round(sum(x['ret'] for x in bt), 2), 'live_net_pct_sum': round(sum(t['net_pct'] for t in live_closed), 2),
         'bt_win': round(100 * sum(1 for x in bt if x['ret'] > 0) / len(bt), 1) if bt else None, 'live_win': round(100 * sum(1 for t in live_closed if t['net'] > 0) / len(live_closed), 1) if live_closed else None}
    if pairs:
        r['entry_px_diff_pct'] = round(float(np.mean([(t['avg_entry'] / x['entry_px'] - 1) * 100 for t, x in pairs])), 4)
        r['exit_px_diff_pct'] = round(float(np.mean([(t['avg_exit'] / x['exit_px'] - 1) * 100 for t, x in pairs if t.get('avg_exit') and x.get('exit_px')])), 4)
        r['pair_ret_diff_pct'] = round(float(np.mean([t['net_pct'] - x['ret'] for t, x in pairs])), 3)
        r['pair_bt_ret_mean'] = round(float(np.mean([x['ret'] for _, x in pairs])), 3); r['pair_live_ret_mean'] = round(float(np.mean([t['net_pct'] for t, _ in pairs])), 3)
        r['exit_same_bar'] = sum(1 for t, x in pairs if abs(int(x['exit_date'].replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) - t['exit_ts']) <= step)
    r['bt540_n'] = len(full); r['bt540_win'] = round(100 * sum(1 for x in full if x['ret'] > 0) / len(full), 1) if full else None; r['bt540_mean_pct'] = round(float(np.mean([x['ret'] for x in full])), 3) if full else None; r['bt540_pf'] = round(fw / fl, 2) if fl > 0 else None
    r['bt540_per_month'] = round(len(full) / 17.7, 1); allfull.extend(x['ret'] for x in full)
    out.append(r); allbt += [x['ret'] for x in bt]; alllive += [t['net_pct'] for t in live_closed]
    print(r['combo'], r['live_n'], r['bt_n'], r['matched'], flush=True)
fw_ = sum(x for x in allfull if x > 0); fl_ = -sum(x for x in allfull if x < 0)
tot = {'bt540_n': len(allfull), 'bt540_win': round(100 * sum(1 for x in allfull if x > 0) / len(allfull), 1), 'bt540_mean_pct': round(float(np.mean(allfull)), 3), 'bt540_pf': round(fw_ / fl_, 2), 'live_n': sum(r.get('live_n', 0) for r in out), 'bt_n': sum(r.get('bt_n', 0) for r in out), 'matched': sum(r.get('matched', 0) for r in out),
       'bt_mean_pct': round(float(np.mean(allbt)), 3) if allbt else None, 'live_mean_pct': round(float(np.mean(alllive)), 3) if alllive else None}
# 逐筆配對的總覽
pe = [r for r in out if r.get('matched')]
tot['entry_px_diff_pct_wmean'] = round(sum(r['entry_px_diff_pct'] * r['matched'] for r in pe) / sum(r['matched'] for r in pe), 4)
tot['exit_px_diff_pct_wmean'] = round(sum(r['exit_px_diff_pct'] * r['matched'] for r in pe if 'exit_px_diff_pct' in r) / sum(r['matched'] for r in pe if 'exit_px_diff_pct' in r), 4)
tot['pair_ret_diff_pct_wmean'] = round(sum(r['pair_ret_diff_pct'] * r['matched'] for r in pe) / sum(r['matched'] for r in pe), 3)
json.dump({'combos': out, 'total': tot}, open(os.path.join(RAW, 'compare.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(tot, ensure_ascii=False))
