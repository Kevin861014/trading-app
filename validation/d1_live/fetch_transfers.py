# -*- coding: utf-8 -*-
"""D1:入金/出金/劃轉的唯讀歷史查詢(GET)。權限不足或沒有資料就如實記錄,不推算。"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binance_ro import *
HERE = os.path.dirname(os.path.abspath(__file__))
ex = make_client(); now = int(time.time() * 1000); DAY = 86400000
out = {}; status = {}


def try_(name, fn, par):
    try:
        r = call(ex, fn, par); out[name] = r; status[name] = 'ok:%s' % (len(r) if isinstance(r, list) else (len(r.get('rows', [])) if isinstance(r, dict) and 'rows' in r else 'dict'))
    except Exception as e:
        status[name] = 'ERR:' + str(e)[:140]


for s in range(0, 330, 85):                                       # 查詢窗口最多 90 天
    st, en = now - (s + 85) * DAY, now - s * DAY
    try_('deposit_%d' % s, ex.sapiGetCapitalDepositHisrec, {'startTime': st, 'endTime': en, 'limit': 1000})
    try_('withdraw_%d' % s, ex.sapiGetCapitalWithdrawHistory, {'startTime': st, 'endTime': en, 'limit': 1000})
    for ty in ('MAIN_UMFUTURE', 'UMFUTURE_MAIN'):
        try_('xfer_%s_%d' % (ty, s), ex.sapiGetAssetTransfer, {'type': ty, 'startTime': st, 'endTime': en, 'size': 100})
json.dump({'data': out, 'status': status}, open(os.path.join(HERE, 'raw', 'transfers_raw.json'), 'w'))
for k, v in status.items(): print(k, v)
