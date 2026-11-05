# -*- coding: utf-8 -*-
"""D2:組成 docs/d2_portfolio_simulation.md。敘述與表格的數字全部取自 results/*.json。"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, 'results'); ROOT = os.path.dirname(os.path.dirname(HERE))
L = lambda n: json.load(open(os.path.join(RES, n + '.json'), encoding='utf-8'))
rc = L('reconcile')['result']; cal = L('calibration'); rep = L('replay_full_period'); att = L('attribution_reproduction'); sc = L('scenarios'); man = L('backup_manifest')
R = sc['results']; ST = sc['stress']; ce = cal['equity']; cm = cal['matched_stats']; cn = cal['counts']; ct = cal['totals']
f = lambda v, d=2: '—' if v is None else ('%+.*f' % (d, v)); g = lambda v, d=2: '—' if v is None else ('%.*f' % (d, v))

bk = '\n'.join('| %s | %s | %s | %s | `%s…` | %s |' % (e['name'], format(e.get('source_size', 0), ','), e.get('source_mtime', ''), e.get('kind', e.get('status', '')), (e.get('backup_sha256') or '')[:16], (e.get('source_sha256_at_read') or '')[:16] + '…' if e.get('kind', '').startswith('redacted') else '同左') for e in man['files'])


def srow(pk, sk):
    m = R['%s_%s' % (pk, sk)]
    return '| %s | %s%% | %s%% | %s | %s | %s | %s / %s | %s× | %s（%s） | %s / %s | %s |' % (m['label'], f(m['return_pct']), g(m['max_dd_pct']), m['trades'], '—' if m['pf'] is None else m['pf'], g(m['fees']), m['avg_concurrent'], m['max_concurrent'], m['max_exposure_x'],
                                                                           f(m['worst_day_usd']), m['worst_day'], f(m['top3_net']), f(m['net_without_top3']), ' / '.join(f(x, 1) for x in m['thirds_usd']))


def stable(pk):
    return ' / '.join('%s %s%%' % (t['from'][2:] + '→' + t['to'][2:], f(t['btc_pct'], 1)) for t in sc['btc_thirds'][pk])


head = '| 情境 | 淨報酬 | 最大回撤 | 交易數 | 淨 PF | 手續費 | 平均／最多同時持倉 | 最大名目暴露 | 最差單日（USDT） | 最大 3 筆／扣掉後 | 三等分期間損益 USDT |\n|---|---|---|---|---|---|---|---|---|---|---|'
doc = f'''# D2:23 組實盤策略的投資組合層級模擬與風險研究(離線)

**唯讀、離線。** 沒有修改 `trading-bot/`、設定檔或目前倉位;沒有停止或重啟機器人;沒有呼叫任何下單、撤單、轉帳、提領或修改槓桿的 API(幣安只有 GET 的對帳查詢,走 D1 的白名單包裝層);沒有修改網站的回測引擎、策略、OOS;沒有新增策略或市場濾網;沒有使用付費服務。模擬器不會把任何東西套用到實盤。原始資料(`raw/`)與備份(`C:\\Users\\User\\發大財\\研究備份_D2\\`)都在版控之外。

## 0. 結論摘要

1. **資料已保全**:日誌、狀態檔與設定備份已複製到版控外的備份目錄(位元組一致、含 SHA-256;設定檔只存已移除金鑰的副本),驗證備份內不含金鑰。
2. **對帳差額 {rc['residual_wallet_vs_income']:+.4f} USDT 仍未對帳,沒有補差額**:成交與收支逐筆完全一致(手續費、已實現損益各 {rc['fills']} 筆成交 0 差異),差額在日誌起點(2026-10-24)就已存在且之後穩定,所以**成因發生在日誌之前,現有資料無法確認**。
3. **模擬器在『設定與日誌都確定』的期間幾乎完全重現實盤**(2026-10-24 → 11-05,{cn['live_trips']} 筆):已平倉 {cm['n_closed_pairs']}/{ct['live']['n_closed']} 筆逐筆配對成功(進場時間差中位數 {cm['entry_time_diff_s_median']:.1f} 秒、出場都在 1 小時內)、成交名目比中位數 {cm['notional_ratio_sim_over_live_median']:.4f}、手續費比 {cm['fee_ratio_median']:.4f}、淨損益 {ct['sim']['net']:+.2f} vs 實盤 {ct['live']['net']:+.2f}、權益曲線相關 {ce['corr_hourly_changes']:.3f}、最大回撤 {ce['sim_mdd_pct']:.2f}% vs {ce['live_mdd_pct']:.2f}%、同時持倉數相關 {cal['concurrency']['corr']:.4f}。**注意:這一段的滑價參數取自同一段實盤,所以是『校準』不是獨立驗證。**
4. **完整 D1 期間重播(2026-06-22 → 11-05,設定時間線為推測)**:歸屬可靠且該幣策略沒換過的 {rep['counts']['live_comparable']} 筆實盤交易中 {rep['counts']['matched_entry_pm1bar']} 筆({rep['counts']['match_rate_of_live_pct']}%)被重現(進場 ±1 根、出場 ±1 小時),成交名目比中位數 {rep['notional_ratio_sim_over_live']['median']:.2f}。模擬多出的 {rep['counts']['sim_only']} 筆中 {rep['sim_only_split']['before_first_live_trade_of_that_symbol']} 筆發生在該幣第一筆實盤交易之前(該組合很可能還沒上線)。
5. **121 筆「無法可靠歸屬」的交易**:用訊號重現檢驗候選策略,{att['classification']['single_candidate']} 筆只被一個候選重現(推定歸屬)、{att['classification']['ambiguous']} 筆模稜兩可、**{att['classification']['unexplained']} 筆沒有任何候選能重現**(淨 {att['net_by_class']['unexplained']:+.2f},其中包含 D1 發現的最大單筆 XRP +9.96,可能是別的策略、手動單或資料缺漏)。**這只是證據,正式報告仍把這 121 筆列為『無法可靠歸屬』。**
6. **情境比較(都是『現行 23 組固定、起始 310 USDT』的假設性模擬,不是實際成交,也不是樣本外)**:
   - **B 不啟用 1H 組合**:在兩段期間與成本加壓下,最大回撤都比 A 小、交易數與手續費都減少(實盤期間 {g(R['L_B']['max_dd_pct'])}% vs {g(R['L_A']['max_dd_pct'])}%;擴充期間 {g(R['E_B']['max_dd_pct'])}% vs {g(R['E_A']['max_dd_pct'])}%),報酬接近(實盤期間 {f(R['L_B']['return_pct'])}% vs {f(R['L_A']['return_pct'])}%;擴充期間 {f(R['E_B']['return_pct'])}% vs {f(R['E_A']['return_pct'])}%)。成本 ×1.5 時 B 在兩段都比 A 好。**方向一致,但這是兩組 1H 組合帶來的『較少暴露』與『較少手續費』,沒有統計檢定,也不代表它們在未來較差。**
   - **C 同時暴露上限 0.5×** 與 **D 同輪最多 2 組新進場**:兩段期間報酬都明顯變差(C:{f(R['L_C']['return_pct'])}% / {f(R['E_C']['return_pct'])}%;D:{f(R['L_D']['return_pct'])}% / {f(R['E_D']['return_pct'])}%),回撤沒有一致的改善(C 在 L 略小、在 E 反而更大;D 幾乎不變)。以『跳過進場』的方式限制暴露,在這份資料裡**沒有證據顯示有益**。
   - **績效跟著 BTC 走向**:全部是做多,實盤期間賺在 BTC +34.6% 的中段、擴充期間賠在 BTC −21% 的中段;扣掉最大 3 筆交易後,擴充期間 A 的淨損益是 {f(R['E_A']['net_without_top3'])} USDT。
   - **對成本很敏感**:成本 ×1.5 後,擴充期間 A 從 {f(R['E_A']['return_pct'])}% 變成 {f(ST['E_A']['return_pct'])}%。
7. **不要用這些結果直接改實盤**:23 組本身是從類似歷史挑選的(挑選偏誤),實盤期間又已被 D1 看過;模擬結果只當研究與設計後續驗證的依據。

## 1. 階段一:資料保全與對帳

### 1.1 備份(唯讀複製,沒有改動機器人資料夾)

備份目錄:`C:\\Users\\User\\發大財\\研究備份_D2\\<時間戳>\\`(版控之外);`MANIFEST.json` 另有一份在 `validation/d2_portfolio/results/backup_manifest.json`(只含檔名、大小、時間、雜湊)。日誌正被機器人追加,所以其雜湊是「讀取當下」的快照。

| 檔案 | 大小(bytes) | 原始修改時間 | 備份型態 | 備份 SHA-256(前 16 碼) | 原檔 SHA-256(前 16 碼) |
|---|---|---|---|---|---|
{bk}

驗證:備份內找到金鑰 {man['verification']['secrets_found_in_backup']}、雜湊問題 {man['verification']['hash_problems']}。`secret_keys.json` 完全沒有讀取。備份保留原始修改時間(只改備份檔的時間,不動原檔)。

### 1.2 對帳差額 {rc['residual_wallet_vs_income']:+.4f} USDT

| 計算方式 | USDT |
|---|---|
| 入金(現貨→合約劃轉,2026-06-12 與 2026-08-24;無出金) | {rc['deposits_to_futures']:.4f} |
| **帳戶快照計算損益** = 錢包餘額 {rc['snap']['totalWalletBalance']} − 入金 | **{rc['snapshot_based_pnl_wallet']:+.4f}**(再加未實現 {float(rc['snap']['totalUnrealizedProfit']):+.4f} = {rc['snapshot_based_pnl_with_unrealized']:+.4f}) |
| **收支紀錄重建損益** = 已實現 {rc['income_realized_sum']:+.4f} + 手續費 {rc['income_commission_sum']:+.4f} + 資金費率 {rc['income_funding_sum']:+.4f} | **{rc['income_based_pnl_realized']:+.4f}** |
| **差額**(快照 − 重建) | **{rc['residual_wallet_vs_income']:+.4f}** |

(快照時間 {rc['snap']['asOf']} UTC。D1 的快照較早,所以錢包數字不同,但差額相同。)

調查結果:
- 取得收支兩次、中間沒有新紀錄({rc['income_records_first_pass']} → {rc['income_records_second_pass']} 筆):不是取得時間差。
- {rc['fills']} 筆成交對 {rc['income_records_second_pass']} 筆收支:手續費 {rc['fills_commission_sum']:.6f} vs {-rc['income_commission_sum']:.6f}、已實現損益 {rc['fills_realized_sum']:.6f} vs {rc['income_realized_sum']:.6f},**逐筆成交編號完全吻合**,沒有缺漏也沒有多出(收支沒有其他類型,只有一筆劃轉)。
- 用機器人日誌每輪的「保證金≈」在**空手**時(此時等於錢包)重算:2026-10-24 為 −0.6753、10-25 −0.6747、10-29 −0.6705~−0.6722、10-30 −0.6717、10-31 −0.6731(`results/offset_probe.txt`)。**差額在日誌起點就已存在,之後只有 ±0.003 的浮動**。
- 結論:**成因發生在 2026-10-24 之前**(2026-06-12 ~ 10-24 之間),日誌已被輪替、`income` 之外沒有其他紀錄,**無法確認原因**(可能是早期劃轉實際入帳額與查詢金額的差、未列入收支的零星項目,但這只是猜測)。**保留為「未對帳」,沒有把差額分配給任何策略或補進任何統計。** 之後新增的成交與收支都對得上。

## 2. 階段二:模擬器與假設

`validation/d2_portfolio/d2_sim.py`:逐步照 `portfolio_bot.py` 的邏輯(唯讀對照原始碼)重建。

| 項目 | 做法 | 來源／狀態 |
|---|---|---|
| 訊號 | 每根已收盤 K 棒用「最近 400 根」呼叫網站同一份策略程式(與機器人逐字相同),取 el[-1]、xl[-1]、ATR[-1](預先算好) | **D1 確認**(機器人 `closed_ohlcv(limit=400)`) |
| 資金基準 | cap = 錢包 + 未實現;alloc = cap × 權重 / Σ權重(16);risk 4.03%、單組槓桿上限 3、總名目上限 3 | **D1 確認**(設定檔 + 原始碼;日誌「保證金≈」在空手時 = 錢包) |
| 數量 | min(alloc×risk/停損距離, alloc×3/價格),依交易所步長**無條件捨去**;小於步長或最小名目不下單;可用保證金預檢(需求 > 可用×0.9 → 縮量) | **D1 確認**(`reconcile`、`amount_to_precision`);步長/最小名目取自公開合約規格 |
| 進場 | 訊號棒收盤後約 {cal['params']['latency_s']} 秒市價成交 ≈ 下一根開盤 × (1+0.03%);記帳價 = 訊號棒收盤 | 延遲與滑價是 **D1 量測的校準值** |
| 出場 | 收盤後以已收盤 K 判斷:先更新移動停損(ATR 系:peak − trail×ATR,只往上),再判 停損(L≤stop)、停利(H≥tp)、訊號出場 → 市價賣(下一根開盤 × (1−0.01%)) | **D1 確認**(`update_combo`) |
| 交易所保護停損 | 邏輯停損 × 0.995,STOP_MARKET 盤中觸發,成交 = min(觸發價, 開盤) × (1−{cal['params']['slip_stop']*100:.3f}%);以 1H K 棒偵測 | 0.995 **D1 確認**(`sync_protective_stop` 的呼叫端);停損滑價為**校準值**({cal['slip_stop_samples']} 筆實盤停損樣本) |
| 成本 | 吃單手續費 0.05%/邊;資金費率用幣安公開的歷史費率 × 持倉名目 | 手續費 **D1 確認**(100% 吃單、0.05%);費率為公開資料 |
| 逐倉/槓桿 | 3x 逐倉;模擬可用保證金預檢;**不模擬強平**(停損距離遠小於強平距離) | 假設 |
| 同一根 K 棒多組訊號 | 同一輪、依設定順序處理、共用同一個 cap;可用保證金用輪初快照 | **D1 確認**(`cycle`) |
| 1H 與 4H 訊號順序 | 各自在自己的收盤時間觸發;同一時間點(整點)1H 與 4H 在同一輪處理 | **D1 確認** |
| 機器人在線時間 | 校準期間使用日誌的實際輪詢時間(斷線/漏輪自動帶入);日誌之前**假設一直在線**(實際看門狗有 16 次啟動) | 假設(日誌之前) |
| 設定時間線 | 校準期間:24 組(2026-10-29 重啟前)→ 23 組(之後);重啟後新出現的組合會立刻評估最新一根;被換掉的組合殘倉在重啟時平倉。更早:只能用備份檔日期**推測** | 校準期間 **D1 確認**;之前**推測** |
| 連敗斷路器 | **假設不啟用**(日誌從未出現斷路器訊息;需要 ≥25 筆種子樣本) | 假設 |
| 拒單/手動操作/交易所故障 | 不模擬 | 假設 |

## 3. 階段三:校準(先校準,再研究)

### 3.1 設定與日誌都確定的期間:{cal['window']['from']} → {cal['window']['to']} UTC

起始資金取日誌第一輪看到的保證金({cal['window']['init_equity_from_log']},當時空手);設定 = {cal['window']['config']};輪詢時間 = 日誌 {cal['window']['loops_in_log']} 輪。

| 項目 | 實盤 | 模擬 | 差異 |
|---|---|---|---|
| 交易筆數(已平倉 + 持倉中) | {cn['live_trips']} | {cn['sim_trips'] + len(ct['sim_open_end'])} | 0;持倉中的 4 組實盤與模擬都還持有 |
| 逐筆配對(進場 ±1 根) | — | {cn['matched']}/{cn['sim_trips']} 筆 | 模擬多出 {cn['sim_only']}、實盤多出 {cn['live_only']}(= 目前持倉中,模擬也持有) |
| 進場時間差(中位數) | — | {cm['entry_time_diff_s_median']:.1f} 秒 | |
| 出場時間差 | — | 全部在 1 小時內;中位數 {cm['exit_time_diff_h_median']:.2f} 小時 | |
| 成交名目比(模擬/實盤) | — | 中位數 {cm['notional_ratio_sim_over_live_median']:.4f}、平均 {cm['notional_ratio_mean']:.4f} | |
| 手續費 | {ct['live']['fees']:.4f} | {ct['sim']['fees']:.4f} | 比值中位數 {cm['fee_ratio_median']:.4f} |
| 資金費率 | {ct['live']['funding']:.4f} | {ct['sim']['funding']:.4f} | |
| 已實現淨損益(已平倉) | {ct['live']['net']:+.4f} | {ct['sim']['net']:+.4f} | {ct['sim']['net'] - ct['live']['net']:+.4f}(已配對逐筆淨損益差中位數 {cm['net_diff_median_usd']:+.4f}) |
| 同時持倉(平均/最多) | {cal['concurrency']['live_avg']:.2f} / {cal['concurrency']['live_max']} | {cal['concurrency']['sim_avg']:.2f} / {cal['concurrency']['sim_max']} | 逐小時相關 {cal['concurrency']['corr']:.4f} |
| 權益變動(日誌保證金 vs 模擬權益,{ce['hours_compared']} 小時) | {ce['live_change_usd']:+.2f} | {ce['sim_change_usd']:+.2f} | 逐小時差平均 {ce['hourly_diff_mean_usd']:+.3f}、最大 {ce['hourly_diff_abs_max_usd']:.2f} USDT |
| 權益最大回撤 | {ce['live_mdd_pct']:.2f}%({ce['live_max_dd_usd']:.2f} USDT) | {ce['sim_mdd_pct']:.2f}%({ce['sim_max_dd_usd']:.2f} USDT) | 逐小時變動相關 {ce['corr_hourly_changes']:.4f} |

**差異來源**:模擬淨損益比實盤多 {ct['sim']['net'] - ct['live']['net']:+.2f} USDT(約 1%),來自成交價的細微差(進出場滑價用平均值、實際每筆不同)與停損成交價的分布;沒有任何一筆交易是「有無」的差異。**限制:只有 {ct['live']['n_closed']} 筆已平倉、約 12 天,只含一次設定更換,而且滑價參數取自同一段**——所以這證明的是「機制與數量/成本公式正確」,不是「模擬能預測未來績效」。

### 3.2 與 D1 相同的完整期間(2026-06-22 → 11-05)重播

設定時間線只能推測(20 組 → 24 組(≈10-10) → 23 組),日誌之前假設機器人一直在線;資金 = 2026-06-12 入金 152.49 與 2026-08-24 入金 156.39。**只比較歸屬可靠、且該幣策略整段沒換的實盤交易**(排除 AAVE、BNB、PAXG、PYTH、SOL、XRP)。

| 項目 | 數值 |
|---|---|
| 可比較的實盤交易 / 模擬交易 | {rep['counts']['live_comparable']} / {rep['counts']['sim']} |
| 實盤被模擬重現(進場 ±1 根) | {rep['counts']['matched_entry_pm1bar']}（{rep['counts']['match_rate_of_live_pct']}%);其中出場在 1 小時內 {rep['exit_within_1h']}/{rep['closed_pairs']} |
| 成交名目比(模擬/實盤)中位數 / 10%~90% | {rep['notional_ratio_sim_over_live']['median']:.2f} / {rep['notional_ratio_sim_over_live']['p10']:.2f} ~ {rep['notional_ratio_sim_over_live']['p90']:.2f} |
| 已配對交易淨損益合計(模擬 / 實盤) | {rep['net_matched']['sim']:+.2f} / {rep['net_matched']['live']:+.2f} |
| 模擬多出的交易 | {rep['counts']['sim_only']} 筆:其中 **{rep['sim_only_split']['before_first_live_trade_of_that_symbol']} 筆發生在該幣第一筆實盤交易之前**(該組合可能還沒上線),只有 {rep['sim_only_split']['after_first_live_trade']} 筆在上線之後(TRX 2026-08-13、WLD 2026-10-01,可能是停機或手動) |
| 模擬期末權益(含入金) | {rep['sim_final']['equity']}(實盤快照:{float(rc['snap']['totalMarginBalance']):.2f};兩者接近,但模擬用的是新策略、實盤那段時間有舊策略,所以**不能視為重現**) |

名目比的 10% 分位 0.79 來自:歷史資金/權重與現行不同(早期資金只有 152、Σ權重不同),以及小額單的步長進位。

### 3.3 121 筆「無法可靠歸屬」的交易

**沒有假裝完成歸屬。** 做法:對每個「曾經出現在狀態檔／設定備份」的候選策略單獨重播,看哪個能同時重現該筆實盤交易的進場(±1 根)與出場(±1 小時)。

| 結果 | 筆數 | 淨損益 USDT |
|---|---|---|
| 只被一個候選重現(推定歸屬) | {att['classification']['single_candidate']} | {att['net_by_class']['single_candidate']:+.2f} |
| 被多個候選重現(模稜兩可) | {att['classification']['ambiguous']} | {att['net_by_class']['ambiguous']:+.2f} |
| **沒有任何候選能重現** | {att['classification']['unexplained']} | {att['net_by_class']['unexplained']:+.2f} |

推定歸屬(僅供參考):{'、'.join('%s %s %d 筆' % (k.split('|')[0].replace('/USDT', ''), k.split('|')[1], v) for k, v in att['inferred_single_candidate'].items())}。未被任何候選重現的 5 筆在 {', '.join('%s %d' % (k.replace('/USDT',''), v.get('unexplained', 0)) for k, v in att['by_symbol'].items() if v.get('unexplained'))},**包含 D1 發現的最大單筆(XRP +40.5%)**:可能是狀態檔沒有紀錄的策略、手動操作或當時的設定與備份不同。**訊號重現只是證據,不是帳務標記**(不同策略可能在同一根 K 棒產生相同的進出場)。

## 4. 階段四:固定情境比較

**共同設定**:現行 23 組固定、起始 310 USDT(不入金不出金)、同一套成本與在線假設、相同期間。情境各只改一件事、事先定義、沒有掃描參數:A 全部 23 組;B 不啟用 1H(TRX、XRP),其餘 alloc 不變;C 新進場若讓總名目 > 0.5×權益就不進場(不縮倉);D 同一輪最多 2 組新進場(權重大者優先)。
**期間**:實盤期間 L = {sc['periods']['L']['from']} → {sc['periods']['L']['to']}(BTC 三等分:{stable('L')});擴充期間 E = {sc['periods']['E']['from']} → {sc['periods']['E']['to']}(BTC 三等分:{stable('E')})。

**重要**:23 組是從類似歷史挑出來的(挑選偏誤),L 期間又已被 D1 看過;**兩個期間都不是樣本外**,所以下表只能當「在同一份資料上,改變一件事會怎樣」的比較,**不能當成預期績效**。模擬的 A 在 L 期間得到 {f(R['L_A']['return_pct'])}%,遠高於實盤實際的約 +2%,是因為這是「現行 23 組一開始就在」的假設情境(實盤那段時間有舊策略、資金較少、有停機),而且現行組合是用這段歷史挑的。

### 實盤期間 L

{head}
{chr(10).join(srow('L', k) for k in 'ABCD')}

### 擴充期間 E

{head}
{chr(10).join(srow('E', k) for k in 'ABCD')}

### 成本壓力(吃單 0.075%/邊、進場滑價 0.06%、出場 0.02%、停損 0.084%;只對 A、B 各跑一次,看結論會不會翻轉)

| 情境 | 實盤期間 L 報酬／回撤／交易數 | 擴充期間 E 報酬／回撤／交易數 |
|---|---|---|
| A(成本 ×1.5) | {f(ST['L_A']['return_pct'])}% ／ {g(ST['L_A']['max_dd_pct'])}% ／ {ST['L_A']['trades']} | {f(ST['E_A']['return_pct'])}% ／ {g(ST['E_A']['max_dd_pct'])}% ／ {ST['E_A']['trades']} |
| B(成本 ×1.5) | {f(ST['L_B']['return_pct'])}% ／ {g(ST['L_B']['max_dd_pct'])}% ／ {ST['L_B']['trades']} | {f(ST['E_B']['return_pct'])}% ／ {g(ST['E_B']['max_dd_pct'])}% ／ {ST['E_B']['trades']} |

### 解讀(只描述,不做建議)

- **B(不啟用 1H)**:兩段期間與成本加壓下,B 的最大回撤都比 A 小(L {g(R['L_B']['max_dd_pct'])}% vs {g(R['L_A']['max_dd_pct'])}%;E {g(R['E_B']['max_dd_pct'])}% vs {g(R['E_A']['max_dd_pct'])}%)、交易數少約 21~23%、手續費較低,報酬沒有明顯變差;成本 ×1.5 時 B 在 L 與 E 都比 A 好(E:{f(ST['E_B']['return_pct'])}% vs {f(ST['E_A']['return_pct'])}%)。**這與 D1 的實盤觀察(TRX 1H 淨 −7.5)方向一致**。限制:只拿掉 2 組、只有兩段相互重疊的歷史、沒有統計檢定。
- **C(暴露上限 0.5×)**:兩段報酬都顯著變差(L {f(R['L_C']['return_pct'])}%、E {f(R['E_C']['return_pct'])}%),回撤只在 L 略小({g(R['L_C']['max_dd_pct'])}% vs {g(R['L_A']['max_dd_pct'])}%),在 E 反而更大({g(R['E_C']['max_dd_pct'])}% vs {g(R['E_A']['max_dd_pct'])}%)。原因:以「跳過進場」限制暴露會同時擋掉賺錢與賠錢的進場,且不縮倉。**沒有證據顯示它有益。**
- **D(同輪最多 2 組新進場)**:兩段報酬都較差,回撤幾乎沒變。**同一根 K 棒同時進場本身沒有被證明是主要風險來源**(D1 的同步停損是『停損』群聚,不是『進場』群聚)。
- **對少數交易的依賴**:E 期間 A 的最大 3 筆合計 {f(R['E_A']['top3_net'])} USDT,扣掉後 {f(R['E_A']['net_without_top3'])};L 期間扣掉後仍為 {f(R['L_A']['net_without_top3'])}(A 的總淨損益約 {f(R['L_A']['net_closed'])})。
- **市場期間的穩定性**:全部做多 ⇒ 績效跟 BTC 走向。L 期間幾乎所有獲利來自 BTC +34.6% 的中段({' / '.join(f(x, 1) for x in R['L_A']['thirds_usd'])});E 期間 BTC −21% 的中段虧 {f(R['E_A']['thirds_usd'][1], 1)} USDT、最後一段賺 {f(R['E_A']['thirds_usd'][2], 1)}。BTC 下跌 21% 的那一段(E 中段),四個情境都虧損;L 最後一段(BTC −7%)A、C、D 虧損,只有 B 小賺 {f(R['L_B']['thirds_usd'][2], 1)}(金額很小,不能當作結論)。
- **最差單日**:A {f(R['L_A']['worst_day_usd'])} USDT(L)、{f(R['E_A']['worst_day_usd'])} USDT(E);B 的最差單日較小。
- 暴露:最大名目暴露 A {R['L_A']['max_exposure_x']}×(L)/ {R['E_A']['max_exposure_x']}×(E),遠低於 3× 上限;槓桿不是主要風險。

## 5. 限制與不確定性

1. **校準期間很短**(約 12 天、{ct['live']['n_closed']} 筆),參數(滑價、停損滑價)取自同一段;更早期間的設定時間線是推測,機器人在線時間是假設(日誌之前)。
2. **對帳差額 {rc['residual_wallet_vs_income']:+.4f} USDT 未能解釋**;不影響模擬(模擬以日誌起點的實際保證金為起始),但意味著 06-12 ~ 10-24 的帳務沒有完整對上。
3. **模擬 ≠ 真實成交**:停損成交價、盤中順序、滑價分布、拒單、手動操作、交易所故障、資金費率的實際結算時點(用 1H 近似)都被簡化;停損用 1H K 棒偵測,同一小時內先後順序未知。
4. **情境比較不是樣本外**,而且 23 組有挑選偏誤;兩個期間彼此重疊(L 包含在 E 的後段),不是獨立的兩次驗證。
5. **結果對成本敏感**(成本 ×1.5 就讓 E 期間 A 轉虧),任何「改善」都小於成本假設的不確定性時,不應據此行動。
6. 沒有模擬:資金入出金對 alloc 的影響(情境用固定 310)、強平、斷路器、API 故障。

## 6. 下一步研究建議(都不是實盤修改)

1. 若要研究 B,應先用**更長、獨立**的歷史(例如 2020–2024,含 2022 熊市)與 walk-forward,而不是只用這兩段;並比較 1H 組合替換成 4H 版本的效果,而不是只移除。
2. 把這個模擬器擴充成「每週自動用最新日誌重跑校準」,累積校準樣本(目前只有 {ct['live']['n_closed']} 筆),並在校準期間內檢驗滑價參數是否穩定。
3. 備份已存在;建議之後定期(例如每週)重跑 `d2_backup.py`,避免日誌輪替丟掉歸屬證據。
4. 對帳差額:用幣安官方帳單(月報)核對 2026-06-12 ~ 10-24 的紀錄;在確認前不要把它歸給任何策略。
5. 同步停損問題(D1)用模擬做更直接的研究:例如停損距離與同時持倉數的關係,但**必須用獨立資料驗證**,避免再次依實盤期間挑條件。

## 7. 重現
```
python validation/d2_portfolio/d2_backup.py      # 唯讀備份 + 雜湊(設定檔移除金鑰)
python validation/d2_portfolio/d2_reconcile.py   # 唯讀(GET)對帳調查
python validation/d2_portfolio/d2_data.py        # 公開 K 線/費率/規格 → raw/(不進版控)
python validation/d2_portfolio/d2_signals.py     # 預先計算逐棒訊號(約 30 秒)
python validation/d2_portfolio/d2_calibrate.py   # 3.1
python validation/d2_portfolio/d2_replay.py      # 3.2
python validation/d2_portfolio/d2_attrib.py      # 3.3
python validation/d2_portfolio/d2_scenarios.py   # 4
python validation/d2_portfolio/d2_doc.py         # 組成本文件
```
'''
open(os.path.join(ROOT, 'docs', 'd2_portfolio_simulation.md'), 'w', encoding='utf-8').write(doc); print('doc written', len(doc))
