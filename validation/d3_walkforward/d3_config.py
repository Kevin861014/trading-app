# -*- coding: utf-8 -*-
"""D3 事先固定的設定(在看任何結果之前寫死):區段、分類、BTC 區段標籤規則、成本/風險參數。測試會檢查這些不被改動。"""
import datetime
ms = lambda y, m, d: int(datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc).timestamp() * 1000)
INIT = 310.0
ONE_H = ('TRX/USDT', 'XRP/USDT')
# (類別, 名稱, 起, 迄)  迄 = None 代表『到資料結束』
BLOCKS = [('I', '2021H1', ms(2021, 1, 1), ms(2021, 7, 1)), ('I', '2021H2', ms(2021, 7, 1), ms(2022, 1, 1)), ('I', '2022H1', ms(2022, 1, 1), ms(2022, 7, 1)), ('I', '2022H2', ms(2022, 7, 1), ms(2023, 1, 1)),
          ('I', '2023H1', ms(2023, 1, 1), ms(2023, 7, 1)), ('G', '2023H2', ms(2023, 7, 1), ms(2024, 1, 1)), ('G', '2024-01~02', ms(2024, 1, 1), ms(2024, 3, 1)),
          ('X', '2024-03~12', ms(2024, 3, 1), ms(2025, 1, 1)), ('X', '2025H1', ms(2025, 1, 1), ms(2025, 7, 1)), ('X', '2025H2', ms(2025, 7, 1), ms(2026, 1, 1)), ('X', '2026H1', ms(2026, 1, 1), ms(2026, 7, 1)),
          ('X', '2026-07~10-29', ms(2026, 7, 1), ms(2026, 10, 29)), ('T', '2026-10-29~now', ms(2026, 10, 29), None)]
CLASS_LABEL = {'I': '較獨立的歷史(未證明獨立)', 'G': '灰色地帶(曾被取得當暖機,不算獨立)', 'X': '歷史探索(選擇已看過)', 'T': '選擇之後(太短)'}
SELECTION_EXPOSED_FROM = ms(2023, 7, 1)          # 此日之後的歷史都不算獨立(深度分析取得範圍 ≈ 選擇日往前 1130 天;策略庫研究用 900 天 4H 快取)
REGIME_UP, REGIME_DOWN = 15.0, -15.0               # BTC 區段漲跌 > +15% 上升、< −15% 下跌、其餘盤整
# D2 已校準的成本/風險(不重新調整)
PB = dict(slip_entry=0.0003, slip_exit=0.0001, slip_stop=0.00042, sumw_override=16.0)
PS = dict(taker=0.00075, slip_entry=0.0006, slip_exit=0.0002, slip_stop=0.00084, sumw_override=16.0)    # 成本 ×1.5
D2_CALIBRATED = dict(risk=0.0403, max_lev=3.0, max_total=3.0, taker=0.0005)


def btc_regime(pct):
    return 'up' if pct > REGIME_UP else ('down' if pct < REGIME_DOWN else 'range')
