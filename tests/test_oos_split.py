# -*- coding: utf-8 -*-
"""第二階段:IS / OOS 隔離。固定種子的合成資料,不連網。
設計見 validation/stage2_oos/DESIGN.md。"""
import os, sys, math, random, datetime, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import sim as S

FIXED_NOW = datetime.datetime(2026, 11, 1, 0, 0, 0)          # 固定「現在」,讓切點可重現
STEP = {"4h": 4 * 3600000, "1d": 86400000}
SUBSET = ["trend", "supertrend", "donchian", "tsmom", "smc", "ttm", "vortex", "sixline", "bbreak", "cci", "keltner", "hma"]


def ms(dt_):
    return A._to_ms(dt_)


def synth(n, step_ms, seed, end_dt=FIXED_NOW, start_px=100.0):
    rnd = random.Random(seed); px = start_px; rows = []
    end = ms(end_dt) - step_ms
    for i in range(n):
        drift = 0.0009 * math.sin(i / 90.0); vol = 0.012 + 0.006 * (1 + math.sin(i / 60.0))
        o = px; c = o * (1 + drift + rnd.gauss(0, vol))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2))); l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        rows.append([end - (n - 1 - i) * step_ms, o, h, l, c, 1000 * (1 + abs(rnd.gauss(0, 1)))]); px = c
    return rows


def scramble_after(rows, boundary_ms, seed):
    """把 boundary 之後的 K 棒換成完全不同的亂數走勢(時間戳不變)。"""
    out = [list(r) for r in rows]
    idx = next(i for i, r in enumerate(out) if r[0] >= boundary_ms)
    other = synth(len(out) - idx, out[1][0] - out[0][0], seed, start_px=out[idx - 1][4] * 0.7)
    for k, r in enumerate(other):
        out[idx + k][1:] = r[1:]
    return out


class TestSplit(unittest.TestCase):
    def test_time_ordered_split(self):
        rows = synth(5000, STEP["4h"], 1)
        ws = FIXED_NOW - datetime.timedelta(days=700)
        sp = A.is_oos_split(rows, ws, FIXED_NOW)
        self.assertIsNotNone(sp)
        b = ms(sp["boundary_dt"])
        i = sp["idx_b"]
        self.assertLess(rows[i - 1][0], b)
        self.assertGreaterEqual(rows[i][0], b)
        self.assertTrue(all(rows[k][0] < rows[k + 1][0] for k in range(len(rows) - 1)), "時間必須遞增(沒有被打亂)")
        # 邊界在窗口的 70% 處
        frac = (sp["boundary_dt"] - ws) / (FIXED_NOW - ws)
        self.assertAlmostEqual(frac, 0.7, places=6)

    def test_returns_none_when_data_too_short(self):
        rows = synth(150, STEP["4h"], 1)
        self.assertIsNone(A.is_oos_split(rows, FIXED_NOW - datetime.timedelta(days=20), FIXED_NOW))

    def test_partition_rules(self):
        d = lambda n: datetime.datetime(2026, 1, 1) + datetime.timedelta(days=n)
        ws, b = d(10), d(70)
        tl = [
            dict(entry_date=d(5), exit_date=d(20), ret=1.0),       # 暖機期進場 → 不算
            dict(entry_date=d(20), exit_date=d(30), ret=1.0),      # IS
            dict(entry_date=d(60), exit_date=d(80), ret=1.0),      # 跨邊界 → carry,兩邊都不算
            dict(entry_date=d(70), exit_date=d(75), ret=1.0),      # 剛好在邊界 → OOS
            dict(entry_date=d(90), exit_date=d(95), ret=-1.0),     # OOS
            dict(entry_date=d(99), exit_date=None, ret=None, open=True),   # 未平倉
        ]
        is_t, oos_t, carry, opened = A.partition_trades(tl, ws, b)
        self.assertEqual((len(is_t), len(oos_t), len(carry), len(opened)), (1, 2, 1, 1))
        self.assertIs(carry[0], tl[2])


class TestVerdict(unittest.TestCase):
    def test_insufficient_never_passes_even_with_great_pf(self):
        self.assertEqual(A.oos_verdict(A.OOS_MIN_TRADES - 1, 99.0), (True, False))
        self.assertEqual(A.oos_verdict(0, 999.0), (True, False))

    def test_enough_trades_then_pf_decides(self):
        self.assertEqual(A.oos_verdict(A.OOS_MIN_TRADES, 1.5), (False, True))
        self.assertEqual(A.oos_verdict(A.OOS_MIN_TRADES, 1.0), (False, False))
        self.assertEqual(A.oos_verdict(A.OOS_MIN_TRADES + 10, 0.8), (False, False))


class TestNoLeak(unittest.TestCase):
    def setUp(self):
        self.rows = synth(5000, STEP["4h"], 3)
        self.days = 700
        ws = FIXED_NOW - datetime.timedelta(days=self.days)
        self.split = A.is_oos_split(self.rows, ws, FIXED_NOW)
        self.b_ms = ms(self.split["boundary_dt"])
        self.pool = {k for k in SUBSET}
        p = mock.patch.dict(S.STRATS, {k: v for k, v in S.STRATS.items() if k in SUBSET}, clear=True)
        p.start(); self.addCleanup(p.stop)

    def rank(self, rows, **kw):
        kw.setdefault("top_n", 200)
        return A.rank_strategies(rows, "BTC/USDT", "4h", self.pool, kw.pop("min_trades", 5), self.days, now_dt=FIXED_NOW, **kw)

    def test_scrambling_oos_bars_cannot_change_is_ranking_or_is_stats(self):
        top1, sp1, _ = self.rank(self.rows)
        self.assertGreaterEqual(len(top1), 3, "合成資料要能選出足夠的策略,否則這個測試是空的")
        rows2 = scramble_after(self.rows, self.b_ms, 99)
        top2, sp2, _ = self.rank(rows2)
        self.assertEqual([r["strat"] for r in top1], [r["strat"] for r in top2], "OOS 資料不得影響入選名單與排名")
        for a, b in zip(top1, top2):
            self.assertEqual(a["is"], b["is"], a["strat"])
            self.assertEqual(a["score"], b["score"], a["strat"])
        # 但 OOS 與全期間績效必須跟著變(證明 OOS 資料確實只用在 OOS)
        self.assertTrue(any(a["oos"] != b["oos"] for a, b in zip(top1, top2)))
        self.assertTrue(any(a["full"] != b["full"] for a, b in zip(top1, top2)))

    def test_is_backtests_never_see_oos_bars(self):
        seen = []
        real = A.run_backtest
        def spy(ohlcv, *a, **k):
            seen.append(ohlcv[-1][0]); return real(ohlcv, *a, **k)
        with mock.patch.object(A, "run_backtest", spy):
            top, sp, tested = self.rank(self.rows, top_n=3)
        n_is_phase = tested                                   # 先對每個策略跑 IS,之後才對入選者跑完整資料
        self.assertTrue(all(t < self.b_ms for t in seen[:n_is_phase]), "IS 階段的回測不得包含邊界之後的 K 棒")
        self.assertTrue(all(t == self.rows[-1][0] for t in seen[n_is_phase:]), "只有入選者才會用完整資料跑 OOS")
        self.assertLessEqual(len(seen) - n_is_phase, 3)       # OOS 只對入選者做一次,沒有反覆

    def test_ranking_is_sorted_by_is_score_only(self):
        top, _, _ = self.rank(self.rows)
        self.assertEqual([r["score"] for r in top], sorted([r["score"] for r in top], reverse=True))

    def test_insufficient_oos_trades_is_labelled_and_never_counts_as_pass(self):
        with mock.patch.object(A, "OOS_MIN_TRADES", 10 ** 6):
            top, sp, _ = self.rank(self.rows)
        self.assertTrue(top)
        for r in top:
            self.assertEqual(r["oosStatus"], "insufficient")
            self.assertTrue(r["oosInsufficient"])
            self.assertFalse(r["oos"]["pass"])
            self.assertIsNone(r["oosPass"])
            self.assertIsNone(r["oosPf"])

    def test_pass_requires_enough_trades_and_pf_above_one(self):
        with mock.patch.object(A, "OOS_MIN_TRADES", 1):
            top, sp, _ = self.rank(self.rows)
        for r in top:
            o = r["oos"]
            if r["oosStatus"] == "pass":
                self.assertGreater(o["pf"], 1); self.assertGreaterEqual(o["trades"], 1)
            elif r["oosStatus"] == "fail":
                self.assertTrue(o["pf"] <= 1 or o["trades"] < 1)

    def test_oos_trades_all_enter_after_boundary(self):
        # 交易依進場時間歸屬:用公開的 partition 直接驗證完整回測的結果
        res = S.run_backtest(self.rows, strategy="trend", timeframe="4h", **S.cost_kwargs("BTC/USDT"))
        ws = FIXED_NOW - datetime.timedelta(days=self.days)
        is_t, oos_t, carry, _ = A.partition_trades(res[2]["trade_log"], ws, self.split["boundary_dt"])
        self.assertTrue(all(t["entry_date"] >= self.split["boundary_dt"] for t in oos_t))
        self.assertTrue(all(t["exit_date"] < self.split["boundary_dt"] for t in is_t))
        self.assertTrue(all(t["entry_date"] < self.split["boundary_dt"] <= t["exit_date"] for t in carry))

    def test_warmup_bars_precede_the_window(self):
        # 窗口起點之前還有暖機資料;IS 統計只算窗口內進場的交易
        ws = FIXED_NOW - datetime.timedelta(days=self.days)
        self.assertLess(self.rows[0][0], ms(ws))
        top, sp, _ = self.rank(self.rows)
        res = S.run_backtest(self.rows[:self.split["idx_b"]], strategy=top[0]["strat"], timeframe="4h", **S.cost_kwargs("BTC/USDT"))
        before_window = [t for t in res[2]["trade_log"] if not t.get("open") and t["entry_date"] < ws]
        inside = [t for t in res[2]["trade_log"] if not t.get("open") and t["entry_date"] >= ws]
        self.assertEqual(top[0]["is"]["trades"], len(inside))
        self.assertTrue(len(before_window) >= 0)

    def test_quick_mode_has_no_oos(self):
        top, sp, _ = self.rank(self.rows, use_oos=False)
        self.assertIsNone(sp)
        for r in top:
            self.assertEqual(r["oosStatus"], "unavailable")
            self.assertIsNone(r["oos"]); self.assertFalse(r["oosIndependent"])
            self.assertEqual(r["full"], r["is"])

    def test_too_short_window_reports_no_oos_instead_of_faking_it(self):
        top, sp, _ = A.rank_strategies(self.rows, "BTC/USDT", "4h", self.pool, 1, 8, now_dt=FIXED_NOW, top_n=5)
        self.assertIsNone(sp)
        for r in top: self.assertEqual(r["oosStatus"], "unavailable")


class TestApiIsOos(unittest.TestCase):
    def setUp(self):
        self._patches = [
            mock.patch.object(A, "_utcnow", lambda: FIXED_NOW),
            mock.patch.object(A, "IS_RENDER", False),
            mock.patch.dict(S.STRATS, {k: v for k, v in S.STRATS.items() if k in SUBSET}, clear=True),
        ]
        for p in self._patches: p.start()
        self.client = A.app.test_client()

    def tearDown(self):
        for p in reversed(self._patches): p.stop()

    def _call(self, path, sym, tf, rows, **q):
        with mock.patch.object(A, "fetch_data", lambda s, start, interval="1d": rows):
            r = self.client.get(path, query_string=dict(symbol=sym, timeframe=tf, **q))
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()

    def _boundary_ms(self, days):
        ws = FIXED_NOW - datetime.timedelta(days=days)
        return ms(ws + (FIXED_NOW - ws) * 0.7)

    def test_best_strategy_api_structure_and_no_leak(self):
        rows = synth(5000, STEP["4h"], 3)
        j1 = self._call("/api/best_strategy", "BTC/USDT", "4h", rows, period="2y", use_oos="1")
        self.assertTrue(j1["oosAvailable"]); self.assertEqual(j1["split"]["mode"], "time")
        self.assertTrue(j1["results"])
        for r in j1["results"]:
            self.assertTrue({"is", "oos", "full", "oosStatus", "minOosTrades", "oosIndependent"} <= set(r))
            self.assertTrue(r["oosIndependent"])
            for k in ("pf", "total", "mdd", "win", "trades"):
                self.assertEqual(r[k], r["is"][k], "頂層數字 = 樣本內(IS)")
        rows2 = scramble_after(rows, self._boundary_ms(700), 5)
        j2 = self._call("/api/best_strategy", "BTC/USDT", "4h", rows2, period="2y", use_oos="1")
        self.assertEqual([r["strat"] for r in j1["results"]], [r["strat"] for r in j2["results"]])
        self.assertEqual([r["is"] for r in j1["results"]], [r["is"] for r in j2["results"]])

    def test_best_strategy_quick_mode(self):
        rows = synth(5000, STEP["4h"], 3)
        j = self._call("/api/best_strategy", "BTC/USDT", "4h", rows, period="2y", use_oos="0")
        self.assertFalse(j["oosAvailable"]); self.assertIsNone(j["split"])
        self.assertTrue(all(r["oosStatus"] == "unavailable" for r in j["results"]))

    def test_deep_analysis_crypto_uses_is_only_for_ranking(self):
        rows = synth(7000, STEP["4h"], 4)
        j1 = self._call("/api/deep_analysis", "BTC/USDT", "4h", rows, use_oos="1")
        self.assertTrue(j1["oosAvailable"]); self.assertTrue(j1["results"])
        self.assertTrue(all("in3y" not in r and "in5y" not in r for r in j1["results"]), "已移除巢狀窗口的欄位")
        for r in j1["results"]:
            self.assertEqual(r["trust"], 2 if r["oosStatus"] == "pass" else 1)
        scores = [r["score"] for r in j1["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True), "排序只看 IS 分數,不看 OOS/trust")
        rows2 = scramble_after(rows, self._boundary_ms(730), 8)
        j2 = self._call("/api/deep_analysis", "BTC/USDT", "4h", rows2, use_oos="1")
        self.assertEqual([r["strat"] for r in j1["results"]], [r["strat"] for r in j2["results"]])
        self.assertEqual([r["is"] for r in j1["results"]], [r["is"] for r in j2["results"]])

    def test_deep_analysis_daily_has_no_oos_gate(self):
        rows = synth(3500, STEP["1d"], 6)
        j = self._call("/api/deep_analysis", "2330.TW", "1d", rows, use_oos="1")
        self.assertTrue(j["oosAvailable"])
        # 以前 OOS PF<=1 的策略會被剔除;現在只是標註(可能出現 fail / insufficient)
        statuses = {r["oosStatus"] for r in j["results"]}
        self.assertTrue(statuses <= {"pass", "fail", "insufficient"})


if __name__ == "__main__":
    unittest.main()
