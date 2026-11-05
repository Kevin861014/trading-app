# -*- coding: utf-8 -*-
"""C1.1:若把策略使用的 sim.dmi 換成教科書 Wilder(只在記憶體裡暫時替換,不改任何檔案),六個用 ADX 的策略進出場訊號與回測會不會變?

1) 用執行期追蹤確認 184 個策略中,真正呼叫 sim.dmi 的有哪幾個。
2) 對 snapshots/ 的每條真實 K 線,比較『現狀 sim.dmi』與『教科書 Wilder』產生的進場/出場訊號(完整陣列逐根比對)。
3) 若訊號有差,再用同一套回測(app 的 run_backtest 路徑 → 這裡用 sim 的回測函式)比較交易筆數、PF、報酬。
"""
import glob, json, os, sys, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); os.chdir(ROOT)
import adx_reference as R
import app as A, sim

ADX_USERS = ['diadx', 'ema50_200_adx', 'adx_di', 'dmi_cross', 'adx_di_trend', 'holy_grail']
orig_dmi = sim.dmi


def wilder_dmi(H, L, C, n=14):
    return R.wilder_adx(H, L, C, n)


def build(key, O, H, L, C, V, tf):
    m = A.STRATS[key]
    try: return m['build'](O, H, L, C, V, tf)
    except TypeError: return m['build'](O, H, L, C, V)


def tlog_of(key, rows, sig, tf):
    T = [r[0] for r in rows]; O, H, L, C = [[r[i] for r in rows] for i in (1, 2, 3, 4)]
    Aatr = sim.atr(H, L, C, 14); st = A.STRATS[key]
    el, xl = sig[0], sig[1]
    if st.get('pyramid'):
        pp = st['pyramid']; return sim._simulate_pyramid(T, O, H, L, C, el, Aatr, pp['init_atr'], pp['trail_atr'], pp['add_atr'], pp['max_adds'], 0.015, 3.0, 10000.0)[3]
    return sim._simulate(T, O, H, L, C, el, xl, Aatr, st.get('atr_stop', 0), st.get('atr_trail', 0), st.get('atr_tp', 0), 0.015, 3.0, 10000.0, st.get('pct_stop', 0.0), st.get('pct_trail', 0.0), st.get('pct_tp', 0.0))[3]


def trades(key, rows, sig, tf):
    return [(t.get('entry_i'), t.get('exit_i')) for t in tlog_of(key, rows, sig, tf)]


def main():
    # 1) 追蹤:哪些策略會呼叫 sim.dmi
    calls = {'n': 0}
    def traced(*a, **k): calls['n'] += 1; return orig_dmi(*a, **k)
    sim.dmi = traced
    d0 = json.load(open(glob.glob(os.path.join(HERE, 'snapshots', 'BTC-USDT_1d.json'))[0]))['rows']
    O, H, L, C, V = [[r[i] for r in d0] for i in (1, 2, 3, 4, 5)]
    users = []
    for k, m in A.STRATS.items():
        b = calls['n']; build(k, O, H, L, C, V, '1d')
        if calls['n'] > b: users.append(k)
    sim.dmi = orig_dmi
    assert sorted(users) == sorted(ADX_USERS), users
    out = {'total_strategies': len(A.STRATS), 'adx_users': users, 'rows': []}
    for f in sorted(glob.glob(os.path.join(HERE, 'snapshots', '*.json'))):
        d = json.load(open(f)); rows = d['rows']; tf = d['tf']
        O, H, L, C, V = [[r[i] for r in rows] for i in (1, 2, 3, 4, 5)]
        for k in ADX_USERS:
            sim.dmi = orig_dmi; a = build(k, O, H, L, C, V, tf)
            sim.dmi = wilder_dmi; b = build(k, O, H, L, C, V, tf)
            sim.dmi = orig_dmi
            el_a, xl_a = a[0], a[1]; el_b, xl_b = b[0], b[1]
            de = [i for i in range(len(C)) if bool(el_a[i]) != bool(el_b[i])]
            dx = [i for i in range(len(C)) if bool(xl_a[i]) != bool(xl_b[i])]
            tl_a = trades(k, rows, a, tf); tl_b = trades(k, rows, b, tf)
            out['rows'].append({'trades_now': len(tl_a), 'trades_wilder': len(tl_b), 'trade_list_identical': tl_a == tl_b, 'pf_now': A.calc_pf(tlog_of(k, rows, a, tf)), 'pf_wilder': A.calc_pf(tlog_of(k, rows, b, tf)),
                                'symbol': d['symbol'], 'tf': tf, 'strategy': k, 'bars': len(C), 'entries_now': int(sum(bool(x) for x in el_a)), 'entries_wilder': int(sum(bool(x) for x in el_b)),
                                'entry_diff_bars': len(de), 'exit_diff_bars': len(dx), 'first_diff_idx': (min(de + dx) if (de or dx) else None), 'last_diff_idx': (max(de + dx) if (de or dx) else None)})
    json.dump(out, open(os.path.join(HERE, 'strategy_impact.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    rows = out['rows']; nd = [r for r in rows if r['entry_diff_bars'] or r['exit_diff_bars']]
    md = ['# C1.1 策略影響(暫時把 sim.dmi 換成教科書 Wilder,逐根比對訊號)', '', '184 個策略中呼叫 sim.dmi 的只有 %d 個:%s' % (len(users), '、'.join(users)), '',
          '比較組合:%d 條真實 K 線 × %d 策略 = %d 組;訊號有差異的組合:%d 組。' % (len(rows) // len(ADX_USERS), len(ADX_USERS), len(rows), len(nd)), '',
          '| 標的 | 週期 | 策略 | 根數 | 進場數(現狀 / Wilder) | 進場差異根數 | 出場差異根數 | 差異出現的 K 棒索引(最早 ~ 最晚) | 完整回測的交易筆數(現狀 / Wilder) | 交易清單相同 | PF(現狀 / Wilder) |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in nd: md.append('| %s | %s | %s | %d | %d / %d | %d | %d | %s ~ %s | %d / %d | %s | %s / %s |' % (r['symbol'], r['tf'], r['strategy'], r['bars'], r['entries_now'], r['entries_wilder'], r['entry_diff_bars'], r['exit_diff_bars'], r['first_diff_idx'], r['last_diff_idx'], r['trades_now'], r['trades_wilder'], '是' if r['trade_list_identical'] else '否', r['pf_now'], r['pf_wilder']))
    if not nd: md.append('| (無) | | | | | | | |')
    open(os.path.join(HERE, 'strategy_impact.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('combos', len(rows), 'with diff', len(nd)); print('\n'.join(md))


main()
