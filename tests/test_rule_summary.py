# -*- coding: utf-8 -*-
"""C3 規則式研究摘要:每句話可追溯到 API 欄位與固定規則;資料過期/樣本不足/沒有交易/OOS 不佳都不產生過度肯定的結論;文字與 API 數值一致。
離線(validation/stage3_ui/C2/snapshot.json 的真實 K 線:BTC、SOL、2330.TW、AAPL)。"""
import copy, datetime, json, os, re, sys, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app as A
import rule_summary as RSUM

SNAP = json.load(open(os.path.join(ROOT, "validation", "stage3_ui", "C2", "snapshot.json"), encoding="utf-8"))
ROWS = SNAP["rows"]
NOW = datetime.datetime.fromisoformat(SNAP["__now__"]).replace(microsecond=0) - datetime.timedelta(hours=8)     # 快照用本地時間存檔 → 換成真正的 UTC
BANNED = ("建議買進", "建議賣出", "推薦買入", "會上漲", "會下跌", "保證", "穩賺", "一定賺", "預測會", "買進訊號", "賣出訊號")


class Base(unittest.TestCase):
    now = NOW

    def setUp(self):
        def fake(symbol, start, interval="1d"):
            k = "%s|%s" % (symbol, interval)
            if k not in ROWS: raise RuntimeError("no snapshot " + k)
            return ROWS[k]
        self.ps = [mock.patch.object(A, "fetch_data", fake), mock.patch.object(A, "_utcnow", lambda: self.now), mock.patch.object(A, "CCXT_AVAILABLE", True)]
        for p in self.ps: p.start()
        self.c = A.app.test_client()

    def tearDown(self):
        for p in reversed(self.ps): p.stop()

    def study(self, **q):
        q.setdefault("period", "2y"); r = self.c.get("/api/regime_study", query_string=q); self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:200]); return r.get_json()

    def mtf(self, symbol, tfs):
        r = self.c.get("/api/mtf", query_string=dict(symbol=symbol, tfs=tfs)); self.assertEqual(r.status_code, 200); return r.get_json()

    def summ(self, study, mtf=None, trials=None):
        r = self.c.post("/api/rule_summary", json={"study": study, "mtf": mtf, "trials": trials or {}}); self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300]); return r.get_json()


def all_items(s): return [it for sec in s["sections"] for it in sec["items"]] + [s["headline"]]
def text_of(s): return "\n".join(it["text"] for it in all_items(s))
def sec(s, sid): return next(x for x in s["sections"] if x["id"] == sid)
def item(s, iid): return next(it for it in all_items(s) if it["id"] == iid)


class TestTraceability(Base):
    CASES = [("BTC/USDT", "4h", "sixline", "1d,4h"), ("SOL/USDT", "1d", "diadx", "1d,4h"), ("2330.TW", "1d", "diadx", "1d"), ("AAPL", "1d", "tsmom", "1d")]

    def check(self, s, study, mtf, trials=None):
        root = {"study": study, "mtf": mtf, "trials": trials or {}}
        for it in all_items(s):
            shown = []
            for e in it["evidence"]:
                self.assertEqual(RSUM.get_path(root, e["path"]), e["value"], e["path"])                      # 依據欄位的值 = API 回應裡的值
                self.assertEqual(RSUM.fmt(e["kind"], e["value"], root), e["display"])                         # 顯示值 = 固定格式化規則套在該值上
                shown.append(e["display"])
            blob = " ".join(shown)
            for num in re.findall(r"\d+(?:\.\d+)?", it["text"]):                                              # 文字裡的每個數字都來自依據欄位,或是規則裡的固定門檻
                self.assertTrue(num in blob or num in RSUM.FIXED_NUMBERS, (it["id"], num, it["text"]))
            self.assertNotIn("{", it["text"]); self.assertNotIn("}", it["text"])
            for w in BANNED: self.assertNotIn(w, it["text"], w)

    def test_every_sentence_traces_to_api_fields_for_the_four_symbols(self):
        for sym, tf, strat, tfs in self.CASES:
            study = self.study(symbol=sym, timeframe=tf, strategy=strat, allow="up,transition", basis="own"); mtf = self.mtf(sym, tfs)
            s = self.summ(study, mtf); self.check(s, study, mtf)
            self.assertFalse(s["engine"]["ai"]); self.assertIn("不是 AI 預測", s["disclaimer"]); self.assertIn("不是買賣訊號", s["disclaimer"])

    def test_summary_works_without_mtf_and_says_so(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); s = self.summ(study, None)
        self.assertIn("尚未取得", text_of(s)); self.check(s, study, None)

    def test_all_values_in_text_match_the_api_numbers(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); s = self.summ(study, self.mtf("BTC/USDT", "1d,4h")); t = item(s, "st_all")["text"]; o = study["overall"]["all"]
        self.assertIn("%d 筆" % o["trades"], t); self.assertIn("%.2f" % o["pf"], t); self.assertIn("%.1f%%" % o["win"], t); self.assertIn("%.2f%%" % o["mdd"], t)

    def test_headline_levels_and_no_buy_sell_words(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); s = self.summ(study, self.mtf("BTC/USDT", "1d,4h"))
        self.assertEqual(s["headline"]["level"], "descriptive"); self.assertIn("不是預測或買賣訊號", s["headline"]["text"])


class TestScenarios(Base):
    def test_insufficient_samples_never_get_a_confident_conclusion(self):
        for sym, tf, strat in (("SOL/USDT", "1d", "diadx"), ("2330.TW", "1d", "diadx"), ("AAPL", "1d", "tsmom")):
            study = self.study(symbol=sym, timeframe=tf, strategy=strat); s = self.summ(study, None)
            self.assertLess(study["overall"]["is"]["trades"], 20)
            self.assertEqual(s["headline"]["level"], "insufficient"); self.assertIn("樣本不足", s["headline"]["text"])
            self.assertIn("不能當成策略有效或無效的證據", s["headline"]["text"])
            for it in sec(s, "support")["items"]: self.assertNotIn("方向一致", it["text"]); self.assertNotIn("沒有看到樣本外失效", it["text"])
            self.assertNotIn("方向與樣本內一致", text_of(s))

    def test_stale_data_blocks_conclusions(self):
        self.now = NOW + datetime.timedelta(days=12)                      # 資料比現在舊 12 天
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); mtf = self.mtf("BTC/USDT", "1d,4h")
        self.assertTrue(study["dataQuality"]["blocking"]); s = self.summ(study, mtf)
        self.assertEqual(s["headline"]["level"], "blocked"); self.assertIn("資料過期", s["headline"]["text"])
        self.assertIn("不評估目前環境", text_of(s)); self.assertEqual([it["id"] for it in sec(s, "support")["items"]], ["sup_blocked"])
        self.assertIn("歷史狀態", item(s, "env_own")["text"])
        self.assertNotIn("沒有看到樣本外失效", text_of(s).replace("不評估", ""))   # 不給正面結論的字眼

    def test_quality_unknown_is_not_treated_as_ok(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); study["dataQuality"] = None; s = self.summ(study, None)
        self.assertEqual(s["headline"]["level"], "insufficient"); self.assertIn("未檢查", s["headline"]["text"])

    def test_no_trades(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); z = {k: None for k in study["overall"]["all"]}; z.update(trades=0)
        study["overall"] = {"all": dict(z), "is": dict(z), "oos": dict(z)}
        s = self.summ(study, None); self.assertEqual(s["headline"]["level"], "notrades"); self.assertIn("沒有交易", s["headline"]["text"])
        self.assertEqual([it["id"] for it in sec(s, "strategy")["items"]], ["st_none"]); self.assertEqual([it["id"] for it in sec(s, "support")["items"]], ["sup_none"])
        self.assertIn("沒有任何交易", text_of(s))

    def test_oos_poor_is_called_out(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); study["overall"]["is"].update(pf=1.6, trades=40); study["overall"]["oos"].update(pf=0.6, trades=25)
        s = self.summ(study, None); t = item(s, "st_oos")["text"]
        self.assertIn("樣本外沒有延續", t); self.assertIn("1.60", t); self.assertIn("0.60", t); self.assertNotIn("沒有看到樣本外失效", t)
        study["overall"]["oos"].update(pf=1.3, trades=3); self.assertIn("證據不足", item(self.summ(study, None), "st_oos")["text"])
        study["overall"]["oos"].update(pf=1.3, trades=25); self.assertIn("沒有看到樣本外失效的跡象", item(self.summ(study, None), "st_oos")["text"])
        study["overall"]["is"].update(pf=0.8); study["overall"]["oos"].update(pf=0.9); self.assertIn("沒有看到正的期望值", item(self.summ(study, None), "st_oos")["text"])

    def test_current_environment_support_needs_enough_history(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); cur = study["currentRegime"]["own"]; s = self.summ(study, None)
        n = study["breakdown"]["own"]["is"][cur]["n"]; t = item(s, "sup_own")["text"]
        if n == 0: self.assertIn("沒有任何進場交易", t)
        elif n < 20: self.assertIn("樣本不足", t); self.assertIn("不足以判斷", t)
        study["breakdown"]["own"]["is"][cur].update(n=30, pf=1.4, avg=0.5); study["breakdown"]["own"]["oos"][cur].update(n=25, pf=1.2)
        t = item(self.summ(study, None), "sup_own")["text"]; self.assertIn("樣本內 30 筆", t); self.assertIn("1.40", t); self.assertIn("方向一致", t)
        study["breakdown"]["own"]["oos"][cur].update(n=25, pf=0.7); self.assertIn("沒有延續", item(self.summ(study, None), "sup_own")["text"])
        study["breakdown"]["own"]["is"][cur].update(n=30, pf=0.9); self.assertIn("沒有正的期望", item(self.summ(study, None), "sup_own")["text"])

    def test_filter_improvement_needs_oos_evidence(self):
        base = dict(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up,transition", basis="own")
        study = self.study(**base)
        # 構造:樣本內改善且樣本數夠;樣本外尚未揭露
        f = study["filter"]; f["B"]["is"].update(trades=25, pf=2.0); f["A"]["is"].update(trades=30, pf=1.1)
        s = self.summ(study, None); self.assertIn("樣本內：濾網", item(s, "flt_is")["text"]); self.assertIn("沒有樣本外證據", item(s, "flt_oos")["text"]); self.assertIn("不代表有效", item(s, "flt_oos")["text"])
        self.assertFalse([e for it in all_items(s) for e in it["evidence"] if e["path"].startswith("study.filter.oos.A") or e["path"].startswith("study.filter.oos.B")])   # 沒揭露就不碰樣本外
        # 揭露後:樣本外不足 / 同方向 / 沒延續
        study2 = self.study(**dict(base, reveal_oos="1")); f = study2["filter"]; f["B"]["is"].update(trades=25, pf=2.0); f["A"]["is"].update(trades=30, pf=1.1)
        f["oos"]["B"].update(trades=8, pf=3.0); self.assertIn("不足以確認", item(self.summ(study2, None), "flt_oos")["text"])
        f["oos"]["B"].update(trades=30, pf=1.8); f["oos"]["A"].update(trades=30, pf=1.2); self.assertIn("方向與樣本內一致", item(self.summ(study2, None), "flt_oos")["text"])
        f["oos"]["B"].update(trades=30, pf=0.8); self.assertIn("沒有延續到樣本外", item(self.summ(study2, None), "flt_oos")["text"])
        # 樣本內沒改善 → 不用樣本外背書
        f["B"]["is"].update(pf=0.9); self.assertIn("不需要、也不應該", item(self.summ(study2, None), "flt_oos")["text"])
        # 濾網後樣本內不足
        f["B"]["is"].update(trades=9, pf=5.0); self.assertIn("資料不足，不下結論", item(self.summ(study2, None), "flt_is")["text"])

    def test_trials_warnings(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up", basis="own")
        s = self.summ(study, None, {"count": 4, "revealed": 2}); self.assertIn("多重比較", item(s, "flt_trials")["text"]); self.assertIn("不再獨立", item(s, "flt_rev")["text"])
        self.assertNotIn("flt_trials", [it["id"] for it in all_items(self.summ(study, None, {"count": 2, "revealed": 1}))])

    def test_mtf_consistency_text_comes_from_the_api_summary(self):
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline"); mtf = self.mtf("BTC/USDT", "1d,4h"); s = self.summ(study, mtf)
        self.assertEqual(item(s, "mtf_sum")["text"], mtf["summary"]["text"])


class TestEndpointAndUi(Base):
    def test_endpoint_is_pure_and_validates_input(self):
        with mock.patch.object(A, "fetch_data", side_effect=AssertionError("摘要端點不應該下載資料")):
            c = A.app.test_client()
            self.assertEqual(c.post("/api/rule_summary", json={}).status_code, 400); self.assertEqual(c.post("/api/rule_summary", data="x").status_code, 400)
            self.assertEqual(c.post("/api/rule_summary", json={"study": {"overall": {}}}).status_code, 200)

    def test_jump_targets_exist_in_the_page(self):
        html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read(); js = open(os.path.join(ROOT, "static", "js", "67-regime.js"), encoding="utf-8").read() + open(os.path.join(ROOT, "static", "js", "66-mtf.js"), encoding="utf-8").read()
        study = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up"); s = self.summ(study, self.mtf("BTC/USDT", "1d,4h"))
        for it in all_items(s):
            if not it["jump"]: continue
            tgt = it["jump"]["target"]
            if tgt.startswith("#regBody"): self.assertIn("class=\"rg-head\"" if ".rg-head" in tgt else ("rg-tbl" if ".rg-tbl" in tgt else "rg-filter"), js)
            else: self.assertIn('id="%s"' % tgt[1:], html + js)

    def test_front_end_wording_and_calls(self):
        js = open(os.path.join(ROOT, "static", "js", "68-summary.js"), encoding="utf-8").read()
        code = re.sub(r"(^|\s)//[^\n]*", " ", re.sub(r"/\*.*?\*/", "", js, flags=re.S))
        self.assertEqual(set(re.findall(r"/api/[a-z_]+", code)), {"/api/rule_summary", "/api/mtf", "/api/regime_study"})
        for needle in ("setInterval", "requestAnimationFrame", "RCEngine"): self.assertNotIn(needle, code)
        for needle in ("規則式", "不是 AI", "判斷依據", "查看對應數據"): self.assertIn(needle, js, needle)
        for w in BANNED: self.assertNotIn(w, js, w)


if __name__ == "__main__":
    unittest.main()
