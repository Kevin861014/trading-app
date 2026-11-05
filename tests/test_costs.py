# -*- coding: utf-8 -*-
"""第一階段:交易成本與市場分類。不連網、不依賴歷史資料。
執行:  python -m unittest discover -s tests -t .   (在 trading-app 資料夾)"""
import os, sys, unittest, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim as S


class TestClassify(unittest.TestCase):
    def test_crypto_symbol_forms(self):
        for s in ["BTC/USDT", "SOL/USDT", "1000PEPE/USDT", "BTC-USD", "PAXG-USD", "BTCUSDT",
                  "AVGO/USDT:USDT", "SOL", "BTC"]:
            self.assertEqual(S.classify_market(s), "crypto", s)

    def test_data_source_does_not_change_asset_class(self):
        # 同一個 BTC,不管資料來源標成 yf 還是 ccxt,資產類別一樣
        for spec in [("yf", "BTC/USDT"), ("yf", "BTC-USD"), ("ccxt", "binanceusdm", "BTC/USDT"), "BTC/USDT", "BTC-USD"]:
            self.assertEqual(S.classify_market(spec), "crypto", spec)
        self.assertEqual(S.classify_market(("yf", "AAPL")), "us")
        self.assertEqual(S.classify_market(("yf", "2330.TW")), "tw")

    def test_tw_and_us(self):
        self.assertEqual(S.classify_market("2330.TW"), "tw")
        self.assertEqual(S.classify_market("0050.TW"), "tw")
        self.assertEqual(S.classify_market("6488.TWO"), "tw")
        for s in ["AAPL", "NVDA", "TSLA", "MSFT"]:
            self.assertEqual(S.classify_market(s), "us", s)

    def test_us_tickers_that_contain_crypto_letters_are_not_crypto(self):
        # 以前用子字串比對,這些美股會被誤判成加密貨幣
        for s in ["GBTC", "ETHE", "BTCS", "SOLV", "DOTS", "ADAP"]:
            self.assertEqual(S.classify_market(s), "us", s)

    def test_commodity_and_metal_etf(self):
        for s in ["GC=F", "SI=F", "CL=F"]:
            self.assertEqual(S.classify_market(s), "commodity", s)
        for s in ["GLD", "SLV"]:
            self.assertEqual(S.classify_market(s), "metal_etf", s)


class TestCostModel(unittest.TestCase):
    def test_crypto_default_is_taker_005_plus_slip_002(self):
        for sym in ["BTC/USDT", "BTC-USD", ("yf", "BTC-USD"), ("ccxt", "binanceusdm", "SOL/USDT")]:
            k = S.cost_kwargs(sym)
            self.assertAlmostEqual(k["commission"], 0.0005)
            self.assertAlmostEqual(k["slippage"], 0.0002)
            self.assertEqual(k["sell_tax"], 0.0)
            # 來回約 0.14%
            self.assertAlmostEqual(2 * (k["commission"] + k["slippage"]), 0.0014)

    def test_tw_has_sell_only_tax_and_etf_is_lower(self):
        stock = S.cost_kwargs("2330.TW"); etf = S.cost_kwargs("0050.TW")
        self.assertAlmostEqual(stock["sell_tax"], 0.003)
        self.assertAlmostEqual(etf["sell_tax"], 0.001)
        self.assertAlmostEqual(stock["commission"], S.TW_COMMISSION)
        self.assertEqual(stock["slippage"], 0.0)

    def test_us_keeps_its_own_rule(self):
        for sym in ["AAPL", "NVDA"]:
            k = S.cost_kwargs(sym)
            self.assertAlmostEqual(k["commission"], 0.00015)
            self.assertAlmostEqual(k["slippage"], 0.00005)
            self.assertEqual(k["sell_tax"], 0.0)

    def test_same_cost_regardless_of_source_label(self):
        self.assertEqual(S.cost_kwargs(("yf", "BTC-USD")), S.cost_kwargs("BTC/USDT"))
        self.assertEqual(S.cost_kwargs(("ccxt", "binanceusdm", "BTC/USDT")), S.cost_kwargs("BTC-USD"))

    def test_no_maker_assumption_from_strategy_name(self):
        # 模擬器是「下一根開盤價成交」,沒有模擬限價單是否成交,不能只因策略名稱就假定 maker
        for strat in ["rsi2dip", "ibsdip", "zdip"]:
            self.assertEqual(S.cost_kwargs("BTC/USDT", strat), S.cost_kwargs("BTC/USDT", "trend"))
            self.assertEqual(S.cost_kwargs("2330.TW", strat), S.cost_kwargs("2330.TW", "trend"))

    def test_legacy_market_cost_wrapper_classifies_by_symbol(self):
        # 舊介面:即使傳 ('yf', 'BTC/USDT') 也不能再當美股
        c, s = S.market_cost(("yf", "BTC/USDT"), "trend")
        self.assertAlmostEqual(c + s, 0.0007)


def _flat_with_one_trade(entry, exit_, **kw):
    """合成資料:bar0 訊號、bar1 開盤進場、bar2 開盤出場(訊號出場),價格固定方便手算。"""
    T = [i * 86400000 for i in range(4)]
    O = [entry, entry, exit_, exit_]; H = list(O); L = list(O); C = list(O)
    el = [True, False, False, False]; xl = [False, True, False, False]
    A = [1.0] * 4
    return S._simulate(T, O, H, L, C, el, xl, A, 0.0, 0.0, 0.0, 0.0, 1.0, 10000.0, **kw)


class TestDirectionalCosts(unittest.TestCase):
    def test_tw_sell_tax_only_on_sell(self):
        com = S.TW_COMMISSION; tax = 0.003
        _, eq, trades, log = _flat_with_one_trade(100.0, 110.0, commission=com, slippage=0.0, sell_tax=tax)
        qty = 10000.0 / 100.0                      # risk_pct=0 → 全額,max_lev=1
        expected = qty * 10.0 - qty * 100.0 * com - qty * 110.0 * (com + tax)
        self.assertAlmostEqual(trades[0], expected, places=6)
        # 買進方向不收稅:若稅也收在買進,數字會不同
        wrong = qty * 10.0 - qty * 100.0 * (com + tax) - qty * 110.0 * (com + tax)
        self.assertNotAlmostEqual(trades[0], wrong, places=3)
        self.assertAlmostEqual(log[0]["cost"], qty * 100.0 * com + qty * 110.0 * (com + tax), places=6)

    def test_net_return_equals_gross_minus_costs(self):
        com, slp = 0.0005, 0.0002
        _, _, _, log = _flat_with_one_trade(100.0, 110.0, commission=com, slippage=slp)
        t = log[0]
        self.assertAlmostEqual(t["ret_gross"], 10.0, places=2)
        expected_net = (10.0 - 100.0 * (com + slp) - 110.0 * (com + slp)) / 100.0 * 100
        self.assertAlmostEqual(t["ret"], round(expected_net, 2), places=2)
        self.assertLess(t["ret"], t["ret_gross"])

    def test_round_trip_cost_before_after(self):
        """修復前後成本比較(來回,以名目為 100% 計)。"""
        old = {"BTC/USDT(以前被當美股)": 2 * (0.00015 + 0.00005),
               "2330.TW(以前平均值)": 2 * 0.00225}
        new_btc = 2 * (S.CRYPTO_COMMISSION + S.CRYPTO_SLIPPAGE)
        k = S.cost_kwargs("2330.TW")
        new_tw = 2 * (k["commission"] + k["slippage"]) + k["sell_tax"]
        print("\n成本比較(來回)  BTC/USDT: %.3f%% -> %.3f%%   2330.TW: %.3f%% -> %.3f%%" % (
            100 * old["BTC/USDT(以前被當美股)"], 100 * new_btc, 100 * old["2330.TW(以前平均值)"], 100 * new_tw))
        self.assertGreater(new_btc, old["BTC/USDT(以前被當美股)"])


if __name__ == "__main__":
    unittest.main()
