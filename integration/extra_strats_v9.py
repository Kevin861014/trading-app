# -*- coding: utf-8 -*-
"""外人教科書策略 v9（參數凍結，禁止依場外改 lookback）。

【參數凍結聲明】以下所有參數在 2026-08-17 開跑前寫死，**不是**看完幣安
回測結果再發明或再調。回測結果不理想也不回頭改 lookback／門檻／持有根數，
只在報告中註明失敗。與 sim 內建 36 碼、v1–v8 58 碼、extra_strats_loop 84 碼
（合計 178 碼）全部不重複。

【v8 教訓→本輪約束】fade（逆勢/均值回歸）家族在既有籃子已滿額 3/3
（ibs_fade、td_setup9、psy_line），v9 **不寫逆勢策略**；優先 trend_quality、
volume、cycle、candle（非逆勢型）、momentum、breakout。

凍結清單（策略 code → 參數 → 文獻）：
  rsq_lrs      : R²(18) 上穿 0.27 且 LRS(18) 方向定多空；R²<0.27 或 LRS 反向出場
                 （Chande & Kroll《The New Technical Trader》1994：R² 臨界值 0.27）
  er_mom       : Kaufman Efficiency Ratio(10) 上穿 0.5 且 10 根漲跌定方向；ER<0.3 出
                 （Kaufman《Trading Systems and Methods》：ER 趨勢效率門檻）
  se_channel   : 標準誤差通道 LinReg(21)±2SE：收盤破上軌多、破下軌空、回中軸出
                 （經典 Standard Error Channel，統計回歸通道）
  gann_hilo    : Gann HiLo Activator：C 上穿 SMA(H,10) 多、下穿 SMA(L,10) 空
                 （Gann 高低價均線趨勢線，TV 經典 HiLo）
  ssmooth_x    : Ehlers 2 極 SuperSmoother(20) 收盤交叉（非 roofing，無高通級）
                 （Ehlers《Cybernetic Analysis for Stocks and Futures》2004）
  bandpass_x   : Ehlers Bandpass(20, 帶寬 0.3) 對前一根交叉
                 （Ehlers, "The Bandpass Indicator"）
  itrend_x     : Ehlers Instantaneous Trendline α=0.07，trigger=2×IT−IT[i−2] 交叉
                 （Ehlers《Cybernetic Analysis for Stocks and Futures》2004 第 5 章）
  vo_zero      : Volume Oscillator 100×(EMA(V,5)−EMA(V,20))/EMA(V,20) 零軸交叉+K棒方向
                 （經典量擺盪，Granville 量價體系）
  vroc_surge   : VROC(14) 上穿 +50% 且 K 棒方向定多空；VROC<0 出
                 （經典 Volume Rate of Change 量能激增）
  marubozu_run : 連續 2 根同向 Marubozu（身≥85% 幅）且第 2 根收過前高/低；抱≤6 根
                 （Nison 日本蠟燭圖：Marubozu 強勢連續）
  range_leader : 中價 (H+L)/2 越過前根極值且振幅擴大、順 K 棒方向；抱≤4 根
                 （Michael Harris, Range Leader 棒, Price Action Lab）
  darvas_box   : 10 根盒頂底（HH−LL≤1.5×ATR14）收斂後收盤破盒頂多、破盒底空；回盒底/頂出
                 （Nicolas Darvas《How I Made $2,000,000 in the Stock Market》1960）

（Harami 孕線原在草稿，因屬逆勢反轉型、違反本輪「不寫 fade」約束，已刪除不測。）

build(O,H,L,C,V,tf) 回傳 (el, xl, es, xs)，對齊 v6–v8 與 fixed_stop_backtest 呼叫。
滾動工具函式自 extra_strats_v7 引用，不重複實作。
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path


def _find_unpacked() -> Path:
    here = Path(__file__).resolve().parent
    env = os.environ.get("AUTOTRADE_ROOT")
    if env and (Path(env) / "sim.py").exists():
        return Path(env)
    for cand in (here.parent / "unpacked-utf", here.parent, here):
        if (cand / "sim.py").exists():
            return cand
    return here.parent / "unpacked-utf"


UNPACKED = _find_unpacked()
if str(UNPACKED) not in sys.path:
    sys.path.insert(0, str(UNPACKED))
_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)

import sim  # noqa: E402
from extra_strats_v7 import _empty, _prefix, _roll_max, _roll_min  # noqa: E402

# ═══════════════ 凍結參數（開跑前寫死，見模組 docstring）═══════════════
R2_N, R2_LVL = 18, 0.27
ER_N, ER_UP, ER_DN = 10, 0.5, 0.3
SE_N, SE_K = 21, 2.0
GH_N = 10
SS_N = 20
BP_N, BP_BW = 20, 0.3
IT_ALPHA = 0.07
VO_F, VO_S = 5, 20
VROC_N, VROC_LVL = 14, 50.0
MARU_BODY, MARU_HOLD = 0.85, 6
RL_HOLD = 4
DARVAS_N, DARVAS_TIGHT, DARVAS_ATR = 10, 1.5, 14


# ── 指標實作 ────────────────────────────────────────────────────────
def _linreg_fit(xs, i, n):
    """xs[i-n+1..i] 對 x=0..n-1 回歸：回傳 (斜率, 在 x=n-1 的擬合值, 標準誤)。"""
    sx = n * (n - 1) / 2.0
    sxx = n * (n - 1) * (2 * n - 1) / 6.0
    sy = sxy = 0.0
    for j in range(n):
        y = xs[i - n + 1 + j]
        sy += y
        sxy += j * y
    den = n * sxx - sx * sx
    if den == 0:
        return 0.0, sy / n, 0.0
    slope = (n * sxy - sx * sy) / den
    intercept = (sy - slope * sx) / n
    fit_end = intercept + slope * (n - 1)
    sse = 0.0
    for j in range(n):
        r = xs[i - n + 1 + j] - (intercept + slope * j)
        sse += r * r
    se = math.sqrt(sse / (n - 2)) if n > 2 else 0.0
    return slope, fit_end, se


def _rsq_lrs(C, n):
    """R² 判定係數與 LRS 斜率（Chande/Kroll）。"""
    rsq, lrs = [None] * len(C), [None] * len(C)
    sx = n * (n - 1) / 2.0
    sxx = n * (n - 1) * (2 * n - 1) / 6.0
    vx = sxx / n - (sx / n) ** 2
    for i in range(n - 1, len(C)):
        win = C[i - n + 1: i + 1]
        my = sum(win) / n
        sxy = sum(j * win[j] for j in range(n))
        cov = sxy / n - (sx / n) * my
        vy = sum((y - my) ** 2 for y in win) / n
        if vx > 0 and vy > 0:
            r = cov / math.sqrt(vx * vy)
            rsq[i] = r * r
            lrs[i] = cov / vx
    return rsq, lrs


def _kaufman_er(C, n):
    out = [None] * len(C)
    dc = [abs(C[i] - C[i - 1]) if i else 0.0 for i in range(len(C))]
    acc = _prefix(dc)
    for i in range(n, len(C)):
        den = acc[i + 1] - acc[i + 1 - n]
        if den > 0:
            out[i] = abs(C[i] - C[i - n]) / den
    return out


def _supersmoother(C, n):
    a1 = math.exp(-1.414 * math.pi / n)
    b1 = 2.0 * a1 * math.cos(math.radians(1.414 * 180.0 / n))
    c2, c3 = b1, -a1 * a1
    c1 = 1.0 - c2 - c3
    out = [None] * len(C)
    f1 = f2 = 0.0
    for i in range(1, len(C)):
        f = c1 * (C[i] + C[i - 1]) / 2.0 + c2 * f1 + c3 * f2
        out[i] = f
        f2, f1 = f1, f
    return out


def _bandpass(C, n, bw):
    beta = math.cos(2.0 * math.pi / n)
    gamma = 1.0 / math.cos(2.0 * math.pi * bw / n)
    alpha = gamma - math.sqrt(gamma * gamma - 1.0)
    out = [None] * len(C)
    b1 = b2 = 0.0
    for i in range(2, len(C)):
        b = (0.5 * (1.0 - alpha) * (C[i] - C[i - 2])
             + beta * (1.0 + alpha) * b1 - alpha * b2)
        out[i] = b
        b2, b1 = b1, b
    trig = [None] * len(C)
    for i in range(1, len(C)):
        trig[i] = out[i - 1]
    return out, trig


def _itrend(C, alpha):
    N = len(C)
    it = [0.0] * N
    for i in range(N):
        if i < 7:
            it[i] = (C[i] + 2.0 * C[i - 1] + C[i - 2]) / 3.0 if i >= 2 else C[i]
        else:
            it[i] = ((alpha - alpha * alpha / 4.0) * C[i]
                     + 0.5 * alpha * alpha * C[i - 1]
                     - (alpha - 0.75 * alpha * alpha) * C[i - 2]
                     + 2.0 * (1.0 - alpha) * it[i - 1]
                     - (1.0 - alpha) ** 2 * it[i - 2])
    trig = [None] * N
    for i in range(2, N):
        trig[i] = 2.0 * it[i] - it[i - 2]
    return it, trig


def _vroc(V, n):
    vv = [(v or 0.0) for v in V]
    out = [None] * len(vv)
    for i in range(n, len(vv)):
        if vv[i - n] > 0:
            out[i] = 100.0 * (vv[i] - vv[i - n]) / vv[i - n]
    return out


# ── 訊號（el=多進, xl=多出, es=空進, xs=空出）──────────────────────────
def sig_rsq_lrs(O, H, L, C, V=None, tf=None):
    """R²(18) 上穿 0.27 進場（LRS 定方向）；R²<0.27 或 LRS 反向出場。"""
    rsq, lrs = _rsq_lrs(C, R2_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (rsq[i], rsq[i - 1], lrs[i]):
            continue
        up = rsq[i - 1] <= R2_LVL < rsq[i]
        if up and lrs[i] > 0:
            el[i] = True
        if up and lrs[i] < 0:
            es[i] = True
        if rsq[i] < R2_LVL or lrs[i] < 0:
            xl[i] = True
        if rsq[i] < R2_LVL or lrs[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_er_mom(O, H, L, C, V=None, tf=None):
    """Kaufman ER(10) 上穿 0.5 進場（10 根漲跌定方向）；ER<0.3 出場。"""
    er = _kaufman_er(C, ER_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(ER_N + 1, n):
        if er[i] is None or er[i - 1] is None:
            continue
        up = er[i - 1] <= ER_UP < er[i]
        if up and C[i] > C[i - ER_N]:
            el[i] = True
        if up and C[i] < C[i - ER_N]:
            es[i] = True
        if er[i] < ER_DN:
            xl[i] = True
            xs[i] = True
    return el, xl, es, xs


def sig_se_channel(O, H, L, C, V=None, tf=None):
    """標準誤差通道 LinReg(21)±2SE：破上軌多、破下軌空、回中軸出。"""
    n = len(C)
    mid, up, lo = [None] * n, [None] * n, [None] * n
    for i in range(SE_N - 1, n):
        slope, fit_end, se = _linreg_fit(C, i, SE_N)
        mid[i] = fit_end
        up[i] = fit_end + SE_K * se
        lo[i] = fit_end - SE_K * se
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (up[i], up[i - 1], lo[i], lo[i - 1], mid[i]):
            continue
        if C[i - 1] <= up[i - 1] and C[i] > up[i]:
            el[i] = True
        if C[i] < mid[i]:
            xl[i] = True
        if C[i - 1] >= lo[i - 1] and C[i] < lo[i]:
            es[i] = True
        if C[i] > mid[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_gann_hilo(O, H, L, C, V=None, tf=None):
    """Gann HiLo：C 上穿 SMA(H,10) 多、下穿 SMA(L,10) 空。"""
    mh = sim.sma(H, GH_N)
    ml = sim.sma(L, GH_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (mh[i], mh[i - 1], ml[i], ml[i - 1]):
            continue
        if C[i - 1] <= mh[i - 1] and C[i] > mh[i]:
            el[i] = True
        if C[i] < ml[i]:
            xl[i] = True
        if C[i - 1] >= ml[i - 1] and C[i] < ml[i]:
            es[i] = True
        if C[i] > mh[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_ssmooth_x(O, H, L, C, V=None, tf=None):
    """Ehlers 2 極 SuperSmoother(20) 收盤交叉（無高通級，非 roofing）。"""
    f = _supersmoother(C, SS_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(SS_N + 1, n):
        if f[i] is None or f[i - 1] is None:
            continue
        if C[i - 1] <= f[i - 1] and C[i] > f[i]:
            el[i] = True
        if C[i] < f[i]:
            xl[i] = True
        if C[i - 1] >= f[i - 1] and C[i] < f[i]:
            es[i] = True
        if C[i] > f[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_bandpass_x(O, H, L, C, V=None, tf=None):
    """Ehlers Bandpass(20, 帶寬0.3) 對 trigger（前一根）交叉。"""
    bp, tr = _bandpass(C, BP_N, BP_BW)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(BP_N + 1, n):
        if None in (bp[i], bp[i - 1], tr[i], tr[i - 1]):
            continue
        if bp[i - 1] <= tr[i - 1] and bp[i] > tr[i]:
            el[i] = True
        if bp[i] < tr[i]:
            xl[i] = True
        if bp[i - 1] >= tr[i - 1] and bp[i] < tr[i]:
            es[i] = True
        if bp[i] > tr[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_itrend_x(O, H, L, C, V=None, tf=None):
    """Ehlers Instantaneous Trendline(0.07)：trigger=2×IT−IT[i−2] 上穿 IT 多。"""
    it, tr = _itrend(C, IT_ALPHA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(9, n):
        if tr[i] is None or tr[i - 1] is None:
            continue
        if tr[i - 1] <= it[i - 1] and tr[i] > it[i]:
            el[i] = True
        if tr[i] < it[i]:
            xl[i] = True
        if tr[i - 1] >= it[i - 1] and tr[i] < it[i]:
            es[i] = True
        if tr[i] > it[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_vo_zero(O, H, L, C, V=None, tf=None):
    """量擺盪 VO(5,20) 零軸交叉，方向看該根漲跌。"""
    vv = [(v or 0.0) for v in (V or [0.0] * len(C))]
    ef = sim.ema(vv, VO_F)
    es_ = sim.ema(vv, VO_S)
    n = len(C)
    vo = [None] * n
    for i in range(n):
        if ef[i] is None or es_[i] in (None, 0):
            continue
        vo[i] = 100.0 * (ef[i] - es_[i]) / es_[i]
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if vo[i] is None or vo[i - 1] is None:
            continue
        if vo[i - 1] <= 0 < vo[i] and C[i] > C[i - 1]:
            el[i] = True
        if vo[i] < 0:
            xl[i] = True
        if vo[i - 1] >= 0 > vo[i] and C[i] < C[i - 1]:
            es[i] = True
        if vo[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_vroc_surge(O, H, L, C, V=None, tf=None):
    """VROC(14) 上穿 +50% 量能激增，順 K 棒方向；VROC<0 出場。"""
    vr = _vroc(V or [0.0] * len(C), VROC_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if vr[i] is None or vr[i - 1] is None:
            continue
        up = vr[i - 1] <= VROC_LVL < vr[i]
        if up and C[i] > O[i]:
            el[i] = True
        if up and C[i] < O[i]:
            es[i] = True
        if vr[i] < 0:
            xl[i] = True
            xs[i] = True
    return el, xl, es, xs


def sig_marubozu_run(O, H, L, C, V=None, tf=None):
    """連續 2 根同向 Marubozu（身≥85% 幅）且第 2 根收過前根極值；抱≤6 根。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)

    def maru(i, bull):
        rng = H[i] - L[i]
        if rng <= 0:
            return False
        body = C[i] - O[i]
        if bull:
            return body > 0 and body >= MARU_BODY * rng
        return body < 0 and -body >= MARU_BODY * rng

    for i in range(1, n):
        if maru(i, True) and maru(i - 1, True) and C[i] > H[i - 1]:
            el[i] = True
            xs[i] = True
        if maru(i, False) and maru(i - 1, False) and C[i] < L[i - 1]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_range_leader(O, H, L, C, V=None, tf=None):
    """Range Leader：中價越過前根極值且振幅擴大，順 K 棒方向；抱≤4 根。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        mid = 0.5 * (H[i] + L[i])
        rng = H[i] - L[i]
        rng1 = H[i - 1] - L[i - 1]
        if rng <= 0 or rng1 <= 0:
            continue
        if mid > H[i - 1] and rng > rng1 and C[i] > O[i]:
            el[i] = True
            xs[i] = True
        if mid < L[i - 1] and rng > rng1 and C[i] < O[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_darvas_box(O, H, L, C, V=None, tf=None):
    """Darvas 盒：10 根 HH−LL≤1.5×ATR14 收斂後，收盤破盒頂多、破盒底空。"""
    a = sim.atr(H, L, C, DARVAS_ATR)
    hh = _roll_max(H, DARVAS_N)
    ll = _roll_min(L, DARVAS_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        j = i - 1  # 盒體看前一根已完成的窗口
        if a[j] is None or hh[j] is None or ll[j] is None:
            continue
        tight = (hh[j] - ll[j]) <= DARVAS_TIGHT * a[j]
        if not tight:
            continue
        if C[i] > hh[j]:
            el[i] = True
            xs[i] = True
        if C[i] < ll[j]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


EXTRA_STRATS_V9 = {
    "rsq_lrs": {
        "name": "R²(18)>0.27 + LRS 方向",
        "family": "trend_quality",
        "speed": "mid",
        "sided": "both",
        "build": sig_rsq_lrs,
        "min_bars": R2_N + 20,
        "source": "Chande & Kroll R-squared 0.27 + LRS, New Technical Trader 1994",
    },
    "er_mom": {
        "name": "Kaufman ER(10)>0.5 動能",
        "family": "trend_quality",
        "speed": "mid",
        "sided": "both",
        "build": sig_er_mom,
        "min_bars": ER_N + 20,
        "source": "Kaufman Efficiency Ratio, Trading Systems and Methods",
    },
    "se_channel": {
        "name": "標準誤差通道(21,2SE) 突破",
        "family": "breakout",
        "speed": "mid",
        "sided": "both",
        "build": sig_se_channel,
        "min_bars": SE_N + 20,
        "source": "Classic Standard Error Channel LinReg±2SE",
    },
    "gann_hilo": {
        "name": "Gann HiLo(10) 趨勢線",
        "family": "ma",
        "speed": "mid",
        "sided": "both",
        "build": sig_gann_hilo,
        "min_bars": GH_N + 20,
        "source": "Gann HiLo Activator, SMA(high)/SMA(low) 10",
    },
    "ssmooth_x": {
        "name": "Ehlers SuperSmoother(20) 交叉",
        "family": "cycle",
        "speed": "mid",
        "sided": "both",
        "build": sig_ssmooth_x,
        "min_bars": SS_N + 20,
        "source": "Ehlers 2-pole SuperSmoother, Cybernetic Analysis 2004",
    },
    "bandpass_x": {
        "name": "Ehlers Bandpass(20,0.3) 交叉",
        "family": "cycle",
        "speed": "mid",
        "sided": "both",
        "build": sig_bandpass_x,
        "min_bars": BP_N + 20,
        "source": "Ehlers Bandpass Indicator",
    },
    "itrend_x": {
        "name": "Ehlers Instantaneous Trendline 交叉",
        "family": "cycle",
        "speed": "mid",
        "sided": "both",
        "build": sig_itrend_x,
        "min_bars": 40,
        "source": "Ehlers Instantaneous Trendline, Cybernetic Analysis 2004 ch.5",
    },
    "vo_zero": {
        "name": "量擺盪 VO(5,20) 零軸交叉",
        "family": "volume",
        "speed": "mid",
        "sided": "both",
        "build": sig_vo_zero,
        "min_bars": VO_S + 20,
        "source": "Classic Volume Oscillator EMA5/20 (Granville lineage)",
    },
    "vroc_surge": {
        "name": "VROC(14)>+50% 量能激增",
        "family": "volume",
        "speed": "fast",
        "sided": "both",
        "build": sig_vroc_surge,
        "min_bars": VROC_N + 20,
        "source": "Classic Volume Rate of Change surge",
    },
    "marubozu_run": {
        "name": "雙 Marubozu 連續（抱≤6根）",
        "family": "candle",
        "speed": "fast",
        "sided": "both",
        "build": sig_marubozu_run,
        "max_hold_bars": MARU_HOLD,
        "min_bars": 20,
        "source": "Nison Marubozu continuation, JCT Techniques",
    },
    "range_leader": {
        "name": "Range Leader 中價越界+振幅擴大（抱≤4根）",
        "family": "momentum",
        "speed": "fast",
        "sided": "both",
        "build": sig_range_leader,
        "max_hold_bars": RL_HOLD,
        "min_bars": 20,
        "source": "Michael Harris Range Leader, Price Action Lab",
    },
    "darvas_box": {
        "name": "Darvas 盒(10,1.5ATR) 突破",
        "family": "breakout",
        "speed": "mid",
        "sided": "both",
        "build": sig_darvas_box,
        "min_bars": DARVAS_N + DARVAS_ATR + 20,
        "source": "Nicolas Darvas Box, How I Made $2,000,000 (1960)",
    },
}
