# -*- coding: utf-8 -*-
"""D3:事先固定的設定不被改動、資料只來自幣安 USDT-M 永續公開 K 線、區段分類遵守『被選擇看過的歷史不算獨立』的規則。離線、不依賴 raw 資料。"""
import glob, json, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D3 = os.path.join(ROOT, "validation", "d3_walkforward")
sys.path.insert(0, D3); sys.path.insert(0, os.path.join(ROOT, "validation", "d2_portfolio"))
import d3_config as C
import d2_sim as S


class TestPreRegisteredConfig(unittest.TestCase):
    def test_blocks_are_contiguous_ordered_and_non_overlapping(self):
        b = C.BLOCKS
        for (c1, n1, a1, e1), (c2, n2, a2, e2) in zip(b, b[1:]): self.assertEqual(e1, a2, (n1, n2)); self.assertLess(a1, e1)
        self.assertIsNone(b[-1][3])

    def test_independent_class_never_touches_selection_exposed_history(self):
        for cls, name, a, e in C.BLOCKS:
            if cls == 'I': self.assertLessEqual(e, C.SELECTION_EXPOSED_FROM, name)
            if e is None or e > C.SELECTION_EXPOSED_FROM: self.assertNotEqual(cls, 'I', name)
        self.assertEqual({c for c, *_ in C.BLOCKS}, {'I', 'G', 'X', 'T'}); self.assertEqual(set(C.CLASS_LABEL), {'I', 'G', 'X', 'T'})
        self.assertNotIn("OOS", " ".join(C.CLASS_LABEL.values()))                      # 沒有任何類別被稱為 OOS 通過

    def test_selection_tail_starts_when_the_last_swap_happened(self):
        t = [x for x in C.BLOCKS if x[0] == 'T'][0]; self.assertEqual(t[2], C.ms(2026, 10, 29))
        self.assertEqual([x for x in C.BLOCKS if x[0] == 'X'][-1][3], C.ms(2026, 10, 29))

    def test_btc_regime_rule(self):
        for pct, want in ((15.1, 'up'), (15.0, 'range'), (0, 'range'), (-15.0, 'range'), (-15.1, 'down'), (-40, 'down'), (90, 'up')): self.assertEqual(C.btc_regime(pct), want, pct)

    def test_scenario_parameters_equal_the_d2_calibrated_ones(self):
        P = S.default_params({}, **C.PB)
        for k, v in C.D2_CALIBRATED.items(): self.assertEqual(P[k], v, k)
        self.assertEqual((P['slip_entry'], P['slip_exit'], P['slip_stop']), (0.0003, 0.0001, 0.00042)); self.assertEqual(C.PB['sumw_override'], 16.0); self.assertEqual(C.INIT, 310.0)
        d2 = open(os.path.join(ROOT, "validation", "d2_portfolio", "d2_scenarios.py"), encoding="utf-8").read()
        self.assertIn("slip_entry=0.0003, slip_exit=0.0001, slip_stop=0.00042, sumw_override=16.0", d2)               # 與 D2 的 A/B 設定逐字相同
        Ps = S.default_params({}, **C.PS); self.assertEqual((Ps['taker'], Ps['slip_entry'], Ps['slip_exit'], Ps['slip_stop']), (0.00075, 0.0006, 0.0002, 0.00084))

    def test_only_the_two_1h_combos_are_removed_in_scenario_b(self):
        self.assertEqual(set(C.ONE_H), {'TRX/USDT', 'XRP/USDT'})
        bk = sorted(glob.glob(os.path.join(r"C:\Users\User\發大財\研究備份_D2", "2*")))
        if not bk: self.skipTest("backup not available")
        cfg = json.load(open(os.path.join(bk[-1], "config.portfolio.json.REDACTED.json"), encoding="utf-8"))["combos"]
        self.assertEqual({c['symbol'] for c in cfg if c['timeframe'] == '1h'}, set(C.ONE_H)); self.assertEqual(len(cfg), 23)


class TestDataSourceAndSafety(unittest.TestCase):
    def test_only_binance_usdm_public_klines_no_spot_no_other_exchange(self):
        src = open(os.path.join(D3, "d3_data.py"), encoding="utf-8").read()
        self.assertIn("fapiPublicGetKlines", src); self.assertIn("binanceusdm", src)
        for bad in ("sapi", "spot", "Spot", "bybit", "okx", "coinbase", "kraken", "kucoin", "fetch_data(", "yfinance", "apiKey", "api_key", "create_order", "cancel_order", "set_leverage"):
            self.assertNotIn(bad, src.replace("spot", "") if bad in ("spot", "Spot") else src, bad)

    def test_no_script_touches_trading_apis_or_writes_the_bot_folder(self):
        for f in glob.glob(os.path.join(D3, "*.py")):
            t = open(f, encoding="utf-8").read()
            for bad in ("create_order", "cancel_order", "set_leverage", "fapiPrivate", "withdraw(", "binance_ro"): self.assertNotIn(bad, t, (f, bad))
            self.assertNotRegex(t, r"open\([^)]*BOT[^)]*,\s*['\"][wa]")

    def test_inventory_if_present_is_consistent(self):
        p = os.path.join(D3, "results", "data_inventory.json")
        if not os.path.exists(p): self.skipTest("inventory not generated")
        inv = json.load(open(p, encoding="utf-8")); syms = {k: v for k, v in inv["symbols"].items() if k != "BTC/USDT"}
        self.assertEqual(len(syms), 23)
        for s, e in syms.items():
            self.assertTrue(e["4h"]["bars"] > 0, s)
            if e.get("onboard_date"): self.assertGreaterEqual(e["4h"]["first"], e["onboard_date"], s)             # 不早於上市日:沒有補造
        self.assertIn("下架", inv["exchange_info"]["note"])


if __name__ == "__main__":
    unittest.main()
