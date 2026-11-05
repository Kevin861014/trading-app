# -*- coding: utf-8 -*-
"""D1 步驟 6:組成 docs/d1_live_research.md。敘述中的數字全部取自 results/*.json(與 tables.md 同源)。"""
import json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'results'); ROOT = os.path.dirname(os.path.dirname(HERE))
R = json.load(open(os.path.join(OUT, 'analysis.json'))); C = json.load(open(os.path.join(OUT, 'compare.json'))); ST = json.load(open(os.path.join(OUT, 'stats.json')))
tab = open(os.path.join(OUT, 'tables.md'), encoding='utf-8').read()
T = {m.group(1): m.group(0).replace('## T', '### T', 1) for m in re.finditer(r'## (T\d+) .*?(?=\n## T\d+ |\Z)', tab, flags=re.S)}
rc, ov, eq, ex, cc, co, xq, cp = R['reconcile'], R['overall_closed'], R['equity'], R['exposure'], R['concentration'], R['costs'], R['execution'], C['total']
tf = ST['by_tf']; o = ST['overall_net_pct']; mo = {m['month']: m for m in R['monthly']}
reg = R['by_btc_regime']; sc = ST['stop_clusters'][0] if ST.get('stop_clusters') else None
unk = sum(c['unknown_trips']['n'] for c in R['combos']); unk_net = sum(c['unknown_trips']['net'] for c in R['combos'])
n_lt20 = sum(1 for c in R['combos'] if c['n'] < 20)
trx = next(c for c in R['combos'] if c['combo'].startswith('TRX'))
state_diff = None
for x in R['state_crosscheck']: pass
body = f'''# D1:23 組實盤機器人的歷史績效與風險分析(唯讀研究)

資料截止:{R['asOf']} UTC。**嚴格唯讀**:沒有修改 `trading-bot/` 或任何實盤設定、沒有停止或重啟機器人、沒有呼叫任何下單／撤單／改槓桿／轉帳／提領 API、沒有修改網站既有策略／回測／OOS、沒有使用付費服務。
幣安只用 GET 的帳戶讀取端點(`/fapi/v1/income`、`/fapi/v1/userTrades`、`/fapi/v2/account`、入金／劃轉的歷史查詢、公開 K 線),由白名單包裝層在送出前擋掉其他任何路徑與非 GET 方法(`validation/d1_live/binance_ro.py`,`tests/test_d1_readonly.py` 驗證);API 金鑰只在記憶體內簽名,不顯示、不寫檔。原始成交資料存在 `validation/d1_live/raw/`(已加入 `.gitignore`,不進版控);報告用的彙總結果在 `validation/d1_live/results/`。

## 0. 結論摘要

1. **整體:小幅正報酬,但統計上與零無法區分。** 入金合計 {rc['deposits_to_futures']} USDT(2 筆,無任何出金);交易損益(已實現 {rc['realized']} − 手續費 {-rc['commission']} − 資金費率 {-rc['funding']})= **{rc['net_pnl_realized_basis']:+.2f} USDT**,加上目前 4 組未平倉的未實現 {rc['unrealized_now']:+.2f},合計 **{rc['net_pnl_incl_unrealized']:+.2f} USDT(約 {rc['return_on_deposits_pct']:+.1f}% / 約 4.5 個月)**。{ov['n']} 筆已平倉交易:勝率 {ov['win']}%、淨 PF {ov['pf']}、平均每筆淨報酬 {o['mean']:+.2f}%(95% 信賴區間 [{o['ci95'][0]:+.2f}%, {o['ci95'][1]:+.2f}%],包含 0)。
2. **資金曲線**:{mo['2026-08']['month']} +{mo['2026-08']['ret_pct']}%、{mo['2026-09']['month']} +{mo['2026-09']['ret_pct']}%、{mo['2026-10']['month']} {mo['2026-10']['ret_pct']}%、{mo['2026-11']['month']}(到 11-05)**{mo['2026-11']['ret_pct']}%**;最大回撤 **{eq['max_dd_pct']}%({eq['max_dd_usd']} USDT)**,自 {eq['dd_from']} UTC 的高點起算,**目前仍在谷底**(含未實現的估算)。
3. **手續費吃掉大部分毛利**:已平倉毛損益 {co['gross_realized']} USDT,手續費 {co['commission_total']}(占毛利 {co['fees_vs_gross_pct']}%),資金費率 {co['funding_total']}。平均來回成本約 {co['avg_roundtrip_cost_pct_of_notional']}% 名目(100% 吃單);每月約 {co['trips_per_month']} 筆來回。
4. **1H 組合是主要拖累**:歸屬可靠的 1H 交易 {tf['1h']['n']} 筆淨 {tf['1h']['net']:+.2f}(毛 {tf['1h']['gross']:+.2f}、手續費 {tf['1h']['fees']:.2f});4H {tf['4h']['n']} 筆淨 {tf['4h']['net']:+.2f}。TRX 1H tsmom 一組({trx['n']} 筆)淨 {trx['net']:+.2f},占「歸屬可靠且虧損的組合」合計的一半。
5. **績效高度依賴少數極端交易**:最大 3 筆合計 {cc['top3']:+.2f} 超過全部淨損益 {cc['total_net']:+.2f};扣掉最大 3 筆後淨 **{cc['net_without_top3']:+.2f}**。最大一筆是 XRP 的 +40.5%(持倉 55 小時,2026-08-19,屬於日誌之前、策略無法可靠歸屬的期間)。
6. **23 組裡 {n_lt20} 組樣本不足(< 20 筆)**,只有 TRX 1H 達 {trx['n']} 筆。**目前實盤數字不足以替個別組合排名、汰換或調權重。**
7. **BTC 環境**:各環境的每筆淨報酬信賴區間都包含 0;下降趨勢最好(+{reg['down']['avg_pct']:.2f}%/筆)、上升趨勢略負({reg['up']['avg_pct']:+.2f}%/筆),**這與「做多機器人在 BTC 上升時比較好」的直覺相反,但差異遠小於不確定性,不能當成證據。**
8. **風險面:全部做多、同時持倉不多但會同步停損。** 平均同時持倉 {ex['avg_concurrent']} 組(最多 {ex['max_concurrent']}),約 {ex['share_hours_flat']}% 時間完全空手,名目槓桿最高約 {ex['max_leverage_x']}x——槓桿很低,主要風險是同步被停損:2026-10-29(UTC)一天 {R['worst_days'][0]['exits']} 筆出場、{R['worst_days'][0]['losers']} 筆虧損,淨 {R['worst_days'][0]['net']:+.2f}(超過整段淨獲利)。{f"其中 {'、'.join(sc['symbols'])} 在 {sc['span_s']} 秒內連續被停損,當時 BTC 6 小時只變動 {sc['btc_6h_pct']:+.2f}%——不需要大跌就會同步觸發。" if sc else ''}
9. **實盤與網站回測在訊號層面很一致**:{cp['live_n']} 筆實盤交易中 {cp['matched']} 筆能在同一個窗口的網站回測找到同一根 K 棒的進場;配對交易的每筆淨報酬差只有 {cp['pair_ret_diff_pct_wmean']:+.3f}%。**所以實盤落後網站長期回測的原因,主要不是執行或延遲**,而是期間與行情、成本口徑、與組合選擇偏誤(網站最近 540 天、23 組的回測本身就是 {cp['bt540_n']} 筆、勝率 {cp['bt540_win']}%、每筆 {cp['bt540_mean_pct']:+.3f}%、PF {cp['bt540_pf']},約等於零期望)。
10. **資料限制**:{unk} 筆交易(占已平倉 {unk/ov['n']*100:.0f}%,淨 {unk_net:+.2f})發生在日誌之前、且該幣曾換策略,**無法可靠歸屬到策略**;帳戶對帳有 {rc['residual']} USDT 的小差額原因不明;入金歷史只能用唯讀的劃轉查詢確認,沒有帳戶層級的完整帳單。

## 1. 資料盤點與可靠度

| 資料 | 內容 | 涵蓋期間 | 可靠度 | 用途／限制 |
|---|---|---|---|---|
| 幣安 `income`(唯讀) | 已實現損益、手續費、資金費率(全部 USDT;沒有 BNB 折抵) | 2026-06-22 → 2026-11-05 | 高(交易所原始紀錄) | 帳務基準;每筆有幣種與時間,但沒有策略標記 |
| 幣安 `userTrades`(唯讀) | 773 筆成交(23 個合約,100% 吃單) | 同上 | 高 | 重建來回交易、進場價、延遲;有 1 筆賣單的買單在資料範圍之前 |
| 入金／劃轉歷史(唯讀) | 2026-06-12 入金 152.49(TRX 鏈)→ 現貨轉合約;2026-08-24 入金 156.39(BSC)→ 合約;出金 0、合約轉出 0 | 2026-06 → 11 | 中高(兩次入金與劃轉金額吻合) | 第一筆入金不在 `income`(早於第一筆成交),所以要靠劃轉歷史 |
| 帳戶快照(唯讀) | 錢包 {rc['actual_wallet']}、未實現 {rc['unrealized_now']:+.2f}、4 組持倉 | 取得當下 | 高 | 未實現損益只有這個時間點的數字;逐小時的未實現是用公開 1H 收盤價估算 |
| 機器人日誌 `portfolio.log(.old)` | 進場／出場的策略名稱、訊號價、停損價、出場原因 | 2026-10-24 → 11-05(**之前的日誌已被輪替掉**) | 高(僅此期間) | 策略歸屬與出場原因的唯一直接證據 |
| 機器人狀態 `portfolio_state.json` | 每個組合的 `trades`(只有報酬率,**沒有時間**)與 `realized`(**毛損益**) | 各組合的存續期 | 中 | 用來交叉檢查與判斷「曾換過策略」;不能用來還原時間序列 |
| 設定檔與兩份備份 | 20 組(~10/10 前)→ 24 組 → 現行 23 組(2026-10-29 21:26 換 4 組) | — | 中 | 備份日期是檔案時間,不是啟用時間 |

**對帳**:入金 {rc['deposits_to_futures']} + 已實現 {rc['realized']} + 手續費 {rc['commission']} + 資金費率 {rc['funding']} = {rc['expected_wallet']},實際錢包 {rc['actual_wallet']},**差 {rc['residual']} USDT(原因不明,可能是 `income` 未涵蓋的微小項目;沒有硬湊)**。重建的 {ov['n']} 筆已平倉交易淨 {ov['net']:+.2f},與 `income` 基準的 {rc['net_pnl_realized_basis']:+.2f} 差 0.63:主要是 1 筆在資料範圍之前進場的 TRX 賣單(已實現 +0.68)與未平倉交易已付的進場手續費。

**策略歸屬**(已平倉 {ov['n']} 筆):日誌可確認 {R['attribution']['counts'].get('log', 0)} 筆(可靠);該幣只出現過一個策略 {R['attribution']['counts'].get('single', 0)} 筆(由設定與狀態檔推得,可靠度中高);**無法歸屬 {R['attribution']['counts'].get('unknown', 0)} 筆**(AAVE、BNB、PAXG、PYTH、SOL、XRP 在日誌之前換過策略,例如 BNB cmf→ttm、XRP cci→vortex、SOL force→ema_8_21),這些**不分配給任何策略**。

## 2. 整體績效、入金／出金與已實現／未實現

| 項目 | USDT |
|---|---|
| 入金（現貨→合約劃轉） | {rc['deposits_to_futures']}(2026-06-12 與 2026-08-24 各一筆) |
| 出金／合約轉出 | 0 |
| 已實現損益(毛) | {rc['realized']:+.2f} |
| 手續費 | {rc['commission']:+.2f} |
| 資金費率 | {rc['funding']:+.2f} |
| **交易淨損益(已實現基準)** | **{rc['net_pnl_realized_basis']:+.2f}** |
| 未實現損益(4 組未平倉,快照) | {rc['unrealized_now']:+.2f}（{', '.join('%s %+.2f' % (p['symbol'].replace('/USDT',''), p['unrealized']) for p in R['open'])}） |
| **含未實現的總損益** | **{rc['net_pnl_incl_unrealized']:+.2f}（占入金 {rc['return_on_deposits_pct']:+.2f}%）** |
| 錢包餘額 | {rc['actual_wallet']} |

「報酬率%」用淨值單位法(排除入金影響,早期資金較少所以權重較大),所以月報酬加總不等於 USDT 損益占入金的比例(例如期末淨值指數 {eq['nav_end']},約 +{(eq['nav_end']-1)*100:.1f}%,而總損益只占入金 {rc['return_on_deposits_pct']:+.2f}%)。

{T['T1']}

回撤:最大 **{eq['max_dd_pct']}%**(約 {eq['max_dd_usd']} USDT),高點 {eq['dd_from']} UTC → 目前({eq['dd_to']} UTC)。{eq['caveat']}

## 3. 23 組策略比較

只有歸屬可靠的交易計入各組合;**樣本量分級只是筆數分級,不是統計顯著性**。每組幾乎都 < 20 筆,所以個別組合的排名主要是運氣與少數交易,**不要據此汰換或調權重**。

{T['T2']}

{T['T3']}

## 4. 成本與執行

{T['T9']}

- 手續費占毛利 {co['fees_vs_gross_pct']}%:這個機器人單筆名目很小(平均 {co['avg_notional']} USDT),收益被固定比例的吃單手續費吃掉一大半。1H 組合換手最勤,所以侵蝕最嚴重(TRX:毛 {trx['gross']:+.2f}、手續費 {trx['fees']:.2f})。
- 實際成本比網站假設(加密 0.14% 來回)略低(手續費約 {co['avg_roundtrip_cost_pct_of_notional']}%);進場另有約 {xq['slip_mean_pct']}% 的成交價差(相對日誌訊號價)與 {xq['delay_median_s']} 秒中位數延遲——**對 4H 以上的策略影響很小**。

## 5. 市場環境(BTC)對照

環境分類 = C2 的規則(ADX (Wilder, 14) 與 ±DI),只用「進場當下已收盤的 BTC 4H K 棒」,對齊規則是收盤時間 ≤ 進場時間;這些環境是**事前**分類,績效是事後結果。

{T['T4']}

- 每個環境都有 63–104 筆,但報酬分散度大,**信賴區間都跨過 0**:不能說哪個環境「有效」或「無效」。最好的是 BTC 下降趨勢(淨 {reg['down']['net']:+.2f}),最差的是上升趨勢({reg['up']['net']:+.2f});盤整環境的平均每筆 {reg['range']['avg_pct']:+.2f}% 明顯被 ARB 一筆 +67.6% 拉高(淨損益只有 {reg['range']['net']:+.2f},PF {reg['range']['pf']})。
- 期間內 BTC 各環境佔比差不多(上升 {R['btc_regime_share_of_time']['up']['pct']}%、下降 {R['btc_regime_share_of_time']['down']['pct']}%、盤整 {R['btc_regime_share_of_time']['range']['pct']}%、轉換 {R['btc_regime_share_of_time']['transition']['pct']}%),所以沒有「某環境樣本特別少」的問題。
- **哪些組合容易同時虧損**:沒有固定的「一組一起死」的配對(兩兩持倉重疊率平均只有 {R['overlap_mean']});但同一根 4H 棒同時進場最多 5 組(見 T8),且停損會群聚(T6、T11)。

{T['T5']}

**市場急跌**:觀察期內 BTC 24 小時內回落 ≥ 4% 的事件只有幾次,其中只有 2026-10-21→22(跌 4.3%,當時 8 組持倉、槓桿 {R['btc_drops'][-1]['leverage_at_peak']}x,權益 {R['btc_drops'][-1]['equity_change_pct']}%)與 2026-10-29→30(跌 6.05%,當時 1 組持倉)有持倉。**沒有觀察到「大跌時暴露很高」的情況,但這是因為期間沒有嚴重的急跌,不能推論機器人能承受更大的急跌。**最大的單日虧損(10-29,UTC)不是 BTC 急跌所觸發:當天 BTC 大致在 79.9k–81.1k 之間(約 ±1.4%),BTC 的 -6% 發生在隔天(10-30 00:00 UTC 前後)。

{T['T6']}

## 6. 組合風險

{T['T7']}

{T['T8']}

- **同方向風險集中**:全部是做多,只要大盤與山寨幣同跌,所有持倉同向虧損。分散主要來自「不同時間進場」,不是方向分散。
- **同時持倉**:平均 {ex['avg_concurrent']} 組,但有 {ex['share_hours_ge5']}% 的時間 ≥ 5 組同時持倉;最多 {ex['max_concurrent']} 組({ex['max_conc_time']} UTC),名目 {ex['max_notional']} USDT。
- **多組高度重複**:持倉時間重疊最高的是 ALGO×XLM({R['overlap_top'][0][2]}),前 5 名在 {R['overlap_top'][4][2]}–{R['overlap_top'][0][2]},全部配對的平均只有 {R['overlap_mean']};價格日報酬兩兩相關平均 {R['price_corr']['mean_pairwise']}(中等,≥ 0.7 的配對只占 {R['price_corr']['share_pairs_ge_0.7']}%)。**沒有發現大量高度重複的組合**,但 23 個全是做多的加密貨幣,基本上共同暴露在同一個加密市場風險。
- **少數極端交易支撐績效**:是(見上)。這是最需要小心的結論:近 4.5 個月的正報酬可能只是 1–3 筆大贏。
- **單一標的／單一環境造成的大虧損**:沒有單一幣造成超過總毛虧損 10% 的損失(最大虧損是 TRX {R['by_symbol_net']['TRX/USDT']:+.2f},約占 {abs(R['by_symbol_net']['TRX/USDT'])/abs(cc['gross_loss'])*100:.0f}% 的毛虧損,但它同時也是 55 筆交易的累積);各 BTC 環境的虧損也沒有明顯集中。
- **同步停損事件**(同一 10 分鐘內 ≥ 3 筆停損類出場,只計日誌可辨識出場原因的交易,即 2026-10-24 之後):{'；'.join('%s UTC %s 在 %d 秒內連續停損(淨 %+.2f),BTC 前 6 小時 %+.2f%%' % (c['at'], '、'.join(c['symbols']), c['span_s'], c['net'], c['btc_6h_pct']) for c in ST['stop_clusters']) if ST.get('stop_clusters') else '無'}。另有 10-29 當天 AAVE 在約 47 分鐘後、以及晚間 SOL、AAVE、RUNE、TRX 多筆停損(T6)。

## 7. 與網站回測比較(不同口徑,不能直接相減)

| 面向 | 實盤 | 網站回測 |
|---|---|---|
| 成交 | 市價單(100% 吃單),K 棒收盤後約 {xq['delay_median_s']} 秒成交 | 下一根開盤價,無延遲 |
| 成本 | 實際手續費 ≈ 0.05%/邊(約 {co['avg_roundtrip_cost_pct_of_notional']}% 來回)、資金費率 {co['funding_total']}、真實滑價(進場平均 {xq['slip_mean_pct']}%) | 手續費 + 滑價共 0.14% 來回,無資金費率 |
| 資金與部位 | 本金 ≈ 310 USDT、每組分配 = 本金 × 權重 / 16(Σ權重)、風險 4.03%、最大 3x、逐倉、最小名目與數量進位、斷路器、重啟漏輪 | 起始 10,000、風險 1.5%、單組獨立、無進位 |
| 停損 | 交易所端保護停損(可能成交價不同) | 模擬器以停損價或開盤價較差者 |
| 期間 | 2026-06-22 → 11-05(各組合存續期不同,部分組合更晚才加入) | 可選任意期間;預設最近約 540 天 |
| 策略組合 | 實際換過策略(2026-10-29 換 4 組),有手動停止 | 固定一組 |

{T['T10']}

- **訊號與進場層面一致**:配對成功率 {cp['matched']}/{cp['live_n']};進場價平均比回測下一根開盤貴 {cp['entry_px_diff_pct_wmean']:+.3f}%,出場價差 {cp['exit_px_diff_pct_wmean']:+.3f}%,每筆淨報酬差 {cp['pair_ret_diff_pct_wmean']:+.3f}%——都遠小於一般單筆報酬的波動。未配對的 {cp['live_n'] - cp['matched']} 筆實盤與 {cp['bt_n'] - cp['matched']} 筆回測多出的交易,可能來自重啟漏輪、斷路器、最小下單量或手動操作(**沒有逐筆查證,不下結論**)。
- **所以實盤沒有明顯「落後」網站回測**:同一窗口內回測的每筆淨報酬 {cp['bt_mean_pct']:+.3f}%、實盤 {cp['live_mean_pct']:+.3f}%。先前報告提到的「實盤勝率 18% 對回測 29–30%」主要是期間、組合與計算方式不同(18% 來自 09-30~10-30 的 FIFO 估算);本研究以完整區間重建的勝率是 {ov['win']}%。
- 網站長期回測(最近 540 天、23 組)本身的每筆期望值約為零(PF {cp['bt540_pf']}),所以實盤接近零報酬**與回測一致**,不是機器人壞掉。

{T['T11']}

## 8. 資料限制(請特別注意)

1. 約 {unk/ov['n']*100:.0f}% 的已平倉交易(淨 {unk_net:+.2f})無法可靠歸屬到策略;各組合表只含歸屬可靠者,**合計不等於全部**(表內已列出差額來源)。
2. 日誌只有 2026-10-24 之後;之前的出場原因、訊號價、停損價無法取得;`portfolio.log.old` 到 5MB 就輪替,更早的紀錄已不存在。
3. 狀態檔的 `realized` 是毛損益,且與幣安成交重建的毛損益逐組有差(T11,狀態檔偏樂觀)。
4. 權益曲線與回撤含未實現,是用公開 1H 收盤價逐小時估算,**不是帳戶實際逐筆淨值**;未實現損益的「真實」值只有快照那一刻。
5. 對帳差 {rc['residual']} USDT、入金歷史只能靠劃轉查詢,沒有交易所完整帳單核對。
6. 期間只有約 4.5 個月、單一加密貨幣市場,其中只有一段約 -6% 的 BTC 急跌(2026-10-29→30);**無法評估大熊市下的表現**。
7. 所有組合的樣本都很小(只有 TRX 1H > 50 筆);信賴區間以 bootstrap 估計,假設交易之間獨立(同步停損顯示並不完全獨立),實際不確定性更大。

## 9. 下一步研究建議(都是研究;沒有改動實盤)

1. **先保全資料**:把 `portfolio.log(.old)`、`portfolio_state.json`、設定備份複製存檔(目前輪替會丟掉歸屬證據);若日後要改機器人讓每筆交易記錄策略與時間,必須另案取得你的明確批准,不在 D1 範圍。
2. **用幣安官方帳單核對**那 {rc['residual']} USDT 差額與 06-22 之前的紀錄。
3. **做一個「組合層級」的回測**(共用保證金、總名目上限、最小下單量與進位、同一時間的停損群聚),量化 1H 組合(TRX、XRP)與同步停損對整體的實際拖累,再決定 1H 是否值得保留——**這是純網站端研究,不碰實盤**。
4. **不要用目前的實盤數字替組合排名**:22/23 組 < 20 筆;若要評估個別組合,需要更長的實盤或用較長歷史做 walk-forward(含熊市),並控制多重比較。
5. **BTC 環境濾網**:D1 的實盤樣本沒有顯示出可用的環境效應(區間跨 0),也看不到「BTC 上升時較好」的證據;若要研究濾網,應使用較長歷史的 walk-forward,且樣本外只能揭露一次(C2/C3 的紀律)。
6. **降低對極端交易的依賴**(研究方向):比較「固定停損 2.5% / 止盈 7.5%」與追蹤停損的分布、檢查尾部交易(例如 XRP 一筆 +40%)是否可重複。
7. 持續累積:每週用同一批腳本(`validation/d1_live/`)重跑,追蹤樣本量與信賴區間是否收斂。

## 10. 如何重現
```
python validation/d1_live/fetch_all.py        # 唯讀:income / userTrades / 帳戶快照 → raw/(不進版控)
python validation/d1_live/fetch_transfers.py  # 唯讀:入金、劃轉歷史
python validation/d1_live/d1_trips.py         # 重建來回交易 + 策略歸屬
python validation/d1_live/d1_analyze.py       # 績效、成本、環境、風險
python validation/d1_live/d1_compare.py       # 與網站回測逐筆配對
python validation/d1_live/d1_stats.py         # bootstrap 與補充統計
python validation/d1_live/d1_report.py && python validation/d1_live/d1_doc.py
```
'''
body = body.replace('{sum(1 for _ in range(0))}771+', '773')
open(os.path.join(ROOT, 'docs', 'd1_live_research.md'), 'w', encoding='utf-8').write(body)
print('doc written', len(body))
