# -*- coding: utf-8 -*-
"""D2 投資組合層級模擬器(離線)。逐步照機器人 portfolio_bot.py 的邏輯(唯讀對照原始碼)重建:
- 資金:cap = 錢包 + 未實現(機器人用 fetch_balance 的 total);每組 alloc = cap × 權重 / Σ權重;單筆數量 = min(alloc×risk/停損距離, alloc×槓桿上限/價格),再依交易所步長『無條件捨去』,小於步長或最小名目就不下單。
- 訊號:每根已收盤 K 棒用最近 400 根算 el[-1]、xl[-1]、ATR[-1](預先算好,signals.pkl)。進場價(記帳)= 訊號棒收盤;成交 = 下一根開盤 × (1+進場滑價)。
- 出場:先更新移動停損(ATR 系:peak − trail×ATR,只往上)→ 以『已收盤 K』判斷 停損(L<=stop)/停利(H>=tp)/訊號出場(xl)→ 市價賣(下一根開盤 × (1−滑價))。
- 交易所端保護停損 = 邏輯停損 × 0.995(STOP_MARKET,盤中觸發,成交 = min(觸發價, 開盤) × (1−停損滑價));以 1H K 棒偵測。
- 成本:吃單手續費(進出各一次)、資金費率(實際歷史費率 × 持倉名目)。
- 多組同一根 K 棒的訊號:同一輪、依設定順序處理,同一個 `cap`;可用保證金預檢用輪初的快照(與機器人相同)。
無法重建的條件(都列在報告的假設表):機器人斷線/漏輪(除非提供日誌的輪詢時間)、連敗斷路器(日誌從未觸發,假設不啟用)、實際的滑價分布、交易所拒單、手動操作。"""
import bisect, collections, math, os, pickle

HOUR = 3600000; TFMS = {'1h': HOUR, '4h': 4 * HOUR}


class Market:
    def __init__(self, data):
        self.c = data['candles']; self.mk = data['markets']; self.fund = data['funding']
        self.h = {}                                      # sym → (ts[], o[], h[], l[], c[]) 1H
        for (s, tf), rows in self.c.items():
            if tf == '1h' and rows:
                self.h[s] = ([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows], [r[4] for r in rows])
        self.bars = {}                                   # (sym,tf) → {ts: (o,h,l,c)}
        for (s, tf), rows in self.c.items(): self.bars[(s, tf)] = {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}

    def open_px(self, s, t):
        ts, o, _, _, c = self.h[s]; i = bisect.bisect_right(ts, t - t % HOUR) - 1
        if i < 0: return None
        return o[i] if ts[i] == t - t % HOUR else c[i]

    def close_px(self, s, t_end):                         # t_end 是整點;回傳上一根 1H 的收盤
        ts, _, _, _, c = self.h[s]; i = bisect.bisect_right(ts, t_end - HOUR) - 1
        return c[i] if i >= 0 else None

    def candle(self, s, t):                               # 開盤時間 t 的 1H K 棒 (o,h,l,c) 或 None
        ts, o, h, l, c = self.h[s]; i = bisect.bisect_left(ts, t)
        return (o[i], h[i], l[i], c[i]) if i < len(ts) and ts[i] == t else None

    def step_min(self, s):
        m = self.mk.get(s, {}); return float(m.get('step') or 0), float(m.get('min_cost') or 5.0)


def floor_step(q, step):
    return math.floor(q / step + 1e-9) * step if step > 0 else q


def run(M, signals, timeline, T0, T1, P, init_wallet, deposits=(), loop_times=None, entry_guard=None, max_entries_per_cycle=None, restrict_symbols=None, equity_marks=True):
    """timeline = [(start_ts, [combo dict(symbol, timeframe, strategy, weight)...]), ...](設定更換/重啟時間);回傳 dict(trades, equity, ...)。"""
    wallet = float(init_wallet); pos = {}; trades = []; marks = []; funding_rec = collections.defaultdict(float)
    last_bar = {}; rejected = collections.Counter(); notes = collections.Counter()
    cycles = []                                           # (tau, combo_index, key, bar_ts)
    epochs = []                                           # (start, end, combos)
    for i, (st, combos) in enumerate(timeline):
        en = timeline[i + 1][0] if i + 1 < len(timeline) else T1 + 1
        epochs.append((max(st, T0), min(en, T1 + 1), combos))
    def key_of(c): return '%s|%s|%s' % (c['symbol'], c['timeframe'], c['strategy'])
    lat = P.get('latency_s', 13.8) * 1000
    def tau_of(b):
        if not loop_times or b < loop_times[0]: return int(b + lat)          # 沒有日誌輪詢時間(日誌之前)→ 假設機器人一直在線,收盤後約 13.8 秒處理
        j = bisect.bisect_left(loop_times, b); return loop_times[j] if j < len(loop_times) else None
    for ei, (a, b_end, combos) in enumerate(epochs):
        for ci, c in enumerate(combos):
            k = key_of(c); step = TFMS[c['timeframe']]; sig = signals.get((c['symbol'], c['timeframe'], c['strategy']))
            if sig is None: continue
            for bt in sorted(sig):
                close = bt + step
                if close < a or close >= b_end: continue
                tau = tau_of(close)
                if tau is None or tau >= b_end + HOUR: continue
                cycles.append((tau, ei, ci, k, bt))
    # 重啟後『新出現的組合』:機器人第一次看到它,會立刻評估『最新一根已收盤 K 棒』(lb is None → new_idx=[最新一根]),所以重啟當下就可能進場
    for ei, (a, b_end, combos) in enumerate(epochs):
        if ei == 0: continue
        prev = {key_of(c) for c in epochs[ei - 1][2]}
        for ci, c in enumerate(combos):
            k = key_of(c)
            if k in prev: continue
            step = TFMS[c['timeframe']]; sig = signals.get((c['symbol'], c['timeframe'], c['strategy']))
            if not sig: continue
            cand = [bt for bt in sig if bt + step <= a]
            if cand:
                tau = tau_of(a)
                if tau is not None: cycles.append((tau, ei, ci, k, max(cand)))
    cycles = sorted(set(cycles), key=lambda x: (x[0], x[1], x[2], x[4]))
    # 設定更換:被移除/換掉的組合,殘倉在重啟時被機器人平掉(orphan cleanup / 目標歸零)
    switches = [(a, ei) for ei, (a, _, _) in enumerate(epochs) if ei > 0]
    dep = sorted(deposits)

    def equity_at(t):
        e = wallet
        for p in pos.values():
            px = M.open_px(p['sym'], t)
            if px: e += p['qty'] * (px - p['fill'])
        return e

    def record_trade(p, t, px, why):
        nonlocal wallet
        fee = p['qty'] * px * P['taker']; gross = p['qty'] * (px - p['fill'])
        wallet += gross - fee
        trades.append({'key': p['key'], 'sym': p['sym'], 'tf': p['tf'], 'entry_ts': p['t'], 'exit_ts': int(t), 'qty': p['qty'], 'entry_fill': p['fill'], 'exit_fill': px, 'notional': p['qty'] * p['fill'],
                       'gross': gross, 'fees': p['fee_in'] + fee, 'funding': p['funding'], 'net': gross - p['fee_in'] - fee + p['funding'], 'why': why, 'sig_px': p['sig_px']})
        del pos[p['key']]

    def scan_stops(h):                                    # 掃描 [h-1h, h) 這根 1H:交易所保護停損是否被打到
        for k in list(pos):
            p = pos[k]
            if p['scan_from'] > h - HOUR: continue
            cd = M.candle(p['sym'], h - HOUR)
            if not cd: continue
            o_, h_, l_, c_ = cd
            if l_ <= p['exch_stop']:
                fill = min(p['exch_stop'], o_) * (1 - P['slip_stop'])
                record_trade(p, h - HOUR / 2, fill, '交易所保護停損'); notes['exchange_stop_exit'] += 1

    def apply_funding(h):
        for k, p in list(pos.items()):
            fr = M.fund.get(p['sym'])
            if not fr: continue
            ts = P.setdefault('_fts', {}).setdefault(p['sym'], [x[0] for x in fr])
            i = bisect.bisect_right(ts, h - HOUR)
            while i < len(ts) and ts[i] <= h:
                px = M.open_px(p['sym'], ts[i]) or p['fill']; amt = -p['qty'] * px * fr[i][1]
                wallet_add(amt); p['funding'] += amt; funding_rec[p['key']] += amt; i += 1

    def wallet_add(x):
        nonlocal wallet
        wallet += x

    def do_cycle(tau, items):
        nonlocal wallet
        h = tau - tau % HOUR; cap = equity_at(tau)
        # 目前這個設定的 Σ權重
        ei = items[0][1]; combos = epochs[ei][2]; sumw = P.get('sumw_override') or (sum(c.get('weight', 1) for c in combos) or 1)
        free = wallet - sum(p['qty'] * p['fill'] for p in pos.values()) / P['max_lev_int']
        cands = []; ncycle_entries = 0
        by_combo = collections.OrderedDict()
        for (_, ei2, ci, k, bt) in items: by_combo.setdefault((ci, k), []).append(bt)
        for (ci, k), bts in by_combo.items():
            c = epochs[ei][2][ci]; sym, tf, strat = c['symbol'], c['timeframe'], c['strategy']
            if restrict_symbols is not None and k.split('|')[0] not in restrict_symbols: continue
            sig = signals[(sym, tf, strat)]; sd = P['exit'][strat]
            aStop, aTrail, aTP, pStop, pTrail, pTP = sd; usePct = (pStop > 0 or pTrail > 0 or pTP > 0)
            for n, bt in enumerate(sorted(bts)):
                el, xl, atr = sig[bt]; o_, hi, lo, cl = M.bars[(sym, tf)][bt]
                p = pos.get(k)
                if p is not None:
                    p['peak'] = max(p['peak'], hi)
                    if pTrail > 0: ns = p['peak'] * (1 - pTrail); p['stop'] = ns if p['stop'] is None else max(p['stop'], ns)
                    elif aTrail > 0 and atr: ns = p['peak'] - aTrail * atr; p['stop'] = ns if p['stop'] is None else max(p['stop'], ns)
                    out = None
                    if p['stop'] is not None and lo <= p['stop']: out = '停損/鎖利(收盤判定)'
                    elif p['tp'] is not None and hi >= p['tp']: out = '停利(收盤判定)'
                    elif xl: out = '訊號出場'
                    if out:
                        px = (M.open_px(sym, tau) or cl) * (1 - P['slip_exit']); record_trade(p, tau, px, out); continue
                    p['exch_stop'] = (p['stop'] * 0.995) if p['stop'] else p['entry_sig'] * 0.85
                    p['scan_from'] = h
                # 進場只看本輪最後一根
                if n == len(bts) - 1 and k not in pos and el:
                    cands.append((c, k, bt, (cl, atr, hi)))
        # 進場(可套用情境的限制)
        order = sorted(cands, key=lambda x: -x[0].get('weight', 1)) if max_entries_per_cycle else cands      # 情境 D:同一輪太多進場時,權重大的優先(穩定排序,同權重依設定順序)
        for (c, k, bt, (cl, atr, hi)) in order:
            if max_entries_per_cycle is not None and ncycle_entries >= max_entries_per_cycle: rejected['guard_max_entries'] += 1; continue
            sym, tf, strat = c['symbol'], c['timeframe'], c['strategy']; aStop, aTrail, aTP, pStop, pTrail, pTP = P['exit'][strat]; usePct = (pStop > 0 or pTrail > 0 or pTP > 0)
            alloc = cap * c.get('weight', 1) / sumw; price = cl
            sdist = (pStop * price) if (usePct and pStop > 0) else (aStop * atr if (aStop > 0 and atr) else 0)
            if not atr or sdist <= 0: continue
            qty = min(alloc * P['risk'] / sdist, alloc * P['max_lev'] / price)
            notional_all = sum(p['qty'] * (M.open_px(p['sym'], tau) or p['fill']) for p in pos.values())
            if (notional_all + qty * price) > cap * P['max_total']: qty = max(0.0, (cap * P['max_total'] - notional_all) / price); notes['total_cap_scaled'] += 1
            if entry_guard is not None and not entry_guard(cap, notional_all, qty * price, pos):
                rejected['guard_exposure'] += 1; continue
            step, min_cost = M.step_min(sym)
            need = qty * price / P['max_lev_int']
            if need > free * 0.9:
                afford = (free * 0.9 * P['max_lev_int']) / price
                if afford < step or afford <= 0: rejected['margin'] += 1; continue
                qty = min(qty, afford)
            qty = floor_step(qty, step)
            if qty <= 0 or (step and qty < step): rejected['below_step'] += 1; continue
            if qty * price < min_cost: rejected['below_min_notional'] += 1; continue
            fill = (M.open_px(sym, tau) or price) * (1 + P['slip_entry']); fee = qty * fill * P['taker']; wallet -= fee
            stop = None if not (pStop > 0 or aStop > 0) else (price * (1 - pStop) if usePct else price - aStop * atr)
            tp = (price * (1 + pTP) if (usePct and pTP > 0) else (price + aTP * atr if aTP > 0 else None))
            pos[k] = {'key': k, 'sym': sym, 'tf': tf, 'qty': qty, 'fill': fill, 'entry_sig': price, 'sig_px': price, 'stop': stop, 'tp': tp, 'peak': hi, 't': int(tau), 'fee_in': fee, 'funding': 0.0,
                      'exch_stop': (stop * 0.995) if stop else price * 0.85, 'scan_from': h}
            ncycle_entries += 1

    # 主迴圈:逐小時
    hours = list(range((T0 - T0 % HOUR), T1 + HOUR, HOUR)); ci_ptr = 0; sw_ptr = 0; dep_ptr = 0
    for h in hours:
        scan_stops(h)                                                       # [h-1h, h) 的盤中停損
        apply_funding(h)
        while dep_ptr < len(dep) and dep[dep_ptr][0] <= h: wallet += dep[dep_ptr][1]; dep_ptr += 1
        while sw_ptr < len(switches) and switches[sw_ptr][0] < h + HOUR:    # 設定更換:不在新設定裡的組合,殘倉平掉
            st_t, ei = switches[sw_ptr]; newkeys = {key_of(c) for c in epochs[ei][2]}
            for k in list(pos):
                if k not in newkeys:
                    px = (M.open_px(pos[k]['sym'], max(st_t, h)) or pos[k]['fill']) * (1 - P['slip_exit']); record_trade(pos[k], max(st_t, h), px, '設定更換/重啟:殘倉平倉')
            sw_ptr += 1
        if equity_marks:
            e = wallet; expo = 0.0
            for p in pos.values():
                px = M.close_px(p['sym'], h)
                if px: e += p['qty'] * (px - p['fill']); expo += p['qty'] * px
            marks.append((h, e, wallet, expo, len(pos)))
        group = collections.OrderedDict()
        while ci_ptr < len(cycles) and cycles[ci_ptr][0] < h + HOUR:
            c0 = cycles[ci_ptr]
            if c0[0] >= T0: group.setdefault(c0[0], []).append(c0)
            ci_ptr += 1
        for tau in sorted(group): do_cycle(tau, group[tau])
    # 期末:未平倉
    e_end = wallet; open_pos = []
    for p in pos.values():
        px = M.close_px(p['sym'], hours[-1] + HOUR) or p['fill']; e_end += p['qty'] * (px - p['fill']); open_pos.append({'key': p['key'], 'unrealized': p['qty'] * (px - p['fill']), 'notional': p['qty'] * px})
    return {'trades': trades, 'marks': marks, 'wallet_end': wallet, 'equity_end': e_end, 'open': open_pos, 'rejected': dict(rejected), 'notes': dict(notes)}


def default_params(exit_params, **kw):
    P = {'risk': 0.0403, 'max_lev': 3.0, 'max_lev_int': 3, 'max_total': 3.0, 'taker': 0.0005, 'slip_entry': 0.0003, 'slip_exit': 0.0003, 'slip_stop': 0.0005, 'latency_s': 13.8, 'exit': exit_params}
    P.update(kw); return P
