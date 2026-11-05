# -*- coding: utf-8 -*-
"""D1:幣安『唯讀』查詢工具。
- 只允許 HTTP GET,且只允許下方白名單路徑(帳戶/成交/收支/持倉的讀取與公開行情);任何下單、撤單、改槓桿、轉帳、提領的路徑都會在送出前被擋掉。
- API Key / Secret 從機器人設定檔讀進記憶體(只用來簽名),不顯示、不寫檔、不放進任何輸出;例外訊息也會過濾。
"""
import json, os, re, sys, time
from urllib.parse import urlparse
import ccxt

BOT_CFG = r'C:\Users\User\發大財\順勢交易機器人\config.portfolio.json'
ALLOWED = {
    '/fapi/v1/time', '/fapi/v1/exchangeInfo', '/fapi/v1/klines', '/fapi/v1/ping',               # 公開
    '/fapi/v1/income', '/fapi/v1/userTrades', '/fapi/v2/account', '/fapi/v3/account', '/fapi/v2/balance', '/fapi/v3/balance',
    '/fapi/v2/positionRisk', '/fapi/v3/positionRisk', '/fapi/v1/openOrders', '/fapi/v1/fundingRate',                           # 帳戶唯讀
    '/sapi/v1/capital/deposit/hisrec', '/sapi/v1/capital/withdraw/history', '/sapi/v1/asset/transfer',      # 入金/出金/帳戶間劃轉的『歷史查詢』(只有 GET)
}


class ReadOnlyViolation(RuntimeError):
    pass


def _scrub(msg, secrets):
    s = str(msg)
    for x in secrets:
        if x: s = s.replace(x, '***')
    return re.sub(r'(signature=)[0-9a-f]+', r'\1***', s)[:300]


def guard(orig):
    """包住 ccxt 的 HTTP 送出函式:只放行 GET + 白名單路徑,其餘在送出前就丟 ReadOnlyViolation(不會有任何網路請求)。"""
    def guarded(url, method='GET', headers=None, body=None):
        p = urlparse(url).path
        if str(method).upper() != 'GET': raise ReadOnlyViolation('blocked non-GET request: %s %s' % (method, p))
        if p not in ALLOWED: raise ReadOnlyViolation('blocked path not on the read-only allowlist: %s' % p)
        return orig(url, method, headers, body)
    return guarded


def make_client():
    cfg = json.load(open(BOT_CFG, encoding='utf-8'))
    key, sec = cfg.get('api_key'), cfg.get('api_secret')
    ex = ccxt.binanceusdm({'apiKey': key, 'secret': sec, 'enableRateLimit': True, 'options': {'defaultType': 'future', 'adjustForTimeDifference': False, 'recvWindow': 20000}})
    ex.fetch = guard(ex.fetch)
    ex._secrets = (key, sec)
    # 用伺服器時間校正(機器人日誌裡曾出現 -1021 時間差),只讀 /fapi/v1/time
    try:
        t = ex.fapiPublicGetTime(); ex.options['timeDifference'] = int(t['serverTime']) - int(time.time() * 1000)
    except Exception as e:
        print('time sync failed:', _scrub(e, ex._secrets), file=sys.stderr)
    return ex


def call(ex, fn, params):
    """呼叫一個隱含方法並過濾例外訊息(避免金鑰/簽章外洩);回傳 JSON。"""
    for attempt in range(4):
        try:
            return fn(params)
        except ReadOnlyViolation:
            raise
        except Exception as e:
            msg = _scrub(e, ex._secrets)
            if attempt < 3 and ('429' in msg or '418' in msg or 'Too many' in msg or '-1003' in msg or 'timed out' in msg.lower() or '-1021' in msg):
                time.sleep(2 + attempt * 3); continue
            raise RuntimeError(msg) from None
