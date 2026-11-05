# -*- coding: utf-8 -*-
"""D2 階段三:無法可靠歸屬的 121 筆交易 —— 用『訊號重現』檢驗每個候選策略(只用狀態檔/設定備份裡出現過的策略)。
每個候選各自單獨重播(同一套機器人邏輯),實盤交易若能在進場(±1 根)與出場(±1 小時)都被某候選重現,就算『被該候選重現』。
這只是『證據』,不是帳務標記:被一個候選獨佔重現 → 推定歸屬(inferred);多個候選都重現 → 模稜兩可;沒有候選重現 → 無法解釋。結果不寫回任何策略績效表。"""
import collections, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d2_common import *
M, data = load_market(); sigs = load_signals(); EX = exit_params()
S_ = lambda ms: datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')
CAND = {'AAVE/USDT': [('4h', 'ppo_cross'), ('4h', 'cmf_zero')], 'BNB/USDT': [('4h', 'cmf'), ('4h', 'ttm')], 'XRP/USDT': [('1h', 'cci'), ('1h', 'vortex')],
        'PAXG/USDT': [('4h', 'supertrend'), ('4h', 'lrs'), ('4h', 'trix_signal'), ('4h', 'inside_break')], 'PYTH/USDT': [('4h', 'week_hl'), ('4h', 'fisher_zero')], 'SOL/USDT': [('4h', 'force'), ('4h', 'ema_8_21'), ('4h', 'ssl_channel')]}
T0 = int(datetime.datetime(2026, 6, 22, 12, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000); T1 = M.h['TRX/USDT'][0][-1] + HOUR
live = [t for t in live_trips() if t['attr'] == 'unknown']
tfms = {'1h': HOUR, '4h': 4 * HOUR}; P = S.default_params(EX, slip_entry=0.0003, slip_exit=0.0001, slip_stop=0.00042, sumw_override=1.0)
cand_res = {}; cover = collections.defaultdict(list)
for sym, cands in CAND.items():
    ul = [t for t in live if t['symbol'] == sym]
    for tf, st in cands:
        if (sym, tf, st) not in sigs: cand_res['%s|%s|%s' % (sym, tf, st)] = {'error': 'no signals'}; continue
        res = S.run(M, sigs, [(T0, [{'symbol': sym, 'timeframe': tf, 'strategy': st, 'weight': 1}])], T0, T1, P, 300.0, equity_marks=False)
        sim = res['trades']; hit = 0
        for t in ul:
            ok = any(abs(s['entry_ts'] - t['entry_ts']) <= tfms[tf] and t['closed'] and abs(s['exit_ts'] - t['exit_ts']) <= HOUR * 1.01 for s in sim)
            if ok: hit += 1; cover[id(t)].append(st)
        cand_res['%s|%s|%s' % (sym, tf, st)] = {'sim_trips': len(sim), 'live_unknown_trips_of_symbol': len(ul), 'reproduced': hit}
cls = collections.Counter(); net = collections.defaultdict(float); bysym = collections.defaultdict(lambda: collections.Counter()); inferred = collections.Counter()
for t in live:
    c = cover.get(id(t), []); k = 'unexplained' if not c else ('single_candidate' if len(c) == 1 else 'ambiguous')
    cls[k] += 1; net[k] += t['net']; bysym[t['symbol']][k] += 1
    if k == 'single_candidate': inferred[(t['symbol'], c[0])] += 1
out = {'unknown_trips': len(live), 'classification': dict(cls), 'net_by_class': {k: round(v, 3) for k, v in net.items()}, 'by_symbol': {k: dict(v) for k, v in bysym.items()}, 'candidates': cand_res,
       'inferred_single_candidate': {'%s|%s' % k: v for k, v in sorted(inferred.items())}, 'caveat': '訊號重現只是證據:被重現不代表帳務上就是該策略(不同策略可能在同一根 K 棒產生相同進出場)。實盤歸屬表仍把這 %d 筆列為「無法可靠歸屬」。' % len(live)}
json.dump(out, open(os.path.join(HERE, 'results', 'attribution_reproduction.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
