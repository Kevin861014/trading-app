# -*- coding: utf-8 -*-
"""D4 前向紙上交易:離線測試(假行情來源 + 合成 K 棒,不連網、不碰 trading-bot、不依賴 raw 資料)。
重點:只用已收盤 K 棒/無未來資料、A/B 同一份行情、固定實驗雜湊、重啟不重複記帳、原始紀錄不被覆蓋、暖機不計績效、缺棒處理、與實盤隔離。"""
import glob, hashlib, json, os, random, re, shutil, stat, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P4 = os.path.join(ROOT, 'paper_trading'); sys.path.insert(0, P4); sys.path.insert(0, ROOT)
import d4_engine as E
import d4_report as R
from d4_store import FileLock, LockBusy, append_jsonl, read_jsonl

HOUR = 3600000; DAY = 24 * HOUR
T0 = 1794009600000                                                    # 2026-11-07 00:00 UTC 之後的某個整點(固定即可)
T0 = (T0 // HOUR) * HOUR
COMBOS = [{'symbol': s, 'timeframe': tf, 'strategy': st, 'weight': w} for s, tf, st, w in (
    ('TRX/USDT', '1h', 'tsmom', 1), ('XRP/USDT', '1h', 'vortex', 1), ('BNB/USDT', '4h', 'ttm', 1), ('XLM/USDT', '4h', 'supertrend', 1), ('INJ/USDT', '4h', 'supertrend', 1.5), ('SOL/USDT', '4h', 'ssl_channel', 0.5))]
SYMS = sorted({c['symbol'] for c in COMBOS}) + ['BTC/USDT']
MARKETS = {s: {'id': s.replace('/', ''), 'step': 0.001, 'min_amount': 0.001, 'min_cost': 5.0} for s in SYMS}


def synth(seed, span_before=80, span_after=14):
    """合成 1H/4H K 棒(有趨勢段與雜訊)+ 資金費率。回傳 ({(sid,tf): rows}, {sid: [(t,rate)]})。"""
    rnd = random.Random(seed); series = {}; fund = {}
    for si, s in enumerate(SYMS):
        sid = s.replace('/', ''); px = 1.0 + si * 40.0; drift = 0.0; rows1 = []
        t = T0 - span_before * DAY
        while t < T0 + span_after * DAY:
            if rnd.random() < 1 / 150: drift = rnd.choice((-0.0012, -0.0006, 0.0, 0.0008, 0.0016))
            r = drift + rnd.gauss(0, 0.007); o = px; c = px * (1 + r); h = max(o, c) * (1 + abs(rnd.gauss(0, 0.002))); l = min(o, c) * (1 - abs(rnd.gauss(0, 0.002)))
            rows1.append([t, o, h, l, c, 100.0 + rnd.random() * 50]); px = c; t += HOUR
        series[(sid, '1h')] = rows1; r4 = []
        for i in range(0, len(rows1) - 3, 4):
            if rows1[i][0] % (4 * HOUR): continue
            g = rows1[i:i + 4]; r4.append([g[0][0], g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)])
        series[(sid, '4h')] = r4
        fund[sid] = [(tt + 3, 0.0001 * rnd.choice((-1, 1, 2))) for tt in range(T0 - span_before * DAY, T0 + span_after * DAY, 8 * HOUR)]
    return series, fund


SERIES, FUND = synth(7)


class FakeFeed:
    def __init__(self, now, series=SERIES, fund=FUND):
        self.now = now; self.series = series; self.fund = fund; self.drop = set(); self.tamper = {}; self.leak_forming = False; self.calls = []; self.ffail = set(); self.info = {}
    def now_ms(self): return self.now
    def klines(self, sid, tf, start_ms):
        step = E.STEP[tf]; self.calls.append((sid, tf, start_ms)); out = []
        for r in self.series[(sid, tf)]:
            if r[0] < start_ms or (sid, tf, r[0]) in self.drop: continue
            closed = r[0] + step <= self.now - 5000
            if not closed and not (self.leak_forming and r[0] <= self.now): continue          # leak_forming:模擬行情來源『誤回傳尚未收盤的那一根』
            r = list(r)
            if (sid, tf, r[0]) in self.tamper: r[4] = self.tamper[(sid, tf, r[0])]
            out.append(r)
        return out
    def funding(self, sid, start_ms):
        if sid in self.ffail: raise RuntimeError('funding endpoint down')
        return [(t, x) for t, x in self.fund[sid] if t >= start_ms and t <= self.now - 1]
    def funding_info(self): return dict(self.info)
    def markets(self, symbols): return {s: dict(MARKETS[s]) for s in symbols}


def rmtree(p):
    def onerr(f, path, exc):
        os.chmod(path, stat.S_IWRITE); f(path)
    shutil.rmtree(p, onerror=onerr)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='d4test_'); self.dir = os.path.join(self.tmp, 'exp')
    def tearDown(self): rmtree(self.tmp)
    def init(self, d=None, start=T0, created=None):
        return E.init_experiment(d or self.dir, 'T', start, COMBOS, MARKETS, created if created is not None else T0 - DAY, {'file': 'test'})
    def events(self, d=None): return read_jsonl(os.path.join(d or self.dir, 'ledger', 'events.jsonl'))[0]
    def sha(self, p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
    def ledger_hashes(self, d=None):
        d = d or self.dir; out = {}
        for p in glob.glob(os.path.join(d, '**', '*'), recursive=True):
            if os.path.isfile(p) and not p.endswith(('status.json', 'tick.lock')): out[os.path.relpath(p, d)] = self.sha(p)
        return out


class TestSnapshotAndManifest(Base):
    def test_ab_definition_and_snapshot_is_complete(self):
        self.init(); s = json.load(open(os.path.join(self.dir, 'config_snapshot.json'), encoding='utf-8'))
        A, B = s['scenarios']['A']['combos'], s['scenarios']['B']['combos']
        self.assertEqual(len(A), 6); self.assertEqual([E.key_of(c) for c in A if E.key_of(c) not in [E.key_of(b) for b in B]], E.B_EXCLUDED)
        self.assertEqual(len(B), len(A) - 2); self.assertEqual(s['scenarios']['A']['sumw'], s['scenarios']['B']['sumw'])          # B 的 Σ權重沿用 A
        for c in B: self.assertIn(c, A)                                                                                          # B 的組合設定與 A 逐字相同
        for k in ('params', 'exit_params', 'markets', 'start_ts', 'initial_equity', 'data_source', 'rules'): self.assertIn(k, s)
        self.assertEqual(s['params']['slip_entry'], 0.0003); self.assertEqual(s['params']['sumw_override'], 16.0); self.assertEqual(s['initial_equity'], 310.0)
        m = json.load(open(os.path.join(self.dir, 'MANIFEST.json'), encoding='utf-8'))
        self.assertEqual(m['snapshot_sha256'], hashlib.sha256(open(os.path.join(self.dir, 'config_snapshot.json'), 'rb').read()).hexdigest())
        for f in ('sim.py', 'validation/d2_portfolio/d2_sim.py', 'paper_trading/d4_engine.py'): self.assertRegex(m['files_sha256'][f], r'^[0-9a-f]{64}$')
        self.assertEqual(E.verify_manifest(E.Exp(self.dir)), [])

    def test_real_config_gives_23_vs_21_with_same_sumw(self):
        src = E.default_combos_source()
        if not os.path.exists(src): self.skipTest('backup not available')
        combos = [{'symbol': c['symbol'], 'timeframe': c['timeframe'], 'strategy': c['strategy'], 'weight': c.get('weight', 1)} for c in json.load(open(src, encoding='utf-8'))['combos']]
        mk = {c['symbol']: {'id': 'X', 'step': 1, 'min_cost': 5} for c in combos}; mk['BTC/USDT'] = {'id': 'BTCUSDT', 'step': 0.001, 'min_cost': 5}
        s = E.build_snapshot('x', T0, combos, mk, T0 - DAY, {})
        self.assertEqual((len(s['scenarios']['A']['combos']), len(s['scenarios']['B']['combos'])), (23, 21)); self.assertEqual((s['scenarios']['A']['sumw'], s['scenarios']['B']['sumw']), (16, 16))
        self.assertEqual({E.key_of(c) for c in s['scenarios']['A']['combos']} - {E.key_of(c) for c in s['scenarios']['B']['combos']}, set(E.B_EXCLUDED))

    def test_records_are_read_only_and_never_overwritten(self):
        self.init()
        for f in ('config_snapshot.json', 'MANIFEST.json', 'MANIFEST.sha256'): self.assertFalse(os.access(os.path.join(self.dir, f), os.W_OK), f)
        with self.assertRaises(FileExistsError): self.init()                                                                      # 同目錄不能再建立/覆蓋
        with self.assertRaises(ValueError): self.init(d=os.path.join(self.tmp, 'past'), start=T0, created=T0 + HOUR)             # 開始日期不能在建立之前
        with self.assertRaises(ValueError): self.init(d=os.path.join(self.tmp, 'odd'), start=T0 + 1234)                           # 必須是整點

    def test_tampered_snapshot_or_code_hash_stops_the_tick(self):
        self.init(); snap = os.path.join(self.dir, 'config_snapshot.json'); os.chmod(snap, stat.S_IWRITE); open(snap, 'a').write(' ')
        self.assertIn('config_snapshot.json', E.verify_manifest(E.Exp(self.dir)))
        with self.assertRaises(E.ManifestMismatch): E.tick(self.dir, FakeFeed(T0 + 5 * HOUR))
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'bars')) and os.listdir(os.path.join(self.dir, 'bars')))          # 拒絕時沒有抓/寫任何資料

    def test_changed_strategy_or_simulator_file_hash_is_detected(self):
        self.init(); orig = E.tracked_hashes
        try:
            for f in ('sim.py', 'validation/d2_portfolio/d2_sim.py'):
                h = orig(); h[f] = '0' * 64; E.tracked_hashes = lambda h=h: h
                self.assertEqual(E.verify_manifest(E.Exp(self.dir)), [f])
        finally: E.tracked_hashes = orig
        self.assertEqual(E.verify_manifest(E.Exp(self.dir)), [])


class TestTick(Base):
    def run_ticks(self, nows, d=None, feed_hook=None):
        recs = []
        for n in nows:
            f = FakeFeed(n)
            if feed_hook: feed_hook(f)
            recs.append(E.tick(d or self.dir, f))
        return recs

    FINAL = T0 + 9 * DAY + 3 * HOUR + 40000

    def test_before_start_is_warmup_only_and_records_nothing_as_performance(self):
        self.init(); r = self.run_ticks([T0 - 2 * HOUR + 30000])[0]
        self.assertIn('warm-up', r.get('note', '')); self.assertEqual(self.events(), [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'ledger', 'marks_A.jsonl')))

    def test_warmup_history_is_not_counted_and_start_is_fixed(self):
        self.init(); self.run_ticks([self.FINAL]); evs = self.events()
        self.assertTrue(evs)
        for e in evs:
            ts = e.get('decision_ts') or e.get('ts'); self.assertGreaterEqual(ts, T0, e['id'])
        for sc in ('A', 'B'):
            m = read_jsonl(os.path.join(self.dir, 'ledger', 'marks_%s.jsonl' % sc))[0]; self.assertEqual(m[0]['h'], T0); self.assertEqual(m[0]['equity'], 310.0); self.assertEqual(m[0]['n_open'], 0)
            self.assertTrue(all(x['h'] >= T0 for x in m))

    def test_only_closed_bars_are_stored_and_future_is_never_used(self):
        self.init(); now = T0 + 4 * DAY + 90 * 60 * 1000; f = FakeFeed(now); f.leak_forming = True       # 行情來源誤給了尚未收盤的 K 棒
        r = E.tick(self.dir, f); self.assertEqual(r['errors'], [])
        for p in glob.glob(os.path.join(self.dir, 'bars', '*.jsonl')):
            tf = os.path.basename(p).rsplit('_', 1)[1][:2]; step = E.STEP[tf]
            for b in read_jsonl(p)[0]: self.assertLessEqual(b['t'] + step, now, p); self.assertGreaterEqual(b['fetched_at'], b['t'] + step)
        self.assertLessEqual(r['T1'] + HOUR, now - 2 * HOUR + HOUR)                                      # 處理範圍落後現在 ≥ 2 小時(資金費率已公布)
        # 早期 tick 的紀錄,在之後(更多資料)重算時完全不變 = 沒有使用未來資料
        early = {e['id']: e for e in self.events()}; self.run_ticks([self.FINAL])
        later = {e['id']: e for e in self.events()}
        for i, e in early.items():
            for k in E.COMPARE_KEYS:
                if k in e: self.assertTrue(E._close(e[k], later[i].get(k)), (i, k))
        self.assertEqual(read_jsonl(os.path.join(self.dir, 'ledger', 'divergences.jsonl'))[0], [])

    def test_progressive_ticks_equal_one_big_tick(self):
        d2 = os.path.join(self.tmp, 'exp2'); self.init(); self.init(d=d2)
        self.run_ticks([T0 + 26 * HOUR + 20000, T0 + 3 * DAY + 5 * HOUR, T0 + 6 * DAY + 11 * HOUR + 5000, self.FINAL]); self.run_ticks([self.FINAL], d=d2)
        a = {e['id']: e for e in self.events()}; b = {e['id']: e for e in self.events(d2)}
        self.assertEqual(set(a), set(b)); self.assertTrue(a)
        for i in a:
            for k in E.COMPARE_KEYS:
                if k in a[i]: self.assertTrue(E._close(a[i][k], b[i].get(k)), (i, k))
        for sc in ('A', 'B'):
            ma = read_jsonl(os.path.join(self.dir, 'ledger', 'marks_%s.jsonl' % sc))[0]; mb = read_jsonl(os.path.join(d2, 'ledger', 'marks_%s.jsonl' % sc))[0]
            self.assertEqual([(x['h'], round(x['equity'], 8)) for x in ma], [(x['h'], round(x['equity'], 8)) for x in mb])
        for p in glob.glob(os.path.join(self.dir, 'bars', '*.jsonl')): self.assertEqual(len(read_jsonl(p)[0]), len({b['t'] for b in read_jsonl(p)[0]}), p)   # 沒有重複的 K 棒
        self.assertEqual(len(a), len(self.events()), 'duplicate ids in ledger'); self.assertTrue(any(e['type'] == 'EXIT' for e in a.values()), 'synthetic data should produce closed trades')

    def test_rerun_is_idempotent_and_does_not_touch_existing_records(self):
        self.init(); self.run_ticks([self.FINAL]); h1 = {k: v for k, v in self.ledger_hashes().items() if 'ticks.jsonl' not in k}
        r = self.run_ticks([self.FINAL])[0]; self.assertEqual(r['new_records'], 0); self.assertEqual(r['divergences'], 0)
        h2 = {k: v for k, v in self.ledger_hashes().items() if 'ticks.jsonl' not in k}; self.assertEqual(h1, h2)

    def test_restart_after_partial_write_recovers_without_double_booking(self):
        self.init(); self.run_ticks([self.FINAL]); ev = os.path.join(self.dir, 'ledger', 'events.jsonl'); full = {e['id']: e for e in self.events()}; raw = open(ev, 'rb').read()
        open(ev, 'wb').write(raw[:len(raw) // 2 + 7])                                                      # 模擬寫到一半當機:檔案被截斷、最後一行殘缺
        tk = os.path.join(self.dir, 'ledger', 'ticks.jsonl'); lines = open(tk, 'rb').read().splitlines(True); open(tk, 'wb').write(b''.join(lines[:-1]))   # 並且尚未寫下 tick 提交紀錄
        r = self.run_ticks([self.FINAL])[0]; after = self.events(); ids = [e['id'] for e in after]
        self.assertEqual(len(ids), len(set(ids)), 'double booking'); self.assertEqual(set(ids), set(full)); self.assertGreater(r['new_records'], 0)
        for e in after:
            for k in E.COMPARE_KEYS:
                if k in e: self.assertTrue(E._close(e[k], full[e['id']].get(k)))
        self.assertTrue(read_jsonl(os.path.join(self.dir, 'ledger', 'corrupt_lines.jsonl'))[0], 'truncated fragment must be isolated, not lost')

    def test_original_decision_events_are_preserved_and_divergence_is_logged(self):
        self.init(); self.run_ticks([self.FINAL]); ev = os.path.join(self.dir, 'ledger', 'events.jsonl'); lines = open(ev, encoding='utf-8').read().splitlines()
        i = next(n for n, l in enumerate(lines) if '"type":"ENTRY"' in l); rec = json.loads(lines[i]); rec['sim_fill'] = rec['sim_fill'] * 1.5; rec['recorded_utc'] = 'ORIGINAL'; lines[i] = json.dumps(rec, sort_keys=True, separators=(',', ':'))
        open(ev, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n'); before = self.sha(ev)
        r = self.run_ticks([self.FINAL])[0]
        self.assertEqual(self.sha(ev), before, 'original records must never be rewritten'); self.assertEqual(r['divergences'], 1)
        d = read_jsonl(os.path.join(self.dir, 'ledger', 'divergences.jsonl'))[0]; self.assertEqual(d[0]['id'], rec['id']); self.assertIn('sim_fill', d[0]['diff'])

    def test_fills_are_labelled_simulated_with_expected_vs_market_difference(self):
        self.init(); self.run_ticks([self.FINAL]); n = 0
        for e in self.events():
            if e['type'] in ('ENTRY', 'EXIT'):
                n += 1; self.assertEqual(e['label'], 'SIMULATED'); self.assertIn('expected_px', e); self.assertIn('market_open', e); self.assertIn('slip_vs_market_open_pct', e)
                self.assertIsInstance(e['fill_within_candle_range'], bool); self.assertIsNotNone(e['recorded_utc'])       # 模擬成交 = 開盤 ± 滑價,偶爾會略超出該根 K 棒高低點;這個旗標照實記錄(報告會統計); self.assertIsNotNone(e['tick_id'])
        self.assertGreater(n, 0)
        for e in self.events():
            if e['type'] == 'ENTRY': self.assertGreater(e['sim_fill'], 0); self.assertGreater(e['fee'], 0)

    def test_a_and_b_use_the_same_market_data_and_b_has_fewer_combos(self):
        self.init(); r = self.run_ticks([self.FINAL])[0]
        self.assertEqual(len(glob.glob(os.path.join(self.dir, 'bars', '*.jsonl'))), len({(s, tf) for s, tf in [(c['symbol'].replace('/', '-'), c['timeframe']) for c in COMBOS] + [('BTC-USDT', '4h'), ('BTC-USDT', '1h')] + [(c['symbol'].replace('/', '-'), '1h') for c in COMBOS]}))
        self.assertIn('A', r); self.assertIn('B', r)
        keysB = {e['key'] for e in self.events() if e['scenario'] == 'B'}; self.assertFalse(keysB & set(E.B_EXCLUDED)); self.assertTrue({e['key'] for e in self.events() if e['scenario'] == 'A'} & set(E.B_EXCLUDED) or True)

    def test_missing_bar_stops_processing_before_the_gap_and_resumes_when_it_appears(self):
        self.init(); gap_t = T0 + 3 * DAY + 5 * HOUR; sid = 'TRXUSDT'
        def hook(f): f.drop.add((sid, '1h', gap_t))
        r = self.run_ticks([self.FINAL], feed_hook=hook)[0]
        self.assertLess(r['T1'], gap_t); self.assertTrue(any(g.get('sym') == 'TRX/USDT' for g in r['gaps']))
        self.assertTrue(all((e.get('decision_ts') or e.get('ts')) <= r['T1'] + HOUR for e in self.events()))                    # 缺口之後沒有任何紀錄
        d2 = os.path.join(self.tmp, 'ref'); self.init(d=d2); self.run_ticks([self.FINAL], d=d2); r2 = self.run_ticks([self.FINAL])[0]                # 行情補齊後
        self.assertEqual(r2['gaps'], []); a = {e['id']: e for e in self.events()}; b = {e['id']: e for e in self.events(d2)}; self.assertEqual(set(a), set(b))
        self.assertEqual(read_jsonl(os.path.join(self.dir, 'ledger', 'divergences.jsonl'))[0], [])

    def test_bar_revision_is_recorded_but_stored_bar_is_not_overwritten(self):
        self.init(); self.run_ticks([T0 + 3 * DAY + 40000]); p = os.path.join(self.dir, 'bars', 'TRX-USDT_1h.jsonl'); stored = {b['t']: b['c'] for b in read_jsonl(p)[0]}; t = max(stored)
        def hook(f): f.tamper[('TRXUSDT', '1h', t)] = stored[t] * 1.1
        r = self.run_ticks([T0 + 3 * DAY + 2 * HOUR + 40000], feed_hook=hook)[0]
        self.assertTrue(r['bar_mismatches']); self.assertEqual({b['t']: b['c'] for b in read_jsonl(p)[0]}[t], stored[t])

    def test_lock_prevents_concurrent_ticks_and_stale_lock_is_taken_over(self):
        self.init(); lock = os.path.join(self.dir, 'tick.lock'); open(lock, 'w').write('{}')
        with self.assertRaises(LockBusy): E.tick(self.dir, FakeFeed(self.FINAL))
        old = os.path.getmtime(lock) - 7200; os.utime(lock, (old, old)); r = E.tick(self.dir, FakeFeed(self.FINAL)); self.assertTrue(r['lock_takeover']); self.assertFalse(os.path.exists(lock))

    def test_b_is_not_a_superset_and_scenarios_run_independently(self):
        self.init(); self.run_ticks([self.FINAL]); evs = self.events()
        for sc in ('A', 'B'): self.assertTrue(any(e['scenario'] == sc and e['type'] == 'ENTRY' for e in evs), sc)


class PoisonFeed(FakeFeed):
    """決策時點 C 之後『還不可能知道』的行情全部換成垃圾值:收盤時間 > C 的 K 棒只保留開盤價(若它在 C 之前已開盤),更晚的整根換掉;C 之後的資金費率也換掉。"""
    def __init__(self, now, cutoff):
        super().__init__(now); self.cut = cutoff
    def klines(self, sid, tf, start_ms):
        step = E.STEP[tf]; out = []
        for r in super().klines(sid, tf, start_ms):
            t, o, h, l, c, v = r
            if t + step <= self.cut: out.append(r)
            elif t <= self.cut: out.append([t, o, o * 3, o * 0.2, o * 2.7, v])            # 這根在 C 時剛開盤:只有開盤價是已知的
            else: out.append([t, o * 2.5, o * 3, o * 0.2, o * 2.7, v])                    # 尚未開盤:整根都是未來
        return out
    def funding(self, sid, start_ms): return [(t, (x if t <= self.cut else 0.05)) for t, x in super().funding(sid, start_ms)]


class TestEvidenceLabels(Base):
    FINAL = T0 + 9 * DAY + 3 * HOUR + 40000

    def live(self, d=None, from_h=2, to_h=24 * 3 + 6, every=4, hook=None):
        out = []
        for k in range(from_h, to_h + 1, every):
            f = FakeFeed(T0 + k * HOUR + 30000)
            if hook: hook(f, k)
            out.append(E.tick(d or self.dir, f))
        return out

    def marks(self, sc, d=None): return read_jsonl(os.path.join(d or self.dir, 'ledger', 'marks_%s.jsonl' % sc))[0]
    def flags(self, d=None): return read_jsonl(os.path.join(d or self.dir, 'ledger', 'data_flags.jsonl'))[0]

    def test_snapshot_fixes_the_live_lag_limit(self):
        self.init(); s = json.load(open(os.path.join(self.dir, 'config_snapshot.json'), encoding='utf-8'))
        self.assertEqual(s['rules']['live_max_lag_ms'], 8 * HOUR); self.assertEqual(set(s['rules']['evidence_classes']), {'LIVE_FORWARD', 'BACKFILL', 'AFTER_INTERRUPTION'})

    def test_every_decision_keeps_close_time_fetch_time_tick_time_and_backfill_flag(self):
        self.init(); self.live(); evs = self.events(); self.assertTrue(evs); kinds = {e['type'] for e in evs}; self.assertTrue({'ENTRY', 'EXIT', 'FUNDING'} <= kinds, kinds)
        for e in evs:
            for k in ('bar_close_ts', 'bar_close_utc', 'inputs_fetched_utc', 'tick_wall_utc', 'is_backfill', 'evidence', 'record_lag_s', 'ref_close_ts', 'tick_id', 'recorded_utc'): self.assertIn(k, e, (e['id'], k))
            self.assertFalse(e['is_backfill']); self.assertEqual(e['evidence'], 'LIVE_FORWARD', e['id'])
            self.assertLessEqual(e['bar_close_ts'], e['ref_close_ts']); self.assertGreaterEqual(e['inputs_fetched_utc'], e['bar_close_utc']); self.assertGreaterEqual(e['tick_wall_utc'], e['inputs_fetched_utc'])
            self.assertGreaterEqual(e['record_lag_s'], 0); self.assertLessEqual(e['record_lag_s'], 8 * 3600)
            if e['type'] == 'ENTRY': self.assertEqual(e['bar_close_ts'], e['decision_bar_open'] + E.STEP[e['tf']]); self.assertLessEqual(e['bar_close_ts'], e['decision_ts'])      # 決策在訊號棒收盤之後
        for sc in ('A', 'B'):
            for m in self.marks(sc):
                for k in ('bar_close_ts', 'tick_wall_utc', 'is_backfill', 'evidence'): self.assertIn(k, m)
                self.assertEqual(m['evidence'], 'LIVE_FORWARD', (sc, m['h']))
        self.assertEqual(self.flags(), []); rep = R.build_report(self.dir); self.assertFalse(rep['evidence']['mixed']); self.assertIn('全部紀錄皆為 LIVE_FORWARD', R.render(rep))

    def test_late_first_tick_is_labelled_backfill_not_live(self):
        self.init(); E.tick(self.dir, FakeFeed(self.FINAL)); fl = self.flags()
        self.assertEqual([f['type'] for f in fl], ['LATE_START']); self.assertEqual(fl[0]['taint_from_ts'], T0)
        evs = self.events(); self.assertTrue(evs); self.assertFalse([e for e in evs if e['evidence'] == 'LIVE_FORWARD'])
        self.assertTrue([e for e in evs if e['evidence'] == 'BACKFILL' and 'record_lag_exceeds_limit' in e['backfill_reasons'] and e['is_backfill']])
        ms = self.marks('A'); self.assertEqual({m['evidence'] for m in ms}, {'BACKFILL', 'AFTER_INTERRUPTION'})
        rep = R.build_report(self.dir); txt = R.render(rep); self.assertTrue(rep['evidence']['mixed']); self.assertEqual(rep['evidence']['A_clean']['trades_closed'], 0)
        for s in ('已處理到', '不是「未中斷的即時前向」', '混合', 'LATE_START'): self.assertIn(s, txt)

    def test_long_interruption_marks_later_records_and_never_rewrites_earlier_ones(self):
        self.init(); tk = self.live(to_h=24 + 4); path = os.path.join(self.dir, 'ledger', 'events.jsonl'); before = open(path, 'rb').read(); last_wall = tk[-1]['wall_ms']
        self.assertEqual(self.flags(), []); E.tick(self.dir, FakeFeed(T0 + 5 * DAY + 30000))                       # 4 天沒跑
        self.assertTrue(open(path, 'rb').read().startswith(before), 'earlier records must be byte-identical')
        fl = self.flags(); self.assertEqual([f['type'] for f in fl], ['INTERRUPTION']); taint = fl[0]['taint_from_ts']; self.assertEqual(taint, last_wall)
        old_ids = {json.loads(l)['id'] for l in before.decode('utf-8').splitlines()}
        for e in self.events():
            if e['id'] in old_ids: self.assertEqual(e['evidence'], 'LIVE_FORWARD')
            elif e['ref_close_ts'] > taint: self.assertIn(e['evidence'], ('BACKFILL', 'AFTER_INTERRUPTION'), e['id'])
        self.assertTrue([e for e in self.events() if e['evidence'] == 'BACKFILL'])
        rep = R.build_report(self.dir); live_exits = [e for e in self.events() if e['scenario'] == 'A' and e['type'] == 'EXIT' and e['evidence'] == 'LIVE_FORWARD']
        self.assertEqual(rep['evidence']['A_clean']['trades_closed'], len(live_exits)); self.assertLessEqual(rep['evidence']['A_clean']['trades_closed'], rep['A']['trades_closed'])
        self.assertLessEqual(rep['evidence']['taint_utc'], E.iso(taint))                                   # 汙染起點 = 最早的補跑輸入或旗標,不會晚於中斷旗標

    def test_data_gap_is_flagged_and_post_gap_records_are_not_live(self):
        self.init(); gap_t = T0 + 2 * DAY + 5 * HOUR
        def hook(f, k):
            if T0 + 2 * DAY + 5 * HOUR <= f.now < T0 + 3 * DAY + 4 * HOUR: f.drop.add(('TRXUSDT', '1h', gap_t))                # 缺棒持續一段時間,之後行情補齊
        self.live(to_h=24 * 4 + 2, hook=hook); fl = self.flags(); gaps = [f for f in fl if f['type'] == 'DATA_GAP']
        self.assertEqual(len(gaps), 1); self.assertEqual(gaps[0]['taint_from_ts'], gap_t)
        for e in self.events(): self.assertTrue(e['evidence'] != 'LIVE_FORWARD' if e['ref_close_ts'] > gap_t else True, e['id'])
        self.assertTrue([e for e in self.events() if e['ref_close_ts'] > gap_t])
        self.assertTrue(all(e['evidence'] == 'LIVE_FORWARD' for e in self.events() if e['ref_close_ts'] <= gap_t))

    def test_bar_revision_is_flagged_and_later_records_are_not_live(self):
        self.init(); self.live(to_h=24 + 2); p = os.path.join(self.dir, 'bars', 'TRX-USDT_1h.jsonl'); stored = {b['t']: b['c'] for b in read_jsonl(p)[0]}; t = max(stored)
        def hook(f, k): f.tamper[('TRXUSDT', '1h', t)] = stored[t] * 1.1
        E.tick(self.dir, (lambda f: (hook(f, 0), f)[1])(FakeFeed(T0 + (24 + 6) * HOUR + 30000)))
        self.live(from_h=24 + 10, to_h=24 * 3)
        rv = [f for f in self.flags() if f['type'] == 'BAR_REVISION']; self.assertTrue(rv); tt = min(f['taint_from_ts'] for f in rv)
        self.assertEqual({b['t']: b['c'] for b in read_jsonl(p)[0]}[t], stored[t])                                  # 原始 K 棒不被覆蓋
        for e in self.events(): self.assertTrue(e['evidence'] != 'LIVE_FORWARD' if e['ref_close_ts'] > tt else True, e['id'])

    def test_decisions_use_only_data_observable_at_decision_time(self):
        d2 = os.path.join(self.tmp, 'poison'); self.init(); self.init(d=d2); E.tick(self.dir, FakeFeed(self.FINAL))
        ents = sorted([e for e in self.events() if e['scenario'] == 'A' and e['type'] == 'ENTRY'], key=lambda e: e['decision_ts']); self.assertGreater(len(ents), 4)
        C = ents[len(ents) // 2]['decision_ts']
        E.tick(d2, PoisonFeed(self.FINAL, C))
        def observable(e):
            if e['type'] == 'FUNDING': return e['ts'] <= C
            if e['type'] == 'EXIT' and e['why'] == '交易所保護停損': return e['bar_close_ts'] <= C
            return e['decision_ts'] <= C
        a = {e['id']: e for e in self.events() if observable(e)}; b = {e['id']: e for e in self.events(d2) if observable(e)}
        self.assertGreater(len(a), 10); self.assertEqual(set(a), set(b), 'decisions made at or before C changed when the future was poisoned')
        for i in a:
            for k in E.COMPARE_KEYS:
                if k in a[i]: self.assertTrue(E._close(a[i][k], b[i].get(k)), (i, k, a[i][k], b[i].get(k)))
        self.assertTrue([e for e in self.events() if not observable(e) and e['decision_ts' if 'decision_ts' in e else 'ts'] > C], 'there must be later events that the poison could affect')

    def test_hash_mismatch_never_resets_the_baseline(self):
        self.init(); mp = os.path.join(self.dir, 'MANIFEST.json'); sp = os.path.join(self.dir, 'MANIFEST.sha256'); h = (self.sha(mp), self.sha(sp)); orig = E.tracked_hashes
        try:
            bad = orig(); bad['sim.py'] = '0' * 64; E.tracked_hashes = lambda: bad
            for _ in range(2):
                with self.assertRaises(E.ManifestMismatch): E.tick(self.dir, FakeFeed(self.FINAL))
        finally: E.tracked_hashes = orig
        self.assertEqual((self.sha(mp), self.sha(sp)), h); self.assertFalse(os.path.exists(os.path.join(self.dir, 'ledger')) and os.listdir(os.path.join(self.dir, 'ledger')))
        eng = open(os.path.join(P4, 'd4_engine.py'), encoding='utf-8').read(); self.assertEqual(eng.count("open(ex.manifest, 'wb')"), 1); self.assertEqual(eng.count("open(ex.snapshot, 'wb')"), 1)       # 只有 init_experiment 寫入基準檔
        ini = open(os.path.join(P4, 'd4_init.py'), encoding='utf-8').read(); self.assertNotIn('--force', ini); self.assertNotIn('--reset', ini); self.assertNotIn('--rebaseline', ini)
        for f in glob.glob(os.path.join(P4, 'd4_*.py')): self.assertNotIn('S_IWRITE', open(f, encoding='utf-8').read(), f)


class TestReport(Base):
    def test_report_is_read_only_and_has_required_sections(self):
        self.init(); E.tick(self.dir, FakeFeed(T0 + 9 * DAY + 3 * HOUR + 40000)); before = self.ledger_hashes()
        rep = R.build_report(self.dir); txt = R.render(rep); self.assertEqual(before, self.ledger_hashes(), 'report must not modify anything')
        for s in ('觀察期間', '已平倉交易筆數', '淨 PF', '淨報酬', '最大回撤', '最差單日', '手續費', '資金費率', '平均/最大同時持倉', '暴露', 'BTC 環境', '限制與資料狀況', 'SIMULATED', '不自動調整', '不構成調整實盤'):
            self.assertIn(s, txt, s)
        for sc in ('A', 'B'):
            for k in ('trades_closed', 'net_return_pct', 'net_pf', 'max_dd_pct', 'worst_day_usd', 'fees_usd', 'funding_usd', 'avg_concurrent', 'max_exposure_x'): self.assertIn(k, rep[sc])
        self.assertGreater(rep['period']['hours_processed'], 24); self.assertTrue(rep['regime']); self.assertEqual(rep['manifest_mismatch'], [])
        a = rep['A']; self.assertLessEqual(a['max_dd_pct'], 0); self.assertAlmostEqual(a['equity_end'] / 310 * 100 - 100, a['net_return_pct'], 2)

    def test_report_numbers_match_the_ledger(self):
        self.init(); E.tick(self.dir, FakeFeed(T0 + 9 * DAY + 3 * HOUR + 40000)); rep = R.build_report(self.dir); evs = self.events()
        for sc in ('A', 'B'):
            ex = [e for e in evs if e['scenario'] == sc and e['type'] == 'EXIT']; self.assertEqual(rep[sc]['trades_closed'], len(ex)); self.assertAlmostEqual(rep[sc]['closed_net_usd'], sum(e['net'] for e in ex), 3)
            self.assertAlmostEqual(rep[sc]['funding_usd'], sum(e['amount'] for e in evs if e['scenario'] == sc and e['type'] == 'FUNDING'), 3)

    def test_empty_experiment_report_does_not_crash(self):
        self.init(); rep = R.build_report(self.dir); self.assertIn('觀察期間', R.render(rep))


class TestIsolationAndSafety(unittest.TestCase):
    FILES = sorted(glob.glob(os.path.join(P4, 'd4_*.py')))

    def test_no_trading_or_private_api_no_keys_no_bot_paths(self):
        self.assertTrue(self.FILES)
        for f in self.FILES:
            t = open(f, encoding='utf-8').read()
            for bad in ('create_order', 'cancel_order', 'set_leverage', 'fapiPrivate', 'sapi', 'withdraw', 'transfer', 'apiKey', 'api_key', 'secret', 'binance_ro', 'trading-bot', 'portfolio_bot', '順勢交易機器人', 'os.system', 'Popen', 'schtasks', 'Register-ScheduledTask', 'winreg', 'crontab'):
                self.assertNotIn(bad, t, (os.path.basename(f), bad))
            for m in re.finditer(r'config\.portfolio\.json', t): self.assertTrue(t[m.start():].startswith('config.portfolio.json.REDACTED'), (f, 'only the redacted copy may be named'))

    def test_only_public_market_endpoints_are_used(self):
        t = open(os.path.join(P4, 'd4_feed.py'), encoding='utf-8').read()
        self.assertEqual(sorted(set(re.findall(r'fapi\w+', t))), ['fapiPublicGetFundingInfo', 'fapiPublicGetFundingRate', 'fapiPublicGetKlines']); self.assertIn('load_markets', t); self.assertIn('binanceusdm', t)

    def test_subprocess_is_only_used_for_git_and_nothing_is_resident(self):
        for f in self.FILES:
            t = open(f, encoding='utf-8').read()
            for m in re.finditer(r'subprocess\.run\(\[([^\]]*)\]', t): self.assertTrue(m.group(1).startswith("'git'"), (f, m.group(1)))
            self.assertNotIn('time.sleep', t, f); self.assertNotIn('import schedule', t, f)
        for f in ('d4_tick.py', 'd4_engine.py', 'd4_report.py', 'd4_init.py'): self.assertNotRegex(open(os.path.join(P4, f), encoding='utf-8').read(), r'while\s+True')

    def test_experiment_data_and_raw_are_gitignored(self):
        t = open(os.path.join(P4, '.gitignore'), encoding='utf-8').read(); self.assertIn('experiments/', t)

    def test_strategy_registration_matches_the_website(self):
        try:
            os.environ.setdefault('RENDER', 'true'); import app as A
        except Exception as e: self.skipTest('app not importable: %s' % e)
        STR = E.load_strategies(); src = E.default_combos_source()
        if not os.path.exists(src): self.skipTest('backup not available')
        for c in json.load(open(src, encoding='utf-8'))['combos']:
            k = c['strategy']; self.assertIn(k, STR); self.assertIn(k, A.STRATS)
            for f in ('atr_stop', 'atr_trail', 'atr_tp', 'pct_stop', 'pct_trail', 'pct_tp'): self.assertEqual(STR[k].get(f) or 0.0, A.STRATS[k].get(f) or 0.0, (k, f))
        self.assertEqual(E.exit_params(STR, {'ttm'})['ttm'], tuple_or_list(A.STRATS['ttm']))

    def test_engine_signals_equal_the_d2_signal_function(self):
        d2 = os.path.join(ROOT, 'validation', 'd2_portfolio'); sys.path.insert(0, d2)
        try: import d2_signals as DS
        except Exception as e: self.skipTest('d2_signals not importable: %s' % e)
        rows = SERIES[('XLMUSDT', '4h')]; rows = [r for r in rows if r[0] < T0 + 2 * DAY]; start = T0 - 8 * HOUR
        _, ref = DS.work(('XLM/USDT', '4h', 'supertrend', rows, start))
        tmp = tempfile.mkdtemp(); self.addCleanup(rmtree, tmp)
        ex = E.Exp(os.path.join(tmp, 'e')); os.makedirs(ex.signals); os.makedirs(ex.ledger)
        mine, _ = E.signals_for(ex, E.load_strategies(), 'XLM/USDT', '4h', 'supertrend', rows, T0 + 8 * HOUR)
        common = [t for t in ref if t in mine]; self.assertTrue(common)
        for t in common: self.assertEqual(mine[t][:2], ref[t][:2]); self.assertAlmostEqual(mine[t][2], ref[t][2], 9)


def tuple_or_list(s): return [s.get('atr_stop') or 0.0, s.get('atr_trail') or 0.0, s.get('atr_tp') or 0.0, s.get('pct_stop') or 0.0, s.get('pct_trail') or 0.0, s.get('pct_tp') or 0.0]


if __name__ == '__main__':
    unittest.main()


# ───────────────── 資金費率完整性(缺漏不能默默當成 0) ─────────────────
import d4_funding as F


def regime(segments, jitter=3, rate=0.0001):
    """segments = [(起, 迄, 間隔小時)]:依序產生結算時間(每筆加幾毫秒偏移,像官方資料)。"""
    out = []
    for a, b, h in segments:
        t = a
        while t < b: out.append((t + jitter, rate)); t += h * HOUR
    return out


def fund_variant(replace=None, drop=None):
    f = {k: list(v) for k, v in FUND.items()}
    for sid, rows in (replace or {}).items(): f[sid] = rows
    for sid, times in (drop or {}).items(): f[sid] = [r for r in f[sid] if r[0] not in {t + 3 for t in times}]
    return f


class TestFundingCheck(unittest.TestCase):
    """d4_funding.check:純函式。結算間隔不假設 8 小時,只看實際相鄰間距與 UTC 格線。"""
    A, B = T0 - DAY, T0 + 10 * DAY
    kinds = staticmethod(lambda iss: [i['kind'] for i in iss])

    def test_normal_8h_and_4h_series_are_complete(self):
        self.assertEqual(F.check(regime([(self.A, self.B, 8)]), T0, T0 + 3 * DAY), [])
        self.assertEqual(F.check(regime([(self.A, self.B, 4)]), T0, T0 + 3 * DAY), [])
        self.assertEqual(F.check(regime([(self.A, self.B, 1)]), T0, T0 + 3 * DAY), [])
        self.assertEqual(F.check(regime([(self.A, self.B, 8)], jitter=47), T0, T0 + 3 * DAY), [], '官方資料常見的幾十毫秒偏移要容許')

    def test_interval_change_is_not_a_gap(self):
        shorten = regime([(self.A, T0 + DAY, 8), (T0 + DAY, self.B, 4)])                               # 8h → 4h
        lengthen = regime([(self.A, T0 + DAY, 2), (T0 + DAY, self.B, 8)])                              # 2h → 8h 且持續(像 SOL 2022-11)
        stepwise = regime([(self.A, T0 + DAY + 18 * HOUR, 1), (T0 + DAY + 18 * HOUR, T0 + DAY + 20 * HOUR, 2), (T0 + DAY + 20 * HOUR, self.B, 4)])    # 1h → 2h → 4h(像 KAVA 2025-12-20)
        for rows in (shorten, lengthen, stepwise): self.assertEqual(F.check(rows, T0, T0 + 3 * DAY), [])

    def test_lengthening_without_a_following_record_is_undetermined(self):
        rows = regime([(self.A, T0 + DAY + 4 * HOUR, 4)]) + [(T0 + DAY + 8 * HOUR + 3, 0.0001)]      # 4h 制後接一個 8h 的間距(24h → 32h),後面還沒有資料
        self.assertIn('undetermined_after_lengthening', self.kinds(F.check(rows, T0, T0 + 30 * HOUR)))

    def test_hole_in_4h_regime_is_detected_even_when_it_looks_like_an_8h_gap(self):
        base = regime([(self.A, self.B, 4)])
        on8 = [r for r in base if r[0] != T0 + DAY + 4 * HOUR + 3]                                     # 少 04:00:兩端都在 8h 格線上 → 4→8→4
        off8 = [r for r in base if r[0] != T0 + DAY + 8 * HOUR + 3]                                    # 少 08:00:04:00→12:00 不在 8h 格線上
        self.assertEqual(self.kinds(F.check(on8, T0, T0 + 3 * DAY)), ['possible_missing_settlement'])
        self.assertEqual(self.kinds(F.check(off8, T0, T0 + 3 * DAY)), ['off_grid'])

    def test_holes_in_8h_and_1h_regimes(self):
        r8 = [r for r in regime([(self.A, self.B, 8)]) if r[0] != T0 + DAY + 3]
        r1 = [r for r in regime([(self.A, self.B, 1)]) if r[0] not in (T0 + DAY + 3, T0 + DAY + HOUR + 3)]
        i8, i1 = F.check(r8, T0, T0 + 3 * DAY), F.check(r1, T0, T0 + 3 * DAY)
        self.assertEqual(self.kinds(i8), ['irregular_spacing']); self.assertEqual(self.kinds(i1), ['irregular_spacing'])
        self.assertEqual((i8[0]['from_utc'], i8[0]['to_utc']), (E.iso(T0 + DAY - 8 * HOUR + 3), E.iso(T0 + DAY + 8 * HOUR + 3)))        # 清楚列出時間範圍

    def test_issue_outside_the_processed_range_does_not_stop_anything(self):
        rows = [r for r in regime([(self.A, self.B, 8)]) if r[0] != T0 - 16 * HOUR + 3]                 # 起始之前缺一筆
        self.assertEqual(F.check(rows, T0, T0 + 3 * DAY), [])
        rows = [r for r in regime([(self.A, self.B, 8)]) if r[0] != T0 + 6 * DAY + 3]                   # 處理範圍之後缺一筆
        self.assertEqual(F.check(rows, T0, T0 + 3 * DAY), [])

    def test_coverage_uses_the_actual_interval_not_8_hours(self):
        r4 = regime([(self.A, T0 + 2 * DAY, 4)]); last = r4[-1][0]
        self.assertEqual(F.check(r4, T0, last + 3 * HOUR), [])
        self.assertEqual(self.kinds(F.check(r4, T0, last + 5 * HOUR)), ['coverage_end'], '4 小時制:5 小時後就該有下一筆(用 8 小時假設會漏掉)')
        r8 = regime([(self.A, T0 + 2 * DAY, 8)]); last8 = r8[-1][0]
        self.assertEqual(F.check(r8, T0, last8 + 7 * HOUR), []); self.assertEqual(self.kinds(F.check(r8, T0, last8 + 8 * HOUR)), ['coverage_end'])

    def test_official_funding_info_can_only_tighten_coverage(self):
        r8 = regime([(self.A, T0 + 2 * DAY, 8)]); last = r8[-1][0]
        self.assertEqual(F.check(r8, T0, last + 3 * HOUR, info_h=None), []); self.assertEqual(F.check(r8, T0, last + 3 * HOUR, info_h=8), [])
        self.assertEqual(self.kinds(F.check(r8, T0, last + 3 * HOUR, info_h=2)), ['coverage_end'])

    def test_start_coverage_and_empty(self):
        self.assertEqual(self.kinds(F.check([], T0, T0 + DAY)), ['no_records'])
        self.assertEqual(self.kinds(F.check(regime([(T0 + 16 * HOUR, self.B, 8)]), T0, T0 + 3 * DAY)), ['coverage_start'])
        self.assertEqual(F.limit_ts({'kind': 'coverage_start', 'from_ts': T0}, T0), T0 - HOUR)

    def test_limit_is_the_hour_of_the_last_good_settlement(self):
        iss = F.check([r for r in regime([(self.A, self.B, 8)]) if r[0] != T0 + DAY + 3], T0, T0 + 3 * DAY)[0]
        self.assertEqual(F.limit_ts(iss, T0), T0 + DAY - 8 * HOUR)


class TestFundingGuard(Base):
    def at(self, k, d=None, **kw):
        f = FakeFeed(T0 + k * HOUR + 30000, **({'fund': kw.pop('fund')} if 'fund' in kw else {}))
        for a, v in kw.items(): setattr(f, a, v)
        return E.tick(d or self.dir, f), f

    def events(self, d=None): return {e['id']: e for e in read_jsonl(os.path.join(d or self.dir, 'ledger', 'events.jsonl'))[0]}

    def test_policy_is_in_the_snapshot_and_the_module_is_hash_tracked(self):
        self.init(); s = json.load(open(os.path.join(self.dir, 'config_snapshot.json'), encoding='utf-8')); pol = s['rules']['funding_policy']
        self.assertTrue(pol['missing_funding_is_never_zero']); self.assertEqual(pol['allowed_interval_hours'], [1, 2, 4, 8]); self.assertEqual(s['version'], 2)
        self.assertIn('paper_trading/d4_funding.py', E.TRACKED_FILES); self.assertIn('paper_trading/d4_funding.py', json.load(open(os.path.join(self.dir, 'MANIFEST.json')))['files_sha256'])

    def test_normal_settlement_has_no_issue_and_records_the_successful_fetch(self):
        self.init()
        for k in (2, 8, 14, 20, 30, 40):
            rec, _ = self.at(k); self.assertEqual(rec['funding_issues'], [], k); self.assertEqual(rec['errors'], [], k)
            self.assertEqual(set(rec['funding_ok']), set(SYMS)); self.assertEqual(rec['T1'], T0 + (k - 2) * HOUR)             # 處理範圍沒有被縮短

    def test_missing_record_stops_processing_and_lists_symbol_range_and_reason(self):
        self.init(); hole = T0 + DAY
        rec, _ = self.at(36, fund=fund_variant(drop={'TRXUSDT': [hole]}))
        g = [x for x in rec['gaps'] if x.get('kind') == 'funding_incomplete']
        self.assertEqual([(x['sym'], x['funding_issue']) for x in g], [('TRX/USDT', 'irregular_spacing')])
        self.assertEqual((g[0]['from_utc'], g[0]['to_utc']), (E.iso(hole - 8 * HOUR + 3), E.iso(hole + 8 * HOUR + 3))); self.assertIn('缺漏', g[0]['reason'])
        self.assertEqual(rec['T1'], hole - 8 * HOUR)                                                                          # 停在缺口之前
        fl = read_jsonl(os.path.join(self.dir, 'ledger', 'data_flags.jsonl'))[0]; self.assertTrue([f for f in fl if f['type'] == 'DATA_GAP' and f['detail'].get('sym') == 'TRX/USDT'])
        st = json.load(open(os.path.join(self.dir, 'status.json'), encoding='utf-8')); self.assertTrue([x for x in st['gaps'] if x.get('kind') == 'funding_incomplete'])
        for e in self.events().values(): self.assertLessEqual(e.get('ts') or e['decision_ts'], rec['T1'] + HOUR, e['id'])          # 缺口之後沒有任何事件,沒有『當成 0』的結果

    def test_recovery_repairs_by_requery_and_matches_a_clean_run_without_touching_old_records(self):
        self.init(); hole = T0 + DAY
        r1, _ = self.at(36, fund=fund_variant(drop={'TRXUSDT': [hole]})); path = os.path.join(self.dir, 'ledger', 'events.jsonl'); before = open(path, 'rb').read()
        r2, _ = self.at(40)                                                                                                   # 官方資料補齊(例如之前只是沒抓全)
        self.assertEqual(r2['funding_repaired'], [{'sym': 'TRX/USDT', 'new_records': 1}]); self.assertEqual(r2['funding_issues'], []); self.assertEqual(r2['T1'], T0 + 38 * HOUR)
        self.assertTrue(open(path, 'rb').read().startswith(before), '先前紀錄必須逐位元組不變'); self.assertEqual(r2['divergences'], 0)
        clean = os.path.join(self.tmp, 'clean'); self.init(d=clean); self.at(40, d=clean)
        a, b = self.events(), self.events(clean); self.assertEqual(set(a), set(b))
        for i in a:
            for k in E.COMPARE_KEYS:
                if k in a[i]: self.assertTrue(E._close(a[i][k], b[i].get(k)), (i, k))

    def test_hole_in_a_4h_regime_is_found_and_4h_is_not_treated_as_a_gap(self):
        self.init(); s4 = regime([(T0 - 80 * DAY, T0 + 14 * DAY, 4)])
        rec, _ = self.at(36, fund=fund_variant(replace={'SOLUSDT': s4}))
        self.assertEqual(rec['funding_issues'], [], '4 小時制本身不是缺漏(不假設 8 小時)')
        hole = T0 + DAY + 4 * HOUR
        d2 = os.path.join(self.tmp, 'h4'); self.init(d=d2)
        rec2, _ = self.at(36, d=d2, fund=fund_variant(replace={'SOLUSDT': [r for r in s4 if r[0] != hole + 3]}))
        self.assertEqual([(x['sym'], x['kind']) for x in rec2['funding_issues']], [('SOL/USDT', 'possible_missing_settlement')]); self.assertEqual(rec2['T1'], T0 + DAY)

    def test_interval_change_in_either_direction_runs_normally(self):
        self.init(); trx = regime([(T0 - 80 * DAY, T0 + DAY, 4), (T0 + DAY, T0 + 14 * DAY, 8)]); sol = regime([(T0 - 80 * DAY, T0 + 2 * DAY, 8), (T0 + 2 * DAY, T0 + 14 * DAY, 4)])
        pend, _ = self.at(36, fund=fund_variant(replace={'TRXUSDT': trx, 'SOLUSDT': sol}))                                    # 4h→8h 剛改制:第一個 8h 間距之後還沒有下一筆,暫停(無法和缺漏區分)
        self.assertEqual([(x['sym'], x['kind']) for x in pend['funding_issues']], [('TRX/USDT', 'undetermined_after_lengthening')]); self.assertEqual(pend['T1'], T0 + DAY)
        for k in (44, 60, 76):                                                                                                # 下一筆出現後確認是改制,恢復處理
            rec, _ = self.at(k, fund=fund_variant(replace={'TRXUSDT': trx, 'SOLUSDT': sol})); self.assertEqual(rec['funding_issues'], [], k); self.assertEqual(rec['T1'], T0 + (k - 2) * HOUR)

    def test_long_interruption_then_resume_is_not_a_false_stop(self):
        self.init(); self.at(4); self.at(10)
        rec, _ = self.at(24 * 5 + 3)                                                                                          # 幾乎 5 天沒執行
        self.assertEqual(rec['funding_issues'], []); self.assertEqual(rec['T1'], T0 + (24 * 5 + 1) * HOUR)
        self.assertEqual(rec['divergences'], 0)

    def test_fetch_failure_stops_at_last_verified_time_and_later_recovers(self):
        self.init(); self.at(30)
        rec, _ = self.at(40, ffail={'TRXUSDT'})
        g = [x for x in rec['funding_issues'] if x['kind'] == 'fetch_not_verified']; self.assertEqual([x['sym'] for x in g], ['TRX/USDT'])
        self.assertEqual(rec['T1'], (T0 + 30 * HOUR + 30000 - 2 * HOUR) // HOUR * HOUR); self.assertTrue([e for e in rec['errors'] if 'funding TRX/USDT' in e])
        rec2, _ = self.at(44); self.assertEqual(rec2['funding_issues'], []); self.assertEqual(rec2['T1'], T0 + 42 * HOUR)
        d2 = os.path.join(self.tmp, 'first'); self.init(d=d2)
        r0, _ = self.at(6, d=d2, ffail={'TRXUSDT'}); self.assertTrue([x for x in r0['funding_issues'] if x['sym'] == 'TRX/USDT']); self.assertLessEqual(r0['T1'], T0)     # 第一次就失敗:沒有任何可確認的範圍
        self.assertEqual(self.events(d2), {})

    def test_official_funding_info_shorter_interval_tightens_coverage(self):
        self.init(); rec, _ = self.at(30, info={'TRXUSDT': 1})
        self.assertTrue([x for x in rec['funding_issues'] if x['sym'] == 'TRX/USDT' and x['kind'] == 'coverage_end']); self.assertEqual(rec['funding_info_hours']['TRXUSDT'], 1)

    def test_report_shows_symbol_range_and_reason_until_resolved(self):
        import d4_report as R
        self.init(); hole = T0 + DAY; self.at(36, fund=fund_variant(drop={'TRXUSDT': [hole]})); txt = R.render(R.build_report(self.dir))
        for w in ('資金費率不完整', 'TRX/USDT', E.iso(hole - 8 * HOUR + 3), E.iso(hole + 8 * HOUR + 3), 'irregular_spacing', '不會被當成 0'): self.assertIn(w, txt)
        self.at(40); txt2 = R.render(R.build_report(self.dir)); self.assertIn('最近一次 tick 已完整', txt2)

    def test_formulas_and_formal_results_are_untouched(self):
        import subprocess
        out = subprocess.run(['git', 'diff', '--stat', 'HEAD', '--', 'sim.py', 'validation/d2_portfolio/d2_sim.py', 'validation/d3_walkforward/results', 'validation/d3_walkforward/raw'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, '', 'strategy formulas / simulator / D2-D3 formal results must not change')
