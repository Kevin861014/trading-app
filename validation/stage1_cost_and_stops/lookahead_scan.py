# -*- coding: utf-8 -*-
"""Look-ahead scan: signals at bar i must not change when later bars are removed. Synthetic seeded data only."""
import os, sys, random, math, time, warnings
warnings.filterwarnings('ignore')
os.environ['RENDER'] = 'true'            # avoid the network check at app import; we only need the strategy registry
sys.path.insert(0, r'C:\Users\User\發大財\trading-app')
import app as A
import sim as S

def synth(n, seed):
    rnd = random.Random(seed); px = 100.0; rows = []
    for i in range(n):
        # regime-ish random walk with volatility clustering so trend/range strategies actually fire
        drift = 0.0006 * math.sin(i / 120.0); vol = 0.01 + 0.006 * (1 + math.sin(i / 70.0))
        o = px; c = o * (1 + drift + rnd.gauss(0, vol))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2))); l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        v = 1000 * (1 + abs(rnd.gauss(0, 1))) * (1 + (h - l) / o * 20)
        rows.append([i * 14400000, o, h, l, c, v]); px = c
    return rows

N = int(sys.argv[1]) if len(sys.argv) > 1 else 900
CUTS = [int(N * 0.6), int(N * 0.8)]
rows = synth(N, 7)
O = [r[1] for r in rows]; H = [r[2] for r in rows]; L = [r[3] for r in rows]; C = [r[4] for r in rows]; V = [r[5] for r in rows]
bad = []; errs = []; t0 = time.time(); slow = []
for k, s in S.STRATS.items():
    ts = time.time()
    try:
        el, xl = s['build'](O, H, L, C, V, '4h')
        for cut in CUTS:
            el2, xl2 = s['build'](O[:cut], H[:cut], L[:cut], C[:cut], V[:cut], '4h')
            d_el = [i for i in range(cut) if bool(el[i]) != bool(el2[i])]
            d_xl = [i for i in range(cut) if bool(xl[i]) != bool(xl2[i])]
            if d_el or d_xl:
                bad.append((k, cut, len(d_el), len(d_xl), (d_el + d_xl)[:3])); break
    except Exception as e:
        errs.append((k, repr(e)[:80]))
    dt_ = time.time() - ts
    if dt_ > 3: slow.append((k, round(dt_, 1)))
print('strategies scanned: %d in %.0fs (N=%d, cuts=%s)' % (len(S.STRATS), time.time() - t0, N, CUTS))
print('LOOK-AHEAD SUSPECTS (%d):' % len(bad))
for b in bad: print('  ', b)
print('BUILD ERRORS (%d):' % len(errs))
for e in errs[:15]: print('  ', e)
print('slow:', slow[:8])
