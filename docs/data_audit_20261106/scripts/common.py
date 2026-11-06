# -*- coding: utf-8 -*-
"""行情稽核共用模組。只做『公開行情 GET』:不帶金鑰、不呼叫任何私有/交易端點、不寫入任何既有資料檔。
所有請求都記錄在 REQLOG(網址、參數、HTTP 狀態、回傳筆數、時間),供報告附錄。"""
import datetime, json, os, pickle, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.dirname(HERE)
RAW_API = os.path.join(BASE, 'raw_api'); OUT = os.path.join(BASE, 'out')
FAPI = 'https://fapi.binance.com'; SPOT = 'https://api.binance.com'
ALLOWED = ('/fapi/v1/klines', '/fapi/v1/exchangeInfo', '/api/v3/klines', '/fapi/v1/time', '/fapi/v1/fundingRate', '/fapi/v1/fundingInfo')       # 只允許這幾個公開 GET 路徑
STEP = {'1h': 3600000, '4h': 14400000}
REQLOG = []
U = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
MS = lambda y, m, d, hh=0: int(datetime.datetime(y, m, d, hh, tzinfo=datetime.timezone.utc).timestamp() * 1000)
D2P = r'C:\Users\User\發大財\trading-app\validation\d2_portfolio\raw\data.pkl'
D3P = r'C:\Users\User\發大財\trading-app\validation\d3_walkforward\raw\long.pkl'


def get(base, path, params=None, retries=5):
    assert path in ALLOWED, path
    url = base + path + ('?' + urllib.parse.urlencode(params) if params else '')
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'readonly-data-audit/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(); data = json.loads(body)
                REQLOG.append({'url': url, 'status': r.status, 'rows': len(data) if isinstance(data, list) else None, 'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')})
                time.sleep(0.2); return data
        except Exception as e:
            last = e; time.sleep(1.5 * (a + 1))
    REQLOG.append({'url': url, 'status': 'FAIL', 'err': str(last)[:100]}); raise RuntimeError('request failed: %s %s' % (url, last))


def klines(sym, tf, start, end=None, base=FAPI, path='/fapi/v1/klines', now=None):
    """分頁取原始 K 線(每筆是幣安原始的 12 欄字串陣列)。回傳已收盤的列(開盤時間 + 週期 <= 現在)。"""
    rows = []; cur = start; step = STEP[tf]; now = now or int(time.time() * 1000)
    while True:
        p = {'symbol': sym, 'interval': tf, 'startTime': cur, 'limit': 1500}
        if end is not None: p['endTime'] = end
        r = get(base, path, p)
        if not r: break
        rows += r
        if len(r) < 1500: break
        cur = int(r[-1][0]) + step
    return [x for x in rows if int(x[0]) + step <= now]


def load_local():
    d2 = pickle.load(open(D2P, 'rb')); d3 = pickle.load(open(D3P, 'rb'))
    return {'D2': {k: {r[0]: r for r in v} for k, v in d2['candles'].items() if k[1] in STEP}, 'D3': {k: {r[0]: r for r in v} for k, v in d3['candles'].items() if k[1] in STEP}}, {'D2': d2, 'D3': d3}


def to_unified(sym): return sym[:-4] + '/USDT'


def compare(api_rows, local_by_ts, tf, lo, hi):
    """逐欄比對:開盤時間(用來配對)、收盤時間(本機沒存,用 開盤+週期-1ms 推算並對 API 的 closeTime)、Open/High/Low/Close/Volume。
    浮點數以『API 字串直接轉 float』與本機值做完全相等比對(本機值同樣由字串轉 float 而來)。"""
    step = STEP[tf]; res = {'api_rows': len(api_rows), 'matched': 0, 'missing_in_local': 0, 'extra_in_local': 0, 'field_mismatch': {'o': 0, 'h': 0, 'l': 0, 'c': 0, 'v': 0}, 'close_time_mismatch': 0, 'mismatch_rows': 0, 'examples': []}
    api_ts = set()
    for x in api_rows:
        t = int(x[0]); api_ts.add(t)
        if int(x[6]) != t + step - 1: res['close_time_mismatch'] += 1
        l = local_by_ts.get(t)
        if l is None: res['missing_in_local'] += 1; continue
        bad = []
        for i, k in ((1, 'o'), (2, 'h'), (3, 'l'), (4, 'c'), (5, 'v')):
            if float(x[i]) != l[i]: res['field_mismatch'][k] += 1; bad.append((k, x[i], l[i]))
        if bad: res['mismatch_rows'] += 1; (len(res['examples']) < 3) and res['examples'].append({'t': U(t), 'diff': bad})
        else: res['matched'] += 1
    res['extra_in_local'] = sum(1 for t in local_by_ts if lo <= t <= hi and t not in api_ts)
    return res
