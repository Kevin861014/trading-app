# -*- coding: utf-8 -*-
"""D2 階段四:固定情境比較(事先定義,不掃參數、不挑最佳)。
共同設定:現行 23 組固定、起始資金 310 USDT(不入金不出金)、同一套成本(吃單 0.05%/邊、進場滑價 0.03%、出場 0.01%、停損 0.042%、實際資金費率)、機器人一直在線(延遲 13.8 秒)、相同期間。
情境(各只改一件事):
  A 維持全部 23 組。
  B 不啟用 1H 組合(TRX、XRP);其他組合的 alloc 不變(Σ權重仍 16),所以單純移除這兩組。
  C 同時暴露上限:若新進場會讓『總名目 > 0.5 × 權益』就不進場(不縮倉、不平既有倉)。0.5 是事先選的(約為實盤 95 百分位暴露 0.57x 的整數化),沒有掃描。
  D 同一輪進場上限:同一個決策時點最多 2 組新進場,超過的跳過(權重大者優先,同權重依設定順序)。
期間:L = 實盤期間(2026-06-22 → 11-05);E = 擴充期間(2025-05-08 → 2026-11-05,含 BTC 的中段下跌)。
兩段都不是樣本外:23 組是從類似的歷史挑出來的(挑選偏誤),實盤期間又被 D1 看過。結果一律當『探索』。"""
import collections, datetime, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d2_common import *
M, data = load_market(); sigs = load_signals(); EX = exit_params(); C_ = cfg_combos('config.portfolio.json')
ms = lambda y, m, d, h=0: int(datetime.datetime(y, m, d, h, tzinfo=datetime.timezone.utc).timestamp() * 1000)
S_ = lambda t: datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')
T1 = M.h['TRX/USDT'][0][-1] + HOUR; INIT = 310.0
PERIODS = {'L': ('實盤期間', ms(2026, 6, 22, 12)), 'E': ('擴充期間', ms(2025, 5, 8))}
ONE_H = {'TRX/USDT', 'XRP/USDT'}
SCEN = {'A': dict(label='A 維持全部 23 組'), 'B': dict(label='B 不啟用 1H 組合', restrict=lambda k: k not in ONE_H),
        'C': dict(label='C 同時暴露上限 0.5×權益', guard=lambda cap, notional_all, new, pos: notional_all + new <= 0.5 * cap), 'D': dict(label='D 同一輪最多 2 組新進場', max_entries=2)}


def metrics(res, init, T0):
    tr = res['trades']; mk = res['marks']; nets = [t['net'] for t in tr]
    eq = np.array([e for _, e, _, _, _ in mk]); hrs = [h for h, *_ in mk]
    pk = np.maximum.accumulate(eq); dd = (eq - pk) / pk
    pos = sum(x for x in nets if x > 0); neg = -sum(x for x in nets if x < 0)
    expo = np.array([x / e for (_, e, _, x, _) in mk]); ncon = np.array([n for *_, n in mk])
    day = collections.OrderedDict()
    for h, e, *_ in mk: day[datetime.datetime.fromtimestamp(h / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')] = e
    dv = list(day.values()); dchg = np.diff(dv); dpct = dchg / np.array(dv[:-1])
    srt = sorted(nets, reverse=True); tot = sum(nets); n3 = len(eq) // 3
    thirds = [round(float(eq[min((i + 1) * n3, len(eq) - 1)] - eq[i * n3]), 2) for i in range(3)]
    gross = sum(t['gross'] for t in tr)
    return {'end_equity': round(res['equity_end'], 2), 'return_pct': round((res['equity_end'] / init - 1) * 100, 2), 'max_dd_pct': round(float(dd.min() * 100), 2), 'max_dd_usd': round(float((eq - pk).min()), 2),
            'trades': len(tr), 'win_pct': round(100 * sum(1 for x in nets if x > 0) / len(nets), 1) if nets else None, 'pf': round(pos / neg, 2) if neg > 0 else None, 'avg_net': round(tot / len(nets), 4) if nets else None, 'net_closed': round(tot, 2),
            'fees': round(sum(t['fees'] for t in tr), 2), 'funding': round(sum(t['funding'] for t in tr), 2), 'fees_vs_gross_pct': round(sum(t['fees'] for t in tr) / gross * 100, 1) if gross > 0 else None,
            'avg_concurrent': round(float(ncon.mean()), 2), 'max_concurrent': int(ncon.max()), 'share_hours_flat_pct': round(float((ncon == 0).mean() * 100), 1), 'max_exposure_x': round(float(expo.max()), 2), 'p95_exposure_x': round(float(np.percentile(expo, 95)), 2),
            'worst_day_usd': round(float(dchg.min()), 2), 'worst_day_pct': round(float(dpct.min() * 100), 2), 'worst_day': list(day.keys())[1 + int(np.argmin(dchg))],
            'top3_net': round(sum(srt[:3]), 2), 'net_without_top3': round(tot - sum(srt[:3]), 2), 'top3_share_of_net_pct': round(sum(srt[:3]) / tot * 100, 0) if tot > 0 else None,
            'thirds_usd': thirds, 'rejected': res['rejected'], 'notes': res['notes']}


out = {'init': INIT, 'periods': {k: {'label': v[0], 'from': S_(v[1]), 'to': S_(T1)} for k, v in PERIODS.items()}, 'results': {}}
for pk_, (plabel, T0) in PERIODS.items():
    for sk, sc in SCEN.items():
        P = S.default_params(EX, slip_entry=0.0003, slip_exit=0.0001, slip_stop=0.00042, sumw_override=16.0)
        combos = [c for c in C_ if sc.get('restrict', lambda k: True)(c['symbol'])]
        res = S.run(M, sigs, [(T0, combos)], T0, T1, P, INIT, entry_guard=sc.get('guard'), max_entries_per_cycle=sc.get('max_entries'))
        m = metrics(res, INIT, T0); m['label'] = sc['label']; out['results']['%s_%s' % (pk_, sk)] = m
        print(pk_, sk, json.dumps({k: m[k] for k in ('return_pct', 'max_dd_pct', 'trades', 'pf', 'max_exposure_x', 'worst_day_usd', 'net_without_top3', 'thirds_usd')}, ensure_ascii=False), flush=True)
# 成本壓力(只對 A、B 各跑一次,看『B 比 A 好』這個結論會不會因成本假設而翻轉;不是調參):吃單 0.075%/邊、進場滑價 0.06%、出場 0.02%、停損 0.084%
out['stress'] = {}
for pk_, (plabel, T0) in PERIODS.items():
    for sk in ('A', 'B'):
        sc = SCEN[sk]; P = S.default_params(EX, taker=0.00075, slip_entry=0.0006, slip_exit=0.0002, slip_stop=0.00084, sumw_override=16.0)
        combos = [c for c in C_ if sc.get('restrict', lambda k: True)(c['symbol'])]
        res = S.run(M, sigs, [(T0, combos)], T0, T1, P, INIT)
        m = metrics(res, INIT, T0); m['label'] = sc['label'] + '(成本 ×1.5)'; out['stress']['%s_%s' % (pk_, sk)] = m
        print('stress', pk_, sk, json.dumps({k: m[k] for k in ('return_pct', 'max_dd_pct', 'trades', 'pf')}, ensure_ascii=False), flush=True)
# BTC 同期間的三等分漲跌(只當背景,不參與任何選擇)
import app as A
A.CCXT_AVAILABLE = True
btc = {r[0]: r[4] for r in A.fetch_data('BTC/USDT', '2025-04-01', interval='1d')}
def btc_at(t):
    k = max(x for x in btc if x <= t); return btc[k]
out['btc_thirds'] = {}
for pk_, (plabel, T0) in PERIODS.items():
    b = [T0 + (T1 - T0) * i // 3 for i in range(4)]; out['btc_thirds'][pk_] = [{'from': S_(b[i]), 'to': S_(b[i + 1]), 'btc_pct': round((btc_at(b[i + 1]) / btc_at(b[i]) - 1) * 100, 1)} for i in range(3)]
json.dump(out, open(os.path.join(HERE, 'results', 'scenarios.json'), 'w'), ensure_ascii=False, indent=1)
