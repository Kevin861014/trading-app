# -*- coding: utf-8 -*-
"""D4 行情來源:幣安 USDT-M 永續合約『公開』端點(fapi klines / fundingRate / exchangeInfo)。沒有金鑰、沒有任何私有或寫入端點。
只回傳『已收盤』的 K 棒(開盤時間 + 週期 ≤ 現在 − 安全緩衝)。"""
import time

STEP = {'1h': 3600000, '4h': 14400000}
SAFETY_MS = 5000


class BinanceFeed:
    def __init__(self):
        import ccxt
        self.ex = ccxt.binanceusdm({'enableRateLimit': True})          # 不帶任何金鑰:只能打公開端點

    def now_ms(self): return int(time.time() * 1000)

    def klines(self, sid, tf, start_ms):
        step = STEP[tf]; now = self.now_ms(); cur = int(start_ms); rows = []
        while True:
            r = self.ex.fapiPublicGetKlines({'symbol': sid, 'interval': tf, 'startTime': cur, 'limit': 1500})
            if not r: break
            rows += [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in r]
            if len(r) < 1500: break
            cur = int(r[-1][0]) + step
        return [x for x in rows if x[0] + step <= now - SAFETY_MS]

    def funding(self, sid, start_ms):
        cur = int(start_ms); out = []
        while True:
            r = self.ex.fapiPublicGetFundingRate({'symbol': sid, 'startTime': cur, 'limit': 1000})
            if not r: break
            out += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
            if len(r) < 1000: break
            cur = int(r[-1]['fundingTime']) + 1
        return out

    def markets(self, symbols):
        mk = self.ex.load_markets(); out = {}
        for s in symbols:
            m = mk.get(s + ':USDT') or mk.get(s)
            if m: out[s] = {'id': m['id'], 'step': (m.get('precision') or {}).get('amount'), 'min_amount': ((m.get('limits') or {}).get('amount') or {}).get('min'), 'min_cost': ((m.get('limits') or {}).get('cost') or {}).get('min')}
        return out
