# -*- coding: utf-8 -*-
"""C1.1 ADX 審查測試:獨立的教科書 Wilder 參考實作 vs 現有 calc_adx(網站顯示)與 sim.dmi(策略)。
只讀、離線(用 validation/stage3_ui/C1_1_adx/snapshots 的真實 OHLC 快照)。不修改也不取代任何既有函式。
這些測試同時『釘住』目前的行為:若日後有人改了 calc_adx 或 sim.dmi,這裡會失敗,提醒要照審查結論處理。"""
import glob, json, os, random, sys, unittest, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import adx_reference as R
import app as A
import sim

SNAP = os.path.join(ROOT, "validation", "stage3_ui", "C1_1_adx", "snapshots")


def load(name):
    d = json.load(open(os.path.join(SNAP, name + ".json"), encoding="utf-8"))["rows"]
    return d, [r[2] for r in d], [r[3] for r in d], [r[4] for r in d]


def synth(n=400, seed=3):
    random.seed(seed); c = 100.0; rows = []
    for i in range(n):
        o = c; c = c * (1 + random.gauss(0, 0.01)); h = max(o, c) * (1 + abs(random.gauss(0, 0.004))); l = min(o, c) * (1 - abs(random.gauss(0, 0.004)))
        rows.append([i * 86400000, o, h, l, c, 1000.0])
    return rows, [r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows]


class TestReferenceImplementation(unittest.TestCase):
    def test_reference_matches_pandas_ewm_after_warmup(self):
        # 兩種獨立寫法(n 根加總種子 vs pandas ewm 以第一根為種子)在暖機後會收斂到同一條線
        for name in ("BTC-USDT_1d", "2330.TW_1d", "AAPL_1w"):
            _, H, L, C = load(name); _, _, w = R.wilder_adx(H, L, C); _, _, p = R.pandas_ewm_adx(H, L, C)
            self.assertLess(max(abs(w[t] - p[t]) for t in range(250, len(C))), 0.01, name)

    def test_first_adx_value_index_is_2n_minus_1(self):
        _, H, L, C = synth(); _, _, w = R.wilder_adx(H, L, C, 14)
        self.assertEqual(next(i for i, v in enumerate(w) if v is not None), 27)
        self.assertTrue(all(v is None for v in w[:27]))

    def test_adx_is_bounded_and_flat_series_does_not_crash(self):
        _, H, L, C = synth(); _, _, w = R.wilder_adx(H, L, C)
        self.assertTrue(all(0 <= v <= 100 for v in w if v is not None))
        flat = [100.0] * 80; _, _, f = R.wilder_adx(flat, flat, flat)
        self.assertTrue(all(v is None or v == 0 for v in f))

    def test_classify_matches_market_character(self):
        rows, H, L, C = synth(); pdi, mdi, _ = R.wilder_adx(H, L, C)
        for adx in (10, 19.9, 20, 24.9, 25, 40):
            for p, m in ((20, 10), (10, 20)):
                a = {"adx": adx, "plus_di": p, "minus_di": m}
                orig = A.calc_adx; A.calc_adx = lambda *_a, **_k: a
                try: lab = A.market_character(rows)["label"]
                finally: A.calc_adx = orig
                self.assertEqual(R.classify(adx, p, m), lab, (adx, p, m))


class TestDisplayAdx(unittest.TestCase):
    """C1.1 修正後的 app.calc_adx:預設是教科書 Wilder(14);舊算法 'sma_dx'(最近 14 個 DX 的簡單平均)只留給相容性比較。"""

    def test_default_is_textbook_wilder_against_independent_reference(self):
        for name in ("BTC-USDT_1d", "2330.TW_1w", "AAPL_1h", "SOL-USDT_4h"):
            rows, H, L, C = load(name); pdi, mdi, w = R.wilder_adx(H, L, C)
            random.seed(1)
            for t in [len(C) - 1] + random.sample(range(60, len(C) - 1), 12):
                a = A.calc_adx(rows[:t + 1])
                self.assertEqual((a["adx"], a["plus_di"], a["minus_di"], a["method"]), (round(w[t], 1), round(pdi[t], 1), round(mdi[t], 1), "wilder"), (name, t))

    def test_legacy_sma_dx_mode_still_reproduces_the_old_numbers(self):
        for name in ("BTC-USDT_1d", "2330.TW_1w", "AAPL_1h"):
            rows, H, L, C = load(name); pdi, mdi, _ = R.wilder_adx(H, L, C); _, _, sma = R.sma_dx_adx(H, L, C)
            for t in (len(C) - 1, len(C) - 40, 200):
                a = A.calc_adx(rows[:t + 1], method="sma_dx")
                self.assertEqual((a["adx"], a["plus_di"], a["minus_di"], a["method"]), (round(sma[t], 1), round(pdi[t], 1), round(mdi[t], 1), "sma_dx"), (name, t))

    def test_di_identical_in_both_methods_and_unknown_method_rejected(self):
        rows = load("BTC-USDT_1d")[0]; a, b = A.calc_adx(rows), A.calc_adx(rows, method="sma_dx")
        self.assertEqual((a["plus_di"], a["minus_di"]), (b["plus_di"], b["minus_di"]))
        with self.assertRaises(ValueError): A.calc_adx(rows, method="ewm")

    def test_the_two_methods_really_differ(self):
        for name in ("BTC-USDT_1d", "2330.TW_1w", "AAPL_1d"):
            _, H, L, C = load(name); _, _, w = R.wilder_adx(H, L, C); _, _, s = R.sma_dx_adx(H, L, C)
            d = [abs(s[t] - w[t]) for t in range(100, len(C))]
            self.assertGreater(sum(d) / len(d), 2.5, name); self.assertGreater(max(d), 9, name)

    def test_pinned_last_values_both_methods(self):
        # 快照最後一根:新預設(Wilder)與舊算法(sma_dx)。2330.TW 週線 27.4 vs 16.1 就是 C1.1 發現的例子
        for name, wil, sma in (("BTC-USDT_1d", 21.8, 21.4), ("2330.TW_1w", 27.4, 16.1), ("AAPL_1h", 32.2, 40.0)):
            rows = load(name)[0]
            self.assertEqual(A.calc_adx(rows)["adx"], wil, name); self.assertEqual(A.calc_adx(rows, method="sma_dx")["adx"], sma, name)

    def test_threshold_classification_20_and_25(self):
        rows = load("BTC-USDT_1d")[0]
        def lab(adx, p, m, method=None):
            orig = A.calc_adx; A.calc_adx = lambda *_a, **_k: {"adx": adx, "plus_di": p, "minus_di": m, "method": "wilder"}
            try: return A.market_character(rows, method=method)
            finally: A.calc_adx = orig
        for adx, p, m, want in ((19.9, 20, 10, "盤整"), (20.0, 20, 10, "趨勢轉換中"), (24.9, 10, 20, "趨勢轉換中"), (25.0, 20, 10, "上升趨勢"), (25.0, 10, 20, "下降趨勢"), (40, 15, 15, "上升趨勢")):
            r = lab(adx, p, m); self.assertEqual(r["label"], want, (adx, p, m)); self.assertEqual(r["label"], R.classify(adx, p, m))
            self.assertEqual((r["adxMethod"], r["adxLabel"]), ("wilder", "ADX (Wilder, 14)"))

    def test_label_example_changes_for_2330_weekly(self):
        rows, H, L, C = load("2330.TW_1w"); pdi, mdi, w = R.wilder_adx(H, L, C)
        new, old = A.market_character(rows), A.market_character(rows, method="sma_dx")
        self.assertEqual(old["label"], "盤整"); self.assertIn(new["label"], ("上升趨勢", "下降趨勢")); self.assertEqual(new["label"], R.classify(w[-1], pdi[-1], mdi[-1]))
        self.assertEqual(old["adxMethod"], "sma_dx")

    def test_market_character_endpoint_reports_method(self):
        from unittest import mock
        rows = load("BTC-USDT_1d")[0][-130:]
        with mock.patch.object(A, "fetch_data", lambda *a, **k: rows):
            j = A.app.test_client().get("/api/market_character?symbol=BTC/USDT&timeframe=1d").get_json()
        self.assertEqual((j["adxMethod"], j["adxLabel"]), ("wilder", "ADX (Wilder, 14)")); self.assertEqual(j["adx"], A.calc_adx(rows)["adx"])
        with mock.patch.object(A, "fetch_data", lambda *a, **k: rows[:10]):
            j = A.app.test_client().get("/api/market_character?symbol=BTC/USDT&timeframe=1d").get_json()
        self.assertEqual((j["code"], j["adxMethod"]), ("na", "wilder"))

    def test_ranking_signals_pf_oos_do_not_depend_on_the_display_adx_method(self):
        # 排名/PF/勝率/回撤/OOS/訊號:換 ADX 顯示算法(wilder <-> sma_dx)後,best_strategy 與 analyze 的回應除了 character 之外逐欄相同
        from unittest import mock
        rows = load("BTC-USDT_1d")[0]
        def run(method):
            with mock.patch.object(A, "fetch_data", lambda *a, **k: rows), mock.patch.object(A, "ADX_METHOD_DEFAULT", method):
                c = A.app.test_client()
                best = c.get("/api/best_strategy?symbol=BTC/USDT&period=2y&timeframe=1d&use_oos=1").get_json()
                ana = c.get("/api/analyze?symbol=BTC/USDT&strategy=diadx&period=2y&timeframe=1d").get_json()
            return best, ana
        (b1, a1), (b2, a2) = run("wilder"), run("sma_dx")
        self.assertEqual(b1["character"]["adxMethod"], "wilder"); self.assertEqual(b2["character"]["adxMethod"], "sma_dx")
        self.assertNotEqual(b1["character"]["adx"], b2["character"]["adx"])
        strip = lambda d: {k: v for k, v in d.items() if k != "character"}
        self.assertTrue(b1["results"]); self.assertEqual(strip(b1), strip(b2)); self.assertEqual(a1, a2)

    def test_front_end_labels(self):
        st = os.path.join(ROOT, "static")
        rd = lambda p: open(os.path.join(st, p), encoding="utf-8").read()
        for f in ("js/50-analysis.js", "js/60-views.js", "js/66-mtf.js", "js/10-cards.js"):
            self.assertIn("ADX (Wilder, 14)", rd(f), f)
        self.assertIn("ADX (Wilder, 14)", rd("index.html"))


class TestStrategyAdx(unittest.TestCase):
    """sim.dmi(六個策略用):核心是 Wilder,但 ADX 的『第一個種子』接法有暖機瑕疵,只影響前約 100 根。"""

    def test_converges_to_textbook_wilder_after_150_bars(self):
        for name in ("BTC-USDT_1d", "SOL-USDT_1h", "2330.TW_1w", "AAPL_1d"):
            _, H, L, C = load(name); _, _, w = R.wilder_adx(H, L, C); _, _, s = sim.dmi(H, L, C)
            self.assertLess(max(abs(w[t] - s[t]) for t in range(150, len(C))), 1e-3, name)

    def test_plus_minus_di_identical_to_textbook(self):
        _, H, L, C = load("BTC-USDT_1d"); wp, wm, _ = R.wilder_adx(H, L, C); sp, sm, _ = sim.dmi(H, L, C)
        for t in range(len(C)):
            self.assertEqual(wp[t] is None, sp[t] is None)
            if wp[t] is not None: self.assertAlmostEqual(wp[t], sp[t], 9); self.assertAlmostEqual(wm[t], sm[t], 9)

    def test_known_warmup_artifact_is_documented_not_silently_assumed_fixed(self):
        # 現況:sim.dmi 在第 15 根就吐出 ADX(教科書要到第 27 根),且那幾根用到了之後 DX 的平均(輕微前視),前 100 根內最多差約 1.4~6 點。
        # 這是審查發現,不是這次要改的東西;若日後修正,這個測試要跟著更新並重跑回測比對。
        _, H, L, C = load("BTC-USDT_1d"); _, _, s = sim.dmi(H, L, C)
        self.assertEqual(next(i for i, v in enumerate(s) if v is not None), 15)
        short = sim.dmi(H[:20], L[:20], C[:20])[2]
        self.assertTrue(all(v is None for v in short))      # 只給 20 根時 sim.dmi 沒有 ADX,給 28 根以上才『回頭』補出第 15~26 根
        longer = sim.dmi(H[:30], L[:30], C[:30])[2]
        self.assertIsNotNone(longer[15])

    def test_exactly_six_strategies_use_adx(self):
        calls = {"n": 0}; orig = sim.dmi
        def traced(*a, **k): calls["n"] += 1; return orig(*a, **k)
        rows, H, L, C = synth(); O = [r[1] for r in rows]; V = [r[5] for r in rows]; users = []
        sim.dmi = traced
        try:
            for k, m in A.STRATS.items():
                b = calls["n"]
                try: m["build"](O, H, L, C, V, "1d")
                except TypeError: m["build"](O, H, L, C, V)
                if calls["n"] > b: users.append(k)
        finally: sim.dmi = orig
        self.assertEqual(sorted(users), sorted(["diadx", "ema50_200_adx", "adx_di", "dmi_cross", "adx_di_trend", "holy_grail"]))

    def test_site_display_adx_is_not_used_by_any_strategy_or_ranking(self):
        src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
        import re
        # calc_adx / market_character 只出現在:定義、/api/market_character、tf_indicators(/api/mtf)、best_strategy 的 character 欄位
        used = re.findall(r"(?<![\w])(?<!def )(?:market_character|calc_adx)\(", src)
        self.assertEqual(len(used), 5, "calc_adx/market_character 的呼叫點數量變了,請重新審查 ADX 影響範圍")   # market_character 內 1、tf_indicators 2、/api/market_character 1、best_strategy 1


class TestNoMutation(unittest.TestCase):
    def test_audit_leaves_functions_unreplaced(self):
        import inspect
        self.assertIn("sum(dx_list[-period:]) / period", inspect.getsource(A.calc_adx))      # 仍是現有版
        self.assertIn("s=(s*(n-1)+dx[i])/n", inspect.getsource(sim.dmi))


if __name__ == "__main__":
    unittest.main()
