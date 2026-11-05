# -*- coding: utf-8 -*-
"""第四階段:所有策略的訊號不得使用未來資料。只用固定種子的合成資料,不連網。

方法一(截斷不變性):把資料尾巴截掉,前面每一根的進出場訊號必須完全一樣。
方法二(序列開頭):前面幾十根的訊號不能因為『整段資料多長』而改變——
          這能抓到負索引繞回(C[i-3] 在 i<3 時取到整段資料的最後一根)這種只發生在開頭的未來函數。"""
import os, sys, math, random, unittest, warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")          # 匯入 app 只為了載入擴充策略庫,不做網路連線檢查
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A          # noqa: E402  (註冊 147 個擴充策略)
import sim as S          # noqa: E402


def synth(n, seed):
    rnd = random.Random(seed); px = 100.0; rows = []
    for i in range(n):
        drift = 0.0006 * math.sin(i / 120.0); vol = 0.01 + 0.006 * (1 + math.sin(i / 70.0))
        o = px; c = o * (1 + drift + rnd.gauss(0, vol))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2))); l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        v = 1000 * (1 + abs(rnd.gauss(0, 1))) * (1 + (h - l) / o * 20)
        rows.append([i * 14400000, o, h, l, c, v]); px = c
    return rows


def arrays(rows):
    return ([r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows], [r[5] for r in rows])


class TestNoLookahead(unittest.TestCase):
    def test_strategy_library_is_loaded(self):
        self.assertGreaterEqual(len(S.STRATS), 180)

    def test_signals_do_not_change_when_future_bars_are_removed(self):
        rows = synth(900, 7); O, H, L, C, V = arrays(rows)
        bad = []
        for k, s in S.STRATS.items():
            el, xl = s["build"](O, H, L, C, V, "4h")
            for cut in (540, 720):
                O2, H2, L2, C2, V2 = arrays(rows[:cut])
                el2, xl2 = s["build"](O2, H2, L2, C2, V2, "4h")
                d = [i for i in range(cut) if bool(el[i]) != bool(el2[i]) or bool(xl[i]) != bool(xl2[i])]
                if d:
                    bad.append((k, cut, d[:3])); break
        self.assertEqual(bad, [], "這些策略的訊號會隨未來資料改變(未來函數):%s" % bad)

    def test_first_bars_do_not_depend_on_series_length(self):
        base = synth(1400, 11); K = 60; bad = {}
        rnd = random.Random(5)
        for _ in range(12):
            a = rnd.randint(0, 600); l1 = rnd.randint(300, 600); l2 = rnd.randint(300, 600)
            s1 = base[a:a + l1]; s2 = base[a:a + l2]
            for k, s in S.STRATS.items():
                e1, x1 = s["build"](*arrays(s1), "4h"); e2, x2 = s["build"](*arrays(s2), "4h")
                d = [i for i in range(K) if bool(e1[i]) != bool(e2[i]) or bool(x1[i]) != bool(x2[i])]
                if d: bad.setdefault(k, set()).update(d)
        self.assertEqual(bad, {}, "這些策略開頭幾根的訊號會隨資料長度改變(負索引繞回):%s" % bad)

    def test_three_soldiers_regression(self):
        """修正前:i=2 時比較 C[0] > C[-1](整段最後一根)。專門用會觸發的資料驗證。"""
        # 前 3 根:每根陽線、且 C[0] 必須大於『整段最後一根』才會被舊版誤觸發;最後一根設很低
        n = 10
        O = [10, 11, 12] + [11] * (n - 4) + [5]
        C = [11, 12, 13] + [11] * (n - 4) + [4]
        H = [max(o, c) + 0.1 for o, c in zip(O, C)]; L = [min(o, c) - 0.1 for o, c in zip(O, C)]
        el, xl = S.STRATS["three_soldiers"]["build"](O, H, L, C, [1.0] * n, "4h")
        self.assertFalse(el[2], "第 3 根不能因為 C[-1] 而被判成三白兵")


if __name__ == "__main__":
    unittest.main()
