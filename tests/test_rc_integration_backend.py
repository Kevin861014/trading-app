# -*- coding: utf-8 -*-
"""Research Core 正式整合的後端保證:事件在工作『進行中』就能取得、各工作互不干擾、不為進度重跑或重下載、可取消、有清理。"""
import os, sys, threading, time, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import research_events as R
from tests.test_ui_api import _Base


def poll(client, job, after=0):
    return client.get("/api/job_events", query_string=dict(job=job, after=after)).get_json()


def pairs(evs):
    return [(e["stage"], e["status"]) for e in evs]


class TestStreamingWhileRunning(_Base):
    """用一個『卡住』的回測當作長時間工作:卡住的期間,輪詢端點必須已經拿得到前面完成的事件。"""

    def _blocked_run(self, job, block_at=3):
        orig = A.run_backtest; gate = threading.Event(); reached = threading.Event(); n = [0]
        def slow(*a, **k):
            n[0] += 1
            if n[0] == block_at: reached.set(); gate.wait(10)
            return orig(*a, **k)
        out = {}
        def worker():
            c = A.app.test_client()
            out["r"] = c.get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF, job=job))
        return slow, gate, reached, out, worker

    def test_events_arrive_while_the_work_is_still_running(self):
        slow, gate, reached, out, worker = self._blocked_run("job-stream-001")
        with mock.patch.object(A, "run_backtest", slow):
            th = threading.Thread(target=worker); th.start()
            self.assertTrue(reached.wait(10))
            mid = poll(self.client, "job-stream-001")
            self.assertEqual(mid["status"], "running")                                  # 工作還沒結束
            self.assertNotIn("r", out)                                                  # HTTP 回應也還沒回來
            prog = [e for e in mid["events"] if e["stage"] == "backtest" and e["status"] == "progress"]
            self.assertEqual([e["i"] for e in prog], [1, 2])                            # 前兩個策略的事件已可取得,第 3 個還沒有
            self.assertIn(("data", "done"), pairs(mid["events"]))
            gate.set(); th.join(10)
        end = poll(self.client, "job-stream-001", after=mid["lastSeq"])
        self.assertEqual(end["status"], "ok")
        self.assertTrue(end["events"] and end["events"][0]["seq"] == mid["lastSeq"] + 1)   # 只回傳新的事件
        self.assertEqual(out["r"].status_code, 200)

    def test_two_jobs_do_not_interfere(self):
        slow, gate, reached, out, worker = self._blocked_run("job-iso-aaaa1")
        with mock.patch.object(A, "run_backtest", slow):
            th = threading.Thread(target=worker); th.start(); self.assertTrue(reached.wait(10))
            r2 = self.client.get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF, job="job-iso-bbbb2"))
            self.assertEqual(r2.status_code, 200)
            a_mid = poll(self.client, "job-iso-aaaa1"); b = poll(self.client, "job-iso-bbbb2")
            self.assertEqual(a_mid["status"], "running"); self.assertEqual(b["status"], "ok")
            n_b = sum(1 for e in b["events"] if e["stage"] == "backtest" and e["status"] == "progress")
            self.assertEqual(n_b, r2.get_json()["total_tested"])
            # A 仍卡在第 3 個策略(只有 2 筆),B 的事件沒有混進來
            self.assertEqual(sum(1 for e in a_mid["events"] if e["stage"] == "backtest" and e["status"] == "progress"), 2)
            gate.set(); th.join(10)
        a_end = poll(self.client, "job-iso-aaaa1")
        self.assertEqual(sum(1 for e in a_end["events"] if e["stage"] == "backtest" and e["status"] == "progress"), r2.get_json()["total_tested"])
        self.assertEqual([e["seq"] for e in a_end["events"]], sorted({e["seq"] for e in a_end["events"]}))


class TestNoExtraWork(_Base):
    def _count(self, with_job):
        calls = {"bt": 0, "fetch": 0}; obt, ofe = A.run_backtest, A.fetch_data
        def bt(*a, **k): calls["bt"] += 1; return obt(*a, **k)
        def fe(*a, **k): calls["fetch"] += 1; return ofe(*a, **k)
        q = dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF)
        if with_job: q["job"] = "job-count-001"
        with mock.patch.object(A, "run_backtest", bt), mock.patch.object(A, "fetch_data", fe):
            r = self.client.get("/api/best_strategy", query_string=q)
        return calls, r.get_json()

    def test_progress_tracking_never_reruns_strategies_or_redownloads(self):
        c1, r1 = self._count(True); c0, r0 = self._count(False)
        self.assertEqual(c1, c0)                                   # 回測次數、下載次數完全相同
        self.assertEqual(c1["fetch"], 1)
        self.assertEqual(r1, r0)

    def test_poll_endpoint_does_no_analysis(self):
        self._count(True)
        with mock.patch.object(A, "run_backtest", side_effect=AssertionError("poll must not run strategies")), \
             mock.patch.object(A, "fetch_data", side_effect=AssertionError("poll must not download")):
            for _ in range(5): self.assertEqual(poll(self.client, "job-count-001")["status"], "ok")

    def test_deep_analysis_result_is_identical_with_and_without_events(self):
        q = dict(symbol=self.SYMBOL, timeframe=self.TF)
        a = self.client.get("/api/deep_analysis", query_string=dict(q, job="job-deepeq-01")).get_json()
        b = self.client.get("/api/deep_analysis", query_string=q).get_json()
        self.assertEqual(a, b)


class TestCancelAndCleanup(_Base):
    def test_cancel_stops_remaining_work_and_returns_no_partial_result(self):
        orig = A.run_backtest; n = [0]; started = threading.Event(); gate = threading.Event(); out = {}
        def slow(*a, **k):
            n[0] += 1
            if n[0] == 2: started.set(); gate.wait(10)
            return orig(*a, **k)
        def worker():
            out["r"] = A.app.test_client().get("/api/best_strategy", query_string=dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF, job="job-cancel-001"))
        with mock.patch.object(A, "run_backtest", slow):
            th = threading.Thread(target=worker); th.start(); self.assertTrue(started.wait(10))
            r = self.client.post("/api/job_cancel", query_string=dict(job="job-cancel-001")).get_json()
            self.assertEqual(r, {"ok": True, "found": True})
            gate.set(); th.join(10)
        self.assertEqual(out["r"].status_code, 499); self.assertTrue(out["r"].get_json()["cancelled"])
        self.assertLessEqual(n[0], 2)                               # 取消後沒有再跑任何策略
        j = poll(self.client, "job-cancel-001"); self.assertEqual(j["status"], "cancelled")
        self.assertNotIn(("validation", "start"), pairs(j["events"]))   # 沒有進到樣本外驗證

    def test_cancel_is_safe_for_unknown_finished_and_invalid_ids(self):
        for jid in ("nope-nope-1", "bad id!!", ""):
            self.assertEqual(self.client.post("/api/job_cancel", query_string=dict(job=jid)).get_json()["found"], False)
        self.client.get("/api/analyze", query_string=dict(symbol=self.SYMBOL, strategy="supertrend", period=self.PERIOD, timeframe=self.TF, job="job-done-0001"))
        self.assertFalse(self.client.post("/api/job_cancel", query_string=dict(job="job-done-0001")).get_json()["found"])
        self.assertEqual(poll(self.client, "job-done-0001")["status"], "ok")        # 已完成的不會被改成取消
        self.assertEqual(self.client.get("/api/job_cancel").status_code, 405)         # 只接受 POST

    def test_cancel_exception_is_not_swallowed_by_strategy_error_handlers(self):
        self.assertTrue(issubclass(R.JobCancelled, BaseException)); self.assertFalse(issubclass(R.JobCancelled, Exception))

    def test_cancelled_job_does_not_affect_next_normal_run(self):
        q = dict(symbol=self.SYMBOL, period=self.PERIOD, timeframe=self.TF)
        base = self.client.get("/api/best_strategy", query_string=q).get_json()
        j = A.JOBS.begin("job-pre-cancel1", "best"); j.cancelled = True            # 另一個被取消的舊工作
        again = self.client.get("/api/best_strategy", query_string=q).get_json()
        self.assertEqual(base, again)

    def test_finished_jobs_are_purged_quickly_running_ones_later(self):
        s = R.JobEvents(); a = s.begin("job-fin-00001", "analyze"); s.begin("job-run-00001", "analyze")
        a.finish(True)
        self.assertIsNotNone(s.get("job-fin-00001"))
        with mock.patch.object(R, "FINISHED_TTL_SECONDS", -1):
            self.assertIsNone(s.get("job-fin-00001"))                              # 已結束的工作很快就釋放
            self.assertIsNotNone(s.get("job-run-00001"))                           # 執行中的不會因為完成期限被清掉
        self.assertEqual(s.count(), 1)


if __name__ == "__main__":
    unittest.main()
