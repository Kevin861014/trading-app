# -*- coding: utf-8 -*-
"""第三階段:時間週期、時區與資料一致性。用假的資料來源(monkeypatch),不連網。"""
import os, sys, datetime, unittest, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import app as A

H1 = 3600000; H4 = 4 * H1; D1 = 24 * H1


def utc_ms(y, m, d, hh=0):
    return int(datetime.datetime(y, m, d, hh, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def hourly(start_ms, n, skip=()):
    rows = []
    for i in range(n):
        if i in skip: continue
        rows.append([start_ms + i * H1, 100 + i, 101 + i, 99 + i, 100.5 + i, 10.0])
    return rows


class TestResample(unittest.TestCase):
    def test_only_complete_aligned_buckets(self):
        start = utc_ms(2026, 1, 1)
        rows = hourly(start, 26, skip={5})          # 00:00~01:00(+1d);第 5 小時缺 → 04-08 那桶不完整;最後一桶只有 2 根
        out = A.resample_ohlcv(rows, H4)
        starts_h = [(r[0] - start) // H1 for r in out]
        self.assertEqual(starts_h, [0, 8, 12, 16, 20])
        for r in out: self.assertEqual(r[0] % H4, 0, "必須對齊 UTC 0/4/8/12/16/20 點(跟幣安 4H 一致)")
        b0 = out[0]
        self.assertEqual(b0[1], 100)                  # open = 第一根的 open
        self.assertEqual(b0[2], 104)                  # high = 4 根中最高
        self.assertEqual(b0[3], 99)                   # low  = 4 根中最低
        self.assertEqual(b0[4], 103.5)                # close = 最後一根的 close
        self.assertEqual(b0[5], 40.0)                 # volume 加總

    def test_does_not_fill_gaps(self):
        start = utc_ms(2026, 1, 1)
        rows = hourly(start, 8) + hourly(start + 3 * D1, 8)     # 中間整整缺 3 天(假日/週末)
        out = A.resample_ohlcv(rows, H4)
        self.assertEqual(len(out), 4)                  # 只有真的存在且填滿的區間,不會補出假 K 棒


class FakeEx:
    NOW = utc_ms(2026, 6, 10, 10) + 30 * 60 * 1000     # 2026-06-10 10:30 UTC

    def __init__(self, *a, **k): pass
    def milliseconds(self): return self.NOW
    def fetch_ohlcv(self, sym, tf, since=None, limit=1000):
        step = {"1h": H1, "4h": H4, "1d": D1}[tf]
        last_start = (self.NOW // step) * step          # 目前還在走的那一根的開始時間
        n = 300
        return [[last_start - (n - 1 - i) * step, 100 + i, 101 + i, 99 + i, 100 + i, 5.0] for i in range(n)]


class TestIntervals(unittest.TestCase):
    def setUp(self):
        A._cache.clear(); A._cache_time.clear()
        self._ccxt_flag = A.CCXT_AVAILABLE

    def tearDown(self):
        A.CCXT_AVAILABLE = self._ccxt_flag

    def test_4h_requests_real_4h_not_1h(self):
        calls = []
        orig = A.fetch_ccxt_ohlcv
        A.fetch_ccxt_ohlcv = lambda sym, interval, days: (calls.append(interval) or
                                                          [[i * H4, 1, 2, 0.5, 1.5, 1.0] for i in range(300)])
        A.CCXT_AVAILABLE = True
        try:
            out = A.fetch_data("BTC/USDT", "2024-01-01", "4h")
        finally:
            A.fetch_ccxt_ohlcv = orig
        self.assertEqual(calls, ["4h"])
        self.assertEqual(out[1][0] - out[0][0], H4)
        self.assertEqual(A.tf_to_data_interval("4h"), "4h")
        self.assertEqual(A.tf_to_data_interval("1h"), "1h")
        self.assertEqual(A.tf_to_data_interval("1d"), "1d")

    def test_ccxt_drops_forming_bar_for_all_intraday_and_daily(self):
        import ccxt
        orig = ccxt.binanceusdm; ccxt.binanceusdm = FakeEx
        try:
            for tf, step in (("1h", H1), ("4h", H4), ("1d", D1)):
                out = A.fetch_ccxt_ohlcv("BTC/USDT", tf, 100)
                self.assertTrue(out, tf)
                self.assertLessEqual(out[-1][0] + step, FakeEx.NOW, "%s 最後一根必須已收盤" % tf)
        finally:
            ccxt.binanceusdm = orig

    def test_yfinance_path_builds_true_4h_from_1h_for_stocks(self):
        import yfinance
        start = utc_ms(2026, 1, 1)
        idx = pd.DatetimeIndex([pd.Timestamp(r[0], unit="ms", tz="UTC") for r in hourly(start, 24 * 12 + 2)])
        df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1.0}, index=idx)
        class FakeTicker:
            def __init__(self, s): pass
            def history(self, **kw): return df
        orig = yfinance.Ticker; yfinance.Ticker = FakeTicker
        A.CCXT_AVAILABLE = False
        try:
            out = A.fetch_data("AAPL", "2026-01-01", "4h")          # 股票仍走 yfinance(加密貨幣不再走這條路,見 test_crypto_data_source.py)
        finally:
            yfinance.Ticker = orig
        self.assertTrue(len(out) > 50)
        self.assertEqual({out[i + 1][0] - out[i][0] for i in range(len(out) - 1)}, {H4})
        self.assertTrue(all(r[0] % H4 == 0 for r in out))


class TestDailyBars(unittest.TestCase):
    def setUp(self):
        A._cache.clear(); A._cache_time.clear()

    def _fake(self, df):
        import yfinance
        class FakeTicker:
            def __init__(self, s): pass
            def history(self, **kw): return df
        self._orig = yfinance.Ticker; yfinance.Ticker = FakeTicker
        self.addCleanup(lambda: setattr(yfinance, "Ticker", self._orig))

    def test_taiwan_daily_label_is_exchange_local_date_and_weekend_not_filled(self):
        days = [d for d in pd.date_range("2026-10-26", "2026-11-06", tz="Asia/Taipei") if d.weekday() < 5]   # 週一到週五
        df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1.0}, index=pd.DatetimeIndex(days))
        self._fake(df)
        orig = A._is_forming; A._is_forming = lambda *a, **k: False
        try:
            out = A.fetch_data("2330.TW", "2020-01-01", "1d")
        finally:
            A._is_forming = orig
        self.assertEqual(len(out), len(days), "週末/假日不能被補成 K 棒")
        for d, r in zip(days, out):
            got = datetime.datetime.utcfromtimestamp(r[0] / 1000).date()
            self.assertEqual(got, d.date(), "台股 %s 的 K 棒日期標籤不能差一天(以前 UTC+8 午夜會被標成前一天)" % d.date())

    def test_forming_daily_bar_is_dropped(self):
        days = list(pd.date_range("2026-10-26", periods=5, tz="Asia/Taipei"))
        df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1.0}, index=pd.DatetimeIndex(days))
        self._fake(df)
        orig = A._is_forming; A._is_forming = lambda *a, **k: True
        try:
            out = A.fetch_data("2330.TW", "2021-01-01", "1d")
        finally:
            A._is_forming = orig
        self.assertEqual(len(out), 4)

    def test_is_forming_rules(self):
        tw = lambda s: pd.Timestamp(s, tz="Asia/Taipei")
        ny = lambda s: pd.Timestamp(s, tz="America/New_York")
        utc = lambda s: pd.Timestamp(s, tz="UTC")
        self.assertTrue(A._is_forming(tw("2026-11-05"), "2330.TW", "1d", now=tw("2026-11-05 11:00")))      # 盤中
        self.assertFalse(A._is_forming(tw("2026-11-05"), "2330.TW", "1d", now=tw("2026-11-05 14:00")))     # 已收盤
        self.assertFalse(A._is_forming(tw("2026-11-04"), "2330.TW", "1d", now=tw("2026-11-05 11:00")))     # 昨天
        self.assertTrue(A._is_forming(ny("2026-11-04"), "AAPL", "1d", now=ny("2026-11-04 15:00")))
        self.assertFalse(A._is_forming(ny("2026-11-04"), "AAPL", "1d", now=ny("2026-11-04 16:30")))
        self.assertTrue(A._is_forming(utc("2026-11-05"), "BTC-USD", "1d", now=utc("2026-11-05 23:59")))    # 加密貨幣整天都還沒收
        self.assertTrue(A._is_forming(utc("2026-11-05 10:00"), "BTC-USD", "1h", now=utc("2026-11-05 10:30")))
        self.assertFalse(A._is_forming(utc("2026-11-05 10:00"), "BTC-USD", "1h", now=utc("2026-11-05 11:00")))


class TestTimeAndData(unittest.TestCase):
    def test_utcnow_is_naive_utc(self):
        d = A._utcnow(); self.assertIsNone(d.tzinfo)
        self.assertLess(abs((d - datetime.datetime.utcnow()).total_seconds()), 5)

    def test_insufficient_history_is_reported_not_faked(self):
        c = A.app.test_client()
        orig = A.fetch_data
        try:
            for n, needle in ((50, "資料不足"), (150, "資料不足")):
                A.fetch_data = lambda *a, n=n, **k: [[i * D1, 100, 101, 99, 100, 1.0] for i in range(n)]
                r = c.get("/api/analyze", query_string=dict(symbol="AAPL", strategy="trend", period="1y", timeframe="1d"))
                self.assertEqual(r.status_code, 400, n)
                self.assertIn(needle, r.get_json()["error"])
        finally:
            A.fetch_data = orig

    def test_market_character_uses_the_requested_timeframe_data(self):
        seen = []
        orig = A.fetch_data
        A.fetch_data = lambda sym, start, interval="1d": (seen.append(interval) or [])
        try:
            A.app.test_client().get("/api/market_character", query_string=dict(symbol="BTC/USDT", timeframe="4h"))
            A.app.test_client().get("/api/market_character", query_string=dict(symbol="BTC/USDT", timeframe="1h"))
        finally:
            A.fetch_data = orig
        self.assertEqual(seen, ["4h", "1h"])


if __name__ == "__main__":
    unittest.main()
