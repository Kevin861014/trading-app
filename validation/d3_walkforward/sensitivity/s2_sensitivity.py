# -*- coding: utf-8 -*-
"""D3 異常 4H 棒敏感度測試 步驟 2(資料敏感度分析,替代資料不是『正確版本』,也不是獨立 OOS)。
- 正式 D3 檔案完全不動:long.pkl、signals_long.pkl、results/walkforward.json 都只讀;替代資料只存在記憶體,結果寫到本資料夾 results/。
- 情境 A:官方原始 4H(= 現有 long.pkl)。情境 B':只把 s1 判定 VERIFIED 的 74 根異常 4H 棒,換成『同時間四根官方 1H 依 OHLCV 規則聚合』的 4H。其他所有 K 棒、1H、資金費率、成本、期間、資金、模擬器、方案(A=現行全部、B=不含 TRX/XRP 1H)完全沿用 D3 固定設定。
- 訊號:替換棒落在 400 根視窗內的訊號才重算(i ∈ [j, j+399]);其餘沿用原訊號。重算前先對原資料做同樣的重算並與 signals_long.pkl 比對,證明重算流程可重現。
- 先用原資料跑出 D3 結果並逐項比對 results/walkforward.json,證明這個測試框架本身重現正式結果。"""
import bisect, collections, copy, datetime, json, os, pickle, sys, time, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); D3 = os.path.dirname(HERE); RES = os.path.join(HERE, 'results'); ROOT = os.path.dirname(os.path.dirname(D3))
sys.path.insert(0, os.path.join(ROOT, 'validation', 'd2_portfolio')); sys.path.insert(0, D3); sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
import d2_sim as S
from d2_common import cfg_combos, exit_params
from d3_config import *
import app as A, sim

HOUR = S.HOUR; WIN = 400
S_ = lambda t: datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')
long0 = pickle.load(open(os.path.join(D3, 'raw', 'long.pkl'), 'rb')); sigs0 = pickle.load(open(os.path.join(D3, 'raw', 'signals_long.pkl'), 'rb'))
formal = json.load(open(os.path.join(D3, 'results', 'walkforward.json'), encoding='utf-8'))
EX = exit_params(); C_ = cfg_combos('config.portfolio.json'); ONE_H = set(ONE_H)
bars = [b for b in json.load(open(os.path.join(RES, 's1_bars.json'), encoding='utf-8'))['bars'] if b['status'] == 'VERIFIED']
print('verified abnormal bars to replace:', len(bars), flush=True)

# ---------- 建立替代資料(記憶體內) ----------
long1 = {'candles': {k: [list(r) for r in v] for k, v in long0['candles'].items()}, 'funding': long0['funding'], 'markets': long0['markets'], 'fetched_at': long0['fetched_at']}
rep_idx = collections.defaultdict(list); rep_info = []
for b in bars:
    s, t = b['sym'], b['t']; r1 = {r[0]: r for r in long0['candles'][(s, '1h')]}; parts = [r1[t + i * HOUR] for i in range(4)]
    new = [t, parts[0][1], max(p[2] for p in parts), min(p[3] for p in parts), parts[3][4], sum(p[5] for p in parts)]
    rows = long1['candles'][(s, '4h')]; j = next(i for i, r in enumerate(rows) if r[0] == t); old = list(rows[j]); rows[j] = new; rep_idx[s].append(j)
    rep_info.append({'sym': s, 'utc': b['utc'], 'old': old[1:], 'new': new[1:]})
assert sum(len(v) for v in rep_idx.values()) == len(bars)


# ---------- 訊號重算(與 d2_signals.work 相同邏輯,但只重算受影響視窗) ----------
def sig_at(rows, i, strat, tf):
    w = rows[i - WIN + 1:i + 1]; O = [r[1] for r in w]; H = [r[2] for r in w]; L = [r[3] for r in w]; C = [r[4] for r in w]; V = [(r[5] if len(r) > 5 else 0.0) for r in w]
    try: res = A.STRATS[strat]['build'](O, H, L, C, V, tf); el, xl = res[0], res[1]
    except Exception: return None
    return (bool(el[-1]), bool(xl[-1]), sim.atr(H, L, C, 14)[-1])


def affected_idx(idx_list, n):
    s = set()
    for j in idx_list: s.update(range(max(j, WIN - 1), min(j + WIN, n)))
    return sorted(s)


sigs1 = {k: dict(v) for k, v in sigs0.items()}; repro = {'checked': 0, 'equal': 0, 'diff_examples': []}; sigdiff = {}; t0 = time.time()
for c in C_:
    if c['timeframe'] != '4h' or c['symbol'] not in rep_idx: continue
    key = (c['symbol'], c['timeframe'], c['strategy']); rows0 = long0['candles'][(c['symbol'], '4h')]; rows1 = long1['candles'][(c['symbol'], '4h')]; idxs = affected_idx(rep_idx[c['symbol']], len(rows0))
    for i in idxs:
        ts = rows0[i][0]; o = sig_at(rows0, i, c['strategy'], '4h'); orig = sigs0[key].get(ts)
        repro['checked'] += 1
        same = (o is None and orig is None) or (o is not None and orig is not None and o[0] == orig[0] and o[1] == orig[1] and abs(o[2] - orig[2]) <= 1e-9 * max(1.0, abs(orig[2])))
        if same: repro['equal'] += 1
        elif len(repro['diff_examples']) < 3: repro['diff_examples'].append((key, S_(ts), o, orig))
        n = sig_at(rows1, i, c['strategy'], '4h')
        if n is None: sigs1[key].pop(ts, None)
        else: sigs1[key][ts] = n
    d_el = d_xl = d_atr = 0
    for ts in set(sigs0[key]) | set(sigs1[key]):
        a, b = sigs0[key].get(ts), sigs1[key].get(ts)
        if a == b: continue
        if a is None or b is None: d_el += 1; continue
        if a[0] != b[0]: d_el += 1
        if a[1] != b[1]: d_xl += 1
        if a[0] == b[0] and a[1] == b[1] and a[2] != b[2]: d_atr += 1
    sigdiff['%s|%s|%s' % key] = {'recomputed_windows': len(idxs), 'entry_signal_changed_bars': d_el, 'exit_signal_changed_bars': d_xl, 'atr_only_changed_bars': d_atr}
print('signal recompute: %.0fs; reproduction of formal signals on affected windows: %d/%d equal' % (time.time() - t0, repro['equal'], repro['checked']), flush=True)

# ---------- 與 d3_run.py 相同的模擬與指標(逐字照抄,只改成可對任一份資料執行) ----------
NOW = long0['candles'][('TRX/USDT', '1h')][-1][0] + HOUR
BL = [(c, n, a, (b if b is not None else NOW)) for c, n, a, b in BLOCKS]


def metrics(res):
    tr = res['trades']; mk = res['marks']; nets = [t['net'] for t in tr]
    eq = np.array([e for _, e, *_ in mk]); pk = np.maximum.accumulate(eq); dd = (eq - pk) / pk
    pos = sum(x for x in nets if x > 0); neg = -sum(x for x in nets if x < 0)
    day = collections.OrderedDict()
    for h, e, *_ in mk: day[datetime.datetime.fromtimestamp(h / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')] = e
    dv = list(day.values()); dchg = np.diff(dv) if len(dv) > 1 else np.array([0.0])
    return {'return_pct': round((res['equity_end'] / INIT - 1) * 100, 2), 'max_dd_pct': round(float(dd.min() * 100), 2), 'worst_day_usd': round(float(dchg.min()), 2), 'trades': len(tr), 'pf': round(pos / neg, 2) if neg > 0 else None, 'net_closed': round(sum(nets), 2)}


def run_set(long, sigs):
    M = S.Market(long); bt = long['candles'][('BTC/USDT', '4h')]; bt_ts = [r[0] for r in bt]; bt_c = [r[4] for r in bt]
    btc_at = lambda t: bt_c[max(0, bisect.bisect_right(bt_ts, t) - 1)]
    def one(T0, T1, restrict): return S.run(M, sigs, [(T0, [c for c in C_ if restrict(c['symbol'])])], T0, T1, S.default_params(EX, **PB), INIT)
    out = {'blocks': [], 'trades': {}}
    for cls, name, T0, T1 in BL:
        rA = one(T0, T1, lambda s: True); rB = one(T0, T1, lambda s: s not in ONE_H)
        pct = round((btc_at(T1) / btc_at(T0) - 1) * 100, 1)
        out['blocks'].append({'class': cls, 'name': name, 'btc_pct': pct, 'btc_regime': btc_regime(pct), 'A': metrics(rA), 'B': metrics(rB)})
        out['trades'][name] = {'A': sorted((t['key'], t['entry_ts'], t['exit_ts']) for t in rA['trades']), 'B': sorted((t['key'], t['entry_ts'], t['exit_ts']) for t in rB['trades'])}
    out['continuous'] = {}
    for cls, T0, T1 in (('I', ms(2021, 1, 1), ms(2023, 7, 1)), ('X', ms(2024, 3, 1), ms(2026, 10, 29))):
        rA = one(T0, T1, lambda s: True); rB = one(T0, T1, lambda s: s not in ONE_H)
        out['continuous'][cls] = {'A': metrics(rA), 'B': metrics(rB)}; out['trades']['cont_' + cls] = {'A': sorted((t['key'], t['entry_ts'], t['exit_ts']) for t in rA['trades']), 'B': sorted((t['key'], t['entry_ts'], t['exit_ts']) for t in rB['trades'])}
    return out


t0 = time.time(); base = run_set(long0, sigs0); print('baseline run %.0fs' % (time.time() - t0), flush=True)
# 1) 重現正式結果
mism = []
for b, fb in zip(base['blocks'], formal['blocks']):
    for sc in ('A', 'B'):
        for k in ('return_pct', 'max_dd_pct', 'worst_day_usd', 'trades', 'pf'):
            if b[sc][k] != fb[sc][k]: mism.append((b['name'], sc, k, b[sc][k], fb[sc][k]))
for cls in ('I', 'X'):
    for sc in ('A', 'B'):
        for k in ('return_pct', 'max_dd_pct', 'trades', 'pf'):
            if base['continuous'][cls][sc][k] != formal['continuous'][cls][sc][k]: mism.append(('cont_' + cls, sc, k, base['continuous'][cls][sc][k], formal['continuous'][cls][sc][k]))
print('BASELINE REPRODUCES FORMAL walkforward.json:', 'YES (all compared fields equal)' if not mism else 'NO %s' % mism[:5], flush=True)
t0 = time.time(); var = run_set(long1, sigs1); print('variant run %.0fs' % (time.time() - t0), flush=True)


# ---------- 比較 ----------
def count(res):
    hist = [b for b in res['blocks'] if b['class'] != 'T']
    return {'blocks_hist': len(hist), 'B_dd_smaller': sum(1 for b in hist if b['B']['max_dd_pct'] > b['A']['max_dd_pct']), 'B_return_higher': sum(1 for b in hist if b['B']['return_pct'] > b['A']['return_pct']),
            'B_worst_day_smaller': sum(1 for b in hist if b['B']['worst_day_usd'] > b['A']['worst_day_usd']),
            'by_class': {cl: {'n': sum(1 for b in hist if b['class'] == cl), 'B_dd_smaller': sum(1 for b in hist if b['class'] == cl and b['B']['max_dd_pct'] > b['A']['max_dd_pct'])} for cl in 'IGX'}}
rows = []
for b0, b1 in zip(base['blocks'], var['blocks']):
    r = {'class': b0['class'], 'name': b0['name'], 'btc_regime_same': b0['btc_regime'] == b1['btc_regime']}
    for sc in ('A', 'B'):
        t0_, t1_ = set(base['trades'][b0['name']][sc]), set(var['trades'][b0['name']][sc])
        r[sc] = {'orig': b0[sc], 'alt': b1[sc], 'trades_only_in_orig': len(t0_ - t1_), 'trades_only_in_alt': len(t1_ - t0_)}
    rows.append(r)
res = {'replaced_bars': len(bars), 'replaced_detail': rep_info, 'signal_diff_by_combo': sigdiff, 'signal_recompute_reproduction': {k: v for k, v in repro.items()}, 'baseline_reproduces_formal': not mism, 'blocks': rows,
       'counts_orig': count(base), 'counts_alt': count(var), 'continuous': {cl: {sc: {'orig': base['continuous'][cl][sc], 'alt': var['continuous'][cl][sc], 'trades_only_in_orig': len(set(base['trades']['cont_' + cl][sc]) - set(var['trades']['cont_' + cl][sc])), 'trades_only_in_alt': len(set(var['trades']['cont_' + cl][sc]) - set(base['trades']['cont_' + cl][sc]))} for sc in ('A', 'B')} for cl in ('I', 'X')}}
json.dump(res, open(os.path.join(RES, 's2_sensitivity.json'), 'w'), ensure_ascii=False, indent=1, default=str)
print('\ncounts orig', res['counts_orig']); print('counts alt ', res['counts_alt'])
for r in rows:
    print('%-14s A ret %7.2f->%7.2f dd %7.2f->%7.2f tr %4d->%4d pf %s->%s | B ret %7.2f->%7.2f dd %7.2f->%7.2f tr %4d->%4d | diffTrades A -%d/+%d B -%d/+%d' % (r['name'], r['A']['orig']['return_pct'], r['A']['alt']['return_pct'], r['A']['orig']['max_dd_pct'], r['A']['alt']['max_dd_pct'], r['A']['orig']['trades'], r['A']['alt']['trades'], r['A']['orig']['pf'], r['A']['alt']['pf'],
          r['B']['orig']['return_pct'], r['B']['alt']['return_pct'], r['B']['orig']['max_dd_pct'], r['B']['alt']['max_dd_pct'], r['B']['orig']['trades'], r['B']['alt']['trades'], r['A']['trades_only_in_orig'], r['A']['trades_only_in_alt'], r['B']['trades_only_in_orig'], r['B']['trades_only_in_alt']))
