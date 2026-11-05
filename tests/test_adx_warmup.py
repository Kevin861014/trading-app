# -*- coding: utf-8 -*-
"""C1.1 第二部分:sim.dmi 暖機/前視問題的獨立測試(A 現行 / B 教科書因果版 / C 現行+嚴格暖機)。
不修改 sim.py:只在記憶體暫時替換 sim.dmi(validation/stage3_ui/C1_1_adx/warmup/warmup_common.py)。離線,用 warmup/snapshots.json 的真實 K 線。"""
import os, sys, unittest, warnings
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "validation", "stage3_ui", "C1_1_adx", "warmup"))
import warmup_common as W
import sim

SNAP = W.load_snap()["rows"]
LENS = [20, 28, 30, 35, 40, 60, 100, 150, 250]


def hlc(rows): return [r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows]


def differs(a, b):
    if a is None or b is None: return (a is None) != (b is None)
    return abs(a - b) > 1e-9


def dmi_violations(F, rows):
    H, L, C = hlc(rows); full = F(H, L, C); bad = []
    for n in LENS:
        part = F(H[:n], L[:n], C[:n])
        bad += [(n, t) for t in range(n) if any(differs(part[j][t], full[j][t]) for j in range(3))]
    return bad


class TestCausality(unittest.TestCase):
    def test_current_sim_dmi_leaks_future_data_in_the_first_bars(self):
        # 現況(A):資料只有 20 根時第 15~19 根沒有 ADX,給 28 根以上卻『回頭』補出第 15~26 根(用了之後的 DX)。這是審查發現,不是新改的東西。
        bad = dmi_violations(W.dmi_A, SNAP["BTC/USDT|4h"][:700])
        self.assertTrue(bad); self.assertTrue(all(t < 27 for _, t in bad), bad[:5])

    def test_textbook_wilder_is_causal(self):
        for k in ("BTC/USDT|4h", "2330.TW|1d", "CHZ/USDT|4h"):
            self.assertEqual(dmi_violations(W.dmi_B, SNAP[k][:700]), [], k)

    def test_strict_warmup_masks_are_causal_and_cut_exactly_K_bars(self):
        for K in (27, 50, 100, 200):
            F = W.dmi_C(K); rows = SNAP["CHZ/USDT|4h"][:700]; H, L, C = hlc(rows)
            self.assertEqual(dmi_violations(F, rows), [], K)
            p, m, a = F(H, L, C)
            self.assertTrue(all(x is None for x in a[:K]) and all(x is None for x in p[:K]) and a[K] is not None)

    def test_strategy_signals_are_prefix_invariant_for_B_and_C(self):
        rows = SNAP["2330.TW|1d"][:700]
        for V in ("B", "C27", "C100"):
            for key in W.ADX_STRATS:
                with W.use(V):
                    full = W.build(key, rows, "1d")
                    for n in LENS:
                        part = W.build(key, rows[:n], "1d")
                        for t in range(n):
                            self.assertEqual((bool(part[0][t]), bool(part[1][t])), (bool(full[0][t]), bool(full[1][t])), (V, key, n, t))

    def test_strategy_signals_of_A_show_the_leak(self):
        n_bad = 0; rows = SNAP["2330.TW|1d"][:700]
        for key in W.ADX_STRATS:
            with W.use("A"):
                full = W.build(key, rows, "1d")
                for n in LENS:
                    part = W.build(key, rows[:n], "1d"); n_bad += sum(1 for t in range(n) if (bool(part[0][t]), bool(part[1][t])) != (bool(full[0][t]), bool(full[1][t])))
        self.assertGreater(n_bad, 0)


class TestConvergenceAndNoMutation(unittest.TestCase):
    def test_A_and_B_agree_after_150_bars(self):
        for k in ("BTC/USDT|4h", "NVDA|1d", "CHZ/USDT|4h"):
            H, L, C = hlc(SNAP[k]); a = W.dmi_A(H, L, C)[2]; b = W.dmi_B(H, L, C)[2]
            self.assertLess(max(abs(a[t] - b[t]) for t in range(150, len(C))), 1e-3, k)

    def test_use_restores_the_original_function_and_sim_source_is_unchanged(self):
        import inspect
        orig = sim.dmi
        with W.use("B"): self.assertIsNot(sim.dmi, orig)
        self.assertIs(sim.dmi, orig)
        self.assertIn("s=(s*(n-1)+dx[i])/n", inspect.getsource(orig))        # sim.py 原樣


class TestBotComboChz(unittest.TestCase):
    """機器人 CHZ/USDT 4H ema50_200_adx:機器人每輪用最近 400 根已收盤 K 棒。比較最近 300 個滾動窗口的末端決定。"""

    def test_last_300_rolling_windows_have_identical_decisions(self):
        rows = SNAP["CHZ/USDT|4h"]; N = len(rows)
        def pos(el, xl):
            p = False
            for i in range(len(el)):
                if p and xl[i]: p = False
                if (not p) and el[i]: p = True
            return p
        for e in range(N - 300, N):
            win = rows[e - 399:e + 1]; res = {}
            for V in ("A", "B", "C100", "C200"):
                with W.use(V): el, xl = W.build("ema50_200_adx", win, "4h")[:2]
                res[V] = ([(bool(el[i]), bool(xl[i])) for i in range(-10, 0)], pos(el, xl))
            for V in ("B", "C100", "C200"): self.assertEqual(res[V], res["A"], (V, e))

    def test_bot_strategy_source_is_the_same_as_the_app_copy(self):
        bot = os.path.join(os.path.dirname(ROOT), "順勢交易機器人", "integration", "extra_strats.py")
        if not os.path.exists(bot): self.skipTest("bot copy not found")
        a = open(bot, encoding="utf-8").read(); b = open(os.path.join(ROOT, "integration", "extra_strats.py"), encoding="utf-8").read()
        f = lambda s: s[s.index("def sig_ema50_200_adx"):s.index("def dual_mom_positions")]
        self.assertEqual(f(a), f(b))
        sa = open(os.path.join(os.path.dirname(bot), "..", "sim.py"), encoding="utf-8").read(); sb = open(os.path.join(ROOT, "sim.py"), encoding="utf-8").read()
        g = lambda s: s[s.index("def dmi("):s.index("def vortex(")]
        self.assertEqual(g(sa), g(sb))


if __name__ == "__main__":
    unittest.main()
