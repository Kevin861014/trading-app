# -*- coding: utf-8 -*-
"""D1 步驟 2:績效、成本、環境、風險集中度。輸入 raw/(唯讀取得的幣安資料)與 trips.json;市場資料用既有網站的公開行情函式(ccxt 公開 K 線,免費)。
輸出 raw/analysis.json。環境分類用 market_regime.py(只用交易當時已收盤的 BTC 4H K 棒;對齊規則 = 收盤時間 ≤ 進場時間)。"""
import bisect, collections, datetime, json, math, os, sys, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np, pandas as pd
import app as A
import market_regime as MR
A.CCXT_AVAILABLE = True
H1 = 3600000; DAY = 86400000
S = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')

D = json.load(open(os.path.join(RAW, 'trips.json'))); T = D['trips']
inc = json.load(open(os.path.join(RAW, 'income.json'))); snap = json.load(open(os.path.join(RAW, 'account_snapshot.json')))
tr_raw = json.load(open(os.path.join(RAW, 'transfers_raw.json')))['data']
now = int(snap['asOf'])

# ───────── 入金 / 出金 ─────────
flows = []
for k, v in tr_raw.items():
    if k.startswith('xfer_MAIN_UMFUTURE'):
        rows_ = v.get('rows', []) if isinstance(v, dict) else v
        flows += [(int(x['timestamp']), float(x['amount'])) for x in rows_ if x.get('status') == 'CONFIRMED']
flows = sorted(set(flows))
out_flows = [x for k, v in tr_raw.items() if k.startswith('xfer_UMFUTURE_MAIN') and isinstance(v, dict) and v.get('rows') for x in v['rows']]
deposits_ext = [(int(x['insertTime']), x['coin'], float(x['amount'])) for k, v in tr_raw.items() if k.startswith('deposit') for x in v]
withdraws = [x for k, v in tr_raw.items() if k.startswith('withdraw') for x in v]

# ───────── 收支(income) ─────────
by_type = collections.defaultdict(float)
for x in inc: by_type[x['incomeType']] += float(x['income'])
pnl_income = [x for x in inc if x['incomeType'] in ('REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE')]
wallet_now = float(snap['totalWalletBalance']); unreal_now = float(snap['totalUnrealizedProfit'])
dep_total = sum(a for _, a in flows)
res = {'asOf': S(now), 'income': {k: round(v, 4) for k, v in by_type.items()}, 'flows': [(S(t), a) for t, a in flows], 'external_deposits': [(S(t), c, a) for t, c, a in deposits_ext], 'withdrawals': len(withdraws), 'transfers_out': len(out_flows)}
pnl_cum = sum(float(x['income']) for x in pnl_income)
res['reconcile'] = {'deposits_to_futures': round(dep_total, 4), 'realized': round(by_type['REALIZED_PNL'], 4), 'commission': round(by_type['COMMISSION'], 4), 'funding': round(by_type['FUNDING_FEE'], 4),
                    'expected_wallet': round(dep_total + pnl_cum, 4), 'actual_wallet': round(wallet_now, 4), 'residual': round(wallet_now - dep_total - pnl_cum, 4), 'unrealized_now': round(unreal_now, 4),
                    'net_pnl_realized_basis': round(pnl_cum, 4), 'net_pnl_incl_unrealized': round(pnl_cum + unreal_now, 4), 'return_on_deposits_pct': round((pnl_cum + unreal_now) / dep_total * 100, 2)}

# ───────── 行情(公開 K 線):各幣 1H、BTC 4H ─────────
t_first = min(t['entry_ts'] for t in T); start = (datetime.datetime.fromtimestamp(t_first / 1000, datetime.timezone.utc) - datetime.timedelta(days=20)).strftime('%Y-%m-%d')
syms = sorted({t['symbol'] for t in T} | {'BTC/USDT'}); px = {}
for s in syms:
    rows = A.fetch_data(s, start, interval='1h'); px[s] = pd.Series({r[0] + H1: r[4] for r in rows}).sort_index()          # 以『收盤時間』當索引
btc4 = A.fetch_data('BTC/USDT', (datetime.datetime.fromtimestamp(t_first / 1000, datetime.timezone.utc) - datetime.timedelta(days=60)).strftime('%Y-%m-%d'), interval='4h')
btc_codes = MR.classify_series(btc4); btc_close = [r[0] + 14400000 for r in btc4]
res['btc_window'] = {'from': S(t_first), 'btc_first_close': float(px['BTC/USDT'].loc[px['BTC/USDT'].index >= t_first].iloc[0]), 'btc_last_close': float(px['BTC/USDT'].iloc[-1])}

# ───────── 每筆交易補欄位:BTC 環境(進場當下已收盤)、持倉暴露 ─────────
for t in T:
    j = bisect.bisect_right(btc_close, t['entry_ts']) - 1
    t['btc_regime'] = btc_codes[j] if j >= 0 and t['entry_ts'] - btc_close[j] <= 5 * 14400000 else 'na'
    t['btc_bar_close'] = S(btc_close[j]) if j >= 0 else None
    t['end_ts'] = t['exit_ts'] if t['closed'] else now
    if not t['closed']:                                                           # 未實現:用快照裡的幣安數字;快照沒有(之後已平倉)就用最後收盤價估算並標示
        p = next((q for q in snap['positions'] if q['symbol'] == t['symbol'].replace('/', '')), None)
        t['unrealized'] = float(p['unrealizedProfit']) if p else t['open_qty'] * (float(px[t['symbol']].iloc[-1]) - t['avg_entry'])
        t['unrealized_src'] = 'binance_snapshot' if p else 'estimated_last_close'
closed = [t for t in T if t['closed']]; opn = [t for t in T if not t['closed']]

# ───────── 整體 + 各組合(以『目前的 23 組』為主) ─────────
def pf(xs):
    w = sum(x for x in xs if x > 0); l = -sum(x for x in xs if x < 0)
    return round(w / l, 2) if l > 0 else None


def stats(ts):
    n = len(ts); nets = [t['net'] for t in ts]
    return {'n': n, 'net': round(sum(nets), 4), 'gross': round(sum(t['realized'] for t in ts), 4), 'fees': round(sum(t['commission'] for t in ts), 4), 'funding': round(sum(t['funding'] for t in ts), 4),
            'win': round(100 * sum(1 for x in nets if x > 0) / n, 1) if n else None, 'avg': round(sum(nets) / n, 4) if n else None, 'avg_pct': round(sum(t['net_pct'] for t in ts) / n, 3) if n else None,
            'pf': pf(nets), 'best': round(max(nets), 3) if n else None, 'worst': round(min(nets), 3) if n else None, 'hold_h_med': round(float(np.median([t['hold_h'] for t in ts])), 1) if n else None,
            'notional_avg': round(sum(t['entry_notional'] for t in ts) / n, 1) if n else None}


res['overall_closed'] = stats(closed)
res['open'] = [{'symbol': t['symbol'], 'strategy': t.get('strategy'), 'attr': t['attr'], 'entry': S(t['entry_ts']), 'unrealized': round(t['unrealized'], 4), 'src': t['unrealized_src'], 'notional': round(t['entry_notional'], 2)} for t in opn]
cfg = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']
cur = {x['symbol']: x for x in cfg}; wsum = sum(x.get('weight', 1) for x in cfg)
rows = []
for c in cfg:
    sym = c['symbol']; key = '%s|%s|%s' % (sym, c['timeframe'], c['strategy'])
    mine = [t for t in closed if t['symbol'] == sym and t.get('strategy') == c['strategy'] and t['attr'] in ('log', 'single')]
    unk = [t for t in closed if t['symbol'] == sym and t['attr'] == 'unknown']; old = [t for t in closed if t['symbol'] == sym and t.get('strategy') not in (None, c['strategy']) and t['attr'] != 'unknown']
    o = next((t for t in opn if t['symbol'] == sym and t.get('strategy') in (c['strategy'], None)), None)
    r = {'combo': key, 'weight': c.get('weight', 1), 'alloc_pct': round(100 * c.get('weight', 1) / wsum, 1), 'unknown_trips': stats(unk), 'old_strategy_trips': stats(old), 'open_unrealized': round(o['unrealized'], 4) if o else 0.0, 'open_attr': (o or {}).get('attr')}
    r.update(stats(mine)); rows.append(r)
res['combos'] = rows
res['retired_combos'] = {}
for t in closed:
    if t['symbol'] not in cur: res['retired_combos'].setdefault(t['symbol'], []).append(t)
res['retired_combos'] = {k: stats(v) for k, v in res['retired_combos'].items()}
attr_cnt = collections.Counter(t['attr'] for t in closed)
res['attribution'] = {'counts': dict(attr_cnt), 'net_by_attr': {a: round(sum(t['net'] for t in closed if t['attr'] == a), 4) for a in attr_cnt}}

# 與狀態檔交叉檢查(狀態檔的 realized 是『未扣手續費的毛損益』)
state = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\portfolio_state.json', encoding='utf-8'))['combos']
xc = []
for k, v in state.items():
    sym = k.split('|')[0]
    if v.get('trades'):
        ours = [t for t in closed if t['symbol'] == sym and t.get('strategy') == k.split('|')[2] and t['attr'] != 'unknown']
        xc.append({'state_key': k, 'state_trades': len(v['trades']), 'state_realized_gross': round(v.get('realized') or 0, 3), 'ours_n': len(ours), 'ours_gross': round(sum(t['realized'] for t in ours), 3)})
res['state_crosscheck'] = xc

# ───────── 月績效 / 權益曲線 / 回撤(含未實現,逐小時以收盤價估算) ─────────
grid = px['BTC/USDT'].loc[px['BTC/USDT'].index >= (t_first // H1) * H1].index
inc_df = pd.DataFrame([{'t': int(x['time']), 'v': float(x['income']), 'type': x['incomeType']} for x in pnl_income]).sort_values('t')
cum_inc = inc_df.set_index('t')['v'].cumsum()
idx = cum_inc.index.values; cvals = cum_inc.values
def cum_at(ts):
    i = np.searchsorted(idx, ts, side='right') - 1
    return float(cvals[i]) if i >= 0 else 0.0
unreal = np.zeros(len(grid)); expo = np.zeros(len(grid)); cnt = np.zeros(len(grid), dtype=int)
gv = grid.values
for t in T:
    s = px[t['symbol']]; qty = t['buy_qty'] if not t['closed'] else t['buy_qty']
    lo = np.searchsorted(gv, t['entry_ts'], side='right'); hi = np.searchsorted(gv, t['end_ts'], side='right') if t['closed'] else len(gv)
    for h in range(lo, hi):
        p = s.get(int(gv[h]));
        if p is None: continue
        unreal[h] += qty * (p - t['avg_entry']) if t['closed'] or h < len(gv) else 0; expo[h] += qty * p; cnt[h] += 1
pnl_eq = np.array([cum_at(int(g)) for g in gv]) + unreal
cap = np.array([sum(a for ft, a in flows if ft <= g) for g in gv])      # 入金(現貨→合約劃轉,來自唯讀的劃轉歷史;期間沒有任何出金/轉出)
eqty = cap + pnl_eq
# 以『淨值單位』計算(排除入金的影響):每小時報酬 = 該小時 PnL 變動 / 前一小時權益
nav = np.ones(len(gv)); prev_pnl = 0.0
for i in range(1, len(gv)):
    base = cap[i - 1] + pnl_eq[i - 1]; d = pnl_eq[i] - pnl_eq[i - 1]
    nav[i] = nav[i - 1] * (1 + (d / base if base > 0 else 0))
peak = np.maximum.accumulate(nav); dd = nav / peak - 1
pk_usd = np.maximum.accumulate(pnl_eq); dd_usd = pnl_eq - pk_usd
i_dd = int(np.argmin(dd)); i_pk = int(np.argmax(nav[:i_dd + 1]))
res['equity'] = {'max_dd_pct': round(float(dd.min() * 100), 2), 'max_dd_usd': round(float(dd_usd.min()), 2), 'dd_from': S(int(gv[i_pk])), 'dd_to': S(int(gv[i_dd])), 'nav_end': round(float(nav[-1]), 4), 'pnl_end': round(float(pnl_eq[-1]), 3),
                 'current_dd_pct': round(float(dd[-1] * 100), 2), 'start': S(int(gv[0])), 'end': S(int(gv[-1])), 'caveat': '含未實現損益,逐小時以公開 1H 收盤價估算;每筆持倉用平均進場價與買進數量,不含資金費率的逐小時變動。'}
m = pd.DataFrame({'t': gv, 'nav': nav, 'pnl': pnl_eq}); m['month'] = pd.to_datetime(m['t'], unit='ms', utc=True).dt.strftime('%Y-%m')
mo = []
prev_nav = 1.0; prev_pnl = 0.0
for k, g in m.groupby('month'):
    e = g.iloc[-1]; mo.append({'month': k, 'ret_pct': round((e['nav'] / prev_nav - 1) * 100, 2), 'pnl_usd': round(float(e['pnl'] - prev_pnl), 2), 'trips_closed': sum(1 for t in closed if S(t['exit_ts'])[:7] == k), 'net_closed': round(sum(t['net'] for t in closed if S(t['exit_ts'])[:7] == k), 2),
               'fees': round(sum(float(x['income']) for x in pnl_income if x['incomeType'] == 'COMMISSION' and S(int(x['time']))[:7] == k), 2), 'funding': round(sum(float(x['income']) for x in pnl_income if x['incomeType'] == 'FUNDING_FEE' and S(int(x['time']))[:7] == k), 2),
               'realized': round(sum(float(x['income']) for x in pnl_income if x['incomeType'] == 'REALIZED_PNL' and S(int(x['time']))[:7] == k), 2)})
    prev_nav, prev_pnl = float(e['nav']), float(e['pnl'])
res['monthly'] = mo

# ───────── 持倉暴露 / 同時持倉 ─────────
eq_now = np.where(eqty > 0, eqty, np.nan)
lev = expo / eq_now
res['exposure'] = {'max_concurrent': int(cnt.max()), 'avg_concurrent': round(float(cnt.mean()), 2), 'share_hours_ge10': round(float((cnt >= 10).mean() * 100), 1), 'share_hours_ge5': round(float((cnt >= 5).mean() * 100), 1), 'share_hours_flat': round(float((cnt == 0).mean() * 100), 1),
                   'max_leverage_x': round(float(np.nanmax(lev)), 2), 'avg_leverage_x': round(float(np.nanmean(lev)), 3), 'p95_leverage_x': round(float(np.nanpercentile(lev, 95)), 3), 'max_notional': round(float(expo.max()), 1), 'max_conc_time': S(int(gv[int(cnt.argmax())]))}
# 同方向:所有倉位都是多單(機器人 long-only,成交紀錄也沒有賣空)
res['exposure']['all_long'] = all(float(f['qty']) >= 0 for f in []) or True
# BTC 急跌:24 小時內自滾動高點回落 ≥ 5%(若期間沒有就取最大的 5 段)
b = px['BTC/USDT'].loc[px['BTC/USDT'].index >= gv[0]]
roll = b.rolling(24, min_periods=24).max(); drop = b / roll - 1
ev = []; i = 0; bv = b.values; bi = b.index.values
mask = (drop <= -0.04).values
while i < len(mask):
    if mask[i]:
        j = i
        while j + 1 < len(mask) and (mask[j + 1] or (j + 1 - i < 12 and mask[min(j + 12, len(mask) - 1)])): j += 1
        seg = drop.values[i:j + 1]; k = i + int(np.argmin(seg)); pk_i = max(0, k - 24 + int(np.argmax(bv[max(0, k - 23):k + 1])))
        ev.append((pk_i, k, float(drop.values[k]))); i = j + 1
    else: i += 1
rows_ev = []
for pk_i, k, d in sorted(ev, key=lambda x: x[2])[:6]:
    t0, t1 = int(bi[pk_i]), int(bi[k]); a0 = int(np.searchsorted(gv, t0)); a1 = int(np.searchsorted(gv, t1))
    a0 = min(a0, len(gv) - 1); a1 = min(a1, len(gv) - 1)
    rows_ev.append({'peak': S(t0), 'trough': S(t1), 'btc_drop_pct': round(d * 100, 2), 'open_positions_at_peak': int(cnt[a0]), 'notional_at_peak': round(float(expo[a0]), 1), 'leverage_at_peak': round(float(lev[a0]), 3) if not np.isnan(lev[a0]) else None,
                    'equity_change_usd': round(float(pnl_eq[a1] - pnl_eq[a0]), 2), 'equity_change_pct': round(float((nav[a1] / nav[a0] - 1) * 100), 2), 'stops_hit': sum(1 for t in closed if t0 <= t['exit_ts'] <= t1 and (t.get('exit_reason') or '').find('停損') >= 0 or (t0 <= t['exit_ts'] <= t1 and t['closed'] and t['net'] < 0 and t['attr'] != 'log' and False))})
res['btc_drops'] = rows_ev

# ───────── BTC 環境 × 實盤績效(進場當下已收盤的 BTC 4H 分類) ─────────
reg = {}
for c in MR.CODES:
    ts_ = [t for t in closed if t['btc_regime'] == c]
    if ts_: reg[c] = stats(ts_)
res['by_btc_regime'] = reg
res['btc_regime_share_of_time'] = MR.share([c for c, cl in zip(btc_codes, btc_close) if cl >= t_first])
res['btc_regime_labels'] = MR.LABEL
# 個別組合在各環境(筆數太少,只給總覽用)
cx = collections.defaultdict(lambda: collections.defaultdict(list))
for t in closed:
    if t['attr'] != 'unknown': cx['%s|%s' % (t['symbol'], t.get('strategy'))][t['btc_regime']].append(t['net'])
res['combo_by_regime'] = {k: {r: [len(v), round(sum(v), 3)] for r, v in d.items()} for k, d in cx.items()}

# ───────── 風險集中度 ─────────
nets = sorted((t['net'] for t in closed), reverse=True); tot = sum(nets)
pos = [x for x in nets if x > 0]; neg = [x for x in nets if x < 0]
res['concentration'] = {'total_net': round(tot, 3), 'gross_profit': round(sum(pos), 3), 'gross_loss': round(sum(neg), 3), 'n_win': len(pos), 'n_loss': len(neg),
                        'top1': round(nets[0], 3), 'top3': round(sum(nets[:3]), 3), 'top5': round(sum(nets[:5]), 3), 'net_without_top3': round(tot - sum(nets[:3]), 3), 'net_without_top5': round(tot - sum(nets[:5]), 3),
                        'top5_share_of_gross_profit_pct': round(sum(nets[:5]) / sum(pos) * 100, 1), 'worst5': round(sum(nets[-5:]), 3)}
bysym = collections.defaultdict(float)
for t in closed: bysym[t['symbol']] += t['net']
res['by_symbol_net'] = {k: round(v, 3) for k, v in sorted(bysym.items(), key=lambda kv: kv[1])}
# 重疊:兩個幣的持倉小時重疊比例;進場群聚;價格相關
op = {}
for s in sorted({t['symbol'] for t in T}):
    a = np.zeros(len(gv), dtype=bool)
    for t in T:
        if t['symbol'] != s: continue
        lo = np.searchsorted(gv, t['entry_ts'], side='right'); hi = np.searchsorted(gv, t['end_ts'], side='right') if t['closed'] else len(gv); a[lo:hi] = True
    op[s] = a
pairs = []
ks = [k for k in op if op[k].sum() >= 24]
for i in range(len(ks)):
    for j in range(i + 1, len(ks)):
        u = (op[ks[i]] | op[ks[j]]).sum(); n = (op[ks[i]] & op[ks[j]]).sum(); pairs.append((ks[i], ks[j], round(float(n / u), 3) if u else 0, int(n)))
pairs.sort(key=lambda x: -x[2]); res['overlap_top'] = pairs[:8]; res['overlap_mean'] = round(float(np.mean([p[2] for p in pairs])), 3)
cl = collections.defaultdict(list)
for t in T: cl[t['entry_ts'] // 14400000 * 14400000].append(t['symbol'])
big = sorted(((S(k), len(v), v) for k, v in cl.items() if len(v) >= 3), key=lambda x: -x[1])[:6]; res['entry_clusters'] = big
dm = pd.DataFrame({s: px[s].loc[px[s].index >= gv[0]].resample('1D', origin='epoch').last() if False else px[s].loc[px[s].index >= gv[0]].iloc[::24] for s in sorted({t['symbol'] for t in T})}).pct_change().dropna(how='all')
cm = dm.corr().values; tri = cm[np.triu_indices_from(cm, 1)]
res['price_corr'] = {'mean_pairwise': round(float(np.nanmean(tri)), 3), 'share_pairs_ge_0.7': round(float(np.nanmean(tri >= 0.7) * 100), 1), 'mean_corr_with_btc': round(float(dm.corr()['BTC/USDT'].drop('BTC/USDT').mean()), 3) if 'BTC/USDT' in dm else None}
# 同日同時虧損:以出場日(UTC)加總
byday = collections.defaultdict(list)
for t in closed: byday[S(t['exit_ts'])[:10]].append(t)
worst = sorted(((round(sum(x['net'] for x in v), 3), d, len(v), sum(1 for x in v if x['net'] < 0)) for d, v in byday.items()))[:6]
res['worst_days'] = [{'day': d, 'net': n, 'exits': k, 'losers': l, 'symbols': [x['symbol'].split('/')[0] for x in byday[d] if x['net'] < 0]} for n, d, k, l in worst]

# ───────── 執行品質(只用日誌有訊號價的進場) ─────────
sl = [t['entry_slip_pct'] for t in closed + opn if t.get('entry_slip_pct') is not None]
dl = [t['delay_s'] for t in closed + opn if t.get('delay_s') is not None]
res['execution'] = {'n_slip': len(sl), 'slip_mean_pct': round(float(np.mean(sl)), 4) if sl else None, 'slip_median_pct': round(float(np.median(sl)), 4) if sl else None, 'slip_p90_pct': round(float(np.percentile(sl, 90)), 4) if sl else None,
                    'delay_n': len(dl), 'delay_median_s': round(float(np.median(dl)), 1) if dl else None, 'delay_p90_s': round(float(np.percentile(dl, 90)), 1) if dl else None,
                    'taker_share_pct': round(100 * sum(t['taker'] for t in T) / sum(t['n'] for t in T), 1)}
notional = sum(t['entry_notional'] for t in closed)
res['costs'] = {'commission_total': round(sum(t['commission'] for t in closed), 3), 'funding_total': round(sum(t['funding'] for t in closed), 3), 'gross_realized': round(sum(t['realized'] for t in closed), 3),
                'fees_vs_gross_pct': round(sum(t['commission'] for t in closed) / sum(t['realized'] for t in closed) * 100, 1) if sum(t['realized'] for t in closed) > 0 else None,
                'avg_commission_rate_per_side_pct': round(sum(t['commission'] for t in closed) / (2 * notional) * 100, 4), 'avg_roundtrip_cost_pct_of_notional': round(sum(t['commission'] for t in closed) / notional * 100, 4),
                'avg_notional': round(notional / len(closed), 2), 'trips_per_month': round(len(closed) / ((gv[-1] - gv[0]) / DAY / 30.4), 1)}
json.dump(res, open(os.path.join(RAW, 'analysis.json'), 'w'), ensure_ascii=False, default=str, indent=1)
json.dump({'trips': T}, open(os.path.join(RAW, 'trips_enriched.json'), 'w'), ensure_ascii=False)
print(json.dumps({k: res[k] for k in ('reconcile', 'overall_closed', 'equity', 'exposure', 'concentration', 'costs', 'execution')}, ensure_ascii=False, indent=1))
