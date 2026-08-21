# -*- coding: utf-8 -*-
"""公開／教科書策略 v4（參數凍結，禁止依結果改 lookback）。

把已公布的指標做成完整進出場，不是掃參優化。
來源寫在各條 source；常數寫死。
回傳 (el, xl, es, xs)。只讀公開行情。
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

# ── 凍結常數（寫死，禁止優化）────────────────────────────────
ELDER_EMA = 13
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIG = 9

AROON_N = 25

AO_FAST = 5
AO_SLOW = 34

STOCH_N = 14
STOCH_D = 3

GOLDEN_FAST = 50
GOLDEN_SLOW = 200


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


def sig_elder_impulse(O, H, L, C, V=None, tf=None):
    """Elder Impulse：EMA13 斜率 + MACD 柱同向。

    綠柱（EMA上升且柱>0）轉多；紅柱轉空；非綠平多、非紅平空。
    來源：Alexander Elder, Come Into My Trading Room。
    """
    e = sim.ema(C, ELDER_EMA)
    ef = sim.ema(C, MACD_FAST)
    es = sim.ema(C, MACD_SLOW)
    macd = [(a - b) if (a is not None and b is not None) else None for a, b in zip(ef, es)]
    sg = sim.ema(macd, MACD_SIG)
    n = len(C)
    el, xl, esig, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    color = [0] * n  # 1 green, -1 red, 0 blue
    for i in range(1, n):
        if None in (e[i], e[i - 1], macd[i], sg[i]):
            continue
        hist = macd[i] - sg[i]
        rising = e[i] > e[i - 1]
        falling = e[i] < e[i - 1]
        if rising and hist > 0:
            color[i] = 1
        elif falling and hist < 0:
            color[i] = -1
        else:
            color[i] = 0
        if color[i] == 1 and color[i - 1] != 1:
            el[i] = True
        if color[i] != 1:
            xl[i] = True
        if color[i] == -1 and color[i - 1] != -1:
            esig[i] = True
        if color[i] != -1:
            xs[i] = True
    return el, xl, esig, xs


def sig_aroon_cross(O, H, L, C, V=None, tf=None):
    """Aroon(25) Up 上穿 Down 做多、下穿做空。

    來源：Tushar Chande, 1995 Technical Analysis of Stocks & Commodities。
    """
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    up = [None] * n
    dn = [None] * n
    w = AROON_N
    for i in range(w - 1, n):
        hh = max(H[i - w + 1:i + 1])
        ll = min(L[i - w + 1:i + 1])
        since_h = next((j for j in range(w) if H[i - j] == hh), 0)
        since_l = next((j for j in range(w) if L[i - j] == ll), 0)
        up[i] = 100.0 * (w - since_h) / w
        dn[i] = 100.0 * (w - since_l) / w
    for i in range(1, n):
        if None in (up[i], dn[i], up[i - 1], dn[i - 1]):
            continue
        if up[i - 1] <= dn[i - 1] and up[i] > dn[i]:
            el[i] = True
            xs[i] = True
        if up[i - 1] >= dn[i - 1] and up[i] < dn[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_ao_zero(O, H, L, C, V=None, tf=None):
    """Awesome Oscillator 零軸交叉。

    AO = SMA(HL2,5) − SMA(HL2,34)。上穿 0 多、下穿 0 空。
    來源：Bill Williams, Trading Chaos。
    """
    mid = [(H[i] + L[i]) / 2.0 for i in range(len(C))]
    f = sim.sma(mid, AO_FAST)
    s = sim.sma(mid, AO_SLOW)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    ao = [(a - b) if (a is not None and b is not None) else None for a, b in zip(f, s)]
    for i in range(1, n):
        if ao[i] is None or ao[i - 1] is None:
            continue
        if ao[i - 1] <= 0 < ao[i]:
            el[i] = True
            xs[i] = True
        if ao[i - 1] >= 0 > ao[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_stoch_cross(O, H, L, C, V=None, tf=None):
    """Stochastic %K(14) 上穿／下穿 %D(3)。

    來源：George Lane 隨機指標交叉；不加 20/80 過濾（那會變成事後加條件）。
    """
    ll = sim.lowest(L, STOCH_N)
    hh = sim.highest(H, STOCH_N)
    n = len(C)
    k = [None] * n
    for i in range(n):
        if ll[i] is None or hh[i] is None:
            continue
        den = hh[i] - ll[i]
        if den <= 0:
            k[i] = 50.0
        else:
            k[i] = 100.0 * (C[i] - ll[i]) / den
    d = _sma_ok(k, STOCH_D)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (k[i], d[i], k[i - 1], d[i - 1]):
            continue
        if k[i - 1] <= d[i - 1] and k[i] > d[i]:
            el[i] = True
            xs[i] = True
        if k[i - 1] >= d[i - 1] and k[i] < d[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_golden_50_200(O, H, L, C, V=None, tf=None):
    """SMA50 上穿 SMA200 做多、下穿做空。

    與 sim.ema_cross(20/50) 不同，也與 ema50_200_adx（EMA+ADX 只做多）不同。
    來源：經典黃金／死亡交叉。
    """
    f = sim.sma(C, GOLDEN_FAST)
    s = sim.sma(C, GOLDEN_SLOW)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (f[i], s[i], f[i - 1], s[i - 1]):
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


EXTRA_STRATS_V4 = {
    "elder_impulse": {
        "name": "Elder Impulse：EMA13 斜率 + MACD 柱同向",
        "family": "elder",
        "speed": "mid",
        "sided": "both",
        "build": sig_elder_impulse,
        "min_bars": MACD_SLOW + MACD_SIG + 20,
        "source": "Alexander Elder, Come Into My Trading Room; EMA13 + MACD(12/26/9) hist",
    },
    "aroon_cross": {
        "name": "Aroon(25) Up/Down 交叉雙向",
        "family": "aroon",
        "speed": "mid",
        "sided": "both",
        "build": sig_aroon_cross,
        "min_bars": AROON_N + 20,
        "source": "Tushar Chande 1995 Aroon; period 25",
    },
    "ao_zero": {
        "name": "Williams Awesome Oscillator 零軸交叉",
        "family": "williams",
        "speed": "mid",
        "sided": "both",
        "build": sig_ao_zero,
        "min_bars": AO_SLOW + 20,
        "source": "Bill Williams Trading Chaos; SMA5−SMA34 of HL2",
    },
    "stoch_cross": {
        "name": "Lane Stochastic %K(14)/%D(3) 交叉雙向",
        "family": "stoch",
        "speed": "fast",
        "sided": "both",
        "build": sig_stoch_cross,
        "min_bars": STOCH_N + STOCH_D + 20,
        "source": "George Lane stochastic cross; no 20/80 filter",
    },
    "golden_50_200": {
        "name": "SMA50/200 黃金／死亡交叉雙向",
        "family": "ma",
        "speed": "slow_ma",
        "sided": "both",
        "build": sig_golden_50_200,
        "min_bars": GOLDEN_SLOW + 20,
        "source": "Classic golden/death cross; not ema_cross 20/50, not ema50_200_adx",
    },
}

# sim.py 已有、但 3R 協議還沒掃過的公開系統（參數已在 sim 凍結）
SIM_ROUND3_CODES = (
    "ichimoku", "macd", "psar", "diadx", "bbreak", "vortex",
    "hma", "rsi50", "kama", "heikin", "lrs", "cci", "obv", "cmf",
)

SIM_ROUND3_FAMILY = {
    "ichimoku": "ichimoku",
    "macd": "macd",
    "psar": "psar",
    "diadx": "dmi",
    "bbreak": "breakout",
    "vortex": "vortex",
    "hma": "ma",
    "rsi50": "rsi",
    "kama": "kama",
    "heikin": "heikin",
    "lrs": "lrs",
    "cci": "cci",
    "obv": "volume",
    "cmf": "volume",
}

# v3 已宣告、3R 還沒跑的趨勢向規則（fade 不進本輪：3R 寬停損不適合）
V3_ROUND3_CODES = ("cci_zero",)
