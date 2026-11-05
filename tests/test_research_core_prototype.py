# -*- coding: utf-8 -*-
"""Research Core v2 原型的『誠實性』檢查:不能有示範輪播、計時器假進度;錄製的紀錄必須是合法的真實事件。"""
import json, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import research_events as R

PROTO = os.path.join(ROOT, "static", "prototype")


def read(name):
    with open(os.path.join(PROTO, name), encoding="utf-8") as f: return f.read()


def strip_comments(js):
    return re.sub(r"(^|\s)//[^\n]*", " ", re.sub(r"/\*.*?\*/", "", js, flags=re.S))


def read_js(name):
    with open(os.path.join(ROOT, "static", "js", name), encoding="utf-8") as f: return f.read()


class TestHonestVisuals(unittest.TestCase):
    """原型頁與正式網站共用 rc-job.js / rc-engine.js;誠實性檢查涵蓋這三個檔案。"""
    FILES = (("proto", "research-core-v2.js"), ("job", "rc-job.js"), ("engine", "rc-engine.js"))

    def code(self, which):
        return strip_comments(read("research-core-v2.js") if which == "proto" else read_js(dict(self.FILES)[which]))

    def test_no_demo_loop_or_fake_progress(self):
        for which, _ in self.FILES:
            js = self.code(which)
            self.assertNotIn("setInterval", js, which)                            # 沒有週期性計時器驅動的進度
            self.assertNotRegex(js, r"simulate|demo|DEMO|fake|假資料", which)        # 沒有示範/模擬入口
        # Math.random 只能用在產生 job 代號的備援(rc-job.js 一處);不能用於動畫、進度或事件
        self.assertEqual(len(re.findall(r"Math\.random", self.code("job"))), 1)
        j = self.code("job"); self.assertIn("newJobId", j[j.index("Math.random") - 500: j.index("Math.random") + 100])
        self.assertNotIn("Math.random", self.code("engine")); self.assertNotIn("Math.random", self.code("proto"))

    def test_events_have_only_two_sources_in_the_prototype(self):
        js = self.code("proto")
        self.assertIn("RC_TRACES", js); self.assertIn("J.run(", js)               # 即時(RCJob.run 輪詢真實事件)與重播(錄製的真實紀錄)
        self.assertEqual(len(re.findall(r"core[.]event[(]", js)), 1)                 # 畫面只經 onEvent 取得事件(只有 onEvent 呼叫 core.event)
        self.assertIn("/api/job_events", self.code("job"))

    def test_stages_match_backend(self):
        ids = re.findall(r"\{ id: '(\w+)',\s+label", read_js("rc-job.js"))
        self.assertEqual(tuple(ids), R.STAGES)

    def test_loop_guards_present(self):
        js = read_js("rc-engine.js")
        for needle in ("prefers-reduced-motion", "visibilitychange", "IntersectionObserver", "max-width: 720px", "lowPower", "saveData"):
            self.assertIn(needle, js, needle)

    def test_ambient_rotation_is_opt_in_and_idle_has_no_loop(self):
        js = self.code("engine")
        self.assertIn("store('rcAmbient') === '1'", js)                           # 裝飾旋轉預設關閉,只有明確開啟過才為真
        self.assertRegex(js, r"function wantLoop\(\)[^}]*working\(\) \|\| eventsFlowing\(\) \|\| ambientOn")   # 迴圈只在:工作中/事件流動中/使用者開啟裝飾
        self.assertRegex(js, r"function stopLoop\(\)")

    def test_prototype_pages_use_relative_paths(self):                       # 雙擊 html 檔(file://)也要能運作
        for name in ("research-core.html", "research-core-v2.html"):
            h = read(name)
            for m in re.findall(r'(?:src|href)="([^"]+)"', h): self.assertFalse(m.startswith("/"), (name, m))


class TestRecordedTraces(unittest.TestCase):
    def setUp(self):
        txt = read("traces/traces.js"); body = txt[txt.index("window.RC_TRACES = ") + len("window.RC_TRACES = "):].rstrip().rstrip(";")
        self.traces = json.loads(body)

    def test_traces_are_valid_real_event_streams(self):
        self.assertGreaterEqual(len(self.traces), 3)
        for key, tr in self.traces.items():
            ev = tr["events"]; self.assertTrue(ev, key)
            self.assertEqual([e["seq"] for e in ev], sorted({e["seq"] for e in ev}), key)
            self.assertEqual([e["t"] for e in ev], sorted(e["t"] for e in ev), key)
            for e in ev:
                self.assertIn(e["stage"], R.STAGES); self.assertIn(e["status"], R.STATUSES)
                if e["status"] == "done": self.assertIn("ms", e, (key, e))     # 完成事件一定帶實測耗時
            self.assertEqual((ev[0]["stage"], ev[0]["status"]), ("data", "start"), key)
            self.assertIn("recordedAt", tr["meta"]); self.assertIn("summary", tr["result"])

    def test_ranking_trace_has_one_progress_event_per_strategy(self):
        tr = next(v for k, v in self.traces.items() if k.startswith("best"))
        prog = [e for e in tr["events"] if e["stage"] == "backtest" and e["status"] == "progress"]
        done = next(e for e in tr["events"] if e["stage"] == "backtest" and e["status"] == "done")
        self.assertEqual(len(prog), done["tested"]); self.assertEqual([e["i"] for e in prog], list(range(1, done["tested"] + 1)))

    def test_error_trace_stops_at_the_failing_stage(self):
        tr = next(v for k, v in self.traces.items() if k.startswith("error"))
        self.assertEqual([(e["stage"], e["status"]) for e in tr["events"]], [("data", "start"), ("data", "error")])
        self.assertFalse(tr["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
