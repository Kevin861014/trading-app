# -*- coding: utf-8 -*-
"""外人教科書策略 v5（參數凍結，禁止依結果改 lookback／止損）。

五套：trix_zero / kst_cross / ultimate_50 / cmo_zero / elder_ray。
與 v1–v4、sim 既有碼分開，不是掃參優化。
止損一律進場價 1%，撮合沿用 extra_strats_v3.simulate_fixed_mae。
只讀公開行情；不下單、不碰金鑰。
"""
from __future__ import annotations

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

# ── 凍結常數（寫死，禁止依場外結果改）────────────────────
TRIX_N = 15

KST_ROC = (10, 15, 20, 30)
KST_SMA = (10, 10, 10, 15)
KST_W = (1, 2, 3, 4)
KST_SIG = 9

UO_P = (7, 14, 28)
UO_W = (4, 2, 1)
UO_LVL = 50.0

CMO_N = 14
CMO_LVL = 0.0

ELDER_EMA = 13


def _empty(n):
    return [False] * n


def _sma_ok(vals, n):
    """只對已有值做 SMA；開頭不足則 None。"""
    out = [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        if any(x is None for x in w):
            continue
        out[i] = sum(w) / n
    return out


def _roc(C, n):
    out = [None] * len(C)
    for i in range(n, len(C)):
        prev = C[i - n]
        if prev and prev != 0:
            out[i] = (C[i] - prev) / prev * 100.0
    return out


def sig_trix_zero(O, H, L, C, V=None, tf=None):
    """TRIX(15) 零軸交叉雙向。

    TRIX = 三重 EMA 的百分比變化。上穿 0 做多、下穿 0 做空。
    來源：Jack Hutson, Technical Analysis of Stocks & Commodities, 1983。
    """
    e1 = sim.ema(C, TRIX_N)
    e2 = sim.ema(e1, TRIX_N)
    e3 = sim.ema(e2, TRIX_N)
    n = len(C)
    trix = [None] * n
    for i in range(1, n):
        if e3[i] is None or e3[i - 1] in (None, 0):
            continue
        trix[i] = (e3[i] - e3[i - 1]) / e3[i - 1] * 100.0
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if trix[i] is None or trix[i - 1] is None:
            continue
        if trix[i - 1] <= 0 < trix[i]:
            el[i] = True
            xs[i] = True
        if trix[i - 1] >= 0 > trix[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_kst_cross(O, H, L, C, V=None, tf=None):
    """Martin Pring KST 交叉其 9 期 SMA。

    ROC 10/15/20/30，再 SMA 10/10/10/15，權重 1/2/3/4。
    來源：Martin J. Pring, Technical Analysis Explained。
    """
    rcmas = []
    for look, sm, _w in zip(KST_ROC, KST_SMA, KST_W):
        rcmas.append(_sma_ok(_roc(C, look), sm))
    n = len(C)
    kst = [None] * n
    for i in range(n):
        parts = [r[i] for r in rcmas]
        if any(x is None for x in parts):
            continue
        kst[i] = sum(w * x for w, x in zip(KST_W, parts))
    sig = _sma_ok(kst, KST_SIG)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (kst[i], sig[i], kst[i - 1], sig[i - 1]):
            continue
        if kst[i - 1] <= sig[i - 1] and kst[i] > sig[i]:
            el[i] = True
            xs[i] = True
        if kst[i - 1] >= sig[i - 1] and kst[i] < sig[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_ultimate_50(O, H, L, C, V=None, tf=None):
    """Williams Ultimate Oscillator(7/14/28) 穿越 50。

    不加 30/70 超買超賣（那會變成事後加條件）。
    來源：Larry Williams, 1976 Ultimate Oscillator。
    """
    n = len(C)
    bp = [0.0] * n
    tr = [0.0] * n
    bp[0] = C[0] - L[0]
    tr[0] = H[0] - L[0]
    for i in range(1, n):
        bp[i] = C[i] - min(L[i], C[i - 1])
        tr[i] = max(H[i], C[i - 1]) - min(L[i], C[i - 1])
    avgs = []
    for p in UO_P:
        a = [None] * n
        sbp = str_ = 0.0
        for i in range(n):
            sbp += bp[i]
            str_ += tr[i]
            if i >= p:
                sbp -= bp[i - p]
                str_ -= tr[i - p]
            if i >= p - 1 and str_ > 0:
                a[i] = sbp / str_
        avgs.append(a)
    wsum = float(sum(UO_W))
    uo = [None] * n
    for i in range(n):
        parts = [a[i] for a in avgs]
        if any(x is None for x in parts):
            continue
        uo[i] = 100.0 * sum(w * x for w, x in zip(UO_W, parts)) / wsum
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if uo[i] is None or uo[i - 1] is None:
            continue
        if uo[i - 1] <= UO_LVL < uo[i]:
            el[i] = True
            xs[i] = True
        if uo[i - 1] >= UO_LVL > uo[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_cmo_zero(O, H, L, C, V=None, tf=None):
    """Chande Momentum Oscillator(14) 零軸交叉。

    CMO = 100 × (Σup − Σdn) / (Σup + Σdn)。
    來源：Tushar Chande, The New Technical Trader, 1994。
    """
    n = len(C)
    up = [0.0] * n
    dn = [0.0] * n
    for i in range(1, n):
        ch = C[i] - C[i - 1]
        up[i] = max(ch, 0.0)
        dn[i] = max(-ch, 0.0)
    cmo = [None] * n
    su = sd = 0.0
    for i in range(1, n):
        su += up[i]
        sd += dn[i]
        if i > CMO_N:
            su -= up[i - CMO_N]
            sd -= dn[i - CMO_N]
        if i >= CMO_N:
            den = su + sd
            cmo[i] = 100.0 * (su - sd) / den if den > 0 else 0.0
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if cmo[i] is None or cmo[i - 1] is None:
            continue
        if cmo[i - 1] <= CMO_LVL < cmo[i]:
            el[i] = True
            xs[i] = True
        if cmo[i - 1] >= CMO_LVL > cmo[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_elder_ray(O, H, L, C, V=None, tf=None):
    """Elder Ray：EMA13 趨勢 + Bull/Bear Power 轉折。

    多：EMA 上升、Bear Power<0 且見底回升。
    空：EMA 下降、Bull Power>0 且見頂回落。
    出場：EMA 反向傾斜。
    來源：Alexander Elder, Trading for a Living。
    與 v4 elder_impulse（EMA 斜率 + MACD 柱顏色）不是同一招。
    """
    e = sim.ema(C, ELDER_EMA)
    n = len(C)
    bull = [None] * n
    bear = [None] * n
    for i in range(n):
        if e[i] is None:
            continue
        bull[i] = H[i] - e[i]
        bear[i] = L[i] - e[i]
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(2, n):
        if None in (e[i], e[i - 1], bull[i], bull[i - 1], bull[i - 2],
                    bear[i], bear[i - 1], bear[i - 2]):
            continue
        rising = e[i] > e[i - 1]
        falling = e[i] < e[i - 1]
        if (rising and bear[i] < 0 and bear[i] > bear[i - 1]
                and bear[i - 1] < bear[i - 2]):
            el[i] = True
        if falling:
            xl[i] = True
        if (falling and bull[i] > 0 and bull[i] < bull[i - 1]
                and bull[i - 1] > bull[i - 2]):
            es[i] = True
        if rising:
            xs[i] = True
    return el, xl, es, xs


EXTRA_STRATS_V5 = {
    "trix_zero": {
        "name": "TRIX(15) 零軸交叉雙向",
        "family": "trix",
        "speed": "mid",
        "sided": "both",
        "build": sig_trix_zero,
        "max_hold_bars": None,
        "min_bars": TRIX_N * 3 + 20,
        "source": "Jack Hutson 1983 TRIX; triple EMA(15) percent change, zero cross",
    },
    "kst_cross": {
        "name": "Pring KST 交叉 9 期訊號線",
        "family": "kst",
        "speed": "mid",
        "sided": "both",
        "build": sig_kst_cross,
        "max_hold_bars": None,
        "min_bars": KST_ROC[-1] + KST_SMA[-1] + KST_SIG + 20,
        "source": "Martin Pring KST; ROC 10/15/20/30, SMA 10/10/10/15, w 1/2/3/4, signal 9",
    },
    "ultimate_50": {
        "name": "Williams Ultimate Oscillator 穿越 50",
        "family": "uo",
        "speed": "mid",
        "sided": "both",
        "build": sig_ultimate_50,
        "max_hold_bars": None,
        "min_bars": UO_P[-1] + 20,
        "source": "Larry Williams 1976 UO 7/14/28 weights 4/2/1; midpoint 50 only",
    },
    "cmo_zero": {
        "name": "Chande Momentum Oscillator(14) 零軸交叉",
        "family": "cmo",
        "speed": "mid",
        "sided": "both",
        "build": sig_cmo_zero,
        "max_hold_bars": None,
        "min_bars": CMO_N + 20,
        "source": "Tushar Chande 1994 CMO(14) zero cross",
    },
    "elder_ray": {
        "name": "Elder Ray：EMA13 + Bull/Bear Power 轉折",
        "family": "elder",
        "speed": "mid",
        "sided": "both",
        "build": sig_elder_ray,
        "max_hold_bars": None,
        "min_bars": ELDER_EMA + 20,
        "source": "Alexander Elder Trading for a Living; not Impulse System",
    },
}
