# -*- coding: utf-8 -*-
"""C1 畫面展示用的『狀態範例』伺服器(只綁 127.0.0.1,埠由參數指定)。

資料是固定種子的合成資料,而且刻意做出各種資料品質問題,用來驗證:真實的程式路徑(/api/mtf、/api/signal、/api/analyze、卡片與多週期畫面)
遇到這些狀況時,畫面是否如實標示。這不是行情,不要拿來做任何判斷。時鐘固定在 2026-11-08(週日)12:30 UTC。

標的 → 情境:
  BTC/USDT  日線、4H 正常;1H 落後 13 根(資料過期);週線只有 30 根(資料不足);4H 的最後一根尚未收盤(已排除)
  SOL/USDT  日線有重複時間戳(時間戳異常);4H 取得失敗;1H 為合成且有不完整區間;週線正常
  AAPL      日線停在週三,但大盤(SPY)週五有開盤 → 這個標的沒更新(過期);1H 同樣落後
  NVDA      全部正常,現在是週日(休市,資料到週五)→ 資料正常(休市中)
  2330.TW   全部正常,週日休市
"""
import datetime, os, sys, warnings
warnings.filterwarnings('ignore'); os.environ['RENDER'] = 'true'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, ROOT)
import app as A
from tests.test_mtf_api import walk, trading_day_rows, ms, HOUR, DAY, WEEK

NOW = datetime.datetime(2026, 11, 8, 12, 30)
A._utcnow = lambda: NOW


def stock_1h(last_open_ms, n, seed):
    return walk(last_open_ms, HOUR, n, seed)


def books():
    return {
        'BTC/USDT': {'1w': walk(ms(2026, 10, 26), WEEK, 30, 11), '1d': walk(ms(2026, 11, 7), DAY, 900, 12),
                     '4h': walk(ms(2026, 11, 8, 12), 4 * HOUR, 1500, 13),                   # 12:00 開盤的這根尚未收盤
                     '1h': walk(ms(2026, 11, 7, 21), HOUR, 1500, 14)},                       # 落後約 13 小時
        'SOL/USDT': {'1w': walk(ms(2026, 10, 26), WEEK, 300, 21), '1d': walk(ms(2026, 11, 7), DAY, 900, 22), '4h': None,
                     '1h': walk(ms(2026, 11, 8, 11), HOUR, 1500, 24)},
        'AAPL': {'1w': [[ms(2026, 11, 2) - i * WEEK - WEEK, 100, 101, 99, 100 + i * .01, 1] for i in range(299, -1, -1)], '1d': trading_day_rows(datetime.date(2026, 11, 4), 700, 'us', 31),
                 '1h': stock_1h(ms(2026, 11, 4, 20, 30), 600, 33)},
        'NVDA': {'1w': [[ms(2026, 11, 2) - i * WEEK, 100, 101, 99, 100 + i * .01, 1] for i in range(299, -1, -1)], '1d': trading_day_rows(datetime.date(2026, 11, 6), 700, 'us', 41),
                 '1h': stock_1h(ms(2026, 11, 6, 20, 30), 600, 43)},
        '2330.TW': {'1w': [[ms(2026, 11, 2) - i * WEEK, 100, 101, 99, 100 + i * .01, 1] for i in range(299, -1, -1)], '1d': trading_day_rows(datetime.date(2026, 11, 6), 700, 'tw', 51),
                    '1h': stock_1h(ms(2026, 11, 6, 5), 600, 53)},
    }


BOOKS = books()
BENCH = {'SPY': trading_day_rows(datetime.date(2026, 11, 6), 60, 'us', 61), '^TWII': trading_day_rows(datetime.date(2026, 11, 6), 60, 'tw', 62)}
# 卡片預設自選清單用到的其他標的:給和 2330.TW / AAPL 同型的資料
ALIAS = {'2317.TW': 'AAPL', '2603.TW': '2330.TW', '0050.TW': '2330.TW', '2454.TW': '2330.TW', '2881.TW': '2330.TW', 'MSFT': 'NVDA', 'TSLA': 'NVDA', 'GOOGL': 'NVDA', 'SOL-USD': 'BTC/USDT', 'ETH-USD': 'BTC/USDT', 'BTC-USD': 'BTC/USDT', 'PAXG-USD': 'BTC/USDT'}   # 2317.TW 拿『停在週三』的資料 → 示範卡片的過期標示


def fake_fetch(symbol, start, interval='1d'):
    key = '%s_%s_%s' % (symbol, start, interval)
    if symbol in BENCH: return BENCH[symbol]
    book = BOOKS.get(ALIAS.get(symbol, symbol))
    if book is None: return []
    if symbol == 'SOL/USDT' and interval == '4h': raise RuntimeError('交易所回應逾時(示範用的取得失敗)')
    if symbol == 'SOL/USDT' and interval == '1h':
        A._fetch_meta[key] = {'cached': False, 'ageSec': 0, 'source': 'yfinance(1h→4h 合成)', 'formingExcluded': False, 'synth': {'from': '1h', 'droppedInternal': 3}}
    rows = book.get(interval) or []
    if symbol == 'SOL/USDT' and interval == '1d':
        rows = rows + [list(rows[-1])]                                                       # 重複的時間戳
    return rows


A.fetch_data = fake_fetch

if __name__ == '__main__':
    A.app.run(host='127.0.0.1', port=int(sys.argv[1]) if len(sys.argv) > 1 else 5057, debug=False, threaded=True)
