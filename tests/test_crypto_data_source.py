# -*- coding: utf-8 -*-
"""加密貨幣行情來源:只走幣安 USDT-M 永續;失敗/不足要明確回報,不能靜默退回 yfinance 現貨、不能偷偷由 1H 合成 4H;來源標籤要反映實際來源。
股票(台股、美股)的 yfinance 流程保持不變。全部用假資料來源,不連網。
注意:這些測試證明的是『程式在失敗時的行為』,不是『行情是真實的』——行情真偽靠 docs/data_audit_20261106 的官方 API 比對。"""
import os, sys, unittest, warnings, random, time, datetime
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import app as A

H1 = 3600000; H4 = 4 * H1; D1 = 24 * H1
STEP = {'1h': H1, '4h': H4, '1d': D1}


def closed_rows(tf, n, skip=(), seed=7):
    """n 根已收盤的假 K 棒(隨機漫步,固定種子),最後一根在現在之前已收盤。"""
    step = STEP[tf]; last = (int(time.time() * 1000) // step) * step - step; rnd = random.Random(seed); px = 100.0; out = []
    for i in range(n):
        t = last - (n - 1 - i) * step; o = px; c = o * (1 + rnd.uniform(-0.01, 0.0115)); h = max(o, c) * (1 + rnd.uniform(0, 0.004)); l = min(o, c) * (1 - rnd.uniform(0, 0.004)); px = c
        if i in skip: continue
        out.append([t, o, h, l, c, 10 + rnd.random()])
    return out


class YahooForbidden:
    """crypto 路徑只要碰到 yfinance 就失敗。"""
    def __init__(self, *a, **k): raise AssertionError("yfinance 不可被加密貨幣路徑呼叫")


class Base(unittest.TestCase):
    def setUp(self):
        import yfinance
        A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear(); self._flag = A.CCXT_AVAILABLE
        self.yf_calls = []
        self._yf = yfinance.Ticker; yfinance.Ticker = YahooForbidden
        self._resample = A.resample_ohlcv
        A.resample_ohlcv = lambda *a, **k: (_ for _ in ()).throw(AssertionError("加密貨幣不可由 1H 合成 4H"))
        self.addCleanup(self._restore)

    def _restore(self):
        import yfinance
        yfinance.Ticker = self._yf; A.resample_ohlcv = self._resample; A.CCXT_AVAILABLE = self._flag
        A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear()

    def fetch_ccxt(self, rows=None, error=None):
        def fake(sym, interval, days):
            if error is not None: A._tl.ccxt_error = error; return None
            return rows
        p = mock.patch.object(A, 'fetch_ccxt_ohlcv', fake); p.start(); self.addCleanup(p.stop)


class TestNormal(Base):
    def test_good_data_passes_through_unchanged_and_is_labelled_binance(self):
        A.CCXT_AVAILABLE = True
        for sym, tf in (("BTC/USDT", "4h"), ("SOL-USD", "1h"), ("1000PEPE/USDT", "4h"), ("PAXG-USD", "1d")):
            A._cache.clear(); rows = closed_rows(tf, 300); self.fetch_ccxt(rows=rows)
            out = A.fetch_data(sym, "2026-01-01", tf)
            self.assertIs(out, rows, "正常資料不可被改動")
            m = A.fetch_meta(sym, "2026-01-01", tf)
            self.assertEqual((m['source'], m['venue'], m['missingBars']), ('ccxt', 'binance_usdm_perp', 0), (sym, tf))

    def test_analyze_result_identical_to_backtest_on_the_same_bars(self):
        rows = closed_rows("4h", 700); self.fetch_ccxt(rows=rows); A.CCXT_AVAILABLE = True
        js = A.app.test_client().get('/api/analyze?symbol=BTC%2FUSDT&strategy=trend&period=6mo&timeframe=4h').get_json()
        self.assertNotIn('error', js, js.get('error'))
        direct = A.run_backtest(rows, strategy='trend', risk_pct=0.015, timeframe='4h', **A.cost_kwargs('BTC/USDT', 'trend'))
        self.assertIsNotNone(direct)
        self.assertEqual(js['dataInfo']['source'], 'ccxt'); self.assertEqual(js['dataInfo']['venue'], 'binance_usdm_perp'); self.assertEqual(js['dataInfo']['interval'], '4h')
        self.assertEqual(js['dataQuality']['source'], 'ccxt'); self.assertEqual(js['dataQuality']['missingBars'], 0)


class TestFailureIsExplicit(Base):
    def test_ccxt_failure_raises_and_never_touches_yahoo_or_resample(self):
        A.CCXT_AVAILABLE = True
        for tf in ("1h", "4h", "1d", "1w"):
            self.fetch_ccxt(error="NetworkError: timed out")
            with self.assertRaises(A.DataSourceError) as cm: A.fetch_data("BTC/USDT", "2026-01-01", tf)
            msg = str(cm.exception)
            self.assertIn("NetworkError: timed out", msg); self.assertIn("不會改用 yfinance", msg); self.assertIn("BTC/USDT", msg)
            self.assertFalse(A._cache, "失敗不可被快取成功"); self.assertEqual(A.fetch_meta("BTC/USDT", "2026-01-01", tf), {})

    def test_real_fetch_function_failure_is_reported_with_reason(self):
        import ccxt
        class Boom:
            def __init__(self, *a, **k): pass
            def milliseconds(self): return int(time.time() * 1000)
            def fetch_ohlcv(self, *a, **k): raise ccxt.NetworkError("binance down")
        orig = ccxt.binanceusdm; ccxt.binanceusdm = Boom; A.CCXT_AVAILABLE = True
        try:
            with self.assertRaises(A.DataSourceError) as cm: A.fetch_data("ETH-USD", "2026-01-01", "4h")
        finally: ccxt.binanceusdm = orig
        self.assertIn("binance down", str(cm.exception))

    def test_flag_off_crypto_is_an_error_not_a_yahoo_fallback(self):
        A.CCXT_AVAILABLE = False
        for sym in ("BTC/USDT", "BTC-USD", "SOL-USD"):
            for tf in ("1h", "4h", "1d"):
                with self.assertRaises(A.DataSourceError, msg=(sym, tf)) as cm: A.fetch_data(sym, "2026-01-01", tf)
                self.assertIn("不會改用 yfinance", str(cm.exception))

    def test_empty_result_is_an_error(self):
        A.CCXT_AVAILABLE = True; self.fetch_ccxt(rows=[])
        with self.assertRaises(A.DataSourceError) as cm: A.fetch_data("NOPE/USDT", "2026-01-01", "4h")
        self.assertIn("沒有回傳任何", str(cm.exception))

    def test_short_history_is_returned_as_is_and_reported_as_insufficient(self):
        A.CCXT_AVAILABLE = True; rows = closed_rows("4h", 60); self.fetch_ccxt(rows=rows)
        self.assertIs(A.fetch_data("NEW/USDT", "2026-01-01", "4h"), rows)                       # 不退回 yfinance、不補資料
        js = A.app.test_client().get('/api/analyze?symbol=NEW%2FUSDT&strategy=trend&period=6mo&timeframe=4h')
        self.assertEqual(js.status_code, 400); self.assertIn("資料不足", js.get_json()['error'])

    def test_endpoints_report_502_with_error_code(self):
        A.CCXT_AVAILABLE = True; self.fetch_ccxt(error="ExchangeNotAvailable: 503")
        c = A.app.test_client()
        for url in ('/api/analyze?symbol=BTC%2FUSDT&strategy=trend&period=6mo&timeframe=4h', '/api/best_strategy?symbol=BTC%2FUSDT&period=6mo&timeframe=4h&use_oos=1',
                    '/api/deep_analysis?symbol=BTC%2FUSDT&timeframe=4h&use_oos=1', '/api/regime_study?symbol=BTC%2FUSDT&timeframe=4h&strategy=trend&period=2y&basis=own'):
            r = c.get(url); js = r.get_json()
            self.assertEqual(r.status_code, 502, url); self.assertEqual(js['errorCode'], 'crypto_data_unavailable', url); self.assertIn('ExchangeNotAvailable', js['error'])
            self.assertNotIn('detail', js)

    def test_mtf_reports_fetch_failed_not_substitute_data(self):
        A.CCXT_AVAILABLE = True; self.fetch_ccxt(error="NetworkError: down")
        js = A.app.test_client().get('/api/mtf?symbol=BTC%2FUSDT&tfs=4h,1h').get_json()
        for e in js['timeframes']:
            self.assertEqual(e['quality']['status'], 'fetch_failed', e['tf']); self.assertFalse(e['usable']); self.assertIn('NetworkError', e['quality']['detail'])
            self.assertIsNone(e['data']['source'])

    def test_config_label_does_not_claim_yahoo_for_crypto(self):
        A.CCXT_AVAILABLE = False; d = A.app.test_client().get('/api/config').get_json()
        self.assertFalse(d['ccxtAvailable']); self.assertIn('無法使用', d['dataSource']); self.assertIn('不會改用 yfinance', d['dataSource'])
        A.CCXT_AVAILABLE = True; d = A.app.test_client().get('/api/config').get_json(); self.assertIn('幣安', d['dataSource'])


class TestMissingBars(Base):
    def test_gap_is_never_filled_and_is_reported(self):
        A.CCXT_AVAILABLE = True; rows = closed_rows("4h", 300, skip={100, 101, 200}); n = len(rows); self.assertEqual(n, 297); self.fetch_ccxt(rows=rows)
        out = A.fetch_data("BTC/USDT", "2026-01-01", "4h")
        self.assertEqual(len(out), 297, "缺棒不可補造")
        self.assertEqual({out[i + 1][0] - out[i][0] for i in range(len(out) - 1)}, {H4, 2 * H4, 3 * H4})
        self.assertEqual(A.fetch_meta("BTC/USDT", "2026-01-01", "4h")['missingBars'], 3)
        q = A.quality_for_series("BTC/USDT", "4h", out, A.fetch_meta("BTC/USDT", "2026-01-01", "4h")); self.assertEqual(q['missingBars'], 3)

    def test_count_missing_bars(self):
        self.assertEqual(A.count_missing_bars(closed_rows("1h", 50), "1h"), 0)
        self.assertEqual(A.count_missing_bars(closed_rows("1h", 50, skip={10, 11, 30}), "1h"), 3)
        self.assertEqual(A.count_missing_bars([], "1h"), 0)


class TestSourceLabel(Base):
    def test_label_comes_from_actual_fetch_not_from_flags(self):
        rows = closed_rows("4h", 300); A.CCXT_AVAILABLE = True                                # 旗標說 ccxt,但這份資料實際來自 yfinance → 標籤必須是 yfinance
        self.assertEqual(A.build_data_info("BTC/USDT", "4h", rows, {'source': 'yfinance'})['source'], 'yfinance')
        self.assertEqual(A.build_data_info("BTC/USDT", "4h", rows, {'source': 'ccxt', 'venue': 'binance_usdm_perp'})['venue'], 'binance_usdm_perp')
        self.assertEqual(A.build_data_info("AAPL", "4h", rows, {'source': 'yfinance(1h→4h 合成)'})['source'], 'yfinance(1h→4h 合成)')
        self.assertEqual(A.build_data_info("BTC/USDT", "4h", rows)['source'], 'unknown', "沒有取得紀錄就不能猜")
        A.CCXT_AVAILABLE = False
        self.assertEqual(A.build_data_info("BTC/USDT", "4h", rows, {'source': 'ccxt'})['source'], 'ccxt')

    def test_job_start_event_does_not_claim_a_source_before_fetching(self):
        import inspect
        src = inspect.getsource(A)
        self.assertNotIn("source='ccxt' if uses_ccxt(symbol) else 'yfinance'", src); self.assertNotIn("'source': 'ccxt' if uses_ccxt(symbol) else 'yfinance'", src)


class TestStocksUnchanged(unittest.TestCase):
    """股票仍走 yfinance,不受加密貨幣新規則影響(旗標開或關都一樣);完全不碰 ccxt。"""
    def setUp(self):
        A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear(); self._flag = A.CCXT_AVAILABLE
        import yfinance
        self._yf = yfinance.Ticker; self._cc = A.fetch_ccxt_ohlcv
        A.fetch_ccxt_ohlcv = lambda *a, **k: (_ for _ in ()).throw(AssertionError("股票不可呼叫 ccxt"))
        self.addCleanup(self._restore)

    def _restore(self):
        import yfinance
        yfinance.Ticker = self._yf; A.fetch_ccxt_ohlcv = self._cc; A.CCXT_AVAILABLE = self._flag; A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear()

    def _fake(self, df):
        import yfinance
        class T:
            def __init__(s, sym): pass
            def history(s, **kw): return df
        yfinance.Ticker = T

    def test_stock_daily_and_synth_4h_still_work_with_flag_on_and_off(self):
        import app as A_; start = int(datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc).timestamp() * 1000)
        idx = pd.DatetimeIndex([pd.Timestamp(start + i * H1, unit="ms", tz="UTC") for i in range(24 * 12)])
        df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1.0}, index=idx); self._fake(df)
        orig = A._is_forming; A._is_forming = lambda *a, **k: False
        try:
            for flag in (True, False):
                A.CCXT_AVAILABLE = flag; A._cache.clear(); A._fetch_meta.clear()
                out = A.fetch_data("AAPL", "2026-01-01", "4h")
                self.assertTrue(len(out) > 40); self.assertEqual({out[i + 1][0] - out[i][0] for i in range(len(out) - 1)}, {H4})
                self.assertEqual(A.fetch_meta("AAPL", "2026-01-01", "4h")['source'], 'yfinance(1h→4h 合成)', "股票的合成 4H 仍如實標示")
                A._cache.clear(); A._fetch_meta.clear()
                self.assertTrue(A.fetch_data("2330.TW", "2026-01-01", "1h"))
                self.assertEqual(A.fetch_meta("2330.TW", "2026-01-01", "1h")['source'], 'yfinance')
        finally: A._is_forming = orig


if __name__ == "__main__":
    unittest.main()
