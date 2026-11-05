# -*- coding: utf-8 -*-
"""Phase-5 regression: real network data, real Flask app (test client). No orders, no private API."""
import sys, os, math, time, json, datetime as dt, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'C:\Users\User\發大財\trading-app')
import app as A, sim as S
c = A.app.test_client()
TARGETS = [('BTC/USDT', '4h', 'supertrend'), ('SOL/USDT', '4h', 'ttm'), ('XRP/USDT', '1h', 'vortex'),
           ('2330.TW', '1d', 'diadx'), ('AAPL', '1d', 'tsmom'), ('NVDA', '1d', 'supertrend')]
STEP = {'4h': 4 * 3600, '1h': 3600, '1d': 86400}
now = dt.datetime.utcnow()
problems = []; log = []
def chk(cond, msg):
    if not cond: problems.append(msg)
    return cond
def finite(x): return x is None or (isinstance(x, (int, float)) and math.isfinite(x))

r = c.get('/api/strategies'); j = r.get_json()
chk(r.status_code == 200 and len(j) >= 180 and all('v' in s and 'l' in s for s in j), 'strategies list')
print('/api/strategies  %d  n=%d' % (r.status_code, len(j)))
r = c.get('/api/config'); print('/api/config', r.status_code, r.get_json())

for sym, tf, st in TARGETS:
    t0 = time.time(); tag = '%s %s' % (sym, tf)
    # --- analyze
    r = c.get('/api/analyze', query_string=dict(symbol=sym, strategy=st, period='1y', timeframe=tf)); j = r.get_json()
    ok = chk(r.status_code == 200, '%s analyze http %d %s' % (tag, r.status_code, str(j)[:120]))
    if ok:
        m = j['metrics']; n = len(j['dates'])
        for key in ('prices', 'opens', 'highs', 'lows', 'ema20', 'ema50', 'buyPoints', 'sellPoints', 'diff', 'volumes'):
            chk(len(j[key]) == n, '%s analyze len(%s)' % (tag, key))
        chk(all(finite(m[k]) for k in ('totalReturn', 'cagr', 'pf', 'maxDD', 'wr')), '%s analyze metrics finite' % tag)
        chk(0 <= m['maxDD'] <= 100, '%s analyze maxDD range %s' % (tag, m['maxDD']))
        # timeframe sanity: spacing and closed last bar
        fmt = '%Y-%m-%d %H:%M' if tf in ('1h', '4h') else '%Y-%m-%d'
        ds = [dt.datetime.strptime(x, fmt) for x in j['dates']]
        gaps = [(ds[i + 1] - ds[i]).total_seconds() for i in range(n - 1)]
        if tf in ('1h', '4h'):
            chk(min(gaps) == STEP[tf], '%s min bar spacing %s != %s (1H posing as 4H?)' % (tag, min(gaps), STEP[tf]))
            chk(all(d.hour % (STEP[tf] // 3600) == 0 and d.minute == 0 for d in ds), '%s bars not aligned to %s grid' % (tag, tf))
            chk(ds[-1] + dt.timedelta(seconds=STEP[tf]) <= now, '%s last bar not closed: %s' % (tag, ds[-1]))
        else:
            chk(all(d.weekday() < 5 for d in ds) or sym.endswith('USDT'), '%s weekend bars present' % tag)
            chk(ds[-1].date() <= now.date(), '%s last daily bar in future' % tag)
        nbuy = sum(1 for x in j['buyPoints'] if x is not None); nsell = sum(1 for x in j['sellPoints'] if x is not None)
        chk(nbuy - nsell in (0, 1), '%s buy/sell markers inconsistent %d/%d' % (tag, nbuy, nsell))
        log.append((tag, 'analyze', dict(bars=n, last=j['dates'][-1], total=m['totalReturn'], mdd=m['maxDD'], trades=m['tradeCount'], pf=m['pf'], wr=m['wr'], buys=nbuy, sells=nsell)))
    # --- signal & character
    r = c.get('/api/signal', query_string=dict(symbol=sym, strategy=st, timeframe=tf)); j = r.get_json()
    chk(r.status_code == 200 and 'state' in j, '%s signal %s' % (tag, str(j)[:100]))
    r = c.get('/api/market_character', query_string=dict(symbol=sym, timeframe=tf)); j2 = r.get_json()
    chk(r.status_code == 200 and 'code' in j2, '%s character' % tag)
    log.append((tag, 'signal/character', dict(state=j.get('state'), character=j2.get('label'), adx=j2.get('adx'))))
    # --- best strategy
    r = c.get('/api/best_strategy', query_string=dict(symbol=sym, period='2y', timeframe=tf, use_oos='1')); j = r.get_json()
    if chk(r.status_code == 200, '%s best http %d %s' % (tag, r.status_code, str(j)[:120])):
        res = j['results']
        chk(all(finite(x['pf']) and finite(x['total']) and finite(x['mdd']) and x['mdd'] < 50 for x in res), '%s best numbers' % tag)
        chk([x['score'] for x in res] == sorted([x['score'] for x in res], reverse=True), '%s best sorted' % tag)
        log.append((tag, 'best_strategy', dict(tested=j['total_tested'], n=len(res), top=[(x['strat'], x['pf'], x['trades'], x.get('oosPf'), x.get('oosInsufficient')) for x in res[:3]], character=j['character'].get('label'))))
    # --- deep analysis
    r = c.get('/api/deep_analysis', query_string=dict(symbol=sym, timeframe=tf, use_oos='1')); j = r.get_json()
    if chk(r.status_code == 200, '%s deep http %d %s' % (tag, r.status_code, str(j)[:120])):
        res = j['results']
        chk(all(finite(x['pf']) and finite(x['total']) and finite(x['mdd']) for x in res), '%s deep numbers' % tag)
        log.append((tag, 'deep_analysis', dict(n=len(res), trust=[x.get('trust') for x in res][:8], top=[(x['strat'], x['pf'], x['trades']) for x in res[:3]])))
    print('%-14s done in %.0fs' % (tag, time.time() - t0), flush=True)

print('\n=== RESULTS ===')
for tag, api, d in log: print('%-14s %-17s %s' % (tag, api, d))
print('\nPROBLEMS (%d):' % len(problems))
for p in problems: print('  -', p)
json.dump(dict(log=[(a, b, c_) for a, b, c_ in log], problems=problems), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'live_regression.json'), 'w'), indent=1, default=str)
