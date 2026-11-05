# -*- coding: utf-8 -*-
"""D3 步驟 1:歷史資料可用性盤點 + 取得完整歷史(幣安 USDT-M 永續合約公開 K 線,免金鑰,只有 GET)。
- 只用 fapi(USDT-M 永續)的 klines;不用現貨、不用其他交易所。沒有資料的期間不補造。
- 取得每個合約的最早 K 棒、筆數、缺口;並統計目前 exchangeInfo 的合約狀態/上市日(下架合約公開 API 取不到,見報告的倖存者偏誤說明)。
輸出 raw/long.pkl(不進版控)與 results/data_inventory.json。"""
import datetime, json, os, pickle, sys, time, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); RES = os.path.join(HERE, 'results'); os.makedirs(RAW, exist_ok=True); os.makedirs(RES, exist_ok=True)
import ccxt
D2 = os.path.join(HERE, '..', 'd2_portfolio', 'raw', 'data.pkl')
d2 = pickle.load(open(D2, 'rb')); MK = d2['markets']
CUR = json.load(open(r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json', encoding='utf-8'))['combos']
SYMS = sorted({c['symbol'] for c in CUR}); ONEH = {c['symbol'] for c in CUR if c['timeframe'] == '1h'}
ex = ccxt.binanceusdm({'enableRateLimit': True})
STEP = {'1h': 3600000, '4h': 14400000, '1d': 86400000}
S_ = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d')
now = int(time.time() * 1000); START = int(datetime.datetime(2019, 9, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def klines(sid, tf, start=START):
    rows = []; cur = start; step = STEP[tf]
    while True:
        r = ex.fapiPublicGetKlines({'symbol': sid, 'interval': tf, 'startTime': cur, 'limit': 1500})
        if not r: break
        rows += [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in r]
        if len(r) < 1500: break
        cur = int(r[-1][0]) + step
    rows = [x for x in rows if x[0] + step <= now]                  # 去掉尚未收盤的最後一根
    seen = set(); out = []
    for x in rows:
        if x[0] not in seen: seen.add(x[0]); out.append(x)
    return out


def gaps(rows, step):
    miss = 0; big = []
    for a, b in zip(rows, rows[1:]):
        n = (b[0] - a[0]) // step - 1
        if n > 0: miss += n; big.append((S_(a[0]), int(n)))
    return miss, sorted(big, key=lambda x: -x[1])[:3]


# 1) exchangeInfo:目前合約狀態與上市日
info = ex.fapiPublicGetExchangeInfo()['symbols']
perp = [s for s in info if s.get('contractType') == 'PERPETUAL' and s.get('quoteAsset') == 'USDT']
stat = {}
for s in perp: stat[s['status']] = stat.get(s['status'], 0) + 1
onboard = {s['symbol']: int(s.get('onboardDate') or 0) for s in perp}
inv = {'generated': S_(now), 'exchange_info': {'usdt_perpetuals_listed_now': len(perp), 'by_status': stat, 'other_contract_types': sorted({s.get('contractType') for s in info}),
       'note': 'exchangeInfo 只列出「目前還存在」的合約;已下架(delisted)的合約不在公開清單裡,無法列舉,所以任何由今天清單挑出的組合都有倖存者偏誤。'}, 'symbols': {}}
long = {'candles': {}, 'funding': {}, 'markets': {}, 'fetched_at': now}
for s in SYMS + ['BTC/USDT']:
    sid = MK[s]['id'] if s in MK else s.replace('/', '')
    long['markets'][s] = MK.get(s) or {'step': 0.001, 'min_cost': 5.0, 'id': sid}
    e = {'id': sid, 'onboard_date': S_(onboard[sid]) if onboard.get(sid) else None, 'one_hour_combo': s in ONEH}
    tfs = ['4h', '1h'] if (s in ONEH or s == 'BTC/USDT') else ['4h', '1h']
    for tf in tfs:
        t0 = time.time(); rows = klines(sid, tf); long['candles'][(s, tf)] = rows
        g, big = gaps(rows, STEP[tf])
        e[tf] = {'bars': len(rows), 'first': S_(rows[0][0]) if rows else None, 'last': S_(rows[-1][0]) if rows else None, 'missing_bars': g, 'largest_gaps': big}
        print(s, tf, len(rows), e[tf]['first'], 'gaps', g, '%.0fs' % (time.time() - t0), flush=True)
    fr = []; cur = START
    while True:
        r = ex.fapiPublicGetFundingRate({'symbol': sid, 'startTime': cur, 'limit': 1000})
        if not r: break
        fr += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
        if len(r) < 1000: break
        cur = int(r[-1]['fundingTime']) + 1
    long['funding'][s] = sorted(set(fr)); e['funding_records'] = len(fr); e['funding_first'] = S_(fr[0][0]) if fr else None
    inv['symbols'][s] = e
pickle.dump(long, open(os.path.join(RAW, 'long.pkl'), 'wb'))
json.dump(inv, open(os.path.join(RES, 'data_inventory.json'), 'w'), ensure_ascii=False, indent=1)
print('saved')
