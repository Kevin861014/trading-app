# -*- coding: utf-8 -*-
"""C1.1 第二部分:策略用 ADX(sim.dmi)暖機問題研究。離線重播 snapshots.json,只在記憶體暫時替換 sim.dmi。

usage: python warmup_study.py <section> [...]     section: causality | startdate | strategies | ranking | chz
輸出 results_<section>.json
"""
import bisect, datetime, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from warmup_common import *

SNAPD = load_snap()['rows']
SERIES = [('BTC/USDT', '4h'), ('SOL/USDT', '4h'), ('CHZ/USDT', '4h'), ('2330.TW', '1d'), ('AAPL', '1d'), ('NVDA', '1d')]
DAYS = 730
WS = FIXED_NOW - datetime.timedelta(days=DAYS)
WS_MS = int(WS.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
OUT = os.path.dirname(os.path.abspath(__file__))


def rows_of(sym, tf): return SNAPD['%s|%s' % (sym, tf)]


def dump(name, obj): json.dump(obj, open(os.path.join(OUT, 'results_%s.json' % name), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)


def differ(a, b):
    if a is None or b is None: return (a is None) != (b is None)
    return abs(a - b) > 1e-9


# ───────── 1) 因果性(任一時間點只能用當時與過去的 K 棒):前綴 vs 全段 ─────────
def causality():
    LENS = [20, 28, 30, 35, 40, 60, 100, 150, 250, 400]
    res = {'dmi': {}, 'signals': {}}
    for sym, tf in [('BTC/USDT', '4h'), ('2330.TW', '1d'), ('CHZ/USDT', '4h')]:
        rows = rows_of(sym, tf)[:700]; H, L, C = [[r[i] for r in rows] for i in (2, 3, 4)]
        for V, F in VARIANTS.items():
            full = F(H, L, C); bad = {}; first_bad = {}
            for Ln in LENS:
                part = F(H[:Ln], L[:Ln], C[:Ln]); n = 0; idx = []
                for t in range(Ln):
                    if any(differ(part[j][t], full[j][t]) for j in range(3)): n += 1; idx.append(t)
                bad[Ln] = n
                if idx: first_bad[Ln] = [idx[0], idx[-1]]
            res['dmi']['%s %s %s' % (sym, tf, V)] = {'violations_by_prefix_len': bad, 'bad_index_range': first_bad}
        for key in ADX_STRATS:
            for V in VARIANTS:
                with use(V):
                    fa = build(key, rows, tf); n = 0
                    for Ln in LENS:
                        pa = build(key, rows[:Ln], tf)
                        n += sum(1 for t in range(Ln) if bool(pa[0][t]) != bool(fa[0][t]) or bool(pa[1][t]) != bool(fa[1][t]))
                res['signals']['%s %s %s %s' % (sym, tf, key, V)] = n
    dump('causality', res); return res


# ───────── 共用:用 app 的同一套函式算「正式窗口」指標 ─────────
def window_metrics(rows, strat, sym, tf):
    ck = A.cost_kwargs(sym, strat)
    split = A.is_oos_split(rows, WS, FIXED_NOW)
    res = A.run_backtest(rows, strategy=strat, risk_pct=0.015, timeframe=tf, **ck)
    if not res: return None
    dates, equity, st = res; tlog = st.get('trade_log', [])
    full_t = [t for t in tlog if not t.get('open') and t.get('entry_date') and t['entry_date'] >= WS]
    out = {'full': A._perf_block(full_t, dates, equity, WS), 'entries': [t['entry_date'].strftime('%Y-%m-%d %H:%M') for t in full_t]}
    if split:
        _, oos_t, carry, _ = A.partition_trades(tlog, WS, split['boundary_dt'])
        out['oos'] = A._perf_block(oos_t, dates, equity, split['boundary_dt'])
        rd = rows[:split['idx_b']]; r2 = A.run_backtest(rd, strategy=strat, risk_pct=0.015, timeframe=tf, **ck)
        if r2:
            d2, e2, s2 = r2; is_t = [t for t in s2.get('trade_log', []) if not t.get('open') and t.get('entry_date') and t['entry_date'] >= WS]
            out['is'] = A._perf_block(is_t, d2, e2, WS)
    return out


def sig_window(key, rows, tf, V):
    with use(V): el, xl = build(key, rows, tf)[:2]
    return {rows[i][0]: (bool(el[i]), bool(xl[i])) for i in range(len(rows)) if rows[i][0] >= WS_MS}


# ───────── 2) 歷史資料起始日期是否影響正式窗口內的訊號 ─────────
def startdate():
    OFFS = [0, 50, 200, 400]; res = []
    for sym, tf in SERIES:
        rows = rows_of(sym, tf)
        for key in ADX_STRATS:
            for V in ('A', 'B', 'C100'):
                base_sig = sig_window(key, rows, tf, V); base_m = window_metrics(rows, key, sym, tf) if V else None
                with use(V): base_m = window_metrics(rows, key, sym, tf)
                for k in OFFS[1:]:
                    sg = sig_window(key, rows[k:], tf, V)
                    flips = sum(1 for t, v in base_sig.items() if sg.get(t) != v)
                    with use(V): m = window_metrics(rows[k:], key, sym, tf)
                    res.append({'symbol': sym, 'tf': tf, 'strategy': key, 'variant': V, 'drop_first_bars': k, 'window_signal_flips': flips,
                                'trades_base': base_m['full']['trades'] if base_m else None, 'trades_k': m['full']['trades'] if m else None,
                                'pf_base': base_m['full']['pf'] if base_m else None, 'pf_k': m['full']['pf'] if m else None,
                                'entries_identical': (base_m or {}).get('entries') == (m or {}).get('entries')})
        print('startdate', sym, tf, flush=True)
    dump('startdate', res); return res


# ───────── 4) 六個策略各自受多少影響(正式窗口,A vs B vs C) ─────────
def strategies():
    VS = ['A', 'B', 'C27', 'C100', 'C200']; res = []
    for sym, tf in SERIES:
        rows = rows_of(sym, tf)
        for key in ADX_STRATS:
            sigs = {V: sig_window(key, rows, tf, V) for V in VS}; ms = {}
            for V in VS:
                with use(V): ms[V] = window_metrics(rows, key, sym, tf)
            r = {'symbol': sym, 'tf': tf, 'strategy': key}
            for V in VS:
                m = ms[V]; r[V] = None if not m else {'trades': m['full']['trades'], 'pf': m['full']['pf'], 'win': m['full']['win'], 'mdd': m['full']['mdd'], 'total': m['full']['total'],
                                                      'is_trades': (m.get('is') or {}).get('trades'), 'is_pf': (m.get('is') or {}).get('pf'), 'oos_trades': (m.get('oos') or {}).get('trades'), 'oos_pf': (m.get('oos') or {}).get('pf')}
                r['sigdiff_vs_A_' + V] = sum(1 for t, v in sigs['A'].items() if sigs[V].get(t) != v)
                r['entries_same_as_A_' + V] = (ms['A'] or {}).get('entries') == (ms[V] or {}).get('entries')
            res.append(r)
        print('strategies', sym, tf, flush=True)
    dump('strategies', res); return res


# ───────── 3) 暖機長度是否改變策略排名與 OOS(走真正的 /api/best_strategy) ─────────
def ranking():
    VS = ['A', 'B', 'C27', 'C100', 'C200']; out = {}
    A._utcnow = lambda: FIXED_NOW
    def fake(symbol, start, interval='1d'): return SNAPD['%s|%s' % (symbol, interval)]
    A.fetch_data = fake
    c = A.app.test_client()
    for sym, tf in SERIES:
        per = {}
        for V in VS:
            t0 = time.time()
            with use(V): j = c.get('/api/best_strategy', query_string=dict(symbol=sym, period='2y', timeframe=tf, use_oos='1')).get_json()
            per[V] = {'tested': j.get('total_tested'), 'top': [(r['strat'], r['score'], r['pf'], r['trades'], r['mdd'], r['win'], r['total'], r.get('oosStatus'), r.get('oosPf'), r.get('oosTrades'), r.get('oosTotal')) for r in j['results']]}
            print('ranking', sym, tf, V, '%.0fs' % (time.time() - t0), flush=True)
        out['%s %s' % (sym, tf)] = per
    dump('ranking', out); return out


# ───────── 5) 機器人 CHZ 4H ema50_200_adx:400 根滾動窗口 ─────────
def replay_pos(el, xl):
    pos = False
    for i in range(len(el)):
        if pos and xl[i]: pos = False
        if (not pos) and el[i]: pos = True
    return pos


def chz():
    rows = rows_of('CHZ/USDT', '4h'); N = len(rows); VS = ['A', 'B', 'C100', 'C200']; W = 400
    cnt = {V: {'last_bar_signal_diff': 0, 'last10_signal_diff': 0, 'final_pos_diff': 0, 'adx_last_maxdiff': 0.0} for V in VS if V != 'A'}
    first_idx = {}; windows = 0; cur = {}
    for e in range(W - 1, N):
        win = rows[e - W + 1:e + 1]; sg = {}
        for V in VS:
            with use(V):
                el, xl = build('ema50_200_adx', win, '4h')[:2]
                H, L, C = [[r[i] for r in win] for i in (2, 3, 4)]; adx = sim.dmi(H, L, C)[2][-1]
            sg[V] = (el, xl, adx)
        windows += 1
        for V in VS[1:]:
            a, b = sg['A'], sg[V]
            if (a[0][-1], a[1][-1]) != (b[0][-1], b[1][-1]): cnt[V]['last_bar_signal_diff'] += 1
            if any((a[0][i], a[1][i]) != (b[0][i], b[1][i]) for i in range(-10, 0)): cnt[V]['last10_signal_diff'] += 1
            if replay_pos(a[0], a[1]) != replay_pos(b[0], b[1]): cnt[V]['final_pos_diff'] += 1
            if a[2] is not None and b[2] is not None: cnt[V]['adx_last_maxdiff'] = max(cnt[V]['adx_last_maxdiff'], abs(a[2] - b[2]))
            elif (a[2] is None) != (b[2] is None): cnt[V].setdefault('adx_none_mismatch', 0); cnt[V]['adx_none_mismatch'] += 1
        if e == N - 1:
            for V in VS: cur[V] = {'adx_last': sg[V][2], 'el_last': bool(sg[V][0][-1]), 'xl_last': bool(sg[V][1][-1]), 'pos_state': replay_pos(sg[V][0], sg[V][1])}
    # 凱利種子歷史(~900 天,不含最後未收盤那根):訊號與以收盤價計的交易報酬
    seed = rows_of('CHZ/USDT', '4h|900d'); sres = {}
    for V in ['A', 'B', 'C100', 'C200']:
        with use(V): el, xl = build('ema50_200_adx', seed, '4h')[:2]
        C = [r[4] for r in seed]; rets = []; pos = False; ent = 0.0
        for i in range(len(C)):
            if pos and xl[i]: rets.append((C[i] - ent) / ent); pos = False
            if (not pos) and el[i]: pos = True; ent = C[i]
        sres[V] = {'trades': len(rets), 'rets': [round(x, 4) for x in rets[-8:]], 'el_idx': [i for i in range(len(el)) if el[i]][:5], 'n_entries': int(sum(bool(x) for x in el))}
    sd = {V: [i for i in range(len(seed)) if False] for V in VS}
    with use('A'): ela, xla = build('ema50_200_adx', seed, '4h')[:2]
    with use('B'): elb, xlb = build('ema50_200_adx', seed, '4h')[:2]
    seed_diff = [i for i in range(len(seed)) if (bool(ela[i]), bool(xla[i])) != (bool(elb[i]), bool(xlb[i]))]
    out = {'windows_400': windows, 'counts_vs_A': cnt, 'current_window': cur, 'seed_900d': sres, 'seed_signal_diff_indexes_A_vs_B': seed_diff[:30], 'seed_bars': len(seed)}
    dump('chz', out); return out


if __name__ == '__main__':
    for s in sys.argv[1:]:
        t0 = time.time(); globals()[s](); print('done', s, '%.0fs' % (time.time() - t0), flush=True)
