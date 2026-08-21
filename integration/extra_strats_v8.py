# -*- coding: utf-8 -*-
"""外人教科書策略 v8（參數凍結，禁止依場外改 lookback）。

【參數凍結聲明】以下所有參數在 2026-08-17 開跑前寫死，**不是**看完幣安
回測結果再發明或再調。回測結果不理想也不回頭改 lookback／門檻／持有根數，
只在報告中註明失敗。與 sim 內建、v1–v7、extra_strats_loop 池全部不重複
（Klinger/Schaff/Qstick/RMI/UO/TSI/StochRSI/Elder Impulse/Pivot/ORB 等
建議家族經盤點已被佔用，本輪改用下列 13 套）。

凍結清單（策略 code → 參數 → 文獻）：
  rwi_trend      : Random Walk Index 短期 j=2..8、ATR(14)、門檻 1.0
                   （Michael Poulos, "Are There Persistent Cycles?", TASC 1992）
  psy_line       : Psychological Line(12)，25/75 極端、50 中軸出場
                   （經典心理線，亞洲教科書慣用 12 期 25/75）
  smi_cross      : Stochastic Momentum Index(20,5,5) 對訊號線 EMA(3) 交叉
                   （William Blau, "Stochastic Momentum", TASC 1993-01）
  roofing_x      : Ehlers Roofing Filter：HighPass(48)+SuperSmoother(10) 對前一根交叉
                   （John Ehlers, "Predictive and Successful Indicators", TASC 2014-01）
  cog_x          : Ehlers Center of Gravity(10) 對前一根交叉
                   （John Ehlers, "The Center of Gravity Oscillator", TASC 2002-05）
  laguerre_rsi   : Ehlers Laguerre RSI γ=0.2，0.2/0.8 衰竭交叉
                   （John Ehlers, "Time Warp – Without Space Travel", TASC）
  vzo_cross      : Volume Zone Oscillator(14) 零軸交叉
                   （Walid Khalil, Volume Zone Oscillator, TASC）
  imi_50         : Intraday Momentum Index(14)（C−O 版 RSI）穿越 50
                   （Chande & Kroll, "The New Technical Trader", 1994）
  projection_osc : Widner 投影帶(14) 擺盪 0–100 穿越 50
                   （Mel Widner, "Automated Support and Resistance", TASC 1995-07）
  bw_mfi         : Bill Williams MFI=(H−L)/V 綠柱（量價齊升/齊跌）順 K 棒方向進場
                   （Bill Williams, "Trading Chaos", 1995）
  morning_star   : 晨星/夜星（大身>0.5×ATR14、星身≤0.3 倍、第三根過半），抱≤6 根
                   （Steve Nison, "Japanese Candlestick Charting Techniques"）
  key_reversal   : 關鍵反轉（新低收高/新高收低），抱≤6 根
                   （Edwards & Magee；Bulkowski 蠟燭圖百科）
  momentum_pinball: Raschke 動能彈珠：ROC(1) 的 RSI(3)，30/70 衰竭、抱≤2 根
                   （Linda Raschke & Larry Connors, "Street Smarts", 1995）

build(O,H,L,C,V,tf) 回傳 (el, xl, es, xs)，對齊 v6/v7 與 fixed_stop_backtest 呼叫。
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
from extra_strats_v7 import _empty, _prefix, _roll_max, _roll_min, _tr  # noqa: E402

# ═══════════════ 凍結參數（開跑前寫死，見模組 docstring）═══════════════
RWI_N, RWI_J, RWI_LVL = 14, 8, 1.0
PSY_N, PSY_OS, PSY_OB, PSY_MID = 12, 25.0, 75.0, 50.0
SMI_N, SMI_S1, SMI_S2, SMI_SIG = 20, 5, 5, 3
ROOF_HP, ROOF_SS = 48, 10
COG_N = 10
LAG_GAMMA, LAG_LO, LAG_HI = 0.2, 0.2, 0.8
VZO_N = 14
IMI_N = 14
PO_N, PO_LVL = 14, 50.0
STAR_ATR, STAR_BIG, STAR_SMALL, STAR_HOLD = 14, 0.5, 0.3, 6
KR_HOLD = 6
PB_LO, PB_HI, PB_HOLD = 30.0, 70.0, 2


# ── 指標實作 ────────────────────────────────────────────────────────
def _rsi_wilder(xs, n):
    """Wilder RSI，容忍開頭 None（給 ROC 之類衍生序列用）。"""
    N = len(xs)
    out = [None] * N
    gains, losses = [], []
    avg_g = avg_l = None
    for i in range(N):
        if i == 0 or xs[i] is None or xs[i - 1] is None:
            continue
        ch = xs[i] - xs[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if avg_g is None:
            gains.append(g)
            losses.append(l)
            if len(gains) == n:
                avg_g = sum(gains) / n
                avg_l = sum(losses) / n
            continue
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
        if avg_l == 0:
            out[i] = 100.0 if avg_g > 0 else 50.0
        else:
            rs = avg_g / avg_l
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _rwi(H, L, C, n, jmax):
    """Poulos 短期 RWI：j=2..jmax 取最大。(H−L[i−j])/(ATR×√j)。"""
    a = sim.atr(H, L, C, n)
    hi, lo = [None] * len(C), [None] * len(C)
    roots = [math.sqrt(j) for j in range(jmax + 1)]
    for i in range(n + jmax, len(C)):
        av = a[i]
        if av is None or av <= 0:
            continue
        hmax = lmax = 0.0
        for j in range(2, jmax + 1):
            rh = (H[i] - L[i - j]) / (av * roots[j])
            rl = (H[i - j] - L[i]) / (av * roots[j])
            hmax = max(hmax, rh)
            lmax = max(lmax, rl)
        hi[i], lo[i] = hmax, lmax
    return hi, lo


def _psy(C, n):
    up = [1.0 if i > 0 and C[i] > C[i - 1] else 0.0 for i in range(len(C))]
    acc = _prefix(up)
    out = [None] * len(C)
    for i in range(n, len(C)):
        out[i] = 100.0 * (acc[i + 1] - acc[i + 1 - n]) / n
    return out


def _smi(C, H, L, n, s1, s2, sig):
    hh = _roll_max(H, n)
    ll = _roll_min(L, n)
    d, r = [None] * len(C), [None] * len(C)
    for i in range(len(C)):
        if hh[i] is None or ll[i] is None:
            continue
        mid = 0.5 * (hh[i] + ll[i])
        d[i] = C[i] - mid
        r[i] = hh[i] - ll[i]
    d2 = sim.ema(sim.ema(d, s1), s2)
    r2 = sim.ema(sim.ema(r, s1), s2)
    smi = [None] * len(C)
    for i in range(len(C)):
        if d2[i] is None or r2[i] in (None, 0):
            continue
        smi[i] = 100.0 * d2[i] / (0.5 * r2[i])
    return smi, sim.ema(smi, sig)


def _roofing(C, hp_n, ss_n):
    """Ehlers Roofing Filter：HighPass(hp_n) 接 SuperSmoother(ss_n)。"""
    N = len(C)
    # 1 極高通（Ehlers 公式）
    alpha1 = (math.cos(math.radians(0.707 * 360.0 / hp_n))
              + math.sin(math.radians(0.707 * 360.0 / hp_n)) - 1.0) \
        / math.cos(math.radians(0.707 * 360.0 / hp_n))
    hp = [0.0] * N
    for i in range(2, N):
        hp[i] = ((1.0 - alpha1 / 2.0) ** 2 * (C[i] - 2.0 * C[i - 1] + C[i - 2])
                 + 2.0 * (1.0 - alpha1) * hp[i - 1]
                 - (1.0 - alpha1) ** 2 * hp[i - 2])
    # SuperSmoother 3 極
    a1 = math.exp(-1.414 * math.pi / ss_n)
    b1 = 2.0 * a1 * math.cos(math.radians(1.414 * 180.0 / ss_n))
    c2, c3 = b1, -a1 * a1
    c1 = 1.0 - c2 - c3
    rf = [0.0] * N
    for i in range(1, N):
        rf[i] = c1 * (hp[i] + hp[i - 1]) / 2.0 + c2 * rf[i - 1] + c3 * rf[i - 2]
    trig = [None] * N
    for i in range(1, N):
        trig[i] = rf[i - 1]
    return rf, trig


def _cog(C, n):
    out = [None] * len(C)
    for i in range(n - 1, len(C)):
        num = den = 0.0
        for j in range(n):
            num += (j + 1) * C[i - j]
            den += C[i - j]
        if den:
            out[i] = -num / den
    trig = [None] * len(C)
    for i in range(1, len(C)):
        trig[i] = out[i - 1]
    return out, trig


def _laguerre_rsi(C, gamma):
    N = len(C)
    L0 = [0.0] * N
    L1 = [0.0] * N
    L2 = [0.0] * N
    L3 = [0.0] * N
    out = [None] * N
    for i in range(1, N):
        L0[i] = gamma * C[i] + (1.0 - gamma) * L0[i - 1]
        L1[i] = -(1.0 - gamma) * L0[i] + L0[i - 1] + (1.0 - gamma) * L1[i - 1]
        L2[i] = -(1.0 - gamma) * L1[i] + L1[i - 1] + (1.0 - gamma) * L2[i - 1]
        L3[i] = -(1.0 - gamma) * L2[i] + L2[i - 1] + (1.0 - gamma) * L3[i - 1]
        cu = cd = 0.0
        for a, b in ((L0, L1), (L1, L2), (L2, L3)):
            cu += max(a[i] - b[i], 0.0)
            cd += max(b[i] - a[i], 0.0)
        if cu + cd > 0:
            out[i] = cu / (cu + cd)
        elif i > 1:
            out[i] = out[i - 1]
    return out


def _vzo(C, V, n):
    sv = []
    for i in range(len(C)):
        v = V[i] or 0.0
        if i == 0 or C[i] == C[i - 1]:
            sv.append(0.0)
        else:
            sv.append(v if C[i] > C[i - 1] else -v)
    ve = sim.ema([(v or 0.0) for v in V], n)
    se = sim.ema(sv, n)
    out = [None] * len(C)
    for i in range(len(C)):
        if ve[i] in (None, 0) or se[i] is None:
            continue
        out[i] = 100.0 * se[i] / ve[i]
    return out


def _imi(O, C, n):
    up = [max(C[i] - O[i], 0.0) for i in range(len(C))]
    dn = [max(O[i] - C[i], 0.0) for i in range(len(C))]
    au, ad = _prefix(up), _prefix(dn)
    out = [None] * len(C)
    for i in range(n, len(C)):
        u = au[i + 1] - au[i + 1 - n]
        d = ad[i + 1] - ad[i + 1 - n]
        if u + d > 0:
            out[i] = 100.0 * u / (u + d)
    return out


def _linreg_slope(xs, i, n):
    """xs[i-n+1..i] 對 x=0..n-1 的最小平方斜率。"""
    sx = n * (n - 1) / 2.0
    sxx = n * (n - 1) * (2 * n - 1) / 6.0
    sy = sxy = 0.0
    for j in range(n):
        y = xs[i - n + 1 + j]
        sy += y
        sxy += j * y
    den = n * sxx - sx * sx
    if den == 0:
        return 0.0
    return (n * sxy - sx * sy) / den


def _projection_bands(H, L, C, n):
    up, lo = [None] * len(C), [None] * len(C)
    for i in range(2 * n - 2, len(C)):
        sh = _linreg_slope(H, i, n)
        sl = _linreg_slope(L, i, n)
        up[i] = max(H[i - j] + sh * j for j in range(n))
        lo[i] = min(L[i - j] + sl * j for j in range(n))
    return up, lo


# ── 訊號（el=多進, xl=多出, es=空進, xs=空出）──────────────────────────
def sig_rwi_trend(O, H, L, C, V=None, tf=None):
    """RWI_high 上穿 1.0 且高於 RWI_low → 多；跌回 1.0 下 → 出。空鏡像。"""
    rh, rl = _rwi(H, L, C, RWI_N, RWI_J)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (rh[i], rh[i - 1], rl[i], rl[i - 1]):
            continue
        if rh[i - 1] <= RWI_LVL < rh[i] and rh[i] > rl[i]:
            el[i] = True
        if rl[i - 1] <= RWI_LVL < rl[i] and rl[i] > rh[i]:
            es[i] = True
        if rh[i] < RWI_LVL:
            xl[i] = True
        if rl[i] < RWI_LVL:
            xs[i] = True
    return el, xl, es, xs


def sig_psy_line(O, H, L, C, V=None, tf=None):
    """心理線(12)：下穿 25 進多、回 50 出；上穿 75 進空、回 50 出。"""
    p = _psy(C, PSY_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if p[i] is None or p[i - 1] is None:
            continue
        if p[i - 1] >= PSY_OS > p[i]:
            el[i] = True
        if p[i] >= PSY_MID:
            xl[i] = True
        if p[i - 1] <= PSY_OB < p[i]:
            es[i] = True
        if p[i] <= PSY_MID:
            xs[i] = True
    return el, xl, es, xs


def sig_smi_cross(O, H, L, C, V=None, tf=None):
    """SMI(20,5,5) 對訊號線 EMA(3) 交叉。"""
    smi, sig = _smi(C, H, L, SMI_N, SMI_S1, SMI_S2, SMI_SIG)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (smi[i], smi[i - 1], sig[i], sig[i - 1]):
            continue
        if smi[i - 1] <= sig[i - 1] and smi[i] > sig[i]:
            el[i] = True
        if smi[i] < sig[i]:
            xl[i] = True
        if smi[i - 1] >= sig[i - 1] and smi[i] < sig[i]:
            es[i] = True
        if smi[i] > sig[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_roofing_x(O, H, L, C, V=None, tf=None):
    """Ehlers Roofing Filter 對 trigger（前一根）交叉。"""
    rf, tr = _roofing(C, ROOF_HP, ROOF_SS)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    warm = ROOF_HP + ROOF_SS
    for i in range(warm, n):
        if tr[i] is None or tr[i - 1] is None:
            continue
        if rf[i - 1] <= tr[i - 1] and rf[i] > tr[i]:
            el[i] = True
        if rf[i] < tr[i]:
            xl[i] = True
        if rf[i - 1] >= tr[i - 1] and rf[i] < tr[i]:
            es[i] = True
        if rf[i] > tr[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_cog_x(O, H, L, C, V=None, tf=None):
    """Ehlers COG(10) 對 trigger（前一根）交叉。"""
    cg, tr = _cog(C, COG_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if None in (cg[i], cg[i - 1], tr[i], tr[i - 1]):
            continue
        if cg[i - 1] <= tr[i - 1] and cg[i] > tr[i]:
            el[i] = True
        if cg[i] < tr[i]:
            xl[i] = True
        if cg[i - 1] >= tr[i - 1] and cg[i] < tr[i]:
            es[i] = True
        if cg[i] > tr[i]:
            xs[i] = True
    return el, xl, es, xs


def sig_laguerre_rsi(O, H, L, C, V=None, tf=None):
    """Laguerre RSI(γ=0.2)：上穿 0.2 進多、下穿 0.8 出多進空、上穿 0.2 出空。"""
    lr = _laguerre_rsi(C, LAG_GAMMA)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if lr[i] is None or lr[i - 1] is None:
            continue
        if lr[i - 1] <= LAG_LO < lr[i]:
            el[i] = True
            xs[i] = True
        if lr[i - 1] >= LAG_HI > lr[i]:
            xl[i] = True
            es[i] = True
    return el, xl, es, xs


def sig_vzo_cross(O, H, L, C, V=None, tf=None):
    """VZO(14) 零軸交叉（量能帶方向）。"""
    z = _vzo(C, V or [0.0] * len(C), VZO_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if z[i] is None or z[i - 1] is None:
            continue
        if z[i - 1] <= 0 < z[i]:
            el[i] = True
        if z[i] < 0:
            xl[i] = True
        if z[i - 1] >= 0 > z[i]:
            es[i] = True
        if z[i] > 0:
            xs[i] = True
    return el, xl, es, xs


def sig_imi_50(O, H, L, C, V=None, tf=None):
    """IMI(14)（K 棒實體版 RSI）穿越 50。"""
    m = _imi(O, C, IMI_N)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if m[i] is None or m[i - 1] is None:
            continue
        if m[i - 1] <= 50 < m[i]:
            el[i] = True
        if m[i] < 50:
            xl[i] = True
        if m[i - 1] >= 50 > m[i]:
            es[i] = True
        if m[i] > 50:
            xs[i] = True
    return el, xl, es, xs


def sig_projection_osc(O, H, L, C, V=None, tf=None):
    """Widner 投影帶擺盪 PO=100(C−下帶)/(上帶−下帶) 穿越 50。"""
    up, lo = _projection_bands(H, L, C, PO_N)
    n = len(C)
    po = [None] * n
    for i in range(n):
        if up[i] is None or lo[i] is None or up[i] <= lo[i]:
            continue
        po[i] = 100.0 * (C[i] - lo[i]) / (up[i] - lo[i])
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if po[i] is None or po[i - 1] is None:
            continue
        if po[i - 1] <= PO_LVL < po[i]:
            el[i] = True
        if po[i] < PO_LVL:
            xl[i] = True
        if po[i - 1] >= PO_LVL > po[i]:
            es[i] = True
        if po[i] > PO_LVL:
            xs[i] = True
    return el, xl, es, xs


def sig_bw_mfi(O, H, L, C, V=None, tf=None):
    """BW MFI 綠柱：MFI↑且V↑，順該根 K 棒方向進場；量價背離出場。"""
    n = len(C)
    vv = [(v or 0.0) for v in (V or [0.0] * n)]
    mfi = [None] * n
    for i in range(n):
        if vv[i] > 0:
            mfi[i] = (H[i] - L[i]) / vv[i]
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if mfi[i] is None or mfi[i - 1] is None:
            continue
        green = mfi[i] > mfi[i - 1] and vv[i] > vv[i - 1]
        fade = mfi[i] < mfi[i - 1] or vv[i] < vv[i - 1]
        if green and C[i] > O[i]:
            el[i] = True
        if green and C[i] < O[i]:
            es[i] = True
        if fade:
            xl[i] = True
            xs[i] = True
    return el, xl, es, xs


def sig_morning_star(O, H, L, C, V=None, tf=None):
    """晨星：①大黑 K（身>0.5×ATR）②小星（身≤0.3 倍①）③大紅 K 收過①身中點。夜星鏡像。"""
    a = sim.atr(H, L, C, STAR_ATR)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(2, n):
        if a[i] is None:
            continue
        b1 = C[i - 2] - O[i - 2]
        b2 = C[i - 1] - O[i - 1]
        if abs(b1) <= STAR_BIG * a[i]:
            continue
        if abs(b2) > STAR_SMALL * abs(b1):
            continue
        mid1 = 0.5 * (O[i - 2] + C[i - 2])
        if b1 < 0 and C[i] > O[i] and C[i] > mid1:
            el[i] = True
            xs[i] = True
        if b1 > 0 and C[i] < O[i] and C[i] < mid1:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_key_reversal(O, H, L, C, V=None, tf=None):
    """關鍵反轉：破前兩根低點但收高於昨收且收紅 → 多；鏡像 → 空。"""
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(2, n):
        if L[i] < min(L[i - 1], L[i - 2]) and C[i] > C[i - 1] and C[i] > O[i]:
            el[i] = True
            xs[i] = True
        if H[i] > max(H[i - 1], H[i - 2]) and C[i] < C[i - 1] and C[i] < O[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


def sig_momentum_pinball(O, H, L, C, V=None, tf=None):
    """Raschke 動能彈珠：ROC(1) 的 RSI(3) 下穿 30 進多、上穿 70 進空。"""
    roc = [None] + [C[i] - C[i - 1] for i in range(1, len(C))]
    mp = _rsi_wilder(roc, 3)
    n = len(C)
    el, xl, es, xs = _empty(n), _empty(n), _empty(n), _empty(n)
    for i in range(1, n):
        if mp[i] is None or mp[i - 1] is None:
            continue
        if mp[i - 1] >= PB_LO > mp[i]:
            el[i] = True
            xs[i] = True
        if mp[i - 1] <= PB_HI < mp[i]:
            es[i] = True
            xl[i] = True
    return el, xl, es, xs


EXTRA_STRATS_V8 = {
    "rwi_trend": {
        "name": "RWI(14,j≤8) 隨機走路指數 >1.0",
        "family": "trend_quality",
        "speed": "mid",
        "sided": "both",
        "build": sig_rwi_trend,
        "min_bars": RWI_N + RWI_J + 20,
        "source": "Michael Poulos Random Walk Index, TASC 1992",
    },
    "psy_line": {
        "name": "心理線 PSY(12) 25/75 衰竭",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_psy_line,
        "min_bars": PSY_N + 20,
        "source": "Classic Psychological Line 12期 25/75",
    },
    "smi_cross": {
        "name": "SMI(20,5,5) 對 EMA3 交叉",
        "family": "osc",
        "speed": "mid",
        "sided": "both",
        "build": sig_smi_cross,
        "min_bars": SMI_N + SMI_S1 + SMI_S2 + SMI_SIG + 20,
        "source": "William Blau Stochastic Momentum Index, TASC 1993-01",
    },
    "roofing_x": {
        "name": "Ehlers Roofing Filter(48,10) 交叉",
        "family": "cycle",
        "speed": "mid",
        "sided": "both",
        "build": sig_roofing_x,
        "min_bars": ROOF_HP + ROOF_SS + 20,
        "source": "John Ehlers Roofing Filter, TASC 2014-01",
    },
    "cog_x": {
        "name": "Ehlers COG(10) 交叉",
        "family": "cycle",
        "speed": "fast",
        "sided": "both",
        "build": sig_cog_x,
        "min_bars": COG_N + 20,
        "source": "John Ehlers Center of Gravity Oscillator, TASC 2002-05",
    },
    "laguerre_rsi": {
        "name": "Laguerre RSI(0.2) 0.2/0.8 衰竭",
        "family": "osc",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_laguerre_rsi,
        "min_bars": 40,
        "source": "John Ehlers Laguerre RSI, Time Warp Without Space Travel",
    },
    "vzo_cross": {
        "name": "VZO(14) 量能區帶零軸交叉",
        "family": "volume",
        "speed": "mid",
        "sided": "both",
        "build": sig_vzo_cross,
        "min_bars": VZO_N + 20,
        "source": "Walid Khalil Volume Zone Oscillator, TASC",
    },
    "imi_50": {
        "name": "IMI(14) K棒實體RSI 穿越 50",
        "family": "momentum",
        "speed": "mid",
        "sided": "both",
        "build": sig_imi_50,
        "min_bars": IMI_N + 20,
        "source": "Chande & Kroll Intraday Momentum Index, New Technical Trader 1994",
    },
    "projection_osc": {
        "name": "Widner 投影帶擺盪(14) 穿越 50",
        "family": "osc",
        "speed": "mid",
        "sided": "both",
        "build": sig_projection_osc,
        "min_bars": PO_N * 2 + 20,
        "source": "Mel Widner Projection Oscillator, TASC 1995-07",
    },
    "bw_mfi": {
        "name": "BW MFI 綠柱順勢（量價齊動）",
        "family": "volume",
        "speed": "fast",
        "sided": "both",
        "build": sig_bw_mfi,
        "min_bars": 20,
        "source": "Bill Williams Market Facilitation Index, Trading Chaos 1995",
    },
    "morning_star": {
        "name": "晨星/夜星反轉（抱≤6根）",
        "family": "candle",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_morning_star,
        "max_hold_bars": STAR_HOLD,
        "min_bars": STAR_ATR + 24,
        "source": "Steve Nison Morning/Evening Star, JCT Techniques",
    },
    "key_reversal": {
        "name": "關鍵反轉 K 棒（抱≤6根）",
        "family": "candle",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_key_reversal,
        "max_hold_bars": KR_HOLD,
        "min_bars": 24,
        "source": "Edwards & Magee Key Reversal; Bulkowski Encyclopedia",
    },
    "momentum_pinball": {
        "name": "Raschke 動能彈珠 RSI3(ROC1) 30/70（抱≤2根）",
        "family": "fade",
        "speed": "fast_fade",
        "sided": "both",
        "build": sig_momentum_pinball,
        "max_hold_bars": PB_HOLD,
        "min_bars": 30,
        "source": "Linda Raschke Momentum Pinball, Street Smarts 1995",
    },
}
