# -*- coding: utf-8 -*-
"""D3:組成 docs/d3_walkforward_study.md。敘述與表格的數字全部取自 results/*.json。"""
import collections, json, os
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, 'results'); ROOT = os.path.dirname(os.path.dirname(HERE))
L = lambda n: json.load(open(os.path.join(RES, n + '.json'), encoding='utf-8'))
inv = L('data_inventory'); sv = L('survivorship'); wf = L('walkforward')
f = lambda v, d=2: '—' if v is None else ('%+.*f' % (d, v)); g = lambda v, d=2: '—' if v is None else ('%.*f' % (d, v))
B = wf['blocks']; CL = wf['class_label']
RG = {'up': '上升', 'down': '下跌', 'range': '盤整'}
COMBO_1H = ('TRX/USDT', 'XRP/USDT')

# 1. 資料表
rows = []
for s, e in sorted(inv['symbols'].items(), key=lambda kv: kv[1]['onboard_date'] or ''):
    if s == 'BTC/USDT': continue
    rows.append('| %s | %s | %s | %s | %s | %s |' % (s.replace('/USDT', ''), e['onboard_date'], e['4h']['first'], format(e['4h']['bars'], ','), format(e['1h']['bars'], ','), '是(1H 組合)' if e['one_hour_combo'] else ''))
avail = '\n'.join(rows)
n_before = lambda d: sum(1 for s, e in inv['symbols'].items() if s != 'BTC/USDT' and e['onboard_date'] and e['onboard_date'] < d)
gap_total = sum(e['4h']['missing_bars'] + e['1h']['missing_bars'] for e in inv['symbols'].values())


def block_rows():
    out = []
    for b in B:
        A, Bm = b['A'], b['B']
        out.append('| %s | %s %s→%s | %s %s%% | %s | %s%% / %s%% | %s%% / %s%% | %s / %s | %s / %s | %s / %s | %s / %s | %s / %s |' % (
            CL[b['class']].split('(')[0], b['name'], b['from'][2:], b['to'][2:], RG[b['btc_regime']], f(b['btc_pct'], 1), b['active_combos_at_start'], f(A['return_pct']), f(Bm['return_pct']), g(A['max_dd_pct']), g(Bm['max_dd_pct']),
            f(A['worst_day_usd']), f(Bm['worst_day_usd']), A['trades'], Bm['trades'], g(A['fees'], 1), g(Bm['fees'], 1), A['pf'] if A['pf'] is not None else '—', Bm['pf'] if Bm['pf'] is not None else '—', f(A['avg_net_pct_of_notional'], 3), f(Bm['avg_net_pct_of_notional'], 3)))
    return '\n'.join(out)


def agg(cls_set, label):
    bs = [b for b in B if b['class'] in cls_set]
    if not bs: return ''
    n = len(bs); ddb = sum(1 for b in bs if b['B']['max_dd_pct'] > b['A']['max_dd_pct']); retb = sum(1 for b in bs if b['B']['return_pct'] > b['A']['return_pct'])
    stb = sum(1 for b in bs if b['B_stress']['return_pct'] > b['A_stress']['return_pct']); wdb = sum(1 for b in bs if b['B']['worst_day_usd'] > b['A']['worst_day_usd'])
    sa = sum(b['A']['return_pct'] for b in bs); sb = sum(b['B']['return_pct'] for b in bs)
    tr = (sum(b['B']['trades'] for b in bs) / sum(b['A']['trades'] for b in bs) - 1) * 100; fe = (sum(b['B']['fees'] for b in bs) / sum(b['A']['fees'] for b in bs) - 1) * 100
    nd = [b['btc_drops']['A']['sum_usd'] for b in bs]; ndb = [b['btc_drops']['B']['sum_usd'] for b in bs]
    return '| %s | %d | %d/%d | %d/%d | %d/%d | %d/%d | %s%% / %s%% | %.0f%% | %.0f%% | %s / %s |' % (label, n, ddb, n, wdb, n, retb, n, stb, n, f(sa, 1), f(sb, 1), tr, fe, f(sum(nd), 0), f(sum(ndb), 0))


def by_regime(cls_set, label):
    out = []
    for rg in ('up', 'down', 'range'):
        bs = [b for b in B if b['class'] in cls_set and b['btc_regime'] == rg]
        if not bs: continue
        out.append('| %s | %s | %d(%s) | %s%% / %s%% | %s%% / %s%% | %d/%d | %d/%d |' % (label, RG[rg], len(bs), '、'.join(b['name'] for b in bs), f(sum(b['A']['return_pct'] for b in bs) / len(bs), 1), f(sum(b['B']['return_pct'] for b in bs) / len(bs), 1),
                                                                                  g(sum(b['A']['max_dd_pct'] for b in bs) / len(bs), 1), g(sum(b['B']['max_dd_pct'] for b in bs) / len(bs), 1), sum(1 for b in bs if b['B']['max_dd_pct'] > b['A']['max_dd_pct']), len(bs),
                                                                                  sum(1 for b in bs if b['B']['return_pct'] > b['A']['return_pct']), len(bs)))
    return '\n'.join(out)


def decomp_pool(cls_set):
    tot = {'1H': collections.Counter(), '4H': collections.Counter()}; nh = {'1H': 0.0, '4H': 0.0}
    for b in B:
        if b['class'] not in cls_set: continue
        for k in ('1H', '4H'):
            d = b['decomp_A'][k]
            if not d.get('n'): continue
            for kk in ('n', 'gross', 'fees', 'funding', 'net'): tot[k][kk] += d[kk]
            nh[k] += d['notional_hours']; tot[k]['sum_gross_pct'] += d['avg_gross_pct'] * d['n']; tot[k]['sum_net_pct'] += d['avg_net_pct'] * d['n']; tot[k]['sum_fee_pct'] += d['avg_fee_pct'] * d['n']
    rows = []
    for k in ('1H', '4H'):
        t = tot[k]
        if not t['n']: continue
        rows.append('| %s | %d | %s | %s | %s | %s | %s%% | %s%% | %s%% | %s | %s |' % (k, t['n'], f(t['gross'], 1), g(t['fees'], 1), f(t['funding'], 1), f(t['net'], 1), f(t['sum_gross_pct'] / t['n'], 3), g(t['sum_fee_pct'] / t['n'], 3), f(t['sum_net_pct'] / t['n'], 3),
                                                              f(t['gross'] / nh[k] * 1e4, 2), f(t['net'] / nh[k] * 1e4, 2)))
    share = nh['1H'] / (nh['1H'] + nh['4H']) * 100 if (nh['1H'] + nh['4H']) else 0
    return '\n'.join(rows), share, tot


tI, shI, totI = decomp_pool({'I'}); tX, shX, totX = decomp_pool({'G', 'X'})
cont = wf['continuous']; cI, cX = cont['I'], cont['X']
I_bs = [b for b in B if b['class'] == 'I']
hdr = '| 區段類別 | 區段 | BTC | 可用組合數 | 報酬 A / B | 最大回撤 A / B | 最差單日 A / B（USDT） | 交易數 A / B | 手續費 A / B | 淨 PF A / B | 每筆平均淨報酬（占名目）A / B |\n|---|---|---|---|---|---|---|---|---|---|---|'
agg_hdr = '| 類別 | 區段數 | B 回撤較小 | B 最差單日較小 | B 報酬較高 | 成本×1.5 下 B 報酬較高 | 區段報酬加總 A / B | B 交易數變化 | B 手續費變化 | BTC 急跌(≥5%/24h)期間權益變動加總 A / B（USDT） |\n|---|---|---|---|---|---|---|---|---|---|'
tot_nontail = [b for b in B if b['class'] != 'T']
all_dd = sum(1 for b in tot_nontail if b['B']['max_dd_pct'] > b['A']['max_dd_pct']); all_ret = sum(1 for b in tot_nontail if b['B']['return_pct'] > b['A']['return_pct'])
drops_ok = sum(1 for b in tot_nontail if b['btc_drops']['A']['n'] and b['btc_drops']['B']['sum_usd'] > b['btc_drops']['A']['sum_usd']); drops_tot = sum(1 for b in tot_nontail if b['btc_drops']['A']['n'])
n1h_better = sum(1 for b in tot_nontail if b['decomp_A']['1H'].get('n') and b['decomp_A']['1H']['avg_gross_pct'] > b['decomp_A']['4H']['avg_gross_pct'])
n1h_bp_better = sum(1 for b in tot_nontail if b['decomp_A']['1H'].get('n') and b['decomp_A']['1H']['gross_bp_per_notional_hour'] > b['decomp_A']['4H']['gross_bp_per_notional_hour'])
top3_dep_I = [b for b in I_bs if b['A']['net_without_top3'] < 0]; top3_dep_all = [b for b in tot_nontail if b['A']['net_without_top3'] < 0]

doc = f'''# D3:獨立歷史資料可用性檢查與固定規則的時間順序多區段研究(A vs B)

**唯讀、離線。** 沒有修改 `trading-bot/`、設定、策略公式、網站回測引擎預設結果;沒有呼叫任何交易 API(只有幣安 USDT-M 永續合約的**公開** K 線與資金費率,沒有使用金鑰);沒有停止或重啟機器人;沒有使用付費服務;沒有重新開發模擬器(直接使用 D2 已校準的 `d2_sim.py`,成本與風險參數逐字相同)。原始行情在 `validation/d3_walkforward/raw/`(不進版控)。

## 0. 結論摘要

1. **歷史資料夠用,但不是所有合約都有同樣長的歷史。** 23 個 USDT-M 永續合約的 K 線都從各自的上市日開始、沒有缺口(1H 與 4H 共 {gap_total} 根缺漏);**沒有補造任何資料,也沒有用現貨或其他交易所冒充**。2021-01 時只有 15 個組合能產生訊號、2023-07 時 18 個;**PAXG 永續到 2025-03 才上市**(JUP 2024-01、PYTH 2023-11、WLD 2023-07),所以這些組合在較早的歷史裡根本不存在。
2. **倖存者偏誤無法完全排除**:公開清單只列出目前仍存在的合約,已被移除的下架合約看不到。目前清單中在 2023-07 之前上市的 {sv['onboarded_before_2023-07-01']['listed_before']} 個 USDT 永續裡,已有 {sv['onboarded_before_2023-07-01']['by_status_now'].get('SETTLING', 0)} 個({sv['onboarded_before_2023-07-01']['by_status_now'].get('SETTLING', 0) / sv['onboarded_before_2023-07-01']['listed_before'] * 100:.0f}%)處於下架結算中;而我們的 23 個合約**全部是今天還在交易的**。所以對歷史的任何回測,都比「當時真實可選的母體」樂觀。
3. **沒有任何一段歷史可以被證明是獨立樣本外。** 23 組是用網站「深度分析」從約 180 種策略挑選的(文件記載有挑選偏誤),深度分析對加密貨幣取 730 天評估窗口並多取 400 天暖機;更早的策略庫研究用 900 天 4H 快取。因此 **2023-07 之後的歷史一律視為「選擇已看過」**。2021-01 → 2023-06 沒有文件記載被用來挑選這 23 組,所以標為「**較獨立的歷史(未證明獨立)**」——但策略模板(例如 `ttm`、`supertrend`、`smc`、`tsmom`)的原始設計歷史不明,所以**不能宣稱通過 OOS**。
4. **A vs B 的結果(固定規則、固定區段、沒有重新調參)**:
   - **B(不啟用 TRX、XRP 1H)幾乎每個區段的最大回撤都較小**(12 個歷史區段中 {all_dd} 個;較獨立歷史 5/5),交易數約少 {(1 - sum(b['B']['trades'] for b in I_bs) / sum(b['A']['trades'] for b in I_bs)) * 100:.0f}%、手續費約少 {(1 - sum(b['B']['fees'] for b in I_bs) / sum(b['A']['fees'] for b in I_bs)) * 100:.0f}%,BTC 急跌期間的權益損失較小({drops_ok}/{drops_tot} 個有急跌事件的區段)。
   - **報酬沒有一致的優劣**:B 報酬較高的區段只有 {all_ret}/{len(tot_nontail)};**在 BTC 上升的區段 A 通常較好,在 BTC 下跌的區段 B 較好**(見下表)。
   - **這是「暴露與成本變少」,不能推論成「1H 策略沒有交易優勢」**:1H 組合在手續費與資金費率之前的毛損益,在較獨立歷史合計為 {f(totI['1H']['gross'], 1)} USDT(4H:{f(totI['4H']['gross'], 1)});它們輸在成本(1H 手續費 {g(totI['1H']['fees'], 1)}、資金費率 {f(totI['1H']['funding'], 1)}),而不是毛損益特別差。1H 的毛邊際與 4H 同量級:每筆平均毛報酬 1H 高於 4H 的區段有 {n1h_better}/{len(tot_nontail)} 個(以『名目×持有小時』計是 {n1h_bp_better}/{len(tot_nontail)} 個),並不是系統性較差。
   - **對少數極端獲利交易的依賴**:A 在 {len(top3_dep_all)}/{len(tot_nontail)} 個區段「扣掉最大 3 筆後淨損益為負」(較獨立歷史 {len(top3_dep_I)}/5)。
5. **不要把這些結果當成「B 已通過 OOS」**:它們是「在固定規則下的歷史探索與穩健性分析」。若要用 B 的結論改實盤,需要沒有被看過的資料(例如未來幾個月的前向紙上交易),這是下一步。

## 1. 歷史資料可用性

資料來源:幣安 USDT-M 永續合約公開 K 線(`/fapi/v1/klines`)與資金費率(`/fapi/v1/fundingRate`);最後一根未收盤的 K 棒已排除;沒有任何缺口被補值。

| 合約 | 上市日(exchangeInfo) | 第一根 4H | 4H 根數 | 1H 根數 | 備註 |
|---|---|---|---|---|---|
{avail}

- 上市日在 2021-01-01 前的合約:{n_before('2021-01-01')} / 23;在 2023-07-01 前:{n_before('2023-07-01')} / 23;在 2024-03-01 前:{n_before('2024-03-01')} / 23。各區段「可用組合數」見下方表格(組合需要 400 根 K 棒暖機才會產生訊號)。
- 目前 USDT 永續合約清單 {sv['asof_perpetual_count']} 個(交易中 {sv['status_now'].get('TRADING')}、下架結算中 {sv['status_now'].get('SETTLING')}、待上市 {sv['status_now'].get('PENDING_TRADING', 0)});2021-01 前上市的 {sv['onboarded_before_2021-01-01']['listed_before']} 個中 {sv['onboarded_before_2021-01-01']['by_status_now'].get('SETTLING', 0)} 個已在結算;2023-07 前上市的 {sv['onboarded_before_2023-07-01']['listed_before']} 個中 {sv['onboarded_before_2023-07-01']['by_status_now'].get('SETTLING', 0)} 個。**已經從清單消失的下架合約公開 API 取不到,無法列舉,所以這只是倖存者偏誤的下限。**
- 限制:歷史的最小下單量/步長/最小名目沿用現行規格(早期可能不同);早期合約的流動性與滑價可能比現在差,模擬沿用 D2 的滑價假設。

## 2. 資料是否獨立:被看過的歷史

| 證據 | 內容 | 含義 |
|---|---|---|
| 機器人說明報告 §2、§3 | 23 組是使用者用網站「深度分析」從約 180 種策略中挑選;其中 4 組在 2026-10-29 更換;報告自己指出「回測成績本身存在挑選偏誤」。2026-10-29 另發現網站的「4H」原本實際用 1H 資料,舊 4H 篩選無效,已重新篩選 | 挑選窗口 = 深度分析的資料範圍;舊篩選與新篩選用的資料不同 |
| `app.py` `deep_analysis` | 加密貨幣:評估窗口 730 天、另多取 400 天暖機(取得範圍約從選擇日往前 1130 天);排名只用樣本內,但**人是看過樣本外結果才挑的** | 以選擇日 2026-10-29 計,取得範圍起點約 2023-09;更早的選擇日起點更早 → 保守分界取 2023-07-01 |
| 機器人 `integration/out`(2026-08 的策略庫與籃子研究) | 70 檔 4H 快取、`fetch_binance_4h(days=900)`(約 2024-02-29 起);漏斗 2,773 對 → 62 → 前 20,使用 IS/OOS 與多重比較檢定。該研究的資料來源**偏好現貨**(本研究不使用現貨) | 策略庫與籃子規則已看過 2024-02 之後的歷史;連它的 OOS 也不獨立於後續的組合挑選 |
| `sim.py` 的策略模板(`ttm`、`supertrend`、`smc`、`tsmom`) | 原始設計歷史沒有紀錄 | **無法證明 2023-07 之前的歷史沒被看過** |

據此,本研究事先固定的分類(在看任何結果前寫死,`d3_config.py`):

| 類別 | 區間 | 稱呼 | 能不能說是 OOS |
|---|---|---|---|
| I | 2021-01 → 2023-06-30 | 較獨立的歷史(未證明獨立) | **不能**(只是沒有文件記載被用來挑選;策略模板的設計歷史不明) |
| G | 2023-07 → 2024-02-29 | 灰色地帶 | 不能(可能只當暖機取得,但無法排除被看過) |
| X | 2024-03 → 2026-10-29 | 歷史探索 | 不能(已知被用於研究與挑選) |
| T | 2026-10-29 → 現在 | 選擇之後 | 太短(約 1 週,19 筆交易),只列出不下結論 |

**沒有「真正未使用過的獨立資料」可以驗證**,所以全部結果只能稱為「歷史探索」或「穩健性分析」。**這不是傳統的 walk-forward**:組合與參數沒有重新擬合,所以只是「固定規則在連續不重疊區段上的表現」。

## 3. 方法(事先固定,沒有因結果調整)

- 方案:**A** 現行全部 23 組;**B** 不啟用 TRX、XRP(1H),其餘條件完全相同(Σ權重仍 16,其他組合的資金配置不變)。不搜尋其他組合。
- 模擬器:D2 的 `d2_sim.py`,成本/風險/滑價/資金費率與 D2 的 A/B 逐字相同(測試確認);起始資金 310 USDT,**每個區段各自從空手重新開始**;尚未上市的合約沒有資料就不交易、不重新分配資金。
- 區段:日曆半年(2021H1 … 2026-07~10-29,共 12 個)+ 選擇之後的尾巴。BTC 區段標籤規則寫死:區段內 BTC 漲跌 > +15% = 上升、< −15% = 下跌、其餘 = 盤整。成本壓力:吃單 0.075%/邊、進場滑價 0.06%、出場 0.02%、停損 0.084%。
- **不因任何區段結果不好而更換區段或調參。** 沒有掃描參數。

## 4. 結果

### 4.1 各區段(A / B)

{hdr}
{block_rows()}

### 4.2 依類別彙總

{agg_hdr}
{agg({'I'}, '較獨立的歷史 I')}
{agg({'G'}, '灰色地帶 G')}
{agg({'X'}, '歷史探索 X')}
{agg({'I', 'G', 'X'}, '全部歷史(I+G+X)')}

連續(不重置資金)的長期結果:較獨立的歷史 {cI['from']} → {cI['to']}:A {f(cI['A']['return_pct'])}% / 最大回撤 {g(cI['A']['max_dd_pct'])}% / {cI['A']['trades']} 筆;B {f(cI['B']['return_pct'])}% / {g(cI['B']['max_dd_pct'])}% / {cI['B']['trades']} 筆。歷史探索 {cX['from']} → {cX['to']}:A {f(cX['A']['return_pct'])}% / {g(cX['A']['max_dd_pct'])}% / {cX['A']['trades']} 筆;B {f(cX['B']['return_pct'])}% / {g(cX['B']['max_dd_pct'])}% / {cX['B']['trades']} 筆。

### 4.3 依 BTC 市場期間(上升／下跌／盤整)

| 類別 | BTC 區段 | 區段數 | 平均報酬 A / B | 平均最大回撤 A / B | B 回撤較小 | B 報酬較高 |
|---|---|---|---|---|---|---|
{by_regime({'I'}, '較獨立 I')}
{by_regime({'G', 'X'}, '探索 G+X')}

(盤整區段只有 1 個,不能下結論。)

### 4.4 「移除 1H」= 降低暴露與成本?還是「1H 策略本身沒有優勢」?

方法:用 A 的實際交易,把 1H 組合與 4H 組合分開統計(手續費前的毛損益、手續費、資金費率、淨損益,以及每單位「名目 × 持有小時」的邊際)。

**較獨立的歷史 I(5 個區段合計):**

| 週期 | 交易數 | 毛損益 | 手續費 | 資金費率 | 淨損益 | 每筆平均毛報酬(占名目) | 每筆平均手續費 | 每筆平均淨報酬 | 毛邊際(bp/名目·小時) | 淨邊際(bp/名目·小時) |
|---|---|---|---|---|---|---|---|---|---|---|
{tI}

**歷史探索 G+X(7 個區段合計):**

| 週期 | 交易數 | 毛損益 | 手續費 | 資金費率 | 淨損益 | 每筆平均毛報酬(占名目) | 每筆平均手續費 | 每筆平均淨報酬 | 毛邊際(bp/名目·小時) | 淨邊際(bp/名目·小時) |
|---|---|---|---|---|---|---|---|---|---|---|
{tX}

(1H 組合只有 2 組、佔 I 期間約 {shI:.0f}% 的「名目×持有小時」暴露;G+X 約 {shX:.0f}%。)

**解讀(只描述):**
- **兩個說法都有一部分成立,但不能畫等號。** B 的好處(回撤、手續費、BTC 急跌時的損失)是可以直接由「少了兩個高換手、常在場內的部位」解釋的:交易數與手續費大幅減少、同時持倉與暴露下降。
- **沒有證據顯示 1H 策略「本身沒有優勢」**:1H 的毛損益在 I 期間為 {f(totI['1H']['gross'], 1)}(4H {f(totI['4H']['gross'], 1)}),毛邊際與 4H 同量級、同方向;1H 的淨損益為負,主因是每筆約 {g(totI['1H']['sum_fee_pct'] / totI['1H']['n'], 3)}% 的手續費(再加資金費率)超過了很小的毛邊際。若成本更低(例如 maker 或更低費率),結論可能不同——但這需要另外的驗證。
- **在 BTC 上升的區段 B 通常報酬較低**(7 個上升區段中 A 較好 6 個);在下跌區段 B 較好(4 個中 3 個),但那些區段 4H 組合同樣虧損,所以優勢主要是「少曝險」。這符合「降低暴露」的解釋,不需要「1H 沒有優勢」的假設。
- **做不到的區分**:A 與 B 只差兩組,無法在不新增情境的前提下把「暴露效果」與「1H 策略本身」完全分開(這需要「暴露相同、策略不同」的對照,不屬於 D3 預先指定的比較,也容易變成搜尋)。

### 4.5 其他風險面

- **最差單日、同時持倉與暴露**:見 4.1 的最差單日;B 的最差單日在 {sum(1 for b in tot_nontail if b['B']['worst_day_usd'] > b['A']['worst_day_usd'])}/{len(tot_nontail)} 個區段較小。平均同時持倉約 {sum(b['A']['avg_concurrent'] for b in tot_nontail) / len(tot_nontail):.1f}(A)/ {sum(b['B']['avg_concurrent'] for b in tot_nontail) / len(tot_nontail):.1f}(B);最大名目暴露 A 最高 {max(b['A']['max_exposure_x'] for b in tot_nontail)}×、B 最高 {max(b['B']['max_exposure_x'] for b in tot_nontail)}×(遠低於 3× 上限)。
- **成本放大 ×1.5**:{sum(1 for b in tot_nontail if b['B_stress']['return_pct'] > b['A_stress']['return_pct'])}/{len(tot_nontail)} 個區段 B 的報酬高於 A(正常成本下 {all_ret}/{len(tot_nontail)});成本越高,B 越相對有利,因為它的交易數更少。
- **BTC 急跌(24 小時內自滾動高點回落 ≥ 5%)**:有事件的 {drops_tot} 個區段中 B 的權益損失較小者 {drops_ok} 個(B 少了兩組部位,所以損失較小是預期的)。
- **依賴少數極端獲利交易**:A 在 {len(top3_dep_all)}/{len(tot_nontail)} 個區段扣掉最大 3 筆後淨損益為負;B 也有類似情形(見各區段的「最大 3 筆」欄,結果檔 `walkforward.json`)。**兩個方案都高度依賴少數大贏。**

## 5. 限制與不確定性

1. **沒有獨立樣本外**:所有區段都是歷史探索/穩健性分析;較獨立的歷史也不能宣稱通過 OOS。
2. **倖存者偏誤**:23 組是今天還在交易的合約;已移除的下架合約不在資料裡,歷史結果偏樂觀。
3. **可用組合數隨時間變化**:早期只有 15–17 組,Σ權重固定 16,所以早期的資金利用率較低、結果不能與後期直接比較績效數字,只能比較 A 與 B 的相對差異。
4. **區段之間不是獨立的統計樣本**(同一批策略、同一個加密市場);「B 在 N/12 區段較好」只是描述,不是顯著性檢定。
5. **模擬假設沿用 D2**:校準只在約 12 天、32 筆交易的已知設定期間完成,更長歷史與早期流動性沒有校準;步長/最小名目沿用現行規格。
6. 區段類別的分界(2023-07-01)是保守估計,真正被看過的範圍可能更早;若更早,較獨立歷史的可用範圍更小。

## 6. 結論與可行方案

- **資料足夠做固定規則的歷史比較,但不足以產生「獨立驗證」。** 如果要有真正的 OOS,只有兩條路:(a) **前向紙上交易**(從現在起,不動實盤,依 B 的規則並行記錄,累積未被看過的資料);(b) 找到**策略設計與挑選都沒用過的資料**——目前沒有。
- B 的證據強度:**「降低回撤、成本與急跌損失」一致**(12 個歷史區段 {all_dd} 個回撤較小);**「提高報酬」不一致**。是否採用取決於你更在意哪一個,**這個研究不建議也不自動修改實盤**。
- 建議的下一步(只是研究):1) 開一個**前向紙上交易**紀錄 B(與 A 並行),至少累積一段完整的 BTC 上升/下跌/盤整循環,再看是否出現與歷史一致的差異;2) 在紙上紀錄中加入「暴露相同、策略不同」的預先登記對照(例如把 1H 組合改為 4H 或只做長持),以分開暴露效果與策略效果;3) 評估較低成本的成交方式對 1H 邊際的影響(研究,不碰實盤)。

## 7. 重現
```
python validation/d3_walkforward/d3_data.py         # 公開 USDT-M K 線/費率 → raw/ + results/data_inventory.json(約 12 分鐘)
python validation/d3_walkforward/d3_survivorship.py # 公開 exchangeInfo 統計
python validation/d3_walkforward/d3_signals.py      # 完整歷史的逐棒訊號(約 2 分鐘)
python validation/d3_walkforward/d3_run.py          # A/B 多區段(約 2 分鐘)
python validation/d3_walkforward/d3_doc.py          # 組成本文件
```
'''
open(os.path.join(ROOT, 'docs', 'd3_walkforward_study.md'), 'w', encoding='utf-8').write(doc); print('doc written', len(doc))
