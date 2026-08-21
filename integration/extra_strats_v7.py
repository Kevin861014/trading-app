# -*- coding: utf-8 -*-
"""外人教科書策略 v7（參數凍結，禁止依場外改 lookback）。

【參數凍結聲明】以下所有參數在 2026-08-17 開跑前寫死，**不是**看完幣安
回測結果再發明或再調。回測結果不理想也不回頭改 lookback／門檻／持有根數，
只在報告中註明失敗。與 v1–v6、sim 既有碼、extra_strats_loop 池全部不重複。

凍結清單（策略 code → 參數 → 文獻）：
  vhf_trend   : VHF 收盤價 28 根、上門檻 0.40、下門檻 0.30、EMA(50) 方向過濾
                （Adam White, "Vertical Horizontal Filter", TASC 1991）
  chop_trend  : Choppiness Index 14 根、盤整線 61.8、趨勢線 38.2、SMA(50) 方向過濾
                （Bill Dreiss, "Choppiness Index", TASC 1990s）
  pgo_zero    : Pretty Good Oscillator 14 根零軸
                （Mark Johnson, "Pretty Good Oscillator", TASC 2003）
  bop_zero    : Balance of Power SMA(14) 零軸
                （Igor Livshin, "Balance of Power", TASC 2001-08）
  tii_80_20   : Trend Intensity Index 主 60 / 次 30、上 80 下 20 中 50
                （M.H. Pee, "Trend Intensity Index", TASC 2003-06）
  ttf_pm100   : Trend Trigger Factor 15 根、±100 觸發、零軸出場
                （M.H. Pee, "Trend Trigger Factor", TASC 2004-12）
  vwma_sma    : VWMA(20) 對 SMA(20) 交叉
                （Buff Dormeier, "Investing with Volume Analysis", 2011）
  abands_break: Headley 加速帶 20 根、加速因子 4、中軌 SMA(20) 出場
                （Price Headley, "Big Trends in Trading", 2002）
  td_setup9   : TD Sequential 9 計數（C 對 C[i-4]）、最多抱 12 根 4H
                （Tom DeMark, "The New Science of Technical Analysis", 1994）
  double7     : Connors Double 7s：SMA(200) 上、7 根最低收盤進、7 根最高收盤出
                （Larry Connors, "Short Term Trading Strategies That Work", 2008）
  frama_cross : Ehlers FRAMA 16 根（α=exp(-4.6*(D-1))，夾 0.01~1）
                （John Ehlers, "FRAMA — Fractal Adaptive Moving Average", TASC 2005-10）
  cyber_cycle : Ehlers Cyber Cycle α=0.07、trigger=前一根
                （John Ehlers, "Cybernetic Analysis for Stocks and Futures", 2004）

已佔用（不得重用）的既有池：sim.STRATS 36 碼；v1 turtle_s1/s2、tsmom_12m、
ema50_200_adx、dual_mom；v2 nr7id/pairs_btc_eth/bb_adx_fade/funding_z_fade/
crabel_nr7_only；v3 connors_rsi2/ibs_fade/donchian100/cci_zero/williams_r；
v4 elder_impulse/aroon_cross/ao_zero/stoch_cross/golden_50_200；
v5 trix_zero/kst_cross/ultimate_50/cmo_zero/elder_ray；
v6 mfi_50/ppo_zero/wma_10_30/sma_10_40/tsi_zero/cci_pm100/boll_mid/adx_di；
extra_strats_loop 約 90 碼（含 coppock_zero、dpo_zero、fisher_zero、rvi_cross、
stoch_rsi、mass_reversion、mcginley_slope、qstick_zero、rmi_zero、schaff_tc 等）。
build(O,H,L,C,V,tf) 回傳 (el, xl, es, xs)，對齊 v6 與 fixed_stop_backtest 呼叫。
"""
from __future__ import annotations

import math
import os
import sys
from collections import deque
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

# ═══════════════ 凍結參數（開跑前寫死，見模組 docstring）═══════════════
VHF_N, VHF_UP, VHF_DN, VHF_EMA = 28, 0.40, 0.30, 50
CHOP_N, CHOP_HI, CHOP_LO, CHOP_SMA = 14, 61.8, 38.2, 50
PGO_N = 14
BOP_N = 14
TII_MAJOR, TII_MINOR, TII_UP, TII_DN, TII_MID = 60, 30, 80.0, 20.0, 50.0
TTF_N, TTF_TRIG = 15, 100.0
VWMA_N = 20
AB_N, AB_K = 20, 4.0
TD_SETUP, TD_MAX_HOLD = 9, 12
D7_N, D7_TREND = 7, 200
FRAMA_N = 16
CYBER_ALPHA = 0.07


def _empty(n):
    return [False] * n


# ── 通用小工具（滾動最高/最低用單調佇列，O(n)）─────────────────────────
def _roll_max(xs, n):
    out = [None] * len(xs)
    dq = deque()
    for i, x in enumerate(xs):
        while dq and dq[0] <= i - n:
            dq.popleft()
        while dq and xs[dq[-1]] <= x:
            dq.pop()
        dq.append(i)
        if i >= n - 1:
            out[i] = xs[dq[0]]
    return out


def _roll_min(xs, n):
    out = [None] * len(xs)
    dq = deque()
    for i, x in enumerate(xs):
        while dq and dq[0] <= i - n:
            dq.popleft()
        while dq and xs[dq[-1]] >= x:
            dq.pop()
        dq.append(i)
        if i >= n - 1:
            out[i] = xs[dq[0]]
    return out


def _tr(H, L, C):
    n = len(C)
    out = [None] * n
    for i in range(n):
        if i == 0:
            out[i] = H[i] - L[i]
        else:
            out[i] = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
    return out


def _prefix(xs):
    acc = [0.0] * (len(xs) + 1)
    for i, x in enumerate(xs):
        acc[i + 1] = acc[i] + (x if x is not None else 0.0)
    return acc


# ── 指標實作 ────────────────────────────────────────────────────────
def _vhf(C, n):
    """Vertical Horizontal Filter：n 根內（最高收盤−最低收盤）/ Σ|ΔC|。"""
    hh = _roll_max(C, n)
    ll = _roll_min(C, n)
    dc = [abs(C[i] - C[i - 1]) if i else 0.0 for i in range(len(C))]
    acc = _prefix(dc)
    out = [None] * len(C)
    for i in range(n, len(C)):
        den = acc[i + 1] - acc[i + 1 - n]
        if den > 0 and hh[i] is not None and ll[i] is not None:
            out[i] = (hh[i] - ll[i]) / den
    return out


def _chop(H, L, C, n):
    """Choppiness Index：100*log10(ΣTR(n)/(HH(n)−LL(n)))/log10(n)。"""
    tr = _tr(H, L, C)
    acc = _prefix(tr)
    hh = _roll_max(H, n)
    ll = _roll_min(L, n)
    out = [None] * len(C)
    lgn = math.log10(n)
    for i in range(n, len(C)):
        rng = (hh[i] or 0.0) - (ll[i] or 0.0)
        s = acc[i + 1] - acc[i + 1 - n]
        if rng > 0 and s > 0:
            out[i] = 100.0 * math.log10(s / rng) / lgn
    return out


def _pgo(H, L, C, n):
    """Pretty Good Oscillator：(C − SMA(C,n)) / EMA(TR,n)。"""
    m = sim.sma(C, n)
    tr = _tr(H, L, C)
    e = sim.ema(tr, n)
    out = [None] * len(C)
    for i in range(len(C)):
        if m[i] is None or e[i] in (None, 0):
            continue
        out[i] = (C[i] - m[i]) / e[i]
    return out


def _bop(O, H, L, C, n):
    """Balance of Power：SMA((C−O)/(H−L), n)。"""
    raw = []
    for o, h, l, c in zip(O, H, L, C):
        rng = h - l
        raw.append((c - o) / rng if rng > 0 else 0.0)
    acc = _prefix(raw)
    out = [None] * len(C)
    for i in range(n - 1, len(C)):
        out[i] = (acc[i + 1] - acc[i + 1 - n]) / n
    return out


def _tii(C, major, minor):
    """Trend Intensity Index：最近 minor 根中收盤在 SMA(major) 上的百分比。"""
    m = sim.sma(C, major)
    dev = [1.0 if (m[i] is not None and C[i] > m[i]) else 0.0 for i in range(len(C))]
    acc = _prefix(dev)
    out = [None] * len(C)
    for i in range(major + minor - 1, len(C)):
        out[i] = 100.0 * (acc[i + 1] - acc[i + 1 - minor]) / minor
    return out


def _ttf(H, L, n):
    """Trend Trigger Factor：bp=HH(n)今−LL(n)前n根；sp=HH(n)前n根−LL(n)今。
    「前 n 根」＝結束於 n 根前的那 n 根（Pee 原文：the 15 days before that）。"""
    hh = _roll_max(H, n)
    ll = _roll_min(L, n)
    out = [None] * len(H)
    for i in range(2 * n - 1, len(H)):
        if hh[i] is None or hh[i - n] is None or ll[i] is None or ll[i - n] is None:
            continue
        bp = hh[i] - ll[i - n]
        sp = hh[i - n] - ll[i]
        den = 0.5 * (bp + sp)
        if den > 0:
            out[i] = 100.0 * (bp - sp) / den
    return out


def _vwma(C, V, n):
    cv = [c * (v or 0.0) for c, v in zip(C, V)]
    vv = [(v or 0.0) for v in V]
    acv, avv = _prefix(cv), _prefix(vv)
    out = [None] * len(C)
    for i in range(n - 1, len(C)):
        d = avv[i + 1] - avv[i + 1 - n]
        if d > 0:
            out[i] = (acv[i + 1] - acv[i + 1 - n]) / d
    return out


def _abands(H, L, C, n, k):
    """Headley 加速帶：f=k*(H−L)/(H+L)；上=SMA(H*(1+f))；下=SMA(L*(1−f))。"""
    up_raw, lo_raw = [], []
    for h, l in zip(H, L):
        f = k * (h - l) / (h + l) if (h + l) > 0 else 0.0
        up_raw.append(h * (1.0 + f))
        lo_raw.append(l * (1.0 - f))
    au, al = _prefix(up_raw), _prefix(lo_raw)
    up, lo = [None] * len(C), [None] * len(C)
    for i in range(n - 1, len(C)):
        up[i] = (au[i + 1] - au[i + 1 - n]) / n
        lo[i] = (al[i + 1] - al[i + 1 - n]) / n
    return up, lo


def _frama(C, n):
    """Ehlers FRAMA：D=(log(N1+N2)−log(N3))/log2；α=exp(−4.6*(D−1)) 夾 0.01~1。"""
    N = len(C)
    out = [None] * N
    half = n // 2
    prev = None
    for i in range(n - 1, N):
        w1 = C[i - n + 1: i - n + 1 + half]
        w2 = C[i - n + 1 + half: i + 1]
        w3 = C[i - n + 1: i + 1]
        n1 = (max(w1) - min(w1)) / half
        n2 = (max(w2) - min(w2)) / half
        n3 = (max(w3) - min(w3)) / n
        if prev is None:
            prev = C[i]
            out[i] = prev
            continue
        alpha = 1.0
        if n1 + n2 > 0 and n3 > 0:
            d = (math.log(n1 + n2) - math.log(n3)) / math.log(2.0)
            alpha = math.exp(-4.6 * (d - 1.0))
        alpha = max(0.01, min(1.0, alpha))
        prev = alpha * C[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _cyber(C, alpha):
    """Ehlers Cyber Cycle：smooth=(C+2C1+2C2+C3)/6；cycle 二階遞迴；trigger=前一根。"""
    N = len(C)
    smooth = [0.0] * N
    for i in range(3, N):
        smooth[i] = (C[i] + 2.0 * C[i - 1] + 2.0 * C[i - 2] + C[i - 3]) / 6.0
    cycle = [0.0] * N
    for i in range(N):
        if i < 2:
            cycle[i] = 0.0
        elif i < 7:
            cycle[i] = (C[i] - 2.0 * C[i - 1] + C[i - 2]) / 4.0
        else:
            cycle[i] = ((1.0 - 0.5 * alpha) ** 2
                        * (smooth[i] - 2.0 * smooth[i - 1] + smooth[i - 2])
                        + 2.0 * (1.0 - alpha) * cycle[i - 1]
                        - (1.0 - alpha) ** 2 * cycle[i - 2])
    trig = [None] * N
    for i in range(1, N):
        trig[i] = cycle[i - 1]
    return cycle, trig


# ── 訊號（el=多進, xl=多出, es=空進, xs=空出）──────────────────────────
def sig_vhf_trend(O, H, L, C, V=None, tf=None):
    """VHF(28) 上穿 0.40 進入趨勢態，方向看 EMA50；跌破 0.30 出場。"""
    v = _vhf(C, VHF_N)
    m = sim.ema(C, VHF_EMA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if v[i] is None or v[i - 1] is None or m[i] is None:
            continue
        up = v[i - 1] <= VHF_UP < v[i]
        if up and C[i] > m[i]:
            el[i] = True
        if up and C[i] < m[i]:
            es[i] = True
        if v[i] < VHF_DN:
            xl[i] = True
            xs[i] = True
    return el, xl, es, xs


def sig_chop_trend(O, H, L, C, V=None, tf=None):
    """CI(14) 下穿 38.2（脫離盤整）順 SMA50 方向進場；CI>61.8 或破 SMA50 出場。"""
    ci = _chop(H, L, C, CHOP_N)
    m = sim.sma(C, CHOP_SMA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if ci[i] is None or ci[i - 1] is None or m[i] is None:
            continue
        go = ci[i - 1] >= CHOP_LO > ci[i]
        if go and C[i] > m[i]:
            el[i] = True
        if go and C[i] < m[i]:
            es[i] = True
        if ci[i] > CHOP_HI or C[i] < m[i]:
            xl[i] = True
        if ci[i] > CHOP_HI or C[i] > m[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_pgo_zero(O, H, L, C, V=None, tf=None):
    """PGO(14) 零軸交叉。"""
    p = _pgo(H, L, C, PGO_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if p[i] is None or p[i - 1] is None:
            continue
        if p[i - 1] <= 0 < p[i]:
            el[i] = True
        if p[i] < 0:
            xl[i] = True
        if p[i - 1] >= 0 > p[i]:
            es[i] = True
        if p[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_bop_zero(O, H, L, C, V=None, tf=None):
    """BOP SMA(14) 零軸交叉。"""
    b = _bop(O, H, L, C, BOP_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if b[i] is None or b[i - 1] is None:
            continue
        if b[i - 1] <= 0 < b[i]:
            el[i] = True
        if b[i] < 0:
            xl[i] = True
        if b[i - 1] >= 0 > b[i]:
            es[i] = True
        if b[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_tii_80_20(O, H, L, C, V=None, tf=None):
    """TII(60/30) 上穿 80 多、下穿 20 空、回 50 出場。"""
    t = _tii(C, TII_MAJOR, TII_MINOR)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if t[i] is None or t[i - 1] is None:
            continue
        if t[i - 1] <= TII_UP < t[i]:
            el[i] = True
        if t[i] < TII_MID:
            xl[i] = True
        if t[i - 1] >= TII_DN > t[i]:
            es[i] = True
        if t[i] > TII_MID:
            xs[i] = True
    return el, xl, es, xs


def sig_ttf_pm100(O, H, L, C, V=None, tf=None):
    """TTF(15) 上穿 +100 多、下穿 −100 空、回零軸出場。"""
    t = _ttf(H, L, TTF_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if t[i] is None or t[i - 1] is None:
            continue
        if t[i - 1] <= TTF_TRIG < t[i]:
            el[i] = True
        if t[i] < 0:
            xl[i] = True
        if t[i - 1] >= -TTF_TRIG > t[i]:
            es[i] = True
        if t[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_vwma_sma(O, H, L, C, V=None, tf=None):
    """VWMA(20) 對 SMA(20) 交叉；量加持的價格趨勢。"""
    v = _vwma(C, V or [0.0] * len(C), VWMA_N)
    s = sim.sma(C, VWMA_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (v[i], v[i - 1], s[i], s[i - 1]):
            continue
        if v[i - 1] <= s[i - 1] and v[i] > s[i]:
            el[i] = True
        if v[i] < s[i]:
            xl[i] = True
        if v[i - 1] >= s[i - 1] and v[i] < s[i]:
            es[i] = True
        if v[i] > s[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_abands_break(O, H, L, C, V=None, tf=None):
    """加速帶(20,4)：收盤破上軌多、破下軌空、回中軌 SMA20 出場。"""
    up, lo = _abands(H, L, C, AB_N, AB_K)
    mid = sim.sma(C, AB_N)
    n = len(C)
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


def sig_td_setup9(O, H, L, C, V=None, tf=None):
    """TD Sequential：連續 9 根 C<C[i-4] 買進衰竭；9 根 C>C[i-4] 賣出衰竭。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    buy = sell = 0
    for i in range(n):
        if i >= 4:
            buy = buy + 1 if C[i] < C[i - 4] else 0
            sell = sell + 1 if C[i] > C[i - 4] else 0
        if buy >= TD_SETUP:
            el[i] = True
            xs[i] = True
        if sell >= TD_SETUP:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_double7(O, H, L, C, V=None, tf=None):
    """Connors Double 7s（只做多）：C>SMA200 且收 7 根最低收盤 → 進；收 7 根最高收盤 → 出。"""
    m = sim.sma(C, D7_TREND)
    lo = _roll_min(C, D7_N)
    hi = _roll_max(C, D7_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(n):
        if m[i] is None or lo[i] is None or hi[i] is None:
            continue
        if C[i] > m[i] and C[i] <= lo[i]:
            el[i] = True
        if C[i] >= hi[i]:
            xl[i] = True
    return el, xl, es, xs


def sig_frama_cross(O, H, L, C, V=None, tf=None):
    """收盤對 FRAMA(16) 交叉。"""
    f = _frama(C, FRAMA_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
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


def sig_cyber_cycle(O, H, L, C, V=None, tf=None):
    """Ehlers Cyber Cycle(α=0.07) 對 trigger（前一根）交叉。"""
    cy, tr = _cyber(C, CYBER_ALPHA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(8, n):
        if tr[i] is None or tr[i - 1] is None:
            continue
        if cy[i - 1] <= tr[i - 1] and cy[i] > tr[i]:
            el[i] = True
        if cy[i] < tr[i]:
            xl[i] = True
        if cy[i - 1] >= tr[i - 1] and cy[i] < tr[i]:
            es[i] = True
        if cy[i] > tr[i]:
            xs[i] = True
    return el, xl, es, xs


EXTRA_STRATS_V7 = {
    "vhf_trend": {
        "name": "VHF(28) 趨勢態 + EMA50 方向",
        "family": "trend_quality",
        "speed": "mid",
        "sided": "both",
        "build": sig_vhf_trend,
        "min_bars": VHF_N + VHF_EMA + 20,
        "source": "Adam White Vertical Horizontal Filter, TASC 1991; 0.40/0.30 + EMA50",
    },
    "chop_trend": {
        "name": "Choppiness(14) 脫離盤整 + SMA50",
        "family": "trend_quality",
        "speed": "mid",
        "sided": "both",
        "build": sig_chop_trend,
        "min_bars": CHOP_N + CHOP_SMA + 20,
        "source": "Bill Dreiss Choppiness Index; 61.8/38.2 + SMA50",
    },
    "pgo_zero": {
        "name": "PGO(14) 零軸交叉",
        "family": "osc",
        "speed": "mid",
        "sided": "both",
        "build": sig_pgo_zero,
        "min_bars": PGO_N + 20,
        "source": "Mark Johnson Pretty Good Oscillator, TASC 2003",
    },
    "bop_zero": {
        "name": "Balance of Power(14) 零軸交叉",
        "family": "osc",
        "speed": "mid",
        "sided": "both",
        "build": sig_bop_zero,
        "min_bars": BOP_N + 20,
        "source": "Igor Livshin Balance of Power, TASC 2001-08",
    },
    "tii_80_20": {
        "name": "TII(60/30) 80/20 趨勢強度",
        "family": "trend_quality",
        "speed": "slow",
        "sided": "both",
        "build": sig_tii_80_20,
        "min_bars": TII_MAJOR + TII_MINOR + 20,
        "source": "M.H. Pee Trend Intensity Index, TASC 2003-06",
    },
    "ttf_pm100": {
        "name": "TTF(15) ±100 趨勢觸發",
        "family": "momentum",
        "speed": "mid",
        "sided": "both",
        "build": sig_ttf_pm100,
        "min_bars": TTF_N * 2 + 20,
        "source": "M.H. Pee Trend Trigger Factor, TASC 2004-12",
    },
    "vwma_sma": {
        "name": "VWMA20/SMA20 交叉（量加持）",
        "family": "volume",
        "speed": "mid",
        "sided": "both",
        "build": sig_vwma_sma,
        "min_bars": VWMA_N + 20,
        "source": "Buff Dormeier VWMA vs SMA, Investing with Volume Analysis 2011",
    },
    "abands_break": {
        "name": "Headley 加速帶(20,4) 突破",
        "family": "breakout",
        "speed": "fast",
        "sided": "both",
        "build": sig_abands_break,
        "min_bars": AB_N + 20,
        "source": "Price Headley Acceleration Bands, Big Trends in Trading 2002",
    },
    "td_setup9": {
        "name": "TD Sequential 9 計數衰竭（抱≤12根）",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_td_setup9,
        "max_hold_bars": TD_MAX_HOLD,
        "min_bars": TD_SETUP + 24,
        "source": "Tom DeMark TD Sequential setup 9, New Science of TA 1994",
    },
    "double7": {
        "name": "Connors Double 7s（SMA200+7根低點）",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "long",
        "build": sig_double7,
        "min_bars": D7_TREND + 20,
        "source": "Larry Connors Double 7s, Short Term Trading Strategies 2008",
    },
    "frama_cross": {
        "name": "FRAMA(16) 收盤交叉（Ehlers）",
        "family": "ma",
        "speed": "mid",
        "sided": "both",
        "build": sig_frama_cross,
        "min_bars": FRAMA_N * 2 + 20,
        "source": "John Ehlers FRAMA, TASC 2005-10",
    },
    "cyber_cycle": {
        "name": "Ehlers Cyber Cycle(0.07) 交叉",
        "family": "cycle",
        "speed": "fast",
        "sided": "both",
        "build": sig_cyber_cycle,
        "min_bars": 40,
        "source": "John Ehlers Cybernetic Analysis for Stocks and Futures, 2004",
    },
}
