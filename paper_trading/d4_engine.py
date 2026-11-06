# -*- coding: utf-8 -*-
"""D4 前向紙上交易引擎(離線模擬,與實盤完全隔離)。
- 計算邏輯 = D2 已校準的模擬器(validation/d2_portfolio/d2_sim.py);這裡只負責:實驗快照/雜湊驗證、只收『已收盤』K 棒、逐棒訊號快取、
  以『確定性重播』產生事件、把事件 append 到不可覆寫的帳本(同一事件 id 不會重複記帳;重跑只會比對,不一致就另記 DIVERGENCE,不覆蓋原始紀錄)。
- 不讀取交易所金鑰、不呼叫任何私有/寫入 API、不讀寫機器人資料夾。
"""
import bisect, datetime, json, os, platform, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, 'validation', 'd2_portfolio')); sys.path.insert(0, ROOT)
import d2_sim as S
import d4_funding as FUND
from d4_store import FileLock, append_jsonl, dumps, read_jsonl, read_jsonl_ro, sha256_bytes, sha256_file

HOUR = 3600000; STEP = {'1h': HOUR, '4h': 4 * HOUR}
WARMUP_BARS = 420                                  # 策略每輪用最近 400 根;多留一點
FUNDING_LAG_MS = 2 * HOUR                          # 處理範圍落後 2 小時,確保該段資金費率已公布
LIVE_MAX_LAG_MS = 8 * HOUR                         # 即時前向的容許延遲(2 小時結構性延遲 + 6 小時 tick 間隔);超過 = 補跑(BACKFILL)。寫進快照、受雜湊保護
REF_SYMBOL = 'BTC/USDT'                            # 只用來分類市場環境,不交易
INTEGRATION_FILES = ['extra_strats.py', 'extra_strats_v3.py', 'extra_strats_v4.py', 'extra_strats_v5.py', 'extra_strats_v6.py', 'extra_strats_v7.py', 'extra_strats_v8.py', 'extra_strats_v9.py', 'extra_strats_loop.py']
TRACKED_FILES = ['sim.py'] + ['integration/' + f for f in INTEGRATION_FILES] + ['validation/d2_portfolio/d2_sim.py', 'paper_trading/d4_store.py', 'paper_trading/d4_feed.py', 'paper_trading/d4_funding.py', 'paper_trading/d4_engine.py', 'paper_trading/d4_tick.py']
PARAMS = {'risk': 0.0403, 'max_lev': 3.0, 'max_lev_int': 3, 'max_total': 3.0, 'taker': 0.0005, 'slip_entry': 0.0003, 'slip_exit': 0.0001, 'slip_stop': 0.00042, 'latency_s': 13.8, 'sumw_override': 16.0}
INIT_EQUITY = 310.0
B_EXCLUDED = ['TRX/USDT|1h|tsmom', 'XRP/USDT|1h|vortex']
BACKUP_ROOT = r'C:\Users\User\發大財\研究備份_D2'


class ManifestMismatch(RuntimeError):
    pass


def iso(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
def key_of(c): return '%s|%s|%s' % (c['symbol'], c['timeframe'], c['strategy'])


# ───────────────── 策略(與網站 app.py 的註冊方式相同,不匯入網站) ─────────────────
def load_strategies():
    integ = os.path.join(ROOT, 'integration')
    if integ not in sys.path: sys.path.insert(0, integ)
    import sim
    STR = {k: dict(v) for k, v in sim.STRATS.items()}
    from extra_strats import EXTRA_STRATS as V1
    from extra_strats_v3 import EXTRA_STRATS_V3
    from extra_strats_v4 import EXTRA_STRATS_V4
    from extra_strats_v5 import EXTRA_STRATS_V5
    from extra_strats_v6 import EXTRA_STRATS_V6
    from extra_strats_v7 import EXTRA_STRATS_V7
    from extra_strats_v8 import EXTRA_STRATS_V8
    from extra_strats_v9 import EXTRA_STRATS_V9
    from extra_strats_loop import EXTRA_STRATS_LOOP

    def wrap(fn):
        def build(O, H, L, C, V, tf):
            out = fn(O, H, L, C, V, tf)
            return (out[0], out[1]) if isinstance(out, tuple) and len(out) == 4 else out
        return build
    for pool in (V1, EXTRA_STRATS_V3, EXTRA_STRATS_V4, EXTRA_STRATS_V5, EXTRA_STRATS_V6, EXTRA_STRATS_V7, EXTRA_STRATS_V8, EXTRA_STRATS_V9, EXTRA_STRATS_LOOP):
        for code, meta in pool.items():
            if not meta.get('build') or code in STR: continue
            STR[code] = dict(name=meta.get('name', code), build=wrap(meta['build']), atr_stop=0.0, atr_trail=0.0, atr_tp=0.0, pct_stop=0.025, pct_tp=0.075, min_bars=int(meta.get('min_bars') or 0))
    return STR


def exit_params(STR, strats):
    out = {}
    for k in strats:
        s = STR[k]; out[k] = [s.get('atr_stop') or 0.0, s.get('atr_trail') or 0.0, s.get('atr_tp') or 0.0, s.get('pct_stop') or 0.0, s.get('pct_trail') or 0.0, s.get('pct_tp') or 0.0]
    return out


# ───────────────── 實驗目錄 ─────────────────
class Exp:
    def __init__(self, d):
        self.dir = os.path.abspath(d)
        j = lambda *p: os.path.join(self.dir, *p)
        self.manifest = j('MANIFEST.json'); self.manifest_sha = j('MANIFEST.sha256'); self.snapshot = j('config_snapshot.json')
        self.bars = j('bars'); self.funding = j('funding'); self.signals = j('signals'); self.ledger = j('ledger'); self.reports = j('reports')
        self.events = j('ledger', 'events.jsonl'); self.ticks = j('ledger', 'ticks.jsonl'); self.diverge = j('ledger', 'divergences.jsonl'); self.corrupt = j('ledger', 'corrupt_lines.jsonl')
        self.lock = j('tick.lock'); self.status = j('status.json'); self.flags = j('ledger', 'data_flags.jsonl')

    def marks(self, scen): return os.path.join(self.ledger, 'marks_%s.jsonl' % scen)
    def bar_file(self, sym, tf): return os.path.join(self.bars, '%s_%s.jsonl' % (sym.replace('/', '-'), tf))
    def fund_file(self, sym): return os.path.join(self.funding, '%s.jsonl' % sym.replace('/', '-'))
    def sig_file(self, key): return os.path.join(self.signals, '%s.jsonl' % key.replace('/', '-').replace('|', '_'))

    def load_snapshot(self): return json.load(open(self.snapshot, encoding='utf-8'))


def tracked_hashes():
    return {f: (sha256_file(os.path.join(ROOT, f)) if os.path.exists(os.path.join(ROOT, f)) else None) for f in TRACKED_FILES}


def git_info():
    try:
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        dirty = bool(subprocess.run(['git', 'status', '--porcelain', '--', 'sim.py', 'integration', 'validation/d2_portfolio/d2_sim.py', 'paper_trading'], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip())
        return {'head': head, 'tracked_paths_dirty': dirty}
    except Exception as e:
        return {'error': str(e)[:80]}


def default_combos_source():
    import glob
    d = sorted(glob.glob(os.path.join(BACKUP_ROOT, '2*')))[-1]
    return os.path.join(d, 'config.portfolio.json.REDACTED.json')


def build_snapshot(exp_id, start_ms, combos, markets, created_ms, source_info):
    STR = load_strategies()
    A = [{'symbol': c['symbol'], 'timeframe': c['timeframe'], 'strategy': c['strategy'], 'weight': c.get('weight', 1)} for c in combos]
    for c in A: assert c['strategy'] in STR, c
    Bc = [c for c in A if key_of(c) not in B_EXCLUDED]
    assert len(Bc) == len(A) - len(B_EXCLUDED), 'B must exclude exactly the two 1H combos'
    syms = sorted({c['symbol'] for c in A})
    return {'experiment_id': exp_id, 'version': 2, 'created_utc': iso(created_ms), 'start_ts': int(start_ms), 'start_utc': iso(start_ms), 'initial_equity': INIT_EQUITY,
            'scenarios': {'A': {'label': 'A 維持目前全部 23 組', 'combos': A, 'sumw': sum(c['weight'] for c in A)},
                          'B': {'label': 'B 排除 TRX 1H、XRP 1H(其餘 21 組配置/風險參數/資金分配公式不變;Σ權重沿用 A 的 16,與 D3 相同)', 'combos': Bc, 'sumw': sum(c['weight'] for c in A), 'excluded': B_EXCLUDED}},
            'params': dict(PARAMS), 'exit_params': exit_params(STR, {c['strategy'] for c in A}), 'symbols': syms, 'reference_symbol': REF_SYMBOL, 'markets': markets,
            'data_source': {'exchange': 'Binance USDT-M perpetual (fapi, public endpoints only)', 'klines': '/fapi/v1/klines', 'funding': '/fapi/v1/fundingRate', 'closed_bars_only': True, 'safety_ms': 5000, 'funding_lag_ms': FUNDING_LAG_MS, 'warmup_bars': WARMUP_BARS},
            'rules': {'live_max_lag_ms': LIVE_MAX_LAG_MS, 'evidence_classes': {'LIVE_FORWARD': '即時前向:記帳時距離最後輸入 K 棒收盤 ≤ live_max_lag_ms,且之前沒有中斷/缺口/修訂/補跑', 'BACKFILL': '補跑:記帳或取得行情時已超過 live_max_lag_ms', 'AFTER_INTERRUPTION': '中斷/缺口/修訂/補跑之後才記的決策(路徑已受影響,不是未中斷的即時證據)'}, 'funding_policy': {'completeness_check': True, 'allowed_interval_hours': list(FUND.ALLOWED_H), 'grid_tolerance_ms': FUND.TOL_MS, 'missing_funding_is_never_zero': True, 'on_incomplete': 'stop processing before the gap; list symbol, time range and reason; never skip or fabricate', 'fetch_failed': 'process only through last successful fetch minus funding_lag_ms', 'info_endpoint': '/fapi/v1/fundingInfo (current interval, cross-check only)'}, 'warmup_not_counted': '開始時間之前的 K 棒只用於指標暖機,所有績效從 start_ts 起算;開始時全部空手。', 'same_bars_for_A_and_B': True, 'no_live_connection': True, 'fills': 'SIMULATED(下一根 1H 開盤價 × (1+滑價));與市場實際價的差異另行記錄'},
            'config_source': source_info}


def init_experiment(exp_dir, exp_id, start_ms, combos, markets, created_ms, source_info, allow_past=False):
    import stat
    ex = Exp(exp_dir)
    if os.path.exists(ex.dir): raise FileExistsError('experiment directory already exists (never overwritten): %s' % ex.dir)
    if start_ms % HOUR: raise ValueError('start must be on a UTC hour boundary')
    if not allow_past and start_ms < created_ms: raise ValueError('start must not be in the past for a forward experiment (use a later --start)')
    snap = build_snapshot(exp_id, start_ms, combos, markets, created_ms, source_info)
    for d in (ex.dir, ex.bars, ex.funding, ex.signals, ex.ledger, ex.reports): os.makedirs(d)
    sb = dumps(snap).encode('utf-8')
    with open(ex.snapshot, 'wb') as f: f.write(sb)
    man = {'experiment_id': exp_id, 'version': 2, 'created_utc': iso(created_ms), 'start_utc': iso(start_ms), 'snapshot_sha256': sha256_bytes(sb), 'markets_sha256': sha256_bytes(dumps(markets).encode('utf-8')),
           'files_sha256': tracked_hashes(), 'python': platform.python_version(), 'git': git_info(), 'rule': '任何一個雜湊不符,tick 會拒絕執行;要修改必須建立新的實驗版本(新目錄),不得覆蓋本紀錄。'}
    mb = json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True).encode('utf-8'); open(ex.manifest, 'wb').write(mb); open(ex.manifest_sha, 'w').write(sha256_bytes(mb) + '\n')
    for p in (ex.snapshot, ex.manifest, ex.manifest_sha):
        os.chmod(p, stat.S_IREAD)                                                # 唯讀旗標(防誤改,不是安全機制)
    return man


def verify_manifest(ex):
    """回傳不符清單;空清單 = 一致。檢查:MANIFEST 自身雜湊、快照雜湊、所有追蹤檔案(策略/模擬器/紙上交易程式)的雜湊。"""
    bad = []
    mb = open(ex.manifest, 'rb').read()
    if sha256_bytes(mb) != open(ex.manifest_sha).read().strip(): bad.append('MANIFEST.json')
    man = json.loads(mb.decode('utf-8'))
    if sha256_file(ex.snapshot) != man['snapshot_sha256']: bad.append('config_snapshot.json')
    now = tracked_hashes()
    for f, h in man['files_sha256'].items():
        if now.get(f) != h: bad.append(f)
    return bad


# ───────────────── K 棒儲存(只收已收盤;重疊部分只比對、不覆蓋) ─────────────────
def load_bars(ex, sym, tf, readonly=False):
    recs = read_jsonl_ro(ex.bar_file(sym, tf)) if readonly else read_jsonl(ex.bar_file(sym, tf), ex.corrupt)[0]; step = STEP[tf]
    rows = {r['t']: [r['t'], r['o'], r['h'], r['l'], r['c'], r['v']] for r in recs if r['fetched_at'] >= r['t'] + step}      # 排除任何『收盤前就被記下』的 K 棒(不應發生;防未來資料)
    return [rows[t] for t in sorted(rows)]                                  # 依時間排序(補抓的缺口棒是附加在檔尾的)


def store_bars(ex, sym, tf, rows, fetched_ms):
    step = STEP[tf]; have, _ = read_jsonl(ex.bar_file(sym, tf), ex.corrupt); idx = {r['t']: r for r in have}; new = []; mism = []
    for t, o, h, l, c, v in rows:
        if t + step > fetched_ms: continue                                     # 尚未收盤
        if t in idx:
            r = idx[t]
            if (r['o'], r['h'], r['l'], r['c']) != (o, h, l, c): mism.append({'sym': sym, 'tf': tf, 't': t, 'stored': [r['o'], r['h'], r['l'], r['c']], 'fetched': [o, h, l, c]})
        else: new.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'fetched_at': fetched_ms})
    append_jsonl(ex.bar_file(sym, tf), sorted(new, key=lambda r: r['t']))
    return len(new), mism


def store_funding(ex, sym, rows, fetched_ms):
    have, _ = read_jsonl(ex.fund_file(sym), ex.corrupt); seen = {r['t'] for r in have}
    new = [{'t': t, 'rate': r, 'fetched_at': fetched_ms} for t, r in rows if t not in seen]
    append_jsonl(ex.fund_file(sym), sorted(new, key=lambda r: r['t'])); return len(new)


def load_funding(ex, sym):
    recs, _ = read_jsonl(ex.fund_file(sym), ex.corrupt); return sorted((r['t'], r['rate']) for r in recs)


def _last_funding_ok(prev_ticks, sym):
    for t in reversed(prev_ticks):
        v = (t.get('funding_ok') or {}).get(sym)
        if v: return v
    return None


def funding_guard(ex, feed, snap, T0, T1, now, fund_ok, prev_ticks, finfo, rec):
    """資金費率完整性:缺漏不能被模擬器當成 0。檢查每個交易符號的結算紀錄(見 d4_funding.py);有問題先向官方重新要一次(只附加沒有的紀錄),
    仍有問題就回報並讓處理範圍停在缺口之前。回傳 (新的 T1, 問題清單)。不改任何既有紀錄。"""
    T0h = T0 - T0 % HOUR; out = []
    if T1 < T0h: return T1, out                                                  # 還在暖機,沒有處理範圍
    for s in snap['symbols']:
        sid = snap['markets'].get(s, {}).get('id') or s.replace('/', ''); info_h = (finfo or {}).get(sid)
        proven = (now if s in fund_ok else _last_funding_ok(prev_ticks, s))
        proven = proven - FUNDING_LAG_MS if proven else None
        T1c = min(T1, proven) if proven is not None else T1                      # 只能確認到『最後一次成功取得』的範圍;超過的部分另列 fetch_not_verified
        rows = load_funding(ex, s); iss = FUND.check(rows, T0, T1c, info_h)
        req = [i for i in iss if i['kind'] in FUND.REQUERY_KINDS]
        if req:
            try:
                n = store_funding(ex, s, feed.funding(sid, min(i['from_ts'] for i in req) + 1), now)
                if n: rec['funding_repaired'].append({'sym': s, 'new_records': n})
            except Exception as e: rec['errors'].append('funding requery %s: %s' % (s, str(e)[:100]))
            iss = FUND.check(load_funding(ex, s), T0, T1c, info_h)
        if proven is None or proven < T1:
            a = proven if proven is not None else T0
            iss.append({'kind': 'fetch_not_verified', 'from_ts': int(a), 'to_ts': int(T1), 'from_utc': iso(a), 'to_utc': iso(T1), 'detail': '這次沒有成功取得資金費率;只能確認到上次成功取得的時間 − %d 小時' % (FUNDING_LAG_MS // HOUR)})
        out += [dict(i, sym=s) for i in iss]
    for i in out: T1 = min(T1, FUND.limit_ts(i, T0))
    return T1, out


def first_hole(rows, step):
    """已存 K 棒(依時間遞增)中第一個缺口的開盤時間;沒有缺口 → 最後一根(重疊一根只做比對)。"""
    ts = [r[0] for r in rows]
    for a, b in zip(ts, ts[1:]):
        if b - a != step: return a + step
    return ts[-1]


def last_contiguous(times, step, from_ts):
    """times(已排序、去重)中,從 from_ts 起連續不缺的最後一根開盤時間;from_ts 本身缺就回 from_ts − step。"""
    s = set(times); t = from_ts
    if t not in s: return from_ts - step
    while (t + step) in s: t += step
    return t


# ───────────────── 逐棒訊號(以該棒結尾的 400 根視窗;append-only 快取) ─────────────────
def signals_for(ex, STR, sym, tf, strat, rows, T0):
    key = '%s|%s|%s' % (sym, tf, strat); step = STEP[tf]
    cached, _ = read_jsonl(ex.sig_file(key), ex.corrupt); out = {r['t']: (r['el'], r['xl'], r['atr']) for r in cached}
    import sim
    new = []; s = STR[strat]; first_needed = T0 - 2 * step; gaps = 0
    for i in range(399, len(rows)):
        t = rows[i][0]
        if t < first_needed or t in out: continue
        w = rows[i - 399:i + 1]
        if w[-1][0] - w[0][0] != 399 * step: gaps += 1; continue              # 視窗內有缺棒 → 不產生訊號(不用不完整的資料)
        O = [r[1] for r in w]; H = [r[2] for r in w]; L = [r[3] for r in w]; C = [r[4] for r in w]; V = [r[5] for r in w]
        try: res = s['build'](O, H, L, C, V, tf); el, xl = bool(res[0][-1]), bool(res[1][-1])
        except Exception: continue
        atr = sim.atr(H, L, C, 14)[-1]
        new.append({'t': t, 'el': el, 'xl': xl, 'atr': atr}); out[t] = (el, xl, atr)
    append_jsonl(ex.sig_file(key), new)
    return out, gaps


# ───────────────── 事件(由確定性重播導出) ─────────────────
def _r(x): return None if x is None else round(float(x), 10)


def derive_events(scen, res, M, snap):
    taker = snap['params']['taker']; ev = []

    def cdl(sym, ts):
        c = M.candle(sym, ts - ts % HOUR); return c
    def fill_info(sym, ts, fill, exp):
        c = cdl(sym, ts)
        d = {'expected_px': _r(exp), 'sim_fill': _r(fill), 'label': 'SIMULATED'}
        if c: d.update(market_open=_r(c[0]), candle_high=_r(c[1]), candle_low=_r(c[2]), fill_within_candle_range=bool(c[2] <= fill <= c[1]), slip_vs_market_open_pct=_r((fill / c[0] - 1) * 100))
        if exp: d['slip_vs_expected_pct'] = _r((fill / exp - 1) * 100)
        return d

    def entry(key, sym, tf, ts, qty, fill, sig, fee, stop=None, tp=None):
        step = STEP[tf]; bc = ts - ts % step
        e = {'type': 'ENTRY', 'scenario': scen, 'key': key, 'sym': sym, 'tf': tf, 'decision_ts': int(ts), 'decision_bar_open': int(bc - step), 'qty': _r(qty), 'fee': _r(fee), 'id': '%s|ENTRY|%s|%d' % (scen, key, ts)}
        e.update(fill_info(sym, ts, fill, sig)); return e
    for t in res['trades']:
        ev.append(entry(t['key'], t['sym'], t['tf'], t['entry_ts'], t['qty'], t['entry_fill'], t['sig_px'], t['qty'] * t['entry_fill'] * taker))
        x = {'type': 'EXIT', 'scenario': scen, 'key': t['key'], 'sym': t['sym'], 'tf': t['tf'], 'entry_ts': int(t['entry_ts']), 'decision_ts': int(t['exit_ts']), 'qty': _r(t['qty']), 'why': t['why'], 'decision_bar_open': (int(t['exit_bar_ts']) if t.get('exit_bar_ts') is not None else None), 'gross': _r(t['gross']), 'fees': _r(t['fees']), 'funding': _r(t['funding']), 'net': _r(t['net']),
             'id': '%s|EXIT|%s|%d' % (scen, t['key'], t['entry_ts'])}
        x.update(fill_info(t['sym'], t['exit_ts'], t['exit_fill'], t.get('exit_exp_px'))); ev.append(x)
    for p in res['open_detail']:
        e = entry(p['key'], p['sym'], p['tf'], p['entry_ts'], p['qty'], p['fill'], p['entry_sig'], p['fee_in']); e['stop'] = _r(p['stop']); e['tp'] = _r(p['tp']); ev.append(e)
    for f in res['funding_log']:
        ev.append({'type': 'FUNDING', 'scenario': scen, 'key': f['key'], 'ts': int(f['ts']), 'rate': _r(f['rate']), 'amount': _r(f['amount']), 'id': '%s|FUNDING|%s|%d' % (scen, f['key'], f['ts'])})
    for (tau, key, reason) in res['reject_log']:
        ev.append({'type': 'REJECT', 'scenario': scen, 'key': key, 'decision_ts': int(tau), 'reason': reason, 'id': '%s|REJECT|%s|%d|%s' % (scen, key, tau, reason)})
    return ev


COMPARE_KEYS = ('decision_ts', 'qty', 'sim_fill', 'expected_px', 'net', 'fees', 'amount', 'rate', 'why', 'reason', 'ts')


# ───────────────── 證據分類:即時前向 / 補跑 / 中斷之後 ─────────────────
def fetch_map(ex, syms, need4):
    """(幣, 週期或 'fund', 開盤/結算時間) → 實際取得時間(ms)。來自 bars/、funding/ 內每筆記錄的 fetched_at。"""
    fm = {}
    for s in syms:
        for tf in ('1h', '4h'):
            if tf == '4h' and s not in need4: continue
            for r in read_jsonl_ro(ex.bar_file(s, tf)): fm[(s, tf, r['t'])] = r['fetched_at']
        for r in read_jsonl_ro(ex.fund_file(s)): fm[(s, 'fund', r['t'])] = r['fetched_at']
    return fm


def _inputs(e):
    """這個決策用到的已收盤行情:(幣, 週期, 開盤時間);資金費率用 'fund'。進場/出場的成交參考價 = 決策當下剛開盤那一根的開盤價,另列為第二個輸入。"""
    t = e['type']; sym = e.get('sym') or e['key'].split('|')[0]
    if t == 'ENTRY': tau = e['decision_ts']; return [(sym, e['tf'], e['decision_bar_open']), (sym, '1h', tau - tau % HOUR)]
    if t == 'EXIT':
        if e['why'] == '交易所保護停損': return [(sym, '1h', e['decision_bar_open'])]
        tau = e['decision_ts']; return [(sym, e['tf'], e['decision_bar_open']), (sym, '1h', tau - tau % HOUR)]
    if t == 'FUNDING': ts = e['ts']; return [(sym, 'fund', ts), (sym, '1h', ts - ts % HOUR)]
    tau = e['decision_ts']; tf = e['key'].split('|')[1]; return [(sym, tf, tau - tau % STEP[tf] - STEP[tf])]           # REJECT


def _close_of(tf, t): return t if tf == 'fund' else t + STEP[tf]


def annotate(e, fm, live_ms):
    ins = [x for x in _inputs(e) if x[2] is not None]; closes = []; fetched = []; late = False; missing = not ins
    for (s, tf, t) in ins:
        f = fm.get((s, tf, t)); c = _close_of(tf, t)
        if f is None: missing = True; continue
        closes.append(c); fetched.append(f); late = late or (f - c > live_ms)
    return {'bar_close_ts': (_close_of(ins[0][1], ins[0][2]) if ins else None), 'ref_close_ts': max(closes) if closes else None, 'inputs_fetched_ms': max(fetched) if fetched else None, 'late': late, 'missing': missing}


def annotate_mark(h, fm, syms, live_ms):
    f = [fm[(s, '1h', h - HOUR)] for s in syms if (s, '1h', h - HOUR) in fm]
    return {'bar_close_ts': int(h), 'ref_close_ts': int(h), 'inputs_fetched_ms': max(f) if f else None, 'late': bool(f) and max(f) - h > live_ms, 'missing': not f}


def classify(meta, now, taint, live_ms):
    """回傳要寫進紀錄的欄位。決定於『第一次記帳』當下,之後永遠不改。"""
    reasons = []
    if meta['ref_close_ts'] is None or meta['missing']: reasons.append('input_fetch_time_missing')
    else:
        if now - meta['ref_close_ts'] > live_ms: reasons.append('record_lag_exceeds_limit')
        if meta['late']: reasons.append('input_bar_fetched_late')
    bf = bool(reasons)
    ev = 'BACKFILL' if bf else ('AFTER_INTERRUPTION' if (taint is not None and meta['ref_close_ts'] > taint) else 'LIVE_FORWARD')
    return {'bar_close_ts': meta['bar_close_ts'], 'bar_close_utc': iso(meta['bar_close_ts']) if meta['bar_close_ts'] else None, 'ref_close_ts': meta['ref_close_ts'], 'inputs_fetched_utc': iso(meta['inputs_fetched_ms']) if meta['inputs_fetched_ms'] else None,
            'tick_wall_utc': iso(now), 'record_lag_s': (round((now - meta['ref_close_ts']) / 1000) if meta['ref_close_ts'] else None), 'is_backfill': bf, 'evidence': ev, 'backfill_reasons': reasons}


def current_taint(ex):
    """最早的『汙染』時間:任何資料旗標,或任何補跑紀錄的輸入收盤時間。沒有就回傳 None。"""
    ts = [f['taint_from_ts'] for f in read_jsonl_ro(ex.flags)]
    for p in [ex.events, ex.marks('A'), ex.marks('B')]:
        ts += [r['ref_close_ts'] for r in read_jsonl_ro(p) if r.get('is_backfill') and r.get('ref_close_ts') is not None]
    return min(ts) if ts else None


def detect_flags(ex, rec, snap, now, tick_id, prev_wall):
    """中斷/缺口/修訂都另存為不可覆寫的旗標(ledger/data_flags.jsonl)。回傳『新』旗標。"""
    T0 = snap['start_ts']; live = snap['rules']['live_max_lag_ms']; fl = []
    prev = T0 if prev_wall is None else max(prev_wall, T0)
    if now > T0 and now - prev > live:
        fl.append({'id': 'INTERRUPTION|%d' % prev, 'type': 'LATE_START' if (prev_wall is None or prev_wall < T0) else 'INTERRUPTION', 'taint_from_ts': int(prev), 'detail': {'from_utc': iso(prev), 'to_utc': iso(now), 'hours': round((now - prev) / HOUR, 1)}})
    for g in rec['gaps']:
        if 'sym' in g: fl.append({'id': 'GAP|%s|%d' % (g['sym'], g['first_missing_ts']), 'type': 'DATA_GAP', 'taint_from_ts': int(g['first_missing_ts']), 'detail': g})
    for m in rec['bar_mismatches']: fl.append({'id': 'REV|%s|%s|%d' % (m['sym'], m['tf'], m['t']), 'type': 'BAR_REVISION', 'taint_from_ts': int(max(m['t'], T0)), 'detail': m})
    have = {r['id'] for r in read_jsonl(ex.flags, ex.corrupt)[0]}; new = []
    for f in fl:
        if f['id'] in have: continue
        have.add(f['id']); f['recorded_utc'] = iso(now); f['tick_id'] = tick_id; new.append(f)
    append_jsonl(ex.flags, new); return new


def reconcile_events(ex, events, tick_id, now_ms, fm=None, live_ms=LIVE_MAX_LAG_MS, taint=None):
    """把『新』事件 append 到帳本(附上證據分類);既有 id 只做比對。回傳 (新增, 相同, 不一致)。不覆蓋、不刪除任何既有紀錄。"""
    have, _ = read_jsonl(ex.events, ex.corrupt); idx = {r['id']: r for r in have}; new = []; same = 0; div = []; seen = set()
    for e in events:
        if e['id'] in seen: continue
        seen.add(e['id']); old = idx.get(e['id'])
        if old is None:
            e = dict(e); e.update(classify(annotate(e, fm or {}, live_ms), now_ms, taint, live_ms)); e['recorded_utc'] = iso(now_ms); e['tick_id'] = tick_id; new.append(e)
        else:
            diff = {k: (old.get(k), e.get(k)) for k in COMPARE_KEYS if k in e and not _close(old.get(k), e.get(k))}
            if diff: div.append({'id': e['id'], 'diff': diff, 'tick_id': tick_id, 'at': iso(now_ms)})
            else: same += 1
    append_jsonl(ex.events, new); append_jsonl(ex.diverge, div)
    return len(new), same, len(div)


def _close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)): return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def reconcile_marks(ex, scen, marks, T0, tick_id, now_ms, fm=None, syms=(), live_ms=LIVE_MAX_LAG_MS, taint=None):
    have, _ = read_jsonl(ex.marks(scen), ex.corrupt); idx = {r['h']: r for r in have}; new = []; div = []; h0 = T0 - T0 % HOUR
    for h, e, w, x, n in marks:
        if h < h0: continue
        if h in idx:
            if not _close(idx[h]['equity'], e): div.append({'id': '%s|MARK|%d' % (scen, h), 'diff': {'equity': (idx[h]['equity'], e)}, 'tick_id': tick_id, 'at': iso(now_ms)})
        else:
            meta = annotate_mark(h, fm or {}, syms, live_ms)
            if h == h0: meta['missing'] = False                                   # 起始那一點沒有行情輸入(空手、起始資金)
            r = {'h': int(h), 'equity': _r(e), 'wallet': _r(w), 'exposure': _r(x), 'n_open': int(n), 'recorded_utc': iso(now_ms), 'tick_id': tick_id}
            r.update(classify(meta, now_ms, taint, live_ms)); new.append(r)
    append_jsonl(ex.marks(scen), new); append_jsonl(ex.diverge, div)
    return len(new), len(div)


def pending_backfill_min(ex, ev_by, runs_marks, T0, fm, syms, now, live_ms):
    """這次 tick『將要新增』的紀錄中,最早的補跑輸入收盤時間(用來決定同一 tick 內之後的紀錄是否算『中斷之後』)。"""
    have_ids = {r['id'] for r in read_jsonl_ro(ex.events)}; ts = []
    for evs in ev_by.values():
        for e in evs:
            if e['id'] in have_ids: continue
            m = annotate(e, fm, live_ms)
            if classify(m, now, None, live_ms)['is_backfill'] and m['ref_close_ts'] is not None: ts.append(m['ref_close_ts'])
    h0 = T0 - T0 % HOUR
    for scen, marks in runs_marks.items():
        have_h = {r['h'] for r in read_jsonl_ro(ex.marks(scen))}
        for h, *_ in marks:
            if h in have_h or h <= h0: continue
            if classify(annotate_mark(h, fm, syms, live_ms), now, None, live_ms)['is_backfill']: ts.append(h)
    return min(ts) if ts else None


# ───────────────── 一次 tick ─────────────────
def tick(exp_dir, feed, now_ms=None, stale_lock_s=1800):
    ex = Exp(exp_dir); bad = verify_manifest(ex)
    if bad: raise ManifestMismatch('manifest/hash mismatch: %s — create a NEW experiment version; this record must not be overwritten' % ', '.join(bad))
    snap = ex.load_snapshot(); T0 = snap['start_ts']; now = int(now_ms if now_ms is not None else feed.now_ms()); tick_id = '%s_%d' % (iso(now).replace(' ', 'T').replace(':', ''), os.getpid())
    A = snap['scenarios']['A']['combos']; Bc = snap['scenarios']['B']['combos']
    with FileLock(ex.lock, stale_lock_s) as lk:
        prev_ticks = read_jsonl_ro(ex.ticks); prev_wall = prev_ticks[-1].get('wall_ms') if prev_ticks else None
        rec = {'tick_id': tick_id, 'wall_utc': iso(now), 'wall_ms': now, 'lock_takeover': lk.took_over, 'errors': [], 'gaps': [], 'bar_mismatches': [], 'new_bars': 0, 'funding_ok': {}, 'funding_repaired': [], 'funding_issues': []}
        syms = snap['symbols'] + [snap['reference_symbol']]; need4 = {c['symbol'] for c in A if c['timeframe'] == '4h'} | {snap['reference_symbol']}
        mk = snap['markets']; finfo = None
        try:
            if hasattr(feed, 'funding_info'): finfo = feed.funding_info(); rec['funding_info_hours'] = {mk.get(s, {}).get('id') or s.replace('/', ''): finfo.get(mk.get(s, {}).get('id') or s.replace('/', '')) for s in snap['symbols']}
        except Exception as e: rec['errors'].append('funding_info: %s' % str(e)[:100])
        for s in syms:
            sid = mk.get(s, {}).get('id') or s.replace('/', '')
            for tf in ('1h', '4h'):
                if tf == '4h' and s not in need4: continue
                try:
                    have = load_bars(ex, s, tf); step = STEP[tf]
                    start = first_hole(have, step) if have else T0 - WARMUP_BARS * step              # 從『第一個缺口』(沒有缺口就是最後一根)開始補抓;已存在的棒只比對、不覆蓋
                    rows = feed.klines(sid, tf, start); n, mm = store_bars(ex, s, tf, rows, now); rec['new_bars'] += n; rec['bar_mismatches'] += mm
                except Exception as e: rec['errors'].append('%s %s: %s' % (s, tf, str(e)[:100]))
            try:
                fh = load_funding(ex, s); fr = feed.funding(sid, (fh[-1][0] + 1) if fh else T0 - 24 * HOUR); store_funding(ex, s, fr, now); rec['funding_ok'][s] = now
            except Exception as e: rec['errors'].append('funding %s: %s' % (s, str(e)[:100]))
        # 處理範圍 T1:所有幣的 1H 從 T0 所在小時起連續不缺的最後一根,且落後現在 ≥ 2 小時(資金費率已公布)
        T0h = T0 - T0 % HOUR; lastclosed = now - now % HOUR - HOUR; T1 = lastclosed - FUNDING_LAG_MS + HOUR; wanted = T1
        bars = {}; contig = {}
        for s in syms:
            r1 = load_bars(ex, s, '1h'); bars[(s, '1h')] = r1; lc = last_contiguous([r[0] for r in r1], HOUR, T0h); contig[s] = lc
            if wanted >= T0h and lc < wanted: rec['gaps'].append({'sym': s, 'last_contiguous_1h': iso(lc), 'first_missing_ts': int(max(lc + HOUR, T0h)), 'wanted_through': iso(wanted)})       # 缺棒:處理範圍停在缺口之前,不補造
            T1 = min(T1, lc)
            if s in need4: bars[(s, '4h')] = load_bars(ex, s, '4h')
        T1, fiss = funding_guard(ex, feed, snap, T0, T1, now, rec['funding_ok'], prev_ticks, finfo, rec); rec['funding_issues'] = fiss
        for i in fiss: rec['gaps'].append({'sym': i['sym'], 'kind': 'funding_incomplete', 'first_missing_ts': i['from_ts'], 'funding_issue': i['kind'], 'from_utc': i['from_utc'], 'to_utc': i['to_utc'], 'reason': i['detail']})       # 停在缺口前,不補造、不當成 0
        rec['T1'] = int(T1); rec['T1_utc'] = iso(T1) if T1 > 0 else None
        new_flags = detect_flags(ex, rec, snap, now, tick_id, prev_wall); rec['new_flags'] = [f['type'] for f in new_flags]
        if T1 < T0h:
            rec['note'] = 'warm-up only (no processing before the start)'; append_jsonl(ex.ticks, [rec]); _status(ex, rec, snap); return rec
        STR = load_strategies(); sigs = {}
        for scen_name, combos in (('A', A),):
            for c in combos:
                rows = bars[(c['symbol'], c['timeframe'])] if (c['symbol'], c['timeframe']) in bars else load_bars(ex, c['symbol'], c['timeframe'])
                sg, g = signals_for(ex, STR, c['symbol'], c['timeframe'], c['strategy'], rows, T0)
                sigs[(c['symbol'], c['timeframe'], c['strategy'])] = sg
                if g: rec['gaps'].append({'signals_window_gap': key_of(c), 'bars_skipped': g})
        data = {'candles': {k: v for k, v in bars.items()}, 'markets': {s: m for s, m in mk.items()}, 'funding': {s: load_funding(ex, s) for s in syms}}
        M = S.Market(data); P = S.default_params({k: tuple(v) for k, v in snap['exit_params'].items()}, **snap['params'])
        tot_new = tot_same = tot_div = 0; live = snap['rules']['live_max_lag_ms']
        runs = {n: S.run(M, sigs, [(T0, cs)], T0, T1, P, snap['initial_equity']) for n, cs in (('A', A), ('B', Bc))}
        ev_by = {n: derive_events(n, r, M, snap) for n, r in runs.items()}; need4s = need4
        fm = fetch_map(ex, syms, need4s); taint = current_taint(ex)
        pm = pending_backfill_min(ex, ev_by, {n: r['marks'] for n, r in runs.items()}, T0, fm, syms, now, live)                    # 這次新增的補跑紀錄也算汙染起點
        ts_ = [x for x in (taint, pm) + tuple(f['taint_from_ts'] for f in new_flags) if x is not None]; taint = min(ts_) if ts_ else None
        rec['taint_ts'] = taint; rec['taint_utc'] = iso(taint) if taint else None
        for scen_name in ('A', 'B'):
            res = runs[scen_name]
            n, same, dv = reconcile_events(ex, ev_by[scen_name], tick_id, now, fm, live, taint); n2, d2 = reconcile_marks(ex, scen_name, res['marks'], T0, tick_id, now, fm, syms, live, taint)
            tot_new += n + n2; tot_same += same; tot_div += dv + d2
            rec[scen_name] = {'equity_end': _r(res['equity_end']), 'trades_closed': len(res['trades']), 'open': len(res['open_detail']), 'rejected': res['rejected']}
        rec.update(new_records=tot_new, unchanged_events=tot_same, divergences=tot_div)
        append_jsonl(ex.ticks, [rec])                                                  # 最後才寫 tick 記錄(提交標記):中途中斷時,下一次 tick 會用相同 id 比對,不會重複記帳
        _status(ex, rec, snap)
    return rec


def _status(ex, rec, snap):
    st = {'experiment_id': snap['experiment_id'], 'last_tick_utc': rec['wall_utc'], 'processed_through_utc': rec.get('T1_utc'), 'new_records': rec.get('new_records'), 'divergences': rec.get('divergences'), 'errors': rec['errors'], 'gaps': rec['gaps'], 'note': 'derived status, overwritten each tick; the ledger/ folder is the record'}
    tmp = ex.status + '.tmp'; open(tmp, 'w', encoding='utf-8').write(json.dumps(st, ensure_ascii=False, indent=1)); os.replace(tmp, ex.status)
