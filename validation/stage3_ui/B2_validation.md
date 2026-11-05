# 階段三 B2(iPhone 介面優化 + PWA)驗證紀錄

分支 `feature/research-platform-ui`,接在 B1(cec4a3c)之後。未 push / merge / 部署;未開放區網(測試伺服器只綁 127.0.0.1);未修改 `trading-bot/`、未動機器人行程;沒有使用任何付費 API。
**未修改**回測計算、策略公式、OOS 選擇邏輯;後端只做:移除 Render 專屬限制、新增 PWA 靜態路由、註解。

## 改了什麼
1. **清理過時的 Render 邏輯**:前端移除 `isRender`(深度分析不再被擋、`/api/config` 不再回 `isRender`、相關提示文字);後端移除 `deep_analysis` 的 403。`RENDER=true` 環境變數僅剩「略過啟動時的 ccxt 連線檢查」的用途(測試用)。README 改為本機 Windows 執行說明。
2. **OOS 分級前後端與文件一致**(<20 樣本不足 / 20–49 初步觀察 / ≥50 可進一步評估):`app.py` 常數、`05-ui-helpers.js`、`index.html` 說明、README、方案文件。新測試會比對 JS 與後端常數,不一致即失敗。
3. **iPhone Safari**(`static/css/mobile.css`、`static/js/70-mobile.js`):
   - 字體:一般文字 ≥13–14px,說明/日期 ≥12px(審計 0 個 <12px);輸入框與下拉 16px(避免 iOS 點擊後自動放大);`dvh`、safe-area。
   - 觸控:所有按鈕/連結/下拉/分頁最小 44×44px(審計 0 個不足);`touch-action: manipulation`;說明提示(ⓘ)改為**輕點顯示底部提示條**,按鈕類(指標開關)用**長按**顯示、不誤觸切換。
   - 底部導覽:58px + safe-area,圖示 22px、文字 12px;彈窗/抽屜開啟時鎖住背景捲動。
   - 卡片:標題列與動作鈕重排(分析鈕 2 欄、圖示鈕右上),KPI 2×2,展開區單欄。
   - K 線圖:手機圖較高(主圖 260/300)、副圖加高、點擊顯示資訊列;放大圖為全螢幕;垂直滑動可正常捲動頁面、水平滑動平移、雙指縮放。
   - 分析彈窗:改為接近全高的底部彈窗(把手、48px ✕、粘性關閉鈕);策略比較表在手機改成卡片(**資料與桌面表格同一份**)。
   - 市場環境表在手機改為卡片;控制列改 2 欄;資料來源標示移到頁尾(沒有因手機隱藏任何功能)。
4. **PWA**(沒有 Service Worker):`/manifest.webmanifest`(standalone、zh-TW、深色)、`apple-touch-icon`(180)、192/512/maskable 512 圖示(自繪,`tools/make_icons.py` 可重生)、favicon、iOS meta(status-bar `black`、title「順勢分析」)。

## 驗證
- 單元/整合測試:`python -X utf8 -m unittest discover -s tests -t .` → **91 項全過**(B1 的 83 + 本階段 8:manifest/圖示像素尺寸與無透明通道、HTML head 標籤、沒有 Service Worker、OOS 常數一致、舊門檻不被稱為可信度、Render 邏輯已移除且深度分析不再被擋)。
- 桌面回歸(`tools/after.py`):7 張卡片數字 = API(0 差異);標的分析頁台股/美股/加密數字 = API;主控台 0 錯誤。
- **真實觸控測試**(`tools/b2_mobile.py`,CDP `Input.dispatchTouchEvent`,iPhone 14 390×844、iPhone SE 375×667,`pointer:coarse`、`hover:none`):
  底部分頁切換 ✔、輕點 KPI 顯示提示/點別處關閉 ✔、展開卡片並建立 5 張圖 ✔、**圖上垂直滑動會捲動頁面**(scrollY 1527→1824)✔、**水平滑動平移**圖 ✔、**雙指縮放**(可視區間 484→232)✔、長按指標鈕只顯示提示不切換、輕點則切換 ✔、放大圖全螢幕且背景鎖定 ✔、股票列表抽屜開/關/跳到卡片 ✔、搜尋 ✔、最佳策略底部彈窗(793/844px 高,貼底)✔、彈窗「詳細」進入標的分析 ✔、美股/加密標的分析 ✔。SE 結果相同。
- **桌面/手機一致性**:最佳策略結果中,桌面表格 6 列的所有數字(樣本內/外/全期間的報酬、PF、筆數、回撤)都出現在手機卡片中,**0 差異**(同一份 DOM、同一份 API 資料,僅 CSS 切換顯示)。
- 審計(iPhone 14/SE,所有主要畫面):<44px 觸控目標 **0**;<12px 文字 **0**;<16px 輸入框 **0**;橫向溢出 **無**。
- PWA:manifest 200、`application/manifest+json`、圖示 200 `image/png`;`navigator.serviceWorker.getRegistrations()` = 0;`/sw.js` 404。
- 橫向(844×390):沿用桌面版型(頂部導覽),無橫向溢出。

## 測試工具的修正(影響先前截圖,已重拍)
`tools/shot.py` 原本只結束 Edge 的啟動程序,留下殘餘瀏覽器,後續測試重連到舊瀏覽器(沿用舊的 localStorage、快取失敗)。已改為依除錯埠結束所有相關 msedge,並重拍 `B1_after/` 的桌面截圖。B1 的數字對照結果不受影響(每次都直接向 API 取值)。

## 已知限制
- 沒有在真實 iPhone 上測試(只有 CDP 的觸控與 iPhone UA/尺寸模擬);iOS 專屬行為(橡皮筋捲動、動態工具列、主畫面 PWA 的狀態列)需實機確認。
- 手機上網站仍只在本機 Windows 執行;iPhone 要連線需要另行設計的安全連線(區網/Tailscale,尚未做,依你的指示不開放)。
- 全頁截圖中固定的底部分頁列會出現在頁面中間(截圖工具的特性,不是版面問題)。

## 截圖
`B2_after/`:`b2_iphone14_*`(首屏、整頁、提示條、展開卡片 K 線、放大圖、抽屜、搜尋、分析底部彈窗、標的分析 ×3 市場、市場環境、實驗室、最佳策略)、`b2_se_*`、`b2_landscape_*`;`b2_report_*.json` 為完整測試與審計數據。
