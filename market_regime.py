# -*- coding: utf-8 -*-
"""C2:市場環境分類(純函式,不連網,不依賴 app / sim)。

分類條件(與網站卡片上的『市場性格』徽章 app.market_character 完全相同,所以全站只有一種定義):
  ADX (Wilder, 14) 與 +DI / −DI 都先四捨五入到小數 1 位(和徽章一樣),再判斷:
    ADX >= 25                    趨勢:+DI >= −DI → 上升趨勢(up),否則 → 下降趨勢(down)
    ADX <  20                    盤整(range)
    20 <= ADX < 25               趨勢轉換中(transition)
    ADX / DI 尚未有值(前 27 根)   未分類(na)
無前視保證:第 i 根的分類只使用第 0..i 根(已收盤)的 H/L/C。ADX 用教科書 Wilder(前 14 個 DX 平均當第一個值,之後 (ADX*13+DX)/14),
逐根遞迴,所以前綴與全段算出來的結果相同(測試驗證)。這裡**不使用 sim.dmi**(它的前 26 根有已知的暖機前視,見 docs/tech_debt.md)。
分類只描述『當時的環境』,不含任何事後漲跌;交易績效是事後結果,兩者在輸出裡分開。
"""
import bisect

N = 14
TREND_TH = 25.0
RANGE_TH = 20.0
UP, DOWN, RANGE, TRANSITION, NA = 'up', 'down', 'range', 'transition', 'na'
CODES = (UP, DOWN, RANGE, TRANSITION, NA)
LABEL = {UP: '上升趨勢', DOWN: '下降趨勢', RANGE: '盤整', TRANSITION: '趨勢轉換中', NA: '未分類（暖機／資料不足）'}
RULES = [
    ('上升趨勢', 'ADX (Wilder, 14) ≥ 25 且 +DI ≥ −DI'),
    ('下降趨勢', 'ADX (Wilder, 14) ≥ 25 且 +DI < −DI'),
    ('盤整', 'ADX (Wilder, 14) < 20'),
    ('趨勢轉換中', '20 ≤ ADX (Wilder, 14) < 25'),
    ('未分類', '資料最前面 27 根（ADX 還沒有值）'),
]


def causal_dmi(H, L, C, n=N):
    """教科書 Wilder +DI、−DI、ADX。回傳三個長度 len(C) 的串列,還沒有值的位置是 None。第 i 個值只用第 0..i 根。"""
    size = len(C); pdi = [None] * size; mdi = [None] * size; adx = [None] * size
    if size <= n: return pdi, mdi, adx
    tr = [0.0] * size; pdm = [0.0] * size; mdm = [0.0] * size
    for t in range(1, size):
        up, dn = H[t] - H[t - 1], L[t - 1] - L[t]
        pdm[t] = up if (up > dn and up > 0) else 0.0
        mdm[t] = dn if (dn > up and dn > 0) else 0.0
        tr[t] = max(H[t] - L[t], abs(H[t] - C[t - 1]), abs(L[t] - C[t - 1]))
    st, sp, sm = sum(tr[1:n + 1]), sum(pdm[1:n + 1]), sum(mdm[1:n + 1])
    dx = [None] * size; seq = []
    for t in range(n, size):
        if t > n:
            st = st - st / n + tr[t]; sp = sp - sp / n + pdm[t]; sm = sm - sm / n + mdm[t]
        if st > 0:
            pdi[t] = 100.0 * sp / st; mdi[t] = 100.0 * sm / st
            tot = pdi[t] + mdi[t]
            dx[t] = 100.0 * abs(pdi[t] - mdi[t]) / tot if tot > 0 else 0.0
            seq.append(t)
    if len(seq) >= n:
        a = sum(dx[t] for t in seq[:n]) / n; adx[seq[n - 1]] = a
        for t in seq[n:]:
            a = (a * (n - 1) + dx[t]) / n; adx[t] = a
    return pdi, mdi, adx


def classify_values(adx, pdi, mdi):
    """單一時間點的分類(和 app.market_character 同規則,先四捨五入到 1 位)。"""
    if adx is None or pdi is None or mdi is None: return NA
    adx, pdi, mdi = round(adx, 1), round(pdi, 1), round(mdi, 1)
    if adx >= TREND_TH: return UP if pdi >= mdi else DOWN
    if adx < RANGE_TH: return RANGE
    return TRANSITION


def classify_series(rows):
    """rows = [[ts,o,h,l,c,v],...](必須是已收盤 K 棒)。回傳每根 K 棒的分類代碼;第 i 個只用第 0..i 根。"""
    H = [r[2] for r in rows]; L = [r[3] for r in rows]; C = [r[4] for r in rows]
    pdi, mdi, adx = causal_dmi(H, L, C)
    return [classify_values(adx[i], pdi[i], mdi[i]) for i in range(len(C))]


def align_reference(main_ts, ref_ts, ref_codes, step_ms, max_gap_bars=5):
    """把大盤（參考）的分類對到主標的每一根 K 棒:取『開盤時間 <= 主標的這一根開盤時間』的最後一根參考 K 棒。
    同週期、同市場時,兩者收盤時間相同,所以決策當下已經確定;絕不使用比這根更晚的參考 K 棒。
    參考 K 棒比主標的舊超過 max_gap_bars 根（長假、缺資料）→ 未分類,不拿很舊的環境來湊。"""
    out = []
    for ts in main_ts:
        j = bisect.bisect_right(ref_ts, ts) - 1
        out.append(ref_codes[j] if (j >= 0 and ts - ref_ts[j] <= max_gap_bars * step_ms) else NA)
    return out


def share(codes, start_idx=0):
    """分類在 codes[start_idx:] 的佔比（K 棒數與百分比）。"""
    seg = codes[start_idx:]; n = len(seg)
    return {c: {'bars': sum(1 for x in seg if x == c), 'pct': round(100.0 * sum(1 for x in seg if x == c) / n, 1) if n else 0.0} for c in CODES}
