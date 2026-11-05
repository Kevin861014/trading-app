# Research Core 正式整合 — 驗證紀錄

測試環境:這台 Windows 電腦、獨立測試埠 5055(完成後關閉)、無頭 Edge(CDP)。真實資料(Binance 公開行情 / Yahoo),不使用任何付費服務。設計與證據對照見 `docs/research_core_events.md`。

## 1. 整合前 → 整合後
| | 整合前(99fd0e0) | 整合後 |
|---|---|---|
| 進度條 | 依時間推算:第 4 秒「8%」、第 12 秒「22%」,文字寫「約需 60~120 秒」(實際 21 秒就完成) | 「策略回測 83 / 166」+ 該階段真實比例;不知道比例時顯示「處理中」 |
| 取消 | 沒有 | 進度列「取消」;關閉彈窗/分頁也會取消;後端真的停止 |
| 實驗室 | 只有進度條 + 結果表 | 球形網絡(真實事件光點)+ 進度列 + 點節點看該階段實際結果 + 結果表 |
| 截圖 | `before_desktop_lab_running_t4s/t12s.png`、`before_desktop_lab_done.png`、`before_mobile_*` | `live_*.png`、`phone_*.png`、`modal_*`、`best_view_*`、`live_deep_run.gif` |

## 2. 截圖與 GIF(本資料夾)
- 桌面實驗室:`live_00_standby.png`(待機靜態)、`live_01_backtest_early.png`、`live_02_backtest_mid.png`、`live_04_done.png`;`live_node_data/backtest/validation/indicators.png`(點節點的詳情);`live_deep_run.gif`(真實 1H 深度分析,約 21 秒,取樣縮短)。
- 取消:`cancel_01_running.png` → `cancel_02_cancelled.png`。
- 彈窗與最佳策略頁(只有進度列、沒有球體):`modal_desktop_*`、`modal_mobile_*`、`best_view_desktop_*`、`best_view_mobile_*`。
- iPhone 尺寸(390×844、DPR 2、iPhone UA、觸控事件):`phone_01_lab_idle.png`、`phone_02_lab_running.png`、`phone_03_node_tapped.png`、`phone_04_cancelled.png`。
- 回歸:`regression/`(B2 iPhone 報告 `b2_report_iphone14.json`、桌面 `desktop_*`)。

## 3. 真實分析的事件一致性(`report_live_deep_desktop.json`,SOL-USD 1H 深度分析)
- 183 個事件;其中策略回測 166 筆 progress(= 測試策略數)、樣本外驗證 8 筆 progress(= 入選數 8)、行情資料 2、其餘三個階段各 1 筆 `skip`(排名流程不含)。
- 事件**逐步**到達:約 21 秒內分 54 次增量(不是結束時一次到齊);取樣時間軸 25%/50%/75% 處累計事件數為 51 / 112 / 164。
- 畫面的 `i / n`、各階段耗時、筆數 = 事件欄位;點節點看到的入選表、樣本外表、分級 = API 回應(`labState.data`)。
- **有 job 的結果 = 沒有 job 的同一請求結果**:真實資料逐欄比對,`sameResults=true`、`sameTested=true`(另有合成資料的自動化測試)。
- 輪詢成本:一次分析 55 次 `job_events`、合計約 49 KB;沒有任何額外的分析或下載請求。
- 畫面上沒有任何「分析中… NN%」「約需 N 秒」文字(`percentTextSeen=false`、`hasPercentText=false`)。

## 4. 取消(真實)
- 實驗室:回測進行到第 10/166 時按取消 → 前端狀態「已取消」、回測階段標為「已中止」、動畫迴圈已停(`loopOn=false`)、取消鈕隱藏、結果區顯示「已取消分析」;後端工作狀態 `cancelled`,事件序號在取消後 4 秒內**不再增加**(`serverStoppedGrowing=true`)。
- 彈窗:執行中關閉彈窗 → 後端 `cancelled`,事件序號不再增加。
- 自動化測試另外證明:取消後沒有再跑任何策略、沒有進入樣本外驗證、回傳 499 `cancelled`、無半套結果、對未知/已完成/非法 id 安全。

## 5. 手機(iPhone 尺寸,`report_phone_mobile.json`)
- 球體為靜態(`static=true`、`loopOn=false`),待機與分析中皆然;節點為 3×2 按鈕格(每格 106×70 px),取消鈕 68×44 px;最小字級 12 px;沒有橫向溢出;`smallFontEls=[]`。
- 觸控:點節點 → 顯示該階段詳情;點取消 → 取消成功。
- B2 回歸:`regression/b2_report_iphone14.json` 與先前 `B2_after/b2_report_iphone14.json` 逐項比對,152 個欄位中只有 3 項不同(彈窗新增進度列的文字節點數 +14、一次捲動位置差 4 px),觸控/字級/尺寸稽核全部相同。
- 桌面回歸:卡片與標的分析頁數字對 API 0 差異;主控台 0 錯誤。

## 6. 資源(`resources_report.json`;細節與解讀見設計文件 §5)
真實 GPU、2–3 次重複取中位數:待機(預設)≈0;分析中(動畫開)CPU 約 15% 單核、GPU 0.27%;動畫關 3.8%;reduced-motion 4.0%;完成後 0.8%;手機分析中 5.0%;對照整合前原型待機 6.5% → 現在 ≈0。
過程中發現並修正一個實質問題:進度列的 `width` CSS transition 每個影格都會觸發排版,讓分析期間 CPU/GPU 多出一倍以上(診斷:`tools/rc_cpu_breakdown.py`),已改為事件驅動的離散更新。

## 7. 安全與範圍
- `trading-bot/` 與機器人程序未動(PID 13436、16836 仍在執行);沒有付費 API;沒有開放 LAN(測試伺服器只綁 127.0.0.1:5055,完成後關閉);沒有 push / merge / 部署。
- 沒有修改策略公式、回測、OOS 選擇、交易成本計算;`rank_strategies` 只多了不影響結果的取消檢查點與事件記錄。

## 8. 未驗證
- 真實 iPhone 實機(Safari)。
- 非 Edge 的瀏覽器。
