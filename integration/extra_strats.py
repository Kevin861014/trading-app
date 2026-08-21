# -*- coding: utf-8 -*-
"""外人教科書策略（參數凍結，禁止依結果改 lookback）。

來源是公開經典定義，不是本專案調參。現有 sim.tsmom 是 look=40 + EMA100
過濾，與 TSMOM_12m（12*30*6 根 4H）不是同一招，不要雙計。

現有 sim.donchian 是 20/10 + EMA100 只做多；海龜無長均線過濾、可多可空。

【已退役 2026-08-18 統整】dual_mom：宇宙級多商品輪動、非單幣格，結構不相容，
自可用清單移除（研究檔案保留，不刪碼）。
"""
from __future__ import annotations

import sys
import os
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
TURTLE_S1_ENTER = 20
TURTLE_S1_EXIT = 10
TURTLE_S2_ENTER = 55
TURTLE_S2_EXIT = 20
TSMOM_12M_BARS = 12 * 30 * 6          # 2160 根 4H ≈ 12 個月
EMA_FAST = 50
EMA_SLOW = 200
ADX_LEN = 14
ADX_MIN = 25
DUAL_MOM_UNIVERSE = ("BTC-USD", "ETH-USD", "PAXG-USD")  # 辯論後縮宇宙
DUAL_MOM_LOOK = 12 * 30 * 6
# 現有 tsmom 不是 12m：sim.sig_tsmom look=40, trend=100
EXISTING_TSMOM_IS_12M = False


def _empty(n):
    return [False] * n


def sig_turtle(O, H, L, C, n_enter, n_exit):
    """經典海龜通道：收盤突破 n_enter 高/低進場，反向 n_exit 通道出場。

    多空都做。不用 EMA 趨勢過濾（那是現有 donchian 的改法）。
    慣例：第 i 棒收盤確認，第 i+1 棒開盤成交。
    回傳 (el, xl, es, xs)。
    """
    hh_e = sim.highest(H, n_enter)
    ll_e = sim.lowest(L, n_enter)
    hh_x = sim.highest(H, n_exit)
    ll_x = sim.lowest(L, n_exit)
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


def sig_turtle_s1(O, H, L, C, V=None, tf=None):
    return sig_turtle(O, H, L, C, TURTLE_S1_ENTER, TURTLE_S1_EXIT)


def sig_turtle_s2(O, H, L, C, V=None, tf=None):
    return sig_turtle(O, H, L, C, TURTLE_S2_ENTER, TURTLE_S2_EXIT)


def sig_tsmom_12m(O, H, L, C, V=None, tf=None, look=TSMOM_12M_BARS):
    """時間序列動能 12 個月：過去 look 根報酬 >0 做多、<0 做空。

    這是部位狀態（Moskowitz / Ooi / Pedersen TSMOM），不是 40 根交叉。
    look 寫死 2160，樣本不夠就標 insufficient，不准改短。
    回傳 (el, xl, es, xs)。
    """
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    if n <= look + 1:
        return el, xl, es, xs
    want = [0] * n
    for i in range(look, n):
        prev = C[i - look]
        if prev and prev > 0:
            want[i] = 1 if C[i] > prev else -1
    for i in range(look + 1, n):
        if want[i] == 1 and want[i - 1] != 1:
            el[i] = True
        if want[i] != 1:
            xl[i] = True
        if want[i] == -1 and want[i - 1] != -1:
            es[i] = True
        if want[i] != -1:
            xs[i] = True
    return el, xl, es, xs


def sig_ema50_200_adx(O, H, L, C, V=None, tf=None):
    """收盤站上 EMA50 且 EMA50>EMA200 且 ADX>25 做多；
    跌破 EMA50 或 EMA50<EMA200 出場。只做多。
    回傳 (el, xl, es, xs)，空單永遠 False。
    """
    e50 = sim.ema(C, EMA_FAST)
    e200 = sim.ema(C, EMA_SLOW)
    _pdi, _ndi, adx = sim.dmi(H, L, C, ADX_LEN)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    on = False
    for i in range(1, n):
        if None in (e50[i], e200[i], adx[i], e50[i - 1], e200[i - 1]):
            continue
        long_ok = C[i] > e50[i] and e50[i] > e200[i] and adx[i] > ADX_MIN
        must_exit = C[i] < e50[i] or e50[i] < e200[i]
        if (not on) and long_ok:
            el[i] = True
            on = True
        if on and must_exit:
            xl[i] = True
            on = False
    return el, xl, es, xs


def dual_mom_positions(series_map, look=DUAL_MOM_LOOK):
    """宇宙內相對強者 + 絕對動能（對現金：12m 報酬>0 才做多）。

    series_map: {ticker: {"T","O","H","L","C"}} 已對齊或未對齊皆可。
    回傳依時間排序的持倉清單 [(ts, ticker_or_None)]，ticker=None 為現金。
    宇宙凍結為 BTC/ETH/PAXG。
    """
    # 以時間戳做 inner join
    keys = [k for k in DUAL_MOM_UNIVERSE if k in series_map and series_map[k].get("T")]
    if len(keys) < 2:
        return [], keys
    ts_sets = [set(series_map[k]["T"]) for k in keys]
    common = ts_sets[0]
    for s in ts_sets[1:]:
        common &= s
    common = sorted(common)
    if len(common) <= look + 1:
        return [], keys
    idx = {k: {t: i for i, t in enumerate(series_map[k]["T"])} for k in keys}
    held = []
    prev = None
    for j, ts in enumerate(common):
        if j < look:
            held.append((ts, None))
            continue
        rets = {}
        for k in keys:
            i = idx[k][ts]
            i0 = idx[k][common[j - look]]
            c1 = series_map[k]["C"][i]
            c0 = series_map[k]["C"][i0]
            if c0 and c0 > 0 and c1 and c1 > 0:
                rets[k] = c1 / c0 - 1.0
        if not rets:
            pick = None
        else:
            best = max(rets, key=rets.get)
            pick = best if rets[best] > 0 else None  # 絕對動能：輸現金則空手
        held.append((ts, pick))
        prev = pick
    return held, keys


def dual_mom_trades_from_held(held, series_map):
    """把持倉序列轉成『換倉』訊號：在持倉變化的那根，對舊標的出場、新標的進場。

    回傳 {ticker: (el, xl, es, xs)}，長度對齊該 ticker 的 bars。
    """
    out = {}
    for k, s in series_map.items():
        n = len(s["C"])
        out[k] = (_empty(n), _empty(n), _empty(n), _empty(n))
    ts_to_i = {k: {t: i for i, t in enumerate(series_map[k]["T"])} for k in series_map}
    prev = None
    for ts, pick in held:
        if pick == prev:
            continue
        if prev is not None and prev in ts_to_i and ts in ts_to_i[prev]:
            i = ts_to_i[prev][ts]
            out[prev][1][i] = True  # xl
        if pick is not None and pick in ts_to_i and ts in ts_to_i[pick]:
            i = ts_to_i[pick][ts]
            out[pick][0][i] = True  # el
        prev = pick
    return out


EXTRA_STRATS = {
    "turtle_s1": {
        "name": "海龜 S1 Donchian 20/10（經典，無均線過濾）",
        "build": sig_turtle_s1,
        "sided": "both",
        "family": "turtle",
        "speed": "fast_turtle",
        "symbols_allow": ("BTC-USD", "ETH-USD", "PAXG-USD"),  # 只測這三檔
    },
    "turtle_s2": {
        "name": "海龜 S2 Donchian 55/20（經典慢突破）",
        "build": sig_turtle_s2,
        "sided": "both",
        "family": "turtle",
        "speed": "slow_turtle",
        "symbols_allow": None,
    },
    "tsmom_12m": {
        "name": "TSMOM 12m（4H×2160 根，非 sim.tsmom look=40）",
        "build": sig_tsmom_12m,
        "sided": "both",
        "family": "tsmom",
        "speed": "slow_mom",
        "symbols_allow": None,
        "min_bars": TSMOM_12M_BARS + 220,
    },
    "ema50_200_adx": {
        "name": "EMA50/200 + ADX>25（教科書均線，多頭）",
        "build": sig_ema50_200_adx,
        "sided": "long",
        "family": "ema_adx",
        "speed": "slow_ma",
        "symbols_allow": None,
    },
    "dual_mom": {
        "name": "Dual Momentum（宇宙 BTC/ETH/PAXG，絕對動能對現金）",
        "build": None,  # 宇宙級，見 dual_mom_* 
        "sided": "long",
        "family": "tsmom",
        "speed": "slow_mom",
        "symbols_allow": DUAL_MOM_UNIVERSE,
        "universe": True,
        "min_bars": DUAL_MOM_LOOK + 220,
    },
}

# 現有 sim 策略（只用訊號，止損改 1% 價）
EXISTING_POOL = (
    "sixline", "supertrend", "tsmom", "donchian", "vwap",
    "keltner", "ttm", "trend", "volbreak", "ema_cross",
)

EXISTING_FAMILY = {
    "sixline": "ma",
    "supertrend": "supertrend",  # 不進籃
    "tsmom": "tsmom_fast",       # look=40，不是 12m
    "donchian": "turtle",        # 20/10 + EMA100，與海龜同族
    "vwap": "vwap",
    "keltner": "breakout",
    "ttm": "breakout",
    "trend": "ma",
    "volbreak": "breakout",
    "ema_cross": "ma",
}

EXISTING_SPEED = {
    "sixline": "mid",
    "supertrend": "mid",
    "tsmom": "fast_mom",
    "donchian": "fast_turtle",
    "vwap": "mid",
    "keltner": "mid",
    "ttm": "mid",
    "trend": "mid",
    "volbreak": "mid",
    "ema_cross": "mid",
}
