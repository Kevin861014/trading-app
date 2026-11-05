# -*- coding: utf-8 -*-
"""階段三 B1:UI 新增的欄位(dataInfo / validation / backtest / oosTier)必須和既有指標一致,
而且不能改變回測、排名或 OOS 判定本身。資料用固定種子的合成資料,不連網。"""
import os, sys, math, random, time, datetime, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import sim as S
from tests.test_api_consistency import synth, STEP, SUBSET


class _Base(unittest.TestCase):
    SYMBOL, TF, PERIOD = "2330.TW", "1d", "1y"

    def setUp(self):
        self.rows = synth(1500, STEP[self.TF], 5)
        self.now = datetime.datetime.utcfromtimestamp(self.rows[-1][0] / 1000.0) + datetime.timedelta(seconds=STEP[self.TF] / 1000.0)
        self._patches = [
            mock.patch.object(A, "fetch_data", lambda sym, start, interval="1d": self.rows),
            mock.patch.dict(S.STRATS, {k: v for k, v in S.STRATS.items() if k in SUBSET}, clear=True),
            mock.patch.object(A, "IS_RENDER", False),
            mock.patch.object(A, "_utcnow", lambda: self.now),
        ]
        for p in self._patches: p.start()
        self.client = A.app.test_client()

    def tearDown(self):
        for p in reversed(self._patches): p.stop()

    def analyze(self, strat="supertrend", sym=None, tf=None, period=None):
        r = self.client.get("/api/analyze", query_string=dict(symbol=sym or self.SYMBOL, strategy=strat, period=period or self.PERIOD, timeframe=tf or self.TF))
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()


class TestTierBoundaries(unittest.TestCase):
    def test_tier_thresholds(self):
        for n, t in [(0, "insufficient"), (1, "insufficient"), (19, "insufficient"), (20, "preliminary"), (49, "preliminary"), (50, "evaluable"), (500, "evaluable")]:
            self.assertEqual(A.oos_tier(n), t, n)
        self.assertEqual((A.OOS_TIER_PRELIM, A.OOS_TIER_EVAL), (20, 50))

    def test_tier_is_not_the_legacy_verdict(self):
        # 舊技術門檻(>=5 筆且 PF>1)與展示分級是兩件事:7 筆、PF 2 → 舊門檻達成,但分級仍是『樣本不足』
        insufficient, passed = A.oos_verdict(7, 2.0)
        self.assertFalse(insufficient); self.assertTrue(passed)
        self.assertEqual(A.oos_tier(7), "insufficient")
        insufficient, passed = A.oos_verdict(4, 9.0)      # 筆數少於 5 → 不能算通過
        self.assertTrue(insufficient); self.assertFalse(passed)


class TestAnalyzeExtras(_Base):
    def test_new_blocks_present_and_consistent_with_metrics(self):
        d = self.analyze()
        self.assertNotIn("extrasError", d)
        for k in ("dataInfo", "validation", "backtest"):
            self.assertIn(k, d)
        m, bt = d["metrics"], d["backtest"]
        self.assertTrue(bt["available"])
        # 權益曲線最後一點 = 卡片上的總報酬;回撤最低點 = 最大回撤(同一個切法)
        self.assertAlmostEqual(bt["equity"][-1][1], m["totalReturn"], delta=0.02)
        self.assertAlmostEqual(bt["summary"]["strategyTotal"], m["totalReturn"], delta=0.02)
        self.assertAlmostEqual(-min(v for _, v in bt["drawdown"]), m["maxDD"], delta=0.02)
        self.assertAlmostEqual(bt["summary"]["strategyMaxDD"], m["maxDD"], delta=0.02)
        self.assertEqual(bt["period"]["trades"], m["tradeCount"])
        # 時間為嚴格遞增的 epoch 秒
        ts = [t for t, _ in bt["equity"]]
        self.assertEqual(ts, sorted(set(ts)))
        self.assertLessEqual(len(bt["equity"]), 300 + 1)

    def test_cost_block_matches_cost_kwargs(self):
        for sym, tf in (("2330.TW", "1d"), ("AAPL", "1d"), ("BTC-USD", "1d")):
            d = self.analyze(sym=sym, tf=tf)
            ck = S.cost_kwargs(sym, "supertrend")
            exp = (2 * (ck["commission"] + ck["slippage"]) + ck["sell_tax"]) * 100
            self.assertAlmostEqual(d["backtest"]["cost"]["roundTripPct"], exp, places=3, msg=sym)
            self.assertEqual(d["backtest"]["cost"]["sellTax"] > 0, sym.endswith(".TW"), sym)

    def test_data_info_describes_the_last_closed_bar(self):
        d = self.analyze()
        di = d["dataInfo"]
        self.assertTrue(di["lastBarClosed"])
        self.assertEqual(di["lastBarUtc"], datetime.datetime.utcfromtimestamp(self.rows[-1][0] / 1000.0).strftime("%Y-%m-%d"))
        self.assertEqual(di["market"], "tw"); self.assertEqual(di["tz"], "Asia/Taipei")
        self.assertEqual(self.analyze(sym="AAPL")["dataInfo"]["tz"], "America/New_York")

    def test_validation_matches_best_strategy_oos(self):
        r = self.client.get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF)).get_json()
        self.assertTrue(r["results"], "合成資料下排名應有結果")
        top = r["results"][0]
        d = self.analyze(strat=top["strat"])
        v = d["validation"]
        self.assertTrue(v["available"])
        self.assertEqual(v["split"]["boundary"], r["split"]["boundary"])
        self.assertEqual(v["split"]["windowStart"], r["split"]["windowStart"])
        self.assertEqual(v["split"]["end"], r["split"]["end"])
        o = top["oos"]
        self.assertEqual(v["oos"]["trades"], o["trades"])
        self.assertAlmostEqual(v["oos"]["total"], o["total"], places=2)
        self.assertAlmostEqual(v["oos"]["pf"], o["pf"], places=2)
        self.assertEqual(v["oos"]["tier"], top["oosTier"])
        self.assertEqual(v["legacyTechPass"], top["legacyTechPass"])
        self.assertEqual(v["is"]["trades"], top["is"]["trades"])

    def test_extras_failure_never_breaks_core_response(self):
        base = self.analyze()
        with mock.patch.object(A, "build_validation", side_effect=RuntimeError("boom")):
            d = self.analyze()
        self.assertIn("extrasError", d)
        self.assertNotIn("backtest", d)
        for k in ("metrics", "dates", "prices", "buyPoints", "sellPoints", "posState"):
            self.assertEqual(d[k], base[k], k)

    def test_extras_do_not_change_existing_fields(self):
        d = self.analyze()
        with mock.patch.object(A, "build_data_info", side_effect=RuntimeError("x")):
            plain = self.analyze()
        for k in ("metrics", "dates", "prices", "ema20", "ema50", "buyPoints", "sellPoints", "posState", "diff"):
            self.assertEqual(d[k], plain[k], k)


class TestRankingAnnotations(_Base):
    def _rank(self):
        r = self.client.get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF))
        self.assertEqual(r.status_code, 200); return r.get_json()

    def test_every_result_carries_tier_and_legacy_flag(self):
        r = self._rank()
        self.assertTrue(r["results"])
        self.assertEqual(r["split"]["tierThresholds"], {"preliminary": 20, "evaluable": 50})
        for x in r["results"]:
            self.assertEqual(x["oosTier"], A.oos_tier(x["oos"]["trades"]))
            self.assertEqual(x["legacyTechPass"], x["oos"]["pass"])
            self.assertEqual(x["oos"]["tier"], x["oosTier"])

    def test_tier_thresholds_never_influence_ranking(self):
        a = [(x["strat"], x["score"]) for x in self._rank()["results"]]
        with mock.patch.object(A, "OOS_TIER_PRELIM", 1), mock.patch.object(A, "OOS_TIER_EVAL", 2):
            b = [(x["strat"], x["score"]) for x in self._rank()["results"]]
        self.assertEqual(a, b)

    def test_without_oos_results_are_marked_unavailable(self):
        r = self.client.get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF, use_oos="0")).get_json()
        for x in r["results"]:
            self.assertEqual(x["oosTier"], "unavailable"); self.assertIsNone(x["legacyTechPass"])


class TestDownsample(unittest.TestCase):
    def test_keeps_endpoints_and_caps_length(self):
        seq = [[i, float(i)] for i in range(1000)]
        out = A._downsample(seq, 300)
        self.assertLessEqual(len(out), 301)
        self.assertEqual(out[0], seq[0]); self.assertEqual(out[-1], seq[-1])
        self.assertEqual([x[0] for x in out], sorted(x[0] for x in out))
        short = [[1, 1.0], [2, 2.0]]
        self.assertEqual(A._downsample(short, 300), short)


if __name__ == "__main__":
    unittest.main()
