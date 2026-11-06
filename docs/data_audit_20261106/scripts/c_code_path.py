# -*- coding: utf-8 -*-
"""稽核 C:實際跑一次『網站 1H / 4H 回測』與『D4 行情來源』的程式路徑,記錄:實際打的網址、送進策略引擎的 K 棒間距、與官方 API 逐欄比對。
全部唯讀:只有公開 GET;網站以 Flask test_client 在行程內呼叫(不開 port、不寫檔);不修改任何既有程式。
注意:這會『執行』網站程式(app.py)的真實取資料函式,所以是真實行情,不是模擬。"""
import collections, json, os, sys, time, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *
ROOT = r'C:\Users\User\發大財\trading-app'
os.environ['RENDER'] = 'true'; sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'paper_trading')); os.chdir(ROOT)
import ccxt
OUTJ = {}

# ---- 1) ccxt 實際打哪個網址 ----
ex = ccxt.binanceusdm({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
seen = []; _orig = ex.fetch
def _spy(url, method='GET', headers=None, body=None): seen.append((method, url)); return _orig(url, method, headers, body)
ex.fetch = _spy
ex.load_markets(); m = ex.market('BTC/USDT')
OUTJ['ccxt_market_BTC/USDT'] = {'id': m['id'], 'type': m['type'], 'linear': m['linear'], 'swap': m['swap'], 'contract': m['contract'], 'settle': m['settle'], 'symbol': m['symbol']}
seen.clear(); r = ex.fetch_ohlcv('BTC/USDT', '1h', since=MS(2024, 3, 12), limit=2)
OUTJ['ccxt_fetch_ohlcv_url'] = [u for _, u in seen]; OUTJ['ccxt_fetch_ohlcv_rows'] = r
seen.clear(); ex.fapiPublicGetKlines({'symbol': 'BTCUSDT', 'interval': '4h', 'startTime': MS(2024, 3, 12), 'limit': 2})
OUTJ['fapiPublicGetKlines_url'] = [u for _, u in seen]
print('ccxt BTC/USDT market ->', OUTJ['ccxt_market_BTC/USDT']); print('fetch_ohlcv url ->', OUTJ['ccxt_fetch_ohlcv_url']); print('fapiPublicGetKlines url ->', OUTJ['fapiPublicGetKlines_url'], flush=True)

# ---- 2) 網站:/api/analyze 選 1H / 4H,實際送進策略引擎的 K 棒 ----
import app as A
A.CCXT_AVAILABLE = True                                                   # 與網站『啟動時 ccxt 連線成功』的狀態相同(RENDER=true 只是略過啟動檢查)
cap = {'fetch': [], 'bt': []}
_fd = A.fetch_data; _rb = A.run_backtest
def fd(*a, **k):
    r = _fd(*a, **k); cap['fetch'].append((a, k, r)); return r
def rb(ohlcv, *a, **k):
    cap['bt'].append((len(ohlcv), [r[0] for r in ohlcv], k.get('timeframe'))); return _rb(ohlcv, *a, **k)
A.fetch_data = fd; A.run_backtest = rb
cl = A.app.test_client(); NOW = int(time.time() * 1000); site = []
for sym, tf, strat in (('BTC/USDT', '4h', 'trend'), ('SOL/USDT', '4h', 'supertrend'), ('XRP/USDT', '1h', 'trend'), ('TRX/USDT', '1h', 'tsmom')):
    cap['fetch'].clear(); cap['bt'].clear(); t0 = time.time()
    resp = cl.get('/api/analyze?symbol=%s&strategy=%s&period=2y&timeframe=%s' % (sym.replace('/', '%2F'), strat, tf)); js = resp.get_json() or {}
    n, ts, tfarg = cap['bt'][0] if cap['bt'] else (0, [], None)
    dif = collections.Counter(b - a for a, b in zip(ts, ts[1:])); step = STEP[tf]
    # 對官方 API:這份被送進策略引擎的 K 棒逐欄比對
    sid = sym.replace('/', '')
    api = klines(sid, tf, ts[0], ts[-1], now=NOW) if ts else []
    loc = {r[0]: r for r in cap['fetch'][0][2]} if cap['fetch'] else {}
    cmp = compare(api, loc, tf, ts[0], ts[-1]) if ts else {}
    rec = {'symbol': sym, 'ui_timeframe': tf, 'http': resp.status_code, 'bars_sent_to_engine': n, 'timeframe_arg_to_engine': tfarg, 'spacing_ms': dict(dif.most_common(3)), 'expected_step_ms': step,
           'first': U(ts[0]) if ts else None, 'last': U(ts[-1]) if ts else None, 'dataInfo': {k: (js.get('dataInfo') or {}).get(k) for k in ('interval', 'source', 'bars', 'firstBar', 'lastBarUtc', 'lastBarClosed')},
           'fetch_meta_source': A.fetch_meta(sym, cap['fetch'][0][0][1], tf).get('source') if cap['fetch'] else None, 'dataQuality_source': (js.get('dataQuality') or {}).get('source'),
           'official_compare': {k: cmp.get(k) for k in ('api_rows', 'matched', 'mismatch_rows', 'missing_in_local', 'extra_in_local', 'close_time_mismatch', 'field_mismatch')}, 'secs': round(time.time() - t0, 1)}
    site.append(rec); print(json.dumps(rec, ensure_ascii=False), flush=True)
OUTJ['site_analyze'] = site

# ---- 3) D4 行情來源(BinanceFeed,與 D4 引擎同一份程式)----
from d4_feed import BinanceFeed
feed = BinanceFeed(); seen2 = []; _o2 = feed.ex.fetch
feed.ex.fetch = lambda url, method='GET', headers=None, body=None: (seen2.append(url), _o2(url, method, headers, body))[1]
d4 = []
for sid in ('BTCUSDT', 'TRXUSDT', 'XRPUSDT', 'SOLUSDT'):
    for tf in ('1h', '4h'):
        lo = MS(2026, 10, 25); rows = feed.klines(sid, tf, lo); api = klines(sid, tf, lo, now=NOW - 5000)
        loc = {r[0]: r for r in rows}; cmp = compare(api, loc, tf, int(api[0][0]), int(api[-1][0]))
        dif = collections.Counter(b[0] - a[0] for a, b in zip(rows, rows[1:]))
        rec = {'sym': sid, 'tf': tf, 'feed_rows': len(rows), 'api_rows': cmp['api_rows'], 'matched': cmp['matched'], 'mismatch_rows': cmp['mismatch_rows'], 'missing': cmp['missing_in_local'], 'extra': cmp['extra_in_local'], 'spacing_ms': dict(dif.most_common(2)), 'last_closed': U(rows[-1][0])}
        d4.append(rec); print('D4feed', rec, flush=True)
OUTJ['d4_feed'] = d4; OUTJ['d4_feed_urls_sample'] = list(dict.fromkeys(u.split('?')[0] for u in seen2))

# ---- 4) D2 / D3 訊號:每個組合的訊號棒間距(證明用的是該組合的週期)----
import pickle
bk =sorted(__import__('glob').glob(r'C:\Users\User\發大財\研究備份_D2\2*'))[-1]
combos = json.load(open(os.path.join(bk, 'config.portfolio.json.REDACTED.json'), encoding='utf-8'))['combos']
sig = {'D2 signals.pkl': pickle.load(open(os.path.join(ROOT, 'validation', 'd2_portfolio', 'raw', 'signals.pkl'), 'rb')), 'D3 signals_long.pkl': pickle.load(open(os.path.join(ROOT, 'validation', 'd3_walkforward', 'raw', 'signals_long.pkl'), 'rb'))}
chk = []
for name, s in sig.items():
    bad = []; n = 0
    for c in combos:
        k = (c['symbol'], c['timeframe'], c['strategy']); ts = sorted(s.get(k, {}))
        if not ts: bad.append(('missing', k)); continue
        n += 1; st = STEP[c['timeframe']]; dif = collections.Counter(b - a for a, b in zip(ts, ts[1:]))
        if any(t % st for t in ts): bad.append(('misaligned_to_utc_grid', k))
        if dif and min(dif) < st: bad.append(('spacing_below_step', k, min(dif)))
        if dif and min(dif) != st: bad.append(('min_spacing_not_equal_step', k, min(dif)))
    chk.append({'file': name, 'combos_checked': n, 'of': len(combos), 'issues': bad, 'n_1h': sum(c['timeframe'] == '1h' for c in combos), 'n_4h': sum(c['timeframe'] == '4h' for c in combos)})
    print(chk[-1])
OUTJ['signals_interval_check'] = chk
json.dump(OUTJ, open(os.path.join(OUT, 'c_code_path.json'), 'w'), ensure_ascii=False, indent=1, default=str)
json.dump(REQLOG, open(os.path.join(OUT, 'c_requests.json'), 'w'), ensure_ascii=False)
