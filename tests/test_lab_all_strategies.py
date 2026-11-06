# -*- coding: utf-8 -*-
"""策略實驗室:全部策略分析結果(allStrategyResults / strategyStats)。固定種子的合成資料,不連網。
重點:新增欄位不改變原本的前 8 名(排序、分數、IS/OOS);每個候選策略都有明確狀態且數量合計正確;所有淘汰原因都保留(可重疊);
只有真的做過 OOS 的策略才有 OOS;回測無結果/例外會被如實標示,不洩漏例外訊息。"""
import json, os, sys, math, random, datetime, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app as A
import sim as S
from tests.test_oos_split import synth, FIXED_NOW, STEP, SUBSET

STATUSES = {"top", "passed", "filtered", "no_result", "error"}


def dump(o): return json.dumps(o, sort_keys=True, default=str, ensure_ascii=False)


class Base(unittest.TestCase):
    def setUp(self):
        self.rows = synth(5000, STEP["4h"], 3); self.days = 700; self.pool = set(SUBSET)
        p = mock.patch.dict(S.STRATS, {k: v for k, v in S.STRATS.items() if k in SUBSET}, clear=True); p.start(); self.addCleanup(p.stop)

    def rank(self, rows=None, collect=None, **kw):
        kw.setdefault("top_n", 8); mt = kw.pop("min_trades", 5)
        return A.rank_strategies(rows or self.rows, "BTC/USDT", "4h", self.pool, mt, self.days, now_dt=FIXED_NOW, collect=collect, **kw)


class TestCollectDoesNotChangeTheRanking(Base):
    def test_return_value_is_identical_with_and_without_collect(self):
        a = self.rank(); c = {}; b = self.rank(collect=c)
        self.assertEqual(dump(a), dump(b), "collect 只是多留資料,前 8 名、切分資訊、測試數都不能變")
        self.assertIn("allStrategyResults", c); self.assertIn("strategyStats", c)

    def test_top_results_keep_their_original_fields(self):
        top, _, _ = self.rank()
        self.assertGreaterEqual(len(top), 3)
        for r in top:
            for k in ("strat", "name", "cat", "score", "pf", "total", "mdd", "win", "trades", "is", "oos", "full", "oosStatus", "oosTier", "legacyTechPass"): self.assertIn(k, r)
            self.assertNotIn("reasons", r); self.assertNotIn("status", r)                  # 新欄位只在 allStrategyResults,不混進原本的結果


class TestEveryCandidateHasAnExplicitStatus(Base):
    def test_counts_add_up_and_agree_with_the_rows(self):
        c = {}; top, split, tested = self.rank(collect=c); rows, s = c["allStrategyResults"], c["strategyStats"]
        self.assertEqual(len(rows), tested); self.assertEqual(s["candidates"], tested)
        self.assertTrue(all(r["status"] in STATUSES for r in rows))
        cnt = lambda st: sum(1 for r in rows if r["status"] == st)
        self.assertEqual(s["candidates"], s["backtested"] + s["noResult"] + s["errors"])
        self.assertEqual(s["backtested"], s["passed"] + s["filtered"])
        self.assertEqual((s["top"], s["passedNotTop"]), (len(top), s["passed"] - len(top)))
        self.assertEqual((cnt("top"), cnt("passed"), cnt("filtered"), cnt("no_result"), cnt("error")), (s["top"], s["passedNotTop"], s["filtered"], s["noResult"], s["errors"]))
        self.assertEqual([r["strat"] for r in sorted((x for x in rows if x["status"] == "top"), key=lambda x: x["rank"])], [r["strat"] for r in top], "前 8 名的名次必須與原本排序一致")
        self.assertEqual({r["strat"] for r in rows}, {k for k in SUBSET if k in S.STRATS and k not in A.SCALPERS})

    def test_passed_rows_have_rank_and_score_and_filtered_do_not(self):
        c = {}; self.rank(collect=c)
        for r in c["allStrategyResults"]:
            if r["status"] in ("top", "passed"): self.assertTrue(r["rank"] >= 1 and r["score"] is not None and r["reasons"] == [], r["strat"])
            if r["status"] == "filtered": self.assertTrue(r["rank"] is None and r["score"] is None and r["reasons"], r["strat"])
        ranks = sorted(r["rank"] for r in c["allStrategyResults"] if r["rank"]); self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_is_numbers_match_the_ranking_for_every_passed_strategy(self):
        c = {}; top, _, _ = self.rank(collect=c, top_n=200); by = {r["strat"]: r for r in c["allStrategyResults"]}
        for r in top:
            for k in ("pf", "total", "mdd", "win", "trades", "cagr"): self.assertEqual(by[r["strat"]]["is"][k], r["is"][k], (r["strat"], k))
            self.assertEqual(by[r["strat"]]["score"], r["score"])


class TestAllFailureReasonsAreKept(Base):
    def test_multiple_reasons_are_recorded_together(self):
        c = {}; self.rank(collect=c, min_trades=10 ** 6)                                       # 筆數門檻設到不可能達成:每個策略都有 trades 原因
        rows = c["allStrategyResults"]; s = c["strategyStats"]
        self.assertTrue(all(r["status"] == "filtered" and "trades" in r["reasons"] for r in rows))
        both = [r for r in rows if "pf" in r["reasons"]]
        self.assertTrue(both, "合成資料裡要有 PF<=1 的策略,否則這個測試是空的"); self.assertTrue(all(len(r["reasons"]) >= 2 for r in both))
        self.assertEqual(s["multiReason"], sum(1 for r in rows if len(r["reasons"]) > 1))
        self.assertEqual(s["reasonCounts"]["trades"], len(rows)); self.assertGreater(s["multiReason"], 0)
        self.assertEqual(s["filtered"], len(rows)); self.assertEqual(s["passed"], 0)
        self.assertGreater(s["reasonCounts"]["pf"] + s["reasonCounts"]["trades"], s["filtered"], "原因會重疊,加總會大於未通過數(前端不可直接相加)")

    def test_reason_flags_follow_the_same_conditions_as_the_filter(self):
        c = {}; self.rank(collect=c, min_trades=20)
        for r in c["allStrategyResults"]:
            i = r["is"]
            if r["status"] == "filtered":
                self.assertEqual(set(r["reasons"]), {k for k, bad in (("pf", not i["pf"] > 1), ("trades", not i["trades"] >= 20), ("mdd", not i["mdd"] < 50)) if bad}, r["strat"])
            else: self.assertTrue(i["pf"] > 1 and i["trades"] >= 20 and i["mdd"] < 50, r["strat"])


class TestNoResultAndErrorsAreReportedHonestly(Base):
    def _run(self):
        orig = A.run_backtest
        def fake(rows, strategy=None, **k):
            if strategy == "vortex": return None
            if strategy == "cci": raise RuntimeError("secret path C:\\Users\\X\\token=abc123")
            return orig(rows, strategy=strategy, **k)
        c = {}
        with mock.patch.object(A, "run_backtest", fake): res = self.rank(collect=c)
        return res, c

    def test_statuses_counts_and_no_leak(self):
        (top, _, tested), c = self._run(); rows = {r["strat"]: r for r in c["allStrategyResults"]}; s = c["strategyStats"]
        self.assertEqual(rows["vortex"]["status"], "no_result"); self.assertEqual(rows["cci"]["status"], "error"); self.assertEqual(rows["cci"]["errorKind"], "RuntimeError")
        self.assertEqual((s["noResult"], s["errors"]), (1, 1)); self.assertEqual(s["candidates"], tested); self.assertEqual(s["candidates"], s["backtested"] + 2)
        self.assertTrue(rows["vortex"]["is"] is None and rows["cci"]["is"] is None)
        blob = dump(c); self.assertNotIn("secret", blob); self.assertNotIn("token", blob); self.assertNotIn("Traceback", blob); self.assertNotIn("C:\\\\", blob)
        self.assertTrue(all(r["strat"] not in ("vortex", "cci") for r in top))

    def test_the_rest_of_the_ranking_is_unaffected(self):
        base = self.rank(top_n=200)[0]; (top, _, _), _ = self._run(); only = [r for r in base if r["strat"] not in ("vortex", "cci")]
        self.assertEqual([(r["strat"], r["score"]) for r in only[:8]], [(r["strat"], r["score"]) for r in top])


class TestOosOnlyForTheTopEight(Base):
    def test_only_validated_strategies_have_oos(self):
        c = {}; top, split, _ = self.rank(collect=c); rows = c["allStrategyResults"]; s = c["strategyStats"]
        self.assertTrue(split); self.assertEqual(s["oos"]["attempted"], len(top))
        self.assertEqual(s["oos"]["pass"] + s["oos"]["fail"] + s["oos"]["insufficient"] + s["oos"]["unavailable"], len(top))
        top_names = {r["strat"] for r in top}
        for r in rows:
            if r["strat"] in top_names:
                self.assertTrue(r["oosDone"] and r["oos"] is not None and r["oos"]["status"] in ("pass", "fail", "insufficient"), r["strat"])
                o = next(t for t in top if t["strat"] == r["strat"])["oos"]; self.assertEqual((r["oos"]["trades"], r["oos"]["pf"], r["oos"]["total"]), (o["trades"], o["pf"], o["total"]))
            else: self.assertFalse(r["oosDone"]); self.assertIsNone(r["oos"], "沒做過樣本外驗證的策略不可以有 OOS 數字")

    def test_no_oos_when_not_requested_or_data_too_short(self):
        c = {}; self.rank(collect=c, use_oos=False); s = c["strategyStats"]["oos"]
        self.assertEqual((s["available"], s["attempted"]), (False, 0)); self.assertTrue(s["skipReason"])
        self.assertFalse(any(r["oosDone"] or r["oos"] for r in c["allStrategyResults"]))
        c2 = {}; A.rank_strategies(synth(300, STEP["4h"], 5), "BTC/USDT", "4h", self.pool, 1, self.days, now_dt=FIXED_NOW, collect=c2)        # 只有約 50 天的資料,切不出樣本外
        self.assertFalse(c2["strategyStats"]["oos"]["available"]); self.assertFalse(any(r["oosDone"] for r in c2["allStrategyResults"]))


class TestEndpointResponse(unittest.TestCase):
    def setUp(self):
        self.rows = synth(6000, STEP["4h"], 11)
        for p in (mock.patch.dict(S.STRATS, {k: v for k, v in S.STRATS.items() if k in SUBSET}, clear=True), mock.patch.object(A, "strategy_pool", lambda *a, **k: set(SUBSET)),
                  mock.patch.object(A, "fetch_data", lambda *a, **k: self.rows), mock.patch.object(A, "_utcnow", lambda: FIXED_NOW), mock.patch.object(A, "CCXT_AVAILABLE", True)):
            p.start(); self.addCleanup(p.stop)
        A._cache.clear(); self.client = A.app.test_client()

    def deep(self, job=None):
        q = dict(symbol="BTC/USDT", timeframe="4h", use_oos=1)
        if job: q["job"] = job
        return self.client.get("/api/deep_analysis", query_string=q)

    def test_deep_response_has_the_new_fields_and_unchanged_top(self):
        r = self.deep(); self.assertEqual(r.status_code, 200); d = r.get_json()
        self.assertEqual(len(d["allStrategyResults"]), d["total_tested"]); s = d["strategyStats"]
        self.assertEqual(s["candidates"], d["total_tested"]); self.assertEqual(s["top"], len(d["results"]))
        self.assertEqual([x["strat"] for x in d["results"]], [x["strat"] for x in sorted((y for y in d["allStrategyResults"] if y["status"] == "top"), key=lambda y: y["rank"])])
        for k in ("results", "total_tested", "split", "oosAvailable", "hasOos", "isDeep", "isCrypto", "dataQuality"): self.assertIn(k, d)
        self.assertTrue(all("trust" in x for x in d["results"]))

    def test_best_strategy_response_is_unchanged(self):
        d = self.client.get("/api/best_strategy", query_string=dict(symbol="BTC/USDT", period="2y", timeframe="4h", use_oos=1)).get_json()
        self.assertNotIn("allStrategyResults", d); self.assertNotIn("strategyStats", d); self.assertIn("results", d)

    def test_progress_events_carry_outcome_and_match_the_stats(self):
        d = self.deep("job-lab-all-001").get_json(); s = d["strategyStats"]
        ev = self.client.get("/api/job_events", query_string=dict(job="job-lab-all-001")).get_json()["events"]
        st = next(e for e in ev if e["stage"] == "backtest" and e["status"] == "start")
        self.assertEqual((st["pfAbove"], st["minTrades"], st["mddBelow"], st["topN"]), (1.0, s["thresholds"]["minTrades"], 50.0, 8)); self.assertEqual(s["thresholds"]["minTrades"], 15)
        prog = [e for e in ev if e["stage"] == "backtest" and e["status"] == "progress"]; self.assertEqual(len(prog), s["candidates"])
        out = lambda o: sum(1 for e in prog if e["outcome"] == o)
        self.assertEqual((out("kept"), out("filtered"), out("no_result"), out("error")), (s["passed"], s["filtered"], s["noResult"], s["errors"]))
        why = lambda c: sum(1 for e in prog if c in e["why"].split(","))
        self.assertEqual({c: why(c) for c in ("pf", "trades", "mdd")}, s["reasonCounts"]); self.assertEqual(sum(1 for e in prog if len(e["why"].split(",")) > 1 and e["why"]), s["multiReason"])
        done = next(e for e in ev if e["stage"] == "backtest" and e["status"] == "done"); self.assertEqual((done["tested"], done["kept"]), (s["candidates"], s["passed"]))
        data_done = next(e for e in ev if e["stage"] == "data" and e["status"] == "done"); self.assertTrue(data_done["firstBar"] and data_done["lastBar"] and data_done["bars"] == len(self.rows))

    def test_partial_failure_is_visible_in_the_response(self):
        orig = A.run_backtest
        def fake(rows, strategy=None, **k):
            if strategy == "cci": raise ValueError("boom with /etc/passwd")
            if strategy == "vortex": return None
            return orig(rows, strategy=strategy, **k)
        with mock.patch.object(A, "run_backtest", fake): r = self.deep(); d = r.get_json()
        self.assertEqual(r.status_code, 200); s = d["strategyStats"]
        self.assertEqual((s["noResult"], s["errors"]), (1, 1)); self.assertLess(s["backtested"], s["candidates"], "前端要能看出不是全部都成功")
        self.assertNotIn("/etc/passwd", json.dumps(d)); self.assertNotIn("boom", json.dumps(d))


class TestFrontendStaticGuarantees(unittest.TestCase):
    def rd(self, rel):
        with open(os.path.join(ROOT, "static", rel), encoding="utf-8") as f: return f.read()

    def test_all_five_statuses_and_the_no_oos_wording_exist(self):
        js = self.rd("js/65-research-lab.js")
        for s in ("前 8 名", "通過但未進前 8", "未通過篩選", "回測無結果", "回測發生錯誤", "未進行樣本外驗證"): self.assertIn(s, js)
        for f in ("search", "labAllSet", "per: 20", "上一頁", "下一頁"): self.assertIn(f, js)
        self.assertIn("allStrategyResults", js); self.assertIn("strategyStats", js)

    def test_ranking_table_states_that_oos_does_not_affect_the_ranking(self):
        self.assertIn("排名依樣本內結果產生，樣本外資料用於驗證，不參與策略排名。", self.rd("js/50-analysis.js"))

    def test_the_six_blocks_are_summaries_not_executed_stages(self):
        js = self.rd("js/65-research-lab.js")
        self.assertIn("不是六個運算階段", js.replace("是『資訊摘要』,不是六個運算階段", "不是六個運算階段"))
        for needle in ("指標計算", "訊號判斷", "風險與成本"): self.assertNotIn(needle, js.split("const labState")[1].split("// ══════")[0].replace("指標計算、訊號判斷、風險與成本在這個流程不會執行", ""))
        self.assertNotIn("setInterval", js)

    def test_engine_and_job_model_files_are_untouched_by_this_change(self):
        import subprocess
        out = subprocess.run(["git", "diff", "--stat", "HEAD", "--", "static/js/rc-engine.js", "static/js/rc-job.js"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "", "動畫引擎與事件模型不得修改")


if __name__ == "__main__":
    unittest.main()
