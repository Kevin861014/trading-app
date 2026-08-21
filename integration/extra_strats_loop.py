# -*- coding: utf-8 -*-
"""LOOP 教科書規則庫（參數全部寫死，禁止依場外結果改）。

每條都有公開來源與凍結常數。回傳 (el, xl, es, xs)。
撮合與止損不在本檔。
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

import sim  # noqa: E402

# ── 凍結常數 ─────────────────────────────────────────────
STC_FAST, STC_SLOW, STC_CYCLE, STC_SMOOTH = 23, 50, 10, 3
STC_LO, STC_HI = 25.0, 75.0
DT_LOOK, DT_K1, DT_K2 = 24, 0.5, 0.5          # 4H×24＝4 日
TK_CONV, TK_BASE = 9, 26
MCG_N = 12
MASS_EMA, MASS_SUM, MASS_HI, MASS_LO = 9, 25, 27.0, 26.5
COP_ROC1, COP_ROC2, COP_WMA = 11, 14, 10
TSI_LONG, TSI_SHORT, TSI_SIG = 25, 13, 13
RVI_N, RVI_SIG = 10, 4
FISH_N = 10
ALG_JAW, ALG_TEETH, ALG_LIPS = 13, 8, 5
ALG_JAW_S, ALG_TEETH_S, ALG_LIPS_S = 8, 5, 3
FRAC_N = 2
AC_FAST, AC_SLOW, AC_SMA = 5, 34, 5
MFI_N, MFI_LVL = 14, 50.0
CHO_FAST, CHO_SLOW = 3, 10
PPO_F, PPO_S, PPO_SIG = 12, 26, 9
DEMA_F, DEMA_S = 20, 50
TEMA_F, TEMA_S = 10, 30
QSTICK_N = 8
WMA_F, WMA_S = 10, 30
T3_F, T3_S, T3_V = 8, 21, 0.7
ENV_N, ENV_PCT = 20, 0.025
PIV_BARS = 6                               # 4H×6＝1 日
NR4_LOOK = 4
MACD_F, MACD_S = 12, 26
DMI_N = 14
SRSI_N, SRSI_K, SRSI_D = 14, 14, 3
ROC_N = 12
CCI_N, CCI_HI, CCI_LO = 20, 100.0, -100.0
RSI_N, RSI_MID = 14, 50.0
PSAR_AF0, PSAR_STEP, PSAR_MAX = 0.02, 0.02, 0.2
RAIN_A, RAIN_B, RAIN_C = 10, 20, 40
ZLEMA_F, ZLEMA_S = 10, 30
KVO_F, KVO_S, KVO_SIG = 34, 55, 13
EOM_N = 14
IK_CONV, IK_BASE, IK_SPANB = 9, 26, 52
WPR_N, WPR_MID = 14, -50.0
ALMA_N, ALMA_OFF, ALMA_SIG = 9, 0.85, 6.0
VIDYA_F, VIDYA_S, VIDYA_CMO = 10, 30, 9


def _empty(n):
    return [False] * n


def _sma_ok(vals, n):
    out = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        if any(x is None for x in w):
            continue
        out[i] = sum(w) / n
    return out


def _ema_ok(vals, n):
    out = [None] * len(vals)
    k = 2.0 / (n + 1)
    prev = None
    for i, v in enumerate(vals):
        if v is None:
            continue
        prev = v if prev is None else (v - prev) * k + prev
        out[i] = prev
    return out


def _wma(vals, n):
    out = [None] * len(vals)
    den = n * (n + 1) / 2.0
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        if any(x is None for x in w):
            continue
        out[i] = sum((j + 1) * w[j] for j in range(n)) / den
    return out


def _smma(vals, n):
    out = [None] * len(vals)
    s = None
    for i, v in enumerate(vals):
        if v is None:
            continue
        if i < n - 1:
            continue
        if s is None:
            w = vals[i - n + 1:i + 1]
            if any(x is None for x in w):
                continue
            s = sum(w) / n
        else:
            s = (s * (n - 1) + v) / n
        out[i] = s
    return out


def _shift(vals, k):
    if k <= 0:
        return list(vals)
    out = [None] * len(vals)
    for i in range(k, len(vals)):
        out[i] = vals[i - k]
    return out


def _dema(vals, n):
    e1 = _ema_ok(vals, n)
    e2 = _ema_ok(e1, n)
    out = [None] * len(vals)
    for i in range(len(vals)):
        if e1[i] is None or e2[i] is None:
            continue
        out[i] = 2 * e1[i] - e2[i]
    return out


def _tema(vals, n):
    e1 = _ema_ok(vals, n)
    e2 = _ema_ok(e1, n)
    e3 = _ema_ok(e2, n)
    out = [None] * len(vals)
    for i in range(len(vals)):
        if None in (e1[i], e2[i], e3[i]):
            continue
        out[i] = 3 * e1[i] - 3 * e2[i] + e3[i]
    return out


def _t3(vals, n, v=T3_V):
    def gd(src):
        e1 = _ema_ok(src, n)
        e2 = _ema_ok(e1, n)
        out = [None] * len(src)
        for i in range(len(src)):
            if e1[i] is None or e2[i] is None:
                continue
            out[i] = e1[i] * (1 + v) + e2[i] * (-v)
        return out
    return gd(gd(gd(vals)))


def _zlema(vals, n):
    lag = max(int((n - 1) / 2), 1)
    adj = [None] * len(vals)
    for i in range(len(vals)):
        if vals[i] is None:
            continue
        if i >= lag and vals[i - lag] is not None:
            adj[i] = vals[i] + (vals[i] - vals[i - lag])
        else:
            adj[i] = vals[i]
    return _ema_ok(adj, n)


def _alma(vals, n, offset=ALMA_OFF, sigma=ALMA_SIG):
    out = [None] * len(vals)
    m = offset * (n - 1)
    s = n / sigma
    w = [math.exp(-((i - m) ** 2) / (2 * s * s)) for i in range(n)]
    tw = sum(w)
    for i in range(n - 1, len(vals)):
        window = vals[i - n + 1:i + 1]
        if any(x is None for x in window):
            continue
        out[i] = sum(window[j] * w[j] for j in range(n)) / tw
    return out


def _cmo_abs(C, n):
    out = [None] * len(C)
    su = sd = 0.0
    up = [0.0] * len(C)
    dn = [0.0] * len(C)
    for i in range(1, len(C)):
        ch = C[i] - C[i - 1]
        up[i] = max(ch, 0.0)
        dn[i] = max(-ch, 0.0)
        su += up[i]
        sd += dn[i]
        if i > n:
            su -= up[i - n]
            sd -= dn[i - n]
        if i >= n:
            den = su + sd
            out[i] = abs(su - sd) / den if den > 0 else 0.0
    return out


def _vidya(vals, n, cmo_n):
    cmo = _cmo_abs(vals, cmo_n)
    out = [None] * len(vals)
    k = 2.0 / (n + 1)
    prev = None
    for i, v in enumerate(vals):
        if v is None or cmo[i] is None:
            continue
        sc = k * cmo[i]
        prev = v if prev is None else prev + sc * (v - prev)
        out[i] = prev
    return out


def _roc(C, n):
    out = [None] * len(C)
    for i in range(n, len(C)):
        if C[i - n]:
            out[i] = (C[i] - C[i - n]) / C[i - n] * 100.0
    return out


def _cross_state(a, b):
    """a 上穿 b → 1；下穿 → -1；否則 0。"""
    if None in (a[0], b[0], a[1], b[1]):
        return 0
    if a[0] <= b[0] and a[1] > b[1]:
        return 1
    if a[0] >= b[0] and a[1] < b[1]:
        return -1
    return 0


def _osc_cross(series, lvl, both=True):
    n = len(series)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        a, b = series[i - 1], series[i]
        if a is None or b is None:
            continue
        if a <= lvl < b:
            el[i] = True
            if both:
                xs[i] = True
        if a >= lvl > b:
            if both:
                es[i] = True
            xl[i] = True
    return el, xl, es, xs


def _line_cross(fast, slow):
    n = len(fast)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        c = _cross_state((fast[i - 1], fast[i]), (slow[i - 1], slow[i]))
        if c == 1:
            el[i] = True
            xs[i] = True
        elif c == -1:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def _slope_flip(series):
    n = len(series)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(2, n):
        if None in (series[i], series[i - 1], series[i - 2]):
            continue
        up = series[i] > series[i - 1]
        up_p = series[i - 1] > series[i - 2]
        if up and not up_p:
            el[i] = True
        if not up:
            xl[i] = True
        if (not up) and up_p:
            es[i] = True
        if up:
            xs[i] = True
    return el, xl, es, xs


def _stoch_of(src, n):
    out = [None] * len(src)
    for i in range(n - 1, len(src)):
        w = src[i - n + 1:i + 1]
        if any(x is None for x in w):
            continue
        lo, hi = min(w), max(w)
        den = hi - lo
        out[i] = 50.0 if den <= 0 else 100.0 * (src[i] - lo) / den
    return out


# ═══════════════ 訊號 ═══════════════
def sig_schaff_tc(O, H, L, C, V=None, tf=None):
    """Schaff Trend Cycle：MACD(23/50) 雙重隨機，上穿 25 多、下穿 75 空。

    來源：Doug Schaff, 1999。
    """
    e1 = sim.ema(C, STC_FAST)
    e2 = sim.ema(C, STC_SLOW)
    macd = [(a - b) if (a is not None and b is not None) else None for a, b in zip(e1, e2)]
    k1 = _stoch_of(macd, STC_CYCLE)
    pf = _ema_ok(k1, STC_SMOOTH)
    k2 = _stoch_of(pf, STC_CYCLE)
    stc = _ema_ok(k2, STC_SMOOTH)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if stc[i] is None or stc[i - 1] is None:
            continue
        if stc[i - 1] <= STC_LO < stc[i]:
            el[i] = True
            xs[i] = True
        if stc[i - 1] >= STC_HI > stc[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_dual_thrust(O, H, L, C, V=None, tf=None):
    """Dual Thrust：前 24 根 4H（4 日）Range，開盤 ±0.5 Range 突破。

    Range = max(HH−LC, HC−LL)。來源：Michael Chalek / Futures Truth。
    """
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(DT_LOOK, n):
        hh = max(H[i - DT_LOOK:i])
        ll = min(L[i - DT_LOOK:i])
        hc = max(C[i - DT_LOOK:i])
        lc = min(C[i - DT_LOOK:i])
        rng = max(hh - lc, hc - ll)
        if rng <= 0 or O[i] <= 0:
            continue
        buy = O[i] + DT_K1 * rng
        sell = O[i] - DT_K2 * rng
        if H[i] >= buy:
            el[i] = True
            xs[i] = True
        if L[i] <= sell:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_ichimoku_tk(O, H, L, C, V=None, tf=None):
    """一目轉換線／基準線交叉（不做雲）。與 sim.ichimoku 雲突破分開。"""
    n = len(C)
    ten = [None] * n
    kij = [None] * n
    for i in range(n):
        if i >= TK_CONV - 1:
            ten[i] = (max(H[i - TK_CONV + 1:i + 1]) + min(L[i - TK_CONV + 1:i + 1])) / 2
        if i >= TK_BASE - 1:
            kij[i] = (max(H[i - TK_BASE + 1:i + 1]) + min(L[i - TK_BASE + 1:i + 1])) / 2
    return _line_cross(ten, kij)


def sig_mcginley_slope(O, H, L, C, V=None, tf=None):
    """McGinley Dynamic(12) 斜率翻轉。來源：John McGinley。"""
    n = len(C)
    md = [None] * n
    md[0] = C[0]
    for i in range(1, n):
        prev = md[i - 1]
        if prev is None or prev == 0:
            md[i] = C[i]
            continue
        md[i] = prev + (C[i] - prev) / (MCG_N * (C[i] / prev) ** 4)
    return _slope_flip(md)


def sig_mass_reversion(O, H, L, C, V=None, tf=None):
    """Mass Index 膨脹後跌破 26.5，依 EMA9 方向交易。

    來源：Donald Dorsey。門檻 27 / 26.5 寫死。
    """
    hl = [H[i] - L[i] for i in range(len(C))]
    e1 = sim.ema(hl, MASS_EMA)
    e2 = _ema_ok(e1, MASS_EMA)
    ratio = [(a / b) if (a is not None and b not in (None, 0)) else None
             for a, b in zip(e1, e2)]
    mi = [None] * len(C)
    for i in range(MASS_SUM - 1, len(C)):
        w = ratio[i - MASS_SUM + 1:i + 1]
        if any(x is None for x in w):
            continue
        mi[i] = sum(w)
    ema_c = sim.ema(C, MASS_EMA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    bulge = False
    for i in range(1, n):
        if mi[i] is None or ema_c[i] is None:
            continue
        if mi[i] > MASS_HI:
            bulge = True
        if bulge and mi[i] < MASS_LO:
            if C[i] > ema_c[i]:
                el[i] = True
                xs[i] = True
            elif C[i] < ema_c[i]:
                es[i] = True
                xl[i] = True
            bulge = False
        if C[i] < ema_c[i]:
            xl[i] = True
        if C[i] > ema_c[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_coppock_zero(O, H, L, C, V=None, tf=None):
    """Coppock：WMA10(ROC14+ROC11) 零軸。來源：Edwin Coppock（月線常數凍結用於 4H）。"""
    a = _roc(C, COP_ROC1)
    b = _roc(C, COP_ROC2)
    s = [(x + y) if (x is not None and y is not None) else None for x, y in zip(a, b)]
    cop = _wma(s, COP_WMA)
    return _osc_cross(cop, 0.0)


def sig_tsi_cross(O, H, L, C, V=None, tf=None):
    """True Strength Index(25,13) 交叉訊號 13。來源：William Blau。"""
    n = len(C)
    pc = [None] * n
    apc = [None] * n
    for i in range(1, n):
        pc[i] = C[i] - C[i - 1]
        apc[i] = abs(pc[i])
    ds = _ema_ok(_ema_ok(pc, TSI_LONG), TSI_SHORT)
    das = _ema_ok(_ema_ok(apc, TSI_LONG), TSI_SHORT)
    tsi = [None] * n
    for i in range(n):
        if ds[i] is None or das[i] in (None, 0):
            continue
        tsi[i] = 100.0 * ds[i] / das[i]
    sig = _ema_ok(tsi, TSI_SIG)
    return _line_cross(tsi, sig)


def sig_rvi_cross(O, H, L, C, V=None, tf=None):
    """Relative Vigor Index(10) 交叉訊號 4。來源：John Ehlers。"""
    n = len(C)
    num = [None] * n
    den = [None] * n
    for i in range(3, n):
        num[i] = ((C[i] - O[i]) + 2 * (C[i - 1] - O[i - 1])
                  + 2 * (C[i - 2] - O[i - 2]) + (C[i - 3] - O[i - 3])) / 6.0
        den[i] = ((H[i] - L[i]) + 2 * (H[i - 1] - L[i - 1])
                  + 2 * (H[i - 2] - L[i - 2]) + (H[i - 3] - L[i - 3])) / 6.0
    n_s = _sma_ok(num, RVI_N)
    d_s = _sma_ok(den, RVI_N)
    rvi = [(a / b) if (a is not None and b not in (None, 0)) else None
           for a, b in zip(n_s, d_s)]
    sig = _sma_ok(rvi, RVI_SIG)
    return _line_cross(rvi, sig)


def sig_fisher_zero(O, H, L, C, V=None, tf=None):
    """Ehlers Fisher Transform(10) 零軸。來源：John Ehlers。"""
    n = len(C)
    mid = [(H[i] + L[i]) / 2.0 for i in range(n)]
    val = [None] * n
    fish = [None] * n
    prev_v = 0.0
    prev_f = 0.0
    for i in range(FISH_N - 1, n):
        lo = min(mid[i - FISH_N + 1:i + 1])
        hi = max(mid[i - FISH_N + 1:i + 1])
        den = hi - lo
        x = 0.0 if den <= 0 else 2 * ((mid[i] - lo) / den - 0.5)
        x = max(min(x, 0.999), -0.999)
        v = 0.33 * x + 0.67 * prev_v
        prev_v = v
        val[i] = v
        f = 0.5 * math.log((1 + v) / (1 - v)) + 0.5 * prev_f
        prev_f = f
        fish[i] = f
    return _osc_cross(fish, 0.0)


def sig_alligator(O, H, L, C, V=None, tf=None):
    """Williams Alligator：唇>齒>顎做多，反向做空。來源：Bill Williams。"""
    mid = [(H[i] + L[i]) / 2.0 for i in range(len(C))]
    jaw = _shift(_smma(mid, ALG_JAW), ALG_JAW_S)
    teeth = _shift(_smma(mid, ALG_TEETH), ALG_TEETH_S)
    lips = _shift(_smma(mid, ALG_LIPS), ALG_LIPS_S)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    prev = 0
    for i in range(1, n):
        if None in (jaw[i], teeth[i], lips[i]):
            continue
        long_ok = lips[i] > teeth[i] > jaw[i]
        short_ok = lips[i] < teeth[i] < jaw[i]
        cur = 1 if long_ok else (-1 if short_ok else 0)
        if cur == 1 and prev != 1:
            el[i] = True
        if cur != 1:
            xl[i] = True
        if cur == -1 and prev != -1:
            es[i] = True
        if cur != -1:
            xs[i] = True
        prev = cur
    return el, xl, es, xs


def sig_fractal_break(O, H, L, C, V=None, tf=None):
    """Williams 5-bar 分形突破。來源：Bill Williams。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    last_up = last_dn = None
    for i in range(FRAC_N, n - FRAC_N):
        if (H[i] > H[i - 1] and H[i] > H[i - 2] and H[i] > H[i + 1]
                and H[i] > H[i + 2]):
            last_up = H[i]
        if (L[i] < L[i - 1] and L[i] < L[i - 2] and L[i] < L[i + 1]
                and L[i] < L[i + 2]):
            last_dn = L[i]
        j = i + FRAC_N
        if j >= n or j < 1:
            continue
        if last_up is not None and C[j] > last_up >= C[j - 1]:
            el[j] = True
            xs[j] = True
        if last_dn is not None and C[j] < last_dn <= C[j - 1]:
            es[j] = True
            xl[j] = True
    return el, xl, es, xs


def sig_ac_zero(O, H, L, C, V=None, tf=None):
    """Accelerator Oscillator 零軸。來源：Bill Williams。與 v4 ao_zero 分開。"""
    mid = [(H[i] + L[i]) / 2.0 for i in range(len(C))]
    ao = []
    f = sim.sma(mid, AC_FAST)
    s = sim.sma(mid, AC_SLOW)
    for a, b in zip(f, s):
        ao.append((a - b) if (a is not None and b is not None) else None)
    ac = []
    sma_ao = _sma_ok(ao, AC_SMA)
    for a, b in zip(ao, sma_ao):
        ac.append((a - b) if (a is not None and b is not None) else None)
    return _osc_cross(ac, 0.0)


def sig_mfi_50(O, H, L, C, V=None, tf=None):
    """Money Flow Index(14) 穿越 50。來源：Quong / Soudack。"""
    n = len(C)
    V = V or [0.0] * n
    tp = [(H[i] + L[i] + C[i]) / 3.0 for i in range(n)]
    pos = [0.0] * n
    neg = [0.0] * n
    for i in range(1, n):
        mf = tp[i] * float(V[i] or 0.0)
        if tp[i] > tp[i - 1]:
            pos[i] = mf
        elif tp[i] < tp[i - 1]:
            neg[i] = mf
    mfi = [None] * n
    for i in range(MFI_N, n):
        ps = sum(pos[i - MFI_N + 1:i + 1])
        ng = sum(neg[i - MFI_N + 1:i + 1])
        if ng <= 0:
            mfi[i] = 100.0
        else:
            mfi[i] = 100.0 - 100.0 / (1.0 + ps / ng)
    return _osc_cross(mfi, MFI_LVL)


def sig_chaikin_osc(O, H, L, C, V=None, tf=None):
    """Chaikin Oscillator：ADL 的 EMA3−EMA10 零軸。來源：Marc Chaikin。"""
    n = len(C)
    V = V or [0.0] * n
    adl = [0.0] * n
    acc = 0.0
    for i in range(n):
        den = H[i] - L[i]
        clv = 0.0 if den <= 0 else ((C[i] - L[i]) - (H[i] - C[i])) / den
        acc += clv * float(V[i] or 0.0)
        adl[i] = acc
    osc = []
    f = sim.ema(adl, CHO_FAST)
    s = sim.ema(adl, CHO_SLOW)
    for a, b in zip(f, s):
        osc.append((a - b) if (a is not None and b is not None) else None)
    return _osc_cross(osc, 0.0)


def sig_ppo_cross(O, H, L, C, V=None, tf=None):
    """PPO(12,26,9) 交叉。與 MACD 絕對值不同。來源：Gerald Appel 百分比版。"""
    e1 = sim.ema(C, PPO_F)
    e2 = sim.ema(C, PPO_S)
    ppo = [((a - b) / b * 100.0) if (a is not None and b not in (None, 0)) else None
           for a, b in zip(e1, e2)]
    sig = _ema_ok(ppo, PPO_SIG)
    return _line_cross(ppo, sig)


def sig_dema_cross(O, H, L, C, V=None, tf=None):
    """DEMA20 / DEMA50 交叉。來源：Patrick Mulloy。"""
    return _line_cross(_dema(C, DEMA_F), _dema(C, DEMA_S))


def sig_tema_cross(O, H, L, C, V=None, tf=None):
    """TEMA10 / TEMA30 交叉。來源：Patrick Mulloy。"""
    return _line_cross(_tema(C, TEMA_F), _tema(C, TEMA_S))


def sig_qstick_zero(O, H, L, C, V=None, tf=None):
    """Qstick(8) 零軸。來源：Tushar Chande。"""
    body = [C[i] - O[i] for i in range(len(C))]
    return _osc_cross(sim.sma(body, QSTICK_N), 0.0)


def sig_wma_cross(O, H, L, C, V=None, tf=None):
    """WMA10 / WMA30 交叉。"""
    return _line_cross(_wma(C, WMA_F), _wma(C, WMA_S))


def sig_t3_cross(O, H, L, C, V=None, tf=None):
    """Tillson T3 8/21 交叉。來源：Tim Tillson。"""
    return _line_cross(_t3(C, T3_F), _t3(C, T3_S))


def sig_envelope_break(O, H, L, C, V=None, tf=None):
    """SMA20 ±2.5% 包絡突破；跌回均線出場。"""
    mid = sim.sma(C, ENV_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if mid[i] is None:
            continue
        up = mid[i] * (1.0 + ENV_PCT)
        dn = mid[i] * (1.0 - ENV_PCT)
        if C[i - 1] <= up < C[i]:
            el[i] = True
        if C[i] < mid[i]:
            xl[i] = True
        if C[i - 1] >= dn > C[i]:
            es[i] = True
        if C[i] > mid[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_pivot_break(O, H, L, C, V=None, tf=None):
    """前 6 根 4H（1 日）古典樞紐：破 R1 多、破 S1 空，回到 P 出場。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(PIV_BARS, n):
        hh = max(H[i - PIV_BARS:i])
        ll = min(L[i - PIV_BARS:i])
        cc = C[i - 1]
        p = (hh + ll + cc) / 3.0
        r1 = 2 * p - ll
        s1 = 2 * p - hh
        if C[i] > r1 and C[i - 1] <= r1:
            el[i] = True
        if C[i] < p:
            xl[i] = True
        if C[i] < s1 and C[i - 1] >= s1:
            es[i] = True
        if C[i] > p:
            xs[i] = True
    return el, xl, es, xs


def sig_nr4_break(O, H, L, C, V=None, tf=None):
    """Crabel NR4 突破（不是 NR7）。來源：Toby Crabel。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    setups = [None] * n
    for i in range(NR4_LOOK - 1, n):
        ranges = [H[j] - L[j] for j in range(i - NR4_LOOK + 1, i + 1)]
        if (H[i] - L[i]) <= min(ranges) + 1e-15:
            setups[i] = (H[i], L[i])
    pending = None
    for i in range(n):
        if pending is not None:
            shi, slo = pending
            if H[i] >= shi and not (L[i] <= slo):
                el[i] = True
                xs[i] = True
            elif L[i] <= slo and not (H[i] >= shi):
                es[i] = True
                xl[i] = True
            pending = None
        if setups[i] is not None:
            pending = setups[i]
    return el, xl, es, xs


def sig_inside_break(O, H, L, C, V=None, tf=None):
    """內包 K 下一根突破。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    pending = None
    for i in range(1, n):
        if pending is not None:
            shi, slo = pending
            if H[i] >= shi and not (L[i] <= slo):
                el[i] = True
                xs[i] = True
            elif L[i] <= slo and not (H[i] >= shi):
                es[i] = True
                xl[i] = True
            pending = None
        if H[i] < H[i - 1] and L[i] > L[i - 1]:
            pending = (H[i], L[i])
    return el, xl, es, xs


def sig_macd_zero(O, H, L, C, V=None, tf=None):
    """MACD 線零軸交叉（不是訊號線交叉）。與 sim.macd 分開。"""
    e1 = sim.ema(C, MACD_F)
    e2 = sim.ema(C, MACD_S)
    macd = [(a - b) if (a is not None and b is not None) else None for a, b in zip(e1, e2)]
    return _osc_cross(macd, 0.0)


def sig_dmi_cross(O, H, L, C, V=None, tf=None):
    """+DI / −DI 交叉，無 ADX、無長均線。與 sim.diadx 分開。"""
    pdi, ndi, _adx = sim.dmi(H, L, C, DMI_N)
    return _line_cross(pdi, ndi)


def sig_stoch_rsi(O, H, L, C, V=None, tf=None):
    """StochRSI(14,14,3) %K 上穿／下穿 %D。來源：Chande / Kroll。"""
    rv = sim.rsi(C, SRSI_N)
    k = _stoch_of(rv, SRSI_K)
    d = _sma_ok(k, SRSI_D)
    return _line_cross(k, d)


def sig_roc_zero(O, H, L, C, V=None, tf=None):
    """ROC(12) 零軸。"""
    return _osc_cross(_roc(C, ROC_N), 0.0)


def sig_cci_both(O, H, L, C, V=None, tf=None):
    """CCI(20) 上穿 +100 多、下穿 −100 空；反向閾值出場。與 sim.cci / cci_zero 分開。"""
    cc = sim.cci(H, L, C, CCI_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if cc[i] is None or cc[i - 1] is None:
            continue
        if cc[i - 1] <= CCI_HI < cc[i]:
            el[i] = True
        if cc[i] < 0:
            xl[i] = True
        if cc[i - 1] >= CCI_LO > cc[i]:
            es[i] = True
        if cc[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_rsi50_both(O, H, L, C, V=None, tf=None):
    """RSI(14) 穿越 50 雙向，無長均線。與 sim.rsi50 分開。"""
    return _osc_cross(sim.rsi(C, RSI_N), RSI_MID)


def sig_psar_both(O, H, L, C, V=None, tf=None):
    """Parabolic SAR 翻轉雙向，無長均線。與 sim.psar 分開。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    if n < 3:
        return el, xl, es, xs
    up = True
    af = PSAR_AF0
    ep = H[0]
    sar = L[0]
    tr = [1] * n
    for i in range(1, n):
        psar = sar + af * (ep - sar)
        if up:
            psar = min(psar, L[i - 1], L[i - 2] if i >= 2 else L[i - 1])
            if H[i] > ep:
                ep = H[i]
                af = min(af + PSAR_STEP, PSAR_MAX)
            if L[i] < psar:
                up = False
                psar = ep
                ep = L[i]
                af = PSAR_AF0
        else:
            psar = max(psar, H[i - 1], H[i - 2] if i >= 2 else H[i - 1])
            if L[i] < ep:
                ep = L[i]
                af = min(af + PSAR_STEP, PSAR_MAX)
            if H[i] > psar:
                up = True
                psar = ep
                ep = H[i]
                af = PSAR_AF0
        sar = psar
        tr[i] = 1 if up else -1
    for i in range(1, n):
        if tr[i] == 1 and tr[i - 1] != 1:
            el[i] = True
            xs[i] = True
        if tr[i] == -1 and tr[i - 1] != -1:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_rainbow_align(O, H, L, C, V=None, tf=None):
    """SMA10/20/40 多頭／空頭排列形成。"""
    a = sim.sma(C, RAIN_A)
    b = sim.sma(C, RAIN_B)
    c = sim.sma(C, RAIN_C)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    prev = 0
    for i in range(1, n):
        if None in (a[i], b[i], c[i]):
            continue
        long_ok = a[i] > b[i] > c[i]
        short_ok = a[i] < b[i] < c[i]
        cur = 1 if long_ok else (-1 if short_ok else 0)
        if cur == 1 and prev != 1:
            el[i] = True
        if cur != 1:
            xl[i] = True
        if cur == -1 and prev != -1:
            es[i] = True
        if cur != -1:
            xs[i] = True
        prev = cur
    return el, xl, es, xs


def sig_zlema_cross(O, H, L, C, V=None, tf=None):
    """Zero-lag EMA 10/30 交叉。來源：Ehlers / 改良 EMA。"""
    return _line_cross(_zlema(C, ZLEMA_F), _zlema(C, ZLEMA_S))


def sig_klinger_cross(O, H, L, C, V=None, tf=None):
    """Klinger Volume Oscillator 34/55 交叉訊號 13。來源：Stephen Klinger。"""
    n = len(C)
    V = V or [0.0] * n
    sv = [0.0] * n
    cm = 0.0
    prev_trend = 0
    dm_prev = 0.0
    for i in range(n):
        hlc = H[i] + L[i] + C[i]
        trend = prev_trend
        if i > 0:
            prev = H[i - 1] + L[i - 1] + C[i - 1]
            if hlc > prev:
                trend = 1
            elif hlc < prev:
                trend = -1
        dm = H[i] - L[i]
        if i == 0:
            cm = dm
        elif trend == prev_trend:
            cm += dm
        else:
            cm = dm_prev + dm
        temp = 0.0 if cm == 0 else abs(2 * dm / cm - 1)
        sv[i] = float(V[i] or 0.0) * temp * trend * 100.0
        prev_trend = trend
        dm_prev = dm
    kvo = []
    f = sim.ema(sv, KVO_F)
    s = sim.ema(sv, KVO_S)
    for a, b in zip(f, s):
        kvo.append((a - b) if (a is not None and b is not None) else None)
    sig = _ema_ok(kvo, KVO_SIG)
    return _line_cross(kvo, sig)


def sig_eom_zero(O, H, L, C, V=None, tf=None):
    """Ease of Movement(14) 零軸。來源：Richard Arms。"""
    n = len(C)
    V = V or [0.0] * n
    raw = [None] * n
    for i in range(1, n):
        dist = ((H[i] + L[i]) / 2.0) - ((H[i - 1] + L[i - 1]) / 2.0)
        box = 0.0
        if V[i] and (H[i] - L[i]) > 0:
            box = (float(V[i]) / 1e6) / (H[i] - L[i])
        raw[i] = dist / box if box else 0.0
    return _osc_cross(_sma_ok(raw, EOM_N), 0.0)


def sig_ichimoku_twist(O, H, L, C, V=None, tf=None):
    """一目先行帶 A/B 扭轉（不前移當訊號，避免未來函數）。與雲突破／TK 分開。"""
    n = len(C)
    sa = [None] * n
    sb = [None] * n
    for i in range(n):
        if i >= IK_CONV - 1 and i >= IK_BASE - 1:
            ten = (max(H[i - IK_CONV + 1:i + 1]) + min(L[i - IK_CONV + 1:i + 1])) / 2
            kij = (max(H[i - IK_BASE + 1:i + 1]) + min(L[i - IK_BASE + 1:i + 1])) / 2
            sa[i] = (ten + kij) / 2
        if i >= IK_SPANB - 1:
            sb[i] = (max(H[i - IK_SPANB + 1:i + 1]) + min(L[i - IK_SPANB + 1:i + 1])) / 2
    return _line_cross(sa, sb)


def sig_wpr_mid(O, H, L, C, V=None, tf=None):
    """Williams %R(14) 穿越 −50。與 v3 −80/−20 fade 分開。"""
    hh = sim.highest(H, WPR_N)
    ll = sim.lowest(L, WPR_N)
    n = len(C)
    wr = [None] * n
    for i in range(n):
        if hh[i] is None or ll[i] is None:
            continue
        den = hh[i] - ll[i]
        wr[i] = -50.0 if den <= 0 else -100.0 * (hh[i] - C[i]) / den
    return _osc_cross(wr, WPR_MID)


def sig_alma_slope(O, H, L, C, V=None, tf=None):
    """ALMA(9, 0.85, 6) 斜率翻轉。來源：Arnaud Legoux。"""
    return _slope_flip(_alma(C, ALMA_N, ALMA_OFF, ALMA_SIG))


def sig_vidya_cross(O, H, L, C, V=None, tf=None):
    """VIDYA 10/30 交叉。來源：Tushar Chande 自適應均線。"""
    return _line_cross(_vidya(C, VIDYA_F, VIDYA_CMO), _vidya(C, VIDYA_S, VIDYA_CMO))


GUPPY_S = (3, 5, 8, 10, 12, 15)
GUPPY_L = (30, 35, 40, 45, 50, 60)
HMA_F, HMA_S = 16, 64
KAMA_N, KAMA_FAST, KAMA_SLOW, KAMA_SIG = 10, 2, 30, 30
VORTEX_N = 14
ADX_N, ADX_MIN = 14, 25
KIJUN_N = 26
CAM_BARS = 6
CPR_BARS = 6
SOUP_N, SOUP_HOLD = 20, 12
HG_ADX, HG_EMA = 30, 20
BB_N, BB_K = 20, 2.0
RMI_N, RMI_M, RMI_LVL = 20, 5, 50.0
SSL_N = 10
PD_BARS = 6
SWING_N = 3
FORCE_N = 13
CMF_N = 20
NVI_EMA = 40
TSF_N = 14
EMA_F2, EMA_S2 = 8, 21
SMMA_F, SMMA_S = 10, 30
TYP_F, TYP_S = 10, 30
DON10_E, DON10_X = 10, 5


def _hma(vals, n):
    half = max(n // 2, 1)
    root = max(int(n ** 0.5), 1)
    w1 = _wma(vals, half)
    w2 = _wma(vals, n)
    raw = [(2 * a - b) if (a is not None and b is not None) else None
           for a, b in zip(w1, w2)]
    return _wma(raw, root)


def _linreg_forecast(C, n):
    """下一根線性回歸預測值（當根可算，無未來）。"""
    out = [None] * len(C)
    for i in range(n - 1, len(C)):
        ys = C[i - n + 1:i + 1]
        xs = list(range(n))
        mx = (n - 1) / 2.0
        my = sum(ys) / n
        den = sum((x - mx) ** 2 for x in xs)
        if den <= 0:
            continue
        sl = sum((xs[j] - mx) * (ys[j] - my) for j in range(n)) / den
        out[i] = my + sl * ((n - 1) / 2.0 + 1.0)
    return out


def sig_guppy_mm(O, H, L, C, V=None, tf=None):
    """Guppy MMA：短組全在長組之上做多，反向做空。來源：Daryl Guppy。"""
    shorts = [sim.ema(C, p) for p in GUPPY_S]
    longs = [sim.ema(C, p) for p in GUPPY_L]
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    prev = 0
    for i in range(1, n):
        sv = [e[i] for e in shorts]
        lv = [e[i] for e in longs]
        if any(x is None for x in sv + lv):
            continue
        long_ok = min(sv) > max(lv)
        short_ok = max(sv) < min(lv)
        cur = 1 if long_ok else (-1 if short_ok else 0)
        if cur == 1 and prev != 1:
            el[i] = True
        if cur != 1:
            xl[i] = True
        if cur == -1 and prev != -1:
            es[i] = True
        if cur != -1:
            xs[i] = True
        prev = cur
    return el, xl, es, xs


def sig_hma_cross(O, H, L, C, V=None, tf=None):
    """HMA16 / HMA64 交叉。與 sim.hma 斜率翻轉分開。來源：Alan Hull。"""
    return _line_cross(_hma(C, HMA_F), _hma(C, HMA_S))


def sig_kama_cross(O, H, L, C, V=None, tf=None):
    """KAMA(10) 交叉 SMA30，無長均線過濾。與 sim.kama 分開。來源：Kaufman。"""
    n = len(C)
    scf = 2 / (KAMA_FAST + 1)
    scs = 2 / (KAMA_SLOW + 1)
    k = [None] * n
    for i in range(n):
        if i < KAMA_N:
            k[i] = C[i]
            continue
        ch = abs(C[i] - C[i - KAMA_N])
        vol = sum(abs(C[j] - C[j - 1]) for j in range(i - KAMA_N + 1, i + 1))
        er = ch / vol if vol > 0 else 0
        sc = (er * (scf - scs) + scs) ** 2
        k[i] = k[i - 1] + sc * (C[i] - k[i - 1])
    return _line_cross(k, sim.sma(C, KAMA_SIG))


def sig_vortex_both(O, H, L, C, V=None, tf=None):
    """Vortex VI+/VI− 交叉，無長均線。與 sim.vortex 分開。"""
    vip, vin = sim.vortex(H, L, C, VORTEX_N)
    return _line_cross(vip, vin)


def sig_adx_di_trend(O, H, L, C, V=None, tf=None):
    """ADX>25 且上升，跟 +DI/−DI。來源：Wilder New Concepts。與 diadx 分開。"""
    pdi, ndi, adx = sim.dmi(H, L, C, ADX_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (pdi[i], ndi[i], adx[i], adx[i - 1]):
            continue
        strong = adx[i] > ADX_MIN and adx[i] > adx[i - 1]
        if strong and pdi[i] > ndi[i] and (pdi[i - 1] is None or pdi[i - 1] <= ndi[i - 1]):
            el[i] = True
        if pdi[i] < ndi[i]:
            xl[i] = True
        if strong and ndi[i] > pdi[i] and (ndi[i - 1] is None or ndi[i - 1] <= pdi[i - 1]):
            es[i] = True
        if ndi[i] < pdi[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_kijun_cross(O, H, L, C, V=None, tf=None):
    """收盤穿越一目基準線(26)。與雲／TK 分開。"""
    n = len(C)
    kij = [None] * n
    for i in range(KIJUN_N - 1, n):
        kij[i] = (max(H[i - KIJUN_N + 1:i + 1]) + min(L[i - KIJUN_N + 1:i + 1])) / 2
    return _line_cross(C, kij)


def sig_camarilla_break(O, H, L, C, V=None, tf=None):
    """前 1 日 Camarilla R3/S3 突破。來源：Nick Scott Camarilla。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(CAM_BARS, n):
        hh = max(H[i - CAM_BARS:i])
        ll = min(L[i - CAM_BARS:i])
        cc = C[i - 1]
        rng = hh - ll
        r3 = cc + 1.1 * rng / 4.0
        s3 = cc - 1.1 * rng / 4.0
        if C[i] > r3 and C[i - 1] <= r3:
            el[i] = True
        if C[i] < cc:
            xl[i] = True
        if C[i] < s3 and C[i - 1] >= s3:
            es[i] = True
        if C[i] > cc:
            xs[i] = True
    return el, xl, es, xs


def sig_cpr_break(O, H, L, C, V=None, tf=None):
    """前 1 日 Central Pivot Range 破上緣／下緣。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(CPR_BARS, n):
        hh = max(H[i - CPR_BARS:i])
        ll = min(L[i - CPR_BARS:i])
        cc = C[i - 1]
        p = (hh + ll + cc) / 3.0
        bc = (hh + ll) / 2.0
        tc = 2 * p - bc
        top, bot = max(tc, bc), min(tc, bc)
        if C[i] > top and C[i - 1] <= top:
            el[i] = True
        if C[i] < p:
            xl[i] = True
        if C[i] < bot and C[i - 1] >= bot:
            es[i] = True
        if C[i] > p:
            xs[i] = True
    return el, xl, es, xs


def sig_turtle_soup(O, H, L, C, V=None, tf=None):
    """Turtle Soup：fade 20 根新高／新低。來源：Larry Connors Street Smarts。

    時間出場在撮合端 hold=12 根 4H。
    """
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    hh = sim.highest(H, SOUP_N)
    ll = sim.lowest(L, SOUP_N)
    for i in range(1, n):
        if hh[i - 1] is None or ll[i - 1] is None:
            continue
        if C[i] > hh[i - 1]:
            es[i] = True
            xl[i] = True
        if C[i] < ll[i - 1]:
            el[i] = True
            xs[i] = True
    return el, xl, es, xs


def sig_holy_grail(O, H, L, C, V=None, tf=None):
    """Holy Grail：ADX>30，回踩 EMA20 後續勢。來源：Connors / Raschke。"""
    pdi, ndi, adx = sim.dmi(H, L, C, 14)
    e = sim.ema(C, HG_EMA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (adx[i], e[i], pdi[i], ndi[i], e[i - 1]):
            continue
        if adx[i] > HG_ADX and pdi[i] > ndi[i] and C[i - 1] <= e[i - 1] and C[i] > e[i]:
            el[i] = True
        if C[i] < e[i]:
            xl[i] = True
        if adx[i] > HG_ADX and ndi[i] > pdi[i] and C[i - 1] >= e[i - 1] and C[i] < e[i]:
            es[i] = True
        if C[i] > e[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_bb_bounce(O, H, L, C, V=None, tf=None):
    """布林帶下軌做多、上軌做空，回到中軌出場。來源：John Bollinger 均值回歸用法。"""
    mid = sim.sma(C, BB_N)
    sd = sim.stdev(C, BB_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if mid[i] is None or sd[i] is None:
            continue
        lo = mid[i] - BB_K * sd[i]
        hi = mid[i] + BB_K * sd[i]
        if C[i] < lo and C[i - 1] >= lo:
            el[i] = True
        if C[i] > mid[i]:
            xl[i] = True
        if C[i] > hi and C[i - 1] <= hi:
            es[i] = True
        if C[i] < mid[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_rmi_zero(O, H, L, C, V=None, tf=None):
    """Relative Momentum Index(20, mom=5) 穿越 50。來源：Roger Altman。"""
    n = len(C)
    up = [0.0] * n
    dn = [0.0] * n
    for i in range(RMI_M, n):
        ch = C[i] - C[i - RMI_M]
        up[i] = max(ch, 0.0)
        dn[i] = max(-ch, 0.0)
    rmi = [None] * n
    for i in range(RMI_N + RMI_M, n):
        su = sum(up[i - RMI_N + 1:i + 1])
        sd = sum(dn[i - RMI_N + 1:i + 1])
        if sd <= 0:
            rmi[i] = 100.0
        else:
            rmi[i] = 100.0 - 100.0 / (1.0 + su / sd)
    return _osc_cross(rmi, RMI_LVL)


def sig_ssl_channel(O, H, L, C, V=None, tf=None):
    """SSL 通道：收盤穿越 SMA(H)／SMA(L)。來源：wocs／公開 SSL Channel。"""
    hs = sim.sma(H, SSL_N)
    ls = sim.sma(L, SSL_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    hlv = [0] * n
    for i in range(n):
        if hs[i] is None or ls[i] is None:
            continue
        if C[i] > hs[i]:
            hlv[i] = 1
        elif C[i] < ls[i]:
            hlv[i] = -1
        else:
            hlv[i] = hlv[i - 1] if i else 0
        if i and hlv[i] == 1 and hlv[i - 1] != 1:
            el[i] = True
        if hlv[i] != 1:
            xl[i] = True
        if i and hlv[i] == -1 and hlv[i - 1] != -1:
            es[i] = True
        if hlv[i] != -1:
            xs[i] = True
    return el, xl, es, xs


def sig_prev_day_hl(O, H, L, C, V=None, tf=None):
    """突破前 6 根 4H（1 日）高低。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(PD_BARS, n):
        hh = max(H[i - PD_BARS:i])
        ll = min(L[i - PD_BARS:i])
        if C[i] > hh and C[i - 1] <= hh:
            el[i] = True
        if C[i] < ll:
            xl[i] = True
        if C[i] < ll and C[i - 1] >= ll:
            es[i] = True
        if C[i] > hh:
            xs[i] = True
    return el, xl, es, xs


def sig_swing3_break(O, H, L, C, V=None, tf=None):
    """3 根擺動高／低突破。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    last_h = last_l = None
    for i in range(SWING_N, n - SWING_N):
        if H[i] == max(H[i - SWING_N:i + SWING_N + 1]):
            last_h = H[i]
        if L[i] == min(L[i - SWING_N:i + SWING_N + 1]):
            last_l = L[i]
        j = i + SWING_N
        if j >= n or j < 1:
            continue
        if last_h is not None and C[j] > last_h >= C[j - 1]:
            el[j] = True
            xs[j] = True
        if last_l is not None and C[j] < last_l <= C[j - 1]:
            es[j] = True
            xl[j] = True
    return el, xl, es, xs


def sig_engulfing(O, H, L, C, V=None, tf=None):
    """吞沒線：陽吞陰做多、陰吞陽做空。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        prev_up = C[i - 1] > O[i - 1]
        prev_dn = C[i - 1] < O[i - 1]
        body = abs(C[i] - O[i])
        pbody = abs(C[i - 1] - O[i - 1])
        if (prev_dn and C[i] > O[i] and O[i] <= C[i - 1] and C[i] >= O[i - 1]
                and body > pbody):
            el[i] = True
            xs[i] = True
        if (prev_up and C[i] < O[i] and O[i] >= C[i - 1] and C[i] <= O[i - 1]
                and body > pbody):
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_three_soldiers(O, H, L, C, V=None, tf=None):
    """三白兵／三烏鴉。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(2, n):
        up3 = all(C[j] > O[j] and C[j] > C[j - 1] for j in range(i - 2, i + 1))
        dn3 = all(C[j] < O[j] and C[j] < C[j - 1] for j in range(i - 2, i + 1))
        if up3:
            el[i] = True
            xs[i] = True
        if dn3:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_force_zero(O, H, L, C, V=None, tf=None):
    """Force Index(13) 零軸。與 sim.force 趨勢過濾分開。來源：Elder。"""
    n = len(C)
    V = V or [0.0] * n
    raw = [0.0] * n
    for i in range(1, n):
        raw[i] = float(V[i] or 0.0) * (C[i] - C[i - 1])
    return _osc_cross(sim.ema(raw, FORCE_N), 0.0)


def sig_cmf_zero(O, H, L, C, V=None, tf=None):
    """Chaikin Money Flow(20) 零軸。與 sim.cmf 趨勢過濾分開。"""
    n = len(C)
    V = V or [0.0] * n
    mfv = [0.0] * n
    for i in range(n):
        den = H[i] - L[i]
        clv = 0.0 if den <= 0 else ((C[i] - L[i]) - (H[i] - C[i])) / den
        mfv[i] = clv * float(V[i] or 0.0)
    cmf = [None] * n
    for i in range(CMF_N - 1, n):
        vs = sum(float(V[j] or 0.0) for j in range(i - CMF_N + 1, i + 1))
        cmf[i] = (sum(mfv[i - CMF_N + 1:i + 1]) / vs) if vs else 0.0
    return _osc_cross(cmf, 0.0)


def sig_nvi_ema(O, H, L, C, V=None, tf=None):
    """Negative Volume Index 交叉 EMA40。來源：Norman Fosback。"""
    n = len(C)
    V = V or [0.0] * n
    nvi = [1000.0] * n
    for i in range(1, n):
        nvi[i] = nvi[i - 1]
        if (V[i] or 0) < (V[i - 1] or 0) and C[i - 1]:
            nvi[i] = nvi[i - 1] * (1.0 + (C[i] - C[i - 1]) / C[i - 1])
    return _line_cross(nvi, sim.ema(nvi, NVI_EMA))


def sig_tsf_cross(O, H, L, C, V=None, tf=None):
    """Time Series Forecast(14) 與收盤交叉。來源：線性回歸預測。"""
    tsf = _linreg_forecast(C, TSF_N)
    return _line_cross(C, tsf)


def sig_heikin_both(O, H, L, C, V=None, tf=None):
    """Heikin-Ashi 翻綠／翻紅，無長均線。與 sim.heikin 分開。"""
    n = len(C)
    ha_c = [(O[i] + H[i] + L[i] + C[i]) / 4.0 for i in range(n)]
    ha_o = [O[0]] * n
    for i in range(1, n):
        ha_o[i] = (ha_o[i - 1] + ha_c[i - 1]) / 2.0
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        up = ha_c[i] > ha_o[i]
        up_p = ha_c[i - 1] > ha_o[i - 1]
        if up and not up_p:
            el[i] = True
        if not up:
            xl[i] = True
        if (not up) and up_p:
            es[i] = True
        if up:
            xs[i] = True
    return el, xl, es, xs


def sig_ema_8_21(O, H, L, C, V=None, tf=None):
    """EMA8 / EMA21 交叉。與 ema_cross 20/50、黃金 50/200 分開。"""
    return _line_cross(sim.ema(C, EMA_F2), sim.ema(C, EMA_S2))


def sig_smma_cross(O, H, L, C, V=None, tf=None):
    """SMMA10 / SMMA30 交叉。"""
    return _line_cross(_smma(C, SMMA_F), _smma(C, SMMA_S))


def sig_typical_ma(O, H, L, C, V=None, tf=None):
    """典型價 SMA10/30 交叉。"""
    tp = [(H[i] + L[i] + C[i]) / 3.0 for i in range(len(C))]
    return _line_cross(sim.sma(tp, TYP_F), sim.sma(tp, TYP_S))


def sig_donchian10(O, H, L, C, V=None, tf=None):
    """Donchian 10/5 雙向，無 EMA。與 20/10、55/20、100/50 分開。"""
    hh_e = sim.highest(H, DON10_E)
    ll_e = sim.lowest(L, DON10_E)
    hh_x = sim.highest(H, DON10_X)
    ll_x = sim.lowest(L, DON10_X)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if hh_e[i - 1] is None or ll_e[i - 1] is None:
            continue
        if C[i] > hh_e[i - 1]:
            el[i] = True
        if C[i] < ll_e[i - 1]:
            es[i] = True
        if ll_x[i - 1] is not None and C[i] < ll_x[i - 1]:
            xl[i] = True
        if hh_x[i - 1] is not None and C[i] > hh_x[i - 1]:
            xs[i] = True
    return el, xl, es, xs


def _meta(name, family, build, min_bars, source, speed="mid"):
    return {
        "name": name, "family": family, "speed": speed, "sided": "both",
        "build": build, "max_hold_bars": None, "min_bars": min_bars, "source": source,
    }


EXTRA_STRATS_LOOP = {
    "schaff_tc": _meta("Schaff Trend Cycle 23/50/10 穿 25/75", "schaff",
                       sig_schaff_tc, STC_SLOW + STC_CYCLE + 20, "Doug Schaff 1999"),
    "dual_thrust": _meta("Dual Thrust 4日 Range k=0.5", "thrust",
                         sig_dual_thrust, DT_LOOK + 20, "Michael Chalek Dual Thrust"),
    "ichimoku_tk": _meta("一目 TK 交叉 9/26", "ichimoku",
                         sig_ichimoku_tk, TK_BASE + 20, "Ichimoku Tenkan/Kijun only"),
    "mcginley_slope": _meta("McGinley Dynamic(12) 斜率", "mcginley",
                            sig_mcginley_slope, MCG_N + 20, "John McGinley"),
    "mass_reversion": _meta("Mass Index 27/26.5 + EMA9", "mass",
                            sig_mass_reversion, MASS_SUM + MASS_EMA + 20, "Donald Dorsey"),
    "coppock_zero": _meta("Coppock WMA10(ROC11+14) 零軸", "coppock",
                          sig_coppock_zero, COP_ROC2 + COP_WMA + 20, "Edwin Coppock"),
    "tsi_cross": _meta("TSI(25,13) 交叉 13", "tsi",
                       sig_tsi_cross, TSI_LONG + TSI_SHORT + TSI_SIG + 20, "William Blau TSI"),
    "rvi_cross": _meta("RVI(10) 交叉 4", "rvi",
                       sig_rvi_cross, RVI_N + RVI_SIG + 20, "John Ehlers RVI"),
    "fisher_zero": _meta("Ehlers Fisher(10) 零軸", "fisher",
                         sig_fisher_zero, FISH_N + 20, "John Ehlers Fisher Transform"),
    "alligator": _meta("Williams Alligator 13/8/5", "williams",
                       sig_alligator, ALG_JAW + ALG_JAW_S + 20, "Bill Williams Alligator"),
    "fractal_break": _meta("Williams 5-bar 分形突破", "williams",
                           sig_fractal_break, 20, "Bill Williams fractals"),
    "ac_zero": _meta("Accelerator Oscillator 零軸", "williams",
                     sig_ac_zero, AC_SLOW + AC_SMA + 20, "Bill Williams AC"),
    "mfi_50": _meta("MFI(14) 穿越 50", "volume",
                    sig_mfi_50, MFI_N + 20, "Quong/Soudack MFI"),
    "chaikin_osc": _meta("Chaikin Oscillator 3-10 零軸", "volume",
                         sig_chaikin_osc, CHO_SLOW + 20, "Marc Chaikin oscillator"),
    "ppo_cross": _meta("PPO(12,26,9) 交叉", "macd",
                       sig_ppo_cross, PPO_S + PPO_SIG + 20, "Appel PPO"),
    "dema_cross": _meta("DEMA20/50 交叉", "ma",
                        sig_dema_cross, DEMA_S + 20, "Patrick Mulloy DEMA"),
    "tema_cross": _meta("TEMA10/30 交叉", "ma",
                        sig_tema_cross, TEMA_S * 3 + 20, "Patrick Mulloy TEMA"),
    "qstick_zero": _meta("Qstick(8) 零軸", "qstick",
                         sig_qstick_zero, QSTICK_N + 20, "Tushar Chande Qstick"),
    "wma_cross": _meta("WMA10/30 交叉", "ma",
                       sig_wma_cross, WMA_S + 20, "Weighted MA cross"),
    "t3_cross": _meta("Tillson T3 8/21 交叉", "ma",
                      sig_t3_cross, T3_S * 6 + 20, "Tim Tillson T3"),
    "envelope_break": _meta("SMA20 ±2.5% 包絡突破", "envelope",
                            sig_envelope_break, ENV_N + 20, "Moving average envelope 2.5%"),
    "pivot_break": _meta("前1日樞紐破 R1/S1", "pivot",
                         sig_pivot_break, PIV_BARS + 20, "Classic floor-trader pivots"),
    "nr4_break": _meta("Crabel NR4 突破", "crabel",
                       sig_nr4_break, NR4_LOOK + 20, "Toby Crabel NR4"),
    "inside_break": _meta("內包K突破", "ib",
                          sig_inside_break, 20, "Inside-bar breakout"),
    "macd_zero": _meta("MACD 線零軸交叉", "macd",
                       sig_macd_zero, MACD_S + 20, "MACD line zero; not signal-line"),
    "dmi_cross": _meta("+DI/−DI 交叉無過濾", "dmi",
                       sig_dmi_cross, DMI_N + 20, "Wilder DI cross no ADX"),
    "stoch_rsi": _meta("StochRSI 14/14/3 交叉", "stoch",
                       sig_stoch_rsi, SRSI_N + SRSI_K + 20, "Chande/Kroll StochRSI"),
    "roc_zero": _meta("ROC(12) 零軸", "roc",
                      sig_roc_zero, ROC_N + 20, "Rate of change 12"),
    "cci_both": _meta("CCI(20) ±100 雙向", "cci",
                      sig_cci_both, CCI_N + 20, "Lambert CCI ±100 no EMA"),
    "rsi50_both": _meta("RSI(14) 穿越 50 雙向", "rsi",
                        sig_rsi50_both, RSI_N + 20, "RSI mid-line both sides"),
    "psar_both": _meta("PSAR 翻轉雙向無均線", "psar",
                       sig_psar_both, 20, "Wilder PSAR flip both sides"),
    "rainbow_align": _meta("SMA10/20/40 排列", "ma",
                           sig_rainbow_align, RAIN_C + 20, "3-SMA rainbow alignment"),
    "zlema_cross": _meta("ZLEMA 10/30 交叉", "ma",
                         sig_zlema_cross, ZLEMA_S + 20, "Zero-lag EMA cross"),
    "klinger_cross": _meta("Klinger 34/55 交叉 13", "volume",
                           sig_klinger_cross, KVO_S + KVO_SIG + 20, "Stephen Klinger KVO"),
    "eom_zero": _meta("Ease of Movement(14) 零軸", "volume",
                      sig_eom_zero, EOM_N + 20, "Richard Arms EOM"),
    "ichimoku_twist": _meta("一目先行帶扭轉", "ichimoku",
                            sig_ichimoku_twist, IK_SPANB + 20, "Span A/B twist contemporaneous"),
    "wpr_mid": _meta("Williams %R 穿越 -50", "wr",
                     sig_wpr_mid, WPR_N + 20, "Williams %R midpoint"),
    "alma_slope": _meta("ALMA(9,0.85,6) 斜率", "alma",
                        sig_alma_slope, ALMA_N + 20, "Arnaud Legoux MA"),
    "vidya_cross": _meta("VIDYA 10/30 交叉", "ma",
                         sig_vidya_cross, VIDYA_S + VIDYA_CMO + 20, "Chande VIDYA"),
    "guppy_mm": _meta("Guppy MMA 短組長組排列", "guppy",
                      sig_guppy_mm, 80, "Daryl Guppy MMA"),
    "hma_cross": _meta("HMA16/64 交叉", "ma",
                       sig_hma_cross, HMA_S + 20, "Alan Hull MA cross"),
    "kama_cross": _meta("KAMA10 交叉 SMA30", "kama",
                        sig_kama_cross, KAMA_N + KAMA_SIG + 20, "Kaufman AMA no trend filter"),
    "vortex_both": _meta("Vortex 交叉無均線", "vortex",
                         sig_vortex_both, VORTEX_N + 20, "Vortex both sides"),
    "adx_di_trend": _meta("ADX>25 上升跟 DI", "dmi",
                          sig_adx_di_trend, ADX_N + 20, "Wilder ADX+DI"),
    "kijun_cross": _meta("收盤穿一目基準線26", "ichimoku",
                         sig_kijun_cross, KIJUN_N + 20, "Price vs Kijun"),
    "camarilla_break": _meta("Camarilla R3/S3 突破", "pivot",
                             sig_camarilla_break, CAM_BARS + 20, "Nick Scott Camarilla"),
    "cpr_break": _meta("Central Pivot Range 突破", "pivot",
                       sig_cpr_break, CPR_BARS + 20, "CPR breakout"),
    "turtle_soup": _meta("Turtle Soup fade 20 根", "fade",
                         sig_turtle_soup, SOUP_N + 20, "Connors Street Smarts Turtle Soup"),
    "holy_grail": _meta("Holy Grail ADX30+EMA20 回踩", "connors",
                        sig_holy_grail, 40, "Connors/Raschke Holy Grail"),
    "bb_bounce": _meta("布林帶均值回歸", "fade",
                       sig_bb_bounce, BB_N + 20, "Bollinger mean-reversion"),
    "rmi_zero": _meta("RMI(20,5) 穿越 50", "rmi",
                      sig_rmi_zero, RMI_N + RMI_M + 20, "Roger Altman RMI"),
    "ssl_channel": _meta("SSL 通道", "ssl",
                         sig_ssl_channel, SSL_N + 20, "SSL channel"),
    "prev_day_hl": _meta("前1日高低突破", "breakout",
                         sig_prev_day_hl, PD_BARS + 20, "Prior-day high/low"),
    "swing3_break": _meta("3根擺動突破", "swing",
                          sig_swing3_break, 20, "3-bar swing break"),
    "engulfing": _meta("吞沒線", "candle",
                       sig_engulfing, 20, "Bull/bear engulfing"),
    "three_soldiers": _meta("三白兵／三烏鴉", "candle",
                            sig_three_soldiers, 20, "Three soldiers/crows"),
    "force_zero": _meta("Force Index(13) 零軸", "volume",
                        sig_force_zero, FORCE_N + 20, "Elder Force Index zero"),
    "cmf_zero": _meta("CMF(20) 零軸", "volume",
                      sig_cmf_zero, CMF_N + 20, "Chaikin MF zero"),
    "nvi_ema": _meta("NVI 交叉 EMA40", "volume",
                     sig_nvi_ema, NVI_EMA + 20, "Fosback NVI"),
    "tsf_cross": _meta("時間序列預測穿收盤", "lrs",
                       sig_tsf_cross, TSF_N + 20, "Time series forecast"),
    "heikin_both": _meta("HA 翻色無均線", "heikin",
                         sig_heikin_both, 20, "Heikin-Ashi flip both"),
    "ema_8_21": _meta("EMA8/21 交叉", "ma",
                      sig_ema_8_21, EMA_S2 + 20, "EMA 8/21"),
    "smma_cross": _meta("SMMA10/30 交叉", "ma",
                        sig_smma_cross, SMMA_S + 20, "Smoothed MA cross"),
    "typical_ma": _meta("典型價 SMA10/30", "ma",
                        sig_typical_ma, TYP_S + 20, "Typical-price MA"),
    "donchian10": _meta("Donchian 10/5 雙向", "turtle",
                        sig_donchian10, DON10_E + 20, "Donchian 10/5 no EMA"),
}

EXTRA_STRATS_LOOP["turtle_soup"]["max_hold_bars"] = SOUP_HOLD

# ── 第三批：仍未測、定義不同的公開規則 ──
MACD_SIG = 9
STO_N, STO_D, STO_LO, STO_HI = 14, 3, 20.0, 80.0
RSI_LO, RSI_HI = 30.0, 70.0
MFI_LO, MFI_HI = 20.0, 80.0
UO_LO, UO_HI = 30.0, 70.0
TRIX_SIG = 9
DON40_E, DON40_X = 40, 20
EMA12, EMA26 = 12, 26
SMA20, SMA50 = 20, 50
WMA20, WMA50 = 20, 50
HMA9, HMA21 = 9, 21
TEMA5, TEMA15 = 5, 15
PCTB_LO, PCTB_HI = 0.2, 0.8
AROON_N2 = 25
DPO_N = 20
MOM_N = 10
WEEK_BARS = 42
ORB_BARS = 6
OBV_EMA = 20
PVI_EMA = 40


def sig_macd_signal_both(O, H, L, C, V=None, tf=None):
    """MACD 交叉訊號線，無長均線。與 sim.macd／macd_zero 分開。"""
    e1 = sim.ema(C, 12)
    e2 = sim.ema(C, 26)
    macd = [(a - b) if (a is not None and b is not None) else None for a, b in zip(e1, e2)]
    sig = _ema_ok(macd, MACD_SIG)
    return _line_cross(macd, sig)


def sig_stoch_zone(O, H, L, C, V=None, tf=None):
    """Stochastic 在 <20 金叉做多、>80 死叉做空。來源：Lane 區域用法。與無過濾交叉分開。"""
    ll = sim.lowest(L, STO_N)
    hh = sim.highest(H, STO_N)
    n = len(C)
    k = [None] * n
    for i in range(n):
        if ll[i] is None or hh[i] is None:
            continue
        den = hh[i] - ll[i]
        k[i] = 50.0 if den <= 0 else 100.0 * (C[i] - ll[i]) / den
    d = _sma_ok(k, STO_D)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (k[i], d[i], k[i - 1], d[i - 1]):
            continue
        if k[i - 1] <= d[i - 1] and k[i] > d[i] and k[i] < STO_LO:
            el[i] = True
        if k[i] > 50:
            xl[i] = True
        if k[i - 1] >= d[i - 1] and k[i] < d[i] and k[i] > STO_HI:
            es[i] = True
        if k[i] < 50:
            xs[i] = True
    return el, xl, es, xs


def sig_rsi_zone(O, H, L, C, V=None, tf=None):
    """RSI 上穿 30 做多、下穿 70 做空；回 50 出場。來源：Wilder 超買超賣。"""
    rv = sim.rsi(C, 14)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if rv[i] is None or rv[i - 1] is None:
            continue
        if rv[i - 1] <= RSI_LO < rv[i]:
            el[i] = True
        if rv[i] > 50:
            xl[i] = True
        if rv[i - 1] >= RSI_HI > rv[i]:
            es[i] = True
        if rv[i] < 50:
            xs[i] = True
    return el, xl, es, xs


def sig_trix_signal(O, H, L, C, V=None, tf=None):
    """TRIX(15) 交叉 9 期訊號。與 trix_zero 分開。"""
    e1 = sim.ema(C, 15)
    e2 = sim.ema(e1, 15)
    e3 = sim.ema(e2, 15)
    n = len(C)
    trix = [None] * n
    for i in range(1, n):
        if e3[i] is None or e3[i - 1] in (None, 0):
            continue
        trix[i] = (e3[i] - e3[i - 1]) / e3[i - 1] * 100.0
    return _line_cross(trix, _ema_ok(trix, TRIX_SIG))


def sig_ao_saucer(O, H, L, C, V=None, tf=None):
    """AO 碟形：零軸上方兩根下降後一根上升做多，對稱做空。來源：Williams。"""
    mid = [(H[i] + L[i]) / 2.0 for i in range(len(C))]
    f = sim.sma(mid, 5)
    s = sim.sma(mid, 34)
    ao = [(a - b) if (a is not None and b is not None) else None for a, b in zip(f, s)]
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(3, n):
        if None in (ao[i], ao[i - 1], ao[i - 2], ao[i - 3]):
            continue
        if ao[i] > 0 and ao[i - 1] < ao[i - 2] < ao[i - 3] and ao[i] > ao[i - 1]:
            el[i] = True
        if ao[i] < 0:
            xl[i] = True
        if ao[i] < 0 and ao[i - 1] > ao[i - 2] > ao[i - 3] and ao[i] < ao[i - 1]:
            es[i] = True
        if ao[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_ichimoku_cloud(O, H, L, C, V=None, tf=None):
    """收盤站上／跌破雲（前移 26 的過去雲）。無 TK 條件。與 sim.ichimoku 分開。"""
    n = len(C)
    sa = [None] * n
    sb = [None] * n
    for i in range(n):
        if i >= 8 and i >= 25:
            ten = (max(H[i - 8:i + 1]) + min(L[i - 8:i + 1])) / 2
            kij = (max(H[i - 25:i + 1]) + min(L[i - 25:i + 1])) / 2
            sa[i] = (ten + kij) / 2
        if i >= 51:
            sb[i] = (max(H[i - 51:i + 1]) + min(L[i - 51:i + 1])) / 2
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(26, n):
        ca, cb = sa[i - 26], sb[i - 26]
        if ca is None or cb is None:
            continue
        top, bot = max(ca, cb), min(ca, cb)
        if C[i] > top and C[i - 1] <= top:
            el[i] = True
        if C[i] < bot:
            xl[i] = True
        if C[i] < bot and C[i - 1] >= bot:
            es[i] = True
        if C[i] > top:
            xs[i] = True
    return el, xl, es, xs


def sig_donchian40(O, H, L, C, V=None, tf=None):
    """Donchian 40/20 雙向無 EMA。"""
    hh_e = sim.highest(H, DON40_E)
    ll_e = sim.lowest(L, DON40_E)
    hh_x = sim.highest(H, DON40_X)
    ll_x = sim.lowest(L, DON40_X)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if hh_e[i - 1] is None or ll_e[i - 1] is None:
            continue
        if C[i] > hh_e[i - 1]:
            el[i] = True
        if C[i] < ll_e[i - 1]:
            es[i] = True
        if ll_x[i - 1] is not None and C[i] < ll_x[i - 1]:
            xl[i] = True
        if hh_x[i - 1] is not None and C[i] > hh_x[i - 1]:
            xs[i] = True
    return el, xl, es, xs


def sig_ema_12_26(O, H, L, C, V=None, tf=None):
    """EMA12/26 交叉。"""
    return _line_cross(sim.ema(C, EMA12), sim.ema(C, EMA26))


def sig_sma_20_50(O, H, L, C, V=None, tf=None):
    """SMA20/50 交叉。"""
    return _line_cross(sim.sma(C, SMA20), sim.sma(C, SMA50))


def sig_aroon_osc(O, H, L, C, V=None, tf=None):
    """Aroon Oscillator(25) 零軸。與 Aroon 交叉分開。"""
    n = len(C)
    osc = [None] * n
    for i in range(AROON_N2 - 1, n):
        hh = max(H[i - AROON_N2 + 1:i + 1])
        ll = min(L[i - AROON_N2 + 1:i + 1])
        sh = next((j for j in range(AROON_N2) if H[i - j] == hh), 0)
        sl = next((j for j in range(AROON_N2) if L[i - j] == ll), 0)
        osc[i] = 100.0 * (sl - sh) / AROON_N2
    return _osc_cross(osc, 0.0)


def sig_dpo_zero(O, H, L, C, V=None, tf=None):
    """Detrended Price Oscillator(20) 零軸。來源：公開 DPO。位移用已實現的 N/2+1。"""
    n = len(C)
    shift = DPO_N // 2 + 1
    ma = sim.sma(C, DPO_N)
    dpo = [None] * n
    for i in range(n):
        j = i - shift
        if j >= 0 and ma[j] is not None:
            dpo[i] = C[i] - ma[j]
    return _osc_cross(dpo, 0.0)


def sig_mom_zero(O, H, L, C, V=None, tf=None):
    """Momentum(10) 零軸。"""
    n = len(C)
    mom = [None] * n
    for i in range(MOM_N, n):
        mom[i] = C[i] - C[i - MOM_N]
    return _osc_cross(mom, 0.0)


def sig_week_hl(O, H, L, C, V=None, tf=None):
    """前 42 根 4H（1 週）高低突破。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(WEEK_BARS, n):
        hh = max(H[i - WEEK_BARS:i])
        ll = min(L[i - WEEK_BARS:i])
        if C[i] > hh and C[i - 1] <= hh:
            el[i] = True
        if C[i] < ll:
            xl[i] = True
        if C[i] < ll and C[i - 1] >= ll:
            es[i] = True
        if C[i] > hh:
            xs[i] = True
    return el, xl, es, xs


def sig_utc_orb(O, H, L, C, V=None, tf=None):
    """UTC 日第一根 4H 高低，當日後續突破。Opening Range。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    # 4H bars: 6 per UTC day. Group by day index from start.
    day_hi = [None] * n
    day_lo = [None] * n
    first = {}
    for i in range(n):
        day = i // ORB_BARS
        if day not in first:
            first[day] = i
            day_hi[i] = H[i]
            day_lo[i] = L[i]
        else:
            f = first[day]
            if i == f:
                continue
            if C[i] > H[f] and C[i - 1] <= H[f]:
                el[i] = True
            if C[i] < L[f]:
                xl[i] = True
            if C[i] < L[f] and C[i - 1] >= L[f]:
                es[i] = True
            if C[i] > H[f]:
                xs[i] = True
    return el, xl, es, xs


def sig_obv_ema_cross(O, H, L, C, V=None, tf=None):
    """OBV 交叉其 EMA20。與 sim.obv 趨勢過濾分開。"""
    n = len(C)
    V = V or [0.0] * n
    obv = [0.0] * n
    for i in range(1, n):
        if C[i] > C[i - 1]:
            obv[i] = obv[i - 1] + float(V[i] or 0.0)
        elif C[i] < C[i - 1]:
            obv[i] = obv[i - 1] - float(V[i] or 0.0)
        else:
            obv[i] = obv[i - 1]
    return _line_cross(obv, sim.ema(obv, OBV_EMA))


def sig_pvi_ema(O, H, L, C, V=None, tf=None):
    """Positive Volume Index 交叉 EMA40。來源：Fosback。"""
    n = len(C)
    V = V or [0.0] * n
    pvi = [1000.0] * n
    for i in range(1, n):
        pvi[i] = pvi[i - 1]
        if (V[i] or 0) > (V[i - 1] or 0) and C[i - 1]:
            pvi[i] = pvi[i - 1] * (1.0 + (C[i] - C[i - 1]) / C[i - 1])
    return _line_cross(pvi, sim.ema(pvi, PVI_EMA))


def sig_piercing(O, H, L, C, V=None, tf=None):
    """刺透／烏雲蓋頂。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        mid = (O[i - 1] + C[i - 1]) / 2.0
        if C[i - 1] < O[i - 1] and C[i] > O[i] and O[i] < C[i - 1] and C[i] > mid:
            el[i] = True
            xs[i] = True
        if C[i - 1] > O[i - 1] and C[i] < O[i] and O[i] > C[i - 1] and C[i] < mid:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_hammer(O, H, L, C, V=None, tf=None):
    """錘頭做多、射擊之星做空。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(n):
        body = abs(C[i] - O[i])
        rng = H[i] - L[i]
        if rng <= 0:
            continue
        lower = min(C[i], O[i]) - L[i]
        upper = H[i] - max(C[i], O[i])
        if lower >= 2 * max(body, rng * 0.1) and upper <= body:
            el[i] = True
            xs[i] = True
        if upper >= 2 * max(body, rng * 0.1) and lower <= body:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_bb_pctb(O, H, L, C, V=None, tf=None):
    """布林 %B 上穿 0.2 做多、下穿 0.8 做空。"""
    mid = sim.sma(C, 20)
    sd = sim.stdev(C, 20)
    n = len(C)
    pb = [None] * n
    for i in range(n):
        if mid[i] is None or sd[i] in (None, 0):
            continue
        lo = mid[i] - 2 * sd[i]
        hi = mid[i] + 2 * sd[i]
        pb[i] = (C[i] - lo) / (hi - lo) if hi != lo else 0.5
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if pb[i] is None or pb[i - 1] is None:
            continue
        if pb[i - 1] <= PCTB_LO < pb[i]:
            el[i] = True
        if pb[i] > 0.5:
            xl[i] = True
        if pb[i - 1] >= PCTB_HI > pb[i]:
            es[i] = True
        if pb[i] < 0.5:
            xs[i] = True
    return el, xl, es, xs


EXTRA_STRATS_LOOP.update({
    "macd_signal_both": _meta("MACD 交叉訊號線無均線", "macd",
                              sig_macd_signal_both, 50, "MACD signal no trend filter"),
    "stoch_zone": _meta("Stochastic 20/80 區域交叉", "stoch",
                        sig_stoch_zone, 30, "Lane stochastic zones"),
    "rsi_zone": _meta("RSI 30/70 區域", "rsi",
                      sig_rsi_zone, 30, "Wilder RSI zones"),
    "trix_signal": _meta("TRIX 交叉訊號 9", "trix",
                         sig_trix_signal, 65, "TRIX signal line"),
    "ao_saucer": _meta("AO 碟形", "williams",
                       sig_ao_saucer, 40, "Williams AO saucer"),
    "ichimoku_cloud": _meta("一目只破雲", "ichimoku",
                            sig_ichimoku_cloud, 80, "Price vs kumo only"),
    "donchian40": _meta("Donchian 40/20 雙向", "turtle",
                        sig_donchian40, 60, "Donchian 40/20"),
    "ema_12_26": _meta("EMA12/26 交叉", "ma",
                       sig_ema_12_26, 40, "EMA 12/26"),
    "sma_20_50": _meta("SMA20/50 交叉", "ma",
                       sig_sma_20_50, 60, "SMA 20/50"),
    "aroon_osc": _meta("Aroon Oscillator 零軸", "aroon",
                       sig_aroon_osc, 40, "Aroon oscillator"),
    "dpo_zero": _meta("DPO(20) 零軸", "dpo",
                      sig_dpo_zero, 40, "Detrended price oscillator"),
    "mom_zero": _meta("Momentum(10) 零軸", "mom",
                      sig_mom_zero, 20, "Momentum 10"),
    "week_hl": _meta("前1週高低突破", "breakout",
                     sig_week_hl, WEEK_BARS + 20, "Prior-week high/low"),
    "utc_orb": _meta("UTC 日內開盤區間突破", "orb",
                     sig_utc_orb, 20, "First-bar opening range"),
    "obv_ema_cross": _meta("OBV 交叉 EMA20", "volume",
                           sig_obv_ema_cross, 40, "OBV vs EMA"),
    "pvi_ema": _meta("PVI 交叉 EMA40", "volume",
                     sig_pvi_ema, 50, "Fosback PVI"),
    "piercing": _meta("刺透／烏雲蓋頂", "candle",
                      sig_piercing, 20, "Piercing / dark-cloud"),
    "hammer": _meta("錘頭／射擊之星", "candle",
                    sig_hammer, 20, "Hammer / shooting star"),
    "bb_pctb": _meta("布林 %B 0.2/0.8", "bb",
                     sig_bb_pctb, 40, "Bollinger %B zones"),
})
