# -*- coding: utf-8 -*-
"""外人教科書策略 v6（參數凍結，禁止依場外改 lookback）。

開跑前寫死，不是看完幣安結果再發明。與 v1–v5、sim 既有碼分開。
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

MFI_N = 14
PPO_F, PPO_S = 12, 26
WMA_F, WMA_S = 10, 30
SMA_F, SMA_S = 10, 40
TSI_LONG, TSI_SHORT = 25, 13
CCI_N, CCI_TRIG = 20, 100
BB_N, BB_K = 20, 2.0
ADX_N, ADX_MIN = 14, 25


def _empty(n):
    return [False] * n


def _mfi(H, L, C, V, n):
    tp = [(h + l + c) / 3.0 for h, l, c in zip(H, L, C)]
    out = [None] * len(C)
    for i in range(n, len(C)):
        pos = neg = 0.0
        for j in range(i - n + 1, i + 1):
            mf = tp[j] * (V[j] or 0.0)
            if tp[j] > tp[j - 1]:
                pos += mf
            elif tp[j] < tp[j - 1]:
                neg += mf
        if neg == 0:
            out[i] = 100.0 if pos > 0 else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + pos / neg)
    return out


def _tsi(C, long_n, short_n):
    n = len(C)
    pc = [None] * n
    for i in range(1, n):
        pc[i] = C[i] - C[i - 1]
    apc = [None if x is None else abs(x) for x in pc]
    e1 = sim.ema(pc, long_n)
    e2 = sim.ema(e1, short_n)
    a1 = sim.ema(apc, long_n)
    a2 = sim.ema(a1, short_n)
    out = [None] * n
    for i in range(n):
        if e2[i] is None or a2[i] in (None, 0):
            continue
        out[i] = 100.0 * e2[i] / a2[i]
    return out


def sig_mfi_50(O, H, L, C, V=None, tf=None):
    """MFI(14) 穿越 50。來源：Quong/Soudack money flow index。"""
    m = _mfi(H, L, C, V or [0.0] * len(C), MFI_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if m[i] is None or m[i - 1] is None:
            continue
        if m[i - 1] <= 50 and m[i] > 50:
            el[i] = True
        if m[i] < 50:
            xl[i] = True
        if m[i - 1] >= 50 and m[i] < 50:
            es[i] = True
        if m[i] > 50:
            xs[i] = True
    return el, xl, es, xs


def sig_ppo_zero(O, H, L, C, V=None, tf=None):
    """PPO(12,26) 零軸交叉。來源：Appel 百分比 MACD。"""
    f = sim.ema(C, PPO_F)
    s = sim.ema(C, PPO_S)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    ppo = [None] * n
    for i in range(n):
        if f[i] is None or s[i] in (None, 0):
            continue
        ppo[i] = (f[i] - s[i]) / s[i] * 100.0
    for i in range(1, n):
        if ppo[i] is None or ppo[i - 1] is None:
            continue
        if ppo[i - 1] <= 0 and ppo[i] > 0:
            el[i] = True
        if ppo[i] < 0:
            xl[i] = True
        if ppo[i - 1] >= 0 and ppo[i] < 0:
            es[i] = True
        if ppo[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_wma_10_30(O, H, L, C, V=None, tf=None):
    """WMA10/30 交叉。來源：經典加權均線交叉。"""
    f = sim.wma(C, WMA_F)
    s = sim.wma(C, WMA_S)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (f[i], f[i - 1], s[i], s[i - 1]):
            continue
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            el[i] = True
        if f[i] < s[i]:
            xl[i] = True
        if f[i - 1] >= s[i - 1] and f[i] < s[i]:
            es[i] = True
        if f[i] > s[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_sma_10_40(O, H, L, C, V=None, tf=None):
    """SMA10/40 交叉。來源：經典簡單均線，非 50/200、非 EMA20/50。"""
    f = sim.sma(C, SMA_F)
    s = sim.sma(C, SMA_S)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (f[i], f[i - 1], s[i], s[i - 1]):
            continue
        if f[i - 1] <= s[i - 1] and f[i] > s[i]:
            el[i] = True
        if f[i] < s[i]:
            xl[i] = True
        if f[i - 1] >= s[i - 1] and f[i] < s[i]:
            es[i] = True
        if f[i] > s[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_tsi_zero(O, H, L, C, V=None, tf=None):
    """TSI(25,13) 零軸交叉。來源：William Blau True Strength Index。"""
    t = _tsi(C, TSI_LONG, TSI_SHORT)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if t[i] is None or t[i - 1] is None:
            continue
        if t[i - 1] <= 0 and t[i] > 0:
            el[i] = True
        if t[i] < 0:
            xl[i] = True
        if t[i - 1] >= 0 and t[i] < 0:
            es[i] = True
        if t[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_cci_pm100(O, H, L, C, V=None, tf=None):
    """CCI(20) 穿越 ±100。來源：Lambert；與零軸交叉、sim.cci(+100+EMA) 分開。"""
    c = sim.cci(H, L, C, CCI_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if c[i] is None or c[i - 1] is None:
            continue
        if c[i - 1] <= CCI_TRIG and c[i] > CCI_TRIG:
            el[i] = True
        if c[i] < 0:
            xl[i] = True
        if c[i - 1] >= -CCI_TRIG and c[i] < -CCI_TRIG:
            es[i] = True
        if c[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_boll_mid(O, H, L, C, V=None, tf=None):
    """收盤穿越布林中軌 SMA20。來源：Bollinger；非 bbreak 上下軌突破。"""
    mid = sim.sma(C, BB_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if mid[i] is None or mid[i - 1] is None:
            continue
        if C[i - 1] <= mid[i - 1] and C[i] > mid[i]:
            el[i] = True
        if C[i] < mid[i]:
            xl[i] = True
        if C[i - 1] >= mid[i - 1] and C[i] < mid[i]:
            es[i] = True
        if C[i] > mid[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_adx_di(O, H, L, C, V=None, tf=None):
    """+DI/-DI 交叉且 ADX>25。來源：Wilder；無均線趨勢過濾（與 sim.diadx 分開）。"""
    pdi, mdi, adx = sim.dmi(H, L, C, ADX_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (pdi[i], pdi[i - 1], mdi[i], mdi[i - 1], adx[i]):
            continue
        if adx[i] < ADX_MIN:
            continue
        if pdi[i - 1] <= mdi[i - 1] and pdi[i] > mdi[i]:
            el[i] = True
        if pdi[i] < mdi[i]:
            xl[i] = True
        if mdi[i - 1] <= pdi[i - 1] and mdi[i] > pdi[i]:
            es[i] = True
        if mdi[i] < pdi[i]:
            xs[i] = True
    return el, xl, es, xs


EXTRA_STRATS_V6 = {
    "mfi_50": {
        "name": "MFI(14) 穿越 50",
        "family": "volume",
        "speed": "mid",
        "sided": "both",
        "build": sig_mfi_50,
        "min_bars": MFI_N + 20,
        "source": "Quong/Soudack MFI; midpoint 50",
    },
    "ppo_zero": {
        "name": "PPO(12,26) 零軸交叉",
        "family": "macd",
        "speed": "mid",
        "sided": "both",
        "build": sig_ppo_zero,
        "min_bars": PPO_S + 20,
        "source": "Gerald Appel PPO; not sim.macd histogram",
    },
    "wma_10_30": {
        "name": "WMA10/30 交叉",
        "family": "ma",
        "speed": "mid",
        "sided": "both",
        "build": sig_wma_10_30,
        "min_bars": WMA_S + 20,
        "source": "Classic WMA cross 10/30",
    },
    "sma_10_40": {
        "name": "SMA10/40 交叉",
        "family": "ma",
        "speed": "mid",
        "sided": "both",
        "build": sig_sma_10_40,
        "min_bars": SMA_S + 20,
        "source": "Classic SMA cross 10/40; not golden 50/200",
    },
    "tsi_zero": {
        "name": "TSI(25,13) 零軸交叉",
        "family": "tsi",
        "speed": "mid",
        "sided": "both",
        "build": sig_tsi_zero,
        "min_bars": TSI_LONG + TSI_SHORT + 20,
        "source": "William Blau True Strength Index 25/13",
    },
    "cci_pm100": {
        "name": "CCI(20) 穿越 ±100",
        "family": "cci",
        "speed": "mid",
        "sided": "both",
        "build": sig_cci_pm100,
        "min_bars": CCI_N + 20,
        "source": "Lambert CCI ±100; not zero-cross, not sim.cci+EMA",
    },
    "boll_mid": {
        "name": "收盤穿越布林中軌 SMA20",
        "family": "bollinger",
        "speed": "mid",
        "sided": "both",
        "build": sig_boll_mid,
        "min_bars": BB_N + 20,
        "source": "Bollinger midline; not bbreak outer-band",
    },
    "adx_di": {
        "name": "+DI/-DI 交叉且 ADX>25（無均線過濾）",
        "family": "dmi",
        "speed": "mid",
        "sided": "both",
        "build": sig_adx_di,
        "min_bars": ADX_N * 2 + 20,
        "source": "Wilder DMI/ADX; not sim.diadx trend filter",
    },
}
