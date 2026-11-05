# -*- coding: utf-8 -*-
"""D2 階段一:調查 D1 的對帳差額。全部唯讀(GET)。
做法:短時間內連續取 收支(income) → 帳戶/餘額快照 → 再取一次收支,確認中間沒有新紀錄;逐筆比對成交(userTrades)與收支;分別列出『帳戶快照損益』『收支重建損益』與差額。"""
import collections, json, os, sys, time, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'd1_live'))
from binance_ro import *
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'raw'); os.makedirs(RAW, exist_ok=True)
ex = make_client(); DAY = 86400000


def all_income():
    now = int(time.time() * 1000); out = []; t = now - 330 * DAY
    while t < now + 1000:
        end = min(t + 30 * DAY, now + 5000); cur = t
        while True:
            r = call(ex, ex.fapiPrivateGetIncome, {'startTime': cur, 'endTime': end, 'limit': 1000}); out += r
            if len(r) < 1000: break
            cur = int(r[-1]['time']) + 1
        t = end
    seen = {}; 
    for x in out: seen[json.dumps(x, sort_keys=True)] = x
    return sorted(seen.values(), key=lambda x: (int(x['time']), x['incomeType'], str(x.get('tradeId'))))


i1 = all_income()
acc = call(ex, ex.fapiPrivateV2GetAccount, {}); bal = call(ex, ex.fapiPrivateV2GetBalance, {}) if hasattr(ex, 'fapiPrivateV2GetBalance') else None
time.sleep(1); i2 = all_income()
usdt = next((b for b in (bal or []) if b.get('asset') == 'USDT'), {})
snap = {k: acc.get(k) for k in ('totalWalletBalance', 'totalUnrealizedProfit', 'totalMarginBalance', 'availableBalance', 'totalCrossWalletBalance', 'totalCrossUnPnl', 'totalInitialMargin', 'totalPositionInitialMargin', 'totalOpenOrderInitialMargin', 'maxWithdrawAmount')}
assets = [a for a in acc.get('assets', []) if a.get('asset') == 'USDT']
snap['usdt_asset'] = {k: assets[0].get(k) for k in ('walletBalance', 'unrealizedProfit', 'marginBalance', 'crossWalletBalance', 'crossUnPnl', 'initialMargin', 'positionInitialMargin', 'openOrderInitialMargin', 'maintMargin', 'availableBalance')} if assets else None
snap['balance_endpoint_usdt'] = {k: usdt.get(k) for k in ('balance', 'crossWalletBalance', 'crossUnPnl', 'availableBalance')}
snap['asOf'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
# 逐筆:成交 vs 收支
fills = json.load(open(os.path.join(HERE, '..', 'd1_live', 'raw', 'user_trades.json')))
# 補抓最新成交(D1 之後可能有新成交):只抓有持倉或近期有紀錄的幣的最近 7 天
now = int(time.time() * 1000); syms = list(fills.keys())
for s in syms:
    r = call(ex, ex.fapiPrivateGetUserTrades, {'symbol': s, 'startTime': now - 6 * DAY, 'endTime': now + 5000, 'limit': 1000})
    have = {f['id'] for f in fills[s]}; fills[s] += [f for f in r if f['id'] not in have]
fc = {}; fr = {}
for s, rows in fills.items():
    for f in rows: fc[(s, f['id'])] = float(f['commission']); fr[(s, f['id'])] = float(f['realizedPnl'])
ic = {}; ir = {}; other = collections.defaultdict(float); fund = 0.0
for x in i2:
    t = x['incomeType']; v = float(x['income'])
    if t == 'COMMISSION': ic[(x['symbol'], str(x.get('tradeId')))] = ic.get((x['symbol'], str(x.get('tradeId'))), 0) + v
    elif t == 'REALIZED_PNL': ir[(x['symbol'], str(x.get('tradeId')))] = ir.get((x['symbol'], str(x.get('tradeId'))), 0) + v
    elif t == 'FUNDING_FEE': fund += v
    else: other[t] += v
miss_c = [k for k in fc if (k[0], str(k[1])) not in ic]; extra_c = [k for k in ic if (k[0], k[1]) not in {(a, str(b)) for a, b in fc}]
tot = lambda xs: sum(float(x['income']) for x in xs if x['incomeType'] in ('REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE'))
deposits = 152.49132399 + 156.389344       # 唯讀劃轉歷史(D1 已取得)
wallet = float(snap['totalWalletBalance']); unreal = float(snap['totalUnrealizedProfit'])
res = {'snap': snap, 'income_records_first_pass': len(i1), 'income_records_second_pass': len(i2), 'new_records_between_passes': len(i2) - len(i1),
       'fills': sum(len(v) for v in fills.values()), 'fills_commission_sum': round(sum(fc.values()), 6), 'income_commission_sum': round(sum(ic.values()), 6), 'fills_missing_in_income': len(miss_c), 'income_without_fill': len(extra_c),
       'fills_realized_sum': round(sum(fr.values()), 6), 'income_realized_sum': round(sum(ir.values()), 6), 'income_funding_sum': round(fund, 6), 'income_other_types': dict(other),
       'deposits_to_futures': deposits, 'income_total_pnl': round(tot(i2), 6),
       'snapshot_based_pnl_wallet': round(wallet - deposits, 6), 'snapshot_based_pnl_with_unrealized': round(wallet + unreal - deposits, 6),
       'income_based_pnl_realized': round(tot(i2), 6), 'residual_wallet_vs_income': round(wallet - deposits - tot(i2), 6)}
json.dump({'result': res}, open(os.path.join(HERE, 'results', 'reconcile.json'), 'w'), ensure_ascii=False, indent=1) if os.path.isdir(os.path.join(HERE, 'results')) else None
os.makedirs(os.path.join(HERE, 'results'), exist_ok=True); json.dump({'result': res}, open(os.path.join(HERE, 'results', 'reconcile.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
