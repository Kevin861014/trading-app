# -*- coding: utf-8 -*-
"""外人教科書策略 v3（參數凍結，禁止依結果改 lookback／止損）。

五套：connors_rsi2 / ibs_fade / donchian100 / cci_zero / williams_r。
訊號 + 撮合（含 MAE）。止損一律進場價 1%，不在本檔改協議。
只讀公開行情；不下單、不碰金鑰。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
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
RSI2_N = 2
RSI2_LO = 10.0
RSI2_HI = 90.0
RSI2_X = 50.0
RSI2_MAX_HOLD = 8          # 最多 8 根 4H

IBS_LO = 0.2
IBS_HI = 0.8
IBS_HOLD = 2               # 抱 2 根 4H

DON_ENTER = 100
DON_EXIT = 50

CCI_N = 20
CCI_LVL = 0.0

WR_N = 14
WR_LO = -80.0
WR_HI = -20.0
WR_MAX_HOLD = 4            # 最多 4 根 4H

STOP_PCT = 0.01
COMMISSION = 0.0004
SLIPPAGE = 0.0002
CAPITAL = 1000.0
GRID_NOTIONAL = 1000.0


def _empty(n):
    return [False] * n


def _ts(T, i):
    return datetime.utcfromtimestamp(T[i] / 1000.0)


def _cost(px):
    return px * (COMMISSION + SLIPPAGE)


def _mae_pct(side, entry, H, L, a, b):
    """持有區間 [a, b] 含端點的最大不利偏移 / 進場價。"""
    if entry is None or entry <= 0 or a is None or b is None:
        return None
    if a < 0 or b < a or b >= len(H):
        return None
    if side == "long":
        m = min(L[a:b + 1])
        return max(0.0, (entry - m) / entry)
    m = max(H[a:b + 1])
    return max(0.0, (m - entry) / entry)


def williams_r(H, L, C, n=WR_N):
    """Williams %R = (HH-C)/(HH-LL)*-100。區間 0～-100。"""
    hh = sim.highest(H, n)
    ll = sim.lowest(L, n)
    out = [None] * len(C)
    for i in range(len(C)):
        if hh[i] is None or ll[i] is None:
            continue
        rng = hh[i] - ll[i]
        out[i] = -100.0 * (hh[i] - C[i]) / rng if rng > 0 else -50.0
    return out


def ibs_series(H, L, C):
    """IBS = (C-L)/(H-L)；零幅當 0.5。"""
    n = len(C)
    out = [None] * n
    for i in range(n):
        rng = H[i] - L[i]
        out[i] = ((C[i] - L[i]) / rng) if rng > 0 else 0.5
    return out


# ═══════════════ 1) Connors RSI(2) 均值回歸 ═══════════════
def sig_connors_rsi2(O, H, L, C, V=None, tf=None):
    """RSI(2)<10 做多、RSI(2)>90 做空；出場 RSI 穿越 50。

    時間出場（最多 8 根）在撮合端用 max_hold_bars，不在這裡改 lookback。
    """
    rv = sim.rsi(C, RSI2_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if rv[i] is None or rv[i - 1] is None:
            continue
        if rv[i] < RSI2_LO:
            el[i] = True
        if rv[i] > RSI2_HI:
            es[i] = True
        if rv[i - 1] < RSI2_X <= rv[i]:
            xl[i] = True
        if rv[i - 1] > RSI2_X >= rv[i]:
            xs[i] = True
    return el, xl, es, xs


# ═══════════════ 2) IBS fade ═══════════════
def sig_ibs_fade(O, H, L, C, V=None, tf=None):
    """IBS<0.2 做多、IBS>0.8 做空。無訊號出場；抱 2 根由撮合時間出場。"""
    ibs = ibs_series(H, L, C)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(n):
        if ibs[i] is None:
            continue
        if ibs[i] < IBS_LO:
            el[i] = True
        if ibs[i] > IBS_HI:
            es[i] = True
    return el, xl, es, xs


# ═══════════════ 3) Donchian 100/50 雙向突破 ═══════════════
def sig_donchian100(O, H, L, C, V=None, tf=None):
    """收盤突破前一根 100 通道進場；破 50 通道出場。無 EMA 過濾。

    與現有 sim.donchian（20/10 + EMA100 只做多）及 turtle 20/10、55/20 分開。
    """
    hh_e = sim.highest(H, DON_ENTER)
    ll_e = sim.lowest(L, DON_ENTER)
    hh_x = sim.highest(H, DON_EXIT)
    ll_x = sim.lowest(L, DON_EXIT)
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


# ═══════════════ 4) CCI(20) 零軸交叉 ═══════════════
def sig_cci_zero(O, H, L, C, V=None, tf=None):
    """CCI(20) 上穿 0 做多、下穿 0 做空；反向交叉出場。

    與現有 sim.cci（上穿 +100 + EMA100 只做多）不是同一招。
    """
    cc = sim.cci(H, L, C, CCI_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if cc[i] is None or cc[i - 1] is None:
            continue
        if cc[i - 1] <= CCI_LVL < cc[i]:
            el[i] = True
            xs[i] = True
        if cc[i - 1] >= CCI_LVL > cc[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


# ═══════════════ 5) Williams %R(14) ═══════════════
def sig_williams_r(O, H, L, C, V=None, tf=None):
    """W%R 跌破 -80 做多、升破 -20 做空；反向訊號出場。時間出場在撮合端。"""
    wr = williams_r(H, L, C, WR_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if wr[i] is None or wr[i - 1] is None:
            continue
        if wr[i - 1] >= WR_LO > wr[i]:
            el[i] = True
            xs[i] = True
        if wr[i - 1] <= WR_HI < wr[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


# ═══════════════ 通用 1% 價止損撮合（含 MAE、可選時間出場）═══════════════
def simulate_fixed_mae(T, O, H, L, C, el, xl, es=None, xs=None,
                       notional=GRID_NOTIONAL, start=CAPITAL,
                       max_hold_bars=None):
    """與 fixed_stop_backtest.simulate_fixed 同一條填單規則，多記 MAE。

    多 stop=entry*0.99；空 stop=entry*1.01。qty=notional/entry。
    max_hold_bars：持有滿 N 根（含進場根）後下一開盤時間出場。
    """
    n = len(C)
    if es is None:
        es = [False] * n
    if xs is None:
        xs = [False] * n
    eq = start
    pos = 0
    entry = 0.0
    qty = 0.0
    stop = None
    entry_i = None
    dates, equity, trades = [], [], []
    pos_series = [0] * n

    def close_trade(exit_i, exit_px, reason):
        nonlocal eq, pos, qty, stop, entry, entry_i
        fees = qty * _cost(exit_px) + qty * _cost(entry)
        if pos > 0:
            pnl = qty * (exit_px - entry) - fees
            side = "long"
        else:
            pnl = qty * (entry - exit_px) - fees
            side = "short"
        mae = _mae_pct(side, entry, H, L, entry_i, exit_i)
        et = _ts(T, entry_i if entry_i is not None else exit_i)
        xt = _ts(T, exit_i)
        if xt < et:
            xt = et
        trades.append({
            "entry_time": et, "exit_time": xt,
            "entry_price": float(entry), "exit_price": float(exit_px),
            "quantity": float(qty), "fees": float(fees),
            "pnl": float(pnl), "side": side, "reason": reason,
            "notional": float(notional), "mae_pct": mae,
        })
        eq += pnl
        pos = 0
        qty = 0.0
        stop = None
        entry_i = None

    for i in range(n - 1):
        o2 = O[i + 1]
        if pos > 0:
            if stop is not None and L[i] <= stop:
                close_trade(i, min(stop, O[i]), "stop")
        elif pos < 0:
            if stop is not None and H[i] >= stop:
                close_trade(i, max(stop, O[i]), "stop")
        if pos > 0 and xl[i]:
            close_trade(i + 1, o2, "signal")
        elif pos < 0 and xs[i]:
            close_trade(i + 1, o2, "signal")
        if (pos != 0 and max_hold_bars is not None and entry_i is not None
                and (i - entry_i + 1) >= max_hold_bars):
            close_trade(i + 1, o2, "time")
        if pos == 0 and el[i] and o2 > 0:
            entry = o2
            entry_i = i + 1
            qty = notional / entry
            stop = entry * (1.0 - STOP_PCT)
            pos = 1
        elif pos == 0 and es[i] and o2 > 0:
            entry = o2
            entry_i = i + 1
            qty = notional / entry
            stop = entry * (1.0 + STOP_PCT)
            pos = -1
        mtm = eq
        if pos > 0:
            mtm = eq + qty * (C[i + 1] - entry)
        elif pos < 0:
            mtm = eq + qty * (entry - C[i + 1])
        dates.append(_ts(T, i + 1))
        equity.append(mtm)
        pos_series[i + 1] = pos
    return dates, equity, trades, pos_series


EXTRA_STRATS_V3 = {
    "connors_rsi2": {
        "name": "Connors RSI(2)<10/>90，穿越 50 或最多 8 根 4H",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_connors_rsi2,
        "max_hold_bars": RSI2_MAX_HOLD,
        "min_bars": 30,
        "source": "Larry Connors RSI(2) mean-reversion; 教科書門檻 10/90/50，非 CRSI 複合",
    },
    "ibs_fade": {
        "name": "IBS fade：IBS<0.2 多 / >0.8 空，抱 2 根 4H",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_ibs_fade,
        "max_hold_bars": IBS_HOLD,
        "min_bars": 10,
        "source": "Connors Internal Bar Strength; 教科書 0.2/0.8，固定抱 2 根",
    },
    "donchian100": {
        "name": "Donchian 100/50 雙向突破（非 20/10、無 EMA 過濾）",
        "family": "turtle",
        "speed": "slow_turtle",
        "sided": "both",
        "build": sig_donchian100,
        "max_hold_bars": None,
        "min_bars": DON_ENTER + 20,
        "source": "Donchian / Turtle 通道 100/50；與 sim.donchian 20/10+EMA100 分開",
    },
    "cci_zero": {
        "name": "CCI(20) 零軸交叉雙向，反向交叉出場",
        "family": "cci",
        "speed": "mid",
        "sided": "both",
        "build": sig_cci_zero,
        "max_hold_bars": None,
        "min_bars": CCI_N + 20,
        "source": "Lambert CCI 零軸交叉；與 sim.cci 上穿+100+EMA 分開",
    },
    "williams_r": {
        "name": "Williams %R(14) 跌破 -80 / 升破 -20，反向或最多 4 根",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_williams_r,
        "max_hold_bars": WR_MAX_HOLD,
        "min_bars": WR_N + 20,
        "source": "Larry Williams %R 教科書超買超賣 -20/-80",
    },
}
