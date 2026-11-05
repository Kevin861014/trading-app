import sys, os, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binance_ro import *
ex = make_client()
# 1) 白名單自測:下單/撤單/改槓桿的路徑必須被擋掉(不會真的送出)
for m, p in (('POST', 'https://fapi.binance.com/fapi/v1/order'), ('DELETE', 'https://fapi.binance.com/fapi/v1/order'), ('POST', 'https://fapi.binance.com/fapi/v1/leverage'), ('GET', 'https://fapi.binance.com/sapi/v1/capital/withdraw/apply')):
    try: ex.fetch(p, m); print('NOT BLOCKED', m, p)
    except ReadOnlyViolation as e: print('blocked ok:', m, p.split('.com')[1])
# 2) 能讀到什麼(只印筆數與日期範圍,不印金額/金鑰)
now = int(time.time() * 1000)
for name, fn, par in (('account', ex.fapiPrivateV2GetAccount, {}), ('income_7d', ex.fapiPrivateGetIncome, {'limit': 1000})):
    try:
        r = call(ex, fn, par); print(name, 'ok', type(r).__name__, (len(r) if isinstance(r, list) else list(r.keys())[:6]))
    except Exception as e: print(name, 'ERR', e)
# 最早的 income 記錄(往前找)
for days in (30, 60, 90, 100, 120, 200):
    try:
        r = call(ex, ex.fapiPrivateGetIncome, {'startTime': now - days * 86400000, 'endTime': now - (days - 7) * 86400000, 'limit': 1000})
        print('income window', days, 'days ago ->', len(r), 'records', (datetime.datetime.utcfromtimestamp(int(r[0]['time']) / 1000).strftime('%Y-%m-%d') if r else ''))
    except Exception as e: print('income window', days, 'ERR', e)
