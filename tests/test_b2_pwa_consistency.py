# -*- coding: utf-8 -*-
"""階段三 B2:PWA(manifest + 圖示,沒有 Service Worker)、OOS 分級在前後端與文件一致、Render 專屬邏輯已移除。"""
import os, re, sys, io, json, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app as A
from tests.test_ui_api import _Base


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f: return f.read()


class TestPwa(unittest.TestCase):
    def setUp(self): self.client = A.app.test_client()

    def test_manifest(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/manifest+json", r.headers["Content-Type"])
        m = r.get_json(force=True)
        self.assertEqual(m["display"], "standalone"); self.assertEqual(m["start_url"], "/"); self.assertEqual(m["lang"], "zh-TW")
        sizes = {(i["sizes"], i.get("purpose")) for i in m["icons"]}
        self.assertIn(("192x192", "any"), sizes); self.assertIn(("512x512", "any"), sizes); self.assertIn(("512x512", "maskable"), sizes)
        for i in m["icons"]:
            rr = self.client.get(i["src"]); self.assertEqual(rr.status_code, 200, i["src"]); self.assertEqual(rr.headers["Content-Type"], "image/png")

    def test_icons_have_declared_pixel_sizes(self):
        from PIL import Image
        for url, size in (("/apple-touch-icon.png", 180), ("/static/pwa/icon-192.png", 192), ("/static/pwa/icon-512.png", 512), ("/static/pwa/icon-maskable-512.png", 512)):
            r = self.client.get(url); self.assertEqual(r.status_code, 200, url)
            im = Image.open(io.BytesIO(r.data)); self.assertEqual(im.size, (size, size), url)
            self.assertEqual(im.mode, "RGB", "%s 不該有透明通道(iOS 會把透明塗黑)" % url)
        self.assertEqual(self.client.get("/favicon.ico").status_code, 200)

    def test_html_head_tags(self):
        h = read("static/index.html")
        for needle in ('rel="manifest"', 'rel="apple-touch-icon"', "viewport-fit=cover", 'name="apple-mobile-web-app-capable"', 'name="theme-color"', "/static/css/mobile.css"):
            self.assertIn(needle, h, needle)

    def test_no_service_worker(self):
        self.assertEqual(self.client.get("/sw.js").status_code, 404)
        self.assertEqual(self.client.get("/service-worker.js").status_code, 404)
        for rel in ("static/index.html",) + tuple("static/js/" + f for f in os.listdir(os.path.join(ROOT, "static/js"))):
            self.assertNotIn("serviceWorker", read(rel), rel)


class TestOosTierConsistency(unittest.TestCase):
    def test_constants_match_across_backend_frontend_and_docs(self):
        js = read("static/js/05-ui-helpers.js")
        m = re.search(r"OOS_TIER_PRELIM\s*=\s*(\d+)\s*,\s*OOS_TIER_EVAL\s*=\s*(\d+)", js)
        self.assertEqual((int(m.group(1)), int(m.group(2))), (A.OOS_TIER_PRELIM, A.OOS_TIER_EVAL))
        self.assertEqual((A.OOS_TIER_PRELIM, A.OOS_TIER_EVAL), (20, 50))
        for rel in ("README.md", "static/index.html", "static/js/05-ui-helpers.js"):
            t = read(rel)
            self.assertIn("20", t, rel); self.assertTrue(re.search(r"少於 ?20 ?筆", t) or "<20" in t, rel)
            self.assertTrue("20～49" in t or "20~49" in t, rel); self.assertTrue(re.search(r"50 ?筆以上|≥ ?50", t), rel)
        for label in ("樣本不足", "初步觀察", "可進一步評估"):
            self.assertIn(label, js)

    def test_legacy_threshold_is_never_called_credibility(self):
        js = read("static/js/05-ui-helpers.js") + read("static/js/50-analysis.js")
        self.assertIn("舊版技術門檻", js)
        self.assertNotIn("推薦買入", js); self.assertNotIn("保證獲利", js)


class TestRenderLogicRemoved(_Base):
    def test_no_render_specific_code_left_in_frontend(self):
        for f in os.listdir(os.path.join(ROOT, "static/js")):
            t = read("static/js/" + f)
            self.assertNotIn("isRender", t, f)
            self.assertNotRegex(t, r"Render 免費|Render 請", f)

    def test_config_has_no_isrender_and_deep_analysis_is_not_blocked(self):
        self.assertNotIn("isRender", self.client.get("/api/config").get_json())
        with mock.patch.object(A, "IS_RENDER", True):          # 即使環境變數 RENDER=true 也不再擋深度分析
            r = self.client.get("/api/deep_analysis", query_string=dict(symbol=self.SYMBOL, timeframe="1d"))
        self.assertEqual(r.status_code, 200, r.get_json())


if __name__ == "__main__":
    unittest.main()
