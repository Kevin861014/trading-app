# -*- coding: utf-8 -*-
"""D4 資金費率完整性檢查(純函式,不連網、不寫檔)。
目的:資金費率缺漏不能被模擬器默默當成 0。無法確認完整性時,引擎停止處理(處理範圍停在缺口之前,不補造、不跳過),並清楚列出符號、時間範圍與原因。

結算時程「可驗證」的依據:
  1. 結算間隔不是固定 8 小時。只有 1、2、4、8 小時四種,且每一筆結算都落在該間隔的 UTC 格線上(容許 5 秒內的毫秒偏移)。
     這個規則已用本機 D2/D3 的 50 個序列、209,297 對相鄰結算實測:0 對違反(見 docs/d4_forward_paper_trading.md)。
  2. 結算間隔可以改變(變短、變長)。判斷缺漏用的是『相鄰紀錄的間距』,不是假設 8 小時:
       - 間距不是 1/2/4/8 小時 → 缺漏(例如 8 小時制少一筆 → 16 小時)。
       - 紀錄不在格線上 → 異常。
       - 間距『變長』後下一個間距又『變回較短』(例如 4h → 8h → 4h)→ 中間少了一筆(缺漏的特徵);變長後持續(或繼續變長)才是真的改制。
         變長後還沒有下一筆可判斷時 → 無法確認,暫停。
  3. 資料覆蓋範圍:第一筆必須不晚於起始時間;最後一筆之後的『下一個預期結算』(以最近的間隔與官方 fundingInfo 的目前間隔取較小者)不得已經落在處理範圍內。
  4. 取得失敗不等於沒有:本次 tick 沒有成功取得該符號的資金費率時,只能處理到『上次成功取得的時間 − 2 小時』。
真實歷史上有這種缺漏:2026-06-24 04:00 官方 fundingRate 對 4 小時制的 JUP、PAXG、PYTH、KAVA、IMX 都沒有這一筆(間距 4h → 8h → 4h),這個檢查會在該處停止。"""
import datetime

HOUR = 3600000
ALLOWED_H = (1, 2, 4, 8)
TOL_MS = 5000
REQUERY_KINDS = ('irregular_spacing', 'possible_missing_settlement', 'coverage_end')       # 這幾種缺漏,先向官方重新要一次(也許只是之前沒抓全)再判斷


def iso(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def interval_h(gap_ms):
    for k in ALLOWED_H:
        if abs(gap_ms - k * HOUR) <= TOL_MS: return k
    return None


def on_grid(t, k):
    m = k * HOUR; r = t % m
    return r <= TOL_MS or m - r <= TOL_MS


def _issue(kind, a, b, detail):
    return {'kind': kind, 'from_ts': int(a), 'to_ts': int(b), 'from_utc': iso(a), 'to_utc': iso(b), 'detail': detail}


def check(rows, T0, T1, info_h=None):
    """rows = [(結算時間 ms, 費率), ...];處理範圍 (T0, T1]。回傳問題清單(空 = 完整)。
    info_h = 官方 fundingInfo 目前的結算間隔(小時;沒有就 None,不假設任何預設值)。"""
    issues = []
    if T1 < T0: return issues
    ts = sorted({int(t) for t, _ in rows})
    if not ts: return [_issue('no_records', T0, T1, '沒有任何資金費率紀錄')]
    if ts[0] > T0: issues.append(_issue('coverage_start', T0, ts[0], '第一筆結算 %s 晚於起始時間,起始前後的結算可能缺漏' % iso(ts[0])))
    ks = [interval_h(b - a) for a, b in zip(ts, ts[1:])]
    for i, (a, b) in enumerate(zip(ts, ts[1:])):
        if not (b > T0 and a < T1): continue                                     # 只看會影響處理範圍的相鄰結算
        k = ks[i]
        if k is None: issues.append(_issue('irregular_spacing', a, b, '相鄰結算間距 %.3f 小時,不是 1/2/4/8 小時,中間缺漏了結算' % ((b - a) / HOUR))); continue
        if not (on_grid(a, k) and on_grid(b, k)): issues.append(_issue('off_grid', a, b, '結算時間不在 %d 小時制的 UTC 格線上' % k)); continue
        prev = ks[i - 1] if i > 0 else None                                       # 序列第一對沒有前一個間距可比,不猜
        if prev is not None and k > prev:                                          # 間距變長:是改制,還是中間少了一筆?
            nxt = ks[i + 1] if i + 1 < len(ks) else None
            if nxt is None: issues.append(_issue('undetermined_after_lengthening', a, b, '間距由 %dh 變成 %dh,下一筆結算尚未出現,無法判斷是改制或缺漏' % (prev, k)))
            elif nxt < k: issues.append(_issue('possible_missing_settlement', a, b, '間距 %dh → %dh → %dh:變長後又變回較短,中間少了一筆結算(官方紀錄沒有)' % (prev, k, nxt)))
    last = ts[-1]; k_last = next((k for k in reversed(ks) if k), None)               # 最近一個有效的間距(最後一對若本身就異常,已另列為問題)
    L = min([x for x in (k_last, info_h) if x] or [1])                                # 完全沒有資訊時用最短的 1 小時(最保守)
    if last + L * HOUR - TOL_MS <= T1: issues.append(_issue('coverage_end', last, T1, '最後一筆結算 %s;依 %d 小時制,下一筆應在 %s,已落在處理範圍內但沒有紀錄' % (iso(last), L, iso(last + L * HOUR))))
    return issues


def limit_ts(issue, T0):
    """這個問題要求處理範圍停在哪裡(整點):缺口前最後一筆結算所在的小時;起始就缺 → 停在起始之前(只暖機)。"""
    if issue['kind'] in ('no_records', 'coverage_start'): return T0 - T0 % HOUR - HOUR
    return issue['from_ts'] - issue['from_ts'] % HOUR
