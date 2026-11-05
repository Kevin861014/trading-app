# -*- coding: utf-8 -*-
"""C1 前端靜態保證:多週期畫面只描述不預測、過期資料不顯示成最新訊號、狀態用語與後端一致、不為畫面多打 API。"""
import os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import data_quality as DQ

STATIC = os.path.join(ROOT, "static")


def rd(rel):
    with open(os.path.join(STATIC, rel), encoding="utf-8") as f: return f.read()


def code(rel):
    return re.sub(r"(^|\s)//[^\n]*", " ", re.sub(r"/\*.*?\*/", "", rd(rel), flags=re.S))


class TestMtfScreen(unittest.TestCase):
    def test_only_the_mtf_endpoint_is_called_and_no_timers_or_animation(self):
        js = code("js/66-mtf.js")
        self.assertEqual(set(re.findall(r"/api/[a-z_]+", js)), {"/api/mtf"})
        for needle in ("setInterval", "requestAnimationFrame", "RCEngine"):
            self.assertNotIn(needle, js, needle)

    def test_mtf_screen_states_it_is_description_not_prediction(self):
        js = rd("js/66-mtf.js"); html = rd("index.html")
        self.assertIn("不是價格預測", js); self.assertIn("不是價格預測", html)
        self.assertIn("不會用其他週期代替", html); self.assertIn("沒有原生 4H", js)
        for banned in ("預測會上漲", "建議買進", "保證", "穩賺"):
            self.assertNotIn(banned, js + html, banned)

    def test_lives_in_market_view_not_the_lab(self):
        html = rd("index.html"); m = html.index('id="view-market"'); lab = html.index('id="view-lab"')
        self.assertGreater(html.index('id="mtfPanel"'), m); self.assertGreater(html.index('id="mtfPanel"'), lab)
        self.assertIn("runMtfView()", html)

    def test_rendering_is_table_plus_cards_from_the_same_data(self):
        js = code("js/66-mtf.js")
        self.assertIn("mtfRowHtml", js); self.assertIn("mtfCardHtml", js); self.assertIn("d.timeframes.map(mtfRowHtml)", js); self.assertIn("d.timeframes.map(mtfCardHtml)", js)

    def test_cache_is_shown_honestly(self):
        js = code("js/66-mtf.js")
        self.assertIn("使用快取", js); self.assertIn("重新取得", js); self.assertIn("來源不明", js)         # 沒有資訊時不假裝是『重新取得』或『快取』


class TestStaleDataNeverLooksLatest(unittest.TestCase):
    def test_signal_state_guard(self):
        js = code("js/40-signals-nav.js"); i = js.index("function getSignalState")
        self.assertRegex(js[i:i + 700], r"dataQuality && data\.dataQuality\.blocking")
        self.assertLess(js.index("blocking", i), js.index("hasBuyNow", i) if "hasBuyNow" in js[i:] else 10**9)   # 檢查在『買進訊號』判斷之前
        self.assertLess(js.index("blocking", i), js.index("▲ 買進訊號！", i))

    def test_modal_signal_and_nav_drawer_and_ranking_warn(self):
        self.assertIn("資料過期，不顯示最新訊號", code("js/20-charts.js"))
        self.assertIn("stale:'⚠ 資料過期'", code("js/90-main.js"))
        self.assertIn("資料品質警告", code("js/50-analysis.js"))
        self.assertIn("dqBadge(data.dataQuality)", code("js/10-cards.js") + code("js/60-views.js"))

    def test_backend_signal_endpoint_has_the_same_guard(self):
        src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read(); i = src.index("def signal():")
        seg = src[i:i + 4500]
        self.assertIn("quality_for_series", seg); self.assertIn("'state': 'stale'", seg)
        self.assertLess(seg.index("'state': 'stale'"), seg.index("has_buy_now"))


class TestVocabularyMatchesBackend(unittest.TestCase):
    SPEC = {"資料正常", "資料不足", "資料過期", "K 棒尚未收盤", "合成時間週期不完整", "時間戳異常或重複", "資料取得失敗"}

    def test_the_seven_states_requested(self):
        self.assertEqual({v[0] for v in DQ.STATUS.values()}, self.SPEC)

    def test_js_labels_equal_python_labels(self):
        body = re.search(r"QUALITY_LABEL = \{([^}]*)\}", rd("js/rc-job.js")).group(1)
        js = dict(re.findall(r"(\w+): '([^']+)'", body))
        for k, (label, _) in DQ.STATUS.items():
            if k == "forming": self.assertTrue(js[k].startswith("K 棒尚未收盤")); continue
            self.assertEqual(js[k], label, k)

    def test_blocking_set(self):
        self.assertEqual({k for k, v in DQ.STATUS.items() if v[1]}, {"insufficient", "stale", "incomplete_resample", "bad_timestamps", "fetch_failed"})
        self.assertFalse(DQ.STATUS["ok"][1]); self.assertFalse(DQ.STATUS["forming"][1])


class TestResearchCoreCancelPhases(unittest.TestCase):
    def test_two_phase_cancel_wiring(self):
        js = code("js/rc-job.js")
        for needle in ("handle.cancelling", "onCancelling", "正在取消", "取消中…", "cancelRaced", "unconfirmed"):
            self.assertIn(needle, js, needle)
        self.assertNotRegex(js[js.index("handle.cancel = function"):js.index("handle.cancel = function") + 400], r"ac\.abort\(\)\s*;\s*\} catch \(e\) \{ /\* ignore \*/ \}\s*try \{ root\.fetch")   # 按下取消時不立刻中斷連線
        self.assertIn("cancelling", code("js/rc-engine.js"))


if __name__ == "__main__":
    unittest.main()
