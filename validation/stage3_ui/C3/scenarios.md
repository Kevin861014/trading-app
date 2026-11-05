# C3 情境摘要（離線快照的真實 API 回應 → /api/rule_summary）

## normal_BTC（BTC/USDT 4h sixline）— 描述性摘要

**【描述性摘要】目前標的自身環境為「趨勢轉換中」；樣本內 30 筆、淨 PF 1.14。以下逐項說明依據與限制；這不是預測或買賣訊號。**

### 資料品質
- 策略所用資料（4h，最後已收盤 K 棒 2026-11-05 08:00 UTC）品質：資料正常。  `study.dataInterval, study.data.lastBar, study.dataQuality.label`
- 多週期資料品質：日線 資料正常、4 小時 資料正常。  `mtf.timeframes[0].label, mtf.timeframes[0].quality.label, mtf.timeframes[1].label…`

### 目前市場環境與判斷依據
- 最後已收盤 K 棒（2026-11-05 08:00 UTC）的標的自身環境：「趨勢轉換中」。  `study.currentRegime.barTime, study.currentRegime.own`
- 判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：ADX (Wilder, 14) 23.7，+DI 27.1、−DI 16.0。  `mtf.timeframes[1].indicators.adxLabel, mtf.timeframes[1].indicators.adx, mtf.timeframes[1].indicators.plusDi…`
- EMA：均線未排列(糾結)；收盤價位於 EMA50之上。  `mtf.timeframes[1].indicators.emaAlignText, mtf.timeframes[1].indicators.above.ema50`
- 大盤環境（BTC（幣安永續））：「趨勢轉換中」。  `study.reference.name, study.currentRegime.market`

### 各時間週期是否一致
- 各週期的技術指標方向分歧(日線中性、4 小時偏多)。  `mtf.summary.text`
- 各週期技術偏向（只列資料可用的）：日線中性／分歧、4 小時偏多。這只是指標位置的描述，不是價格預測。  `mtf.timeframes[0].label, mtf.timeframes[0].indicators.bias, mtf.timeframes[1].label…`

### 選定策略的歷史績效
- 「六條線 多頭排列(課程核心・最強)」窗口內（2024-11-05 起）共 43 筆交易（扣成本）：淨 PF 1.28、勝率 20.9%、最大回撤 12.59%、報酬 -1.36%（本站回測口徑）。  `study.strategyName, study.windowStart, study.overall.all.trades…`
- 樣本內 30 筆（初步觀察），淨 PF 1.14、最大回撤 11.10%。  `study.overall.is.trades, study.overall.is.trades, study.overall.is.pf…`
- 樣本內淨 PF 1.14、樣本外 1.66（13 筆）都 ≥ 1：沒有看到樣本外失效的跡象，但這仍只是歷史統計。 樣本外只有 13 筆（樣本不足），僅供參考。  `study.overall.oos.trades, study.overall.oos.pf, study.overall.is.pf`

### 目前環境下，歷史交易夠不夠支持判斷
- 標的自身目前環境「趨勢轉換中」：樣本內只有 7 筆（樣本不足），樣本外 5 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.own, study.breakdown.own.is.transition.n, study.breakdown.own.oos.transition.n`
- 大盤目前環境「趨勢轉換中」：樣本內只有 7 筆（樣本不足），樣本外 5 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.market, study.breakdown.market.is.transition.n, study.breakdown.market.oos.transition.n`

### 市場濾網對照
- 濾網（只在 上升趨勢、趨勢轉換中 進場）後樣本內只剩 15 筆（原始 30 筆），資料不足，不下結論。  `study.filter.B.is.trades, study.filter.A.is.trades, study.filter.B.is.pf…`
- 樣本外尚未揭露：目前沒有樣本外證據支持這個濾網。  `study.filter.oos.revealed`

## normal_SOL（SOL/USDT 4h sixline）— 描述性摘要

**【描述性摘要】目前標的自身環境為「上升趨勢」；樣本內 26 筆、淨 PF 0.95。以下逐項說明依據與限制；這不是預測或買賣訊號。**

### 資料品質
- 策略所用資料（4h，最後已收盤 K 棒 2026-11-05 08:00 UTC）品質：資料正常。  `study.dataInterval, study.data.lastBar, study.dataQuality.label`
- 多週期資料品質：日線 資料正常、4 小時 資料正常。  `mtf.timeframes[0].label, mtf.timeframes[0].quality.label, mtf.timeframes[1].label…`

### 目前市場環境與判斷依據
- 最後已收盤 K 棒（2026-11-05 08:00 UTC）的標的自身環境：「上升趨勢」。  `study.currentRegime.barTime, study.currentRegime.own`
- 判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：ADX (Wilder, 14) 26.5，+DI 24.0、−DI 16.9。  `mtf.timeframes[1].indicators.adxLabel, mtf.timeframes[1].indicators.adx, mtf.timeframes[1].indicators.plusDi…`
- EMA：EMA20 < EMA50 < EMA200(空頭排列)；收盤價位於 EMA50之上。  `mtf.timeframes[1].indicators.emaAlignText, mtf.timeframes[1].indicators.above.ema50`
- 大盤環境（BTC（幣安永續））：「趨勢轉換中」。  `study.reference.name, study.currentRegime.market`

### 各時間週期是否一致
- 各週期的技術指標方向分歧(日線偏空、4 小時中性)。  `mtf.summary.text`
- 各週期技術偏向（只列資料可用的）：日線偏空、4 小時中性／分歧。這只是指標位置的描述，不是價格預測。  `mtf.timeframes[0].label, mtf.timeframes[0].indicators.bias, mtf.timeframes[1].label…`

### 選定策略的歷史績效
- 「六條線 多頭排列(課程核心・最強)」窗口內（2024-11-05 起）共 32 筆交易（扣成本）：淨 PF 1.32、勝率 31.2%、最大回撤 6.12%、報酬 15.28%（本站回測口徑）。  `study.strategyName, study.windowStart, study.overall.all.trades…`
- 樣本內 26 筆（初步觀察），淨 PF 0.95、最大回撤 6.12%。  `study.overall.is.trades, study.overall.is.trades, study.overall.is.pf…`
- 樣本內淨 PF 0.95（< 1）而樣本外 3.97（6 筆）≥ 1：兩段不一致，不宜據此判斷。 樣本外只有 6 筆（樣本不足），僅供參考。  `study.overall.oos.trades, study.overall.oos.pf, study.overall.is.pf`

### 目前環境下，歷史交易夠不夠支持判斷
- 標的自身目前環境「上升趨勢」：樣本內只有 7 筆（樣本不足），樣本外 2 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.own, study.breakdown.own.is.up.n, study.breakdown.own.oos.up.n`
- 大盤目前環境「趨勢轉換中」：樣本內只有 6 筆（樣本不足），樣本外 1 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.market, study.breakdown.market.is.transition.n, study.breakdown.market.oos.transition.n`

## insufficient_2330（2330.TW 1d diadx）— 樣本不足或資料不足

**【樣本不足】樣本內只有 5 筆交易（少於 20 筆）：下列數字只是描述，不能當成策略有效或無效的證據。**

### 資料品質
- 策略所用資料（1d，最後已收盤 K 棒 2026-11-05 00:00 UTC）品質：資料正常。  `study.dataInterval, study.data.lastBar, study.dataQuality.label`
- 多週期資料品質：日線 資料正常。  `mtf.timeframes[0].label, mtf.timeframes[0].quality.label`

### 目前市場環境與判斷依據
- 最後已收盤 K 棒（2026-11-05 00:00 UTC）的標的自身環境：「趨勢轉換中」。  `study.currentRegime.barTime, study.currentRegime.own`
- 判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：ADX (Wilder, 14) 21.0，+DI 15.5、−DI 37.1。  `mtf.timeframes[0].indicators.adxLabel, mtf.timeframes[0].indicators.adx, mtf.timeframes[0].indicators.plusDi…`
- EMA：均線未排列(糾結)；收盤價位於 EMA50之下。  `mtf.timeframes[0].indicators.emaAlignText, mtf.timeframes[0].indicators.above.ema50`
- 大盤環境（台灣加權指數）：「下降趨勢」。  `study.reference.name, study.currentRegime.market`

### 各時間週期是否一致
- 可用的週期少於 2 個,無法比較。  `mtf.summary.text`
- 各週期技術偏向（只列資料可用的）：日線偏空。這只是指標位置的描述，不是價格預測。  `mtf.timeframes[0].label, mtf.timeframes[0].indicators.bias`

### 選定策略的歷史績效
- 「DMI/ADX 方向動能(四市場全過・台股最強)」窗口內（2024-11-05 起）共 6 筆交易（扣成本）：淨 PF 0.00、勝率 0.0%、最大回撤 2.35%、報酬 -1.84%（本站回測口徑）。  `study.strategyName, study.windowStart, study.overall.all.trades…`
- 樣本內 5 筆（樣本不足），淨 PF 0.00、最大回撤 1.90%。樣本不足，這些數字只是描述，不能當成策略有效的證據。  `study.overall.is.trades, study.overall.is.trades, study.overall.is.pf…`
- 樣本外只有 1 筆，證據不足，不能判斷策略在樣本外是否延續。  `study.overall.oos.trades, study.overall.oos.pf, study.overall.is.pf`

### 目前環境下，歷史交易夠不夠支持判斷
- 標的自身目前環境「趨勢轉換中」：樣本內只有 2 筆（樣本不足），樣本外 1 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.own, study.breakdown.own.is.transition.n, study.breakdown.own.oos.transition.n`
- 大盤目前環境「下降趨勢」：樣本內只有 1 筆（樣本不足），樣本外 0 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.market, study.breakdown.market.is.down.n, study.breakdown.market.oos.down.n`

## insufficient_AAPL（AAPL 1d tsmom）— 樣本不足或資料不足

**【樣本不足】樣本內只有 5 筆交易（少於 20 筆）：下列數字只是描述，不能當成策略有效或無效的證據。**

### 資料品質
- 策略所用資料（1d，最後已收盤 K 棒 2026-11-04 00:00 UTC）品質：資料正常。  `study.dataInterval, study.data.lastBar, study.dataQuality.label`
- 多週期資料品質：日線 資料正常。  `mtf.timeframes[0].label, mtf.timeframes[0].quality.label`

### 目前市場環境與判斷依據
- 最後已收盤 K 棒（2026-11-04 00:00 UTC）的標的自身環境：「盤整」。  `study.currentRegime.barTime, study.currentRegime.own`
- 判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：ADX (Wilder, 14) 18.6，+DI 31.7、−DI 25.0。  `mtf.timeframes[0].indicators.adxLabel, mtf.timeframes[0].indicators.adx, mtf.timeframes[0].indicators.plusDi…`
- EMA：EMA20 > EMA50 > EMA200(多頭排列)；收盤價位於 EMA50之上。  `mtf.timeframes[0].indicators.emaAlignText, mtf.timeframes[0].indicators.above.ema50`
- 大盤環境（S&P 500）：「盤整」。  `study.reference.name, study.currentRegime.market`

### 各時間週期是否一致
- 可用的週期少於 2 個,無法比較。  `mtf.summary.text`
- 各週期技術偏向（只列資料可用的）：日線偏多。這只是指標位置的描述，不是價格預測。  `mtf.timeframes[0].label, mtf.timeframes[0].indicators.bias`

### 選定策略的歷史績效
- 「時間序列動能(四市場全過・美股最強)」窗口內（2024-11-05 起）共 12 筆交易（扣成本）：淨 PF 8.34、勝率 58.3%、最大回撤 3.97%、報酬 10.71%（本站回測口徑）。  `study.strategyName, study.windowStart, study.overall.all.trades…`
- 樣本內 5 筆（樣本不足），淨 PF 6.10、最大回撤 3.97%。樣本不足，這些數字只是描述，不能當成策略有效的證據。  `study.overall.is.trades, study.overall.is.trades, study.overall.is.pf…`
- 樣本內淨 PF 6.10、樣本外 12.89（7 筆）都 ≥ 1：沒有看到樣本外失效的跡象，但這仍只是歷史統計。 樣本外只有 7 筆（樣本不足），僅供參考。  `study.overall.oos.trades, study.overall.oos.pf, study.overall.is.pf`

### 目前環境下，歷史交易夠不夠支持判斷
- 標的自身目前環境「盤整」：樣本內只有 2 筆（樣本不足），樣本外 6 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.own, study.breakdown.own.is.range.n, study.breakdown.own.oos.range.n`
- 大盤目前環境「盤整」：樣本內只有 3 筆（樣本不足），樣本外 3 筆，不足以判斷策略在這個環境是否有效。  `study.currentRegime.market, study.breakdown.market.is.range.n, study.breakdown.market.oos.range.n`

## stale_BTC（BTC/USDT 4h sixline）— 資料過期或異常

**【資料過期或異常】策略所用資料品質為「資料過期」：不評估目前環境，以下只是歷史狀態的描述。**

### 資料品質
- 策略所用資料（4h，最後已收盤 K 棒 2026-11-05 08:00 UTC）品質：資料過期。最新已收盤的 4h K 棒應為 2026-11-17 08:00 UTC,但資料只到 2026-11-05 08:00 UTC(落後 72 根) 因此以下所有內容只是歷史狀態，不代表目前，也不下結論。  `study.dataInterval, study.data.lastBar, study.dataQuality.label…`
- 多週期資料品質：日線 資料過期、4 小時 資料過期。  `mtf.timeframes[0].label, mtf.timeframes[0].quality.label, mtf.timeframes[1].label…`

### 目前市場環境與判斷依據
- 最後已收盤 K 棒（2026-11-05 08:00 UTC）的標的自身環境：「趨勢轉換中」。（資料過期/異常，這是最後一根已收盤 K 棒的歷史狀態）  `study.currentRegime.barTime, study.currentRegime.own`
- 判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：ADX (Wilder, 14) 23.7，+DI 27.1、−DI 16.0。  `mtf.timeframes[1].indicators.adxLabel, mtf.timeframes[1].indicators.adx, mtf.timeframes[1].indicators.plusDi…`
- EMA：均線未排列(糾結)；收盤價位於 EMA50之上。  `mtf.timeframes[1].indicators.emaAlignText, mtf.timeframes[1].indicators.above.ema50`
- 大盤環境（BTC（幣安永續））：「趨勢轉換中」。  `study.reference.name, study.currentRegime.market`

### 各時間週期是否一致
- 可用的週期少於 2 個,無法比較。  `mtf.summary.text`

### 選定策略的歷史績效
- 「六條線 多頭排列(課程核心・最強)」窗口內（2024-11-17 起）共 42 筆交易（扣成本）：淨 PF 0.64、勝率 19.0%、最大回撤 12.59%、報酬 -6.57%（本站回測口徑）。  `study.strategyName, study.windowStart, study.overall.all.trades…`
- 樣本內 29 筆（初步觀察），淨 PF 0.26、最大回撤 11.10%。  `study.overall.is.trades, study.overall.is.trades, study.overall.is.pf…`
- 樣本內淨 PF 0.26（< 1）而樣本外 1.66（13 筆）≥ 1：兩段不一致，不宜據此判斷。 樣本外只有 13 筆（樣本不足），僅供參考。  `study.overall.oos.trades, study.overall.oos.pf, study.overall.is.pf`

### 目前環境下，歷史交易夠不夠支持判斷
- 資料過期、異常或未檢查，不評估目前環境下的歷史表現。  ``

## notrades_BTC（BTC/USDT 4h adx_di_trend）— 沒有交易

**【沒有交易】此策略在窗口內沒有任何交易，無法評估，也不做推論。**

### 資料品質
- 策略所用資料（4h，最後已收盤 K 棒 2026-11-05 08:00 UTC）品質：資料正常。  `study.dataInterval, study.data.lastBar, study.dataQuality.label`
- 多週期資料品質：日線 資料正常、4 小時 資料正常。  `mtf.timeframes[0].label, mtf.timeframes[0].quality.label, mtf.timeframes[1].label…`

### 目前市場環境與判斷依據
- 最後已收盤 K 棒（2026-11-05 08:00 UTC）的標的自身環境：「趨勢轉換中」。  `study.currentRegime.barTime, study.currentRegime.own`
- 判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：ADX (Wilder, 14) 23.7，+DI 27.1、−DI 16.0。  `mtf.timeframes[1].indicators.adxLabel, mtf.timeframes[1].indicators.adx, mtf.timeframes[1].indicators.plusDi…`
- EMA：均線未排列(糾結)；收盤價位於 EMA50之上。  `mtf.timeframes[1].indicators.emaAlignText, mtf.timeframes[1].indicators.above.ema50`
- 大盤環境（BTC（幣安永續））：「趨勢轉換中」。  `study.reference.name, study.currentRegime.market`

### 各時間週期是否一致
- 各週期的技術指標方向分歧(日線中性、4 小時偏多)。  `mtf.summary.text`
- 各週期技術偏向（只列資料可用的）：日線中性／分歧、4 小時偏多。這只是指標位置的描述，不是價格預測。  `mtf.timeframes[0].label, mtf.timeframes[0].indicators.bias, mtf.timeframes[1].label…`

### 選定策略的歷史績效
- 此策略「ADX>25 上升跟 DI」在窗口內（2025-11-05 起）沒有任何交易，無法評估，也不做任何推論。  `study.strategyName, study.windowStart`

### 目前環境下，歷史交易夠不夠支持判斷
- 沒有交易，無法評估目前環境下的歷史表現。  ``

