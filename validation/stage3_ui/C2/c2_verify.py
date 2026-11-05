# -*- coding: utf-8 -*-
"""C2 驗證(離線重播 snapshot.json):BTC/USDT、SOL/USDT、2330.TW、AAPL。
1. 原始策略(未加濾網)的績效 = 直接呼叫既有 run_backtest + _perf_block 的數字(也就是排名/分析用的同一條路徑)。
2. 環境分類無前視:把資料截到不同時間點重算,截止點之前的每一根分類、以及截止點之前進場的每一筆交易的環境歸屬,都和用全部資料算出來的一模一樣。
3. 輸出各標的的環境佔比、樣本內/樣本外分環境績效、濾網對照(樣本內),寫入 c2_verify_report.json 與 c2_tables.md。
"""
import datetime, json, os, sys, warnings
warnings.filterwarnings('ignore'); os.environ.setdefault('RENDER', 'true')
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); os.chdir(ROOT)
import app as A, sim
import market_regime as MR, regime_study as RS

S = json.load(open(os.path.join(HERE, 'snapshot.json'))); ROWS = S['rows']
NOW = datetime.datetime.fromisoformat(S['__now__']).replace(microsecond=0)
A.CCXT_AVAILABLE = True; A._utcnow = lambda: NOW
A.fetch_data = lambda s, st, interval='1d': ROWS['%s|%s' % (s, interval)]
c = A.app.test_client()
CASES = [('BTC/USDT', '4h', 'sixline'), ('SOL/USDT', '4h', 'sixline'), ('BTC/USDT', '1d', 'diadx'), ('SOL/USDT', '1d', 'diadx'), ('2330.TW', '1d', 'diadx'), ('AAPL', '1d', 'tsmom')]
rep = {'checks': [], 'cases': []}; md = ['# C2 驗證表格（離線快照 %s）' % NOW.strftime('%Y-%m-%d %H:%M UTC'), '']
LAB = MR.LABEL
bad = 0

for sym, tf, strat in CASES:
    rows = ROWS['%s|%s' % (sym, tf)]
    q = dict(symbol=sym, timeframe=tf, strategy=strat, period='2y')
    d = c.get('/api/regime_study', query_string=q).get_json()
    ws = NOW - datetime.timedelta(days=730); ck = sim.cost_kwargs(sym, strat); split = A.is_oos_split(rows, ws, NOW)
    # 1) 原始策略數字 = 既有流程
    res = A.run_backtest(rows, strategy=strat, risk_pct=0.015, timeframe=tf, **ck)
    full_t = [t for t in res[2]['trade_log'] if not t.get('open') and t.get('entry_date') and t['entry_date'] >= ws]
    ref_all = A._perf_block(full_t, res[0], res[1], ws)
    r2 = A.run_backtest(rows[:split['idx_b']], strategy=strat, risk_pct=0.015, timeframe=tf, **ck)
    is_t = [t for t in r2[2]['trade_log'] if not t.get('open') and t.get('entry_date') and t['entry_date'] >= ws]
    ref_is = A._perf_block(is_t, r2[0], r2[1], ws)
    _, oos_t, _, _ = A.partition_trades(res[2]['trade_log'], ws, split['boundary_dt']); ref_oos = A._perf_block(oos_t, res[0], res[1], split['boundary_dt'])
    eq = d['overall']['all'] == ref_all and d['overall']['is'] == ref_is and d['overall']['oos'] == ref_oos
    # 2) 無前視:截斷重算
    codes = MR.classify_series(rows); causal = True; attr_ok = True; checked = 0
    for cut in (0.35, 0.55, 0.8):
        n = int(len(rows) * cut); sub = rows[:n]
        causal &= MR.classify_series(sub) == codes[:n]
        r3 = A.run_backtest(sub, strategy=strat, risk_pct=0.015, timeframe=tf, **ck)
        if not r3: continue
        sc = MR.classify_series(sub)
        full_by = {t['entry_i']: t for t in res[2]['trade_log']}
        for t in r3[2]['trade_log']:
            i = t['entry_i']
            if i in full_by:
                checked += 1; attr_ok &= (sc[i - 1] == codes[i - 1])
    ok = eq and causal and attr_ok; bad += (not ok)
    rep['checks'].append({'symbol': sym, 'tf': tf, 'strategy': strat, 'original_equals_existing_pipeline': eq, 'classification_prefix_invariant': causal, 'trade_attribution_same_when_truncated': attr_ok, 'trades_checked': checked})
    print(sym, tf, strat, 'OK' if ok else 'MISMATCH', 'eq', eq, 'causal', causal, 'attr', attr_ok, 'checked', checked, flush=True)
    # 3) 表格
    md += ['## %s · %s · %s' % (sym, tf, d['strategyName']), '', '參考大盤：%s（%s）；窗口 %s ～ %s；切分日 %s' % (d['reference'].get('name') or '—', d['reference'].get('reason') or ('支援' if d['reference']['supported'] else ''), d['windowStart'], NOW.strftime('%Y-%m-%d'), (d['split'] or {}).get('boundary')), '']
    for b in ('own', 'market'):
        if not d['breakdown'][b]: continue
        sh = d['share'][b]
        md += ['**%s環境**（窗口內佔比：%s）' % ('標的自身' if b == 'own' else '大盤', '、'.join('%s %.1f%%' % (LAB[k], sh[k]['pct']) for k in MR.CODES if sh[k]['bars'])), '', '| 區段 | 環境 | 筆數 | 分級 | 平均每筆% | 合計報酬% | 淨PF | 勝率% | 最大回撤% |', '|---|---|---|---|---|---|---|---|---|']
        for seg in ('is', 'oos'):
            for k in ('all',) + MR.CODES:
                s = d['breakdown'][b][seg][k]
                if k == 'na' and not s['n']: continue
                md.append('| %s | %s | %d | %s | %s | %s | %s | %s | %s |' % ('樣本內' if seg == 'is' else '樣本外', '整體' if k == 'all' else LAB[k], s['n'], RS.TIER_LABEL[s['tier']] if k != 'all' else '', *[('—' if s[x] is None else s[x]) for x in ('avg', 'total', 'pf', 'win', 'mdd')]))
        md.append('')
    # 濾網(樣本內)
    cand = d['candidate']
    d2 = c.get('/api/regime_study', query_string=dict(q, allow='up,transition', basis='own')).get_json(); f = d2['filter']
    md += ['**濾網對照（樣本內，只在「上升趨勢＋趨勢轉換中」允許新進場，標的自身環境）**：A %d 筆 PF %s / 報酬 %s%% / MDD %s%%；B %d 筆 PF %s / 報酬 %s%% / MDD %s%% %s' % (
        f['A']['is']['trades'], f['A']['is']['pf'], f['A']['is']['total'], f['A']['is']['mdd'], f['B']['is']['trades'], f['B']['is']['pf'], f['B']['is']['total'], f['B']['is']['mdd'], ('— ' + f['isNote']) if f['isNote'] else ''),
           '樣本內候選環境（只看樣本內）：%s' % ('、'.join(LAB[x] for x in cand['regimes']) if cand['regimes'] else '無'), '']
    rep['cases'].append({'symbol': sym, 'tf': tf, 'strategy': strat, 'overall': d['overall'], 'candidate': cand['regimes']})

rep['mismatches'] = bad
json.dump(rep, open(os.path.join(HERE, 'c2_verify_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
open(os.path.join(HERE, 'c2_tables.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
print('total mismatches:', bad)
