# -*- coding: utf-8 -*-
"""C1 修改前/後的回歸比對:對同一份『實際抓到的 K 棒快照』跑既有分析 API,存下完整回應,之後逐欄比對。

  record  <snapshot.json> <out.json>   用真實資料跑一次(同時把每次 fetch_data 回傳的 K 棒存成快照)
  replay  <snapshot.json> <out.json>   不連網,用快照當資料來源重跑(可在『修改前』與『修改後』的程式碼各跑一次)
  compare <before.json> <after.json>   逐欄比對,列出差異(新增欄位另外列出,不算差異)

在哪個程式碼上跑,由 --app-dir 指定(預設是這個檔案往上三層的 trading-app)。
"""
import argparse, datetime, json, os, sys, warnings
warnings.filterwarnings('ignore')
os.environ.setdefault('RENDER', 'true')          # 略過啟動時的 ccxt 連線檢查

TARGETS = [  # (symbol, timeframe, strategy)
    ('BTC/USDT', '4h', 'sixline'), ('BTC/USDT', '1d', 'supertrend'),
    ('SOL/USDT', '4h', 'ttm'), ('SOL/USDT', '1d', 'sixline'),
    ('2330.TW', '1d', 'diadx'), ('AAPL', '1d', 'tsmom'), ('NVDA', '1d', 'tsmom'),
    ('2330.TW', '1h', 'supertrend'), ('AAPL', '1h', 'supertrend'),
]
RANK = [('BTC/USDT', '4h', '2y'), ('SOL/USDT', '4h', '2y'), ('2330.TW', '1d', '2y'), ('AAPL', '1d', '2y'), ('NVDA', '1d', '2y')]
DEEP = [('SOL/USDT', '4h'), ('NVDA', '1d')]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('mode'); ap.add_argument('a'); ap.add_argument('b', nargs='?')
    ap.add_argument('--app-dir', default=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
    ap.add_argument('--tag', default='')
    args = ap.parse_args()
    if args.mode == 'compare':
        return compare(args.a, args.b)
    args.a = os.path.abspath(args.a); args.b = os.path.abspath(args.b) if args.b else None      # 先轉成絕對路徑(下面會 chdir 到程式碼目錄)
    sys.path.insert(0, args.app_dir); os.chdir(args.app_dir)
    import app as A
    A.CCXT_AVAILABLE = True                      # 這台電腦有 ccxt;啟動檢查被 RENDER=true 略過,所以明確設定(兩種模式相同)
    snap = {}; mode = args.mode
    if mode == 'replay':
        snap = json.load(open(args.a, encoding='utf-8'))
        fixed_now = datetime.datetime.fromisoformat(snap['__now__'])
        A._utcnow = lambda: fixed_now
        def fake_fetch(symbol, start, interval='1d'):
            return snap['rows'].get('%s|%s|%s' % (symbol, start, interval), [])
        A.fetch_data = fake_fetch
    else:
        snap = {'__now__': datetime.datetime.utcnow().isoformat(), 'rows': {}}
        real = A.fetch_data
        def rec(symbol, start, interval='1d'):
            rows = real(symbol, start, interval); snap['rows']['%s|%s|%s' % (symbol, start, interval)] = rows; return rows
        A.fetch_data = rec
    c = A.app.test_client(); out = {}
    for sym, tf, st in TARGETS:
        r = c.get('/api/analyze', query_string=dict(symbol=sym, strategy=st, period='2y', timeframe=tf))
        out['analyze|%s|%s|%s' % (sym, tf, st)] = {'status': r.status_code, 'json': r.get_json()}
        print('analyze', sym, tf, st, r.status_code, flush=True)
    for sym, tf, per in RANK:
        r = c.get('/api/best_strategy', query_string=dict(symbol=sym, period=per, timeframe=tf, use_oos='1'))
        out['best|%s|%s|%s' % (sym, tf, per)] = {'status': r.status_code, 'json': r.get_json()}
        print('best', sym, tf, r.status_code, flush=True)
    for sym, tf in DEEP:
        r = c.get('/api/deep_analysis', query_string=dict(symbol=sym, timeframe=tf, use_oos='1'))
        out['deep|%s|%s' % (sym, tf)] = {'status': r.status_code, 'json': r.get_json()}
        print('deep', sym, tf, r.status_code, flush=True)
    if mode == 'record':
        json.dump(snap, open(args.a, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump({'now': snap['__now__'], 'results': out}, open(args.b, 'w', encoding='utf-8'), ensure_ascii=False)


def walk(a, b, path, diffs, added):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b: diffs.append((path + ' > ' + k, 'removed', None))
            else: walk(a[k], b[k], path + ' > ' + k, diffs, added)
        for k in b:
            if k not in a: added.append(path + ' > ' + k)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): diffs.append((path, 'len %d -> %d' % (len(a), len(b)), None)); return
        for i, (x, y) in enumerate(zip(a, b)): walk(x, y, '%s[%d]' % (path, i), diffs, added)
    elif a != b:
        diffs.append((path, repr(a)[:60], repr(b)[:60]))


def compare(fa, fb):
    A = json.load(open(fa, encoding='utf-8'))['results']; B = json.load(open(fb, encoding='utf-8'))['results']
    total = 0; bad = 0; added = set()
    for key in A:
        d, ad = [], []; walk(A[key], B[key], '', d, ad); total += 1
        added.update(x.strip(' >') for x in ad)
        if d: bad += 1; print('DIFF', key, len(d), d[:5])
        else: print('SAME', key, 'status', A[key]['status'])
    print('endpoints compared:', total, 'with differences:', bad)
    print('new (additive) top-level fields:', sorted(added))
    return bad


if __name__ == '__main__':
    sys.exit(main() or 0)
