# -*- coding: utf-8 -*-
"""資金費率稽核 補充:
(a) 結算間隔不是 8 小時的歷史區段(SOL 2 小時、KAVA 1 小時、JUP/PAXG/PYTH/IMX 4 小時):向官方核對這些區段,確認不是本機錯誤。
(b) 缺漏行為示範(只用本機模擬器,不連網、不寫檔):從真實資金費率裡刪掉『持倉期間的一筆』,看模擬器是明確報錯、還是默默當 0。
只有公開 GET(a);(b)純本機。"""
import collections, json, os, sys, time, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *
H = 3600000; d3 = pickle.load(open(D3P, 'rb'))['funding']; res = {'irregular': [], 'gap_demo': {}}
# (a)
for u in ('SOL/USDT', 'KAVA/USDT', 'JUP/USDT', 'PAXG/USDT', 'PYTH/USDT'):
    rows = d3[u]; ts = [r[0] for r in rows]; sid = u.replace('/', '')
    odd = [i for i in range(len(ts) - 1) if round((ts[i + 1] - ts[i]) / H) != 8]
    if u in ('JUP/USDT', 'PAXG/USDT', 'PYTH/USDT'): i = len(ts) - 40; lo, hi = ts[i], ts[i + 20]            # 4 小時間隔的近期區段
    elif odd: i = odd[len(odd) // 2]; lo, hi = ts[max(0, i - 6)], ts[min(len(ts) - 1, i + 12)]
    else: continue
    api = []; cur = lo
    r = get(FAPI, '/fapi/v1/fundingRate', {'symbol': sid, 'startTime': lo, 'endTime': hi, 'limit': 1000}); api = r
    loc = {t: v for t, v in rows if lo <= t <= hi}
    ok = [int(x['fundingTime']) for x in api] == sorted(loc) and all(float(x['fundingRate']) == loc[int(x['fundingTime'])] for x in api)
    sp = collections.Counter(round((int(b['fundingTime']) - int(a['fundingTime'])) / H) for a, b in zip(api, api[1:]))
    res['irregular'].append({'sym': sid, 'window': '%s -> %s' % (U(lo), U(hi)), 'api_rows': len(api), 'local_rows': len(loc), 'identical': ok, 'spacing_hours_in_window': dict(sp)}); print(res['irregular'][-1], flush=True)
json.dump(res['irregular'], open(os.path.join(OUT, 'f2_irregular.json'), 'w'), ensure_ascii=False, indent=1)

# (b) 缺漏示範:用 D3 模擬器(d2_sim)跑一個月,刪掉一筆持倉期間的資金費率
ROOT = r'C:\Users\User\發大財\trading-app'; D3DIR = os.path.join(ROOT, 'validation', 'd3_walkforward')
sys.path.insert(0, os.path.join(ROOT, 'validation', 'd2_portfolio')); sys.path.insert(0, D3DIR); sys.path.insert(0, ROOT); os.chdir(ROOT)
import copy
import d2_sim as S
from d2_common import cfg_combos, exit_params
from d3_config import *
long = pickle.load(open(os.path.join(D3DIR, 'raw', 'long.pkl'), 'rb')); sigs = pickle.load(open(os.path.join(D3DIR, 'raw', 'signals_long.pkl'), 'rb')); C_ = cfg_combos('config.portfolio.json'); EX = exit_params()
T0, T1 = ms(2026, 8, 1), ms(2026, 9, 1)
def run(funding):
    L = {'candles': long['candles'], 'markets': long['markets'], 'funding': funding, 'fetched_at': 0}
    return S.run(S.Market(L), sigs, [(T0, C_)], T0, T1, S.default_params(EX, **PB), INIT)
base = run(long['funding']); fl = base['funding_log']; print('baseline funding events:', len(fl), 'trades', len(base['trades']))
pick = fl[len(fl) // 2]; sym = next(c['symbol'] for c in C_ if '%s|%s|%s' % (c['symbol'], c['timeframe'], c['strategy']) == pick['key'])
f2 = {k: list(v) for k, v in long['funding'].items()}; f2[sym] = [r for r in f2[sym] if r[0] != pick['ts']]                 # 刪掉『一筆』結算
err = None
try: alt = run(f2)
except Exception as e: err = repr(e)[:200]; alt = None
res['gap_demo'] = {'deleted': {'symbol': sym, 'settlement_utc': U(pick['ts']), 'rate': pick['rate'], 'amount_that_would_have_been_charged_usd': pick['amount'], 'position': pick['key']}, 'raised_error': err}
if alt:
    keys = {(f['ts'], f['key']) for f in alt['funding_log']}
    res['gap_demo'].update({'funding_events_baseline': len(fl), 'funding_events_after_delete': len(alt['funding_log']), 'deleted_event_present_after': (pick['ts'], pick['key']) in keys, 'notes_after': alt['notes'], 'same_trade_count': len(alt['trades']) == len(base['trades']),
                            'equity_end_diff_usd': round(alt['equity_end'] - base['equity_end'], 6)})
print(json.dumps(res['gap_demo'], ensure_ascii=False, default=str)); json.dump(res['gap_demo'], open(os.path.join(OUT, 'f2_gap_demo.json'), 'w'), ensure_ascii=False, indent=1, default=str)
