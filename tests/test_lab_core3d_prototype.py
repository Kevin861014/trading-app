# -*- coding: utf-8 -*-
"""策略實驗室 3D 研究核心(原型)的靜態保證:授權、沒有偷渡原專案的其他功能、不改動引擎/事件模型、不發網路請求。"""
import hashlib, json, os, re, subprocess, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def rd(*p):
    with open(os.path.join(ROOT, *p), encoding='utf-8') as f: return f.read()

def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)(^|\s)//[^\n]*$', '', src)


class Core3DPrototype(unittest.TestCase):
    def test_vendor_files_match_provenance_and_license_kept(self):
        base = os.path.join(ROOT, 'static', 'vendor', 'three')
        prov = json.load(open(os.path.join(base, 'PROVENANCE.json'), encoding='utf-8'))
        self.assertEqual(prov['license'], 'MIT'); self.assertEqual(prov['version'], '0.186.1')
        want = {i['path']: i['sha256'] for i in prov['inventory']}
        have = 0
        for path, sha in want.items():
            fp = os.path.join(base, *path.split('/'))
            if not os.path.exists(fp): continue                       # 只複製了需要的檔案
            have += 1
            self.assertEqual(hashlib.sha256(open(fp, 'rb').read()).hexdigest(), sha, path + ' 與官方發佈的雜湊不同')
        self.assertGreaterEqual(have, 8)
        self.assertIn('three.js authors', open(os.path.join(base, 'LICENSE'), encoding='utf-8').read())

    def test_notices_cover_both_licences(self):
        n = rd('THIRD_PARTY_NOTICES.md')
        self.assertIn('mars-tw', n); self.assertIn('MIT License', n); self.assertIn('Three.js 0.186.1', n)
        js = rd('static', 'js', 'lab-core3d.js'); self.assertIn('MIT', js); self.assertIn('mars-tw', js)
        html = rd('static', 'index.html'); self.assertIn('JEV Trading Command Center', html); self.assertIn('importmap', html)

    def test_module_is_visual_only(self):
        code = strip_comments(rd('static', 'js', 'lab-core3d.js'))
        for bad in ('window.LIVE', 'LineWorkers', 'decision-graph', 'core-effects', 'OrbitControls', 'fetch(', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'sendBeacon', '/api/', 'setInterval'):
            self.assertNotIn(bad, code, bad)
        self.assertNotIn('下單', code)
        self.assertNotRegex(code, r'(?i)\b(vote|voting|pets?|worker)\b')

    def test_no_simulated_events_in_module(self):
        code = strip_comments(rd('static', 'js', 'lab-core3d.js'))
        for w in ('demo', 'simulate', 'fake'): self.assertNotIn(w, code.lower())
        # 動畫迴圈只在有真實工作/光點/拖曳/使用者開啟裝飾旋轉時存在
        self.assertIn('const busy = () => state ===', code)

    def test_lab_fallback_to_canvas_engine(self):
        js = rd('static', 'js', '65-research-lab.js')
        self.assertIn('(max-width: 720px)', js); self.assertIn('webgl', js); self.assertIn('RCEngine.create', js)
        self.assertIn('改用 Canvas 球體', js); self.assertIn("localStorage.getItem('lab3d')", js)

    def test_engine_and_job_model_untouched_by_prototype(self):
        r = subprocess.run(['git', 'diff', '--stat', '--', 'static/js/rc-engine.js', 'static/js/rc-job.js', 'sim.py', 'research_events.py'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), '', r.stdout)

    def test_flow_bar_only_lists_real_stages(self):
        js = rd('static', 'js', '65-research-lab.js')
        m = re.search(r'id="labFlow".*?</div></div>', js, flags=re.S); self.assertTrue(m)
        stages = re.findall(r'data-stage="(\w+)"', m.group(0))
        self.assertEqual(stages, ['data', 'backtest', 'validation', 'result'])      # 不含 indicators / signal / summary(這個流程不會執行)

    def test_prototype_does_not_touch_other_pages(self):
        r = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True, text=True)
        touched = [l[3:].strip().strip('"') for l in r.stdout.splitlines()]
        for f in ('static/js/10-cards.js', 'static/js/60-views.js', 'static/js/66-mtf.js', 'static/js/67-regime.js', 'static/js/68-summary.js', 'static/js/40-signals-nav.js'):
            self.assertNotIn(f, touched, f)


if __name__ == '__main__':
    unittest.main()
