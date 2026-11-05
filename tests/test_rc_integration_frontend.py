# -*- coding: utf-8 -*-
"""Research Core 正式整合的前端靜態保證(不需要瀏覽器):
假進度已移除、請求只多一個 job 參數、整站只有一個球體、重播不在正式網站、階段與分級用語與後端一致。"""
import os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import research_events as R

STATIC = os.path.join(ROOT, "static")


def rd(rel):
    with open(os.path.join(STATIC, rel), encoding="utf-8") as f: return f.read()


def code(rel):
    return re.sub(r"(^|\s)//[^\n]*", " ", re.sub(r"/\*.*?\*/", "", rd(rel), flags=re.S))


SITE_JS = sorted(f for f in os.listdir(os.path.join(STATIC, "js")) if f.endswith(".js"))


def flow_source():
    s = rd("js/50-analysis.js"); a = s.index("async function rankingFlow"); b = s.index("let modalHandle")
    return s[a:b]


class TestFakeProgressRemoved(unittest.TestCase):
    def test_ranking_flow_has_no_time_based_progress(self):
        src = flow_source()
        for needle in ("setInterval", "Math.min(prog", "setProgress", "約需", "step *", "(100 - prog)"):
            self.assertNotIn(needle, src, needle)
        self.assertIn("RCJob.run(", src)

    def test_no_setinterval_in_any_site_script(self):
        for f in SITE_JS: self.assertNotIn("setInterval", code("js/" + f), f)

    def test_old_progress_elements_are_gone(self):
        h = rd("index.html")
        for needle in ('id="progressBar"', 'id="progressText"', "progress-text"):
            self.assertNotIn(needle, h, needle)
        for f in SITE_JS: self.assertNotIn("progressBar", code("js/" + f), f)

    def test_percentage_comes_only_from_backend_counts(self):
        js = code("js/rc-job.js")
        self.assertIn("c.i / c.n", js)                                              # 比例 = 事件裡的 i / n
        self.assertRegex(js, r"處理中.{0,120}indet")                                  # 不知道比例 → 『處理中』+ 不定長度條,不編百分比
        self.assertNotRegex(js, r"Math\.(min|max)\(\s*\w*[Pp]rog")


class TestRequestsAreUnchangedExceptJobId(unittest.TestCase):
    def test_urls_equal_legacy_urls_plus_job_param(self):
        src = flow_source()
        urls = re.findall(r"`(/api/(?:deep_analysis|best_strategy)\?[^`]*)`", src)
        self.assertEqual(len(urls), 2)
        legacy = {
            "deep_analysis": "/api/deep_analysis?symbol=${encodeURIComponent(ctx.symbol)}&timeframe=${ctx.tf}&use_oos=${useOos?1:0}",
            "best_strategy": "/api/best_strategy?symbol=${encodeURIComponent(ctx.symbol)}&period=${ctx.period}&timeframe=${ctx.tf}&use_oos=${useOos?1:0}",
        }
        for u in urls:
            self.assertTrue(u.endswith("&job=${jobId}"), u)
            base = u[: -len("&job=${jobId}")]
            self.assertIn(base, legacy.values())

    def test_no_extra_data_or_analysis_calls_for_progress(self):
        js = code("js/rc-job.js") + code("js/rc-engine.js") + code("js/65-research-lab.js")
        calls = set(re.findall(r"/api/[a-z_]+", js))
        self.assertEqual(calls, {"/api/job_events", "/api/job_cancel"})              # 進度追蹤只碰這兩個不做運算的端點
        self.assertNotIn("/api/analyze", js); self.assertNotIn("/api/best_strategy", js)

    def test_polling_stops_and_is_bounded(self):
        js = code("js/rc-job.js")
        for needle in ("MAX_POLL_MS", "fails >= 5", "clearTimeout(timer)", "delete active[id]", "pagehide", "sendBeacon", "document.hidden"):
            self.assertIn(needle, js, needle)
        self.assertRegex(js, r"interval = evs\.length \? 300 : Math\.min\(1000")       # 有事件 300ms,沒事件逐步放慢到 1 秒


class TestOnlyOneCoreAndNoReplay(unittest.TestCase):
    def test_exactly_one_sphere_in_the_whole_site(self):
        uses = {f: len(re.findall(r"RCEngine\.create\(", code("js/" + f))) for f in SITE_JS}
        self.assertEqual({f: n for f, n in uses.items() if n}, {"65-research-lab.js": 1})
        self.assertEqual(rd("index.html").count('id="labCore"'), 0)                  # 球體容器由實驗室程式在實驗室視圖內建立
        self.assertIn("view-lab", rd("index.html"))
        for f in ("10-cards.js", "30-render-search.js", "50-analysis.js", "40-signals-nav.js"):
            self.assertNotIn("RCEngine", code("js/" + f), f)                         # 卡片、彈窗不渲染球體

    def test_replay_and_traces_are_not_in_the_site(self):
        blob = rd("index.html") + "".join(code("js/" + f) for f in SITE_JS)
        for needle in ("RC_TRACES", "traces.js", "/static/prototype", "startReplay", "重播"):
            self.assertNotIn(needle, blob, needle)
        files = [os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(STATIC, "js")) for f in fs]
        self.assertFalse([f for f in files if "trace" in f.lower() or "replay" in f.lower()])
        self.assertTrue(os.path.exists(os.path.join(STATIC, "prototype", "traces", "traces.js")))   # 只存在於獨立原型

    def test_prototype_is_not_linked_from_site_navigation(self):
        for f in ["index.html"] + ["js/" + x for x in SITE_JS]:
            self.assertNotIn("research-core-v2.html", rd(f), f)

    def test_engine_has_no_simulation_inputs(self):
        js = code("js/rc-engine.js")
        for needle in ("RC_TRACES", "simulate", "fake", "replay"):
            self.assertNotIn(needle, js, needle)
        self.assertEqual(len(re.findall(r"\bevent\s*\(", js)), len(re.findall(r"\bevent\s*\(", js)))


class TestConsistencyWithBackend(unittest.TestCase):
    def test_stage_ids_and_order_match_backend(self):
        ids = re.findall(r"\{ id: '(\w+)',\s+label", rd("js/rc-job.js"))
        self.assertEqual(tuple(ids), R.STAGES)

    def test_tier_labels_match_the_site_helpers(self):
        a = dict(re.findall(r"(\w+): '([^']+)'", re.search(r"TIER_LABEL = \{([^}]*)\}", rd("js/rc-job.js")).group(1)))
        b = dict(re.findall(r"(\w+):'([^']+)'", re.search(r"TIER_LABEL = \{([^}]*)\}", rd("js/05-ui-helpers.js")).group(1)))
        self.assertEqual(a, b)

    def test_stage_details_use_only_events_and_api_results(self):
        js = code("js/rc-job.js")
        self.assertIn("function stageDetail(stageId, model, data)", js)
        self.assertNotRegex(js, r"fetch\([^)]*analyze")                              # 詳情不另外呼叫分析 API
        self.assertIn("esc(", js)                                                    # 事件/回應文字一律跳脫後才進 HTML

    def test_lab_panel_is_in_lab_view_only(self):
        self.assertIn("labEnsure();", rd("js/60-views.js"))
        self.assertIn("rankingFlow('deep', 'lab', ctx, labUi())", rd("js/60-views.js"))
        self.assertIn("rankingFlow('best', 'best', ctx, viewUi(", rd("js/60-views.js"))     # 最佳策略頁只有進度列,沒有球體


class TestCancelWiring(unittest.TestCase):
    def test_closing_the_modal_cancels_the_running_job(self):
        s = rd("js/50-analysis.js")
        self.assertIn("function cancelModalJob()", s)
        self.assertGreaterEqual(s.count("cancelModalJob()"), 3)                      # 定義 + 關閉按鈕 + Esc

    def test_progress_view_has_a_cancel_button(self):
        js = rd("js/rc-job.js"); self.assertIn("rcp-cancel", js); self.assertIn("handle.cancel()", js)


if __name__ == "__main__":
    unittest.main()
