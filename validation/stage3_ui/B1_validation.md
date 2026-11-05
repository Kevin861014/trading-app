# 階段三 B1(桌面版 UI 結構、策略比較、回測視覺化)驗證紀錄

分支 `feature/research-platform-ui`(由 `fix/backtest-reliability` 79ee08c 分出)。未 push / merge / 部署;`trading-bot/` 未修改、機器人行程未動(portfolio_bot.py / sim.py / watchdog_bot.py mtime 仍為 2026-08-21 20:10,config.portfolio.json 2026-10-29 21:26;PID 13436、16836 仍在執行)。

## 改了什麼(摘要)
- 後端(僅新增欄位,不改回測/排名/OOS 判定):`/api/analyze` 多回傳 `dataInfo`、`validation`、`backtest`;`/api/best_strategy`、`/api/deep_analysis` 每名多 `oosTier`、`legacyTechPass`。展示分級:OOS <20 筆=樣本不足、20–49=初步觀察、≥50=可進一步評估(只是樣本量分級,不是顯著性,不影響排名)。
- 前端:`index.html` 拆成 HTML / `static/css/{app,ui}.css` / `static/js/*.js`(vanilla、全域作用域,保留原有功能);Lightweight Charts 改自行託管(附 LICENSE/NOTICE/頁尾歸屬)。
- 版面:桌面頂部導覽 + 5 個視圖(自選清單 / 標的分析 / 最佳策略 / 策略實驗室 / 市場環境),hash 路由;精簡卡片(扣成本報酬、淨 PF、最大回撤、樣本外驗證 + 展開詳細);策略比較表(IS / OOS / 全期間 / 驗證分級);標的分析頁(權益曲線 vs 買進持有、回撤、成本、IS/OOS 日期與表格、K 線);市場環境表。
- 結果類型標籤分開:歷史回測 / 樣本外測試 / 即時技術訊號;「紙上交易」標為尚未提供。舊的「≥5 筆且 PF>1」只以「舊版技術門檻(非可信度)」小字出現。
- 修正 `toTime`:日內時間以 UTC 解析(原本依瀏覽器時區,台灣會偏移 8 小時)。
- 台股/美股/貴金屬的 4H 標為「不支援」(見下)。

## 測試
- 單元/整合:`python -X utf8 -m unittest discover -s tests -t .` → **83 項全過**(原 71 + 新 `tests/test_ui_api.py` 12 項;含 `LEGACY_SIM` 比對 2 項)。新測試涵蓋:權益曲線末點 = totalReturn、回撤最低 = maxDD、成本區塊 = `cost_kwargs`、`validation` 切分與 OOS 績效 = `/api/best_strategy` 的同一策略結果、分級門檻 19/20/49/50、分級與舊門檻是兩件事、改分級門檻不影響排名、額外區塊失敗不影響核心回應、`_downsample`。
- 瀏覽器(CDP,`tools/after.py`,桌面 1440×900 與 iPhone 390×844):7 張卡片全部載入;**卡片上的報酬/PF/回撤/年化 = API 回傳值(7 檔全部 0 差異)**;標的分析頁數字 = API(台股 2330.TW、美股 AAPL、加密 SOL-USD 各 1 個,0 差異;權益曲線末點 = 總報酬);主控台 0 錯誤。
- 市場分類:JS `getMarket` 與 Python `classify_market` 對 52 個代號 0 差異(`B1_after/market_parity_py.json`)。
- 功能回歸(瀏覽器內逐項):搜尋、加入(AAPL,美股標籤)、市場分頁篩選、展開/收合與圖表建立/釋放、指標開關、放大 K 線、股票列表抽屜、匯出、換時框重載、刪除、全部展開/收合,皆正常。
- 狀態:無效代號 → 「資料不足」;網路失敗 → 「連線失敗」;台股 4H → 「此時框不支援」(皆有畫面)。

## 台股/美股日內資料可靠度(實測,本機 yfinance)
| 標的/時框 | 結果 |
|---|---|
| 2330.TW 1H | 3634 根,首根 01:00 UTC=台北 09:00,可用 |
| 2330.TW 4H | **取不到任何完整區間(0 根)**→ 標為不支援 |
| AAPL 1H | 5077 根,首根 14:30 UTC=美東 09:30,可用 |
| AAPL 4H | 僅 722 根(3 年),合成切點為 UTC 0/4/8/…,與交易時段不對齊 → 標為不支援 |
| SOL-USD 1H / 4H | 正常(ccxt) |
原因:資料來源只有 1H,`resample_ohlcv` 只收「填滿」的 UTC 4 小時區間,股市交易時段填不滿。後端未改,僅前端標示;卡片/標的分析/排名流程遇到會直接顯示說明、不送 API。

## 互動式策略研究核心(原型,未整合)
`static/prototype/research-core.*`(Canvas 2D,自行設計,無 JEV 素材)。無頭 Edge、軟體算圖下的主執行緒忙碌率:基準 0.29%、待機(預設靜態)0.21%、選用裝飾旋轉 2.8%、執行中 6.7%、執行中 + CPU 4× 降速 14.0%、捲出畫面 0.22%、分頁隱藏 0.16%、reduced-motion 0.40%、手機簡化版 0.14%。整合時的掛鉤:階段由既有 fetch 生命週期與回應欄位驅動(`dataInfo`→資料、`metrics`→技術、`posState`→訊號、`validation`→驗證、`backtest.summary`→風險),**不新增 API 呼叫、不重跑回測**。是否整合待你決定。

## 已知限制 / 留到 B2 或之後
- 手機版只做了基本堆疊(卡片標題、排名表改卡片);iPhone 的觸控目標、字級、底部彈窗、PWA manifest/圖示留 B2。
- 「ⓘ」說明目前仍是滑鼠 hover(`data-tip`),觸控版 tap 顯示留 B2。
- 日內資料時間以 UTC 顯示,括號內為交易所當地時間;完整的「資料品質狀態機」、多週期、市場環境歷史表現尚未提供(畫面上已註明,不放假資料)。
- 自選清單仍存在瀏覽器 localStorage(各裝置獨立);同步功能延後。

## 截圖
- 改版前:`B1_before/`(桌面/手機 自選清單整頁、首屏、最佳策略彈窗)
- 改版後:`B1_after/`(桌面/手機:自選清單、首屏、展開卡片、標的分析 ×3 市場、市場環境、最佳策略彈窗;桌面另有最佳策略視圖、策略實驗室)
- 原型:`B1_prototype/`
