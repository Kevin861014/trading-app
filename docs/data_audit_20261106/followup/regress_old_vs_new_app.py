# -*- coding: utf-8 -*-
"""回歸檢查:同一份(固定種子的假)K 棒餵給『修改前(git HEAD)的 app.py』與『修改後』的網站,比較 /api/analyze、/api/signal、/api/market_character 的回應。
只有 dataInfo.source/venue、dataQuality 的來源欄位可以不同(那正是這次要改的標籤);其餘必須逐項相同。不連網、不寫專案檔(HEAD 版暫存在 tempdir)。"""
import importlib.util, json, os, random, subprocess, sys, tempfile, time, warnings
warnings.filterwarnings('ignore'); os.environ['RENDER'] = 'true'
ROOT = r'C:\Users\User\發大財\trading-app'; sys.path.insert(0, ROOT); os.chdir(ROOT)
tmp = tempfile.mkdtemp(); old_path = os.path.join(tmp, 'app_old.py')
open(old_path, 'wb').write(subprocess.check_output(['git', 'show', 'HEAD:app.py'], cwd=ROOT))
import app as NEW
spec = importlib.util.spec_from_file_location('app_old', old_path); OLD = importlib.util.module_from_spec(spec); spec.loader.exec_module(OLD)
STEP = {'1h': 3600000, '4h': 14400000}


def rows(tf, n, seed):
    st = STEP[tf]; last = (int(time.time() * 1000) // st) * st - st; r = random.Random(seed); px = 100.0; out = []
    for i in range(n):
        o = px; c = o * (1 + r.uniform(-0.012, 0.0125)); h = max(o, c) * (1 + r.uniform(0, 0.005)); l = min(o, c) * (1 - r.uniform(0, 0.005)); px = c
        out.append([last - (n - 1 - i) * st, o, h, l, c, 10 + r.random()])
    return out


def strip(js):
    js = json.loads(json.dumps(js)); di = js.get('dataInfo') or {}
    for k in ('source', 'venue'): di.pop(k, None)
    dq = js.get('dataQuality') or {}
    for k in ('source', 'venue', 'missingBars'): dq.pop(k, None)
    js.pop('detail', None); return js


bad = 0; n = 0
for tf, strat, sym in (('4h', 'trend', 'BTC/USDT'), ('4h', 'supertrend', 'SOL/USDT'), ('1h', 'tsmom', 'TRX/USDT'), ('1h', 'vortex', 'XRP/USDT'), ('4h', 'ttm', 'BNB/USDT')):
    data = rows(tf, 2500, hash(sym) % 1000)
    out = {}
    for name, A in (('old', OLD), ('new', NEW)):
        A._cache.clear(); A._cache_time.clear(); A._fetch_meta.clear(); A.CCXT_AVAILABLE = True; A.fetch_ccxt_ohlcv = lambda s, i, d, _d=data: _d; A._utcnow = lambda: __import__('datetime').datetime.utcfromtimestamp(time.time() // 3600 * 3600)
        c = A.app.test_client(); q = 'symbol=%s&strategy=%s&timeframe=%s' % (sym.replace('/', '%2F'), strat, tf)
        out[name] = {'analyze': c.get('/api/analyze?%s&period=1y' % q).get_json(), 'signal': c.get('/api/signal?%s' % q).get_json(), 'mc': c.get('/api/market_character?symbol=%s&timeframe=%s' % (sym.replace('/', '%2F'), tf)).get_json()}
    for ep in ('analyze', 'signal', 'mc'):
        a, b = strip(out['old'][ep]), strip(out['new'][ep]); n += 1; same = json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
        bad += (not same); print('%-9s %-3s %-10s %-8s -> %s' % (sym, tf, strat, ep, 'IDENTICAL' if same else 'DIFFERENT'), '(error: %s)' % str(a.get('error'))[:60] if a.get('error') else '', flush=True)
        if not same:
            ka = {k for k in set(a) | set(b) if json.dumps(a.get(k), sort_keys=True, default=str) != json.dumps(b.get(k), sort_keys=True, default=str)}; print('   differing keys:', sorted(ka)[:8])
print('compared %d responses, different: %d' % (n, bad))
