# -*- coding: utf-8 -*-
"""C1.1:獨立的教科書 Wilder ADX 參考實作(只給驗證與測試用,不被 app.py / sim.py 引用,不取代任何既有函式)。

依 J. Welles Wilder, "New Concepts in Technical Trading Systems" (1978) 的步驟,逐步寫出,刻意不沿用 sim.dmi / calc_adx 的程式結構:
  1. TR_t  = max(H-L, |H-C_prev|, |L-C_prev|)
     +DM_t = H-H_prev 若 (H-H_prev) > (L_prev-L) 且 > 0,否則 0
     -DM_t = L_prev-L 若 (L_prev-L) > (H-H_prev) 且 > 0,否則 0
  2. 前 n 根(t=1..n)的 TR、+DM、-DM 各自加總作為第一個平滑值(n=14);
     之後 S_t = S_{t-1} - S_{t-1}/n + X_t   (Wilder 平滑,等價於 alpha=1/n 的 EMA 乘以 n)
  3. +DI = 100 * S(+DM)/S(TR),-DI = 100 * S(-DM)/S(TR)
     DX  = 100 * |+DI - -DI| / (+DI + -DI)
  4. ADX 第一個值 = 前 n 個 DX 的平均(出現在 t = 2n-1);之後 ADX_t = (ADX_{t-1}*(n-1) + DX_t) / n   (再做一次 Wilder 平滑)
另提供:
  - sma_dx_adx:    ADX 以「最近 n 個 DX 的簡單平均」計算(= 目前 app.calc_adx 的做法),用來說明差異的來源。
  - pandas_ewm_adx: pandas ewm(alpha=1/n, adjust=False) 版(以第一個值當種子;網路上常見的簡寫版),用來說明暖機/種子的影響。
"""


def _components(H, L, C, n):
    N = len(C)
    tr = [None] * N; pdm = [0.0] * N; mdm = [0.0] * N
    for t in range(1, N):
        up, dn = H[t] - H[t - 1], L[t - 1] - L[t]
        pdm[t] = up if (up > dn and up > 0) else 0.0
        mdm[t] = dn if (dn > up and dn > 0) else 0.0
        tr[t] = max(H[t] - L[t], abs(H[t] - C[t - 1]), abs(L[t] - C[t - 1]))
    return tr, pdm, mdm


def _wilder_sum(x, n, N):
    """前 n 根(t=1..n)加總當種子,之後 S = S - S/n + x。回傳長度 N,t<n 為 None。"""
    out = [None] * N
    if N <= n: return out
    s = sum(x[1:n + 1]); out[n] = s
    for t in range(n + 1, N):
        s = s - s / n + x[t]; out[t] = s
    return out


def di_dx(H, L, C, n=14):
    """回傳 (+DI, -DI, DX) 三個長度 N 的串列(沒有值的位置是 None)。"""
    N = len(C); tr, pdm, mdm = _components(H, L, C, n)
    st, sp, sm = _wilder_sum(tr, n, N), _wilder_sum(pdm, n, N), _wilder_sum(mdm, n, N)
    pdi = [None] * N; mdi = [None] * N; dx = [None] * N
    for t in range(N):
        if st[t] is None or st[t] == 0: continue
        pdi[t] = 100.0 * sp[t] / st[t]; mdi[t] = 100.0 * sm[t] / st[t]
        tot = pdi[t] + mdi[t]
        dx[t] = 100.0 * abs(pdi[t] - mdi[t]) / tot if tot > 0 else 0.0
    return pdi, mdi, dx


def wilder_adx(H, L, C, n=14):
    """教科書 Wilder ADX。回傳 (+DI, -DI, ADX) 串列。"""
    N = len(C); pdi, mdi, dx = di_dx(H, L, C, n); adx = [None] * N
    idx = [t for t in range(N) if dx[t] is not None]
    if len(idx) < n: return pdi, mdi, adx
    first = idx[n - 1]; a = sum(dx[t] for t in idx[:n]) / n; adx[first] = a
    for t in idx[n:]:
        a = (a * (n - 1) + dx[t]) / n; adx[t] = a
    return pdi, mdi, adx


def sma_dx_adx(H, L, C, n=14):
    """ADX = 最近 n 個 DX 的簡單平均(目前 app.calc_adx 的算法;DI/DX 與 Wilder 版完全相同,只有最後這一步不同)。"""
    N = len(C); pdi, mdi, dx = di_dx(H, L, C, n); adx = [None] * N
    vals = [(t, dx[t]) for t in range(N) if dx[t] is not None]
    for k in range(n - 1, len(vals)):
        adx[vals[k][0]] = sum(v for _, v in vals[k - n + 1:k + 1]) / n
    return pdi, mdi, adx


def pandas_ewm_adx(H, L, C, n=14):
    """pandas ewm(alpha=1/n, adjust=False) 的常見簡寫版(從第一根當種子,沒有 n 根加總的暖機)。回傳最後一根的 (+DI, -DI, ADX) 串列。"""
    import pandas as pd
    h, l, c = pd.Series(H, dtype=float), pd.Series(L, dtype=float), pd.Series(C, dtype=float)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    up, dn = h.diff(), -l.diff()
    pdm = ((up > dn) & (up > 0)) * up; mdm = ((dn > up) & (dn > 0)) * dn
    e = lambda s: s.ewm(alpha=1.0 / n, adjust=False).mean()
    atr = e(tr); pdi = 100 * e(pdm) / atr; mdi = 100 * e(mdm) / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    adx = e(dx)
    f = lambda s: [None if v != v else float(v) for v in s]
    return f(pdi), f(mdi), f(adx)


def classify(adx, pdi, mdi):
    """與 app.market_character 完全相同的規則(25 / 20 門檻、+DI>=-DI 判方向),回傳 label。"""
    if adx is None or pdi is None or mdi is None: return None
    up = pdi >= mdi
    if adx >= 25: return '上升趨勢' if up else '下降趨勢'
    if adx < 20: return '盤整'
    return '趨勢轉換中'
