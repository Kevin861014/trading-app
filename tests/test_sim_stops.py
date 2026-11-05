# -*- coding: utf-8 -*-
"""第二階段:回測停損/停利/進場時序。全部用人工 OHLC,不依賴歷史資料。

K 棒索引約定:bar0 = 訊號棒(收盤後發出買進訊號),bar1 = 下一根開盤進場(第一根持倉的 K 棒)。
OHLC 無法得知一根 K 棒內高低點的先後,所以規則是:
  * 只用「進入該根之前已生效」的停損判斷;追蹤停損要等該根收盤後才更新、下一根才生效(機器人實盤也是這樣)。
  * 同一根同時碰到停利與停損 → 視為停損先到(保守)。
  * 跳空跌破停損 → 以開盤價成交。
  * 追蹤高點從實際進場價起算,不使用進場之前那根訊號棒的高點。"""
import os, sys, unittest, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim as S

H1 = 3600000


def run(O, H, L, C, el, xl=None, A=None, atr_stop=0.0, atr_trail=0.0, atr_tp=0.0,
        pct_stop=0.0, pct_trail=0.0, pct_tp=0.0, mod=S):
    n = len(C)
    T = [i * H1 for i in range(n)]
    xl = xl or [False] * n
    A = A or [2.0] * n
    el = (list(el) + [False] * n)[:n]
    return mod._simulate(T, O, H, L, C, el, xl, A, atr_stop, atr_trail, atr_tp, 0.0, 1.0, 10000.0,
                         pct_stop, pct_trail, pct_tp, commission=0.0, slippage=0.0)


def closed(log):
    return [t for t in log if not t.get("open")]


class TestStopTiming(unittest.TestCase):
    # ---- 先跌後漲 / 進場當根劇烈波動 ----
    def test_down_then_up_in_entry_bar_hits_initial_stop(self):
        O = [100, 100, 95, 95]; H = [100, 130, 96, 96]; L = [100, 93, 94, 94]; C = [100, 128, 95, 95]
        _, _, tr, log = run(O, H, L, C, [True], atr_stop=3.0)          # stop = C[0]-3*2 = 94
        t = closed(log)[0]
        self.assertEqual((t["entry_i"], t["exit_i"]), (1, 1))
        self.assertAlmostEqual(t["entry_px"], 100)
        self.assertAlmostEqual(t["exit_px"], 94)                        # 停損價成交,不是最低價 93,也不是後來的高價

    def test_crash_in_entry_bar(self):
        O = [100, 100, 80, 80]; H = [100, 101, 85, 85]; L = [100, 80, 79, 79]; C = [100, 82, 80, 80]
        _, _, tr, log = run(O, H, L, C, [True], atr_stop=3.0)
        t = closed(log)[0]
        self.assertEqual(t["exit_i"], 1)
        self.assertAlmostEqual(t["exit_px"], 94)

    # ---- 先漲後跌:同一根 K 棒的高點不能先把追蹤停損拉高再拿同根低點去觸發 ----
    def test_same_bar_high_does_not_raise_stop_for_same_bar_low(self):
        # 進場價 100;bar1 衝到 120 又回到 99(低點 99 > 初始停損 94)。
        O = [100, 100, 106, 105, 105]; H = [100, 120, 107, 106, 106]; L = [100, 99, 104, 104, 104]; C = [100, 105, 105, 105, 105]
        _, _, tr, log = run(O, H, L, C, [True], atr_stop=3.0, atr_trail=2.0)   # 追蹤距離 4
        t = closed(log)[0]
        self.assertEqual(t["exit_i"], 2, "bar1 的停損應是進入該根前的 94,低點 99 碰不到;拉高後的停損 116 要到 bar2 才生效")
        self.assertAlmostEqual(t["exit_px"], 106)                       # bar2 開盤 106 已跌破 116 → 以開盤價成交

    def test_legacy_logic_would_have_exited_in_bar1(self):
        """對照組:原本 main 分支的 sim.py 會在 bar1 就出場(用同根高點拉高停損再用同根低點判斷)。"""
        legacy_path = os.environ.get("LEGACY_SIM")
        if not legacy_path or not os.path.exists(legacy_path):
            self.skipTest("沒有提供 LEGACY_SIM(舊版 sim.py 路徑),略過對照")
        import importlib.util
        spec = importlib.util.spec_from_file_location("sim_legacy", legacy_path)
        L0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(L0)
        O = [100, 100, 106, 105, 105]; H = [100, 120, 107, 106, 106]; L = [100, 99, 104, 104, 104]; C = [100, 105, 105, 105, 105]
        n = 5; T = [i * H1 for i in range(n)]
        _, _, _, log = L0._simulate(T, O, H, L, C, [True] + [False] * 4, [False] * n, [2.0] * n, 3.0, 2.0, 0.0, 0.0, 1.0, 10000.0,
                                    0.0, 0.0, 0.0, commission=0.0, slippage=0.0)
        self.assertEqual(log[0]["exit_date"], __import__("datetime").datetime.utcfromtimestamp(1 * H1 / 1000))

    # ---- 跳空 ----
    def test_gap_down_through_stop_fills_at_open(self):
        O = [100, 100, 90, 90]; H = [100, 101, 95, 95]; L = [100, 99, 88, 88]; C = [100, 100, 91, 91]
        # bar1 沒碰停損 94;bar2 開盤 90 直接跳空跌破 → 以開盤價 90 成交
        _, _, tr, log = run(O, H, L, C, [True], atr_stop=3.0)
        t = closed(log)[0]
        self.assertEqual(t["exit_i"], 2)
        self.assertAlmostEqual(t["exit_px"], 90)

    # ---- 同一根同時碰到停利與停損 ----
    def test_stop_and_tp_same_bar_stop_wins(self):
        O = [100, 100, 100, 100]; H = [100, 106, 101, 101]; L = [100, 94, 99, 99]; C = [100, 100, 100, 100]
        _, _, tr, log = run(O, H, L, C, [True], pct_stop=0.05, pct_tp=0.05)    # stop 95, tp 105
        t = closed(log)[0]
        self.assertAlmostEqual(t["exit_px"], 95)
        self.assertLess(t["ret"], 0)

    def test_tp_only(self):
        O = [100, 100, 100, 100]; H = [100, 106, 101, 101]; L = [100, 99, 99, 99]; C = [100, 100, 100, 100]
        _, _, tr, log = run(O, H, L, C, [True], pct_stop=0.05, pct_tp=0.05)
        self.assertAlmostEqual(closed(log)[0]["exit_px"], 105)

    # ---- 訊號棒收盤後,下一根才進場 ----
    def test_entry_is_next_bar_open_not_signal_close(self):
        O = [100, 101, 101, 101]; H = [100, 102, 102, 102]; L = [100, 100, 100, 100]; C = [100, 101, 101, 101]
        _, _, tr, log = run(O, H, L, C, [True], atr_stop=3.0)
        t = log[0]
        self.assertEqual(t["entry_i"], 1)
        self.assertAlmostEqual(t["entry_px"], 101)                      # 下一根開盤,不是訊號棒收盤 100
        import datetime
        self.assertEqual(t["entry_date"], datetime.datetime.utcfromtimestamp(1 * H1 / 1000))

    # ---- 進場前的高點不能影響新倉的追蹤停損 ----
    def test_pre_entry_high_is_not_used(self):
        O = [100, 100, 100, 100]; H = [200, 101, 101, 101]; L = [100, 99.5, 99.5, 99.5]; C = [100, 100, 100, 100]
        _, _, tr, log = run(O, H, L, C, [True], pct_stop=0.05, pct_trail=0.025)
        self.assertEqual(closed(log), [], "訊號棒的高點 200 發生在進場之前,不應把新倉的追蹤停損拉到 195")
        self.assertTrue(log[-1].get("open"))

    def test_pre_entry_high_legacy_exits_immediately(self):
        legacy_path = os.environ.get("LEGACY_SIM")
        if not legacy_path or not os.path.exists(legacy_path):
            self.skipTest("沒有提供 LEGACY_SIM,略過對照")
        import importlib.util
        spec = importlib.util.spec_from_file_location("sim_legacy2", legacy_path)
        L0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(L0)
        O = [100, 100, 100, 100]; H = [200, 101, 101, 101]; L = [100, 99.5, 99.5, 99.5]; C = [100, 100, 100, 100]
        n = 4; T = [i * H1 for i in range(n)]
        _, _, _, log = L0._simulate(T, O, H, L, C, [True, False, False, False], [False] * n, [2.0] * n, 0.0, 0.0, 0.0, 0.0, 1.0, 10000.0,
                                    0.05, 0.025, 0.0, commission=0.0, slippage=0.0)
        self.assertTrue(any(not t.get("open") for t in log), "舊版會因為進場前的高點 200 在 bar1 立刻被洗出場")

    # ---- 正常運作 ----
    def test_atr_stop_price_uses_signal_close_and_atr(self):
        O = [100, 100, 90, 90]; H = [100, 101, 91, 91]; L = [100, 99, 89, 89]; C = [100, 100, 90, 90]
        _, _, tr, log = run(O, H, L, C, [True], A=[2.5] * 4, atr_stop=3.0)           # stop = 100 - 7.5
        self.assertAlmostEqual(closed(log)[0]["exit_px"], 90)           # bar2 開盤 90 < 92.5 → 跳空以開盤成交
        O = [100, 100, 100]; L = [100, 92, 99]; H = [100, 101, 101]; C = [100, 100, 100]
        _, _, tr, log = run(O, H, L, C, [True], A=[2.5, 2.5, 2.5], atr_stop=3.0)
        self.assertAlmostEqual(closed(log)[0]["exit_px"], 92.5)

    def test_pct_stop_price(self):
        O = [100, 100, 100]; H = [100, 101, 101]; L = [100, 96, 99]; C = [100, 100, 100]
        _, _, tr, log = run(O, H, L, C, [True], pct_stop=0.03)          # 97 → 低點 96 觸發
        self.assertAlmostEqual(closed(log)[0]["exit_px"], 97)

    def test_trailing_stop_ratchets_only_up_after_close(self):
        # 持續上漲 → 追蹤停損逐根上移;之後回落才被打到,出場價高於進場價
        O = [100, 100, 108, 116, 114, 100]
        H = [100, 110, 118, 120, 115, 101]
        L = [100, 99, 107, 115, 100, 98]
        C = [100, 108, 116, 118, 101, 99]
        _, _, tr, log = run(O, H, L, C, [True], A=[2.0] * 6, atr_stop=3.0, atr_trail=2.0)
        t = closed(log)[0]
        self.assertGreater(t["exit_px"], 100)
        self.assertEqual(t["exit_i"], 4)

    def test_signal_exit_next_open(self):
        O = [100, 100, 104, 104]; H = [100, 101, 105, 105]; L = [100, 99, 103, 103]; C = [100, 100, 104, 104]
        _, _, tr, log = run(O, H, L, C, [True], xl=[False, True, False, False], atr_stop=3.0)
        t = closed(log)[0]
        self.assertEqual(t["exit_i"], 2)
        self.assertAlmostEqual(t["exit_px"], 104)


class TestPyramidTiming(unittest.TestCase):
    def test_pyramid_stop_checked_before_update(self):
        O = [100, 100, 106, 105, 105]; H = [100, 120, 107, 106, 106]; L = [100, 99, 104, 104, 104]; C = [100, 105, 105, 105, 105]
        n = 5; T = [i * H1 for i in range(n)]
        _, _, tr, log = S._simulate_pyramid(T, O, H, L, C, [True] + [False] * 4, [2.0] * n, 3.0, 2.0, 100.0, 0, 1.0, 1.0, 10000.0,
                                            commission=0.0, slippage=0.0)
        t = closed(log)[0]
        self.assertEqual(t["exit_i"], 2)
        self.assertAlmostEqual(t["exit_px"], 106)

    def test_pyramid_pre_entry_high_not_used(self):
        O = [100, 100, 100, 100]; H = [500, 101, 101, 101]; L = [100, 99, 99, 99]; C = [100, 100, 100, 100]
        n = 4; T = [i * H1 for i in range(n)]
        _, _, tr, log = S._simulate_pyramid(T, O, H, L, C, [True] + [False] * 3, [2.0] * n, 3.0, 2.0, 100.0, 0, 1.0, 1.0, 10000.0,
                                            commission=0.0, slippage=0.0)
        self.assertEqual(closed(log), [])


if __name__ == "__main__":
    unittest.main()
