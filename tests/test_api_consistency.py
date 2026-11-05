# -*- coding: utf-8 -*-
"""第一/四階段:各 API 使用同一套成本;圖上標記 = 回測交易;排名用的 PF 是扣成本後的。
資料全部用固定種子的合成資料(monkeypatch fetch_data),不連網。"""
import os, sys, math, random, time, datetime, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import sim as S

STEP = {"1d": 86400000, "4h": 4 * 3600000, "1h": 3600000}
SUBSET = ["trend", "supertrend", "donchian", "tsmom", "smc", "ttm", "vortex", "sixline", "bbreak", "cci"]


def synth(n, step_ms, seed):
    rnd = random.Random(seed); px = 100.0; rows = []
    end = int(time.time() * 1000) // step_ms * step_ms - step_ms
    for i in range(n):
        drift = 0.0008 * math.sin(i / 90.0); vol = 0.012 + 0.006 * (1 + math.sin(i / 60.0))
        o = px; c = o * (1 + drift + rnd.gauss(0, vol))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2))); l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        rows.append([end - (n - 1 - i) * step_ms, o, h, l, c, 1000 * (1 + abs(rnd.gauss(0, 1)))]); px = c
    return rows


class TestApiCosts(unittest.TestCase):
    SYMBOLS = [("BTC/USDT", "4h"), ("BTC-USD", "1d"), ("2330.TW", "1d"), ("AAPL", "1d")]

    def setUp(self):
        self.captured = []
        real = S.run_backtest
        def capture(*a, **kw):
            self.captured.append((self._sym, dict(commission=kw.get("commission"), slippage=kw.get("slippage"),
                                                  sell_tax=kw.get("sell_tax"))))
            return real(*a, **kw)
        self._patches = [
            mock.patch.object(A, "run_backtest", capture),
            mock.patch.object(A, "fetch_data", lambda sym, start, interval="1d": synth(1500, STEP[interval], 5)),
            mock.patch.dict(S.STRATS, {k: v for k, v in S.STRATS.items() if k in SUBSET}, clear=True),
            mock.patch.object(A, "IS_RENDER", False),
        ]
        for p in self._patches: p.start()
        self.client = A.app.test_client()

    def tearDown(self):
        for p in reversed(self._patches): p.stop()

    def _call_all(self, sym, tf):
        self._sym = sym
        r1 = self.client.get("/api/analyze", query_string=dict(symbol=sym, strategy="supertrend", period="1y", timeframe=tf))
        r2 = self.client.get("/api/best_strategy", query_string=dict(symbol=sym, period="1y", timeframe=tf))
        r3 = self.client.get("/api/deep_analysis", query_string=dict(symbol=sym, timeframe=tf))
        return r1, r2, r3

    def test_every_api_uses_the_same_cost_for_the_same_symbol(self):
        for sym, tf in self.SYMBOLS:
            self.captured.clear()
            r1, r2, r3 = self._call_all(sym, tf)
            self.assertEqual(r1.status_code, 200, (sym, r1.get_json()))
            self.assertEqual(r2.status_code, 200, (sym, r2.get_json()))
            self.assertEqual(r3.status_code, 200, (sym, r3.get_json()))
            expected = S.cost_kwargs(sym)
            self.assertTrue(self.captured, sym)
            for s, kw in self.captured:
                self.assertEqual(kw, expected, "%s 的某個 API 用了不一致的成本" % sym)

    def test_crypto_not_charged_as_us_stock_in_any_api(self):
        for sym, tf in (("BTC/USDT", "4h"), ("BTC-USD", "1d")):
            self.captured.clear(); self._call_all(sym, tf)
            for _, kw in self.captured:
                self.assertAlmostEqual(kw["commission"] + kw["slippage"], 0.0007)

    def test_tw_sell_tax_reaches_every_api(self):
        self.captured.clear(); self._call_all("2330.TW", "1d")
        self.assertTrue(all(abs(kw["sell_tax"] - 0.003) < 1e-12 for _, kw in self.captured))
        self.captured.clear(); self._call_all("AAPL", "1d")
        self.assertTrue(all(kw["sell_tax"] == 0.0 for _, kw in self.captured))


class TestMarkersAndNetPf(unittest.TestCase):
    def setUp(self):
        self.rows = synth(1500, STEP["4h"], 9)
        self.O = [r[1] for r in self.rows]; self.H = [r[2] for r in self.rows]
        self.L = [r[3] for r in self.rows]; self.C = [r[4] for r in self.rows]; self.V = [r[5] for r in self.rows]

    def test_chart_markers_equal_backtest_trades(self):
        for strat in ("supertrend", "trend", "donchian", "smc", "rolltrend", "wbottom"):
            if strat not in S.STRATS: continue
            s = S.STRATS[strat]
            el, xl = s["build"](self.O, self.H, self.L, self.C, self.V, "4h")
            buy, sell = A.get_real_trades(self.rows, el, xl, strat_info=s)
            _, _, st = S.run_backtest(self.rows, strategy=strat, timeframe="4h", **S.cost_kwargs("BTC/USDT"))
            tl = st["trade_log"]
            self.assertEqual({i for i, b in enumerate(buy) if b}, {t["entry_i"] for t in tl}, strat)
            self.assertEqual({i for i, b in enumerate(sell) if b}, {t["exit_i"] for t in tl if t.get("exit_i") is not None}, strat)

    def test_pf_used_for_ranking_is_net_of_costs(self):
        _, _, st = S.run_backtest(self.rows, strategy="trend", timeframe="4h", **S.cost_kwargs("BTC/USDT"))
        tl = [t for t in st["trade_log"] if not t.get("open")]
        self.assertGreater(len(tl), 10)
        net = A.calc_pf(tl)
        gross = A.calc_pf([{"ret": t["ret_gross"]} for t in tl])
        self.assertLess(net, gross, "扣完手續費+滑價後 PF 必須比毛報酬 PF 低")
        for t in tl:
            self.assertLess(t["ret"], t["ret_gross"])
        # 成本越高,PF 越低(單調)
        _, _, st2 = S.run_backtest(self.rows, strategy="trend", timeframe="4h", commission=0.003, slippage=0.001)
        net2 = A.calc_pf([t for t in st2["trade_log"] if not t.get("open")])
        self.assertLess(net2, net)

    def test_strategy_declared_warmup_is_enforced(self):
        # tsmom_12m / dual_mom 宣告需要 2380 根;只有 1500 根時要回報資料不足,不能拿沒暖機完的指標硬跑
        self.assertEqual(S.STRATS["tsmom_12m"]["min_bars"], 2380)
        self.assertIsNone(S.run_backtest(self.rows, strategy="tsmom_12m", timeframe="4h"))
        self.assertIsNotNone(S.run_backtest(self.rows, strategy="trend", timeframe="4h"))
        long_rows = synth(2600, STEP["4h"], 4)
        self.assertIsNotNone(S.run_backtest(long_rows, strategy="tsmom_12m", timeframe="4h"))

    def test_cost_paid_is_reported(self):
        _, _, st = S.run_backtest(self.rows, strategy="trend", timeframe="4h", **S.cost_kwargs("BTC/USDT"))
        self.assertGreater(st["cost_paid"], 0)
        self.assertEqual(st["cost_model"]["commission"], 0.0005)
        _, _, st0 = S.run_backtest(self.rows, strategy="trend", timeframe="4h", commission=0.0, slippage=0.0)
        self.assertEqual(st0["cost_paid"], 0.0)
        self.assertGreater(st0["total"], st["total"])


class TestDeepAnalysisIsMarketAware(unittest.TestCase):
    def test_us_tickers_with_crypto_letters_use_stock_strategy_set(self):
        # GBTC/ETHE 是美股信託,以前因為代碼含 BTC/ETH 被當成加密貨幣(用加密策略集、加密最低筆數、加密成本)
        self.assertFalse(A.is_crypto_symbol("GBTC"))
        self.assertFalse(A.is_crypto_symbol("ETHE"))
        self.assertTrue(A.is_crypto_symbol("PAXG-USD"))
        self.assertTrue(A.is_crypto_symbol("1000PEPE/USDT"))


if __name__ == "__main__":
    unittest.main()
