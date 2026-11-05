# -*- coding: utf-8 -*-
"""C1 資料品質檢查(data_quality.py,純函式)。每個情境都用『明確指定的現在時間』,不連網、不依賴今天是幾號。"""
import datetime, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data_quality as DQ

U = datetime.timezone.utc
HOUR, DAY, WEEK = 3600000, 86400000, 604800000


def ms(y, mo, d, h=0, mi=0):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=U).timestamp() * 1000)


def utc(y, mo, d, h=0, mi=0):
    return datetime.datetime(y, mo, d, h, mi)            # naive UTC,跟 app._utcnow() 一樣


def bars(last_open, step, n, price=100.0):
    return [[last_open - (n - 1 - i) * step, price, price + 1, price - 1, price + (i % 3) * 0.1, 10.0] for i in range(n)]


def daily_rows(dates, price=100.0):
    return [[ms(d.year, d.month, d.day), price, price + 1, price - 1, price, 1.0] for d in dates]


def trading_days(end, n, market):
    out = []; d = end
    while len(out) < n:
        if DQ.is_trading_day(d, market): out.append(d)
        d -= datetime.timedelta(days=1)
    return out[::-1]


def D(y, m, d): return datetime.date(y, m, d)


def boom(): raise AssertionError('benchmark must not be consulted here')


class TestCrypto(unittest.TestCase):
    NOW = utc(2026, 11, 5, 10, 40)          # 4H 的 08:00~12:00 這根還沒收盤;最後已收盤的是 04:00 開盤那根

    def q(self, rows, tf='4h', now=None, **kw): return DQ.assess(rows, tf, 'crypto', now or self.NOW, **kw)

    def test_fresh_4h_is_ok(self):
        q = self.q(bars(ms(2026, 11, 5, 4), 4 * HOUR, 300))
        self.assertEqual((q['status'], q['blocking']), ('ok', False)); self.assertEqual(q['lastClosedBar'], '2026-11-05 04:00 UTC')

    def test_one_bar_behind_is_stale_and_blocking(self):
        q = self.q(bars(ms(2026, 11, 5, 0), 4 * HOUR, 300))
        self.assertEqual((q['status'], q['blocking'], q['lagBars']), ('stale', True, 1)); self.assertIn('落後 1 根', q['detail'])

    def test_publish_grace_period(self):
        rows = bars(ms(2026, 11, 5, 4), 4 * HOUR, 300)
        self.assertEqual(self.q(rows, now=utc(2026, 11, 5, 12, 1))['status'], 'ok')        # 12:00 剛收盤 1 分鐘,新 K 棒可能還沒出來
        self.assertEqual(self.q(rows, now=utc(2026, 11, 5, 12, 3))['status'], 'stale')     # 超過寬限期

    def test_unclosed_last_bar_is_excluded_and_reported(self):
        q = self.q(bars(ms(2026, 11, 5, 8), 4 * HOUR, 300))                                  # 08:00 這根尚未收盤
        self.assertEqual((q['status'], q['blocking']), ('forming', False)); self.assertEqual(q['bars'], 299)
        self.assertEqual(q['lastClosedBar'], '2026-11-05 04:00 UTC'); self.assertIn('forming_trimmed', q['flags'])
        rows, n = DQ.trim_unclosed(bars(ms(2026, 11, 5, 8), 4 * HOUR, 300), '4h', 'crypto', self.NOW)
        self.assertEqual(n, 1); self.assertEqual(rows[-1][0], ms(2026, 11, 5, 4))

    def test_fetch_layer_already_excluded_forming_is_noted_not_alarming(self):
        q = self.q(bars(ms(2026, 11, 5, 4), 4 * HOUR, 300), forming_excluded=True)
        self.assertEqual(q['status'], 'ok'); self.assertTrue(q['formingExcluded'])

    def test_duplicates_backwards_future_offgrid_and_gaps(self):
        base = bars(ms(2026, 11, 5, 4), 4 * HOUR, 300)
        dup = base + [list(base[-1])]
        self.assertEqual(self.q(dup)['status'], 'bad_timestamps'); self.assertIn('重複', self.q(dup)['detail'])
        back = [list(r) for r in base]; back[-5], back[-4] = back[-4], back[-5]
        self.assertEqual(self.q(back)['status'], 'bad_timestamps')
        fut = base + [[ms(2026, 11, 9, 0), 1, 1, 1, 1, 1]]
        self.assertEqual(self.q(fut)['status'], 'bad_timestamps'); self.assertIn('未來', self.q(fut)['detail'])
        off = [list(r) for r in base]; off[-3][0] += 17 * 60000
        self.assertEqual(self.q(off)['status'], 'bad_timestamps'); self.assertIn('格線', self.q(off)['detail'])
        gap = [r for i, r in enumerate(base) if i not in (250, 251)]
        self.assertEqual(self.q(gap)['status'], 'bad_timestamps'); self.assertIn('缺 2 根', self.q(gap)['detail'])
        for rows in (dup, back, fut, off, gap): self.assertTrue(self.q(rows)['blocking'])

    def test_insufficient_failed_and_incomplete_resample(self):
        self.assertEqual(self.q(bars(ms(2026, 11, 5, 4), 4 * HOUR, 30))['status'], 'insufficient')
        self.assertEqual(self.q([])['status'], 'fetch_failed'); self.assertEqual(self.q(None)['status'], 'fetch_failed')
        e = self.q([], fetch_error='HTTP 429'); self.assertEqual(e['status'], 'fetch_failed'); self.assertIn('HTTP 429', e['detail'])
        r = self.q(bars(ms(2026, 11, 5, 4), 4 * HOUR, 300), synth={'from': '1h', 'droppedInternal': 3})
        self.assertEqual((r['status'], r['blocking']), ('incomplete_resample', True))
        ok = self.q(bars(ms(2026, 11, 5, 4), 4 * HOUR, 300), synth={'from': '1h', 'droppedInternal': 0, 'tailIncomplete': True})
        self.assertEqual(ok['status'], 'ok')                                                  # 只有最後一個區間未走完 → 正常(本來就不收)

    def test_priority_when_several_problems(self):
        q = self.q(bars(ms(2026, 11, 5, 0), 4 * HOUR, 30))                                   # 不足 + 過期 同時成立 → 以『資料不足』為主,並列出其他
        self.assertEqual(q['status'], 'insufficient'); self.assertIn('stale', q.get('alsoFound', {}))

    def test_daily_and_weekly(self):
        self.assertEqual(self.q(bars(ms(2026, 11, 4), DAY, 300), '1d')['status'], 'ok')      # 今天 11/05 的日線尚未收盤,最後已收盤是 11/04
        self.assertEqual(self.q(bars(ms(2026, 11, 3), DAY, 300), '1d')['status'], 'stale')
        mon = ms(2026, 10, 26)                                                                # 現在是 11/05(週四);已收盤的最後一週開盤於 10/26
        self.assertEqual(self.q(bars(mon, WEEK, 300), '1w')['status'], 'ok')
        self.assertEqual(self.q(bars(mon - WEEK, WEEK, 300), '1w')['status'], 'stale')
        self.assertEqual(self.q(bars(ms(2026, 11, 2), WEEK, 300), '1w')['status'], 'forming')   # 本週的週線還沒收

    def test_never_raises(self):
        for junk in ([[1]], [["x"] * 6], [[None] * 6]):
            q = self.q(junk); self.assertTrue(q['blocking']); self.assertIn(q['status'], ('fetch_failed', 'bad_timestamps'))


class TestStocksAndHolidays(unittest.TestCase):
    def assess(self, market, rows, now, tf='1d', bench=None, **kw):
        return DQ.assess(rows, tf, market, now, benchmark_dates=bench, **kw)

    def test_us_holiday_rules(self):
        h = DQ.us_market_holidays(2026)
        for d in (D(2026, 1, 1), D(2026, 1, 19), D(2026, 2, 16), D(2026, 4, 3), D(2026, 5, 25), D(2026, 6, 19), D(2026, 7, 3), D(2026, 9, 7), D(2026, 11, 26), D(2026, 12, 25)):
            self.assertIn(d, h, d)
        self.assertEqual(len(h), 10)
        self.assertNotIn(D(2027, 12, 31), DQ.us_market_holidays(2027))          # 新年遇週六:NYSE 不提前到週五
        self.assertIn(D(2028, 1, 17), DQ.us_market_holidays(2028))
        self.assertNotIn(D(2021, 6, 18), DQ.us_market_holidays(2021))            # Juneteenth 2022 起才休市

    def test_weekend_is_not_a_data_fault_tw(self):
        rows = daily_rows(trading_days(D(2026, 11, 6), 300, 'tw'))                # 最後一根:週五 11/06
        for now in (utc(2026, 11, 7, 6), utc(2026, 11, 8, 12), utc(2026, 11, 9, 0, 30)):   # 週六、週日、週一台北 08:30(未開盤)
            q = self.assess('tw', rows, now, bench=boom)
            self.assertEqual((q['status'], q['blocking']), ('ok', False), now)
        self.assertEqual(DQ.market_state(utc(2026, 11, 7, 6), 'tw')['code'], 'weekend')

    def test_weekend_is_not_a_data_fault_us(self):
        rows = daily_rows(trading_days(D(2026, 11, 6), 300, 'us'))
        self.assertEqual(self.assess('us', rows, utc(2026, 11, 8, 15), bench=boom)['status'], 'ok')

    def test_us_thanksgiving_and_good_friday_need_no_benchmark(self):
        rows = daily_rows(trading_days(D(2026, 11, 25), 300, 'us'))               # 最後一根 11/25(週三);11/26 感恩節休市
        q = self.assess('us', rows, utc(2026, 11, 26, 22), bench=boom)
        self.assertEqual(q['status'], 'ok'); self.assertEqual(DQ.market_state(utc(2026, 11, 26, 22), 'us')['code'], 'holiday')
        rows = daily_rows(trading_days(D(2026, 4, 2), 300, 'us'))                 # 耶穌受難日 4/3
        self.assertEqual(self.assess('us', rows, utc(2026, 4, 3, 22), bench=boom)['status'], 'ok')

    def test_session_not_yet_closed_expects_previous_day(self):
        rows = daily_rows(trading_days(D(2026, 11, 9), 300, 'tw'))                # 最後一根週一
        q = self.assess('tw', rows, utc(2026, 11, 10, 3), bench=boom)             # 週二台北 11:00,盤中
        self.assertEqual(q['status'], 'ok')
        late = self.assess('tw', rows, utc(2026, 11, 10, 6, 5), bench=lambda: {'2026-11-10'})   # 收盤 13:30 + 30 分鐘寬限後,週二的日線應該出現
        self.assertEqual(late['status'], 'stale')

    def test_tw_unlisted_holiday_uses_benchmark_evidence(self):
        rows = daily_rows(trading_days(D(2026, 11, 9), 300, 'tw'))
        now = utc(2026, 11, 10, 8)                                                # 週二收盤後;假設 11/10 是臨時休市日
        closed = self.assess('tw', rows, now, bench={'2026-11-06', '2026-11-09'})          # 大盤 11/10 也沒有資料 → 休市,資料正常
        self.assertEqual((closed['status'], closed['blocking'], closed['marketClosed']), ('ok', False, True)); self.assertIn('休市', closed['detail'])
        stale = self.assess('tw', rows, now, bench={'2026-11-09', '2026-11-10'})           # 大盤有開,個股沒更新 → 過期
        self.assertEqual((stale['status'], stale['blocking']), ('stale', True)); self.assertIn('沒有更新', stale['detail'])
        unknown = self.assess('tw', rows, now, bench=lambda: None)                         # 查不到基準 → 為安全視為過期,並說明原因
        self.assertEqual((unknown['status'], unknown['blocking']), ('stale', True)); self.assertIn('無法取得大盤基準', unknown['detail'])

    def test_benchmark_is_only_fetched_when_the_stock_lags(self):
        rows = daily_rows(trading_days(D(2026, 11, 9), 300, 'tw')); calls = []
        def bench(): calls.append(1); return {'2026-11-10'}
        self.assess('tw', rows, utc(2026, 11, 9, 8), bench=bench); self.assertEqual(calls, [])       # 沒落後 → 不查
        self.assess('tw', rows, utc(2026, 11, 10, 8), bench=bench); self.assertEqual(len(calls), 1)  # 落後 → 查一次

    def test_long_closure_e_g_lunar_new_year(self):
        rows = daily_rows(trading_days(D(2026, 2, 12), 300, 'tw'))                # 假設 2/13~2/22 連休,最後一根 2/12
        now = utc(2026, 2, 20, 8)
        q = self.assess('tw', rows, now, bench={'2026-02-12'})
        self.assertEqual((q['status'], q['marketClosed']), ('ok', True))
        q2 = self.assess('tw', rows, utc(2026, 3, 2, 8), bench={'2026-02-12', '2026-02-23', '2026-02-24'})
        self.assertEqual(q2['status'], 'stale')                                   # 大盤已恢復交易,個股仍停在 2/12

    def test_unclosed_daily_bar_is_trimmed(self):
        rows = daily_rows(trading_days(D(2026, 11, 10), 300, 'tw'))               # 含今天(週二)的日線,但現在台北 10:00 尚未收盤
        q = self.assess('tw', rows, utc(2026, 11, 10, 2))
        self.assertEqual((q['status'], q['bars']), ('forming', 299)); self.assertEqual(q['lastClosedBar'], '2026-11-09')

    def test_timestamps_for_daily_must_be_whole_days(self):
        rows = daily_rows(trading_days(D(2026, 11, 6), 300, 'tw')); rows[-3][0] += 3600000
        self.assertEqual(self.assess('tw', rows, utc(2026, 11, 7, 6))['status'], 'bad_timestamps')

    def test_weekly_stock_bars(self):
        mons = [D(2026, 11, 2) - datetime.timedelta(weeks=i) for i in range(299, -1, -1)]
        rows = daily_rows(mons)
        self.assertEqual(self.assess('us', rows, utc(2026, 11, 7, 12), '1w', bench=boom)['status'], 'ok')           # 週六:11/02 那週已收
        mid = self.assess('us', rows, utc(2026, 11, 4, 14), '1w')                                                 # 週三:11/02 這週還沒收 → 排除,以 10/26 為準
        self.assertEqual((mid['status'], mid['lastClosedBar']), ('forming', '2026-10-26'))
        older = daily_rows(mons[:-1])
        self.assertEqual(self.assess('us', older, utc(2026, 11, 7, 12), '1w', bench={'2026-11-02', '2026-11-03'})['status'], 'stale')
        self.assertEqual(self.assess('us', older, utc(2026, 11, 7, 12), '1w', bench={'2026-10-30'})['status'], 'ok')  # 大盤這週沒開 → 休市

    def test_intraday_stock_lag_during_open_session(self):
        # 週三 NY 14:00(盤中):最後已收盤的 1H K 棒還停在週二 15:30 → 落後太久
        ny = lambda d, h, m: ms(2026, 11, d, h + 5, m)                             # 11 月美東 = UTC-5
        rows = [[ny(3, 15, 30) - i * HOUR, 1, 1, 1, 1, 1] for i in range(300)][::-1]
        q = DQ.assess(rows, '1h', 'us', utc(2026, 11, 4, 19))
        self.assertEqual(q['status'], 'stale'); self.assertIn('盤中資料落後', q['detail'])
        self.assertEqual(DQ.assess(rows, '1h', 'us', utc(2026, 11, 3, 23))['status'], 'ok')    # 週二收盤後:正常


if __name__ == '__main__':
    unittest.main()
