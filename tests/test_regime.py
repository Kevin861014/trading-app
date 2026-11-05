# -*- coding: utf-8 -*-
"""C2:市場環境分類(無前視)、環境歸屬、績效分組、濾網對照、樣本外揭露、Research Core 事件。離線,用 validation/stage3_ui/C2/snapshot.json 的真實 K 線。"""
import datetime, json, os, random, re, sys, unittest, warnings
from unittest import mock
warnings.filterwarnings("ignore")
os.environ.setdefault("RENDER", "true")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import adx_reference as R
import app as A
import sim
import market_regime as MR
import regime_study as RS

SNAP = json.load(open(os.path.join(ROOT, "validation", "stage3_ui", "C2", "snapshot.json"), encoding="utf-8"))
ROWS = SNAP["rows"]
NOW = datetime.datetime.fromisoformat(SNAP["__now__"]).replace(microsecond=0)


def lbl(code): return MR.LABEL[code]


class TestClassification(unittest.TestCase):
    def test_equals_textbook_wilder_everywhere(self):
        for k in ("BTC/USDT|4h", "2330.TW|1d"):
            rows = ROWS[k]; H, L, C = [[r[i] for r in rows] for i in (2, 3, 4)]
            p, m, a = MR.causal_dmi(H, L, C); rp, rm, ra = R.wilder_adx(H, L, C)
            for t in range(len(C)):
                self.assertEqual(a[t] is None, ra[t] is None, (k, t))
                if ra[t] is not None: self.assertAlmostEqual(a[t], ra[t], 9); self.assertAlmostEqual(p[t], rp[t], 9); self.assertAlmostEqual(m[t], rm[t], 9)

    def test_label_at_bar_i_uses_only_bars_up_to_i(self):
        for k in ("BTC/USDT|4h", "2330.TW|1d", "AAPL|1d"):
            rows = ROWS[k][:1500]; full = MR.classify_series(rows)
            for n in (20, 28, 29, 30, 60, 150, 400, 900, 1500):
                self.assertEqual(MR.classify_series(rows[:n]), full[:n], (k, n))

    def test_changing_future_bars_never_changes_earlier_labels(self):
        rows = [list(r) for r in ROWS["SOL/USDT|4h"][:1200]]; base = MR.classify_series(rows); rnd = random.Random(5)
        for cut in (100, 400, 800):
            mod = [list(r) for r in rows]
            for i in range(cut + 1, len(mod)):
                f = rnd.uniform(0.5, 1.8); mod[i][2] *= f; mod[i][3] /= f; mod[i][4] *= rnd.uniform(0.7, 1.4)
            self.assertEqual(MR.classify_series(mod)[:cut + 1], base[:cut + 1], cut)

    def test_same_rule_as_the_card_badge(self):
        rows = ROWS["BTC/USDT|1d"]; labels = MR.classify_series(rows); rnd = random.Random(2)
        for i in rnd.sample(range(40, len(rows)), 60):
            mc = A.market_character(rows[:i + 1])
            self.assertEqual(lbl(labels[i]), mc["label"], i)

    def test_threshold_boundaries_and_ties(self):
        c = MR.classify_values
        self.assertEqual(c(25.0, 20, 10), MR.UP); self.assertEqual(c(24.96, 20, 10), MR.UP)       # 先四捨五入到 1 位(和徽章一樣)
        self.assertEqual(c(24.94, 20, 10), MR.TRANSITION); self.assertEqual(c(20.0, 10, 20), MR.TRANSITION)
        self.assertEqual(c(19.96, 10, 20), MR.TRANSITION); self.assertEqual(c(19.94, 10, 20), MR.RANGE)
        self.assertEqual(c(30, 15, 15), MR.UP); self.assertEqual(c(30, 14.9, 15), MR.DOWN)
        self.assertEqual(c(None, 1, 1), MR.NA)

    def test_first_27_bars_are_unclassified(self):
        codes = MR.classify_series(ROWS["BTC/USDT|1d"][:200])
        self.assertTrue(all(x == MR.NA for x in codes[:27])); self.assertNotEqual(codes[27], MR.NA)


class TestReferenceAlignment(unittest.TestCase):
    def test_never_uses_a_later_reference_bar(self):
        rnd = random.Random(3); ref_ts = sorted(rnd.sample(range(0, 10**10, 3600000), 300)); codes = [rnd.choice(MR.CODES) for _ in ref_ts]
        main = sorted(rnd.sample(range(0, 10**10, 1800000), 200)); out = MR.align_reference(main, ref_ts, codes, 3600000, max_gap_bars=10**9)
        for ts, c in zip(main, out):
            earlier = [i for i, t in enumerate(ref_ts) if t <= ts]
            self.assertEqual(c, codes[earlier[-1]] if earlier else MR.NA)

    def test_exact_timestamp_match_and_stale_reference(self):
        D = 86400000
        self.assertEqual(MR.align_reference([5 * D], [4 * D, 5 * D, 6 * D], ["up", "down", "range"], D), ["down"])      # 同一根:兩者收盤時間相同
        self.assertEqual(MR.align_reference([5 * D], [6 * D], ["up"], D), [MR.NA])                                     # 只有更晚的 → 未分類
        self.assertEqual(MR.align_reference([30 * D], [4 * D], ["up"], D), [MR.NA])                                    # 太舊 → 未分類,不湊
        self.assertEqual(MR.align_reference([9 * D], [5 * D], ["up"], D), ["up"])                                      # 長假(4 天)仍可用

    def test_reference_choice_is_same_market_same_timeframe(self):
        self.assertEqual(RS.reference_for("SOL/USDT", "crypto", "4h")[0], "BTC/USDT")
        self.assertEqual(RS.reference_for("2330.TW", "tw", "1d")[0], "^TWII"); self.assertEqual(RS.reference_for("AAPL", "us", "1d")[0], "^GSPC")
        self.assertEqual(RS.reference_for("AAPL", "us", "1d", "^IXIC")[0], "^IXIC"); self.assertEqual(RS.reference_for("AAPL", "us", "1d", "BTC/USDT")[0], "^GSPC")
        for m, tf in (("tw", "4h"), ("us", "4h"), ("commodity", "1d"), ("metal_etf", "1d")):
            sym, _, why = RS.reference_for("X", m, tf); self.assertIsNone(sym); self.assertTrue(why)


class StudyBase(unittest.TestCase):
    def setUp(self):
        def fake(symbol, start, interval="1d"):
            k = "%s|%s" % (symbol, interval)
            if k not in ROWS: raise RuntimeError("no snapshot for " + k)
            return ROWS[k]
        self.ps = [mock.patch.object(A, "fetch_data", fake), mock.patch.object(A, "_utcnow", lambda: NOW), mock.patch.object(A, "CCXT_AVAILABLE", True)]
        for p in self.ps: p.start()
        self.c = A.app.test_client()

    def tearDown(self):
        for p in reversed(self.ps): p.stop()

    def study(self, expect=200, **q):
        q.setdefault("period", "2y"); r = self.c.get("/api/regime_study", query_string=q); self.assertEqual(r.status_code, expect, r.get_data(as_text=True)[:300]); return r.get_json()


class TestStudyNumbers(StudyBase):
    def test_original_strategy_numbers_equal_the_ranking_pipeline(self):
        best = self.c.get("/api/best_strategy?symbol=BTC/USDT&period=2y&timeframe=4h&use_oos=1").get_json()
        self.assertTrue(best["results"])
        for r in best["results"][:3]:
            d = self.study(symbol="BTC/USDT", timeframe="4h", strategy=r["strat"])
            key = lambda b: {k: b[k] for k in ("pf", "total", "cagr", "mdd", "win", "trades")}
            self.assertEqual(key(d["overall"]["is"]), key(r["is"]), r["strat"]); self.assertEqual(key(d["overall"]["all"]), key(r["full"]), r["strat"])
            self.assertEqual(key(d["overall"]["oos"]), key({k: r["oos"][k] for k in ("pf", "total", "cagr", "mdd", "win", "trades")}), r["strat"])

    def test_regime_rows_add_up_to_the_overall_trades(self):
        d = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up,range", basis="market")
        for b in ("own", "market"):
            for seg, rows in d["breakdown"][b].items():
                self.assertEqual(sum(rows[c]["n"] for c in MR.CODES), rows["all"]["n"], (b, seg))
        self.assertEqual(d["breakdown"]["own"]["all"]["all"]["n"], d["overall"]["all"]["trades"])
        self.assertEqual(d["breakdown"]["own"]["is"]["all"]["n"], d["overall"]["is"]["trades"]); self.assertEqual(d["breakdown"]["own"]["oos"]["all"]["n"], d["overall"]["oos"]["trades"])

    def test_attribution_uses_the_closed_signal_bar_before_entry(self):
        rows = ROWS["SOL/USDT|1d"]; ck = sim.cost_kwargs("SOL/USDT", "diadx")
        st = A.run_backtest(rows, strategy="diadx", risk_pct=0.015, timeframe="1d", **ck)[2]["trade_log"]
        codes = MR.classify_series(rows); expect = {c: 0 for c in MR.CODES}
        ws = NOW - datetime.timedelta(days=730); split = A.is_oos_split(rows, ws, NOW)
        for t in st:
            if t.get("open") or t["entry_date"] < ws: continue
            i = t["entry_i"]
            self.assertEqual(codes[i - 1], MR.classify_series(rows[:i])[-1])          # 只用到訊號棒(含)以前的資料
            if t["exit_date"] < split["boundary_dt"] and t["entry_date"] < split["boundary_dt"]: expect[codes[i - 1]] += 1
        d = self.study(symbol="SOL/USDT", timeframe="1d", strategy="diadx")
        self.assertEqual({c: d["breakdown"]["own"]["is"][c]["n"] for c in MR.CODES}, expect)

    def test_small_samples_are_flagged_not_hidden(self):
        d = self.study(symbol="SOL/USDT", timeframe="1d", strategy="diadx")
        for seg in ("is", "oos"):
            for c in MR.CODES:
                s = d["breakdown"]["own"][seg][c]
                if s["n"] < 20: self.assertEqual(s["tier"], "insufficient")
        self.assertEqual(d["breakdown"]["own"]["is"]["down"]["pf"] is None, d["breakdown"]["own"]["is"]["down"]["n"] == 0)   # 沒有交易就是沒有數字,不填 0

    def test_no_future_columns_in_the_classification_output(self):
        d = self.study(symbol="BTC/USDT", timeframe="1d", strategy="diadx")
        self.assertIn("事後", d["disclaimer"]); self.assertIn("只用該根及之前已收盤", d["definition"]["attribution"]); self.assertNotIn("forward", json.dumps(d).lower())


class TestMaskedBacktest(unittest.TestCase):
    def test_all_allowed_equals_run_backtest_exactly(self):
        pyr = [k for k, v in A.STRATS.items() if v.get("pyramid")][:1]
        for sym, tf, ytf in (("BTC/USDT", "4h", "4h"), ("2330.TW", "1d", "1d")):
            rows = ROWS["%s|%s" % (sym, tf)]; ck = sim.cost_kwargs(sym)
            for key in ["sixline", "diadx", "ema50_200_adx", "supertrend", "tsmom"] + pyr:
                if key not in A.STRATS: continue
                ref = A.run_backtest(rows, strategy=key, risk_pct=0.015, timeframe=ytf, **ck)
                got = RS.backtest_masked(A, sim, rows, key, ytf, ck, [True] * len(rows))
                if ref is None: self.assertIsNone(got); continue
                self.assertEqual(got[0], ref[0]); self.assertEqual(got[1], ref[1]); self.assertEqual(got[2], ref[2]["trade_log"], (sym, key))

    def test_only_entries_are_filtered_exits_unchanged(self):
        rows = ROWS["BTC/USDT|4h"]; ck = sim.cost_kwargs("BTC/USDT"); codes = MR.classify_series(rows)
        allowed = [c in (MR.UP, MR.TRANSITION) for c in codes]
        res = RS.backtest_masked(A, sim, rows, "sixline", "4h", ck, allowed); self.assertIsNotNone(res)
        for t in res[2]:
            self.assertTrue(allowed[t["entry_i"] - 1], t["entry_i"])                     # 每筆進場的決策棒環境都在允許清單內
        base = A.run_backtest(rows, strategy="sixline", risk_pct=0.015, timeframe="4h", **ck)[2]["trade_log"]
        self.assertGreater(len(base), len(res[2]))                                        # 擋掉了一部分進場
        bmap = {t["entry_i"]: t for t in base}; same = 0
        for t in res[2]:
            o = bmap.get(t["entry_i"])
            if o is not None and not o.get("open") and not t.get("open"):               # 同一根進場的交易:出場棒與出場價必須完全相同(出場邏輯沒被改)
                self.assertEqual((t["exit_i"], t["exit_px"], t["entry_px"]), (o["exit_i"], o["exit_px"], o["entry_px"])); same += 1
        self.assertGreater(same, 5)


class TestFilterStudy(StudyBase):
    def test_oos_is_not_revealed_unless_asked(self):
        d = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up,transition", basis="own")
        f = d["filter"]; self.assertEqual(f["status"], "ok"); self.assertFalse(f["oos"]["revealed"]); self.assertNotIn("A", f["oos"]); self.assertNotIn("B", f["oos"])
        self.assertIn("樣本外尚未揭露", f["oos"]["note"])
        d2 = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up,transition", basis="own", reveal_oos="1")
        self.assertTrue(d2["filter"]["oos"]["revealed"]); self.assertEqual(d2["filter"]["A"]["is"], d["filter"]["A"]["is"]); self.assertEqual(d2["filter"]["B"]["is"], d["filter"]["B"]["is"])
        self.assertEqual(d2["filter"]["oos"]["A"], {k: d["overall"]["oos"][k] for k in d["overall"]["oos"]} | {"tier": d2["filter"]["oos"]["A"]["tier"], "avg": d2["filter"]["oos"]["A"]["avg"]})

    def test_candidate_comes_only_from_in_sample(self):
        d = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", basis="own")
        c = d["candidate"]; isb = d["breakdown"]["own"]["is"]
        for r in c["regimes"]: self.assertTrue(isb[r]["n"] >= 20 and isb[r]["pf"] > 1 and isb[r]["avg"] > 0)
        for r in ("up", "down", "range", "transition"):
            if isb[r]["n"] >= 20 and isb[r]["pf"] > 1 and isb[r]["avg"] > 0: self.assertIn(r, c["regimes"])

    def test_insufficient_sample_after_filter_is_stated(self):
        d = self.study(symbol="2330.TW", timeframe="1d", strategy="diadx", allow="up", basis="market")
        f = d["filter"]; self.assertLess(f["B"]["is"]["trades"], 20); self.assertFalse(f["isEnough"]); self.assertIn("資料不足", f["isNote"]); self.assertEqual(f["B"]["is"]["tier"], "樣本不足")

    def test_all_regimes_allowed_equals_original_inside_the_window(self):
        d = self.study(symbol="BTC/USDT", timeframe="4h", strategy="sixline", allow="up,down,range,transition", basis="own", reveal_oos="1")
        f = d["filter"]; strip = lambda b: {k: v for k, v in b.items() if k not in ("tier", "avg")}
        self.assertEqual(strip(f["A"]["is"]), strip(f["B"]["is"])); self.assertEqual(strip(f["oos"]["A"]), strip(f["oos"]["B"]))

    def test_market_filter_without_reference_says_unavailable(self):
        d = self.study(symbol="BTC/USDT", timeframe="1d", strategy="diadx", allow="up", basis="market")      # BTC 本身就是參考
        self.assertEqual(d["filter"]["status"], "ok"); self.assertTrue(d["reference"]["isSelf"])
        with mock.patch.object(RS, "reference_for", lambda *a, **k: (None, None, "沒有大盤")):
            d = self.study(symbol="BTC/USDT", timeframe="1d", strategy="diadx", allow="up", basis="market")
        self.assertEqual(d["filter"]["status"], "unavailable"); self.assertIsNone(d["breakdown"]["market"]); self.assertEqual(d["share"]["market"], None)

    def test_strategies_table_is_not_polluted_by_the_study(self):
        before = set(A.STRATS); self.study(symbol="BTC/USDT", timeframe="1d", strategy="diadx", allow="up", basis="own"); self.assertEqual(set(A.STRATS), before)

    def test_bad_requests(self):
        self.study(expect=400, symbol="BTC/USDT", timeframe="1d", strategy="no_such_strategy")
        with mock.patch.object(A, "fetch_data", lambda *a, **k: ROWS["BTC/USDT|1d"][:100]):
            self.study(expect=400, symbol="BTC/USDT", timeframe="1d", strategy="diadx")


class TestResearchCoreEvents(StudyBase):
    def test_real_events_and_identical_result_with_or_without_job(self):
        q = dict(symbol="2330.TW", timeframe="1d", strategy="diadx", allow="up,range", basis="market")
        plain = self.study(**q)
        job = "c2test" + "0" * 10
        withjob = self.study(job=job, **q); self.assertEqual(plain, withjob)
        ev = self.c.get("/api/job_events?job=" + job).get_json(); self.assertEqual(ev["status"], "ok"); evs = ev["events"]
        stages = [(e["stage"], e["status"]) for e in evs]
        for st in ("data", "indicators", "backtest", "validation", "summary"): self.assertIn((st, "done"), stages, st)
        self.assertIn(("signal", "skip"), stages)
        data_prog = [e for e in evs if e["stage"] == "data" and e["status"] == "progress"]
        self.assertEqual([e["meta"].get("role") if "meta" in e else e.get("role") for e in data_prog], ["main", "reference"])
        bt = [e for e in evs if e["stage"] == "backtest" and e["status"] == "progress"]; self.assertEqual(len(bt), 2)             # A 與 B 各一次真實回測

    def test_no_filter_means_one_backtest_event(self):
        job = "c2test" + "1" * 10; self.study(job=job, symbol="AAPL", timeframe="1d", strategy="tsmom")
        evs = self.c.get("/api/job_events?job=" + job).get_json()["events"]
        self.assertEqual(len([e for e in evs if e["stage"] == "backtest" and e["status"] == "progress"]), 1)


class TestFrontEnd(unittest.TestCase):
    def rd(self, p): return open(os.path.join(ROOT, "static", p), encoding="utf-8").read()

    def code(self, p):
        return re.sub(r"(^|\s)//[^\n]*", " ", re.sub(r"/\*.*?\*/", "", self.rd(p), flags=re.S))

    def test_only_the_regime_endpoint_no_timers_no_second_sphere(self):
        js = self.code("js/67-regime.js")
        self.assertEqual(set(re.findall(r"/api/[a-z_]+", js)), {"/api/regime_study"})
        for needle in ("setInterval", "requestAnimationFrame", "RCEngine", "new RCEngine"): self.assertNotIn(needle, js, needle)

    def test_panel_lives_in_market_view(self):
        h = self.rd("index.html"); self.assertGreater(h.index('id="regPanel"'), h.index('id="view-market"')); self.assertLess(h.index('id="regPanel"'), h.index('id="mkTable"'))
        self.assertIn("runRegimeView()", h); self.assertIn("c2.css", h); self.assertIn("67-regime.js", h)

    def test_wording_and_guards(self):
        js = self.rd("js/67-regime.js"); h = self.rd("index.html")
        for needle in ("樣本不足", "不是預測", "reveal_oos", "不再獨立", "只看樣本內", "資料不足", "歷史回測", "樣本外測試"): self.assertIn(needle, js + h, needle)
        for banned in ("保證", "穩賺", "建議買進", "推薦買入", "一定賺"): self.assertNotIn(banned, js + h, banned)

    def test_js_tier_text_matches_backend(self):
        js = self.rd("js/67-regime.js"); body = re.search(r"REG_TIER = \{([^}]*)\}", js).group(1); m = dict(re.findall(r"(\w+): '([^']+)'", body))
        self.assertEqual(m, RS.TIER_LABEL)

    def test_apply_nothing_to_the_live_bot(self):
        js = self.code("js/67-regime.js"); self.assertNotIn("portfolio", js); self.assertNotIn("config.", js)


if __name__ == "__main__":
    unittest.main()
