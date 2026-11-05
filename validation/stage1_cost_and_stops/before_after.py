# -*- coding: utf-8 -*-
"""Before/after on IDENTICAL real data: original sim.py + original cost call vs fixed sim.py + cost_kwargs."""
import sys, os, json, math, time, warnings, datetime as dt, importlib.util
warnings.filterwarnings('ignore')
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r'C:\Users\User\發大財\trading-app')
import app as A          # fixed code (also registers the 147 extra strategies into sim.STRATS)
import sim as NEW
spec = importlib.util.spec_from_file_location('sim_orig', os.path.join(SP, 'sim_orig.py'))
OLD = importlib.util.module_from_spec(spec); spec.loader.exec_module(OLD)
for k, v in NEW.STRATS.items():
    if k not in OLD.STRATS: OLD.STRATS[k] = v                 # same strategy definitions in both

CACHE = os.path.join(SP, 'ba_cache'); os.makedirs(CACHE, exist_ok=True)
def load(sym, tf, days):
    fn = os.path.join(CACHE, sym.replace('/', '_') + '_' + tf + '.json')
    if os.path.exists(fn): return json.load(open(fn))
    start = (dt.datetime.now() - dt.timedelta(days=days)).strftime('%Y-%m-%d')
    A._cache.clear(); A._cache_time.clear()
    o = A.fetch_data(sym, start, interval=tf)            # fixed fetch: closed bars only, local-date daily stamps
    json.dump(o, open(fn, 'w')); return o

TARGETS = [('BTC/USDT', '4h', 900), ('SOL/USDT', '4h', 900), ('XRP/USDT', '1h', 560),
           ('2330.TW', '1d', 365 * 7 + 700), ('AAPL', '1d', 365 * 7 + 700), ('NVDA', '1d', 365 * 7 + 700)]
STRATS = ['trend', 'supertrend', 'donchian', 'tsmom', 'ttm', 'smc', 'vortex', 'sixline', 'bbreak', 'cci',
          'cmf_zero', 'ssl_channel', 'ema_8_21']

def pf_gross(tl):
    w = sum(t['ret'] for t in tl if t.get('ret') and t['ret'] > 0); l = -sum(t['ret'] for t in tl if t.get('ret') and t['ret'] < 0)
    return (w / l) if l else (999 if w else 0)

def run_old(o, strat, sym, tf):
    com, slp = OLD.market_cost(('yf', sym), strat)       # exactly how the old app.py called it
    r = OLD.run_backtest(o, strategy=strat, risk_pct=0.015, timeframe=tf, commission=com, slippage=slp)
    r0 = OLD.run_backtest(o, strategy=strat, risk_pct=0.015, timeframe=tf, commission=0.0, slippage=0.0)
    return r, r0, (com, slp)

def run_new(o, strat, sym, tf):
    ck = NEW.cost_kwargs(sym, strat)
    r = NEW.run_backtest(o, strategy=strat, risk_pct=0.015, timeframe=tf, **ck)
    r0 = NEW.run_backtest(o, strategy=strat, risk_pct=0.015, timeframe=tf, commission=0.0, slippage=0.0, sell_tax=0.0)
    return r, r0, ck

rows = []
for sym, tf, days in TARGETS:
    o = load(sym, tf, days)
    print('%-9s %-3s bars=%d  %s -> %s' % (sym, tf, len(o), dt.datetime.utcfromtimestamp(o[0][0] / 1000).date(), dt.datetime.utcfromtimestamp(o[-1][0] / 1000)))
    for st in STRATS:
        if st not in NEW.STRATS: continue
        try:
            a, a0, ca = run_old(o, st, sym, tf); b, b0, cb = run_new(o, st, sym, tf)
        except Exception as e:
            print('   ', st, 'ERR', repr(e)[:80]); continue
        if not a or not b: continue
        sa, sb = a[2], b[2]
        tla = [t for t in sa['trade_log'] if not t.get('open')]; tlb = [t for t in sb['trade_log'] if not t.get('open')]
        rows.append(dict(sym=sym, tf=tf, strat=st,
            old=dict(total=sa['total'], mdd=sa['mdd'], win=sa['win'], trades=sa['trades'], pf=pf_gross(tla), drag=a0[2]['total'] - sa['total'], rt=2 * (ca[0] + ca[1])),
            new=dict(total=sb['total'], mdd=sb['mdd'], win=sb['win'], trades=sb['trades'], pf=A.calc_pf(tlb), drag=b0[2]['total'] - sb['total'],
                     rt=2 * (cb['commission'] + cb['slippage']) + cb['sell_tax'], cost_paid_pct=sb['cost_paid'] / 10000 * 100)))
json.dump(rows, open(os.path.join(SP, 'before_after.json'), 'w'), indent=1)

def avg(xs): return sum(xs) / len(xs) if xs else float('nan')
print('\n=== per market, average over %d strategies (same data both sides) ===' % len(STRATS))
print('%-9s %-3s | %-34s | %-34s' % ('symbol', 'tf', 'BEFORE  total  mdd  win trades  PF   drag', 'AFTER   total  mdd  win trades  PF   drag'))
for sym, tf, _ in TARGETS:
    rs = [r for r in rows if r['sym'] == sym]
    if not rs: continue
    f = lambda k, v: avg([r[k][v] for r in rs])
    print('%-9s %-3s | %7.1f%% %5.1f %4.0f%% %5.0f %5.2f %5.1fpp | %7.1f%% %5.1f %4.0f%% %5.0f %5.2f %5.1fpp   RT cost %.3f%%->%.3f%%' % (
        sym, tf, f('old', 'total'), f('old', 'mdd'), f('old', 'win'), f('old', 'trades'), f('old', 'pf'), f('old', 'drag'),
        f('new', 'total'), f('new', 'mdd'), f('new', 'win'), f('new', 'trades'), f('new', 'pf'), f('new', 'drag'), 100 * f('old', 'rt'), 100 * f('new', 'rt')))
print('\nstrategies whose sign flips (total return >0 before, <=0 after):')
for r in rows:
    if r['old']['total'] > 0 >= r['new']['total']:
        print('  %-9s %-3s %-12s %+7.1f%% -> %+7.1f%%' % (r['sym'], r['tf'], r['strat'], r['old']['total'], r['new']['total']))
