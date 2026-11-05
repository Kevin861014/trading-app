# -*- coding: utf-8 -*-
"""C1.1:現有 calc_adx vs 教科書 Wilder ADX,用 snapshots/ 的真實 OHLC 離線比較(不連網,不改任何既有程式)。

輸出 adx_compare.json 與 adx_compare.md。
"""
import glob, json, os, random, sys, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); os.chdir(ROOT)
import adx_reference as R
import app as A, sim

STEP = {'1w': 604800, '1d': 86400, '4h': 14400, '1h': 3600}
N = 14


def series(rows):
    return [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows]


def stats(xs):
    xs = sorted(xs)
    if not xs: return None
    q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]
    return {'n': len(xs), 'mean': sum(xs) / len(xs), 'median': q(.5), 'p95': q(.95), 'max': xs[-1]}


def cross_counts(a, th):
    up = dn = 0; prev = None
    for v in a:
        if v is None: continue
        if prev is not None:
            if prev < th <= v: up += 1
            elif prev >= th > v: dn += 1
        prev = v
    return up, dn


def analyse(sym, tf, rows):
    O, H, L, C = series(rows); N_ = len(C)
    pdi, mdi, wil = R.wilder_adx(H, L, C, N)
    _, _, sma = R.sma_dx_adx(H, L, C, N)
    sp, sn, sadx = sim.dmi(H, L, C, N)            # 策略實際使用的 ADX
    rec = {'symbol': sym, 'tf': tf, 'bars': N_}
    # 1) 參考實作 == 策略用的 sim.dmi ?
    d = [abs(a - b) for a, b in zip(wil, sadx) if a is not None and b is not None]
    rec['ref_vs_sim.dmi_maxdiff'] = max(d) if d else None
    rec['ref_vs_sim.dmi_none_mismatch'] = sum((a is None) != (b is None) for a, b in zip(wil, sadx))
    rec['sim_first_adx_idx'] = next(i for i, v in enumerate(sadx) if v is not None); rec['ref_first_adx_idx'] = next(i for i, v in enumerate(wil) if v is not None)
    dd = lambda lo, hi: max([abs(wil[t] - sadx[t]) for t in range(lo, min(hi, N_)) if wil[t] is not None and sadx[t] is not None] or [0.0])
    rec['sim_vs_ref_maxdiff_by_range'] = {'28-59': dd(28, 60), '60-99': dd(60, 100), '100-149': dd(100, 150), '150+': dd(150, N_)}
    # 2) 參考的 SMA 版 == calc_adx ? (最後一根 + 隨機前綴)
    ca = A.calc_adx(rows)
    rec['site_last'] = ca
    rec['ref_sma_last'] = round(sma[-1], 1); rec['wilder_last'] = round(wil[-1], 1)
    rec['calc_adx_equals_sma_ref'] = (ca['adx'] == round(sma[-1], 1))
    random.seed(7); ok = True
    for t in random.sample(range(2 * N + 5, N_), min(25, N_ - 2 * N - 6)):
        c2 = A.calc_adx(rows[:t + 1])
        ok &= (c2 is not None and c2['adx'] == round(sma[t], 1) and c2['plus_di'] == round(pdi[t], 1) and c2['minus_di'] == round(mdi[t], 1))
    rec['calc_adx_prefix_checks_pass'] = bool(ok)
    # 3) 整段歷史差異(兩者都有值,且避開前 100 根的暖機)
    both = [t for t in range(N_) if wil[t] is not None and sma[t] is not None]
    warm = [t for t in both if t >= 100]
    rec['diff_all'] = stats([abs(sma[t] - wil[t]) for t in both]); rec['diff_warm'] = stats([abs(sma[t] - wil[t]) for t in warm])
    rec['signed_mean_sma_minus_wilder'] = sum(sma[t] - wil[t] for t in warm) / len(warm) if warm else None
    # 4) 門檻跨越與分類
    rec['cross25'] = {'wilder': cross_counts([wil[t] for t in warm], 25), 'sma': cross_counts([sma[t] for t in warm], 25)}
    rec['cross20'] = {'wilder': cross_counts([wil[t] for t in warm], 20), 'sma': cross_counts([sma[t] for t in warm], 20)}
    lab = lambda a, t: R.classify(a[t], pdi[t], mdi[t])
    code = lambda l: {'上升趨勢': 'up', '下降趨勢': 'down', '盤整': 'range', '趨勢轉換中': 'range'}.get(l)
    diff_label = [t for t in warm if lab(sma, t) != lab(wil, t)]
    diff_code = [t for t in warm if code(lab(sma, t)) != code(lab(wil, t))]
    rec['label_changed_pct'] = 100.0 * len(diff_label) / len(warm) if warm else None
    rec['code_changed_pct'] = 100.0 * len(diff_code) / len(warm) if warm else None
    dist = lambda a: {k: sum(lab(a, t) == k for t in warm) for k in ('上升趨勢', '下降趨勢', '盤整', '趨勢轉換中')}
    rec['label_dist'] = {'wilder': dist(wil), 'sma': dist(sma)}
    # 5) 假設性:如果策略條件改用 SMA 版,各策略門檻條件有幾 % 的 K 棒會變(實際上策略已用 sim.dmi,不受影響)
    cond = {'diadx adx>20': lambda a, t: a[t] > 20, 'adx_di adx>=25': lambda a, t: a[t] >= 25, 'ema50_200_adx adx>25': lambda a, t: a[t] > 25,
            'holy_grail adx>30': lambda a, t: a[t] > 30, 'adx_di_trend >25 且上升': lambda a, t: a[t] > 25 and a[t - 1] is not None and a[t] > a[t - 1]}
    rec['hypothetical_condition_flip_pct'] = {k: 100.0 * sum(f(sma, t) != f(wil, t) for t in warm) / len(warm) for k, f in cond.items()} if warm else None
    # 6) 網站實際看到的最後一個數字:market_character 只抓 120 日曆天;其他地方用整段
    if tf != '1w':
        cut = rows[-1][0] - 120 * 86400 * 1000
        win = [r for r in rows if r[0] >= cut]
        if len(win) >= 2 * N + 1:
            Ow, Hw, Lw, Cw = series(win)
            _, _, w2 = R.wilder_adx(Hw, Lw, Cw, N); mc = A.market_character(win)
            rec['site120d'] = {'bars': len(win), 'site_adx': mc['adx'], 'site_label': mc['label'], 'wilder_same_window': round(w2[-1], 1), 'wilder_full_history': round(wil[-1], 1),
                               'label_wilder_same_window': R.classify(w2[-1], *[x[-1] for x in R.di_dx(Hw, Lw, Cw, N)[:2]])}
    # 7) pandas ewm 簡寫版(C1 驗證時的對照)
    _, _, pe = R.pandas_ewm_adx(H, L, C, N)
    rec['pandas_ewm_last'] = round(pe[-1], 1)
    rec['pandas_vs_wilder_last_diff'] = round(pe[-1] - wil[-1], 2)
    return rec


def main():
    rows_all = []
    for f in sorted(glob.glob(os.path.join(HERE, 'snapshots', '*.json'))):
        d = json.load(open(f)); rows_all.append(analyse(d['symbol'], d['tf'], d['rows']))
        print(d['symbol'], d['tf'], 'done', flush=True)
    json.dump(rows_all, open(os.path.join(HERE, 'adx_compare.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    f1 = lambda x: '—' if x is None else '%.1f' % x
    out = ['# C1.1 ADX 比較(現有 calc_adx vs 教科書 Wilder)', '', '資料:snapshots/ 的真實 OHLC(與網站同一取得路徑與起算日)。「暖機後」=略過前 100 根。', '',
           '## A. 整段歷史差異與分類改變', '', '| 標的 | 週期 | 根數 | 最後一根:現有 / Wilder | 暖機後 |差|平均 / 中位 / p95 / 最大 | 現有−Wilder 平均 | 市場性格改變(4 類) | 改變(上/下/盤整 3 類) | 跨 25 次數 Wilder↑↓ / 現有↑↓ | 跨 20 次數 Wilder↑↓ / 現有↑↓ |', '|---|---|---|---|---|---|---|---|---|---|']
    for r in rows_all:
        dw = r['diff_warm'] or {}
        out.append('| %s | %s | %d | %s / %s | %s / %s / %s / %s | %+.2f | %s%% | %s%% | %s / %s | %s / %s |' % (
            r['symbol'], r['tf'], r['bars'], f1(r['site_last']['adx']), f1(r['wilder_last']), f1(dw.get('mean')), f1(dw.get('median')), f1(dw.get('p95')), f1(dw.get('max')),
            r['signed_mean_sma_minus_wilder'] or 0, f1(r['label_changed_pct']), f1(r['code_changed_pct']),
            '%d↑%d↓' % tuple(r['cross25']['wilder']), '%d↑%d↓' % tuple(r['cross25']['sma']), '%d↑%d↓' % tuple(r['cross20']['wilder']), '%d↑%d↓' % tuple(r['cross20']['sma'])))
    out += ['', '## B. 網站實際看到的數字(market_character 只抓 120 日曆天)', '', '| 標的 | 週期 | 根數 | 網站 ADX / 標籤 | 同窗口改用 Wilder | Wilder(整段歷史) | 同窗口 Wilder 的標籤 |', '|---|---|---|---|---|---|---|']
    for r in rows_all:
        s = r.get('site120d')
        if s: out.append('| %s | %s | %d | %s / %s | %s | %s | %s |' % (r['symbol'], r['tf'], s['bars'], f1(s['site_adx']), s['site_label'], f1(s['wilder_same_window']), f1(s['wilder_full_history']), s['label_wilder_same_window']))
    out += ['', '## C. 確認公式關係', '', '| 標的 | 週期 | 策略用 sim.dmi 與教科書 Wilder 的最大差:第 28-59 / 60-99 / 100-149 / 150+ 根 | sim.dmi 第一個 ADX 的索引(教科書 = 27) | 參考 SMA 版 == calc_adx(最後一根/25 個前綴) | pandas ewm 簡寫版最後一根 | 與 Wilder 差 |', '|---|---|---|---|---|---|---|']
    for r in rows_all:
        m = r['sim_vs_ref_maxdiff_by_range']
        out.append('| %s | %s | %.2f / %.2f / %.3f / %.1e | %d | %s / %s | %s | %+.2f |' % (r['symbol'], r['tf'], m['28-59'], m['60-99'], m['100-149'], m['150+'], r['sim_first_adx_idx'], r['calc_adx_equals_sma_ref'], r['calc_adx_prefix_checks_pass'], f1(r['pandas_ewm_last']), r['pandas_vs_wilder_last_diff']))
    out += ['', '## D. 假設性:若策略條件改用現有(SMA)版,條件成立與否改變的 K 棒比例(實際上策略用 sim.dmi,不受影響)', '', '| 標的 | 週期 | ' + ' | '.join(next(iter(rows_all))['hypothetical_condition_flip_pct'].keys()) + ' |', '|---|---|---|---|---|---|---|']
    for r in rows_all:
        h = r['hypothetical_condition_flip_pct']
        if h: out.append('| %s | %s | %s |' % (r['symbol'], r['tf'], ' | '.join('%.1f%%' % v for v in h.values())))
    open(os.path.join(HERE, 'adx_compare.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    # 彙總
    tot = sum(r['bars'] for r in rows_all)
    w = [r for r in rows_all if r['label_changed_pct'] is not None]
    print('series', len(rows_all), 'bars', tot, 'avg label change %.1f%%' % (sum(r['label_changed_pct'] for r in w) / len(w)), 'avg code change %.1f%%' % (sum(r['code_changed_pct'] for r in w) / len(w)))


main()
