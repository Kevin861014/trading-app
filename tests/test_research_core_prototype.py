# -*- coding: utf-8 -*-
"""Research Core v2 原型的『誠實性』檢查:不能有示範輪播、計時器假進度;錄製的紀錄必須是合法的真實事件。"""
import json, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import research_events as R

PROTO = os.path.join(ROOT, "static", "prototype")


def read(name):
    with open(os.path.join(PROTO, name), encoding="utf-8") as f: return f.read()


class TestHonestVisuals(unittest.TestCase):
    def test_no_demo_loop_or_fake_progress_in_v2(self):
        js = re.sub(r"(^|\s)//[^\n]*", " ", re.sub(r"/\*.*?\*/", "", read("research-core-v2.js"), flags=re.S))   # code only, comments stripped
        self.assertNotIn("setInterval", js)                                  # 沒有週期性計時器驅動的進度
        self.assertNotRegex(js, r"simulate|demo|DEMO|fake|假資料")             # 沒有示範/模擬入口
        # Math.random 只能用在產生 job 代號的備援;不能用於動畫、進度或事件
        self.assertEqual(len(re.findall(r"Math\.random", js)), 1)
        self.assertIn("newJobId", js[js.index("Math.random") - 400: js.index("Math.random") + 100])
        # 事件只來自兩個管道:即時輪詢 job_events、重播錄製的真實紀錄
        self.assertEqual(sorted(set(re.findall(r"applyEvent\(", js))) and 1, 1)
        self.assertIn("/api/job_events", js); self.assertIn("RC_TRACES", js)

    def test_stages_match_backend(self):
        js = read("research-core-v2.js")
        ids = re.findall(r"\{ id: '(\w+)',\s+label", js)
        self.assertEqual(tuple(ids), R.STAGES)

    def test_loop_guards_present(self):
        js = read("research-core-v2.js")
        for needle in ("prefers-reduced-motion", "visibilitychange", "IntersectionObserver", "max-width: 720px", "lowPower"):
            self.assertIn(needle, js, needle)

    def test_prototype_is_not_linked_from_the_main_site(self):
        for rel in ("static/index.html",) + tuple("static/js/" + f for f in os.listdir(os.path.join(ROOT, "static/js"))):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f: self.assertNotIn("research-core", f.read(), rel)

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
