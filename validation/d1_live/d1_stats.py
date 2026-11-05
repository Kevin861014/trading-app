# -*- coding: utf-8 -*-
"""D1 步驟 4:不確定性(bootstrap)與補充統計:整體/各環境/各週期的每筆淨報酬 95% 信賴區間、最大幾筆交易、1H vs 4H。"""
import collections, datetime, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw')
T = json.load(open(os.path.join(RAW, 'trips_enriched.json')))['trips']; closed = [t for t in T if t['closed']]
rng = np.random.default_rng(7)
S = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')


def boot(xs, n=5000):
    xs = np.array(xs); m = [rng.choice(xs, len(xs)).mean() for _ in range(n)]
    return {'n': len(xs), 'mean': round(float(xs.mean()), 3), 'ci95': [round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]}


res = {'overall_net_pct': boot([t['net_pct'] for t in closed]), 'overall_net_usd': boot([t['net'] for t in closed])}
res['by_regime_net_pct'] = {r: boot([t['net_pct'] for t in closed if t['btc_regime'] == r]) for r in sorted({t['btc_regime'] for t in closed}) if sum(1 for t in closed if t['btc_regime'] == r) >= 10}
res['by_tf'] = {}
for tf in ('1h', '4h'):
    ts = [t for t in closed if t.get('tf') == tf and t['attr'] != 'unknown']
    if ts: res['by_tf'][tf] = {'n': len(ts), 'net': round(sum(t['net'] for t in ts), 3), 'fees': round(sum(t['commission'] for t in ts), 3), 'gross': round(sum(t['realized'] for t in ts), 3), 'win': round(100 * sum(1 for t in ts if t['net'] > 0) / len(ts), 1), 'median_hold_h': round(float(np.median([t['hold_h'] for t in ts])), 1)}
top = sorted(closed, key=lambda t: -t['net'])[:6]
res['top_trades'] = [{'symbol': t['symbol'], 'strategy': t.get('strategy'), 'attr': t['attr'], 'entry': S(t['entry_ts']), 'net': round(t['net'], 3), 'ret_pct': round(t['net_pct'], 2), 'hold_h': round(t['hold_h'], 1), 'btc_regime': t['btc_regime']} for t in top]
bot = sorted(closed, key=lambda t: t['net'])[:5]
res['worst_trades'] = [{'symbol': t['symbol'], 'strategy': t.get('strategy'), 'entry': S(t['entry_ts']), 'net': round(t['net'], 3), 'ret_pct': round(t['net_pct'], 2)} for t in bot]
# 時間穩定性:前半 / 後半(依出場時間)
cs = sorted(closed, key=lambda t: t['exit_ts']); h = len(cs) // 2
res['halves'] = {'first': {'n': h, 'net': round(sum(t['net'] for t in cs[:h]), 3), 'from': S(cs[0]['exit_ts']), 'to': S(cs[h - 1]['exit_ts'])}, 'second': {'n': len(cs) - h, 'net': round(sum(t['net'] for t in cs[h:]), 3), 'from': S(cs[h]['exit_ts']), 'to': S(cs[-1]['exit_ts'])}}
# 手續費 / 毛損益 by symbol(高頻組合侵蝕)
fe = collections.defaultdict(lambda: [0, 0.0, 0.0])
for t in closed: fe[t['symbol']][0] += 1; fe[t['symbol']][1] += t['realized']; fe[t['symbol']][2] += t['commission']
res['fee_vs_gross'] = {k: {'n': v[0], 'gross': round(v[1], 3), 'fees': round(v[2], 3)} for k, v in sorted(fe.items(), key=lambda kv: -kv[1][2])[:8]}
json.dump(res, open(os.path.join(RAW, 'stats.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1)[:3500])

# ───────── 同步停損:10 分鐘內 ≥ 3 筆『停損類』出場(只有日誌可辨識出場原因的交易),與當時 BTC 的 6 小時漲跌 ─────────
os.environ.setdefault('RENDER', 'true')
ROOT = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, ROOT)
import warnings; warnings.filterwarnings('ignore')
import app as A
A.CCXT_AVAILABLE = True
btc = {r[0] + 3600000: r[4] for r in A.fetch_data('BTC/USDT', '2026-10-01', interval='1h')}
stops = sorted([t for t in closed if '停損' in (t.get('exit_reason') or '') or '保護停損' in (t.get('exit_reason') or '')], key=lambda t: t['exit_ts'])
cl = []; cur = []
for t in stops:
    if cur and t['exit_ts'] - cur[-1]['exit_ts'] <= 600000: cur.append(t)
    else:
        if len(cur) >= 3: cl.append(cur)
        cur = [t]
if len(cur) >= 3: cl.append(cur)
def btc_at(ms):
    ks = [k for k in btc if k <= ms]; return btc[max(ks)] if ks else None
res['stop_clusters'] = []
for g in cl:
    t0 = g[0]['exit_ts']; a = btc_at(t0 - 6 * 3600000); b = btc_at(t0)
    res['stop_clusters'].append({'at': S(t0), 'n': len(g), 'symbols': [x['symbol'].replace('/USDT', '') for x in g], 'net': round(sum(x['net'] for x in g), 3), 'btc_6h_pct': round((b / a - 1) * 100, 2) if a and b else None, 'span_s': round((g[-1]['exit_ts'] - t0) / 1000)})
json.dump(res, open(os.path.join(RAW, 'stats.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(res['stop_clusters'], ensure_ascii=False))
