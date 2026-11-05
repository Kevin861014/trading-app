# 第二階段(IS/OOS 隔離)驗證資料

- `DESIGN.md`:修正設計。
- `oos_compare.py`:用同一份快取真實資料,分別跑「第一階段版本(commit 32b7c26)」與「本階段版本」的 `/api/best_strategy`、`/api/deep_analysis`。
  路徑指向當時的暫存資料夾,重跑前請改路徑;K 線快取未放入版本庫。
- `oos_old.json` / `oos_new.json`:原始輸出。

## 結果摘要(前 8 名的「樣本外」標示;舊版的「OOS」其實含在排名資料內)
| 執行 | 舊版 | 新版(IS 排名、OOS 獨立) |
|---|---|---|
| best BTC/USDT 4H | 通過 3 / 未過 5 | 通過 1 / 未過 7 |
| best SOL/USDT 4H | 通過 6 / 未過 2 | 通過 4 / 未過 4 |
| best 2330.TW 日 | **通過 8 / 未過 0** | 通過 2 / 未過 3 / **證據不足 1**(只入選 6 個) |
| best AAPL 日 | 通過 8 / 未過 0 | 通過 5 / 證據不足 3 |
| best NVDA 日 | 通過 3 / 未過 1 | 通過 0 / **證據不足 2** |
| deep BTC/USDT 4H | **沒有 OOS**(加密路徑整段 2 年評估) | 通過 2 / 未過 6 |
| deep 2330.TW 日 | 用 OOS 當門檻剔除再排序 | 通過 5 / 證據不足 3 |

新版「通過」的門檻只是「OOS 筆數 ≥5 且 PF>1」,是低門檻;例如 deep 2330.TW 第 1 名 ichimoku 的 OOS 只有 5 筆、PF 1.06 就算通過。
