# -*- coding: utf-8 -*-
"""稽核 B4:排除「現貨冒充永續」。
(1) exchangeInfo(公開):BTC/TRX/XRP/SOL 的 contractType 必須是 PERPETUAL、quote=USDT。
(2) 同一時段向『現貨』公開端點 /api/v3/klines 取 1H,與本機快取比對:應該有明顯差異(價格小差、成交量差很多),代表本機資料不是現貨。
只有公開 GET;不改任何既有檔案。"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SYMS = ['BTCUSDT', 'TRXUSDT', 'XRPUSDT', 'SOLUSDT']; NOW = int(time.time() * 1000); out = {'contract': [], 'spot_vs_local': []}
info = get(FAPI, '/fapi/v1/exchangeInfo')['symbols']
for s in SYMS:
    m = next((x for x in info if x['symbol'] == s), None)
    out['contract'].append({'symbol': s, 'contractType': m and m.get('contractType'), 'quoteAsset': m and m.get('quoteAsset'), 'status': m and m.get('status'), 'onboardDate': m and U(int(m['onboardDate']))})
    print(out['contract'][-1])
LOC, _ = load_local()
for s in SYMS:
    u = to_unified(s)
    for tf, lo, hi in (('1h', MS(2025, 6, 1), MS(2025, 6, 4)), ('4h', MS(2025, 6, 1), MS(2025, 6, 8))):
        try: sp = klines(s, tf, lo, hi, base=SPOT, path='/api/v3/klines', now=NOW)
        except Exception as e: out['spot_vs_local'].append({'sym': s, 'tf': tf, 'error': str(e)[:120]}); print('spot fail', s, tf, str(e)[:100]); continue
        loc = LOC['D3'][(u, tf)]; same_all = same_ohlc = vol_ratio = 0; vr = []
        for x in sp:
            l = loc.get(int(x[0]))
            if not l: continue
            same_ohlc += all(float(x[i]) == l[i] for i in (1, 2, 3, 4)); same_all += all(float(x[i]) == l[i] for i in (1, 2, 3, 4, 5))
            if float(x[5]) > 0: vr.append(l[5] / float(x[5]))
        vr.sort(); r = {'sym': s, 'tf': tf, 'spot_rows': len(sp), 'local_rows_same_ohlc_as_spot': same_ohlc, 'local_rows_same_ohlcv_as_spot': same_all, 'median_local_vol_over_spot_vol': vr[len(vr) // 2] if vr else None}
        out['spot_vs_local'].append(r); print(r, flush=True)
json.dump(out, open(os.path.join(OUT, 'b4_spot_contract.json'), 'w'), ensure_ascii=False, indent=1); json.dump(REQLOG, open(os.path.join(OUT, 'b4_requests.json'), 'w'), ensure_ascii=False)
