# -*- coding: utf-8 -*-
"""C3:免費規則式研究摘要(沒有 AI、沒有預測、不連網、不重算任何績效)。

輸入:/api/regime_study 的回應(study)、/api/mtf 的回應(mtf,可省略)、前端的條件試驗次數(trials,可省略)。
輸出:繁體中文說明,每一句話都附『依據欄位』(API 回應裡的實際路徑與數值)與跳轉目標;文字只由固定模板 + 這些欄位的數值組成。
固定規則(RULES)全部列在下面;資料過期/不足/沒有交易/樣本不足時,一律降級成『描述 + 說明為什麼不能下結論』,絕不產生肯定的買賣結論。
這份摘要不是交易訊號,也不會套用到實盤機器人。
"""
import re

OOS_MIN_TRADES = 5          # 與 app.OOS_MIN_TRADES 相同(樣本外至少要有這麼多筆才不算『證據不足』)
SAMPLE_OK = 20              # 與 app.OOS_TIER_PRELIM 相同(< 20 筆 = 樣本不足)
FIXED_NUMBERS = {'14', '20', '25', '5', '50', '200', '1', '0', '3', '0.1', '27', '100'}      # 規則文字裡本來就有的固定數字(門檻),不是資料

RULES = [
    '環境分類:ADX (Wilder, 14) ≥ 25 且 +DI ≥ −DI = 上升趨勢;ADX ≥ 25 且 +DI < −DI = 下降趨勢;ADX < 20 = 盤整;20 ≤ ADX < 25 = 趨勢轉換中(與卡片市場性格相同)。',
    '資料過期、不足、時間戳異常、取得失敗(阻擋型品質狀態)→ 只描述歷史狀態,不評估目前環境,也不下結論。',
    '窗口內沒有交易 → 不評估策略。樣本內交易 < 20 筆 → 一律標「樣本不足」,數字只是描述。',
    '樣本外交易 < 5 筆 → 證據不足;5–19 筆 → 樣本不足(只能參考)。',
    '樣本內與樣本外的淨 PF 都 ≥ 1 才說「沒有看到樣本外失效的跡象」;樣本內 ≥ 1 而樣本外 < 1 → 「樣本外沒有延續」。這些都只是歷史統計。',
    '目前環境的支持度:該環境在樣本內有 ≥ 20 筆交易才評論其淨 PF;否則只說「樣本不足,不能判斷」。',
    '濾網:只有在濾網後樣本內 ≥ 20 筆且淨 PF 高於原始策略才算「樣本內改善」;樣本外尚未揭露時,一律說「沒有樣本外證據」;揭露後樣本外也 ≥ 20 筆且淨 PF 高於原始並 ≥ 1,才說「樣本外同方向」。',
    '條件試驗 ≥ 3 個 → 提醒多重比較;樣本外揭露 ≥ 2 個條件 → 提醒樣本外已不再獨立。',
    '不產生任何「建議買進／賣出」、價格預測或報酬保證。',
]
DISCLAIMER = '這是依固定規則整理的研究說明，不是 AI 預測，不是買賣訊號，也不會套用到實盤機器人；每一句話都列出依據的 API 欄位，展開即可對照。過去績效不代表未來。'
BIAS = {'bull': '偏多', 'bear': '偏空', 'neutral': '中性／分歧'}
LEVEL_LABEL = {'blocked': '資料過期或異常', 'insufficient': '樣本不足或資料不足', 'notrades': '沒有交易', 'descriptive': '描述性摘要'}


# ───────── 取值與格式 ─────────
def get_path(root, path):
    cur = root
    for tok in re.findall(r'[^.\[\]]+|\[\d+\]', path):
        if cur is None: return None
        if tok.startswith('['):
            i = int(tok[1:-1])
            cur = cur[i] if isinstance(cur, list) and i < len(cur) else None
        else:
            cur = cur.get(tok) if isinstance(cur, dict) else None
    return cur


def fmt(kind, v, root):
    if v is None: return '—'
    if kind == 'above': return '之上' if v else '之下'
    if isinstance(v, bool): return '是' if v else '否'
    if isinstance(v, list): return '、'.join(str(x) for x in v)
    if kind == 'pf': return ('%.2f' % v) if v < 999 else '∞'
    if kind == 'n1': return '%.1f' % v
    if kind == 'n2': return '%.2f' % v
    if kind == 'int': return str(int(v))
    if kind == 'regime': return root['study'].get('labels', {}).get(v, str(v))
    if kind == 'bias': return BIAS.get(v, str(v))
    if kind == 'tier': return '樣本不足' if v < SAMPLE_OK else ('初步觀察' if v < 50 else '可進一步評估')
    return str(v)


class Builder:
    def __init__(self, root):
        self.root = root

    def item(self, iid, template, ev, jump=None, level=None):
        """ev = [(key, path, label, kind)];template 裡的 {key} 會被該欄位的顯示值取代。回傳一則說明。"""
        out = []; vals = {}
        for key, path, label, kind in ev:
            raw = get_path(self.root, path); disp = fmt(kind, raw, self.root)
            vals[key] = disp; out.append({'key': key, 'path': path, 'label': label, 'kind': kind, 'value': raw, 'display': disp})
        text = template.format(**vals)
        return {'id': iid, 'text': text, 'evidence': out, 'jump': jump, 'level': level}


def J(target, label): return {'view': 'market', 'target': target, 'label': label}


# ───────── 主函式 ─────────
def summarize(study, mtf=None, trials=None):
    root = {'study': study, 'mtf': mtf, 'trials': trials or {}}
    B = Builder(root); sections = []
    dq = study.get('dataQuality'); blocked = bool(dq and dq.get('blocking')); unknown_q = dq is None
    ov = study.get('overall') or {}; allb = ov.get('all') or {}; isb = ov.get('is') or {}; oosb = ov.get('oos')
    ntr = allb.get('trades', 0) or 0
    cur = study.get('currentRegime') or {}
    split = study.get('split')

    # 0. 資料品質
    items = []
    if unknown_q:
        items.append(B.item('dq_main', '策略所用資料的品質檢查沒有結果（視為未檢查），所以不對「目前」環境下結論。', [], J('#regBody .rg-head', '資料與窗口'), 'warn'))
    else:
        t = '策略所用資料（{tf}，最後已收盤 K 棒 {last} UTC）品質：{label}。'
        ev = [('tf', 'study.dataInterval', '資料週期', 'str'), ('last', 'study.data.lastBar', '最後已收盤 K 棒', 'str'), ('label', 'study.dataQuality.label', '資料品質', 'str')]
        if blocked:
            t += '{detail} 因此以下所有內容只是歷史狀態，不代表目前，也不下結論。'; ev.append(('detail', 'study.dataQuality.detail', '品質說明', 'str'))
        items.append(B.item('dq_main', t, ev, J('#regBody .rg-head', '資料與窗口'), 'bad' if blocked else 'ok'))
    if mtf:
        parts = []; ev = []
        for i, e in enumerate(mtf.get('timeframes') or []):
            if not e.get('supported'):
                parts.append('{u%d}（資料來源不支援）' % i); ev.append(('u%d' % i, 'mtf.timeframes[%d].label' % i, '週期', 'str'))
            else:
                parts.append('{l%d} {q%d}' % (i, i)); ev += [('l%d' % i, 'mtf.timeframes[%d].label' % i, '週期', 'str'), ('q%d' % i, 'mtf.timeframes[%d].quality.label' % i, '資料品質', 'str')]
        if parts: items.append(B.item('dq_mtf', '多週期資料品質：' + '、'.join(parts) + '。', ev, J('#mtfBody', '多週期表'), 'ok'))
    sections.append({'id': 'quality', 'title': '資料品質', 'items': items})

    # 1. 目前環境
    items = []; stale_prefix = '（資料過期/異常，這是最後一根已收盤 K 棒的歷史狀態）' if blocked else ''
    if cur.get('own') and cur['own'] != 'na':
        items.append(B.item('env_own', '最後已收盤 K 棒（{bar} UTC）的標的自身環境：「{reg}」。' + stale_prefix,
                            [('bar', 'study.currentRegime.barTime', '最後已收盤 K 棒', 'str'), ('reg', 'study.currentRegime.own', '自身環境', 'regime')], J('#regBody .rg-head', '環境佔比與分類條件')))
    else:
        items.append(B.item('env_own', '目前還在 ADX 暖機期（資料最前面 27 根），沒有環境分類。', [], J('#regBody .rg-head', '環境分類條件'), 'warn'))
    tfe = None
    if mtf:
        for i, e in enumerate(mtf.get('timeframes') or []):
            if e.get('supported') and e.get('tf') == study.get('dataInterval') and e.get('indicators'): tfe = i
    if tfe is not None:
        base = 'mtf.timeframes[%d].indicators.' % tfe
        items.append(B.item('env_adx', '判斷依據（固定規則：ADX ≥ 25 趨勢、< 20 盤整、20–25 轉換中）：{lab} {adx}，+DI {p}、−DI {m}。',
                            [('lab', base + 'adxLabel', '指標', 'str'), ('adx', base + 'adx', 'ADX', 'n1'), ('p', base + 'plusDi', '+DI', 'n1'), ('m', base + 'minusDi', '−DI', 'n1')], J('#mtfBody', '多週期表（ADX／±DI）')))
        items.append(B.item('env_ema', 'EMA：{ema}；收盤價位於 EMA50 {a50}。', [('ema', base + 'emaAlignText', 'EMA 排列', 'str'), ('a50', base + 'above.ema50', '收盤是否在 EMA50 之上', 'above')], J('#mtfBody', '多週期表（EMA）')))
        ml = (mtf['timeframes'][tfe]['indicators'] or {}).get('trendLabel'); sl = (study.get('labels') or {}).get(cur.get('own'))
        if ml and sl and ml != sl:
            items.append(B.item('env_mismatch', '注意：多週期面板的趨勢標籤是「{ml}」，本研究的環境是「{sl}」。兩者資料起點不同，ADX 在門檻附近差 0.1 就會換類，請以本研究（歷史歸屬用的）分類為準。',
                                [('ml', base + 'trendLabel', '多週期標籤', 'str'), ('sl', 'study.currentRegime.own', '本研究環境', 'regime')], None, 'warn'))
    else:
        items.append(B.item('env_adx', '尚未取得這個週期的多週期明細（ADX／±DI／EMA），略過這部分。', [], J('#mtfPanel', '多週期面板'), 'warn'))
    ref = study.get('reference') or {}
    if ref.get('supported') and cur.get('market'):
        items.append(B.item('env_mkt', '大盤環境（{name}）：「{reg}」。', [('name', 'study.reference.name', '大盤參考', 'str'), ('reg', 'study.currentRegime.market', '大盤環境', 'regime')], J('#regBody .rg-head', '大盤環境')))
    elif ref.get('reason'):
        items.append(B.item('env_mkt', '大盤環境：{why}', [('why', 'study.reference.reason', '原因', 'str')], None, 'warn'))
    sections.append({'id': 'environment', 'title': '目前市場環境與判斷依據', 'items': items})

    # 2. 多週期一致性
    items = []
    if mtf and mtf.get('summary'):
        items.append(B.item('mtf_sum', '{txt}', [('txt', 'mtf.summary.text', '多週期彙整', 'str')], J('#mtfBody', '多週期表')))
        parts = []; ev = []
        for i, e in enumerate(mtf.get('timeframes') or []):
            if e.get('supported') and e.get('usable') and e.get('indicators'):
                parts.append('{l%d}{b%d}' % (i, i)); ev += [('l%d' % i, 'mtf.timeframes[%d].label' % i, '週期', 'str'), ('b%d' % i, 'mtf.timeframes[%d].indicators.bias' % i, '技術偏向', 'bias')]
        if parts: items.append(B.item('mtf_bias', '各週期技術偏向（只列資料可用的）：' + '、'.join(parts) + '。這只是指標位置的描述，不是價格預測。', ev, J('#mtfBody', '多週期表')))
    else:
        items.append(B.item('mtf_sum', '尚未取得多週期資料，無法比較各時間週期是否一致。', [], J('#mtfPanel', '多週期面板'), 'warn'))
    sections.append({'id': 'mtf', 'title': '各時間週期是否一致', 'items': items})

    # 3. 策略歷史
    items = []; level = 'descriptive'
    if ntr == 0:
        items.append(B.item('st_none', '此策略「{s}」在窗口內（{ws} 起）沒有任何交易，無法評估，也不做任何推論。', [('s', 'study.strategyName', '策略', 'str'), ('ws', 'study.windowStart', '窗口起點', 'str')], J('#regBody .rg-tbl', '績效表'), 'warn'))
    else:
        items.append(B.item('st_all', '「{s}」窗口內（{ws} 起）共 {n} 筆交易（扣成本）：淨 PF {pf}、勝率 {w}%、最大回撤 {dd}%、報酬 {tot}%（本站回測口徑）。',
                            [('s', 'study.strategyName', '策略', 'str'), ('ws', 'study.windowStart', '窗口起點', 'str'), ('n', 'study.overall.all.trades', '交易筆數', 'int'), ('pf', 'study.overall.all.pf', '淨 PF', 'pf'),
                             ('w', 'study.overall.all.win', '勝率', 'n1'), ('dd', 'study.overall.all.mdd', '最大回撤', 'n2'), ('tot', 'study.overall.all.total', '報酬', 'n2')], J('#regBody .rg-tbl', '績效表')))
        small = (isb.get('trades') or 0) < SAMPLE_OK
        items.append(B.item('st_is', '樣本內 {n} 筆（{tier}），淨 PF {pf}、最大回撤 {dd}%。' + ('樣本不足，這些數字只是描述，不能當成策略有效的證據。' if small else ''),
                            [('n', 'study.overall.is.trades', '樣本內筆數', 'int'), ('tier', 'study.overall.is.trades', '樣本量分級', 'tier'), ('pf', 'study.overall.is.pf', '樣本內淨 PF', 'pf'), ('dd', 'study.overall.is.mdd', '樣本內最大回撤', 'n2')], J('#regBody .rg-tbl', '樣本內表'), 'warn' if small else None))
        if not split or not oosb:
            items.append(B.item('st_oos', '資料太短，沒有獨立的樣本外，所以沒有樣本外證據。', [], None, 'warn'))
        else:
            n = oosb.get('trades') or 0; ev = [('n', 'study.overall.oos.trades', '樣本外筆數', 'int'), ('pf', 'study.overall.oos.pf', '樣本外淨 PF', 'pf'), ('ipf', 'study.overall.is.pf', '樣本內淨 PF', 'pf')]
            if n < OOS_MIN_TRADES: t, lv = '樣本外只有 {n} 筆，證據不足，不能判斷策略在樣本外是否延續。', 'warn'
            else:
                ipf, opf = isb.get('pf') or 0, oosb.get('pf') or 0
                if ipf >= 1 and opf >= 1: t = '樣本內淨 PF {ipf}、樣本外 {pf}（{n} 筆）都 ≥ 1：沒有看到樣本外失效的跡象，但這仍只是歷史統計。'
                elif ipf >= 1: t = '樣本內淨 PF {ipf}，但樣本外只有 {pf}（{n} 筆，< 1）：樣本外沒有延續，樣本內的結果可能不穩定或過度擬合。'
                elif opf >= 1: t = '樣本內淨 PF {ipf}（< 1）而樣本外 {pf}（{n} 筆）≥ 1：兩段不一致，不宜據此判斷。'
                else: t = '樣本內淨 PF {ipf}、樣本外 {pf}（{n} 筆）都 < 1：歷史上沒有看到正的期望值。'
                lv = 'warn' if n < SAMPLE_OK else None
                if n < SAMPLE_OK: t += ' 樣本外只有 {n} 筆（樣本不足），僅供參考。'
                if oosb.get('win') == 100 or isb.get('win') == 100: t += ' 沒有虧損交易時，PF 沿用本站算法（獲利總和），不是真正的比值。'
            items.append(B.item('st_oos', t, ev, J('#regBody .rg-tbl', '樣本外表'), lv))
    sections.append({'id': 'strategy', 'title': '選定策略的歷史績效', 'items': items})

    # 4. 目前環境下的歷史支持度
    items = []
    code = cur.get('own'); bds = (study.get('breakdown') or {})
    def support(basis, code, who):
        bd = bds.get(basis)
        if not bd or not code or code == 'na': return None
        base = 'study.breakdown.%s.' % basis; n = (bd['is'].get(code) or {}).get('n', 0)
        regev = ('reg', 'study.currentRegime.' + ('own' if basis == 'own' else 'market'), who + '環境', 'regime')
        nev = ('n', base + 'is.%s.n' % code, '樣本內筆數', 'int')
        if n == 0: return B.item('sup_' + basis, who + '目前環境「{reg}」：歷史上此策略在這個環境沒有任何進場交易，沒有證據可言。', [regev, nev], J('#regBody .rg-tbl', '分環境績效表'), 'warn')
        if n < SAMPLE_OK:
            o = (bd.get('oos') or {}).get(code) or {}
            return B.item('sup_' + basis, who + '目前環境「{reg}」：樣本內只有 {n} 筆（樣本不足）' + ('，樣本外 {m} 筆' if split else '') + '，不足以判斷策略在這個環境是否有效。',
                          [regev, nev] + ([('m', base + 'oos.%s.n' % code, '樣本外筆數', 'int')] if split else []), J('#regBody .rg-tbl', '分環境績效表'), 'warn')
        pf = (bd['is'][code] or {}).get('pf') or 0
        ev = [regev, nev, ('pf', base + 'is.%s.pf' % code, '樣本內淨 PF', 'pf'), ('avg', base + 'is.%s.avg' % code, '平均每筆', 'n2')]
        t = who + '目前環境「{reg}」：樣本內 {n} 筆，淨 PF {pf}、平均每筆 {avg}%（扣成本）。' + ('歷史上在這個環境沒有正的期望。' if pf <= 1 else '樣本內淨 PF > 1。')
        if split and pf > 1:
            m = (bd['oos'].get(code) or {}).get('n', 0); opf = (bd['oos'].get(code) or {}).get('pf') or 0
            ev += [('m', base + 'oos.%s.n' % code, '樣本外筆數', 'int'), ('opf', base + 'oos.%s.pf' % code, '樣本外淨 PF', 'pf')]
            t += (' 樣本外在這個環境只有 {m} 筆，不足以確認。' if m < SAMPLE_OK else (' 樣本外 {m} 筆、淨 PF {opf}，方向一致。' if opf > 1 else ' 樣本外 {m} 筆、淨 PF {opf}，沒有延續。'))
        return B.item('sup_' + basis, t, ev, J('#regBody .rg-tbl', '分環境績效表'))
    if ntr == 0:
        items.append(B.item('sup_none', '沒有交易，無法評估目前環境下的歷史表現。', [], None, 'warn'))
    elif blocked or unknown_q:
        items.append(B.item('sup_blocked', '資料過期、異常或未檢查，不評估目前環境下的歷史表現。', [], None, 'warn'))
    else:
        for basis, who in (('own', '標的自身'), ('market', '大盤')):
            it = support(basis, code if basis == 'own' else cur.get('market'), who)
            if it: items.append(it)
        if not items: items.append(B.item('sup_na', '目前沒有可對應的環境分類，無法評估。', [], None, 'warn'))
    sections.append({'id': 'support', 'title': '目前環境下，歷史交易夠不夠支持判斷', 'items': items})

    # 5. 濾網
    f = study.get('filter'); items = []; improved = False
    if f:
        if f.get('status') != 'ok':
            items.append(B.item('flt_na', '濾網對照資料不足：{why}', [('why', 'study.filter.reason', '原因', 'str')], J('#regBody .rg-filter', '濾網對照'), 'warn'))
        else:
            nb = f['B']['is']['trades']; ev = [('nb', 'study.filter.B.is.trades', '濾網後樣本內筆數', 'int'), ('na', 'study.filter.A.is.trades', '原始樣本內筆數', 'int'), ('pb', 'study.filter.B.is.pf', '濾網後淨 PF', 'pf'), ('pa', 'study.filter.A.is.pf', '原始淨 PF', 'pf'), ('al', 'study.filter.allowLabels', '所選環境', 'str')]
            if nb < SAMPLE_OK: items.append(B.item('flt_is', '濾網（只在 {al} 進場）後樣本內只剩 {nb} 筆（原始 {na} 筆），資料不足，不下結論。', ev, J('#regBody .rg-filter', '濾網對照'), 'warn'))
            elif f['B']['is']['pf'] > f['A']['is']['pf']:
                improved = True; items.append(B.item('flt_is', '樣本內：濾網（只在 {al} 進場）後淨 PF {pb}（{nb} 筆），高於原始的 {pa}（{na} 筆）。這只是樣本內，而且條件是你自己選的。', ev, J('#regBody .rg-filter', '濾網對照')))
            else: items.append(B.item('flt_is', '樣本內：濾網（只在 {al} 進場）後淨 PF {pb}（{nb} 筆），沒有高於原始的 {pa}（{na} 筆），沒有改善。', ev, J('#regBody .rg-filter', '濾網對照')))
            o = f.get('oos') or {}
            if o.get('unavailable'): items.append(B.item('flt_oos', '沒有獨立樣本外，所以沒有樣本外證據。', [], None, 'warn'))
            elif not o.get('revealed'):
                items.append(B.item('flt_oos', '樣本外尚未揭露：目前沒有樣本外證據支持這個濾網' + ('；樣本內看起來改善不代表有效。' if improved else '。'), [('rv', 'study.filter.oos.revealed', '樣本外已揭露', 'str')], J('#regBody .rg-filter', '濾網對照'), 'warn'))
            else:
                nbo = o['B']['trades']; ev = [('nbo', 'study.filter.oos.B.trades', '濾網後樣本外筆數', 'int'), ('pbo', 'study.filter.oos.B.pf', '濾網後樣本外淨 PF', 'pf'), ('pao', 'study.filter.oos.A.pf', '原始樣本外淨 PF', 'pf')]
                if not improved: items.append(B.item('flt_oos', '樣本內沒有改善（或樣本不足），不需要、也不應該用樣本外替這個濾網背書。', [], J('#regBody .rg-filter', '濾網對照')))
                elif nbo < SAMPLE_OK: items.append(B.item('flt_oos', '樣本外濾網後只有 {nbo} 筆（樣本不足）：不足以確認樣本內的改善，仍不能說濾網有效。', ev, J('#regBody .rg-filter', '濾網對照'), 'warn'))
                elif o['B']['pf'] > o['A']['pf'] and o['B']['pf'] >= 1: items.append(B.item('flt_oos', '樣本外：濾網後淨 PF {pbo}（{nbo} 筆）高於原始的 {pao} 且 ≥ 1，方向與樣本內一致，有一定證據支持；但仍是歷史統計。', ev, J('#regBody .rg-filter', '濾網對照')))
                else: items.append(B.item('flt_oos', '樣本外：濾網後淨 PF {pbo}（{nbo} 筆），沒有高於原始的 {pao}（或 < 1）：樣本內的改善沒有延續到樣本外。', ev, J('#regBody .rg-filter', '濾網對照'), 'warn'))
        tr = root['trials'] or {}
        if tr.get('count', 0) >= 3: items.append(B.item('flt_trials', '你已試過 {c} 個條件：試得越多，樣本內「碰巧好看」的機會越大（多重比較）。', [('c', 'trials.count', '已試條件數', 'int')], None, 'warn'))
        if tr.get('revealed', 0) >= 2: items.append(B.item('flt_rev', '已對 {r} 個條件揭露過樣本外，樣本外已不再獨立。', [('r', 'trials.revealed', '已揭露條件數', 'int')], None, 'warn'))
        sections.append({'id': 'filter', 'title': '市場濾網對照', 'items': items})

    # 標題結論(只有四種,全部是描述或降級,沒有任何買賣結論)
    if blocked:
        head = B.item('head', '【資料過期或異常】策略所用資料品質為「{q}」：不評估目前環境，以下只是歷史狀態的描述。', [('q', 'study.dataQuality.label', '資料品質', 'str')], J('#regBody .rg-head', '資料與窗口')); lv = 'blocked'
    elif unknown_q:
        head = B.item('head', '【資料品質未檢查】沒有品質檢查結果，不下結論；以下只是描述。', [], None); lv = 'insufficient'
    elif ntr == 0:
        head = B.item('head', '【沒有交易】此策略在窗口內沒有任何交易，無法評估，也不做推論。', [], J('#regBody .rg-tbl', '績效表')); lv = 'notrades'
    elif (isb.get('trades') or 0) < SAMPLE_OK:
        head = B.item('head', '【樣本不足】樣本內只有 {n} 筆交易（少於 20 筆）：下列數字只是描述，不能當成策略有效或無效的證據。', [('n', 'study.overall.is.trades', '樣本內筆數', 'int')], J('#regBody .rg-tbl', '績效表')); lv = 'insufficient'
    else:
        head = B.item('head', '【描述性摘要】目前標的自身環境為「{reg}」；樣本內 {n} 筆、淨 PF {pf}。以下逐項說明依據與限制；這不是預測或買賣訊號。',
                      [('reg', 'study.currentRegime.own', '自身環境', 'regime'), ('n', 'study.overall.is.trades', '樣本內筆數', 'int'), ('pf', 'study.overall.is.pf', '樣本內淨 PF', 'pf')], None); lv = 'descriptive'
    return {'headline': dict(head, level=lv, levelLabel=LEVEL_LABEL[lv]), 'sections': sections, 'rules': RULES, 'disclaimer': DISCLAIMER, 'engine': {'ai': False, 'kind': 'fixed-rules', 'paid': False},
            'asOfUtc': study.get('asOfUtc'), 'symbol': study.get('symbol'), 'strategy': study.get('strategy')}
