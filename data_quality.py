# -*- coding: utf-8 -*-
"""資料品質檢查(C1)。純函式:不連網、不讀快取、不改任何資料——只根據『已經取得的 K 棒』與『現在時間』回答:這份資料能不能當成最新資料用?

狀態(status)與是否阻擋(blocking:True = 這份資料不可顯示成「最新」訊號/狀態):
  ok                   資料正常                 否
  forming              K 棒尚未收盤(已排除)     否    傳進來的資料最後一根還沒收盤;已排除,以下以上一根已收盤 K 棒為準
  insufficient         資料不足                 是
  stale                資料過期                 是    最新已收盤 K 棒比「應有的」舊(休市日不算)
  incomplete_resample  合成時間週期不完整        是    由較細週期合成(例如 1H→4H)時有缺漏的區間
  bad_timestamps       時間戳異常或重複          是    重複、倒退、未來、不在週期格線上、近期缺 K 棒
  fetch_failed         資料取得失敗              是
另外 unsupported(資料來源不支援這個週期)由呼叫端處理:那不是資料品質問題,而且絕不用別的週期代替。

休市判斷(台股、美股):
  1. 週末一定休市;美股國定假日用 NYSE 的規則算(含週末遇假日的順延、耶穌受難日)。
  2. 台股的臨時/農曆假日無法用規則算出,所以不靠硬編的假日表,而是『拿大盤基準(^TWII / SPY)的日線當證據』:
     只有當個股的最新日期比預期舊時才去看基準;基準在那幾天也沒有 K 棒 → 市場休市(資料正常);基準有 → 這個標的自己沒更新(過期)。
     查不到基準 → 無法確認是不是休市,為了安全一律標過期(並說明原因)。
"""
import datetime

_UTC = datetime.timezone.utc

STATUS = {
    'ok':                  ('資料正常', False),
    'forming':             ('K 棒尚未收盤', False),
    'insufficient':        ('資料不足', True),
    'stale':               ('資料過期', True),
    'incomplete_resample': ('合成時間週期不完整', True),
    'bad_timestamps':      ('時間戳異常或重複', True),
    'fetch_failed':        ('資料取得失敗', True),
}
PRIORITY = ['fetch_failed', 'bad_timestamps', 'incomplete_resample', 'insufficient', 'stale', 'forming', 'ok']

STEP_MS = {'1h': 3600000, '4h': 14400000, '1d': 86400000, '1w': 604800000}
WEEK_OFFSET_MS = 4 * 86400000                 # epoch(1970-01-01)是週四;週一 00:00 UTC = epoch + 4 天
CRYPTO_GRACE_S = 120                          # 交易所剛收盤後,K 棒出現前的合理延遲
SESSION_GRACE_MIN = 30                        # 股市收盤後,資料商更新日線前的合理延遲
SESSION = {'tw': ('Asia/Taipei', (9, 0), (13, 30)), 'us': ('America/New_York', (9, 30), (16, 0)),
           'commodity': ('America/New_York', (9, 30), (16, 0)), 'metal_etf': ('America/New_York', (9, 30), (16, 0))}
BENCHMARK = {'tw': '^TWII', 'us': 'SPY', 'commodity': 'SPY', 'metal_etf': 'SPY'}
FMT_DATE, FMT_TIME = '%Y-%m-%d', '%Y-%m-%d %H:%M'


def _zi(name):
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


def to_utc_aware(now):
    if now.tzinfo is None: return now.replace(tzinfo=_UTC)
    return now.astimezone(_UTC)


# ───────────────────────── 日曆 ─────────────────────────
def _easter(year):
    a = year % 19; b, c = divmod(year, 100); d, e = divmod(b, 4); f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i, k = divmod(c, 4); l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451; month = (h + l - 7 * m + 114) // 31; day = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    d = datetime.date(year, month, 1); d += datetime.timedelta(days=(weekday - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = datetime.date(year + (month == 12), (month % 12) + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() - weekday) % 7)


def us_market_holidays(year):
    """NYSE 休市日(依規則計算;週六遇假日提前到週五、週日順延到週一,新年遇週六不補休)。"""
    def observed(d):
        if d.weekday() == 5: return d - datetime.timedelta(days=1)
        if d.weekday() == 6: return d + datetime.timedelta(days=1)
        return d
    h = set()
    ny = datetime.date(year, 1, 1)
    if ny.weekday() != 5: h.add(observed(ny))
    h.add(_nth_weekday(year, 1, 0, 3)); h.add(_nth_weekday(year, 2, 0, 3))                       # MLK、總統日
    h.add(_easter(year) - datetime.timedelta(days=2))                                            # 耶穌受難日
    h.add(_last_weekday(year, 5, 0))                                                             # 陣亡將士紀念日
    if year >= 2022: h.add(observed(datetime.date(year, 6, 19)))                                  # Juneteenth
    h.add(observed(datetime.date(year, 7, 4))); h.add(_nth_weekday(year, 9, 0, 1))                # 獨立紀念日、勞動節
    h.add(_nth_weekday(year, 11, 3, 4)); h.add(observed(datetime.date(year, 12, 25)))            # 感恩節、聖誕節
    return h


def is_trading_day(d, market):
    """依規則判斷(週末、美股國定假日)。台股的農曆/臨時假日靠『大盤基準證據』,不在這裡硬編。"""
    if d.weekday() >= 5: return False
    if market in ('us', 'commodity', 'metal_etf') and d in us_market_holidays(d.year): return False
    return True


def _prev_trading_day(d, market):
    d -= datetime.timedelta(days=1)
    while not is_trading_day(d, market): d -= datetime.timedelta(days=1)
    return d


def _next_trading_day(d, market):
    d += datetime.timedelta(days=1)
    while not is_trading_day(d, market): d += datetime.timedelta(days=1)
    return d


def last_closed_session_date(now_utc, market):
    """『依規則』目前應該已經收盤的最近一個交易日(當地日期)。收盤後再等 SESSION_GRACE_MIN 分鐘才算(給資料商更新時間)。"""
    tz, _, close = SESSION[market]; now = to_utc_aware(now_utc).astimezone(_zi(tz))
    d = now.date()
    close_dt = datetime.datetime.combine(d, datetime.time(*close), tzinfo=_zi(tz)) + datetime.timedelta(minutes=SESSION_GRACE_MIN)
    if is_trading_day(d, market) and now >= close_dt: return d
    return _prev_trading_day(d, market)


def market_state(now_utc, market):
    """目前市場狀態(只用規則,供畫面說明;不用來判斷資料好壞)。"""
    if market == 'crypto': return {'code': '24x7', 'label': '加密貨幣 24 小時交易'}
    tz, op, close = SESSION[market]; now = to_utc_aware(now_utc).astimezone(_zi(tz)); d = now.date()
    if d.weekday() >= 5: return {'code': 'weekend', 'label': '週末休市'}
    if not is_trading_day(d, market): return {'code': 'holiday', 'label': '國定假日休市'}
    t = (now.hour, now.minute)
    if op <= t < close: return {'code': 'open', 'label': '盤中'}
    return {'code': 'closed', 'label': '盤前' if t < op else '已收盤'}


# ───────────────────────── K 棒時間 ─────────────────────────
def _dt(ms):
    return datetime.datetime.fromtimestamp(ms / 1000.0, _UTC)


def bar_close_utc(ts_ms, interval, market):
    """一根 K 棒『收盤』的 UTC 時間。日線/週線的時間戳是『交易所當地日期的 00:00 UTC』標籤。"""
    if market == 'crypto' or interval in ('1h', '4h'):
        return _dt(ts_ms + STEP_MS[interval])
    tz, _, close = SESSION[market]; d = _dt(ts_ms).date()
    if interval == '1w': d = d + datetime.timedelta(days=4)                  # 該週週五(保守:假日週縮短時仍視為週五才收)
    return datetime.datetime.combine(d, datetime.time(*close), tzinfo=_zi(tz)).astimezone(_UTC)


def trim_unclosed(rows, interval, market, now_utc):
    """去掉還沒收盤的 K 棒(尾端)。回傳 (rows, 被去掉的根數)。已確認訊號與指標只能用已收盤的 K 棒。"""
    now = to_utc_aware(now_utc); out = list(rows); n = 0
    while out and bar_close_utc(out[-1][0], interval, market) > now:
        out.pop(); n += 1
    return out, n


def label(ms, interval, market):
    """畫面用的時間字串(當地時間;加密與日內另附 UTC)。"""
    d = _dt(ms)
    if interval in ('1d', '1w'): return d.strftime(FMT_DATE)
    if market in SESSION: return d.astimezone(_zi(SESSION[market][0])).strftime(FMT_TIME)
    return d.strftime(FMT_TIME) + ' UTC'


def check_timestamps(rows, interval, market, now_utc):
    """回傳問題清單(空 = 正常)。檢查:重複、倒退、未來、不在週期格線上、加密近期缺 K 棒。"""
    problems = []; step = STEP_MS[interval]; now_ms = to_utc_aware(now_utc).timestamp() * 1000
    ts = [r[0] for r in rows]
    dup = sum(1 for i in range(1, len(ts)) if ts[i] == ts[i - 1]); back = sum(1 for i in range(1, len(ts)) if ts[i] < ts[i - 1])
    if dup: problems.append('重複時間戳 %d 筆' % dup)
    if back: problems.append('時間戳倒退 %d 處' % back)
    if ts and ts[-1] > now_ms + step: problems.append('最後一根的時間在未來(%s)' % label(ts[-1], interval, market))
    if market == 'crypto' or interval in ('1h', '4h'):
        base = WEEK_OFFSET_MS if interval == '1w' else 0
        if market == 'crypto':
            off = sum(1 for t in ts if (t - base) % step != 0)
            if off: problems.append('有 %d 根不在 %s 的時間格線上' % (off, interval))
    else:
        off = sum(1 for t in ts if t % 86400000 != 0)
        if off: problems.append('日/週線時間戳不是整日 %d 筆' % off)
    if market == 'crypto' and len(ts) > 2 and not dup and not back:
        recent = ts[-100:]; missing = sum(max(0, (recent[i] - recent[i - 1]) // step - 1) for i in range(1, len(recent)))
        if missing: problems.append('最近 %d 根內缺 %d 根 K 棒' % (len(recent), missing))
    return problems


# ───────────────────────── 新鮮度 ─────────────────────────
def _mondays_after(d):
    return d - datetime.timedelta(days=d.weekday())


def _week_complete(e, market):
    """交易日 e 所在那一週,是不是已經交易完(之後的下一個交易日落在更後面的週)。"""
    return _next_trading_day(e, market).isocalendar()[:2] != e.isocalendar()[:2]


def freshness(rows, interval, market, now_utc, benchmark_dates=None):
    """回傳 dict: {stale:bool, unknown:bool, lag:int, expected:str, detail:str, marketClosed:bool}。
    benchmark_dates:大盤基準日線的日期集合(set of 'YYYY-MM-DD'),或一個回傳它的函式(只在『個股落後』時才會被呼叫);None = 沒有證據。"""
    now = to_utc_aware(now_utc); last = rows[-1][0]; res = {'stale': False, 'unknown': False, 'lag': 0, 'expected': None, 'detail': '', 'marketClosed': False}
    if market == 'crypto':
        step = STEP_MS[interval]; t = now.timestamp() * 1000 - CRYPTO_GRACE_S * 1000; base = WEEK_OFFSET_MS if interval == '1w' else 0
        cur = int((t - base) // step * step + base); exp = cur - step
        res['expected'] = label(exp, interval, market)
        lag = int((exp - last) // step)
        if lag > 0:
            res.update(stale=True, lag=lag, detail='最新已收盤的 %s K 棒應為 %s,但資料只到 %s(落後 %d 根)' % (interval, label(exp, interval, market), label(last, interval, market), lag))
        return res
    tz, op, close = SESSION[market]; zone = _zi(tz); e = last_closed_session_date(now, market)
    res['expected'] = e.strftime(FMT_DATE)
    if interval == '1w':
        m_last = _dt(last).date(); e_week = _mondays_after(e) if _week_complete(e, market) else _mondays_after(e) - datetime.timedelta(days=7)
        if m_last >= e_week: return res
        lo, hi, what = m_last + datetime.timedelta(days=7), e, '週'
    else:
        l_date = _dt(last).date() if interval == '1d' else _dt(last).astimezone(zone).date()
        if l_date >= e:
            if interval == '1h':                                          # 盤中:最後一根已收盤的 1H 不能比現在落後太多
                st = market_state(now, market)
                if st['code'] == 'open' and now - bar_close_utc(last, interval, market) > datetime.timedelta(hours=2):
                    lag = int((now - bar_close_utc(last, interval, market)).total_seconds() // 3600)
                    res.update(stale=True, lag=lag, detail='盤中資料落後約 %d 小時(最後已收盤 K 棒 %s)' % (lag, label(last, interval, market)))
            return res
        lo, hi, what = l_date + datetime.timedelta(days=1), e, '日'
    missing = []; d = lo
    while d <= hi:
        if is_trading_day(d, market): missing.append(d)
        d += datetime.timedelta(days=1)
    if not missing: return res
    ev = benchmark_dates() if callable(benchmark_dates) else benchmark_dates
    res['lag'] = len(missing)
    if ev is None:
        res.update(stale=True, unknown=True, detail='最新已收盤資料(%s)比預期的 %s 舊,但無法取得大盤基準(%s)來確認是不是休市,為安全起見視為過期' % (label(last, interval, market), e, BENCHMARK[market]))
    elif any(d.strftime(FMT_DATE) in ev for d in missing):
        res.update(stale=True, detail='大盤(%s)在 %s 之後有開盤,但這個標的的最新已收盤資料只到 %s,沒有更新' % (BENCHMARK[market], missing[0].strftime(FMT_DATE), label(last, interval, market)))
    else:
        res.update(marketClosed=True, detail='%s 休市:大盤(%s)在 %s ~ %s 沒有任何交易,所以資料停在 %s 是正常的' % (market.upper(), BENCHMARK[market], missing[0].strftime(FMT_DATE), missing[-1].strftime(FMT_DATE), label(last, interval, market)))
    return res


# ───────────────────────── 主評估 ─────────────────────────
def assess(rows, interval, market, now_utc, *, fetch_error=None, synth=None, forming_excluded=False, min_bars=60, benchmark_dates=None):
    """評估一份 K 棒。rows = [[ts,o,h,l,c,v],...](可以含還沒收盤的最後一根;會被排除)。
    回傳 dict:status/label/blocking/detail/flags/bars/lastClosedBar(ms 與字串)/expectedLast/lagBars/marketState/formingExcluded/marketClosed。
    不丟例外:任何內部錯誤都回報成 bad_timestamps 之外的 fetch_failed(附原因),避免畫面誤顯示正常。"""
    flags, details = [], {}
    base = {'status': 'fetch_failed', 'label': STATUS['fetch_failed'][0], 'blocking': True, 'detail': '', 'flags': flags, 'bars': 0,
            'lastClosedBar': None, 'lastClosedBarMs': None, 'expectedLast': None, 'lagBars': 0, 'formingExcluded': bool(forming_excluded), 'marketClosed': False,
            'marketState': market_state(now_utc, market)}
    try:
        if fetch_error or not rows:
            base['detail'] = '取得失敗:%s' % (fetch_error or '沒有取得任何 K 棒'); return base
        kept, trimmed = trim_unclosed(rows, interval, market, now_utc)
        if trimmed: flags.append('forming_trimmed')
        if forming_excluded: flags.append('forming_excluded_at_fetch')
        found = {}
        probs = check_timestamps(rows, interval, market, now_utc)          # 檢查『原始』資料(含尚未收盤的那根),才抓得到未來時間戳
        if probs: found['bad_timestamps'] = ';'.join(probs)
        if synth and synth.get('droppedInternal'):
            found['incomplete_resample'] = '由 %s 合成時有 %d 個區間不完整而被捨棄(缺少細週期 K 棒)' % (synth.get('from', '較細週期'), synth['droppedInternal'])
        if len(kept) < min_bars: found['insufficient'] = '只有 %d 根已收盤 K 棒,少於 %d 根,不足以計算指標' % (len(kept), min_bars)
        fr = None
        if kept and 'bad_timestamps' not in found:
            fr = freshness(kept, interval, market, now_utc, benchmark_dates)
            base['expectedLast'] = fr['expected']; base['lagBars'] = fr['lag']; base['marketClosed'] = fr['marketClosed']
            if fr['stale']: found['stale'] = fr['detail']
            elif fr['marketClosed']: flags.append('market_closed')
        if kept and len(kept) < 220: flags.append('no_ema200')
        if trimmed: found['forming'] = '最後 %d 根 K 棒尚未收盤,已排除;以下以上一根已收盤 K 棒為準' % trimmed
        status = next((s for s in PRIORITY if s in found), 'ok')
        detail = found.get(status, '')
        if status == 'ok' and fr and fr['marketClosed']: detail = fr['detail']
        base.update(status=status, label=STATUS[status][0], blocking=STATUS[status][1], bars=len(kept), detail=detail)
        if kept:
            base['lastClosedBarMs'] = kept[-1][0]; base['lastClosedBar'] = label(kept[-1][0], interval, market)
        if len(found) > 1: base['alsoFound'] = {k: v for k, v in found.items() if k != status}
        return base
    except Exception as e:                                                  # 品質檢查本身出錯 → 不能假裝正常
        base.update(status='fetch_failed', label=STATUS['fetch_failed'][0], blocking=True, detail='品質檢查發生錯誤:%s' % e)
        return base
