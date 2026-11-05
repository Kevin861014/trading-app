# -*- coding: utf-8 -*-
"""D1:用唯讀白名單 client 把帳戶的收支(income)、成交(userTrades)、目前持倉存成本機檔案(raw/,不進版控)。只有 GET。"""
import sys, os, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binance_ro import *
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw')
ex = make_client(); now = int(time.time() * 1000); DAY = 86400000
# 1) income:全部類型,從最早往後(每 30 天一段,滿 1000 筆就續頁)
inc = []; t = now - 330 * DAY
while t < now:
    end = min(t + 30 * DAY, now); cur = t
    while True:
        r = call(ex, ex.fapiPrivateGetIncome, {'startTime': cur, 'endTime': end, 'limit': 1000})
        inc += r
        if len(r) < 1000: break
        cur = int(r[-1]['time']) + 1
    t = end
seen = set(); uniq = []
for x in inc:
    k = (x.get('tranId'), x['time'], x['incomeType'], x.get('symbol'), x['income'], x.get('info'))
    if k in seen: continue
    seen.add(k); uniq.append(x)
uniq.sort(key=lambda x: int(x['time']))
json.dump(uniq, open(os.path.join(RAW, 'income.json'), 'w'), ensure_ascii=False)
types = {}
for x in uniq: types[x['incomeType']] = types.get(x['incomeType'], 0) + 1
print('income records', len(uniq), types, 'first', datetime.datetime.utcfromtimestamp(int(uniq[0]['time']) / 1000), 'last', datetime.datetime.utcfromtimestamp(int(uniq[-1]['time']) / 1000))
# 2) userTrades:每個有紀錄的合約,從它第一筆 income 往後每 7 天一段
syms = sorted({x['symbol'] for x in uniq if x.get('symbol')})
first = {}
for x in uniq:
    s = x.get('symbol')
    if s and s not in first: first[s] = int(x['time'])
trades = {}
for s in syms:
    rows = []; t0 = first[s] - 2 * DAY
    while t0 < now:
        end = min(t0 + 7 * DAY - 1, now); cur = t0
        while True:
            r = call(ex, ex.fapiPrivateGetUserTrades, {'symbol': s, 'startTime': cur, 'endTime': end, 'limit': 1000})
            rows += r
            if len(r) < 1000: break
            cur = int(r[-1]['time']) + 1
        t0 += 7 * DAY
    ids = set(); u = []
    for x in rows:
        if x['id'] in ids: continue
        ids.add(x['id']); u.append(x)
    trades[s] = u
    print(s, len(u), flush=True)
json.dump(trades, open(os.path.join(RAW, 'user_trades.json'), 'w'))
# 3) 目前帳戶快照(只留彙總與非零持倉)
a = call(ex, ex.fapiPrivateV2GetAccount, {})
snap = {k: a.get(k) for k in ('totalWalletBalance', 'totalUnrealizedProfit', 'totalMarginBalance', 'availableBalance', 'totalPositionInitialMargin', 'totalInitialMargin')}
snap['positions'] = [{k: p.get(k) for k in ('symbol', 'positionAmt', 'entryPrice', 'unrealizedProfit', 'notional', 'leverage', 'isolatedWallet', 'updateTime') if k in p} for p in a.get('positions', []) if float(p.get('positionAmt') or 0) != 0]
snap['asOf'] = now; json.dump(snap, open(os.path.join(RAW, 'account_snapshot.json'), 'w'), ensure_ascii=False)
print('snapshot positions', len(snap['positions']))
