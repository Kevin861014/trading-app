# -*- coding: utf-8 -*-
"""D3:A(現行全部 23 組)vs B(不啟用 TRX、XRP 的 1H 組合)的時間順序多區段比較。沿用 D2 已校準的模擬器(d2_sim.py),不重新開發。
事先固定(在看任何結果之前寫死):
  - 兩個方案、成本、風險、起始資金 310(每個區段各自重新開始,空手)、Σ權重固定 16(合約尚未上市的組合就是沒有資料、不交易,不重新分配資金)。
  - 區段:日曆半年。分四類(分界依據:網站『深度分析』對加密貨幣取 730 天評估窗口、並多取 400 天暖機 → 取得範圍約從選擇日往前 1130 天;2026-08 的策略庫研究用 900 天 4H 快取)——
      I  較獨立的歷史:2021-01 → 2023-06-30(沒有任何文件記載它被取得或用來挑選這 23 組;但不能證明策略『模板』沒有看過它,所以不稱為 OOS 通過)
      G  灰色地帶:2023-07 → 2024-02-29(可能只被當作暖機取得,不在排名窗口,但無法排除被看過 → 不算獨立)
      X  歷史探索:2024-03 → 2026-10-29(已知被用於策略庫研究/深度分析/挑選 → 選擇已看過)
      T  選擇之後:2026-10-29 → 現在(約 1 週,太短,只列出不下結論)
  - BTC 區段標籤規則:區段內 BTC 漲跌 > +15% = 上升、< −15% = 下跌、其餘 = 盤整。
  - 不因任何區段結果不好而更換區段或調整參數。"""
import bisect, collections, datetime, json, os, pickle, sys, time, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); RES = os.path.join(HERE, 'results'); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'validation', 'd2_portfolio')); sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import d2_sim as S
from d2_common import cfg_combos, exit_params

HOUR = S.HOUR
long = pickle.load(open(os.path.join(RAW, 'long.pkl'), 'rb')); M = S.Market(long); sigs = pickle.load(open(os.path.join(RAW, 'signals_long.pkl'), 'rb')); EX = exit_params(); C_ = cfg_combos('config.portfolio.json')
from d3_config import *
S_ = lambda t: datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')
NOW = M.h['TRX/USDT'][0][-1] + HOUR
ONE_H = set(ONE_H)
BLOCKS = [(c, n, a, (b if b is not None else NOW)) for c, n, a, b in BLOCKS]
# BTC
bt = long['candles'][('BTC/USDT', '4h')]; bt_ts = [r[0] for r in bt]; bt_c = [r[4] for r in bt]
def btc_at(t): return bt_c[max(0, bisect.bisect_right(bt_ts, t) - 1)]
b1 = long['candles'][('BTC/USDT', '1h')]; b1c = np.array([r[4] for r in b1]); b1t = [r[0] for r in b1]
roll = np.array([b1c[max(0, i - 23):i + 1].max() for i in range(len(b1c))]); dropv = b1c / roll - 1
events = []; i = 0
while i < len(b1c):
    if dropv[i] <= -0.05:
        j = i
        while j + 1 < len(b1c) and dropv[j + 1] <= -0.05 + 0.02: j += 1         # 回升超過 3% 以上才視為結束(避免來回切碎)
        k = i + int(np.argmin(dropv[i:j + 1])); pk = max(0, k - 23) + int(np.argmax(b1c[max(0, k - 23):k + 1]))
        events.append((b1t[pk] + HOUR, b1t[k] + HOUR, float(dropv[k]))); i = j + 1
    else: i += 1


def active_count(T0):
    n = 0
    for c in C_:
        sg = sigs.get((c['symbol'], c['timeframe'], c['strategy']))
        if sg and min(sg) + {'1h': HOUR, '4h': 4 * HOUR}[c['timeframe']] <= T0: n += 1
    return n


def metrics(res, T0, T1):
    tr = res['trades']; mk = res['marks']; nets = [t['net'] for t in tr]
    eq = np.array([e for _, e, *_ in mk]); pk = np.maximum.accumulate(eq); dd = (eq - pk) / pk
    pos = sum(x for x in nets if x > 0); neg = -sum(x for x in nets if x < 0); srt = sorted(nets, reverse=True); tot = sum(nets)
    expo = np.array([x / e for (_, e, _, x, _) in mk]); ncon = np.array([n for *_, n in mk])
    day = collections.OrderedDict()
    for h, e, *_ in mk: day[datetime.datetime.fromtimestamp(h / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')] = e
    dv = list(day.values()); dchg = np.diff(dv) if len(dv) > 1 else np.array([0.0])
    gross = sum(t['gross'] for t in tr); fees = sum(t['fees'] for t in tr)
    return {'return_pct': round((res['equity_end'] / INIT - 1) * 100, 2), 'max_dd_pct': round(float(dd.min() * 100), 2), 'worst_day_usd': round(float(dchg.min()), 2), 'trades': len(tr),
            'win_pct': round(100 * sum(1 for x in nets if x > 0) / len(nets), 1) if nets else None, 'pf': round(pos / neg, 2) if neg > 0 else None, 'avg_net_usd': round(tot / len(nets), 4) if nets else None,
            'avg_net_pct_of_notional': round(float(np.mean([t['net'] / t['notional'] for t in tr])) * 100, 3) if tr else None, 'fees': round(fees, 2), 'gross': round(gross, 2), 'funding': round(sum(t['funding'] for t in tr), 2),
            'avg_concurrent': round(float(ncon.mean()), 2), 'max_concurrent': int(ncon.max()), 'max_exposure_x': round(float(expo.max()), 2), 'avg_exposure_x': round(float(expo.mean()), 3),
            'top3_net': round(sum(srt[:3]), 2), 'net_without_top3': round(tot - sum(srt[:3]), 2), 'net_closed': round(tot, 2), 'rejected': res['rejected']}


def decomp(res):
    out = {}
    for name, cond in (('1H', lambda t: t['tf'] == '1h'), ('4H', lambda t: t['tf'] == '4h')):
        ts = [t for t in res['trades'] if cond(t)]
        if not ts: out[name] = {'n': 0}; continue
        nh = sum(t['notional'] * max(1.0, (t['exit_ts'] - t['entry_ts']) / HOUR) for t in ts)
        out[name] = {'n': len(ts), 'gross': round(sum(t['gross'] for t in ts), 3), 'fees': round(sum(t['fees'] for t in ts), 3), 'funding': round(sum(t['funding'] for t in ts), 3), 'net': round(sum(t['net'] for t in ts), 3),
                     'avg_gross_pct': round(float(np.mean([t['gross'] / t['notional'] for t in ts])) * 100, 3), 'avg_fee_pct': round(float(np.mean([t['fees'] / t['notional'] for t in ts])) * 100, 3), 'avg_net_pct': round(float(np.mean([t['net'] / t['notional'] for t in ts])) * 100, 3),
                     'avg_hold_h': round(float(np.mean([(t['exit_ts'] - t['entry_ts']) / HOUR for t in ts])), 1), 'notional_hours': round(nh, 0), 'gross_bp_per_notional_hour': round(sum(t['gross'] for t in ts) / nh * 1e4, 4), 'net_bp_per_notional_hour': round(sum(t['net'] for t in ts) / nh * 1e4, 4)}
    return out


def drops_in(res, T0, T1):
    mk = {h: (e, n) for h, e, w, x, n in res['marks']}; rows = []
    for pk, tr, d in events:
        if pk >= T0 and tr <= T1 and pk in mk and tr in mk:
            rows.append({'peak': S_(pk), 'btc_drop_pct': round(d * 100, 1), 'open_at_peak': mk[pk][1], 'equity_change_usd': round(mk[tr][0] - mk[pk][0], 2)})
    return {'events': rows, 'n': len(rows), 'sum_usd': round(sum(r['equity_change_usd'] for r in rows), 2)}


def run_one(T0, T1, restrict, P):
    combos = [c for c in C_ if restrict(c['symbol'])]
    res = S.run(M, sigs, [(T0, combos)], T0, T1, S.default_params(EX, **P), INIT)
    return res


out = {'init': INIT, 'class_label': CLASS_LABEL, 'blocks': [], 'btc_drop_events_total': len(events)}
t0 = time.time()
for cls, name, T0, T1 in BLOCKS:
    r = {'class': cls, 'class_label': CLASS_LABEL[cls], 'name': name, 'from': S_(T0), 'to': S_(T1), 'active_combos_at_start': active_count(T0), 'btc_pct': round((btc_at(T1) / btc_at(T0) - 1) * 100, 1)}
    r['btc_regime'] = btc_regime(r['btc_pct'])
    resA = run_one(T0, T1, lambda s: True, PB); resB = run_one(T0, T1, lambda s: s not in ONE_H, PB)
    r['A'] = metrics(resA, T0, T1); r['B'] = metrics(resB, T0, T1)
    r['A_stress'] = metrics(run_one(T0, T1, lambda s: True, PS), T0, T1); r['B_stress'] = metrics(run_one(T0, T1, lambda s: s not in ONE_H, PS), T0, T1)
    r['decomp_A'] = decomp(resA); r['btc_drops'] = {'A': drops_in(resA, T0, T1), 'B': drops_in(resB, T0, T1)}
    out['blocks'].append(r)
    print(cls, name, 'act', r['active_combos_at_start'], 'btc', r['btc_pct'], r['btc_regime'], '| A', r['A']['return_pct'], r['A']['max_dd_pct'], r['A']['trades'], '| B', r['B']['return_pct'], r['B']['max_dd_pct'], r['B']['trades'], '%.0fs' % (time.time() - t0), flush=True)
# 連續(不重置)的較獨立歷史,看複利與最大回撤
for cls, label, T0, T1 in (('I', '較獨立的歷史連續 2021-01 → 2023-06-30', ms(2021, 1, 1), ms(2023, 7, 1)), ('X', '歷史探索連續 2024-03 → 2026-10-29', ms(2024, 3, 1), ms(2026, 10, 29))):
    rA = run_one(T0, T1, lambda s: True, PB); rB = run_one(T0, T1, lambda s: s not in ONE_H, PB)
    out.setdefault('continuous', {})[cls] = {'label': label, 'from': S_(T0), 'to': S_(T1), 'A': metrics(rA, T0, T1), 'B': metrics(rB, T0, T1), 'decomp_A': decomp(rA)}
json.dump(out, open(os.path.join(RES, 'walkforward.json'), 'w'), ensure_ascii=False, indent=1)
print('saved')
