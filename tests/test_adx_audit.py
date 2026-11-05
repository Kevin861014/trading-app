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


class TestCurrentSiteAdx(unittest.TestCase):
    """app.calc_adx(網站顯示用):+DI/-DI 是 Wilder,ADX 則是『最近 14 個 DX 的簡單平均』,不是 Wilder 的第二次平滑。"""

    def test_di_equals_wilder_and_adx_equals_sma_of_dx(self):
        for name in ("BTC-USDT_1d", "2330.TW_1w", "AAPL_1h"):
            rows, H, L, C = load(name); pdi, mdi, _ = R.wilder_adx(H, L, C); _, _, sma = R.sma_dx_adx(H, L, C)
            random.seed(1)
            for t in [len(C) - 1] + random.sample(range(60, len(C) - 1), 12):
                a = A.calc_adx(rows[:t + 1])
                self.assertEqual((a["adx"], a["plus_di"], a["minus_di"]), (round(sma[t], 1), round(pdi[t], 1), round(mdi[t], 1)), (name, t))

    def test_it_differs_materially_from_wilder_adx(self):
        # 審查結論:不是四捨五入的小差異。暖機後平均 |差| 約 3.5~4.7 點,最大可達 10~20 點。釘住這個事實。
        for name in ("BTC-USDT_1d", "2330.TW_1w", "AAPL_1d"):
            _, H, L, C = load(name); _, _, w = R.wilder_adx(H, L, C); _, _, s = R.sma_dx_adx(H, L, C)
            d = [abs(s[t] - w[t]) for t in range(100, len(C))]
            self.assertGreater(sum(d) / len(d), 2.5, name); self.assertGreater(max(d), 9, name)

    def test_pinned_last_values_so_an_accidental_replacement_is_noticed(self):
        # 快照最後一根的既有輸出;若 calc_adx 被改成 Wilder,這幾個值會變(2330.TW 週線 16.1 → 27.4)
        for name, adx in (("BTC-USDT_1d", 21.4), ("2330.TW_1w", 16.1), ("AAPL_1h", 40.0)):
            self.assertEqual(A.calc_adx(load(name)[0])["adx"], adx, name)

    def test_label_changes_when_swapped_for_wilder(self):
        # 同一個標的、同一根 K 棒,換成 Wilder 後市場性格標籤會不同的例子(2330.TW 週線:現有=盤整,Wilder=上/下趨勢)
        rows, H, L, C = load("2330.TW_1w"); pdi, mdi, w = R.wilder_adx(H, L, C)
        self.assertEqual(A.market_character(rows)["label"], "盤整")
        self.assertIn(R.classify(w[-1], pdi[-1], mdi[-1]), ("上升趨勢", "下降趨勢"))


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
