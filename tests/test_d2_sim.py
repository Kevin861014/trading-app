# -*- coding: utf-8 -*-
"""D2 投資組合模擬器的單元測試(用合成的小資料,離線):資金/數量公式、步長與最小名目、成本、停損(收盤判定 vs 交易所盤中)、移動停損、資金費率、同輪進場限制與暴露上限。
另外檢查備份腳本不含金鑰。"""
import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D2 = os.path.join(ROOT, "validation", "d2_portfolio")
sys.path.insert(0, D2)
import d2_sim as S

H = S.HOUR; T0 = 1_800_000_000_000 - (1_800_000_000_000 % (4 * H))          # 對齊 4H
EXIT_PCT = {"pct": (0.0, 0.0, 0.0, 0.025, 0.0, 0.075), "atr": (3.0, 5.0, 0.0, 0.0, 0.0, 0.0)}


def market(symbols, nh=48, step=0.1, min_cost=5.0, lows=None, opens=None, funding=None, highs=None):
    """每個幣 nh 根 1H(價格 100,可用 lows/opens/highs 覆寫某幾根),以及對應的 4H。"""
    lows = lows or {}; opens = opens or {}; highs = highs or {}; data = {'candles': {}, 'markets': {}, 'funding': {}}
    for s in symbols:
        rows = []
        for i in range(nh):
            ts = T0 + i * H; o = opens.get((s, i), 100.0); rows.append([ts, o, highs.get((s, i), 101.0), lows.get((s, i), 99.0), 100.0, 1.0])
        data['candles'][(s, '1h')] = rows
        data['candles'][(s, '4h')] = [[T0 + j * 4 * H, rows[4 * j][1], max(r[2] for r in rows[4 * j:4 * j + 4]), min(r[3] for r in rows[4 * j:4 * j + 4]), rows[4 * j + 3][4], 1.0] for j in range(nh // 4)]
        data['markets'][s] = {'step': step, 'min_cost': min_cost, 'min_amount': step, 'id': s.replace('/', '')}
        data['funding'][s] = (funding or {}).get(s, [])
    return S.Market(data)


def combos(*xs): return [{'symbol': s, 'timeframe': '4h', 'strategy': st, 'weight': w} for s, st, w in xs]


def sigs(sym, st, el_bars=(), xl_bars=(), n=12, atr=2.0):
    return {(sym, '4h', st): {T0 + j * 4 * H: (j in el_bars, j in xl_bars, atr) for j in range(n)}}


def P(**kw):
    p = S.default_params(EXIT_PCT, slip_entry=0.0, slip_exit=0.0, slip_stop=0.0, latency_s=14.0, **kw); return p


def run(M, sg, cb, T_end_h=44, wallet=300.0, **kw):
    return S.run(M, sg, [(T0, cb)], T0, T0 + T_end_h * H, kw.pop('P', P(sumw_override=kw.pop('sumw', None))), wallet, **kw)


class TestSizingAndCosts(unittest.TestCase):
    def test_quantity_formula_rounding_fee_and_signal_exit(self):
        M = market(['AAA/USDT']); cb = combos(('AAA/USDT', 'pct', 1.0)); sg = sigs('AAA/USDT', 'pct', el_bars={1}, xl_bars={4})
        r = run(M, sg, cb, sumw=2.0)                                      # alloc = 300 × 1/2 = 150
        self.assertEqual(len(r['trades']), 1); t = r['trades'][0]
        sd = 0.025 * 100.0; raw = min(150 * 0.0403 / sd, 150 * 3 / 100.0); self.assertAlmostEqual(t['qty'], int(raw / 0.1 + 1e-9) * 0.1, 9)     # 無條件捨去到 0.1
        self.assertEqual(t['why'], '訊號出場'); self.assertAlmostEqual(t['fees'], t['qty'] * 100 * 0.0005 * 2, 9)
        self.assertAlmostEqual(t['net'], t['gross'] - t['fees'] + t['funding'], 9); self.assertAlmostEqual(r['wallet_end'], 300.0 + t['net'], 9)
        self.assertEqual(t['entry_ts'], T0 + 2 * 4 * H + 14000)                                                                              # 訊號棒收盤後 14 秒成交

    def test_leverage_cap_binds_when_stop_is_tight(self):
        M = market(['AAA/USDT'], step=0.01); cb = combos(('AAA/USDT', 'pct', 1.0)); sg = sigs('AAA/USDT', 'pct', el_bars={1})
        p = P(sumw_override=1.0); p['risk'] = 5.0                           # 風險極大 → 以 3x 名目上限為準
        r = S.run(M, sg, [(T0, cb)], T0, T0 + 20 * H, p, 300.0)
        self.assertAlmostEqual(r['open'][0]['notional'], 300 * 0.9 * 3, delta=1.0)          # 先被『可用保證金 ×0.9』預檢縮量(need = 名目/3 > 可用×0.9),與機器人 reconcile 相同

    def test_below_min_notional_or_step_is_rejected_not_forced(self):
        M = market(['AAA/USDT'], step=1.0); cb = combos(('AAA/USDT', 'pct', 0.5)); sg = sigs('AAA/USDT', 'pct', el_bars={1})
        r = run(M, sg, cb, wallet=20.0, sumw=16.0)                         # alloc 0.6 USDT → 不到一個步長
        self.assertEqual(r['trades'], []); self.assertEqual(r['open'], []); self.assertGreaterEqual(sum(r['rejected'].values()), 1)
        M2 = market(['AAA/USDT'], step=0.001, min_cost=50.0); r2 = run(M2, sg, cb, wallet=40.0, sumw=1.0)       # alloc 20 → 名目約 32 < 最小名目 50
        self.assertEqual(r2['open'], []); self.assertEqual(r2['rejected'].get('below_min_notional'), 1)


class TestStops(unittest.TestCase):
    def test_exchange_stop_triggers_intrabar_below_995_of_stop(self):
        # 停損 = 100×0.975 = 97.5;交易所單 = 97.5×0.995 = 97.0125。第 12 根 1H 的低點 96 → 盤中被打到
        M = market(['AAA/USDT'], lows={('AAA/USDT', 12): 96.0}); sg = sigs('AAA/USDT', 'pct', el_bars={1})
        r = run(M, sg, combos(('AAA/USDT', 'pct', 1.0)), sumw=1.0); t = r['trades'][0]
        self.assertEqual(t['why'], '交易所保護停損'); self.assertAlmostEqual(t['exit_fill'], 97.0125, 6); self.assertEqual(t['exit_ts'], T0 + 12 * H + H // 2)

    def test_bar_close_stop_when_low_is_between_stop_and_exchange_stop(self):
        # 低點 97.3:低於邏輯停損 97.5、但沒到 97.0125 → 交易所單沒觸發;收盤後機器人判定停損並以市價賣
        M = market(['AAA/USDT'], lows={('AAA/USDT', 13): 97.3}); sg = sigs('AAA/USDT', 'pct', el_bars={1})
        r = run(M, sg, combos(('AAA/USDT', 'pct', 1.0)), sumw=1.0); t = r['trades'][0]
        self.assertEqual(t['why'], '停損/鎖利(收盤判定)'); self.assertAlmostEqual(t['exit_fill'], 100.0, 6)                  # 下一根開盤價(價格是平的)

    def test_gap_down_fills_at_open_not_at_stop(self):
        M = market(['AAA/USDT'], opens={('AAA/USDT', 12): 90.0}, lows={('AAA/USDT', 12): 89.0}); sg = sigs('AAA/USDT', 'pct', el_bars={1})
        r = run(M, sg, combos(('AAA/USDT', 'pct', 1.0)), sumw=1.0); t = r['trades'][0]
        self.assertAlmostEqual(t['exit_fill'], 90.0, 6); self.assertLess(t['net'], 0)

    def test_atr_trailing_stop_ratchets_up_and_triggers_on_a_pullback(self):
        # 初始停損 = 100 − 3×2 = 94;第 8 根 1H 高點衝到 110 → 追蹤停損 = 110 − 5×2 = 100。之後第 24 根低點 99.5:原本的 94 不會觸發,但被墊高的 100 會
        M = market(['AAA/USDT'], highs={('AAA/USDT', 8): 110.0}, lows={('AAA/USDT', 24): 99.5}); sg = sigs('AAA/USDT', 'atr', el_bars={1}, atr=2.0)
        r = S.run(M, sg, [(T0, combos(('AAA/USDT', 'atr', 1.0)))], T0, T0 + 44 * H, P(sumw_override=1.0), 300.0)
        self.assertEqual(len(r['trades']), 1); self.assertEqual(r['trades'][0]['why'], '停損/鎖利(收盤判定)')
        M2 = market(['AAA/USDT'], lows={('AAA/USDT', 24): 99.5})                               # 沒有衝高 → 停損仍是 94 → 一路持有
        r2 = S.run(M2, sg, [(T0, combos(('AAA/USDT', 'atr', 1.0)))], T0, T0 + 44 * H, P(sumw_override=1.0), 300.0)
        self.assertEqual(r2['trades'], []); self.assertEqual(len(r2['open']), 1)


class TestFundingAndGuards(unittest.TestCase):
    def test_long_pays_positive_funding(self):
        fund = {'AAA/USDT': [(T0 + 8 * H, 0.001), (T0 + 12 * H, 0.001), (T0 + 40 * H, 0.001)]}      # 8H 在進場前 14 秒、40H 在出場之後 → 只有 12H 這筆要付
        M = market(['AAA/USDT'], funding=fund); sg = sigs('AAA/USDT', 'pct', el_bars={1}, xl_bars={8})
        r = run(M, sg, combos(('AAA/USDT', 'pct', 1.0)), sumw=1.0, T_end_h=40); t = r['trades'][0]
        self.assertAlmostEqual(t['funding'], -t['qty'] * 100.0 * 0.001, 9)

    def test_max_entries_per_cycle_prefers_larger_weight(self):
        syms = ['AAA/USDT', 'BBB/USDT']; M = market(syms); sg = {}
        for s in syms: sg.update(sigs(s, 'pct', el_bars={1}))
        cb = combos(('AAA/USDT', 'pct', 0.5), ('BBB/USDT', 'pct', 1.5))
        r = S.run(M, sg, [(T0, cb)], T0, T0 + 20 * H, P(sumw_override=2.0), 300.0, max_entries_per_cycle=1)
        self.assertEqual([x['key'] for x in r['open']], ['BBB/USDT|4h|pct']); self.assertEqual(r['rejected']['guard_max_entries'], 1)

    def test_entry_guard_blocks_exposure_but_does_not_scale(self):
        syms = ['AAA/USDT', 'BBB/USDT']; M = market(syms); sg = {}
        for s in syms: sg.update(sigs(s, 'pct', el_bars={1}))
        cb = combos(('AAA/USDT', 'pct', 1.0), ('BBB/USDT', 'pct', 1.0))
        free = S.run(M, sg, [(T0, cb)], T0, T0 + 20 * H, P(sumw_override=2.0), 300.0)
        one = free['open'][0]['notional']
        g = S.run(M, sg, [(T0, cb)], T0, T0 + 20 * H, P(sumw_override=2.0), 300.0, entry_guard=lambda cap, na, new, pos: na + new <= 1.5 * one)
        self.assertEqual(len(free['open']), 2); self.assertEqual(len(g['open']), 1); self.assertAlmostEqual(g['open'][0]['notional'], one, 6); self.assertEqual(g['rejected']['guard_exposure'], 1)

    def test_config_switch_closes_removed_combo(self):
        M = market(['AAA/USDT', 'BBB/USDT']); sg = sigs('AAA/USDT', 'pct', el_bars={1}); sg.update(sigs('BBB/USDT', 'pct'))
        a = combos(('AAA/USDT', 'pct', 1.0), ('BBB/USDT', 'pct', 1.0)); b = combos(('BBB/USDT', 'pct', 1.0))
        r = S.run(M, sg, [(T0, a), (T0 + 24 * H, b)], T0, T0 + 44 * H, P(sumw_override=2.0), 300.0)
        self.assertEqual(r['open'], []); self.assertEqual(r['trades'][0]['why'], '設定更換/重啟:殘倉平倉')


class TestBackupSafety(unittest.TestCase):
    def test_redaction_removes_all_secret_fields(self):
        import d2_backup as B
        o = B.redact({'api_key': 'K', 'api_secret': 'S', 'combos': [{'symbol': 'X', 'token_x': 'T'}], 'risk_pct': 4})
        self.assertEqual(o['api_key'], '<removed>'); self.assertEqual(o['api_secret'], '<removed>'); self.assertEqual(o['combos'][0]['token_x'], '<removed>'); self.assertEqual(o['risk_pct'], 4)

    def test_committed_manifest_reports_clean_verification(self):
        p = os.path.join(D2, "results", "backup_manifest.json")
        if not os.path.exists(p): self.skipTest("manifest not generated")
        m = json.load(open(p, encoding="utf-8")); self.assertEqual(m["verification"]["secrets_found_in_backup"], []); self.assertEqual(m["verification"]["hash_problems"], [])
        for e in m["files"]:
            if e.get("kind", "").startswith("redacted"): self.assertTrue(e["backup"].endswith(".REDACTED.json"))
        self.assertNotIn("secret_keys", json.dumps(m))

    def test_d2_scripts_never_call_write_endpoints_or_touch_bot_files_for_writing(self):
        import glob, re
        src = {f: open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(D2, "*.py"))}
        for f, t in src.items():
            for bad in ("create_order", "cancel_order", "set_leverage", "fapiPrivatePost", "fapiPrivateDelete", "fapiPrivatePut", "withdraw("):
                self.assertNotIn(bad, t, (f, bad))
            if os.path.basename(f) not in ("d2_backup.py",):
                self.assertNotRegex(t, r"open\([^)]*BOT[^)]*,\s*['\"][wa]", f)                   # 沒有以寫入模式開機器人資料夾的檔案


if __name__ == "__main__":
    unittest.main()
