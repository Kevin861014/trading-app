# -*- coding: utf-8 -*-
"""Research Core 事件機制:事件必須來自真實工作;沒帶 job 就沒有任何事件/成本;加了事件不能改變任何分析結果。"""
import os, sys, time, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import research_events as R
from tests.test_ui_api import _Base

JOB = "job-test-0001"


def stages(evs, st=None):
    return [(e["stage"], e["status"]) for e in evs if st is None or e["status"] == st]


class TestStore(unittest.TestCase):
    def test_invalid_or_missing_ids_are_null_jobs(self):
        s = R.JobEvents()
        for bad in (None, "", "short", "has space!!", "x" * 80, "../../etc/passwd"):
            self.assertIs(s.begin(bad, "analyze"), R.NULL_JOB, bad)
        self.assertEqual(s.count(), 0)
        R.NULL_JOB.start("data"); R.NULL_JOB.done("data"); R.NULL_JOB.finish(True)     # 空操作,不丟例外

    def test_events_are_ordered_bounded_and_timed(self):
        s = R.JobEvents(); j = s.begin("abcdefgh1", "analyze", symbol="X")
        j.start("data"); time.sleep(0.02); j.done("data", bars=5)
        j.start("nonsense-stage"); j.progress("backtest", status_ok=True)
        out = s.get("abcdefgh1")
        self.assertEqual([e["seq"] for e in out["events"]], [1, 2, 3])                     # 未知階段被忽略
        self.assertGreaterEqual(out["events"][1]["ms"], 15)                                 # 耗時是量到的,不是編的
        self.assertEqual(s.get("abcdefgh1", after=2)["events"][0]["seq"], 3)
        for i in range(R.MAX_EVENTS + 50): j.progress("backtest", i=i)
        self.assertLessEqual(len(s.get("abcdefgh1")["events"]), R.MAX_EVENTS)

    def test_job_count_is_capped_and_expired_jobs_are_purged(self):
        s = R.JobEvents()
        for i in range(R.MAX_JOBS + 10): s.begin("job-%08d" % i, "analyze")
        self.assertLessEqual(s.count(), R.MAX_JOBS)
        with mock.patch.object(R, "TTL_SECONDS", -1): s.begin("job-fresh001", "analyze")
        self.assertLessEqual(s.count(), 2)
        self.assertIsNone(s.get("job-unknown1"))

    def test_module_has_no_background_machinery(self):
        src = open(R.__file__, encoding="utf-8").read()
        for needle in ("Thread(", "Timer(", "sleep(", "schedule", "asyncio", "setInterval"):
            self.assertNotIn(needle, src, needle)


class TestAnalyzeEvents(_Base):
    def _run(self, job=JOB, **kw):
        q = dict(symbol=self.SYMBOL, strategy="supertrend", period=self.PERIOD, timeframe=self.TF)
        if job: q["job"] = job
        r = self.client.get("/api/analyze", query_string=q)
        return r, (A.JOBS.get(job) if job else None)

    def test_analyze_emits_real_stage_events_in_order(self):
        r, ev = self._run()
        self.assertEqual(r.status_code, 200); self.assertEqual(ev["status"], "ok")
        done = [e["stage"] for e in ev["events"] if e["status"] == "done"]
        self.assertEqual(done, ["data", "backtest", "indicators", "signal", "validation", "summary"])
        for st in done:                                                                         # 每個階段都是先 start 再 done
            i0 = next(i for i, e in enumerate(ev["events"]) if e["stage"] == st and e["status"] == "start")
            i1 = next(i for i, e in enumerate(ev["events"]) if e["stage"] == st and e["status"] == "done")
            self.assertLess(i0, i1, st)
        ts = [e["t"] for e in ev["events"]]; self.assertEqual(ts, sorted(ts))
        self.assertTrue(all(e["ms"] >= 0 for e in ev["events"] if e["status"] == "done"))

    def test_event_numbers_equal_the_response(self):
        r, ev = self._run(); d = r.get_json()
        by = {e["stage"]: e for e in ev["events"] if e["status"] == "done"}
        self.assertEqual(by["data"]["bars"], d["dataInfo"]["bars"])
        self.assertEqual(by["indicators"]["bars"], len(d["prices"]))
        self.assertEqual(by["validation"]["oosTrades"], d["validation"]["oos"]["trades"])
        self.assertEqual(by["validation"]["tier"], d["validation"]["oos"]["tier"])
        self.assertEqual(by["summary"]["points"], len(d["backtest"]["equity"]))
        self.assertEqual(by["signal"]["inPos"], d["posState"]["inPos"])

    def test_events_never_change_the_analysis_result(self):
        with_job, _ = self._run(); without, _ = self._run(job=None)
        a, b = with_job.get_json(), without.get_json()
        self.assertEqual(a, b)

    def test_without_job_nothing_is_recorded(self):
        n = A.JOBS.count()
        self._run(job=None); self.client.get("/api/analyze", query_string=dict(symbol=self.SYMBOL, strategy="supertrend", period=self.PERIOD, timeframe=self.TF, job="bad id"))
        self.assertEqual(A.JOBS.count(), n)

    def test_data_failure_is_a_real_error_event(self):
        with mock.patch.object(A, "fetch_data", lambda *a, **k: []):
            r, ev = self._run(job="job-fail-0001")
        self.assertEqual(r.status_code, 400); self.assertEqual(ev["status"], "error")
        self.assertIn(("data", "error"), stages(ev["events"]))
        self.assertNotIn(("backtest", "start"), stages(ev["events"]))                           # 沒有下載到資料就不會有後面的工作

    def test_poll_endpoint(self):
        self._run()
        r = self.client.get("/api/job_events", query_string=dict(job=JOB, after=0)).get_json()
        self.assertEqual(r["status"], "ok"); n = r["lastSeq"]; self.assertGreater(n, 6)
        r2 = self.client.get("/api/job_events", query_string=dict(job=JOB, after=n)).get_json()
        self.assertEqual(r2["events"], [])
        self.assertEqual(self.client.get("/api/job_events", query_string=dict(job="nope-nope-1")).status_code, 404)
        self.assertEqual(self.client.get("/api/job_events").status_code, 404)


class TestRankingEvents(_Base):
    def _rank(self, ep="best_strategy", **kw):
        q = dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF, job="job-rank-0001"); q.update(kw)
        r = self.client.get("/api/" + ep, query_string=q)
        return r, A.JOBS.get(q["job"])

    def test_one_progress_event_per_strategy_and_per_oos_validation(self):
        r, ev = self._rank(); d = r.get_json()
        bt = [e for e in ev["events"] if e["stage"] == "backtest" and e["status"] == "progress"]
        self.assertEqual(len(bt), d["total_tested"])                                            # 每個策略都有一筆(真的跑過才有)
        self.assertEqual([e["i"] for e in bt], list(range(1, d["total_tested"] + 1)))
        self.assertTrue(all(e["ms"] >= 0 and e["n"] == d["total_tested"] for e in bt))
        done_bt = next(e for e in ev["events"] if e["stage"] == "backtest" and e["status"] == "done")
        self.assertEqual(done_bt["tested"], d["total_tested"])
        va = [e for e in ev["events"] if e["stage"] == "validation" and e["status"] == "progress"]
        self.assertEqual(len(va), len(d["results"]))
        self.assertEqual([e["oosTrades"] for e in va], [x["oosTrades"] for x in d["results"]])
        self.assertIn(("validation", "done"), stages(ev["events"]))
        self.assertIn(("data", "done"), stages(ev["events"]))
        for st in ("indicators", "signal", "summary"): self.assertIn((st, "skip"), stages(ev["events"]))

    def test_ranking_result_is_identical_with_and_without_events(self):
        a, _ = self._rank(); b = self.client.get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF)).get_json()
        self.assertEqual(a.get_json(), b)

    def test_no_oos_means_validation_is_skipped_not_faked(self):
        r, ev = self._rank(use_oos="0")
        self.assertIn(("validation", "skip"), stages(ev["events"]))
        self.assertFalse([e for e in ev["events"] if e["stage"] == "validation" and e["status"] in ("start", "progress", "done")])

    def test_deep_analysis_emits_events_too(self):
        r, ev = self._rank("deep_analysis", job="job-deep-0001")
        self.assertEqual(r.status_code, 200)
        self.assertTrue([e for e in ev["events"] if e["stage"] == "backtest" and e["status"] == "progress"])


if __name__ == "__main__":
    unittest.main()
