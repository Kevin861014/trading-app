# -*- coding: utf-8 -*-
"""C1 /api/mtf:多週期技術狀態 + 資料品質 + Research Core 事件。資料用固定種子的合成資料,不連網。"""
import datetime, os, random, sys, threading, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import data_quality as DQ
import sim as S

HOUR, DAY, WEEK = 3600000, 86400000, 604800000
NOW = datetime.datetime(2026, 11, 5, 10, 40)                      # 週四;台北 18:40(已收盤)、紐約 05:40(盤前)
U = datetime.timezone.utc


def ms(y, mo, d, h=0, mi=0):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=U).timestamp() * 1000)


def walk(last_open, step, n, seed, start=100.0):
    r = random.Random(seed); px = start; out = []
    for i in range(n):
        o = px; c = o * (1 + r.uniform(-0.012, 0.0125)); h = max(o, c) * (1 + r.uniform(0, 0.006)); l = min(o, c) * (1 - r.uniform(0, 0.006))
        out.append([last_open - (n - 1 - i) * step, o, h, l, c, 1000 + i]); px = c
    return out


def trading_day_rows(end, n, market, seed):
    days = []; d = end
    while len(days) < n:
        if DQ.is_trading_day(d, market): days.append(d)
        d -= datetime.timedelta(days=1)
    days.reverse(); r = random.Random(seed); px = 100.0; out = []
    for d in days:
        o = px; c = o * (1 + r.uniform(-0.012, 0.0125)); out.append([ms(d.year, d.month, d.day), o, max(o, c) * 1.004, min(o, c) * 0.996, c, 1000]); px = c
    return out


def crypto_book(now=NOW):
    return {'1w': walk(ms(2026, 10, 26), WEEK, 300, 1), '1d': walk(ms(2026, 11, 4), DAY, 900, 2),
            '4h': walk(ms(2026, 11, 5, 4), 4 * HOUR, 1500, 3), '1h': walk(ms(2026, 11, 5, 9), HOUR, 1500, 4)}


def tw_book():
    return {'1w': [[ms(2026, 11, 2) - i * WEEK, 100, 101, 99, 100 + i * 0.01, 1] for i in range(299, -1, -1)],
            '1d': trading_day_rows(datetime.date(2026, 11, 5), 700, 'tw', 5),
            '1h': [[ms(2026, 11, 5, 5) - i * HOUR, 100, 101, 99, 100 + (i % 7) * 0.1, 1] for i in range(600, -1, -1)]}   # 13:00 台北開盤的最後一根


class Base(unittest.TestCase):
    BOOK = staticmethod(crypto_book)
    SYMBOL = 'BTC/USDT'

    def setUp(self):
        self.book = self.BOOK(); self.calls = []; self.fail = set()
        def fake(symbol, start, interval='1d'):
            self.calls.append((symbol, interval))
            if interval in self.fail: raise RuntimeError('boom ' + interval)
            return self.book.get(interval, [])
        self.ps = [mock.patch.object(A, 'fetch_data', fake), mock.patch.object(A, '_utcnow', lambda: NOW)]
        for p in self.ps: p.start()
        self.client = A.app.test_client()

    def tearDown(self):
        for p in reversed(self.ps): p.stop()

    def mtf(self, **q):
        q.setdefault('symbol', self.SYMBOL); r = self.client.get('/api/mtf', query_string=q); self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300]); return r.get_json()

    @staticmethod
    def by(d): return {e['tf']: e for e in d['timeframes']}


class TestCryptoMtf(Base):
    def test_all_four_timeframes_with_real_indicators(self):
        d = self.mtf(); e = self.by(d)
        self.assertEqual([x['tf'] for x in d['timeframes']], ['1w', '1d', '4h', '1h'])
        for tf in ('1w', '1d', '4h', '1h'):
            self.assertTrue(e[tf]['supported']); self.assertEqual(e[tf]['quality']['status'], 'ok', (tf, e[tf]['quality']['detail'])); self.assertTrue(e[tf]['usable'])
        self.assertEqual(e['4h']['data']['lastBarUtc'], '2026-11-05 04:00'); self.assertEqual(e['1w']['data']['lastBarUtc'], '2026-10-26'); self.assertEqual(e['1d']['data']['lastBarUtc'], '2026-11-04')
        self.assertIn('不是價格預測', d['disclaimer']); self.assertIn('不是價格預測', d['summary']['note'])

    def test_indicators_equal_the_existing_functions_on_closed_bars(self):
        e = self.by(self.mtf())['1d']['indicators']; rows = self.book['1d']
        C = [r[4] for r in rows]; H = [r[2] for r in rows]; L = [r[3] for r in rows]
        adx = A.calc_adx(rows); mc = A.market_character(rows)
        self.assertEqual((e['adx'], e['plusDi'], e['minusDi']), (adx['adx'], adx['plus_di'], adx['minus_di'])); self.assertEqual(e['trendCode'], mc['code'])
        self.assertAlmostEqual(e['ema20'], S.ema(C, 20)[-1], places=2); self.assertAlmostEqual(e['ema50'], S.ema(C, 50)[-1], places=2); self.assertAlmostEqual(e['ema200'], S.ema(C, 200)[-1], places=2)
        self.assertAlmostEqual(e['atr'], S.atr(H, L, C, 14)[-1], places=2); self.assertAlmostEqual(e['atrPct'], S.atr(H, L, C, 14)[-1] / C[-1] * 100, places=2)

    def test_unclosed_bar_never_enters_indicators(self):
        forming = self.book['4h'] + [[ms(2026, 11, 5, 8), 1, 9999, 1, 5000, 1]]          # 08:00 開盤的 4H 尚未收盤(現在 10:40)
        self.book['4h'] = forming
        e = self.by(self.mtf())['4h']
        self.assertEqual(e['quality']['status'], 'forming'); self.assertFalse(e['quality']['blocking']); self.assertTrue(e['data']['formingExcluded'])
        self.assertEqual(e['indicators']['close'], round(forming[-2][4], 2))             # 指標以上一根已收盤的收盤價為準,不是 5000
        self.assertEqual(e['data']['lastBarUtc'], '2026-11-05 04:00')

    def test_stale_timeframe_is_flagged_and_excluded_from_the_summary(self):
        self.book['1h'] = walk(ms(2026, 11, 4, 20), HOUR, 1500, 4)                       # 1H 落後約 13 根
        d = self.mtf(); e = self.by(d)
        self.assertEqual((e['1h']['quality']['status'], e['1h']['quality']['blocking'], e['1h']['usable']), ('stale', True, False))
        self.assertIsNotNone(e['1h']['indicators'])                                       # 仍可看歷史狀態,但標明過期、不列入彙整
        self.assertEqual(d['summary']['usableCount'], 3)

    def test_fetch_failure_in_one_timeframe_does_not_break_the_others(self):
        self.fail = {'1h'}
        e = self.by(self.mtf())
        self.assertEqual(e['1h']['quality']['status'], 'fetch_failed'); self.assertIn('boom 1h', e['1h']['quality']['detail']); self.assertIsNone(e['1h']['indicators'])
        for tf in ('1w', '1d', '4h'): self.assertEqual(e[tf]['quality']['status'], 'ok')

    def test_insufficient_history_has_no_indicators(self):
        self.book['1w'] = self.book['1w'][-30:]
        e = self.by(self.mtf())['1w']
        self.assertEqual(e['quality']['status'], 'insufficient'); self.assertIsNone(e['indicators']); self.assertFalse(e['usable'])

    def test_no_ema200_when_between_60_and_219_bars(self):
        self.book['1w'] = self.book['1w'][-120:]
        e = self.by(self.mtf())['1w']; self.assertEqual(e['quality']['status'], 'ok'); self.assertIsNone(e['indicators']['ema200']); self.assertIn('no_ema200', e['quality']['flags'])

    def test_each_timeframe_is_fetched_exactly_once(self):
        self.mtf(); self.assertEqual(sorted(i for _, i in self.calls), ['1d', '1h', '1w', '4h'])

    def test_timeframes_param_limits_work_and_unknown_are_ignored(self):
        d = self.mtf(tfs='1d,15m,1w'); self.assertEqual([x['tf'] for x in d['timeframes']], ['1w', '1d']); self.assertEqual(sorted(i for _, i in self.calls), ['1d', '1w'])

    def test_summary_agreement_is_descriptive_only(self):
        s = self.mtf()['summary']
        self.assertIn(s['agreement'], ('bull', 'bear', 'mixed')); self.assertNotRegex(s['text'], '預測會|將會上漲|建議買')


class TestTaiwanMtf(Base):
    BOOK = staticmethod(tw_book)
    SYMBOL = '2330.TW'

    def test_4h_is_unsupported_and_never_substituted(self):
        d = self.mtf(); e = self.by(d)
        self.assertFalse(e['4h']['supported']); self.assertIn('不提供', e['4h']['reason']); self.assertIsNone(e['4h']['indicators']); self.assertIsNone(e['4h']['data'])
        self.assertNotIn('4h', [i for _, i in self.calls])                                # 連試都沒試:沒有用 1H 合成,也沒有拿別的週期來頂
        self.assertEqual(sorted(i for _, i in self.calls if _ == '2330.TW'), ['1d', '1h', '1w'])
        for tf in ('1w', '1d', '1h'): self.assertTrue(e[tf]['supported'])

    def test_tw_after_close_is_ok_and_local_time_is_taipei(self):
        e = self.by(self.mtf())
        self.assertEqual(e['1d']['quality']['status'], 'ok'); self.assertEqual(e['1d']['data']['lastBarLocal'], '2026-11-05'); self.assertEqual(e['1d']['data']['tzLabel'], '台北時間 (UTC+8)')
        self.assertEqual(e['1h']['data']['lastBarUtc'], '2026-11-05 05:00'); self.assertEqual(e['1h']['data']['lastBarLocal'], '2026-11-05 13:00')   # 13:00 台北 = 05:00 UTC
        self.assertEqual(e['1h']['quality']['status'], 'ok')

    def test_weekend_does_not_make_tw_data_stale(self):
        self.book['1d'] = trading_day_rows(datetime.date(2026, 11, 6), 700, 'tw', 5)                 # 資料到週五 11/06
        self.book['1h'] = [[ms(2026, 11, 6, 5) - i * HOUR, 100, 101, 99, 100 + (i % 7) * 0.1, 1] for i in range(600, -1, -1)]
        with mock.patch.object(A, '_utcnow', lambda: datetime.datetime(2026, 11, 8, 12)):            # 現在是週日
            d = self.mtf()
        e = self.by(d)
        for tf in ('1w', '1d', '1h'): self.assertEqual((tf, e[tf]['quality']['status'], e[tf]['quality']['blocking']), (tf, 'ok', False))
        self.assertEqual(d['marketState']['code'], 'weekend')


class TestUsMtf(Base):
    SYMBOL = 'AAPL'

    @staticmethod
    def BOOK():
        return {'1w': [[ms(2026, 11, 2) - i * WEEK - WEEK, 100, 101, 99, 100, 1] for i in range(299, -1, -1)],
                '1d': trading_day_rows(datetime.date(2026, 11, 4), 700, 'us', 6),
                '1h': [[ms(2026, 11, 4, 20, 30) - i * HOUR, 100, 101, 99, 100 + (i % 5) * 0.1, 1] for i in range(600, -1, -1)]}     # 15:30 美東 = 20:30 UTC

    def test_us_premarket_thursday_uses_wednesday_close(self):
        e = self.by(self.mtf())
        self.assertEqual(e['1d']['quality']['status'], 'ok'); self.assertEqual(e['1d']['data']['lastBarLocal'], '2026-11-04'); self.assertEqual(e['1d']['data']['tzLabel'], '美東時間')
        self.assertEqual(e['1h']['data']['lastBarLocal'], '2026-11-04 15:30'); self.assertEqual(e['1h']['quality']['status'], 'ok')
        self.assertFalse(e['4h']['supported'])


class TestEventsAndCache(Base):
    def test_events_describe_the_real_work_and_do_not_change_the_result(self):
        plain = self.mtf(); n_plain = len(self.calls); self.calls.clear()
        d = self.client.get('/api/mtf', query_string=dict(symbol=self.SYMBOL, job='job-mtf-0001')).get_json()
        self.assertEqual(d, plain)                                                         # 有無 job,回應完全相同
        self.assertEqual(len(self.calls), n_plain)                                         # 下載次數相同:事件不增加任何下載
        ev = A.JOBS.get('job-mtf-0001')['events']; st = [(e['stage'], e['status']) for e in ev]
        self.assertEqual(st.count(('data', 'progress')), 4); self.assertIn(('data', 'done'), st); self.assertEqual(st.count(('indicators', 'progress')), 4)
        for stage in ('signal', 'backtest', 'validation'): self.assertIn((stage, 'skip'), st)
        self.assertEqual([e['tf'] for e in ev if e['stage'] == 'data' and e['status'] == 'progress'], ['1w', '1d', '4h', '1h'])
        self.assertEqual([e['i'] for e in ev if e['stage'] == 'data' and e['status'] == 'progress'], [1, 2, 3, 4])
        q = [e for e in ev if e['stage'] == 'indicators' and e['status'] == 'progress']; self.assertTrue(all(e['quality'] == 'ok' for e in q))

    def test_cancel_between_timeframes_stops_further_downloads(self):
        gate = threading.Event(); reached = threading.Event(); n = [0]; out = {}; book = self.book
        def slow(symbol, start, interval='1d'):
            n[0] += 1
            if n[0] == 2: reached.set(); gate.wait(10)
            return book.get(interval, [])
        with mock.patch.object(A, 'fetch_data', slow):
            th = threading.Thread(target=lambda: out.setdefault('r', A.app.test_client().get('/api/mtf', query_string=dict(symbol=self.SYMBOL, job='job-mtf-cancel'))))
            th.start(); self.assertTrue(reached.wait(10))
            self.assertEqual(A.JOBS.get('job-mtf-cancel')['status'], 'running')
            self.client.post('/api/job_cancel', query_string=dict(job='job-mtf-cancel'))
            self.assertEqual(A.JOBS.get('job-mtf-cancel')['status'], 'cancelling')
            gate.set(); th.join(10)
        self.assertEqual(out['r'].status_code, 499); self.assertEqual(n[0], 2)             # 第 2 個下載完成後就停,沒有再碰第 3、4 個
        self.assertEqual(A.JOBS.get('job-mtf-cancel')['status'], 'cancelled')


class TestRealFetchPathCacheAndWeekly(unittest.TestCase):
    """走真正的 fetch_data(只把網路層換掉):快取要被如實標示,而且不重複下載;週線走原生週線,不是日線冒充。"""

    def setUp(self):
        A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear(); self.calls = []
        book = crypto_book()
        def fake_ccxt(symbol, interval, days):
            self.calls.append(interval); return [list(r) for r in book[interval]]
        self.ps = [mock.patch.object(A, 'CCXT_AVAILABLE', True), mock.patch.object(A, 'fetch_ccxt_ohlcv', fake_ccxt), mock.patch.object(A, '_utcnow', lambda: NOW)]
        for p in self.ps: p.start()
        self.client = A.app.test_client()

    def tearDown(self):
        for p in reversed(self.ps): p.stop()
        A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear()

    def test_second_call_is_served_from_cache_and_says_so(self):
        d1 = self.client.get('/api/mtf', query_string=dict(symbol='ETH/USDT', job='job-cache-0001')).get_json(); first = list(self.calls)
        self.assertEqual(sorted(first), ['1d', '1h', '1w', '4h'])
        self.assertTrue(all(not e['data']['cached'] for e in d1['timeframes']))
        d2 = self.client.get('/api/mtf', query_string=dict(symbol='ETH/USDT', job='job-cache-0002')).get_json()
        self.assertEqual(self.calls, first)                                                # 沒有任何新的下載
        self.assertTrue(all(e['data']['cached'] is True for e in d2['timeframes'])); self.assertTrue(all(e['data']['ageSec'] >= 0 for e in d2['timeframes']))
        ev = A.JOBS.get('job-cache-0002')['events']
        self.assertTrue(all(e['cached'] is True for e in ev if e['stage'] == 'data' and e['status'] == 'progress'))
        self.assertEqual([e for e in A.JOBS.get('job-cache-0001')['events'] if e['stage'] == 'data' and e['status'] == 'done'][0]['cachedCount'], 0)
        self.assertEqual([e for e in ev if e['stage'] == 'data' and e['status'] == 'done'][0]['cachedCount'], 4)

    def test_weekly_uses_the_native_weekly_interval(self):
        self.client.get('/api/mtf', query_string=dict(symbol='SOL/USDT', tfs='1w'))
        self.assertEqual(self.calls, ['1w'])                                               # 只要週線就只下載週線;沒有用日線合成
        self.assertEqual(A.tf_to_data_interval('1w'), '1d')                                # 既有分析/回測的時框對照沒被改(週線只存在於 /api/mtf)

    def test_analysis_data_events_also_report_cache_use(self):
        with mock.patch.object(A, 'IS_RENDER', False):
            r = self.client.get('/api/analyze', query_string=dict(symbol='XRP/USDT', strategy='supertrend', period='1y', timeframe='4h', job='job-an-cache-1'))
        self.assertEqual(r.status_code, 200)
        e = [x for x in A.JOBS.get('job-an-cache-1')['events'] if x['stage'] == 'data' and x['status'] == 'done'][0]
        self.assertIs(e['cached'], False)
        self.client.get('/api/analyze', query_string=dict(symbol='XRP/USDT', strategy='supertrend', period='1y', timeframe='4h', job='job-an-cache-2'))
        e2 = [x for x in A.JOBS.get('job-an-cache-2')['events'] if x['stage'] == 'data' and x['status'] == 'done'][0]
        self.assertIs(e2['cached'], True)


class TestFetchHelpers(unittest.TestCase):
    def test_resample_report_flags_internal_holes_but_not_the_unfinished_tail(self):
        h = 3600000; base = ms(2026, 11, 1, 0)
        rows = [[base + i * h, 1, 1, 1, 1, 1] for i in range(40)]
        self.assertEqual(A.resample_report(rows, 4 * h)['droppedInternal'], 0)
        self.assertTrue(A.resample_report(rows, 4 * h)['full'] == 10)
        holes = [r for i, r in enumerate(rows) if i not in (9, 13)]                         # 兩個不同區間各少 1 根 → 兩個中間區間不完整
        rep = A.resample_report(holes, 4 * h); self.assertEqual(rep['droppedInternal'], 2)
        tail = A.resample_report(rows[:38], 4 * h); self.assertEqual((tail['droppedInternal'], tail['tailIncomplete']), (0, True))

    def test_weekly_forming_rules(self):
        import pandas as pd
        tz = 'Asia/Taipei'; mon = pd.Timestamp('2026-11-02', tz=tz)
        now = lambda h, m, d: pd.Timestamp(2026, 11, d, h, m, tz=tz).to_pydatetime()
        self.assertTrue(A._is_forming(mon, '2330.TW', '1w', now=now(12, 0, 6)))          # 週五 12:00 → 本週還沒收
        self.assertFalse(A._is_forming(mon, '2330.TW', '1w', now=now(14, 0, 6)))         # 週五 14:00(收盤後)
        self.assertTrue(A._is_forming(mon, 'BTC-USD', '1w', now=now(14, 0, 6)))          # 加密要到週日 24:00
        self.assertFalse(A._is_forming(mon, 'BTC-USD', '1w', now=now(1, 0, 9)))


class TestAnalysisDoesNotShowStaleAsLatest(unittest.TestCase):
    def setUp(self):
        self.rows = walk(ms(2026, 10, 20), DAY, 900, 9)                                    # 日線最後一根 10/20,現在 11/05 → 落後 16 天
        self.ps = [mock.patch.object(A, 'fetch_data', lambda s, st, interval='1d': self.rows), mock.patch.object(A, '_utcnow', lambda: NOW)]
        for p in self.ps: p.start()
        self.client = A.app.test_client()

    def tearDown(self):
        for p in reversed(self.ps): p.stop()

    def test_signal_endpoint_says_stale_instead_of_a_live_signal(self):
        d = self.client.get('/api/signal', query_string=dict(symbol='BTC/USDT', strategy='supertrend', timeframe='1d')).get_json()
        self.assertEqual((d['state'], d['dot']), ('stale', 'expired')); self.assertIn('資料過期', d['label']); self.assertEqual(d['dataQuality']['status'], 'stale')
        self.assertNotIn('買進', d['label'])

    def test_fresh_data_keeps_the_normal_signal_and_adds_quality(self):
        self.rows = walk(ms(2026, 11, 4), DAY, 900, 9)
        d = self.client.get('/api/signal', query_string=dict(symbol='BTC/USDT', strategy='supertrend', timeframe='1d')).get_json()
        self.assertNotEqual(d['state'], 'stale'); self.assertEqual(d['dataQuality']['status'], 'ok')

    def test_analyze_returns_quality_and_leaves_the_backtest_untouched(self):
        d = self.client.get('/api/analyze', query_string=dict(symbol='BTC/USDT', strategy='supertrend', period='1y', timeframe='1d')).get_json()
        self.assertEqual(d['dataQuality']['status'], 'stale'); self.assertTrue(d['dataQuality']['blocking'])
        self.assertGreater(d['metrics']['tradeCount'], 0); self.assertIn('posState', d)       # 回測與持倉狀態照常計算,只是畫面會標示資料過期


if __name__ == '__main__':
    unittest.main()
