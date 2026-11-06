# -*- coding: utf-8 -*-
"""稽核 A1:只讀本機快取(data.pkl / long.pkl),不連網、不寫入任何既有檔案。
輸出每個 (symbol, tf) 的:筆數、首末時間、間距分佈、重複、亂序、缺口、OHLC 一致性、非正值、NaN、零成交量。"""
import pickle, sys, json, datetime, collections, math, hashlib, os
ROOT = r'C:\Users\User\發大財\trading-app\validation'
FILES = {'D2 data.pkl': os.path.join(ROOT, 'd2_portfolio', 'raw', 'data.pkl'), 'D3 long.pkl': os.path.join(ROOT, 'd3_walkforward', 'raw', 'long.pkl')}
STEP = {'1h': 3600000, '4h': 14400000}
U = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
OUT = {}
for name, p in FILES.items():
    sha = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    d = pickle.load(open(p, 'rb'))
    print('=====', name, 'sha256', sha[:16], 'mtime', datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M:%S'), 'keys', list(d.keys()), 'fetched_at', U(d['fetched_at']))
    rep = {}
    for (s, tf), rows in sorted(d['candles'].items()):
        if tf not in STEP or not rows: continue
        st = STEP[tf]; n = len(rows); ts = [r[0] for r in rows]
        dif = collections.Counter(b - a for a, b in zip(ts, ts[1:]))
        dup = n - len(set(ts)); unsorted = sum(1 for a, b in zip(ts, ts[1:]) if b <= a)
        gaps = [(U(a), (b - a) // st - 1) for a, b in zip(ts, ts[1:]) if b - a > st]
        misaligned = sum(1 for t in ts if t % st != 0)
        bad_ohlc = 0; nonpos = 0; nan = 0; zero_v = 0; bad_hl = 0
        for r in rows:
            t, o, h, l, c, v = r[:6]
            if any((x is None) or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) for x in (o, h, l, c, v)): nan += 1; continue
            if min(o, h, l, c) <= 0: nonpos += 1
            if h < max(o, c) - 1e-12 or l > min(o, c) + 1e-12: bad_ohlc += 1
            if h < l: bad_hl += 1
            if v == 0: zero_v += 1
        rep['%s|%s' % (s, tf)] = dict(bars=n, first=U(ts[0]), last=U(ts[-1]), spacing=dict(dif.most_common(4)), dup=dup, unsorted=unsorted, gaps_n=len(gaps), missing=sum(g for _, g in gaps), gaps_top=sorted(gaps, key=lambda x: -x[1])[:3], misaligned=misaligned, ohlc_violation=bad_ohlc, h_lt_l=bad_hl, nonpos=nonpos, nan=nan, zero_vol=zero_v, row_len=len(rows[0]))
    OUT[name] = rep
    for k, v in rep.items():
        print('%-14s bars=%6d %s -> %s spacing=%s dup=%d unsorted=%d gaps=%d(miss %d) misalign=%d ohlcViol=%d nonpos=%d nan=%d zeroVol=%d rowlen=%d' % (k, v['bars'], v['first'], v['last'], v['spacing'], v['dup'], v['unsorted'], v['gaps_n'], v['missing'], v['misaligned'], v['ohlc_violation'], v['nonpos'], v['nan'], v['zero_vol'], v['row_len']))
        if v['gaps_n']: print('    gaps_top', v['gaps_top'])
    print('markets:', {k: v.get('id') for k, v in list(d['markets'].items())[:40]})
json.dump(OUT, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'out', 'a1_local.json'), 'w'), ensure_ascii=False, indent=1)
